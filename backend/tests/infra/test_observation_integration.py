"""B2-16 acceptance against disposable brokers/databases and the real browser."""
from copy import deepcopy
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

import pika
import psycopg
import pytest

from backend.app.api.auth import AuthService
from backend.app.config.settings import RuntimeSettings
from backend.app.repositories.postgres import MIGRATIONS
from backend.tests.infra.test_dashboard_integration import free_port, wait_http
from backend.tests.infra.test_messaging_integration import api_request, wait_metrics
from backend.tests.infra.test_rabbitmq_integration import connect, publish
from backend.tests.infra.test_writer_integration import (
    FIELDS, ROOT, queue_size, rows, run, send, stack, wait_drained, wait_point,
)

pytestmark = pytest.mark.integration
SAMPLES = '/api/v3/messaging/messages'


def wait_samples(url, token, predicate, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status, body = api_request(url, SAMPLES, token=token)
        if status == 200 and predicate(body['data']):
            return body['data']
        time.sleep(0.1)
    pytest.fail(f'Observer did not reach expected state: status={status}, body={body}')


def preserved_dead_letter(state, expected, *, timeout=30):
    """Inspect through audit credentials and requeue; never acknowledge or purge."""
    with connect(state['broker'], 'audit') as channel:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            count = channel.queue_declare('coldsafe.dlq', passive=True).method.message_count
            method, properties, raw = channel.basic_get('coldsafe.dlq', auto_ack=False)
            if method:
                channel.basic_nack(method.delivery_tag, requeue=True)
                assert raw == expected
                assert properties.headers['x-death'][0]['queue'] == 'coldsafe.writer'
                assert properties.headers['x-death'][0]['reason'] == 'rejected'
                return count, raw, properties.message_id, properties.correlation_id
            channel.connection.sleep(0.1)
    pytest.fail('Controlled invalid telemetry did not reach the writer DLQ')


def test_real_observation_preserves_writer_and_dlq_with_current_owner_and_browser(stack):
    pg, values = stack['postgres'], stack['values']
    stack['port'] = int(run(stack, 'port', 'mosquitto', '1883').strip().rsplit(':', 1)[1])
    api_url, web_url = (f'http://127.0.0.1:{free_port()}' for _ in range(2))
    password, other_owner = secrets.token_urlsafe(24), uuid4()
    with psycopg.connect(**pg) as database:
        owner = database.execute('SELECT owner_user_id FROM environments WHERE id=%s',
                                 (stack['catalog']['environment_id'],)).fetchone()[0]
    settings = RuntimeSettings(
        mqtt_host='127.0.0.1', mqtt_port=stack['port'], mqtt_topic='coldsafe/v1/telemetry', mqtt_qos=1,
        mqtt_client_id='b216-' + secrets.token_hex(5), mqtt_backend_username='coldsafe-backend',
        mqtt_backend_password=values['MQTT_BACKEND_PASSWORD'], auth_jwt_secret=values['AUTH_JWT_SECRET'],
        influxdb_url=stack['url'], influxdb_org=stack['org'], influxdb_bucket='telemetry_live',
        influxdb_token=values['DOCKER_INFLUXDB_INIT_ADMIN_TOKEN'], postgres_host=pg['host'],
        postgres_port=pg['port'], postgres_db=pg['dbname'], postgres_user=pg['user'],
        postgres_password=pg['password'], cors_origins=web_url, rabbitmq_host='127.0.0.1',
        rabbitmq_port=stack['broker']['port'], rabbitmq_management_port=stack['management_port'],
        rabbitmq_monitor_password=values['RABBITMQ_MONITOR_PASSWORD'],
        rabbitmq_observability_password=values['RABBITMQ_OBSERVABILITY_PASSWORD'],
        aiot_enabled=False, _env_file=None)
    auth = AuthService(settings)
    with psycopg.connect(**pg) as database:
        database.execute('CREATE TABLE IF NOT EXISTS schema_migrations ('
                         'version integer PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())')
        for version, _path in MIGRATIONS:
            database.execute('INSERT INTO schema_migrations(version) VALUES (%s) ON CONFLICT DO NOTHING', (version,))
        database.execute("UPDATE users SET email=%s,password_hash=%s,role='admin' WHERE id=%s",
                         ('observation-admin@example.invalid', auth._passwords.hash(password), owner))
        for name, role, user_id in (('other-admin', 'admin', other_owner),
                                    ('operator', 'operator', uuid4()), ('viewer', 'viewer', uuid4())):
            database.execute('INSERT INTO users(id,email,password_hash,role) VALUES (%s,%s,%s,%s)',
                             (user_id, f'observation-{name}@example.invalid', auth._passwords.hash(password), role))
    observer_broker = {**stack['broker'], 'passwords': {
        'observability': values['RABBITMQ_OBSERVABILITY_PASSWORD']}}
    for forbidden in ('coldsafe.writer', 'coldsafe.dlq'):
        with connect(observer_broker, 'observability') as channel:
            with pytest.raises(pika.exceptions.ChannelClosedByBroker) as denied:
                channel.basic_get(forbidden)
            assert denied.value.reply_code == 403

    node = os.environ.get('COLDSAFE_NODE_BINARY') or shutil.which('node')
    assert node, 'Node.js is required for the real observation browser checks'
    environment = {**os.environ, **values, 'VITE_AIOT_ENABLED': 'false', 'VITE_API_BASE_URL': api_url}
    for key, value in settings.model_dump().items():
        if value is not None:
            environment[key.upper()] = value.get_secret_value() if hasattr(value, 'get_secret_value') else str(value)
    environment.update(MESSAGING_REAL_URL=web_url, MESSAGING_REAL_API_URL=api_url,
                       MESSAGING_REAL_PASSWORD=password,
                       MESSAGING_REAL_ADMIN_EMAIL='observation-admin@example.invalid')
    with tempfile.TemporaryDirectory(prefix='coldsafe-b216-web-') as folder:
        frontend = Path(folder) / 'frontend'
        frontend.mkdir()
        for name in ('src', 'public', 'e2e'):
            shutil.copytree(ROOT / 'frontend' / name, frontend / name)
        for name in ('index.html', 'package.json', 'vite.config.ts', 'tsconfig.app.json',
                     'playwright.observation.config.ts'):
            shutil.copyfile(ROOT / 'frontend' / name, frontend / name)
        dependencies = Path(os.environ.get('COLDSAFE_FRONTEND_NODE_MODULES', str(ROOT / 'frontend/node_modules')))
        (frontend / 'node_modules').symlink_to(dependencies, target_is_directory=True)
        processes = []
        with (Path(folder) / 'servers.log').open('w+') as logs:
            try:
                backend = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'backend.app.main:app',
                                            '--host', '127.0.0.1', '--port', api_url.rsplit(':', 1)[1]],
                                           cwd=ROOT, env=environment, stdout=logs, stderr=logs)
                processes.append(backend)
                wait_http(backend, api_url + '/health/ready')
                tokens = {}
                for role in ('admin', 'other-admin', 'operator', 'viewer'):
                    status, body = api_request(api_url, '/api/v1/auth/login', data={
                        'email': f'observation-{role}@example.invalid', 'password': password})
                    assert status == 200
                    tokens[role] = body['data']['token']
                assert api_request(api_url, SAMPLES)[0] == 401
                for role in ('operator', 'viewer'):
                    assert api_request(api_url, SAMPLES, token=tokens[role])[0] == 403
                wait_samples(api_url, tokens['admin'], lambda data: data['connected'])

                run(stack, 'stop', 'writer')
                events = []
                for _ in range(3):
                    event = deepcopy(stack['event'])
                    event['event_id'] = event['correlation_id'] = str(uuid4())
                    events.append(event)
                    send(stack, event)
                expected_ids = {event['event_id'] for event in events}
                wait_samples(api_url, tokens['admin'], lambda data:
                             expected_ids <= {sample['event_id'] for sample in data['messages']})
                wait_metrics(api_url, tokens['admin'], lambda queues:
                             next(row for row in queues if row['name'] == 'coldsafe.writer')['messages_ready'] >= 3)
                assert queue_size(stack) == 3
                assert all(rows(stack, event_id=event['event_id']) == [] for event in events)
                status, isolated = api_request(api_url, SAMPLES, token=tokens['other-admin'])
                assert status == 200
                assert isolated['data']['messages'] == isolated['data']['dead_letters'] == []
                assert isolated['data']['last_observed_at'] is None
                # Authorization must follow PostgreSQL ownership on every read, not sample-time ownership.
                with psycopg.connect(**pg) as database:
                    database.execute('UPDATE environments SET owner_user_id=%s WHERE id=%s',
                                     (other_owner, stack['catalog']['environment_id']))
                try:
                    revoked = api_request(api_url, SAMPLES, token=tokens['admin'])[1]['data']
                    assert revoked['messages'] == revoked['dead_letters'] == []
                    assert revoked['last_observed_at'] is None
                    reassigned = api_request(api_url, SAMPLES, token=tokens['other-admin'])[1]['data']
                    assert expected_ids <= {sample['event_id'] for sample in reassigned['messages']}
                finally:
                    with psycopg.connect(**pg) as database:
                        database.execute('UPDATE environments SET owner_user_id=%s WHERE id=%s',
                                         (owner, stack['catalog']['environment_id']))
                run(stack, 'start', 'writer')
                for event in events:
                    stored = wait_point(stack, event)
                    for role, field in FIELDS.items():
                        assert stored[field] == event['data']['measurements'][role]['value']
                wait_drained(stack)
                wait_metrics(api_url, tokens['admin'], lambda queues:
                             next(row for row in queues if row['name'] == 'coldsafe.writer')['messages'] == 0)

                invalid = deepcopy(stack['event'])
                invalid['event_id'] = invalid['correlation_id'] = str(uuid4())
                private_value = 'private-invalid-measurement-must-not-be-exposed'
                invalid['data']['measurements']['humidity']['value'] = private_value
                with connect(stack['broker'], 'gateway') as channel:
                    original = publish(channel, {'payload': invalid,
                                                 'routing_key': 'v3.telemetry.' + invalid['device_record_id']})
                before = preserved_dead_letter(stack, original)
                assert before[0] == 1 and before[2:] == (invalid['event_id'], invalid['correlation_id'])
                snapshot = wait_samples(api_url, tokens['admin'], lambda data:
                    any(sample['event_id'] == invalid['event_id'] for sample in data['dead_letters']))
                dead = next(sample for sample in snapshot['dead_letters'] if sample['event_id'] == invalid['event_id'])
                assert (dead['source_queue'], dead['reason'], dead['error_code']) == (
                    'coldsafe.writer', 'rejected', 'INVALID_SCHEMA')
                assert rows(stack, event_id=invalid['event_id']) == []
                for _ in range(3):
                    status, observed = api_request(api_url, SAMPLES, token=tokens['admin'])
                    assert status == 200 and private_value not in json.dumps(observed)
                    for sample in observed['data']['messages'] + observed['data']['dead_letters']:
                        assert set(sample) == {
                            'event_id', 'type', 'occurred_at', 'observed_at', 'device_record_id',
                            'device_id', 'environment_id', 'correlation_id', 'source_queue', 'reason', 'error_code'}
                isolated = api_request(api_url, SAMPLES, token=tokens['other-admin'])[1]['data']
                assert isolated['messages'] == isolated['dead_letters'] == []

                recovered = deepcopy(stack['event'])
                recovered['event_id'] = recovered['correlation_id'] = str(uuid4())
                send(stack, recovered)
                wait_point(stack, recovered)
                wait_drained(stack)
                environment.update(OBSERVATION_REAL_EVENT_ID=recovered['event_id'],
                                   OBSERVATION_REAL_DEAD_ID=invalid['event_id'])
                vite = subprocess.Popen([node, 'node_modules/vite/bin/vite.js', '--host', '127.0.0.1',
                                         '--port', web_url.rsplit(':', 1)[1], '--strictPort'],
                                        cwd=frontend, env=environment, stdout=logs, stderr=logs)
                processes.append(vite)
                wait_http(vite, web_url)
                result = subprocess.run([node, 'node_modules/@playwright/test/cli.js', 'test',
                                         '--config', 'playwright.observation.config.ts'], cwd=frontend,
                                        env=environment, capture_output=True, text=True, timeout=240)
                assert result.returncode == 0, (result.stdout + result.stderr).replace(password, '[REDACTED]')
                print(result.stdout)
                assert preserved_dead_letter(stack, original) == before
                assert rows(stack, event_id=invalid['event_id']) == []
                for event in [*events, recovered]:
                    stored = rows(stack, event_id=event['event_id'])
                    assert len(stored) == 1
                    for role, field in FIELDS.items():
                        assert stored[0][field] == event['data']['measurements'][role]['value']
                print('Real B2-16: independent observer, role/owner isolation and revocation, '
                      'writer backlog/drain, six-sensor exact persistence, safe summaries, '
                      'DLQ bytes/count preservation after API/browser reads, and recovery passed.')
            except BaseException:
                logs.flush()
                logs.seek(0)
                output = ''.join(logs.readlines()[-40:])
                for key, value in {**values, 'TEST_PASSWORD': password}.items():
                    if value and any(part in key for part in ('PASSWORD', 'TOKEN', 'SECRET')):
                        output = output.replace(value, '[REDACTED]')
                print(output)
                raise
            finally:
                for process in reversed(processes):
                    process.terminate()
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
