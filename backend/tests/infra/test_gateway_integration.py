"""Opt-in B2-11 checks through real brokers and the disposable Compose gateway."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

import pika
import psycopg
import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker

from backend.tests.infra.test_rabbitmq_integration import connect, publish
from backend.tests.infra.test_simulator_integration import Probe, actuator_command, command
from simulator.model import SCHEMA

ROOT = Path(__file__).resolve().parents[3]
pytestmark = pytest.mark.integration
TOPIC = 'coldsafe/v3/devices/sim-lab-01/telemetry'
BUS = Draft202012Validator({**SCHEMA, '$ref': '#/$defs/bus_event'}, format_checker=FormatChecker())


def port(base, service, internal):
    return int(command(base, 'port', service, str(internal)).strip().rsplit(':', 1)[1])


@pytest.fixture(scope='module')
def stack(request):
    if os.environ.get('COLDSAFE_GATEWAY_INTEGRATION') != '1':
        pytest.skip('Set COLDSAFE_GATEWAY_INTEGRATION=1 for disposable MQTT/AMQP/PostgreSQL checks')
    project = 'coldsafe-b211-' + secrets.token_hex(4)
    with tempfile.TemporaryDirectory(prefix=project) as folder:
        directory = Path(folder)
        env_file = directory / '.env'
        command([sys.executable, str(ROOT / 'scripts/generate-secrets.py')], '--env-file', str(env_file))
        values = dict(line.split('=', 1) for line in env_file.read_text().splitlines()
                      if line and not line.startswith('#'))
        catalog_dir = directory / 'catalog'
        catalog_dir.mkdir(mode=0o755)
        catalog_file = catalog_dir / 'catalog.json'
        catalog_file.write_bytes((ROOT / 'simulator/catalog.example.json').read_bytes())
        catalog_file.chmod(0o644)
        catalog = json.loads(catalog_file.read_text())
        original = yaml.safe_load((ROOT / 'compose.yaml').read_text())
        names = ('rabbitmq-init', 'rabbitmq', 'mosquitto-init', 'mosquitto', 'postgres', 'simulator', 'gateway')
        services = {name: original['services'][name] for name in names}
        for name, service in services.items():
            if 'build' in service:
                service['build']['context'] = str(ROOT / service['build']['context'])
                service['image'] = project + '-' + name
        for name, internal in (('rabbitmq', 5672), ('mosquitto', 1883), ('postgres', 5432)):
            services[name]['ports'] = [f'127.0.0.1::{internal}']
            services[name]['networks'].append('test-edge')
        for name in ('simulator', 'gateway'):
            for volume in services[name]['volumes']:
                if isinstance(volume, dict) and volume.get('target') == '/catalog':
                    volume['source'] = str(catalog_dir)
        services['simulator']['environment']['SIMULATOR_INTERVAL_SECONDS'] = '0.2'
        owner = str(uuid4())
        services['gateway']['environment']['GATEWAY_OWNER_USER_ID'] = owner
        config = {'services': services,
                  'networks': {'coldsafe-internal': {'internal': True}, 'test-edge': {}},
                  'volumes': {name: {} for name in original['volumes']}}
        compose = directory / 'compose.yaml'
        compose.write_text(yaml.safe_dump(config))
        base = ['docker', 'compose', '-p', project, '--env-file', str(env_file),
                '-f', str(compose), '--profile', 'aiot', '--profile', 'simulator']
        try:
            command(base, 'up', '-d', '--build', '--wait', '--wait-timeout', '120',
                    'rabbitmq', 'mosquitto', 'postgres')
            postgres = {'host': '127.0.0.1', 'port': port(base, 'postgres', 5432),
                        'dbname': values.get('POSTGRES_DB', 'coldsafe'),
                        'user': values.get('POSTGRES_USER', 'coldsafe'),
                        'password': values['POSTGRES_PASSWORD']}
            with psycopg.connect(**postgres) as database:
                for migration in sorted((ROOT / 'backend/migrations').glob('*.sql')):
                    database.execute(migration.read_text())
                database.execute('INSERT INTO users(id,email,password_hash) VALUES (%s,%s,%s)',
                                 (owner, 'gateway-test@example.invalid', 'unused-no-http-login'))
                database.execute('INSERT INTO environments(id,owner_user_id,name) VALUES (%s,%s,%s)',
                                 (catalog['environment_id'], owner, 'Gateway test'))
                database.execute('INSERT INTO devices(id,environment_id,mqtt_device_id,name) VALUES (%s,%s,%s,%s)',
                                 (catalog['device_record_id'], catalog['environment_id'], catalog['device_id'], 'Simulator'))
            command(base, 'up', '-d', '--build', '--wait', '--wait-timeout', '120', 'gateway', 'simulator')
            state = {'base': base, 'port': port(base, 'mosquitto', 1883), 'values': values,
                     'catalog': catalog, 'postgres': postgres, 'owner': owner, 'broker': {'port': port(base, 'rabbitmq', 5672),
                         'passwords': {role: values[f'RABBITMQ_{role.upper()}_PASSWORD']
                                       for role in ('api', 'writer', 'commands', 'delivery', 'audit')}}}
            # Real delivery is readiness: a running process alone does not prove subscriptions.
            receive(state, 'writer', lambda event: event['type'] == 'telemetry', timeout=30)
            yield state
        finally:
            try:
                if request.session.testsfailed:
                    result = subprocess.run([*base, 'logs', '--no-color', '--tail', '50', 'gateway', 'simulator'],
                                            capture_output=True, text=True, timeout=30)
                    logs = result.stdout + result.stderr
                    for key, value in values.items():
                        if value and any(secret in key for secret in ('PASSWORD', 'TOKEN', 'SECRET')):
                            logs = logs.replace(value, '[REDACTED]')
                    print(logs)
            finally:
                command(base, 'down', '--volumes', '--remove-orphans')


def receive(stack, role, predicate, timeout=15):
    deadline = time.monotonic() + timeout
    with connect(stack['broker'], role) as channel:
        while time.monotonic() < deadline:
            method, properties, body = channel.basic_get('coldsafe.' + ('dlq' if role == 'audit' else role))
            if not method:
                channel.connection.sleep(0.05)
                continue
            channel.basic_ack(method.delivery_tag)
            event = json.loads(body)
            if predicate(event):
                BUS.validate(event)
                assert properties.delivery_mode == 2
                assert properties.message_id == event['event_id']
                assert properties.correlation_id == event['correlation_id']
                scope = event['correlation_id'] if event['type'] == 'processing_error' else event['device_record_id']
                assert method.routing_key == f"v3.{event['type']}.{scope}"
                return event
    pytest.fail(f'No matching event in {role} within {timeout}s')


def journal(stack, sql, parameters=()):
    script = ('import json,sqlite3,sys; '
              'db=sqlite3.connect("file:/state/gateway.sqlite3?mode=ro",uri=True); '
              'print(json.dumps(db.execute(sys.argv[1],json.loads(sys.argv[2])).fetchall()))')
    return json.loads(command(stack['base'], 'exec', '-T', 'gateway', 'python', '-c',
                              script, sql, json.dumps(parameters)))


def wait_journal(stack, sql, parameters=(), timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        rows = journal(stack, sql, parameters)
        if rows:
            return rows
        time.sleep(0.1)
    pytest.fail('Gateway journal did not reach the expected state')


def send_command(stack, requested):
    with connect(stack['broker'], 'api') as channel:
        return publish(channel, {'payload': requested,
                                'routing_key': 'v3.command.' + requested['device_record_id']})


def send_raw(probe, topic, body):
    result = probe.client.publish(topic, body, qos=1)
    result.wait_for_publish(timeout=10)
    assert result.is_published()
    assert probe.published.get(timeout=10) is False


def start_simulator(stack):
    reader = Probe(stack, 'coldsafe-gateway', 'MQTT_GATEWAY_PASSWORD')
    try:
        reader.subscribe(TOPIC)
        command(stack['base'], 'start', 'simulator')
        edge = reader.read(timeout=30)
        receive(stack, 'writer', lambda event: event['event_id'] == edge['event_id'], timeout=30)
    finally:
        reader.close()


@pytest.mark.parametrize('actuator', ['led', 'buzzer'])
def test_real_round_trip_has_correlated_ack_and_changed_telemetry(stack, actuator):
    off = actuator_command(actuator, False)
    send_command(stack, off)
    receive(stack, 'commands', lambda event: event['type'] == 'ack' and event['correlation_id'] == off['correlation_id'])
    before = receive(stack, 'writer', lambda event: event['data']['actuators'][actuator]['actual_state'] is False)
    on = actuator_command(actuator, True)
    send_command(stack, on)
    ack = receive(stack, 'commands', lambda event: event['type'] == 'ack' and event['correlation_id'] == on['correlation_id'])
    assert ack['received_at'] is not None
    assert ack['data']['result'] == 'applied' and ack['data']['applied_state'] is True
    assert ack['data']['command_id'] == on['data']['command_id']
    after = receive(stack, 'writer', lambda event: event['data']['actuators'][actuator]['actual_state'] is True)
    assert after['received_at'] is not None
    assert datetime.fromisoformat(after['received_at'].replace('Z', '+00:00')).tzinfo is not None
    if actuator == 'led':
        assert after['data']['measurements']['light']['value'] > before['data']['measurements']['light']['value'] + 35


def test_duplicate_input_keeps_first_received_at_across_restart(stack):
    reader = Probe(stack, 'coldsafe-gateway', 'MQTT_GATEWAY_PASSWORD')
    sender = Probe(stack, 'sim-lab-01', 'MQTT_SIMULATOR_PASSWORD')
    try:
        reader.subscribe(TOPIC)
        edge = reader.read()
        command(stack['base'], 'stop', 'simulator')
        edge['event_id'] = edge['correlation_id'] = str(uuid4())
        original = json.dumps(edge, separators=(',', ':')).encode()
        send_raw(sender, TOPIC, original)
        delivered = receive(stack, 'writer', lambda event: event['event_id'] == edge['event_id'])
        query = 'SELECT CAST(body AS TEXT),hex(input) FROM ingress WHERE event_id=? AND sent=1'
        persisted = wait_journal(stack, query, (edge['event_id'],))
        assert json.loads(persisted[0][0]) == delivered
        assert bytes.fromhex(persisted[0][1]) == original
        for restart in (False, True):
            if restart:
                command(stack['base'], 'restart', 'gateway')
            barrier = {**edge, 'event_id': str(uuid4())}
            barrier['correlation_id'] = barrier['event_id']
            barrier_raw = json.dumps(barrier).encode()
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                send_raw(sender, TOPIC, original)
                send_raw(sender, TOPIC, barrier_raw)
                if journal(stack, 'SELECT event_id FROM ingress WHERE event_id=?', (barrier['event_id'],)):
                    break
                time.sleep(0.2)
            receive(stack, 'writer', lambda event: event['event_id'] == barrier['event_id'])
            assert journal(stack, query, (edge['event_id'],)) == persisted
        # Duplicates may be suppressed or redelivered identically; never mint new receipt times.
        with connect(stack['broker'], 'writer') as channel:
            while True:
                method, _, body = channel.basic_get('coldsafe.writer')
                if not method:
                    break
                channel.basic_ack(method.delivery_tag)
                event = json.loads(body)
                if event['event_id'] == edge['event_id']:
                    assert event == delivered
    finally:
        reader.close()
        sender.close()
        start_simulator(stack)


def test_malformed_mqtt_preserves_raw_bytes_and_publishes_processing_error(stack):
    sender = Probe(stack, 'sim-lab-01', 'MQTT_SIMULATOR_PASSWORD')
    raw = b'{"invalid":"' + secrets.token_hex(8).encode() + b'"\xff'
    try:
        send_raw(sender, TOPIC, raw)
        # hex avoids JSON coercion of arbitrary non-UTF-8 input in the test introspection.
        rows = wait_journal(stack, 'SELECT CAST(event AS TEXT) FROM errors WHERE transport=? AND hex(body)=? AND sent=1',
                            ('mqtt', raw.hex().upper()))
        error = json.loads(rows[0][0])
        assert error['type'] == 'processing_error'
        received = receive(stack, 'delivery', lambda event: event['event_id'] == error['event_id'])
        assert received == error
    finally:
        sender.close()


def test_malformed_amqp_command_goes_to_dlq_with_original_bytes(stack):
    raw = b'{"broken":' + secrets.token_hex(8).encode()
    with connect(stack['broker'], 'api') as channel:
        channel.basic_publish('coldsafe.events', 'v3.command.' + stack['catalog']['device_record_id'], raw,
                              pika.BasicProperties(content_type='application/json', delivery_mode=2,
                                                   message_id=str(uuid4())), mandatory=True)
    with connect(stack['broker'], 'audit') as channel:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            method, properties, body = channel.basic_get('coldsafe.dlq')
            if not method:
                channel.connection.sleep(0.1)
                continue
            channel.basic_ack(method.delivery_tag)
            if body == raw:
                assert properties.headers['x-death'][0]['queue'] == 'coldsafe.gateway'
                assert properties.headers['x-death'][0]['reason'] == 'rejected'
                break
        else:
            pytest.fail('Malformed command was not preserved in DLQ')


def test_rabbit_outage_spools_telemetry_and_drains_after_reconnection(stack):
    command(stack['base'], 'stop', 'rabbitmq')
    try:
        queued = wait_journal(stack, 'SELECT event_id,CAST(body AS TEXT) FROM ingress WHERE sent=0', timeout=20)
    finally:
        command(stack['base'], 'up', '-d', '--wait', '--wait-timeout', '120', 'rabbitmq')
        stack['broker']['port'] = port(stack['base'], 'rabbitmq', 5672)
    identifier, body = queued[0]
    received = receive(stack, 'writer', lambda event: event['event_id'] == identifier, timeout=30)
    assert received == json.loads(body)
    wait_journal(stack, 'SELECT event_id FROM ingress WHERE event_id=? AND sent=1', (identifier,), timeout=30)


def test_mosquitto_restart_restores_telemetry_and_command_round_trip(stack):
    previous = receive(stack, 'writer', lambda event: event['type'] == 'telemetry')
    command(stack['base'], 'restart', 'mosquitto')
    command(stack['base'], 'up', '-d', '--wait', '--wait-timeout', '90', 'mosquitto')
    stack['port'] = port(stack['base'], 'mosquitto', 1883)
    receive(stack, 'writer', lambda event: event['occurred_at'] > previous['occurred_at'], timeout=30)
    requested = actuator_command('buzzer', False)
    send_command(stack, requested)
    receive(stack, 'commands', lambda event: event['type'] == 'ack' and event['correlation_id'] == requested['correlation_id'], timeout=30)


def test_puback_with_simulator_stopped_does_not_invent_device_ack(stack):
    command(stack['base'], 'stop', 'simulator')
    requested = actuator_command()
    try:
        send_command(stack, requested)
        wait_journal(stack, 'SELECT command_id FROM commands WHERE command_id=? AND sent=1',
                     (requested['data']['command_id'],))
        with connect(stack['broker'], 'commands') as channel:
            deadline = time.monotonic() + 1.5
            while time.monotonic() < deadline:
                method, _, body = channel.basic_get('coldsafe.commands')
                if method:
                    channel.basic_ack(method.delivery_tag)
                    event = json.loads(body)
                    assert not (event['type'] == 'ack' and event['correlation_id'] == requested['correlation_id'])
                else:
                    channel.connection.sleep(0.1)
        assert not journal(stack, 'SELECT event_id FROM ingress WHERE json_extract(CAST(body AS TEXT),\'$.correlation_id\')=?',
                           (requested['correlation_id'],))
    finally:
        start_simulator(stack)


def test_revoked_postgres_scope_rejects_input_and_restored_scope_accepts_it(stack):
    reader = Probe(stack, 'coldsafe-gateway', 'MQTT_GATEWAY_PASSWORD')
    sender = Probe(stack, 'sim-lab-01', 'MQTT_SIMULATOR_PASSWORD')
    try:
        reader.subscribe(TOPIC)
        edge = reader.read()
        command(stack['base'], 'stop', 'simulator')
        edge['event_id'] = edge['correlation_id'] = str(uuid4())
        raw = json.dumps(edge).encode()
        try:
            with psycopg.connect(**stack['postgres']) as database:
                database.execute('UPDATE devices SET is_active=false WHERE id=%s',
                                 (stack['catalog']['device_record_id'],))
            send_raw(sender, TOPIC, raw)
            rejected = wait_journal(stack, 'SELECT CAST(event AS TEXT) FROM errors WHERE code=? AND hex(body)=? AND sent=1',
                                    ('UNAUTHORIZED_SCOPE', raw.hex().upper()))
            error = json.loads(rejected[0][0])
            receive(stack, 'delivery', lambda event: event['event_id'] == error['event_id'])
            assert not journal(stack, 'SELECT event_id FROM ingress WHERE event_id=?', (edge['event_id'],))
        finally:
            with psycopg.connect(**stack['postgres']) as database:
                database.execute('UPDATE devices SET is_active=true WHERE id=%s',
                                 (stack['catalog']['device_record_id'],))
        edge['event_id'] = edge['correlation_id'] = str(uuid4())
        send_raw(sender, TOPIC, json.dumps(edge).encode())
        received = receive(stack, 'writer', lambda event: event['event_id'] == edge['event_id'])
        assert received['received_at'] is not None
    finally:
        reader.close()
        sender.close()
        start_simulator(stack)


def test_duplicate_amqp_command_is_not_republished_or_reapplied(stack):
    on = actuator_command('led', True)
    send_command(stack, on)
    receive(stack, 'commands', lambda event: event['type'] == 'ack' and event['correlation_id'] == on['correlation_id'])
    receive(stack, 'writer', lambda event: event['data']['actuators']['led']['actual_state'] is True)
    off = actuator_command('led', False)
    send_command(stack, off)
    receive(stack, 'commands', lambda event: event['type'] == 'ack' and event['correlation_id'] == off['correlation_id'])
    receive(stack, 'writer', lambda event: event['data']['actuators']['led']['actual_state'] is False)
    query = 'SELECT CAST(body AS TEXT),sent FROM commands WHERE command_id=?'
    persisted = journal(stack, query, (on['data']['command_id'],))
    assert len(persisted) == 1 and persisted[0][1] == 1
    observer = Probe(stack, 'sim-lab-01', 'MQTT_SIMULATOR_PASSWORD')
    try:
        observer.subscribe('coldsafe/v3/devices/sim-lab-01/commands')
        assert datetime.now(timezone.utc) < datetime.fromisoformat(on['data']['deadline_at'].replace('Z', '+00:00'))
        send_command(stack, on)
        barrier = actuator_command('led', False)
        send_command(stack, barrier)
        # A subsequent command proves the replay was consumed before inspecting transport/state.
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            message = observer.messages.get(timeout=max(0.1, deadline - time.monotonic()))
            forwarded = json.loads(message.payload)
            assert forwarded['data']['command_id'] != on['data']['command_id']
            if forwarded['data']['command_id'] == barrier['data']['command_id']:
                break
        else:
            pytest.fail('Command barrier did not reach MQTT')
        with connect(stack['broker'], 'commands') as channel:
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                method, _, body = channel.basic_get('coldsafe.commands')
                if not method:
                    channel.connection.sleep(0.05)
                    continue
                channel.basic_ack(method.delivery_tag)
                event = json.loads(body)
                assert not (event['type'] == 'ack' and event['correlation_id'] == on['correlation_id'])
                if event['type'] == 'ack' and event['correlation_id'] == barrier['correlation_id']:
                    assert event['data']['applied_state'] is False
                    barrier_ack_time = datetime.fromisoformat(event['occurred_at'].replace('Z', '+00:00'))
                    break
            else:
                pytest.fail('Command barrier ACK did not return through RabbitMQ')
        after = receive(stack, 'writer', lambda event: datetime.fromisoformat(event['occurred_at'].replace('Z', '+00:00')) >= barrier_ack_time)
        assert after['data']['actuators']['led']['actual_state'] is False
        assert journal(stack, query, (on['data']['command_id'],)) == persisted
    finally:
        observer.close()


def test_mqtt_outage_retries_amqp_command_then_preserves_it_in_dlq(stack):
    command(stack['base'], 'stop', 'mosquitto')
    requested = actuator_command('buzzer', True)
    try:
        raw = send_command(stack, requested)
        with connect(stack['broker'], 'audit') as channel:
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                method, properties, body = channel.basic_get('coldsafe.dlq')
                if not method:
                    channel.connection.sleep(0.05)
                    continue
                channel.basic_ack(method.delivery_tag)
                if body != raw:
                    continue
                assert properties.message_id == requested['event_id']
                assert properties.correlation_id == requested['correlation_id']
                assert properties.content_type == 'application/json' and properties.delivery_mode == 2
                assert properties.headers['x-death'][0]['queue'] == 'coldsafe.gateway'
                assert properties.headers['x-death'][0]['reason'] == 'rejected'
                break
            else:
                pytest.fail('Unavailable MQTT did not exhaust retries and preserve command in DLQ')
        attempts = journal(stack, 'SELECT code FROM errors WHERE transport=? AND hex(body)=? ORDER BY rowid',
                           ('amqp', raw.hex().upper()))
        assert attempts == [['PROCESSING_FAILED'], ['PROCESSING_FAILED'], ['RETRY_EXHAUSTED']]
        assert journal(stack, 'SELECT sent FROM commands WHERE command_id=?',
                       (requested['data']['command_id'],)) == [[0]]
    finally:
        command(stack['base'], 'up', '-d', '--wait', '--wait-timeout', '90', 'mosquitto')
        stack['port'] = port(stack['base'], 'mosquitto', 1883)
    receive(stack, 'writer', lambda event: event['occurred_at'] > requested['occurred_at'], timeout=30)
