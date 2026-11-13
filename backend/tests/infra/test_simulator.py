"""Behavior and trust-boundary checks for the B2-09 simulator."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from jsonschema import ValidationError
import pytest
import yaml

from simulator.control import make_control
from simulator.model import Simulator, TELEMETRY, strict_json, utc
from simulator.runtime import MqttSimulator

ROOT = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 10, 14, 12, tzinfo=timezone.utc)


@pytest.fixture
def catalog():
    return json.loads((ROOT / 'simulator/catalog.example.json').read_text())


def runtime(catalog):
    return MqttSimulator(Simulator(catalog), host='localhost', port=1883, password='unit-only')


def control(**updates):
    value = make_control('sim-lab-01', 'start')
    value.update(issued_at=utc(NOW), expires_at=utc(NOW + timedelta(seconds=30)))
    value.update(updates)
    return json.dumps(value).encode()


def values(event):
    return {key: measurement['value'] for key, measurement in event['data']['measurements'].items()}


def test_reproducible_sensor_values_and_distinct_catalog_ids(catalog):
    first, second = Simulator(catalog, 7), Simulator(catalog, 7)
    for _ in range(20):
        a, b = first.sample(60, NOW), second.sample(60, NOW)
        TELEMETRY.validate(a)
        assert a['data'] == b['data']
        assert a['event_id'] == a['correlation_id']
        assert a['received_at'] is None
        assert a['occurred_at'].endswith('Z')
        assert {item['sensor_id'] for item in a['data']['measurements'].values()} == set(catalog['sensors'].values())
        assert len(a['data']['measurements']) == 6
    assert values(first.sample(1, NOW)) != values(Simulator(catalog, 8).sample(1, NOW))


@pytest.mark.parametrize('fault', ['bearing_wear', 'imbalance'])
def test_gradual_failure_changes_motor_variables_and_cooling(catalog, fault):
    healthy, failing = Simulator(catalog, 9), Simulator(catalog, 9)
    failing.inject_fault(fault)
    initial = values(failing.sample(1, NOW))
    healthy.sample(1, NOW)
    # Fault injection changes the rate, not the instantaneous measured state.
    assert initial['vibration'] < 1
    for _ in range(60):
        good = healthy.sample(60, NOW)
        bad = failing.sample(60, NOW)
    good_values, bad_values = values(good), values(bad)
    for key in ('vibration', 'motor_current', 'motor_temperature', 'ambient_temperature'):
        assert bad_values[key] > good_values[key] + 0.5
    assert bad_values['humidity'] == good_values['humidity']
    assert bad_values['light'] == good_values['light']
    assert not any(key in json.dumps(bad) for key in ('labels', 'health_score_true', 'rul_hours_true', 'bearing_wear', 'imbalance'))


def test_long_run_stays_finite_in_contract(catalog):
    simulator = Simulator(catalog)
    simulator.inject_fault('bearing_wear')
    simulator.inject_fault('imbalance')
    for _ in range(100):
        TELEMETRY.validate(simulator.sample(3600, NOW))
    assert simulator.bearing_wear == simulator.imbalance == 1


@pytest.mark.parametrize('step', [0, -1, 3601, float('nan'), float('inf'), True])
def test_invalid_steps_do_not_change_state(catalog, step):
    simulator = Simulator(catalog)
    with pytest.raises(ValueError):
        simulator.sample(step, NOW)
    assert simulator.elapsed_seconds == simulator.bearing_wear == simulator.imbalance == 0


@pytest.mark.parametrize('mutation', ['duplicate_sensor', 'missing_sensor', 'uuid', 'device', 'extra', 'duplicate_actuator'])
def test_catalog_rejects_invalid_registration(catalog, mutation):
    if mutation == 'duplicate_sensor':
        catalog['sensors']['vibration'] = catalog['sensors']['humidity']
    elif mutation == 'missing_sensor':
        del catalog['sensors']['humidity']
    elif mutation == 'uuid':
        catalog['equipment_id'] = 'not-a-uuid'
    elif mutation == 'device':
        catalog['device_id'] = 'bad/+/topic'
    elif mutation == 'extra':
        catalog['labels'] = {}
    else:
        catalog['actuators']['buzzer'] = catalog['actuators']['led']
    with pytest.raises((ValueError, ValidationError)):
        Simulator(catalog)


@pytest.mark.parametrize('payload', [b'[]', b'{"x":NaN}', b'{"x":Infinity}', b'{"x":1,"x":2}', b'\xff', b'x' * 8193])
def test_strict_json_rejects_invalid_values(payload):
    with pytest.raises(ValueError):
        strict_json(payload)


def test_authorized_control_pause_resume_failure_and_dedup(catalog):
    service = runtime(catalog)
    stop = control(action='stop')
    assert service.apply_control(service.control_topic, stop, retained=False, qos=1, now=NOW)
    assert not service.simulator.active
    with pytest.raises(ValueError, match='paused'):
        service.simulator.sample(1, NOW)
    start = control()
    assert service.apply_control(service.control_topic, start, retained=False, qos=1, now=NOW)
    assert service.simulator.active
    assert not service.apply_control(service.control_topic, stop, retained=False, qos=1, now=NOW)
    assert service.simulator.active
    assert service.apply_control(service.control_topic, control(action='inject_fault', fault='imbalance'), retained=False, qos=1, now=NOW)
    assert service.simulator.faults == {'imbalance'}


@pytest.mark.parametrize('updates', [
    {'device_id': 'sim-lab-02'}, {'action': 'toggle'}, {'action': 'inject_fault'},
    {'fault': 'imbalance'}, {'action': 'inject_fault', 'fault': 'unknown'},
    {'labels': {}}, {'command_id': 'invalid'},
    {'issued_at': utc(NOW + timedelta(seconds=1)), 'expires_at': utc(NOW + timedelta(seconds=31))},
    {'expires_at': utc(NOW + timedelta(seconds=60))},
    {'issued_at': utc(NOW - timedelta(seconds=31)), 'expires_at': utc(NOW - timedelta(seconds=1))},
])
def test_invalid_controls_leave_state_untouched(catalog, updates):
    service = runtime(catalog)
    assert not service.apply_control(service.control_topic, control(**updates), retained=False, qos=1, now=NOW)
    assert service.simulator.active and service.simulator.faults == set() and service.seen == {}


@pytest.mark.parametrize('topic,retained,qos', [('wrong/topic', False, 1), (None, True, 1), (None, False, 0)])
def test_wrong_transport_controls_are_rejected(catalog, topic, retained, qos):
    service = runtime(catalog)
    assert not service.apply_control(topic or service.control_topic, control(action='stop'), retained=retained, qos=qos, now=NOW)
    assert service.simulator.active


def test_dedup_cache_is_bounded_without_evicting_live_commands(catalog):
    service = runtime(catalog)
    for _ in range(256):
        assert service.apply_control(service.control_topic, control(), retained=False, qos=1, now=NOW)
    assert not service.apply_control(service.control_topic, control(action='stop'), retained=False, qos=1, now=NOW)
    assert service.simulator.active
    later = NOW + timedelta(seconds=31)
    payload = control(issued_at=utc(later), expires_at=utc(later + timedelta(seconds=30)))
    assert service.apply_control(service.control_topic, payload, retained=False, qos=1, now=later)
    assert len(service.seen) == 1


def test_deadline_is_inclusive(catalog):
    service = runtime(catalog)
    assert service.apply_control(service.control_topic, control(), retained=False, qos=1, now=NOW + timedelta(seconds=30))
    assert not service.apply_control(service.control_topic, control(), retained=False, qos=1, now=NOW + timedelta(seconds=30, microseconds=1))


@pytest.mark.parametrize('options', [{'password': ''}, {'port': 0}, {'interval': float('nan')}, {'interval': 0}, {'step_seconds': float('inf')}, {'step_seconds': -1}])
def test_runtime_rejects_invalid_settings(catalog, options):
    settings = {'host': 'localhost', 'port': 1883, 'password': 'unit-only', **options}
    with pytest.raises(ValueError):
        MqttSimulator(Simulator(catalog), **settings)


def test_compose_and_acl_keep_simulator_optional_private_and_separate():
    services = yaml.safe_load((ROOT / 'compose.yaml').read_text())['services']
    simulator = services['simulator']
    assert simulator['profiles'] == ['simulator']
    assert simulator['read_only'] and simulator['user'] == '65532:65532'
    assert simulator['mem_limit'] == '64m' and 'ports' not in simulator
    assert simulator['volumes'][0]['read_only'] and not simulator['volumes'][0]['bind']['create_host_path']
    acl = (ROOT / 'infra/mosquitto/config/acl').read_text()
    sections = {section.splitlines()[0]: section.splitlines()[1:] for section in acl.strip().split('\n\n')}
    assert set(sections['user sim-lab-01']) == {
        'topic read coldsafe/v3/devices/sim-lab-01/commands',
        'topic write coldsafe/v3/devices/sim-lab-01/acks',
        'topic write coldsafe/v3/devices/sim-lab-01/telemetry',
        'topic read coldsafe/simulator/devices/sim-lab-01/control',
    }
    assert set(sections['user coldsafe-simulator-operator']) == {
        'topic write coldsafe/simulator/devices/sim-lab-01/control',
        'topic read coldsafe/v3/devices/sim-lab-01/telemetry',
    }
    for role in ('coldsafe-device', 'coldsafe-device-02', 'coldsafe-backend'):
        assert not any('simulator/' in permission or '/v3/' in permission for permission in sections['user ' + role])


def test_gateway_acl_is_scoped_to_simulator_actuator_flow():
    acl = (ROOT / 'infra/mosquitto/config/acl').read_text()
    section = acl.split('user coldsafe-gateway\n')[1].strip().splitlines()
    assert set(section) == {
        'topic write coldsafe/v3/devices/sim-lab-01/commands',
        'topic read coldsafe/v3/devices/sim-lab-01/acks',
        'topic read coldsafe/v3/devices/sim-lab-01/telemetry',
    }


@pytest.mark.parametrize('seed', [7, 42])
def test_runtime_cli_uses_requested_seed(catalog, tmp_path, monkeypatch, seed):
    import sys
    from types import SimpleNamespace
    from simulator import runtime as runtime_module

    path = tmp_path / 'catalog.json'
    path.write_text(json.dumps(catalog))
    models = []

    def mqtt_runtime(simulator, **settings):
        models.append(simulator)
        return SimpleNamespace(run=lambda shutdown: None)

    monkeypatch.setattr(sys, 'argv', ['simulator', '--catalog', str(path), '--seed', str(seed)])
    monkeypatch.setenv('MQTT_SIMULATOR_PASSWORD', 'unit-only')
    monkeypatch.setattr(runtime_module, 'MqttSimulator', mqtt_runtime)
    monkeypatch.setattr(runtime_module.signal, 'signal', lambda *args: None)
    assert runtime_module.main() == 0
    assert models[0].sample(1, NOW)['data'] == Simulator(catalog, seed).sample(1, NOW)['data']


@pytest.mark.parametrize('outcome', ['delivered', 'queue_full', 'timeout', 'disconnected'])
def test_runtime_publication_failure_and_shutdown_keep_loop_bounded(catalog, outcome, caplog):
    from threading import Event
    from types import SimpleNamespace
    import paho.mqtt.client as mqtt

    service = runtime(catalog)
    shutdown = Event()
    calls = []

    def wait_for_publish(timeout):
        assert timeout == 5
        if outcome == 'disconnected':
            raise RuntimeError('disconnected')

    def publish(topic, payload, qos, retain):
        calls.append(('publish', topic, qos, retain))
        TELEMETRY.validate(json.loads(payload))
        shutdown.set()
        return SimpleNamespace(rc=mqtt.MQTT_ERR_QUEUE_SIZE if outcome == 'queue_full' else mqtt.MQTT_ERR_SUCCESS,
                               wait_for_publish=wait_for_publish,
                               is_published=lambda: outcome == 'delivered')

    service.client = SimpleNamespace(
        connect_async=lambda *args, **kwargs: calls.append(('connect',)),
        loop_start=lambda: service.connected.set(), publish=publish,
        disconnect=lambda: calls.append(('disconnect',)),
        loop_stop=lambda: calls.append(('loop_stop',)),
    )
    service.run(shutdown)
    assert [item[0] for item in calls] == ['connect', 'publish', 'disconnect', 'loop_stop']
    assert calls[1][2:] == (1, False)
    assert not service.connected.is_set()
    if outcome != 'delivered':
        assert 'MQTT' in caplog.text
    assert 'unit-only' not in caplog.text


def test_subscription_readiness_requires_both_topics_and_disconnect_clears_it(catalog):
    from types import SimpleNamespace
    service = runtime(catalog)
    subscribed = []
    client = SimpleNamespace(subscribe=lambda topics: subscribed.extend(topics))
    success = SimpleNamespace(is_failure=False)
    failure = SimpleNamespace(is_failure=True)
    service.on_connect(client, None, None, failure, None)
    assert not subscribed and not service.connected.is_set()
    service.on_connect(client, None, None, success, None)
    assert {topic for topic, _ in subscribed} == {service.control_topic, service.command_topic}
    service.on_subscribe(client, None, 1, [success, failure], None)
    assert not service.connected.is_set()
    service.on_subscribe(client, None, 1, [success, success], None)
    assert service.connected.is_set()
    service.on_disconnect(client, None, None, success, None)
    assert not service.connected.is_set()


@pytest.mark.parametrize('publication', ['accepted', 'rejected', 'queue_full'])
def test_control_cli_reports_broker_acceptance_and_always_closes_transport(monkeypatch, publication, capsys):
    import sys
    from types import SimpleNamespace
    from simulator import control as control_module
    import paho.mqtt.client as mqtt

    calls = []
    client = SimpleNamespace()
    client.username_pw_set = lambda user, password: calls.append(('credentials', user))
    client.connect_async = lambda *args: None
    client.loop_start = lambda: client.on_connect(client, None, None, SimpleNamespace(is_failure=False), None)
    client.disconnect = lambda: calls.append(('disconnect',))
    client.loop_stop = lambda: calls.append(('loop_stop',))

    def publish(topic, payload, qos, retain):
        assert topic.endswith('/control') and qos == 1 and not retain
        assert json.loads(payload)['action'] == 'stop'
        client.on_publish(client, None, 1, SimpleNamespace(is_failure=publication == 'rejected'), None)
        return SimpleNamespace(rc=mqtt.MQTT_ERR_QUEUE_SIZE if publication == 'queue_full' else mqtt.MQTT_ERR_SUCCESS)

    client.publish = publish
    monkeypatch.setattr(control_module.mqtt, 'Client', lambda *args, **kwargs: client)
    monkeypatch.setattr(sys, 'argv', ['control', 'stop'])
    monkeypatch.setenv('MQTT_SIMULATOR_OPERATOR_PASSWORD', 'unit-only')
    assert control_module.main() == (0 if publication == 'accepted' else 1)
    assert calls[-2:] == [('disconnect',), ('loop_stop',)]
    output = capsys.readouterr()
    assert 'unit-only' not in output.out + output.err
    assert ('accepted by broker' in output.out) == (publication == 'accepted')
