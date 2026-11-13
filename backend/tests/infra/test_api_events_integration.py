"""B2-13 opt-in checks against disposable real brokers, databases and simulator."""
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from threading import Event, Thread
import time
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
import psycopg
import pytest
from starlette.websockets import WebSocketDisconnect

from backend.app.amqp.consumer import ApiAmqpConsumer
from backend.app.api.aiot import install_aiot
from backend.app.api.app import create_app
from backend.app.api.auth import AuthService
from backend.app.api.catalog import CatalogService, ThresholdInput
from backend.app.api.events import EventHub
from backend.app.config.settings import RuntimeSettings
from backend.app.repositories.postgres import MIGRATIONS
from backend.app.services.aiot_events import AiotEventService
from backend.tests.infra.test_writer_integration import run, send, stack, wait_point
from gateway.bridge import PostgresScope
from simulator.model import utc

pytestmark = pytest.mark.integration


def wait_until(check, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(0.05)
    pytest.fail('Real API pipeline did not reach the expected state')


def receive_matching(websocket, predicate, timeout=15):
    async def receive():
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            message = await asyncio.wait_for(
                websocket._send_rx.receive(), deadline - asyncio.get_running_loop().time())
            websocket._raise_on_close(message)
            event = json.loads(message['text'])
            if predicate(event):
                return event

    return websocket.portal.call(receive)


@pytest.fixture(scope='module')
def api(stack):
    pg = stack['postgres']
    settings = RuntimeSettings(
        mqtt_host='unused', mqtt_port=1883, mqtt_topic='unused', mqtt_qos=1,
        mqtt_client_id='unused', mqtt_backend_username='unused', mqtt_backend_password='unused',
        auth_jwt_secret=stack['values']['AUTH_JWT_SECRET'],
        influxdb_url=stack['url'], influxdb_org=stack['org'],
        influxdb_bucket='telemetry_live', influxdb_token=stack['values']['DOCKER_INFLUXDB_INIT_ADMIN_TOKEN'],
        postgres_host=pg['host'], postgres_port=pg['port'], postgres_db=pg['dbname'],
        postgres_user=pg['user'], postgres_password=pg['password'], _env_file=None)
    auth, catalog, hub = AuthService(settings), CatalogService(settings), EventHub()
    with psycopg.connect(**pg) as database:
        # The writer fixture applies migration files directly; auth also reads their ledger.
        database.execute('CREATE TABLE IF NOT EXISTS schema_migrations ('
                         'version integer PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())')
        for version, _path in MIGRATIONS:
            database.execute('INSERT INTO schema_migrations(version) VALUES (%s) ON CONFLICT DO NOTHING',
                             (version,))
        owner = database.execute('SELECT owner_user_id FROM environments WHERE id=%s',
                                 (stack['catalog']['environment_id'],)).fetchone()[0]
        database.execute('UPDATE users SET password_hash=%s, role=%s WHERE id=%s',
                         (auth._passwords.hash('correct-horse'), 'operator', owner))
        database.execute('INSERT INTO environment_rules(environment_id) VALUES (%s) ON CONFLICT DO NOTHING',
                         (stack['catalog']['environment_id'],))
    owner_token, _ = auth.login('writer-test@example.invalid', 'correct-horse')
    stranger = auth.register('api-stranger@example.invalid', 'correct-horse')
    stranger_token, _ = auth.login('api-stranger@example.invalid', 'correct-horse')
    stranger_environment = catalog.create_environment(stranger, 'Other account')
    catalog.create_device(stranger, UUID(stranger_environment['id']), 'Other device', 'other-account-device')
    service = AiotEventService(settings, stack['catalog'], str(owner))
    # The legacy repository is unused: every request in this module targets the v3 service.
    app = create_app(repository=None, readiness_check=lambda: True, auth=auth, catalog=catalog, events=EventHub())
    install_aiot(app, service, hub, auth, catalog)
    worker = ApiAmqpConsumer(
        service, stack['catalog'], PostgresScope(pg, str(owner)),
        lambda event: hub.publish(event['device_id'], event),
        amqp_host='127.0.0.1', amqp_port=stack['broker']['port'],
        password_commands=stack['values']['RABBITMQ_COMMANDS_PASSWORD'],
        password_delivery=stack['values']['RABBITMQ_DELIVERY_PASSWORD'])
    shutdown, errors = Event(), []

    def consume():
        try:
            worker.run(shutdown)
        except Exception as error:
            errors.append(error)

    thread = Thread(target=consume, daemon=True)
    thread.start()
    wait_until(lambda: worker.is_connected)
    try:
        with TestClient(app) as client:
            yield dict(stack=stack, settings=settings, owner=owner, stranger=stranger, catalog=catalog,
                       service=service, client=client, hub=hub, worker=worker,
                       headers={'Authorization': 'Bearer ' + owner_token},
                       stranger_headers={'Authorization': 'Bearer ' + stranger_token})
    finally:
        shutdown.set()
        thread.join(timeout=15)
        assert not thread.is_alive(), 'API AMQP consumer did not stop'
        assert not errors, f'API AMQP consumer failed: {type(errors[0]).__name__ if errors else ""}'


def summary(api, headers=None, device_id=None):
    response = api['client'].get('/api/v3/monitoring/summary',
                                params={'device_id': device_id or api['stack']['catalog']['device_id']},
                                headers=headers or api['headers'])
    assert response.status_code == 200, response.text
    return response.json()['data']


def new_telemetry(stack, temperature=6.0):
    event = deepcopy(stack['event'])
    event['event_id'] = event['correlation_id'] = str(uuid4())
    event['received_at'] = event['occurred_at'] = utc(datetime.now(timezone.utc))
    event['data']['measurements']['ambient_temperature']['value'] = temperature
    return event


def ticket(api, headers, device):
    response = api['client'].post('/api/v1/auth/ws-ticket', headers=headers, json={'device_id': device})
    assert response.status_code == 200, response.text
    return response.json()['data']['ticket']


def test_real_writer_pending_persisted_websocket_isolation_and_rest_reconnect(api):
    state, client = api['stack'], api['client']
    device = state['catalog']['device_id']
    event = new_telemetry(state)
    run(state, 'stop', 'writer')
    try:
        with client.websocket_connect('/api/v3/events?device_id=' + device) as owner_ws, \
                client.websocket_connect('/api/v3/events?device_id=other-account-device') as stranger_ws:
            owner_ws.send_json({'ticket': ticket(api, api['headers'], device)})
            stranger_ws.send_json({'ticket': ticket(api, api['stranger_headers'], 'other-account-device')})
            wait_until(lambda: len(api['hub']._subscribers) == 2)
            send(state, event)
            wait_until(lambda: summary(api)['telemetry'] is not None
                       and summary(api)['telemetry']['event_id'] == event['event_id'])
            assert summary(api)['persistence'] == 'pending'
            with pytest.raises(TimeoutError):
                receive_matching(owner_ws, lambda message: message['type'] == 'telemetry'
                                 and message['event_id'] == event['event_id'], timeout=0.3)
            run(state, 'start', 'writer')
            wait_point(state, event)
            received = receive_matching(owner_ws, lambda message: message['type'] == 'telemetry'
                                        and message['event_id'] == event['event_id'])
            assert received == event
            wait_until(lambda: summary(api)['persistence'] == 'persisted')
            with pytest.raises(TimeoutError):
                receive_matching(stranger_ws, lambda _message: True, timeout=0.3)
    finally:
        run(state, 'start', 'writer')
    # A new HTTP request recovers state after closing both live sockets.
    assert summary(api)['telemetry'] == event
    response = client.get('/api/v3/readings', params={'device_id': device, 'limit': 10}, headers=api['headers'])
    assert response.status_code == 200
    assert any(row['telemetry']['event_id'] == event['event_id']
               and row['persistence'] == 'persisted' for row in response.json()['data'])
    assert client.get('/api/v3/monitoring/summary', params={'device_id': device},
                      headers=api['stranger_headers']).status_code == 404
    assert client.post('/api/v1/auth/ws-ticket', json={'device_id': device},
                       headers=api['stranger_headers']).status_code == 404
    # A valid ticket for account B cannot be used to open account A's stream.
    with client.websocket_connect('/api/v3/events?device_id=' + device) as websocket:
        websocket.send_json({'ticket': ticket(api, api['stranger_headers'], 'other-account-device')})
        with pytest.raises(WebSocketDisconnect):
            receive_matching(websocket, lambda _message: True)


def test_real_amqp_buzzer_rule_and_manual_led_reach_simulator_and_confirm(api):
    state, client = api['stack'], api['client']
    environment = UUID(state['catalog']['environment_id'])
    api['catalog'].update_rules(api['owner'], environment,
                                ThresholdInput(min_c=2, max_c=4, attention_margin_c=0.5))
    started = datetime.now(timezone.utc)
    run(state, 'start', 'simulator')
    try:
        def confirmed_buzzer():
            with psycopg.connect(**state['postgres']) as database:
                return database.execute(
                    "SELECT command_id FROM aiot_commands WHERE actuator='buzzer' AND desired_state "
                    "AND status='confirmed' AND accepted_at>=%s", (started,)).fetchone()

        assert wait_until(confirmed_buzzer)
        response = client.post('/api/v3/devices/' + state['catalog']['device_id'] + '/led/commands',
                               headers=api['headers'], json={'desired_state': True})
        assert response.status_code in (200, 202), response.text
        identifier = response.json()['data']['data']['command_id']

        def confirmed_led():
            with psycopg.connect(**state['postgres']) as database:
                return database.execute("SELECT status FROM aiot_commands WHERE command_id=%s", (identifier,)).fetchone() == ('confirmed',)

        assert wait_until(confirmed_led)
        with psycopg.connect(**state['postgres']) as database:
            assert database.execute("SELECT count(*) FROM aiot_alerts WHERE opened_at>=%s AND closed_at IS NULL",
                                    (started,)).fetchone()[0] == 1
            assert database.execute("SELECT count(*) FROM aiot_commands WHERE actuator='buzzer' "
                                    "AND desired_state AND accepted_at>=%s", (started,)).fetchone()[0] == 1
    finally:
        run(state, 'stop', 'simulator')
        api['catalog'].update_rules(api['owner'], environment,
                                    ThresholdInput(min_c=2, max_c=8, attention_margin_c=0.5))


@pytest.fixture
def isolated_core(api):
    catalog = deepcopy(api['stack']['catalog'])
    created = api['catalog'].create_device(api['owner'], UUID(catalog['environment_id']),
                                           'Core ordering test', 'core-' + uuid4().hex[:12])
    catalog.update(device_record_id=created['id'], device_id=created['mqtt_device_id'])
    service = AiotEventService(api['settings'], catalog, str(api['owner']))
    clock = [datetime.now(timezone.utc)]
    service._now = lambda: clock[0]
    return service, clock, catalog


def source_event(api, catalog, now):
    event = new_telemetry(api['stack'])
    event.update({key: catalog[key] for key in ('device_id', 'device_record_id', 'environment_id')})
    event['occurred_at'] = event['received_at'] = utc(now)
    return event


def related_event(source, kind, now):
    data = {'equipment_id': source['data']['equipment']['equipment_id'],
            'source_event_id': source['event_id'], 'input_received_at': source['received_at']}
    if kind == 'prediction':
        data.update(features_version='fan-features-1', model_id=None, model_version=None,
                    status='unavailable', health_score=None, rul_hours=None, reason='no_model')
    return {**{key: source[key] for key in ('schema_version', 'device_id', 'device_record_id', 'environment_id')},
            'event_id': str(uuid4()), 'type': kind, 'occurred_at': utc(now), 'received_at': utc(now),
            'correlation_id': source['event_id'], 'data': data}


def test_real_postgres_receipt_prediction_order_redelivery_and_restart(api, isolated_core):
    service, clock, catalog = isolated_core
    device, owner = catalog['device_id'], api['owner']
    assert service.snapshot(owner, device)['freshness']['state'] == 'no_data'
    assert service.history(owner, device, limit=10) == []
    source = source_event(api, catalog, clock[0])
    receipt = related_event(source, 'telemetry_persisted', clock[0])
    prediction = related_event(source, 'prediction', clock[0])
    service.process(receipt)
    service.process(prediction)
    assert service.snapshot(owner, device)['telemetry'] is None
    assert service.persisted_telemetry(source['event_id']) is None
    service.process(source)
    current = service.snapshot(owner, device)
    assert current['telemetry'] == source
    assert current['prediction'] == prediction
    assert current['persistence'] == 'persisted'
    outputs = service.pending_outputs()
    assert outputs
    restarted = AiotEventService(api['settings'], catalog, str(owner))
    restarted._now = lambda: clock[0]
    assert restarted.pending_outputs() == outputs
    restarted.process(source)
    restarted.process(receipt)
    assert restarted.pending_outputs() == outputs
    # A writer restart may emit a second valid receipt with a new identity.
    restarted.process(related_event(source, 'telemetry_persisted', clock[0]))
    assert restarted.persisted_telemetry(source['event_id']) == source
    assert len(restarted.history(owner, device, limit=10)) == 1
    for event in outputs:
        restarted.mark_published(event['event_id'])
    assert restarted.pending_outputs() == []
    clock[0] += timedelta(seconds=1)
    newer = source_event(api, catalog, clock[0])
    restarted.process(newer)
    clock[0] += timedelta(seconds=1)
    late_prediction = related_event(source, 'prediction', clock[0])
    restarted.process(late_prediction)
    assert restarted.snapshot(owner, device)['telemetry'] == newer
    assert restarted.snapshot(owner, device)['prediction'] is None
    history = restarted.history(owner, device, limit=10)
    assert history[1]['prediction'] == late_prediction
    assert history[1]['persistence'] == 'persisted'
    assert history[0]['persistence'] == 'pending'
    clock[0] += timedelta(seconds=31)
    restarted.expire_pending()
    assert restarted.snapshot(owner, device)['freshness']['state'] == 'stale'
    assert restarted.snapshot(api['stranger'], device) is None


def test_real_postgres_ack_deadline_and_timeout_are_durable_and_audited(api, isolated_core):
    service, clock, catalog = isolated_core
    owner, device = api['owner'], catalog['device_id']

    def ack(status, received):
        command = status['data']
        return {**{key: status[key] for key in ('schema_version', 'device_id', 'device_record_id', 'environment_id', 'correlation_id')},
                'event_id': str(uuid4()), 'type': 'ack', 'occurred_at': utc(received),
                'received_at': utc(received), 'data': {
                    **{key: command[key] for key in ('command_id', 'actuator_id', 'actuator')},
                    'result': 'applied', 'applied_state': True, 'reason': None}}

    status = service.request_led(owner, device, True)
    clock[0] += timedelta(seconds=30)
    service.process(ack(status, clock[0]))
    assert service.snapshot(owner, device)['commands']['led']['data']['status'] == 'confirmed'
    status = service.request_led(owner, device, True)
    accepted = clock[0]
    clock[0] += timedelta(seconds=31)
    service.expire_pending()
    assert service.snapshot(owner, device)['commands']['led']['data']['status'] == 'unconfirmed'
    restarted = AiotEventService(api['settings'], catalog, str(owner))
    restarted._now = lambda: clock[0]
    # Even an ACK received inside the window cannot undo a persisted timeout.
    late = ack(status, accepted + timedelta(seconds=29))
    restarted.process(late)
    assert restarted.snapshot(owner, device)['commands']['led']['data']['status'] == 'unconfirmed'
    with psycopg.connect(**api['stack']['postgres']) as database:
        audit = database.execute("SELECT details FROM audit_events WHERE device_id=%s AND event_type='aiot_ack_late'",
                                 (catalog['device_record_id'],)).fetchall()
        assert any(row[0]['event_id'] == late['event_id'] for row in audit)
