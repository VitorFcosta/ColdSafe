"""B2-15: real, disposable broker metrics through authenticated HTTP and a browser."""
import base64
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
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pika
import psycopg
import pytest

from backend.app.api.auth import AuthService
from backend.app.api.messaging import create_messaging_router
from backend.app.config.settings import RuntimeSettings
from backend.app.repositories.postgres import MIGRATIONS
from backend.app.services.messaging import MessagingService
from backend.tests.infra.test_dashboard_integration import free_port, wait_http
from backend.tests.infra.test_rabbitmq_integration import connect
from backend.tests.infra.test_writer_integration import ROOT, run, send, stack

pytestmark = pytest.mark.integration


def management(state, path='/api/queues/coldsafe', *, method='GET', data=None):
    password = state['values']['RABBITMQ_MONITOR_PASSWORD']
    authorization = base64.b64encode(f'coldsafe-monitor:{password}'.encode()).decode()
    request = Request(f'http://127.0.0.1:{state["management_port"]}' + path,
                      method=method, data=json.dumps(data).encode() if data is not None else None,
                      headers={'Authorization': 'Basic ' + authorization,
                               'Content-Type': 'application/json'})
    with urlopen(request, timeout=5) as response:
        return json.load(response)


def api_request(url, path, *, token=None, data=None):
    request = Request(url + path, data=json.dumps(data).encode() if data is not None else None,
                      headers={'Content-Type': 'application/json',
                               **({'Authorization': 'Bearer ' + token} if token else {})})
    try:
        with urlopen(request, timeout=10) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        return error.code, json.load(error)


def wait_metrics(url, token, predicate, timeout=35):
    __tracebackhide__ = True
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status, body = api_request(url, '/api/v3/messaging', token=token)
        if status == 200 and predicate(body['data']['queues']):
            return body['data']
        time.sleep(0.2)
    pytest.fail(f'Real messaging metrics did not reach the expected broker state: '
                f'status={status}, queues={body.get("data", {}).get("queues", [])}')


def test_real_metrics_least_privilege_timeout_recovery_and_browser(stack):
    pg, values = stack['postgres'], stack['values']
    stack['port'] = int(run(stack, 'port', 'mosquitto', '1883').strip().rsplit(':', 1)[1])
    run(stack, 'stop', 'writer')
    api_url, web_url = (f'http://127.0.0.1:{free_port()}' for _ in range(2))
    password = secrets.token_urlsafe(24)
    with psycopg.connect(**pg) as database:
        owner = database.execute('SELECT owner_user_id FROM environments WHERE id=%s',
                                 (stack['catalog']['environment_id'],)).fetchone()[0]
    settings = RuntimeSettings(
        mqtt_host='127.0.0.1', mqtt_port=stack['port'], mqtt_topic='coldsafe/v1/telemetry', mqtt_qos=1,
        mqtt_client_id='b215-' + secrets.token_hex(5), mqtt_backend_username='coldsafe-backend',
        mqtt_backend_password=values['MQTT_BACKEND_PASSWORD'], auth_jwt_secret=values['AUTH_JWT_SECRET'],
        influxdb_url=stack['url'], influxdb_org=stack['org'], influxdb_bucket='telemetry_live',
        influxdb_token=values['DOCKER_INFLUXDB_INIT_ADMIN_TOKEN'], postgres_host=pg['host'],
        postgres_port=pg['port'], postgres_db=pg['dbname'], postgres_user=pg['user'],
        postgres_password=pg['password'], cors_origins=web_url, rabbitmq_host='127.0.0.1',
        rabbitmq_port=stack['broker']['port'], rabbitmq_management_port=stack['management_port'],
        rabbitmq_monitor_password=values['RABBITMQ_MONITOR_PASSWORD'], aiot_enabled=True,
        aiot_catalog_path=ROOT / 'simulator/catalog.example.json', aiot_owner_user_id=owner,
        rabbitmq_commands_password=values['RABBITMQ_COMMANDS_PASSWORD'],
        rabbitmq_delivery_password=values['RABBITMQ_DELIVERY_PASSWORD'], _env_file=None)
    auth = AuthService(settings)
    with psycopg.connect(**pg) as database:
        database.execute('CREATE TABLE IF NOT EXISTS schema_migrations ('
                         'version integer PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())')
        for version, _path in MIGRATIONS:
            database.execute('INSERT INTO schema_migrations(version) VALUES (%s) ON CONFLICT DO NOTHING', (version,))
        database.execute("UPDATE users SET email=%s,password_hash=%s,role='admin' WHERE id=%s",
                         ('messaging-admin@example.invalid', auth._passwords.hash(password), owner))
        for role in ('operator', 'viewer'):
            database.execute('INSERT INTO users(id,email,password_hash,role) VALUES (%s,%s,%s,%s)',
                             (uuid4(), f'messaging-{role}@example.invalid', auth._passwords.hash(password), role))
    # Add a known real backlog without letting the writer consume it.
    for _ in range(3):
        event = deepcopy(stack['event'])
        event['event_id'] = event['correlation_id'] = str(uuid4())
        send(stack, event)
    # The monitor may inspect aggregates, but cannot retrieve bodies, purge, publish or configure.
    for path, method, data in (
        ('/api/queues/coldsafe/coldsafe.writer/get', 'POST',
         {'count': 1, 'ackmode': 'ack_requeue_true', 'encoding': 'auto', 'truncate': 500}),
        ('/api/queues/coldsafe/coldsafe.writer/contents', 'DELETE', None),
    ):
        with pytest.raises(HTTPError) as denied:
            management(stack, path, method=method, data=data)
        assert denied.value.code in (401, 403)
    monitor_broker = {**stack['broker'], 'passwords': {'monitor': values['RABBITMQ_MONITOR_PASSWORD']}}
    for operation in ('get', 'publish', 'configure'):
        with connect(monitor_broker, 'monitor') as channel:
            with pytest.raises(pika.exceptions.ChannelClosedByBroker) as denied:
                if operation == 'get':
                    channel.basic_get('coldsafe.writer')
                elif operation == 'publish':
                    channel.basic_publish('coldsafe.events', 'v3.telemetry.forbidden', b'forbidden')
                else:
                    channel.queue_declare('forbidden')
            assert denied.value.reply_code == 403
    node = os.environ.get('COLDSAFE_NODE_BINARY') or shutil.which('node')
    assert node, 'Node.js is required for the real messaging browser checks'
    environment = {**os.environ, **values, 'VITE_AIOT_ENABLED': 'true', 'VITE_API_BASE_URL': api_url}
    for key, value in settings.model_dump().items():
        if value is not None:
            environment[key.upper()] = value.get_secret_value() if hasattr(value, 'get_secret_value') else str(value)
    environment.update(MESSAGING_REAL_URL=web_url, MESSAGING_REAL_API_URL=api_url,
                       MESSAGING_REAL_PASSWORD=password, MESSAGING_REAL_PYTHON=sys.executable,
                       MESSAGING_REAL_COMPOSE=json.dumps(stack['base'][1:]),
                       MESSAGING_REAL_ADMIN_EMAIL='messaging-admin@example.invalid',
                       MESSAGING_REAL_OPERATOR_EMAIL='messaging-operator@example.invalid',
                       MESSAGING_REAL_VIEWER_EMAIL='messaging-viewer@example.invalid')
    with tempfile.TemporaryDirectory(prefix='coldsafe-b215-web-') as folder:
        frontend = Path(folder) / 'frontend'
        frontend.mkdir()
        for name in ('src', 'public', 'e2e'):
            shutil.copytree(ROOT / 'frontend' / name, frontend / name)
        for name in ('index.html', 'package.json', 'vite.config.ts', 'tsconfig.app.json',
                     'playwright.messaging.config.ts'):
            shutil.copyfile(ROOT / 'frontend' / name, frontend / name)
        dependencies = Path(os.environ.get('COLDSAFE_FRONTEND_NODE_MODULES', str(ROOT / 'frontend/node_modules')))
        (frontend / 'node_modules').symlink_to(dependencies, target_is_directory=True)
        processes = []
        with (Path(folder) / 'servers.log').open('w+') as logs:
            try:
                # Production workers poll basic.get; register one real subscriber to measure consumers.
                consumer = subprocess.Popen([sys.executable, '-c', '''
import os
from backend.tests.infra.test_rabbitmq_integration import connect
broker = {'port': int(os.environ['RABBITMQ_PORT']),
          'passwords': {'training': os.environ['RABBITMQ_TRAINING_PASSWORD']}}
with connect(broker, 'training') as channel:
    channel.basic_consume('coldsafe.training', lambda ch, method, props, body: ch.basic_ack(method.delivery_tag))
    channel.start_consuming()
'''], cwd=ROOT, env=environment, stdout=logs, stderr=logs)
                processes.append(consumer)
                backend = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'backend.app.main:app',
                                            '--host', '127.0.0.1', '--port', api_url.rsplit(':', 1)[1]],
                                           cwd=ROOT, env=environment, stdout=logs, stderr=logs)
                processes.append(backend)
                wait_http(backend, api_url + '/health/ready')
                tokens = {}
                for role in ('admin', 'operator', 'viewer'):
                    status, body = api_request(api_url, '/api/v1/auth/login', data={
                        'email': f'messaging-{role}@example.invalid', 'password': password})
                    assert status == 200
                    tokens[role] = body['data']['token']
                assert api_request(api_url, '/api/v3/messaging')[0] == 401
                for role in ('operator', 'viewer'):
                    assert api_request(api_url, '/api/v3/messaging', token=tokens[role])[0] == 403
                snapshot = wait_metrics(api_url, tokens['admin'], lambda queues:
                    next(row for row in queues if row['name'] == 'coldsafe.writer')['messages_ready'] >= 3
                    and next(row for row in queues if row['name'] == 'coldsafe.training')['consumers'] == 1)
                # Wait for the broker's sampling interval and application's short cache to settle.
                time.sleep(11)
                status, snapshot = api_request(api_url, '/api/v3/messaging', token=tokens['admin'])
                assert status == 200
                direct = {row['name']: row for row in management(stack)}
                for row in snapshot['data']['queues']:
                    real = direct[row['name']]
                    assert {field: row[field] for field in ('messages', 'messages_ready', 'messages_unacknowledged', 'consumers')} == {
                        field: real[field] for field in ('messages', 'messages_ready', 'messages_unacknowledged', 'consumers')}
                    for output, source in (('publish_rate', 'publish_details'), ('deliver_rate', 'deliver_get_details')):
                        assert row[output] == real.get('message_stats', {}).get(source, {}).get('rate')
                assert any(row['publish_rate'] is not None for row in snapshot['data']['queues'])
                # Use real credentials + real broker, changing only the configured password for this route.
                wrong_auth_app = FastAPI()
                wrong_auth_app.include_router(create_messaging_router(auth, MessagingService(
                    '127.0.0.1', stack['management_port'], 'wrong-monitor-password')))
                auth.install_exception_handlers(wrong_auth_app)
                response = TestClient(wrong_auth_app).get('/api/v3/messaging',
                    headers={'Authorization': 'Bearer ' + tokens['admin']})
                assert response.status_code == 503 and 'wrong-monitor-password' not in response.text
                # Pausing the real container leaves the TCP endpoint open but unable to respond.
                run(stack, 'pause', 'rabbitmq')
                try:
                    time.sleep(5.1)
                    started = time.monotonic()
                    status, failure = api_request(api_url, '/api/v3/messaging', token=tokens['admin'])
                    assert status == 503 and failure['error']['code'] == 'DEPENDENCY_UNAVAILABLE'
                    assert 2.5 <= time.monotonic() - started < 8
                finally:
                    run(stack, 'unpause', 'rabbitmq')
                wait_metrics(api_url, tokens['admin'], lambda queues: len(queues) == 10)
                vite = subprocess.Popen([node, 'node_modules/vite/bin/vite.js', '--host', '127.0.0.1',
                                         '--port', web_url.rsplit(':', 1)[1], '--strictPort'],
                                        cwd=frontend, env=environment, stdout=logs, stderr=logs)
                processes.append(vite)
                wait_http(vite, web_url)
                result = subprocess.run([node, 'node_modules/@playwright/test/cli.js', 'test',
                                         '--config', 'playwright.messaging.config.ts'], cwd=frontend,
                                        env=environment, capture_output=True, text=True, timeout=240)
                assert result.returncode == 0, (result.stdout + result.stderr).replace(password, '[REDACTED]')
                print(result.stdout)
                print('Real broker: aggregate counters/rates/consumers matched; monitor privileges denied; '
                      'authenticated roles, wrong credentials, timeout and recovery passed.')
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
