"""B2-10 actuator effects, command identity, deadlines and ACK trust boundaries."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from jsonschema import Draft202012Validator, FormatChecker
import paho.mqtt.client as mqtt
import pytest

from simulator.model import SCHEMA, Simulator, utc
from simulator.runtime import MqttSimulator

ROOT = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 10, 14, 12, tzinfo=timezone.utc)
ACK = Draft202012Validator({**SCHEMA, '$ref': '#/$defs/ack_event'}, format_checker=FormatChecker())


@pytest.fixture
def service():
    catalog = json.loads((ROOT / 'simulator/catalog.example.json').read_text())
    return MqttSimulator(Simulator(catalog, seed=7), host='localhost', port=1883, password='unit-only')


def command(service, actuator='led', desired=True, now=NOW):
    command_id = str(uuid4())
    return {'schema_version': 3, 'event_id': str(uuid4()), 'type': 'command',
            'occurred_at': utc(now), 'received_at': utc(now),
            **{key: service.simulator.catalog[key] for key in ('device_id', 'device_record_id', 'environment_id')},
            'correlation_id': command_id,
            'data': {'command_id': command_id, 'actuator_id': service.simulator.catalog['actuators'][actuator],
                     'actuator': actuator, 'desired_state': desired,
                     'source': 'manual' if actuator == 'led' else 'automatic',
                     'deadline_at': utc(now + timedelta(seconds=30))}}


def apply(service, payload, now=NOW, **transport):
    return service.apply_command(service.command_topic, json.dumps(payload).encode(), now=now,
                                 **{'retained': False, 'qos': 1, **transport})


@pytest.mark.parametrize('actuator', ['led', 'buzzer'])
@pytest.mark.parametrize('desired', [True, False])
def test_command_changes_state_and_matching_ack(service, actuator, desired):
    setattr(service.simulator, actuator, not desired)
    requested = command(service, actuator, desired)
    ack = apply(service, requested)
    ACK.validate(ack)
    assert ack['correlation_id'] == requested['data']['command_id']
    assert ack['received_at'] is None and ack['device_id'] == requested['device_id']
    assert ack['data'] == {**{key: requested['data'][key] for key in ('command_id', 'actuator_id', 'actuator')},
                           'result': 'applied', 'applied_state': desired, 'reason': None}
    telemetry = service.simulator.sample(1, NOW)
    assert telemetry['data']['actuators'][actuator]['actual_state'] == desired
    assert telemetry['data']['equipment']['running'] is True


def test_led_changes_light_only_with_same_seed(service):
    other = Simulator(service.simulator.catalog, seed=7)
    apply(service, command(service))
    lit = service.simulator.sample(1, NOW)['data']['measurements']
    unlit = other.sample(1, NOW)['data']['measurements']
    assert lit['light']['value'] == pytest.approx(unlit['light']['value'] + 40)
    for key in lit.keys() - {'light'}:
        assert lit[key] == unlit[key]


def test_duplicate_returns_same_ack_without_reapplying_old_state(service):
    first = command(service)
    original_ack = apply(service, first)
    apply(service, command(service, desired=False))
    assert apply(service, deepcopy(first)) == original_ack
    assert not service.simulator.led
    assert len(service.commands) == 2


@pytest.mark.parametrize('mutation', ['state', 'actuator', 'event_id', 'extended_deadline'])
def test_same_command_id_with_different_content_is_rejected(service, mutation):
    requested = command(service)
    apply(service, requested)
    changed = deepcopy(requested)
    if mutation == 'state': changed['data']['desired_state'] = False
    elif mutation == 'actuator':
        changed['data'].update(actuator='buzzer', actuator_id=service.simulator.catalog['actuators']['buzzer'], source='automatic')
    elif mutation == 'event_id': changed['event_id'] = str(uuid4())
    else:
        changed.update(occurred_at=utc(NOW + timedelta(seconds=1)), received_at=utc(NOW + timedelta(seconds=1)))
        changed['data']['deadline_at'] = utc(NOW + timedelta(seconds=31))
    ack = apply(service, changed, now=NOW + timedelta(seconds=1))
    ACK.validate(ack)
    assert ack['data']['reason'] == 'INVALID_COMMAND'
    assert service.simulator.led and not service.simulator.buzzer


def test_event_id_cannot_be_reused_for_another_command(service):
    first = command(service)
    apply(service, first)
    second = command(service, desired=False)
    second['event_id'] = first['event_id']
    assert apply(service, second)['data']['reason'] == 'INVALID_COMMAND'
    assert service.simulator.led


@pytest.mark.parametrize('mutation', ['actuator_id', 'correlation', 'deadline', 'received_before', 'future'])
def test_relational_invalid_command_gets_rejected_ack_without_actuation(service, mutation):
    requested = command(service)
    if mutation == 'actuator_id': requested['data']['actuator_id'] = str(uuid4())
    elif mutation == 'correlation': requested['correlation_id'] = str(uuid4())
    elif mutation == 'deadline': requested['data']['deadline_at'] = utc(NOW + timedelta(seconds=31))
    elif mutation == 'received_before': requested['received_at'] = utc(NOW - timedelta(seconds=1))
    else: requested['received_at'] = utc(NOW + timedelta(seconds=1))
    ack = apply(service, requested)
    ACK.validate(ack)
    assert ack['data']['result'] == 'rejected' and ack['data']['reason'] == 'INVALID_COMMAND'
    assert ack['data']['applied_state'] is None and not service.simulator.led


@pytest.mark.parametrize('scope', ['device_id', 'device_record_id', 'environment_id'])
def test_wrong_scope_is_dropped_without_echo_or_actuation(service, scope):
    requested = command(service)
    requested[scope] = 'sim-lab-02' if scope == 'device_id' else str(uuid4())
    assert apply(service, requested) is None
    assert not service.simulator.led


@pytest.mark.parametrize('mutation', ['uuid', 'actuator', 'source', 'boolean', 'extra', 'type'])
def test_invalid_schema_is_dropped_without_fabricating_ack(service, mutation):
    requested = command(service)
    if mutation == 'uuid': requested['data']['command_id'] = 'invalid-id'
    elif mutation == 'actuator': requested['data']['actuator'] = 'fan'
    elif mutation == 'source': requested['data']['source'] = 'automatic'
    elif mutation == 'boolean': requested['data']['desired_state'] = 'true'
    elif mutation == 'extra': requested['data']['labels'] = {}
    else: requested['type'] = 'ack'
    assert apply(service, requested) is None
    assert not service.simulator.led


def test_deadline_inclusive_and_expiration_never_reapplies_or_reports_success(service):
    requested = command(service)
    assert apply(service, requested, now=NOW + timedelta(seconds=30))['data']['result'] == 'applied'
    apply(service, command(service, desired=False, now=NOW + timedelta(seconds=30)), now=NOW + timedelta(seconds=30))
    late = apply(service, requested, now=NOW + timedelta(seconds=30, microseconds=1))
    ACK.validate(late)
    assert late['data']['reason'] == 'EXPIRED_COMMAND' and late['data']['applied_state'] is None
    assert not service.simulator.led
    fresh = command(service)
    assert apply(service, fresh, now=NOW + timedelta(seconds=31))['data']['reason'] == 'EXPIRED_COMMAND'
    assert not service.simulator.led


@pytest.mark.parametrize('transport', [{'retained': True}, {'qos': 0}])
def test_wrong_transport_has_no_ack(service, transport):
    assert apply(service, command(service), **transport) is None
    assert not service.simulator.led


def test_command_cache_refuses_overflow_without_forgetting_old_identity(service):
    first = command(service)
    first_ack = apply(service, first)
    for _ in range(255): apply(service, command(service))
    assert apply(service, command(service, desired=False))['data']['reason'] == 'ACTUATOR_FAILURE'
    assert apply(service, first) == first_ack and service.simulator.led


def test_callback_publishes_ack_and_failed_queue_does_not_claim_delivery(service, caplog):
    published = []
    def publish(topic, payload, qos, retain):
        published.append((topic, json.loads(payload), qos, retain))
        return SimpleNamespace(rc=mqtt.MQTT_ERR_QUEUE_SIZE)
    client = SimpleNamespace(publish=publish)
    now = datetime.now(timezone.utc)
    requested = command(service, now=now)
    message = SimpleNamespace(topic=service.command_topic, payload=json.dumps(requested).encode(), retain=False, qos=1)
    service.on_message(client, None, message)
    assert len(published) == 1 and published[0][0] == service.ack_topic
    ACK.validate(published[0][1])
    assert published[0][2:] == (1, False)
    assert service.simulator.led and 'ACK not queued' in caplog.text
    service.on_message(client, None, message)
    assert published[1][1] == published[0][1]
    assert 'confirmed' not in caplog.text
