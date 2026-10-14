"""Inspect real MQTT from the Compose simulator in an isolated disposable broker."""
import json
import os
from pathlib import Path
from queue import Empty, Queue
import secrets
import subprocess
import sys
import tempfile
from threading import Event
import time

import paho.mqtt.client as mqtt
import pytest
import yaml

from simulator.control import make_control
from simulator.model import TELEMETRY

ROOT = Path(__file__).resolve().parents[3]
pytestmark = pytest.mark.integration
TOPIC = 'coldsafe/v3/devices/sim-lab-01/telemetry'
CONTROL = 'coldsafe/simulator/devices/sim-lab-01/control'


def command(base, *args):
    result = subprocess.run([*base, *args], capture_output=True, text=True, timeout=240)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


@pytest.fixture(scope='module')
def stack(request):
    if os.environ.get('COLDSAFE_SIMULATOR_INTEGRATION') != '1':
        pytest.skip('Set COLDSAFE_SIMULATOR_INTEGRATION=1 for disposable MQTT/Compose checks')
    project = 'coldsafe-b209-' + secrets.token_hex(4)
    with tempfile.TemporaryDirectory(prefix=project) as folder:
        directory = Path(folder)
        env_file = directory / '.env'
        command([sys.executable, str(ROOT / 'scripts/generate-secrets.py')], '--env-file', str(env_file))
        values = dict(line.split('=', 1) for line in env_file.read_text().splitlines()
                      if line and not line.startswith('#'))
        catalog = directory / 'catalog'
        catalog.mkdir(mode=0o755)
        (catalog / 'catalog.json').write_bytes((ROOT / 'simulator/catalog.example.json').read_bytes())
        (catalog / 'catalog.json').chmod(0o644)
        original = yaml.safe_load((ROOT / 'compose.yaml').read_text())
        services = {name: original['services'][name] for name in ('mosquitto-init', 'mosquitto', 'simulator')}
        for name, service in services.items():
            service['build']['context'] = str(ROOT / service['build']['context'])
            service['image'] = project + '-' + name
            service.pop('profiles', None)
        services['simulator']['volumes'][0]['source'] = str(catalog)
        services['simulator']['environment']['SIMULATOR_INTERVAL_SECONDS'] = '0.2'
        services['simulator']['environment']['SIMULATOR_STEP_SECONDS'] = '60'
        services['mosquitto']['ports'] = ['127.0.0.1::1883']
        services['mosquitto']['networks'].append('test-edge')
        config = {'services': services, 'networks': {'coldsafe-internal': {'internal': True}, 'test-edge': {}},
                  'volumes': {'mosquitto-auth': {}, 'mosquitto-data': {}}}
        compose = directory / 'compose.yaml'
        compose.write_text(yaml.safe_dump(config))
        base = ['docker', 'compose', '-p', project, '--env-file', str(env_file), '-f', str(compose)]
        try:
            command(base, 'up', '-d', '--build', '--wait', '--wait-timeout', '90')
            port = int(command(base, 'port', 'mosquitto', '1883').strip().rsplit(':', 1)[1])
            yield {'base': base, 'port': port, 'values': values, 'project': project}
        finally:
            if request.session.testsfailed:
                print(command(base, 'logs', '--no-color', '--tail', '30', 'simulator'))
            command(base, 'down', '--volumes', '--remove-orphans')


class Probe:
    def __init__(self, stack, username='coldsafe-simulator-operator', password_key='MQTT_SIMULATOR_OPERATOR_PASSWORD', password=None):
        self.messages, self.published = Queue(), Queue()
        self.connection, self.subscription = Event(), Event()
        self.connect_failed = False
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv5)
        self.client.username_pw_set(username, password if password is not None else stack['values'][password_key])
        self.client.on_connect = self.on_connect
        self.client.on_subscribe = lambda *args: self.subscription.set()
        self.client.on_publish = lambda client, userdata, mid, reason, properties: self.published.put(reason.is_failure)
        self.client.on_message = lambda client, userdata, message: self.messages.put(message)
        self.client.connect('127.0.0.1', stack['port'])
        self.client.loop_start()
        assert self.connection.wait(10), 'MQTT connection timed out'

    def on_connect(self, client, userdata, flags, reason, properties):
        self.connect_failed = reason.is_failure
        self.connection.set()

    def subscribe(self, topic=TOPIC):
        self.subscription.clear()
        self.client.subscribe(topic, qos=1)
        assert self.subscription.wait(10)

    def publish(self, topic, payload, retain=False):
        self.client.publish(topic, json.dumps(payload), qos=1, retain=retain)
        return not self.published.get(timeout=10)

    def read(self, timeout=10):
        message = self.messages.get(timeout=timeout)
        assert message.topic == TOPIC and message.qos == 1 and not message.retain
        payload = json.loads(message.payload)
        TELEMETRY.validate(payload)
        assert len(message.payload) <= 8192 and payload['received_at'] is None
        assert payload['device_id'] == 'sim-lab-01'
        assert payload['correlation_id'] == payload['event_id']
        return payload

    def drain(self):
        while not self.messages.empty():
            self.messages.get_nowait()

    def close(self):
        self.client.disconnect()
        self.client.loop_stop()


def wait_for_silence(probe, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            probe.messages.get(timeout=0.7)
        except Empty:
            return
    pytest.fail('Telemetry did not stop within the control wait limit')


@pytest.fixture
def probe(stack):
    client = Probe(stack)
    try:
        assert not client.connect_failed
        client.subscribe()
        yield client
    finally:
        client.close()


def test_real_sensor_messages_have_ids_units_and_no_labels(stack, probe):
    first, second = probe.read(), probe.read()
    catalog = json.loads((ROOT / 'simulator/catalog.example.json').read_text())
    assert first['event_id'] != second['event_id']
    assert first['data']['equipment']['equipment_id'] == catalog['equipment_id']
    assert {key: value['sensor_id'] for key, value in first['data']['measurements'].items()} == catalog['sensors']
    assert set(first['data']['measurements']) == {'ambient_temperature', 'humidity', 'light', 'vibration', 'motor_current', 'motor_temperature'}
    assert 'labels' not in json.dumps(first) and 'rul_hours_true' not in json.dumps(first)
    cid = command(stack['base'], 'ps', '-q', 'simulator').strip()
    details = json.loads(command(['docker'], 'inspect', cid))[0]
    assert details['Config']['User'] == '65532:65532'
    assert details['HostConfig']['ReadonlyRootfs'] and details['HostConfig']['Memory'] == 64 * 1024 * 1024
    assert not details['State']['OOMKilled']
    assert all(mount.get('Name', '').startswith(stack['project']) for mount in details['Mounts'] if mount['Type'] == 'volume')


def test_real_operator_pause_resume_failure_and_retained_rejection(stack, probe):
    probe.read()
    # Preserve RETAIN on live delivery (MQTT 5) and never replay retained controls.
    assert probe.publish(CONTROL, make_control('sim-lab-01', 'stop'), retain=True)
    probe.read()
    probe.read()
    assert probe.publish(CONTROL, make_control('sim-lab-01', 'stop'))
    wait_for_silence(probe)
    with pytest.raises(Empty):
        probe.messages.get(timeout=0.7)
    assert probe.publish(CONTROL, make_control('sim-lab-01', 'start'))
    baseline = probe.read()
    assert probe.publish(CONTROL, make_control('sim-lab-01', 'inject_fault', 'bearing_wear'))
    assert probe.publish(CONTROL, make_control('sim-lab-01', 'inject_fault', 'imbalance'))
    for _ in range(30):
        damaged = probe.read()
    for key in ('vibration', 'motor_current', 'motor_temperature', 'ambient_temperature'):
        assert damaged['data']['measurements'][key]['value'] > baseline['data']['measurements'][key]['value'] + 0.5
    # Restore controls before teardown/other tests; restart simulator to reset latent state.
    command(stack['base'], 'restart', 'simulator')
    probe.read(timeout=20)


@pytest.mark.parametrize('username,key,topic', [
    ('coldsafe-device', 'MQTT_DEVICE_PASSWORD', CONTROL),
    ('coldsafe-device-02', 'MQTT_DEVICE_02_PASSWORD', CONTROL),
    ('coldsafe-backend', 'MQTT_BACKEND_PASSWORD', CONTROL),
    ('sim-lab-01', 'MQTT_SIMULATOR_PASSWORD', CONTROL),
    ('sim-lab-01', 'MQTT_SIMULATOR_PASSWORD', 'coldsafe/v3/devices/sim-lab-02/telemetry'),
    ('coldsafe-simulator-operator', 'MQTT_SIMULATOR_OPERATOR_PASSWORD', TOPIC),
    ('coldsafe-simulator-operator', 'MQTT_SIMULATOR_OPERATOR_PASSWORD', 'coldsafe/v3/devices/sim-lab-01/commands'),
])
def test_real_acl_denies_other_roles_and_cross_device_publish(stack, username, key, topic):
    client = Probe(stack, username, key)
    try:
        assert not client.publish(topic, make_control('sim-lab-01', 'stop'))
    finally:
        client.close()


def test_wrong_password_and_anonymous_are_rejected(stack):
    for username, password in [('sim-lab-01', secrets.token_urlsafe(32)), ('', '')]:
        client = Probe(stack, username, password=password)
        try:
            assert client.connect_failed
        finally:
            client.close()


def test_real_broker_restart_reconnects_and_resubscribes(stack):
    command(stack['base'], 'restart', 'mosquitto')
    stack['port'] = int(command(stack['base'], 'port', 'mosquitto', '1883').strip().rsplit(':', 1)[1])
    client = Probe(stack)
    try:
        client.subscribe()
        client.read(timeout=30)
        assert client.publish(CONTROL, make_control('sim-lab-01', 'stop'))
        wait_for_silence(client)
        with pytest.raises(Empty):
            client.messages.get(timeout=0.7)
        assert client.publish(CONTROL, make_control('sim-lab-01', 'start'))
        client.read(timeout=15)
    finally:
        client.close()


@pytest.mark.parametrize('username,key', [
    ('coldsafe-device', 'MQTT_DEVICE_PASSWORD'),
    ('coldsafe-device-02', 'MQTT_DEVICE_02_PASSWORD'),
    ('coldsafe-backend', 'MQTT_BACKEND_PASSWORD'),
])
def test_real_acl_does_not_deliver_private_simulator_telemetry(stack, username, key):
    client = Probe(stack, username, key)
    try:
        client.subscribe()
        with pytest.raises(Empty):
            client.messages.get(timeout=0.7)
    finally:
        client.close()


def test_operator_cli_runs_in_disposable_compose_container(stack, probe):
    process_env = {**os.environ, 'MQTT_SIMULATOR_OPERATOR_PASSWORD': stack['values']['MQTT_SIMULATOR_OPERATOR_PASSWORD']}
    for action in ('stop', 'start'):
        result = subprocess.run([*stack['base'], 'run', '--rm', '--no-deps',
                                 '--entrypoint', 'python', '-e', 'MQTT_SIMULATOR_OPERATOR_PASSWORD',
                                 'simulator', '-m', 'simulator.control', action],
                                env=process_env, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, 'Operator CLI failed (output omitted to protect secrets)'
        assert 'accepted by broker' in result.stdout
        assert process_env['MQTT_SIMULATOR_OPERATOR_PASSWORD'] not in result.stdout + result.stderr
        if action == 'stop':
            wait_for_silence(probe)
            with pytest.raises(Empty):
                probe.messages.get(timeout=0.7)
        else:
            probe.read()


# B2-10 exercises the trusted gateway identity; no HTTP authorization is simulated.
def actuator_command(actuator='led', desired=True, at=None):
    from datetime import datetime, timedelta, timezone
    from uuid import uuid4
    from simulator.model import utc
    catalog = json.loads((ROOT / 'simulator/catalog.example.json').read_text())
    at = at or datetime.now(timezone.utc).replace(microsecond=0)
    identifier = str(uuid4())
    return {'schema_version': 3, 'event_id': str(uuid4()), 'type': 'command',
            'occurred_at': utc(at), 'received_at': utc(at),
            **{key: catalog[key] for key in ('device_id', 'device_record_id', 'environment_id')},
            'correlation_id': identifier,
            'data': {'command_id': identifier, 'actuator_id': catalog['actuators'][actuator],
                     'actuator': actuator, 'desired_state': desired,
                     'source': 'manual' if actuator == 'led' else 'automatic',
                     'deadline_at': utc(at + timedelta(seconds=30))}}


@pytest.fixture
def gateway(stack):
    client = Probe(stack, 'coldsafe-gateway', 'MQTT_GATEWAY_PASSWORD')
    try:
        assert not client.connect_failed
        client.subscribe('coldsafe/v3/devices/sim-lab-01/acks')
        yield client
    finally:
        client.close()


def read_actuator_ack(gateway, requested):
    from jsonschema import Draft202012Validator, FormatChecker
    from simulator.model import SCHEMA
    message = gateway.messages.get(timeout=10)
    assert message.topic == 'coldsafe/v3/devices/sim-lab-01/acks'
    assert message.qos == 1 and not message.retain
    ack = json.loads(message.payload)
    Draft202012Validator({**SCHEMA, '$ref': '#/$defs/ack_event'}, format_checker=FormatChecker()).validate(ack)
    assert ack['received_at'] is None
    assert ack['correlation_id'] == requested['data']['command_id']
    for key in ('device_id', 'device_record_id', 'environment_id'):
        assert ack[key] == requested[key]
    for key in ('command_id', 'actuator_id', 'actuator'):
        assert ack['data'][key] == requested['data'][key]
    return ack


def telemetry_after_ack(probe, ack):
    from datetime import datetime
    ack_time = datetime.fromisoformat(ack['occurred_at'].replace('Z', '+00:00'))
    for _ in range(50):
        event = probe.read()
        if datetime.fromisoformat(event['occurred_at'].replace('Z', '+00:00')) >= ack_time:
            return event
    pytest.fail('No telemetry after actuator ACK')


@pytest.mark.parametrize('actuator', ['led', 'buzzer'])
def test_real_actuator_command_ack_and_telemetry(stack, gateway, probe, actuator):
    # Begin in explicit off state, then compare the subsequent on state.
    off = actuator_command(actuator, False)
    assert gateway.publish('coldsafe/v3/devices/sim-lab-01/commands', off)
    off_ack = read_actuator_ack(gateway, off)
    before = telemetry_after_ack(probe, off_ack)
    on = actuator_command(actuator, True)
    assert gateway.publish('coldsafe/v3/devices/sim-lab-01/commands', on)
    on_ack = read_actuator_ack(gateway, on)
    assert on_ack['data']['result'] == 'applied' and on_ack['data']['applied_state'] is True
    after = telemetry_after_ack(probe, on_ack)
    assert after['data']['actuators'][actuator]['actual_state'] is True
    assert after['data']['equipment']['running'] is True
    if actuator == 'led':
        assert after['data']['measurements']['light']['value'] > before['data']['measurements']['light']['value'] + 35
    # A new off command wins; duplicate on reports the old result but does not reapply it.
    off_again = actuator_command(actuator, False)
    assert gateway.publish('coldsafe/v3/devices/sim-lab-01/commands', off_again)
    off_again_ack = read_actuator_ack(gateway, off_again)
    assert gateway.publish('coldsafe/v3/devices/sim-lab-01/commands', on)
    assert read_actuator_ack(gateway, on) == on_ack
    assert telemetry_after_ack(probe, off_again_ack)['data']['actuators'][actuator]['actual_state'] is False


def test_real_invalid_actuator_and_expired_command_are_rejected(stack, gateway, probe):
    from datetime import datetime, timedelta, timezone
    from uuid import uuid4
    invalid = actuator_command()
    invalid['data']['actuator_id'] = str(uuid4())
    assert gateway.publish('coldsafe/v3/devices/sim-lab-01/commands', invalid)
    ack = read_actuator_ack(gateway, invalid)
    assert ack['data']['reason'] == 'INVALID_COMMAND' and ack['data']['applied_state'] is None
    expired = actuator_command(at=datetime.now(timezone.utc) - timedelta(seconds=31))
    assert gateway.publish('coldsafe/v3/devices/sim-lab-01/commands', expired)
    ack = read_actuator_ack(gateway, expired)
    assert ack['data']['reason'] == 'EXPIRED_COMMAND' and ack['data']['result'] == 'rejected'
    assert not telemetry_after_ack(probe, ack)['data']['actuators']['led']['actual_state']


def test_real_invalid_id_retained_and_wrong_scope_have_no_ack(stack, gateway, probe):
    from uuid import uuid4
    for mode in ('malformed_id', 'retained', 'wrong_scope'):
        requested = actuator_command()
        if mode == 'malformed_id': requested['data']['command_id'] = 'invalid-id'
        if mode == 'wrong_scope': requested['environment_id'] = str(uuid4())
        assert gateway.publish('coldsafe/v3/devices/sim-lab-01/commands', requested, retain=mode == 'retained')
        with pytest.raises(Empty):
            gateway.messages.get(timeout=0.7)
        assert not probe.read()['data']['actuators']['led']['actual_state']


def test_real_absent_confirmation_and_late_retry_never_get_success(stack, gateway, probe):
    from datetime import datetime, timedelta, timezone
    # Stopping the process prevents any device ACK. PUBACK still succeeds.
    command(stack['base'], 'stop', 'simulator')
    requested = actuator_command(at=datetime.now(timezone.utc) - timedelta(seconds=29))
    try:
        assert gateway.publish('coldsafe/v3/devices/sim-lab-01/commands', requested)
        with pytest.raises(Empty):
            gateway.messages.get(timeout=1.2)
        probe.drain()
        command(stack['base'], 'start', 'simulator')
        probe.read(timeout=20)
        assert gateway.publish('coldsafe/v3/devices/sim-lab-01/commands', requested)
        late = read_actuator_ack(gateway, requested)
        assert late['data']['result'] == 'rejected' and late['data']['reason'] == 'EXPIRED_COMMAND'
        assert not telemetry_after_ack(probe, late)['data']['actuators']['led']['actual_state']
    finally:
        command(stack['base'], 'start', 'simulator')


@pytest.mark.parametrize('username,key,topic', [
    ('coldsafe-device', 'MQTT_DEVICE_PASSWORD', 'commands'),
    ('coldsafe-backend', 'MQTT_BACKEND_PASSWORD', 'commands'),
    ('sim-lab-01', 'MQTT_SIMULATOR_PASSWORD', 'commands'),
    ('coldsafe-simulator-operator', 'MQTT_SIMULATOR_OPERATOR_PASSWORD', 'acks'),
    ('coldsafe-gateway', 'MQTT_GATEWAY_PASSWORD', 'acks'),
    ('coldsafe-gateway', 'MQTT_GATEWAY_PASSWORD', 'telemetry'),
    ('coldsafe-gateway', 'MQTT_GATEWAY_PASSWORD', '../sim-lab-02/commands'),
])
def test_real_actuator_acl_denies_publish_for_wrong_identity(stack, username, key, topic):
    client = Probe(stack, username, key)
    try:
        target = 'coldsafe/v3/devices/sim-lab-01/' + topic
        if topic.startswith('../'): target = 'coldsafe/v3/devices/sim-lab-02/commands'
        assert not client.publish(target, actuator_command())
    finally:
        client.close()
