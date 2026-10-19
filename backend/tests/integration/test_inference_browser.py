"""B2-25: real worker/broker/API/WebSocket/Chromium with private trained bundles.

The source and persistence receipt are boundary fixtures, not an InfluxDB test.
The existing 720-row trained fixture uses a two-second window; production feature
windows and physical accuracy are outside this browser acceptance check.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
from threading import Event, Thread
import time
from uuid import uuid4

from fastapi.middleware.cors import CORSMiddleware
import pytest
import uvicorn

from backend.app.amqp.consumer import ApiAmqpConsumer
from backend.app.amqp.inference import InferenceWorker
from backend.app.amqp.models import ModelPublisher
from backend.app.api.aiot import install_aiot
from backend.app.api.app import create_app
from backend.app.api.auth import AuthService
from backend.app.api.catalog import CatalogService
from backend.app.api.events import EventHub
from backend.app.api.models import create_models_router
from backend.app.repositories.postgres import connect
from backend.app.services.aiot_events import AiotEventService
from backend.app.services.inference import InferenceService
from backend.tests.infra.test_dashboard_integration import free_port, wait_http
from backend.tests.infra.test_rabbitmq_integration import broker, connect as amqp_connect, publish
from backend.tests.integration.test_aiot_migrations_integration import database
from backend.tests.integration.test_models_integration import registry
from backend.tests.services.test_training import package
from gateway.bridge import PostgresScope
from simulator.model import Simulator, utc

ROOT = Path(__file__).resolve().parents[3]
pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    os.environ.get('COLDSAFE_INFERENCE_INTEGRATION') != '1',
    reason='Set COLDSAFE_INFERENCE_INTEGRATION=1 with disposable PostgreSQL/RabbitMQ settings',
)]


def test_real_inference_hot_swap_without_worker_or_browser_restart(registry, broker, tmp_path, monkeypatch):
    models, config, owner, stranger, register = registry
    first, _ = register()
    second, _ = register()
    broken, directory = register()
    execute = models.execute

    def fail_third_bundle_after_request(activation_id):
        state = models.get(owner, activation_id)
        if state and state['model_id'] == broken['id']:
            (directory / 'rul/model.pkl').unlink(missing_ok=True)
        return execute(activation_id)

    # Inject storage loss after HTTP acceptance; real approval, loader and rollback still execute.
    monkeypatch.setattr(models, 'execute', fail_third_bundle_after_request)
    api_url, web_url = (f'http://127.0.0.1:{free_port()}' for _ in range(2))
    auth, catalog, hub = AuthService(config), CatalogService(config), EventHub()
    password = secrets.token_urlsafe(24)
    with connect(config) as connection:
        connection.execute('UPDATE users SET password_hash=%s', (auth._passwords.hash(password),))
    environment = catalog.create_environment(owner, 'Inferência real')
    device = catalog.create_device(owner, environment['id'], 'Ventilador real', 'inference-' + uuid4().hex[:12])
    scope = json.loads((ROOT / 'simulator/catalog.example.json').read_text())
    scope.update(environment_id=environment['id'], device_record_id=device['id'], device_id=device['mqtt_device_id'])
    pg = {key: getattr(config, 'postgres_' + name) for key, name in (
        ('host', 'host'), ('port', 'port'), ('dbname', 'db'), ('user', 'user'))}
    pg['password'] = config.postgres_password.get_secret_value()
    check_scope = PostgresScope(pg, str(owner))
    events = AiotEventService(config, scope, str(owner))
    inference = InferenceService(config, scope, owner, models)
    app = create_app(repository=None, readiness_check=lambda: True, auth=auth, catalog=catalog, events=hub)
    app.add_middleware(CORSMiddleware, allow_origins=[web_url], allow_methods=['*'],
                       allow_headers=['authorization', 'content-type'])
    install_aiot(app, events, hub, auth, catalog)
    app.include_router(create_models_router(auth, models))
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1',
        port=int(api_url.rsplit(':', 1)[1]), log_level='warning'))
    api_thread = Thread(target=server.run, daemon=True)
    stop, failures = Event(), []
    control = tmp_path / 'telemetry-control'
    control.write_text('pause')
    control_ack = tmp_path / 'telemetry-control.ack'
    control_ack.write_text('pause')
    worker = InferenceWorker(models, inference, scope, check_scope, host='127.0.0.1',
        port=broker['port'], password=broker['passwords']['inference'])
    publisher = ModelPublisher(models, host='127.0.0.1', port=broker['port'], password=broker['passwords']['api'])
    consumer = ApiAmqpConsumer(events, scope, check_scope,
        lambda event: hub.publish(event['device_id'], event), amqp_host='127.0.0.1',
        amqp_port=broker['port'], password_commands=broker['passwords']['commands'],
        password_delivery=broker['passwords']['delivery'])

    def work(participant):
        try:
            participant.run(stop)
        except BaseException as error:
            failures.append(type(error).__name__)

    def source():
        try:
            # Each Pika connection is created, used and closed by this source thread.
            with amqp_connect(broker, 'gateway') as ingress, amqp_connect(broker, 'writer') as receipts:
                simulator = Simulator(scope)
                next_sample = time.monotonic()
                while not stop.is_set():
                    mode = control.read_text()
                    if mode == 'stream':
                        now = datetime.now(timezone.utc).replace(microsecond=0)
                        event = simulator.sample(1, now)
                        event['received_at'] = utc(now)
                        publish(ingress, {'payload': event,
                            'routing_key': f"v3.telemetry.{scope['device_record_id']}"})
                        received = utc(datetime.now(timezone.utc))
                        receipt = {**event, 'event_id': str(uuid4()), 'type': 'telemetry_persisted',
                            'occurred_at': received, 'received_at': received, 'data': {
                                'equipment_id': scope['equipment_id'], 'source_event_id': event['event_id'],
                                'input_received_at': event['received_at']}}
                        publish(receipts, {'payload': receipt,
                            'routing_key': f"v3.telemetry_persisted.{scope['device_record_id']}"})
                    ingress.connection.process_data_events(time_limit=0)
                    receipts.connection.process_data_events(time_limit=0)
                    control_ack.write_text(mode)
                    next_sample += 1
                    stop.wait(max(0, next_sample - time.monotonic()))
        except BaseException as error:
            failures.append(type(error).__name__)

    node = os.environ.get('COLDSAFE_NODE_BINARY') or shutil.which('node')
    assert node, 'Node 24 is required'
    frontend = tmp_path / 'web'
    frontend.mkdir()
    for name in ('src', 'public', 'e2e'):
        shutil.copytree(ROOT / 'frontend' / name, frontend / name)
    for name in ('index.html', 'package.json', 'package-lock.json', 'vite.config.ts',
                 'tsconfig.app.json', 'playwright.inference.config.ts'):
        shutil.copyfile(ROOT / 'frontend' / name, frontend / name)
    dependencies = Path(os.environ.get('COLDSAFE_FRONTEND_NODE_MODULES', str(ROOT / 'frontend/node_modules')))
    (frontend / 'node_modules').symlink_to(dependencies, target_is_directory=True)
    browser_evidence = tmp_path / 'browser.json'
    environment = {**os.environ, 'VITE_API_BASE_URL': api_url, 'VITE_AIOT_ENABLED': 'true',
        'INFERENCE_REAL_URL': web_url, 'INFERENCE_REAL_API_URL': api_url,
        'INFERENCE_REAL_EMAIL': f'{owner}@example.invalid',
        'INFERENCE_REAL_OTHER_EMAIL': f'{stranger}@example.invalid',
        'INFERENCE_REAL_PASSWORD': password, 'INFERENCE_REAL_DEVICE': scope['device_id'],
        'INFERENCE_REAL_CONTROL': str(control), 'INFERENCE_REAL_EVIDENCE': str(browser_evidence),
        'INFERENCE_REAL_MODELS': json.dumps([str(model['id']) for model in (first, second, broken)]),
        'PATH': str(Path(node).parent) + os.pathsep + os.environ.get('PATH', '')}
    bus_threads = [Thread(target=work, args=(participant,), daemon=True)
                   for participant in (publisher, worker, consumer)]
    source_thread = Thread(target=source, daemon=True)
    vite = None
    with (tmp_path / 'servers.log').open('w+') as logs:
        try:
            api_thread.start()
            deadline = time.monotonic() + 15
            while not server.started:
                assert api_thread.is_alive() and time.monotonic() < deadline
                time.sleep(0.05)
            for thread in [*bus_threads, source_thread]:
                thread.start()
            worker_identity, process_id = bus_threads[1].ident, os.getpid()
            vite = subprocess.Popen([node, 'node_modules/vite/bin/vite.js', '--host', '127.0.0.1',
                '--port', web_url.rsplit(':', 1)[1], '--strictPort'], cwd=frontend, env=environment,
                stdout=logs, stderr=logs)
            wait_http(vite, web_url)
            browser = subprocess.run([node, 'node_modules/@playwright/test/cli.js', 'test',
                '--config', 'playwright.inference.config.ts'], cwd=frontend, env=environment,
                capture_output=True, text=True, timeout=180)
            assert browser.returncode == 0, (browser.stdout + browser.stderr).replace(password, '[REDACTED]')
            print(browser.stdout, flush=True)
            assert os.getpid() == process_id and bus_threads[1].ident == worker_identity and bus_threads[1].is_alive()
            assert models.active(owner)['model_id'] == second['id']
            with connect(config) as connection:
                states = connection.execute('SELECT prediction FROM inference_events ORDER BY received_at').fetchall()
                assert states and all(row[0]['data']['source_event_id'] == row[0]['correlation_id'] for row in states)
                versions = {row[0]['data']['model_version'] for row in states if row[0]['data']['status'] == 'available'}
                assert versions == {first['model_version'], second['model_version']}
                assert connection.execute('SELECT count(*) FROM inference_events WHERE published_at IS NULL').fetchone() == (0,)
            evidence = json.loads(browser_evidence.read_text()) | {
                'worker_pid': process_id, 'worker_thread': worker_identity, 'worker_not_restarted': True,
                'real_postgres_rabbitmq_http_websocket_chromium': True,
                'source_fixture': 'current-clock Simulator telemetry at 1 Hz, timestamps floored to seconds, AMQP gateway identity',
                'persistence_boundary_fixture': 'telemetry_persisted AMQP writer identity; InfluxDB not exercised',
                'training_fixture_rows': 720, 'training_fixture_windows_seconds': [2],
                'production_windows_unchanged': True, 'physical_accuracy_validated': False,
                'failure_injection': 'third bundle RUL file removed by test barrier immediately before real execute',
                'prediction_count': len(states), 'available_model_versions': sorted(versions),
                'prediction_reasons': sorted({row[0]['data']['reason'] for row in states if row[0]['data']['reason']}),
            }
            destination = os.environ.get('COLDSAFE_INFERENCE_EVIDENCE_DIR')
            if destination:
                output = Path(destination)
                output.mkdir(mode=0o700, parents=True, exist_ok=True)
                (output / 'integration.json').write_text(json.dumps(evidence, allow_nan=False, indent=2) + '\n')
                for screenshot in frontend.glob('test-results/**/inference-*.png'):
                    shutil.copyfile(screenshot, output / screenshot.name)
        finally:
            stop.set()
            for thread in [*bus_threads, source_thread]:
                if thread.ident is not None:
                    thread.join(timeout=20)
            server.should_exit = True
            if api_thread.ident is not None:
                api_thread.join(timeout=15)
            worker.close()
            if vite:
                vite.terminate()
                try:
                    vite.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    vite.kill()
                    vite.wait(timeout=5)
            assert not failures, f'Inference integration participant failed: {failures}'
            assert not any(thread.is_alive() for thread in [*bus_threads, source_thread, api_thread])
