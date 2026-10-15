"""Opt-in B2-12 checks with disposable real MQTT/AMQP/PostgreSQL/InfluxDB."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

import psycopg
import pytest
import yaml
from influxdb_client import InfluxDBClient

from backend.app.domain.reading_classification import ReadingStatus
from backend.app.domain.telemetry import TelemetryPayload
from backend.app.repositories.influxdb_client import InfluxSettings, create_influx_repository
from backend.tests.infra.test_gateway_integration import BUS, receive
from backend.tests.infra.test_rabbitmq_integration import connect, publish

ROOT = Path(__file__).resolve().parents[3]
pytestmark = pytest.mark.integration
FIELDS = {'ambient_temperature': 'ambient_temperature_c', 'humidity': 'humidity_percent',
          'light': 'light_percent', 'vibration': 'vibration_rms_mm_s',
          'motor_current': 'motor_current_a', 'motor_temperature': 'motor_temperature_c'}


def run(state, *arguments):
    # The shell's personal credentials must not override this project's temporary .env.
    environment = {key: value for key, value in os.environ.items() if key not in state['values']}
    result = subprocess.run([*state['base'], *arguments], env=environment,
                            capture_output=True, text=True, timeout=240)
    output, stdout = result.stdout + result.stderr, result.stdout
    for key, value in state['values'].items():
        if value and any(part in key for part in ('PASSWORD', 'TOKEN', 'SECRET')):
            output = output.replace(value, '[REDACTED]')
            stdout = stdout.replace(value, '[REDACTED]')
    assert result.returncode == 0, output
    return stdout


def influx(state, path, *, method='GET', data=None, token=None, content_type='application/json'):
    body = (json.dumps(data).encode() if content_type == 'application/json' else data.encode()) if data is not None else None
    request = Request(state['url'] + path, data=body, method=method,
                      headers={'Authorization': 'Token ' + (token or state['values']['DOCKER_INFLUXDB_INIT_ADMIN_TOKEN']),
                               'Content-Type': content_type})
    with urlopen(request, timeout=10) as response:
        raw = response.read()
        return json.loads(raw) if raw else None


def rows(state, bucket='telemetry_live', *, event_id=None, measurement='equipment_reading_v3'):
    query = '''from(bucket: _bucket) |> range(start: 0)
        |> filter(fn: (r) => r._measurement == _measurement)
        |> filter(fn: (r) => _event == "" or r.event_id == _event)
        |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")'''
    with InfluxDBClient(url=state['url'], org=state['org'],
                        token=state['values']['DOCKER_INFLUXDB_INIT_ADMIN_TOKEN']) as client:
        tables = client.query_api().query(query, org=state['org'],
                                         params={'_bucket': bucket, '_measurement': measurement,
                                                 '_event': event_id or ''})
        return [{key: value for key, value in record.values.items()
                 if key not in ('result', 'table', '_start', '_stop')}
                for table in tables for record in table.records]


def wait_point(state, event, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = rows(state, event_id=event['event_id'])
        if result:
            assert len(result) == 1
            return result[0]
        time.sleep(0.1)
    pytest.fail('Writer did not persist the expected event')


def queue_size(state):
    with connect(state['broker'], 'writer') as channel:
        return channel.queue_declare('coldsafe.writer', passive=True).method.message_count


def wait_drained(state, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if queue_size(state) == 0:
            return
        time.sleep(0.1)
    pytest.fail('Writer queue did not drain')


def send(state, event):
    with connect(state['broker'], 'gateway') as channel:
        publish(channel, {'payload': event, 'routing_key': 'v3.telemetry.' + event['device_record_id']})


@pytest.fixture(scope='module')
def stack(request):
    if os.environ.get('COLDSAFE_WRITER_INTEGRATION') != '1':
        pytest.skip('Set COLDSAFE_WRITER_INTEGRATION=1 for disposable writer/brokers/InfluxDB checks')
    project = 'coldsafe-b212-' + secrets.token_hex(4)
    with tempfile.TemporaryDirectory(prefix=project) as folder:
        directory = Path(folder)
        env_file = directory / '.env'
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/generate-secrets.py'),
                                 '--env-file', str(env_file)], capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, 'Disposable credentials generation failed'
        values = dict(line.split('=', 1) for line in env_file.read_text().splitlines()
                      if line and not line.startswith('#'))
        # Populated after InfluxDB creates a bucket-scoped write-only authorization.
        values['INFLUXDB_WRITER_TOKEN'] = ''
        catalog_dir = directory / 'catalog'
        catalog_dir.mkdir(mode=0o755)
        catalog_file = catalog_dir / 'catalog.json'
        catalog_file.write_bytes((ROOT / 'simulator/catalog.example.json').read_bytes())
        catalog_file.chmod(0o644)
        catalog = json.loads(catalog_file.read_text())
        original = yaml.safe_load((ROOT / 'compose.yaml').read_text())
        names = ('rabbitmq-init', 'rabbitmq', 'mosquitto-init', 'mosquitto', 'postgres',
                 'influxdb', 'gateway', 'simulator', 'writer')
        services = {name: original['services'][name] for name in names}
        for name, service in services.items():
            if 'build' in service:
                service['build']['context'] = str(ROOT / service['build']['context'])
                service['image'] = project + '-' + name
        for name, internal in (('rabbitmq', 5672), ('mosquitto', 1883), ('postgres', 5432), ('influxdb', 8086)):
            services[name]['ports'] = [f'127.0.0.1::{internal}']
            services[name]['networks'].append('test-edge')
        for name in ('simulator', 'gateway', 'writer'):
            for volume in services[name].get('volumes', []):
                if isinstance(volume, dict) and volume.get('target') == '/catalog':
                    volume['source'] = str(catalog_dir)
        services['simulator']['environment']['SIMULATOR_INTERVAL_SECONDS'] = '0.2'
        owner = str(uuid4())
        services['gateway']['environment']['GATEWAY_OWNER_USER_ID'] = owner
        services['writer']['environment']['WRITER_OWNER_USER_ID'] = owner
        services['writer']['environment']['INFLUXDB_LIVE_BUCKET'] = 'telemetry_live'
        config = {'services': services,
                  'networks': {'coldsafe-internal': {'internal': True}, 'test-edge': {}},
                  'volumes': {name: {} for name in original['volumes']}}
        compose = directory / 'compose.yaml'
        compose.write_text(yaml.safe_dump(config))
        state = {'values': values, 'org': values.get('DOCKER_INFLUXDB_INIT_ORG', 'coldsafe'),
                 'catalog': catalog, 'base': ['docker', 'compose', '-p', project, '--env-file', str(env_file),
                                           '-f', str(compose), '--profile', 'aiot', '--profile', 'simulator']}

        def port(name, internal):
            return int(run(state, 'port', name, str(internal)).strip().rsplit(':', 1)[1])

        try:
            run(state, 'up', '-d', '--build', '--wait', '--wait-timeout', '120',
                'rabbitmq', 'mosquitto', 'postgres', 'influxdb')
            state['url'] = 'http://127.0.0.1:' + str(port('influxdb', 8086))
            state['port'] = port('mosquitto', 1883)
            state['broker'] = {'port': port('rabbitmq', 5672),
                               'passwords': {role: values[f'RABBITMQ_{role.upper()}_PASSWORD']
                                             for role in ('writer', 'gateway', 'delivery', 'audit')}}
            state['postgres'] = {'host': '127.0.0.1', 'port': port('postgres', 5432),
                                 'dbname': values.get('POSTGRES_DB', 'coldsafe'),
                                 'user': values.get('POSTGRES_USER', 'coldsafe'), 'password': values['POSTGRES_PASSWORD']}
            with psycopg.connect(**state['postgres']) as database:
                for migration in sorted((ROOT / 'backend/migrations').glob('*.sql')):
                    database.execute(migration.read_text())
                database.execute('INSERT INTO users(id,email,password_hash) VALUES (%s,%s,%s)',
                                 (owner, 'writer-test@example.invalid', 'unused-no-http-login'))
                database.execute('INSERT INTO environments(id,owner_user_id,name) VALUES (%s,%s,%s)',
                                 (catalog['environment_id'], owner, 'Writer test'))
                database.execute('INSERT INTO devices(id,environment_id,mqtt_device_id,name) VALUES (%s,%s,%s,%s)',
                                 (catalog['device_record_id'], catalog['environment_id'], catalog['device_id'], 'Simulator'))
            org_id = influx(state, '/api/v2/orgs?' + urlencode({'org': state['org']}))['orgs'][0]['id']
            buckets = {}
            for name in ('telemetry_live', 'telemetry_synthetic'):
                buckets[name] = influx(state, '/api/v2/buckets', method='POST',
                                      data={'orgID': org_id, 'name': name, 'retentionRules': []})['id']
            authorization = influx(state, '/api/v2/authorizations', method='POST',
                                   data={'orgID': org_id, 'description': 'Disposable write-only live writer',
                                         'permissions': [{'action': 'write', 'resource':
                                                          {'type': 'buckets', 'id': buckets['telemetry_live'], 'orgID': org_id}}]})
            values['INFLUXDB_WRITER_TOKEN'] = authorization['token']
            env_file.write_text('\n'.join(f'{key}={value}' for key, value in values.items()) + '\n')
            run(state, 'up', '-d', '--build', '--wait', '--wait-timeout', '120', 'gateway', 'writer', 'simulator')
            # Compose may recreate built dependencies; ephemeral host ports belong to the current container.
            state['broker']['port'] = port('rabbitmq', 5672)
            state['url'] = 'http://127.0.0.1:' + str(port('influxdb', 8086))
            state['event'] = receive(state, 'delivery', lambda event: event['type'] == 'telemetry', timeout=30)
            wait_point(state, state['event'])
            run(state, 'stop', 'simulator')
            wait_drained(state)
            yield state
        finally:
            try:
                if request.session.testsfailed:
                    print(run(state, 'logs', '--no-color', '--tail', '40', 'gateway', 'writer', 'simulator'))
            finally:
                run(state, 'down', '--volumes', '--remove-orphans')


def test_real_pipeline_persists_six_sensors_identity_timestamps_and_actuators(stack):
    event = stack['event']
    stored = wait_point(stack, event)
    for name in ('device_id', 'device_record_id', 'environment_id', 'event_id'):
        assert stored[name] == event[name]
    assert stored['equipment_id'] == event['data']['equipment']['equipment_id']
    assert stored['running'] == event['data']['equipment']['running']
    assert stored['_time'] == datetime.fromisoformat(event['received_at'].replace('Z', '+00:00'))
    for name in ('occurred_at', 'received_at', 'correlation_id', 'schema_version'):
        assert stored[name] == event[name]
    for role, field in FIELDS.items():
        assert stored[field] == event['data']['measurements'][role]['value']
        assert stored[role + '_sensor_id'] == stack['catalog']['sensors'][role]
    for role in ('led', 'buzzer'):
        assert stored[role + '_actual_state'] == event['data']['actuators'][role]['actual_state']
        assert stored[role + '_actuator_id'] == stack['catalog']['actuators'][role]


def test_stopped_writer_accumulates_real_mqtt_and_drains_after_restart(stack):
    run(stack, 'stop', 'writer')
    try:
        with connect(stack['broker'], 'delivery') as channel:
            while True:
                method, _, _ = channel.basic_get('coldsafe.delivery')
                if not method:
                    break
                channel.basic_ack(method.delivery_tag)
        run(stack, 'start', 'simulator')
        # Delivery is a separate subscriber, so observing it does not steal the writer's messages.
        events = [receive(stack, 'delivery', lambda event: event['type'] == 'telemetry') for _ in range(6)]
        run(stack, 'stop', 'simulator')
        assert queue_size(stack) > 0
    finally:
        run(stack, 'stop', 'simulator')
        run(stack, 'start', 'writer')
    for event in events:
        wait_point(stack, event)
    wait_drained(stack)


def test_replay_keeps_one_point_after_restart_and_equal_time_distinct_events_survive(stack):
    event = deepcopy(stack['event'])
    event['event_id'] = event['correlation_id'] = str(uuid4())
    # Integer and floating sensor values share one Influx field type across events.
    event['data']['measurements']['humidity']['value'] = 60
    send(stack, event)
    first = wait_point(stack, event)
    for restart in (False, True):
        if restart:
            run(stack, 'stop', 'writer')
            try:
                send(stack, event)
                with connect(stack['broker'], 'writer') as channel:
                    method, _, raw = channel.basic_get('coldsafe.writer')
                    assert method is not None and json.loads(raw)['event_id'] == event['event_id']
                    channel.basic_nack(method.delivery_tag, requeue=True)
            finally:
                run(stack, 'start', 'writer')
        else:
            send(stack, event)
        barrier = deepcopy(event)
        barrier['event_id'] = barrier['correlation_id'] = str(uuid4())
        barrier['data']['measurements']['humidity']['value'] = 60.5
        send(stack, barrier)
        assert wait_point(stack, barrier)['_time'] == first['_time']
        wait_drained(stack)
        assert rows(stack, event_id=event['event_id']) == [first]
        with connect(stack['broker'], 'audit') as channel:
            assert channel.basic_get('coldsafe.dlq')[0] is None


def test_legacy_v1_v2_history_and_synthetic_bucket_stay_isolated(stack):
    legacy = stack['values'].get('DOCKER_INFLUXDB_INIT_BUCKET', 'telemetry')
    resources = create_influx_repository(InfluxSettings(url=stack['url'], org=stack['org'], bucket=legacy,
                                                       token=stack['values']['DOCKER_INFLUXDB_INIT_ADMIN_TOKEN']))
    at = datetime.now(timezone.utc) - timedelta(seconds=3)
    device = 'legacy-' + uuid4().hex
    try:
        for version in (1, 2):
            resources.repository.save(payload=TelemetryPayload(schema_version=version, device_id=device,
                                                               temperature_c=5.0 + version, humidity_percent=60.0,
                                                               light_percent=40.0 if version == 2 else None),
                                      received_at=at + timedelta(seconds=version), status=ReadingStatus.NORMAL)
        history = resources.repository.list_history(device_id=device, start=at, end=at + timedelta(seconds=4), limit=10)
        assert [reading.schema_version for reading in history] == [1, 2]
        assert [reading.light_percent for reading in history] == [None, 40.0]
        assert resources.repository.get_latest(device) == history[-1]
    finally:
        resources.close()
    influx(stack, '/api/v2/write?' + urlencode({'org': stack['org'], 'bucket': 'telemetry_synthetic'}),
           method='POST', content_type='text/plain', data='synthetic_fixture value=1i')
    assert len(rows(stack, 'telemetry_synthetic', measurement='synthetic_fixture')) == 1
    assert rows(stack, measurement='synthetic_fixture') == []
    assert rows(stack, measurement='environment_reading') == []
    assert rows(stack, legacy) == []
    assert rows(stack, 'telemetry_synthetic') == []


def test_live_writer_token_cannot_read_any_bucket_or_write_legacy_and_synthetic(stack):
    token = stack['values']['INFLUXDB_WRITER_TOKEN']
    legacy = stack['values'].get('DOCKER_INFLUXDB_INIT_BUCKET', 'telemetry')
    for bucket in ('telemetry_live', legacy, 'telemetry_synthetic'):
        with pytest.raises(HTTPError) as denied:
            influx(stack, '/api/v2/query?' + urlencode({'org': stack['org']}), method='POST', token=token,
                   data={'query': f'from(bucket: "{bucket}") |> range(start: 0)'})
        # InfluxDB also hides existing buckets from unauthorized query tokens with 404.
        assert denied.value.code in (401, 403, 404)
        if bucket != 'telemetry_live':
            with pytest.raises(HTTPError) as denied:
                influx(stack, '/api/v2/write?' + urlencode({'org': stack['org'], 'bucket': bucket}),
                       method='POST', token=token, content_type='text/plain', data='forbidden_fixture value=1i')
            assert denied.value.code in (401, 403)
            assert rows(stack, bucket, measurement='forbidden_fixture') == []


def test_real_influx_outage_exhausts_retries_preserves_raw_dlq_and_recovers(stack):
    event = deepcopy(stack['event'])
    event['event_id'] = event['correlation_id'] = str(uuid4())
    run(stack, 'stop', 'influxdb')
    try:
        with connect(stack['broker'], 'gateway') as channel:
            raw = publish(channel, {'payload': event, 'routing_key': 'v3.telemetry.' + event['device_record_id']})
        with connect(stack['broker'], 'audit') as channel:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                method, properties, body = channel.basic_get('coldsafe.dlq')
                if not method:
                    channel.connection.sleep(0.1)
                    continue
                channel.basic_ack(method.delivery_tag)
                assert body == raw
                assert properties.message_id == event['event_id']
                assert properties.correlation_id == event['correlation_id']
                assert properties.headers['x-death'][0]['queue'] == 'coldsafe.writer'
                assert properties.headers['x-death'][0]['reason'] == 'rejected'
                break
            else:
                pytest.fail('InfluxDB outage did not preserve telemetry in writer DLQ')
        errors = []
        # Every error publish is confirmed before the original reaches the DLQ.
        with connect(stack['broker'], 'delivery') as channel:
            while True:
                method, _, body = channel.basic_get('coldsafe.delivery')
                if not method:
                    break
                channel.basic_ack(method.delivery_tag)
                message = json.loads(body)
                if message['type'] == 'processing_error':
                    BUS.validate(message)
                    errors.append(message)
        assert [(error['data']['code'], error['data']['attempt']) for error in errors] == [
            ('PROCESSING_FAILED', 1), ('PROCESSING_FAILED', 2), ('RETRY_EXHAUSTED', 3)]
        assert all(error['data']['source_event_id'] is None and error['device_id'] is None for error in errors)
    finally:
        run(stack, 'up', '-d', '--wait', '--wait-timeout', '90', 'influxdb')
        stack['url'] = 'http://127.0.0.1:' + run(stack, 'port', 'influxdb', '8086').strip().rsplit(':', 1)[1]
    assert rows(stack, event_id=event['event_id']) == []
    # An operator can replay the preserved original after repairing the dependency.
    send(stack, event)
    wait_point(stack, event)
    wait_drained(stack)
