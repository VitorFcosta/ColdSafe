"""B2-26 acceptance: real PostgreSQL, AMQP delivery, HTTP and Chromium.

Telemetry/receipts/predictions are contract-valid boundary fixtures. This checks
predictive alert behavior, not model training, physical accuracy or InfluxDB.
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
from backend.app.api.aiot import install_aiot
from backend.app.api.app import create_app
from backend.app.api.auth import AuthService
from backend.app.api.catalog import CatalogService
from backend.app.api.events import EventHub
from backend.app.repositories.postgres import connect
from backend.app.services.aiot_events import AiotEventService
from backend.tests.infra.test_dashboard_integration import free_port, wait_http
from backend.tests.infra.test_rabbitmq_integration import broker, connect as amqp_connect, publish
from backend.tests.integration.test_aiot_migrations_integration import database, demo
from gateway.bridge import PostgresScope
from simulator.model import Simulator, utc

ROOT = Path(__file__).resolve().parents[3]
pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    os.environ.get('COLDSAFE_INSIGHTS_INTEGRATION') != '1',
    reason='Set COLDSAFE_INSIGHTS_INTEGRATION=1 with disposable PostgreSQL/RabbitMQ settings',
)]


def test_predictive_hysteresis_persistence_and_browser(demo, broker, tmp_path):
    config, (_viewer, owner, stranger) = demo
    auth, catalog, hub = AuthService(config), CatalogService(config), EventHub()
    password = secrets.token_urlsafe(24)
    with connect(config) as connection:
        connection.execute('UPDATE users SET password_hash=%s WHERE id IN (%s,%s)',
                           (auth._passwords.hash(password), owner.owner, stranger.owner))
    device = catalog.create_device(owner.owner, owner.environment, 'Ventilador Insights',
                                   'insights-' + uuid4().hex[:12])
    scope = json.loads((ROOT / 'simulator/catalog.example.json').read_text())
    scope.update(environment_id=str(owner.environment), device_record_id=str(device['id']),
                 device_id=device['mqtt_device_id'])
    pg = {key: getattr(config, 'postgres_' + name) for key, name in (
        ('host', 'host'), ('port', 'port'), ('dbname', 'db'), ('user', 'user'))}
    pg['password'] = config.postgres_password.get_secret_value()
    events = AiotEventService(config, scope, str(owner.owner))
    api_url, web_url = (f'http://127.0.0.1:{free_port()}' for _ in range(2))
    app = create_app(repository=None, readiness_check=lambda: True, auth=auth, catalog=catalog, events=hub)
    app.add_middleware(CORSMiddleware, allow_origins=[web_url], allow_methods=['*'],
                       allow_headers=['authorization', 'content-type'])
    install_aiot(app, events, hub, auth, catalog)
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1',
        port=int(api_url.rsplit(':', 1)[1]), log_level='warning'))
    api_thread = Thread(target=server.run, daemon=True)
    stop, failures = Event(), []
    consumer = ApiAmqpConsumer(events, scope, PostgresScope(pg, str(owner.owner)),
        lambda event: hub.publish(event['device_id'], event), amqp_host='127.0.0.1',
        amqp_port=broker['port'], password_commands=broker['passwords']['commands'],
        password_delivery=broker['passwords']['delivery'])
    control = tmp_path / 'prediction-control'
    acknowledgement = tmp_path / 'prediction-control.ack'
    control.write_text('{"id":0}')
    acknowledgement.write_text('{"id":0}')

    def work():
        try:
            consumer.run(stop)
        except BaseException as error:
            failures.append(repr(error))

    def source():
        try:
            # Pika connections stay in their owning thread, including shutdown.
            with (amqp_connect(broker, 'gateway') as ingress,
                  amqp_connect(broker, 'writer') as receipts,
                  amqp_connect(broker, 'inference') as predictions):
                simulator, previous_id, prediction = Simulator(scope), 0, None
                while not stop.wait(0.05):
                    command = json.loads(control.read_text())
                    if command['id'] == previous_id:
                        for channel in (ingress, receipts, predictions):
                            channel.connection.process_data_events(time_limit=0)
                        continue
                    previous_id = command['id']
                    if not command['duplicate']:
                        now = datetime.now(timezone.utc)
                        telemetry = simulator.sample(1, now)
                        telemetry['received_at'] = utc(now)
                        telemetry['data']['measurements']['ambient_temperature']['value'] = 5
                        publish(ingress, {'payload': telemetry,
                            'routing_key': f"v3.telemetry.{scope['device_record_id']}"})
                        received = utc(datetime.now(timezone.utc))
                        receipt = {**telemetry, 'event_id': str(uuid4()), 'type': 'telemetry_persisted',
                            'occurred_at': received, 'received_at': received, 'data': {
                                'equipment_id': scope['equipment_id'], 'source_event_id': telemetry['event_id'],
                                'input_received_at': telemetry['received_at']}}
                        publish(receipts, {'payload': receipt,
                            'routing_key': f"v3.telemetry_persisted.{scope['device_record_id']}"})
                        usable = command['health'] is not None
                        received = utc(datetime.now(timezone.utc))
                        prediction = {**telemetry, 'event_id': str(uuid4()), 'type': 'prediction',
                            'occurred_at': received, 'received_at': received, 'data': {
                                'equipment_id': scope['equipment_id'], 'source_event_id': telemetry['event_id'],
                                'input_received_at': telemetry['received_at'], 'features_version': 'fan-v1',
                                'model_id': str(owner.model), 'model_version': 'demo-v1',
                                'status': 'available' if usable else 'unavailable',
                                'health_score': command['health'], 'rul_hours': command['rul'],
                                'reason': None if usable else 'insufficient_history'}}
                    assert prediction is not None
                    for _ in range(3 if command['duplicate'] else 1):
                        publish(predictions, {'payload': prediction,
                            'routing_key': f"v3.prediction.{scope['device_record_id']}"})
                    deadline = time.monotonic() + 10
                    while not stop.is_set():
                        with connect(config) as connection:
                            linked = connection.execute('SELECT linked FROM aiot_events WHERE event_id=%s',
                                                        (prediction['event_id'],)).fetchone()
                            persisted = connection.execute("SELECT 1 FROM aiot_events WHERE kind='telemetry_persisted' "
                                'AND source_event_id=%s AND linked', (prediction['data']['source_event_id'],)).fetchone()
                        if linked == (True,) and persisted:
                            break
                        assert time.monotonic() < deadline, 'Prediction fixture was not linked by real AMQP consumer'
                        stop.wait(0.05)
                    restarted = AiotEventService(config, scope, str(owner.owner)).insights(
                        owner.owner, scope['device_id'])
                    next_ack = acknowledgement.with_name(acknowledgement.name + '.next')
                    next_ack.write_text(json.dumps({'id': command['id'],
                        'prediction_event_id': prediction['event_id'],
                        'source_event_id': prediction['data']['source_event_id'],
                        'recreated_active_alert_ids': [alert['alert_id'] for alert in restarted['active_alerts']]}))
                    next_ack.replace(acknowledgement)
        except BaseException as error:
            failures.append(repr(error))

    node = os.environ.get('COLDSAFE_NODE_BINARY') or shutil.which('node')
    assert node, 'Node 24 is required'
    frontend = tmp_path / 'web'
    frontend.mkdir()
    for name in ('src', 'public', 'e2e'):
        shutil.copytree(ROOT / 'frontend' / name, frontend / name)
    for name in ('index.html', 'package.json', 'package-lock.json', 'vite.config.ts',
                 'tsconfig.app.json', 'playwright.insights.config.ts'):
        shutil.copyfile(ROOT / 'frontend' / name, frontend / name)
    dependencies = Path(os.environ.get('COLDSAFE_FRONTEND_NODE_MODULES', str(ROOT / 'frontend/node_modules')))
    (frontend / 'node_modules').symlink_to(dependencies, target_is_directory=True)
    browser_evidence = tmp_path / 'browser.json'
    environment = {**os.environ, 'VITE_API_BASE_URL': api_url, 'VITE_AIOT_ENABLED': 'true',
        'INSIGHTS_REAL_URL': web_url, 'INSIGHTS_REAL_API_URL': api_url,
        'INSIGHTS_REAL_EMAIL': 'operator@example.invalid', 'INSIGHTS_REAL_OTHER_EMAIL': 'admin@example.invalid',
        'INSIGHTS_REAL_PASSWORD': password, 'INSIGHTS_REAL_DEVICE': scope['device_id'],
        'INSIGHTS_REAL_CONTROL': str(control), 'INSIGHTS_REAL_EVIDENCE': str(browser_evidence),
        'PATH': str(Path(node).parent) + os.pathsep + os.environ.get('PATH', '')}
    bus_thread, source_thread = Thread(target=work, daemon=True), Thread(target=source, daemon=True)
    vite = None
    with (tmp_path / 'servers.log').open('w+') as logs:
        try:
            api_thread.start()
            deadline = time.monotonic() + 15
            while not server.started:
                assert api_thread.is_alive() and time.monotonic() < deadline
                time.sleep(0.05)
            bus_thread.start()
            source_thread.start()
            vite = subprocess.Popen([node, 'node_modules/vite/bin/vite.js', '--host', '127.0.0.1',
                '--port', web_url.rsplit(':', 1)[1], '--strictPort'], cwd=frontend, env=environment,
                stdout=logs, stderr=logs)
            wait_http(vite, web_url)
            browser = subprocess.run([node, 'node_modules/@playwright/test/cli.js', 'test',
                '--config', 'playwright.insights.config.ts'], cwd=frontend, env=environment,
                capture_output=True, text=True, timeout=180)
            assert browser.returncode == 0, (browser.stdout + browser.stderr).replace(password, '[REDACTED]')
            print(browser.stdout, flush=True)
            with connect(config) as connection:
                transitions = connection.execute("SELECT event_type,count(*) FROM audit_events "
                    "WHERE event_type IN ('predictive_alert_opened','predictive_alert_closed') GROUP BY event_type").fetchall()
                assert dict(transitions) == {'predictive_alert_opened': 1, 'predictive_alert_closed': 1}
                assert connection.execute('SELECT count(*) FROM predictive_alerts WHERE closed_at IS NULL').fetchone() == (0,)
                assert connection.execute('SELECT count(*) FROM predictive_alerts WHERE closed_at IS NOT NULL').fetchone() == (1,)
                assert connection.execute('SELECT count(*) FROM aiot_commands WHERE actuator=%s', ('buzzer',)).fetchone() == (0,)
            restarted = AiotEventService(config, scope, str(owner.owner)).insights(owner.owner, scope['device_id'])
            evidence = json.loads(browser_evidence.read_text())
            assert restarted['rules'] == evidence['rules']
            assert restarted['active_alerts'] == []
            assert restarted['prediction']['event_id'] == evidence['recovered']['prediction']['event_id']
            evidence.update(real_postgres_rabbitmq_http_chromium=True, service_recreated_preserves_state=True,
                audit_open_count=1, audit_close_count=1, predictive_alert_does_not_request_thermal_buzzer=True,
                prediction_source='contract-valid boundary fixture; model inference not executed',
                influxdb_exercised=False, physical_accuracy_validated=False)
            destination = os.environ.get('COLDSAFE_INSIGHTS_EVIDENCE_DIR')
            if destination:
                output = Path(destination)
                output.mkdir(mode=0o700, parents=True, exist_ok=True)
                (output / 'integration.json').write_text(json.dumps(evidence, allow_nan=False, indent=2) + '\n')
                for screenshot in frontend.glob('test-results/**/insights-*.png'):
                    shutil.copyfile(screenshot, output / screenshot.name)
        finally:
            stop.set()
            consumer.close()
            for thread in (bus_thread, source_thread):
                if thread.ident is not None:
                    thread.join(timeout=20)
            server.should_exit = True
            if api_thread.ident is not None:
                api_thread.join(timeout=15)
            if vite:
                vite.terminate()
                try:
                    vite.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    vite.kill()
                    vite.wait(timeout=5)
            assert not failures, f'Insights integration participant failed: {failures}'
            assert not any(thread.is_alive() for thread in (bus_thread, source_thread, api_thread))
