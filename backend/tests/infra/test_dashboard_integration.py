"""B2-14: opt-in browser checks against the disposable sensor-to-Web stack."""
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import URLError
from urllib.request import urlopen
from uuid import uuid4

import psycopg
import pytest
import yaml

from backend.app.api.auth import AuthService
from backend.app.config.settings import RuntimeSettings
from backend.app.repositories.postgres import MIGRATIONS
from backend.tests.infra.test_writer_integration import ROOT, run, stack

pytestmark = pytest.mark.integration


def free_port():
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        return listener.getsockname()[1]


def wait_http(process, url):
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        assert process.poll() is None, 'Disposable dashboard server stopped before becoming ready'
        try:
            with urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except (URLError, TimeoutError):
            pass
        time.sleep(0.1)
    pytest.fail('Disposable dashboard server did not become ready')


def test_real_sensor_dashboard_commands_permissions_mobile_and_reconnect(stack):
    pg, values = stack['postgres'], stack['values']
    # Exercise the production 1 Hz cadence, rather than the writer fixture's 5 Hz stress input.
    compose_path = Path(stack['base'][stack['base'].index('-f') + 1])
    compose = yaml.safe_load(compose_path.read_text())
    compose['services']['simulator']['environment']['SIMULATOR_INTERVAL_SECONDS'] = '1'
    compose_path.write_text(yaml.safe_dump(compose))
    run(stack, 'up', '-d', '--no-deps', 'simulator')
    run(stack, 'stop', 'simulator')
    stack['port'] = int(run(stack, 'port', 'mosquitto', '1883').strip().rsplit(':', 1)[1])
    api_url = f'http://127.0.0.1:{free_port()}'
    web_url = f'http://127.0.0.1:{free_port()}'
    password = secrets.token_urlsafe(24)
    viewer, viewer_environment, viewer_device = uuid4(), uuid4(), uuid4()
    settings = RuntimeSettings(
        mqtt_host='127.0.0.1', mqtt_port=stack['port'], mqtt_topic='coldsafe/v1/telemetry', mqtt_qos=1,
        mqtt_client_id='b214-' + secrets.token_hex(5), mqtt_backend_username='coldsafe-backend',
        mqtt_backend_password=values['MQTT_BACKEND_PASSWORD'], auth_jwt_secret=values['AUTH_JWT_SECRET'],
        influxdb_url=stack['url'], influxdb_org=stack['org'], influxdb_bucket='telemetry_live',
        influxdb_token=values['DOCKER_INFLUXDB_INIT_ADMIN_TOKEN'], postgres_host=pg['host'],
        postgres_port=pg['port'], postgres_db=pg['dbname'], postgres_user=pg['user'],
        postgres_password=pg['password'], cors_origins=web_url, _env_file=None)
    auth = AuthService(settings)
    with psycopg.connect(**pg) as database:
        database.execute('CREATE TABLE IF NOT EXISTS schema_migrations ('
                         'version integer PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())')
        for version, _path in MIGRATIONS:
            database.execute('INSERT INTO schema_migrations(version) VALUES (%s) ON CONFLICT DO NOTHING', (version,))
        owner = database.execute('SELECT owner_user_id FROM environments WHERE id=%s',
                                 (stack['catalog']['environment_id'],)).fetchone()[0]
        before = time.time()
        server_time = database.execute('SELECT extract(epoch FROM clock_timestamp())').fetchone()[0]
        after = time.time()
        print('Disposable clock offset bounds (seconds):', round(float(server_time) - after, 4),
              round(float(server_time) - before, 4))
        database.execute("UPDATE users SET password_hash=%s,role='operator' WHERE id=%s",
                         (auth._passwords.hash(password), owner))
        database.execute('INSERT INTO environment_rules(environment_id) VALUES (%s) ON CONFLICT DO NOTHING',
                         (stack['catalog']['environment_id'],))
        database.execute("INSERT INTO users(id,email,password_hash,role) VALUES (%s,%s,%s,'viewer')",
                         (viewer, 'dashboard-viewer@example.invalid', auth._passwords.hash(password)))
        database.execute('INSERT INTO environments(id,owner_user_id,name) VALUES (%s,%s,%s)',
                         (viewer_environment, viewer, 'Viewer environment'))
        database.execute('INSERT INTO environment_rules(environment_id) VALUES (%s)', (viewer_environment,))
        database.execute('INSERT INTO devices(id,environment_id,mqtt_device_id,name) VALUES (%s,%s,%s,%s)',
                         (viewer_device, viewer_environment, 'dashboard-viewer-device', 'Viewer sensor'))
    node = os.environ.get('COLDSAFE_NODE_BINARY') or shutil.which('node')
    assert node, 'Node.js 24.20.0 is required to run the real dashboard suite'
    frontend_source = ROOT / 'frontend'
    environment = {**os.environ, **values}
    for key, value in settings.model_dump().items():
        if value is not None:
            environment[key.upper()] = value.get_secret_value() if hasattr(value, 'get_secret_value') else str(value)
    with tempfile.TemporaryDirectory(prefix='coldsafe-b214-web-') as folder:
        frontend = Path(folder) / 'frontend'
        frontend.mkdir()
        for name in ('src', 'public', 'e2e'):
            shutil.copytree(frontend_source / name, frontend / name)
        for name in ('index.html', 'package.json', 'vite.config.ts', 'tsconfig.app.json',
                     'playwright.aiot.config.ts'):
            shutil.copyfile(frontend_source / name, frontend / name)
        dependencies = Path(os.environ.get('COLDSAFE_FRONTEND_NODE_MODULES', str(frontend_source / 'node_modules')))
        (frontend / 'node_modules').symlink_to(dependencies, target_is_directory=True)
        catalog_path = Path(folder) / 'catalog.json'
        catalog_path.write_text(json.dumps(stack['catalog']))
        environment.update(
            AIOT_ENABLED='true', AIOT_CATALOG_PATH=str(catalog_path), AIOT_OWNER_USER_ID=str(owner),
            RABBITMQ_HOST='127.0.0.1', RABBITMQ_PORT=str(stack['broker']['port']),
            VITE_AIOT_ENABLED='true', VITE_API_BASE_URL=api_url,
            DASHBOARD_REAL_URL=web_url, DASHBOARD_REAL_API_URL=api_url,
            DASHBOARD_REAL_PASSWORD=password, DASHBOARD_REAL_COMPOSE=json.dumps(stack['base'][1:]),
            DASHBOARD_REAL_PYTHON=sys.executable, DASHBOARD_REAL_OWNER=str(owner),
            DASHBOARD_REAL_ENVIRONMENT=stack['catalog']['environment_id'],
            DASHBOARD_REAL_DEVICE=stack['catalog']['device_id'],
        )
        processes = []
        with (Path(folder) / 'servers.log').open('w+') as logs:
            try:
                backend = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'backend.app.main:app',
                                            '--host', '127.0.0.1', '--port', api_url.rsplit(':', 1)[1]],
                                           cwd=ROOT, env=environment, stdout=logs, stderr=logs)
                processes.append(backend)
                wait_http(backend, api_url + '/health/ready')
                vite = subprocess.Popen([node, 'node_modules/vite/bin/vite.js', '--host', '127.0.0.1',
                                         '--port', web_url.rsplit(':', 1)[1], '--strictPort'],
                                        cwd=frontend, env=environment, stdout=logs, stderr=logs)
                processes.append(vite)
                wait_http(vite, web_url)
                result = subprocess.run([node, 'node_modules/@playwright/test/cli.js', 'test',
                                         '--config', 'playwright.aiot.config.ts'], cwd=frontend,
                                        env=environment, capture_output=True, text=True, timeout=240)
                output = (result.stdout + result.stderr).replace(password, '[REDACTED]')
                assert result.returncode == 0, output
                print(output)
            except BaseException:
                logs.flush()
                logs.seek(0)
                output = ''.join(logs.readlines()[-40:])
                for key, value in {**values, 'DASHBOARD_REAL_PASSWORD': password}.items():
                    if value and any(part in key for part in ('PASSWORD', 'TOKEN', 'SECRET')):
                        output = output.replace(value, '[REDACTED]')
                print(output)
                raise
            finally:
                try:
                    run(stack, 'stop', 'simulator')
                finally:
                    for process in reversed(processes):
                        process.terminate()
                        try:
                            process.wait(timeout=15)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=5)
