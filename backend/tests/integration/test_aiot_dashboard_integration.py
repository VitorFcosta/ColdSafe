"""Use the opt-in PostgreSQL test connection without starting another stack."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from uuid import uuid4

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
import pytest

from backend.app.repositories.postgres import connect, initialize_schema
from backend.app.services.aiot_events import AiotEventService
from backend.tests.integration.test_postgres_schema_integration import settings
from simulator.model import utc


pytestmark = pytest.mark.integration


@pytest.fixture
def dashboard_database():
    config = settings()
    initialize_schema(config)
    connection = connect(config)
    try:
        owner = connection.execute(
            "INSERT INTO users(email,password_hash,role) VALUES (%s,'test-only','operator') RETURNING id",
            (uuid4().hex + '@example.invalid',),
        ).fetchone()[0]
        environment = connection.execute(
            'INSERT INTO environments(owner_user_id,name) VALUES (%s,%s) RETURNING id',
            (owner, 'Private dashboard room'),
        ).fetchone()[0]
        connection.execute(
            'INSERT INTO environment_rules(environment_id,temp_min_c,temp_max_c,recovery_margin_c) '
            'VALUES (%s,1,7,0.7)', (environment,),
        )
        mqtt_id = 'dashboard-' + uuid4().hex
        device = connection.execute(
            'INSERT INTO devices(environment_id,name,mqtt_device_id) VALUES (%s,%s,%s) RETURNING id',
            (environment, 'Dashboard fan', mqtt_id),
        ).fetchone()[0]
        catalog = json.loads(Path('contracts/examples/aiot.context.json').read_text())
        catalog.update(device_record_id=str(device), device_id=mqtt_id, environment_id=str(environment))
        service = AiotEventService(config, catalog, str(owner))
        clock = [datetime.now(UTC)]
        service._now = lambda: clock[0]

        @contextmanager
        def cursor():
            with connection.cursor(row_factory=dict_row) as current:
                yield current

        service._cursor = cursor
        yield service, connection, owner, clock
    finally:
        connection.rollback()
        connection.close()


def test_snapshot_metadata_and_history_half_open_range_are_private_in_postgres(dashboard_database):
    service, connection, owner, clock = dashboard_database
    device, stranger = service.catalog['device_id'], uuid4()
    snapshot = service.snapshot(owner, device)
    assert snapshot['freshness']['state'] == 'no_data'
    assert snapshot['environment'] == {'id': service.catalog['environment_id'], 'name': 'Private dashboard room'}
    assert snapshot['device'] == {'id': device}
    assert snapshot['thresholds'] == {'min_c': 1.0, 'max_c': 7.0, 'attention_margin_c': 0.7}
    start, end = clock[0] - timedelta(hours=1), clock[0]
    examples = json.loads(Path('contracts/examples/aiot.valid.json').read_text())
    source = next(row['payload'] for row in examples if row['name'] == 'telemetry_received')
    events = []
    for received in (start - timedelta(seconds=1), start, end):
        event = deepcopy(source)
        event.update({key: service.catalog[key] for key in ('device_id', 'device_record_id', 'environment_id')})
        event['event_id'] = event['correlation_id'] = str(uuid4())
        event['received_at'] = event['occurred_at'] = utc(received)
        event['data']['measurements']['ambient_temperature']['value'] = 5.0
        service.process(event)
        events.append(event)
    assert [row['telemetry']['event_id'] for row in service.history(owner, device, 10, start=start, end=end)] == [events[1]['event_id']]
    assert [row['telemetry']['event_id'] for row in service.history(owner, device, 1, start=start, end=end)] == [events[1]['event_id']]
    assert len(service.history(owner, device, 10)) == 3
    assert service.history(stranger, device, 10, start=start, end=end) is None
    assert service.snapshot(stranger, device) is None
    connection.execute('UPDATE environment_rules SET temp_max_c=6 WHERE environment_id=%s',
                       (service.catalog['environment_id'],))
    assert service.snapshot(owner, device)['thresholds']['max_c'] == 6


def test_alert_overlap_and_command_timeout_recovery_are_private_and_durable(dashboard_database):
    service, connection, owner, clock = dashboard_database
    device, record = service.catalog['device_id'], service.catalog['device_record_id']
    start, end = clock[0], clock[0] + timedelta(hours=1)
    expected = set()
    for opened, closed, included in (
        (start - timedelta(hours=1), start, False),
        (end, end + timedelta(seconds=1), False),
        (start - timedelta(hours=1), None, True),
        (start, end, True),
    ):
        identifier = uuid4()
        connection.execute(
            'INSERT INTO aiot_alerts(alert_id,device_id,kind,opened_at,closed_at,envelope) '
            "VALUES (%s,%s,'temperature_high',%s,%s,%s)",
            (identifier, record, opened, closed, Jsonb({})),
        )
        if included:
            expected.add(str(identifier))
    rows = service.list_alerts(owner, device, start=start, end=end, limit=10)
    assert {row['alert_id'] for row in rows} == expected
    assert {row['status'] for row in rows} == {'open', 'closed'}
    assert service.list_alerts(owner, device, start=start, end=end, limit=1) == rows[:1]
    assert service.list_alerts(uuid4(), device, start=start, end=end, limit=10) is None
    status = service.request_led(owner, device, True)
    identifier = status['data']['command_id']
    assert service.get_command_for_user(owner, identifier) == status
    assert service.get_command_for_user(uuid4(), identifier) is None
    clock[0] += timedelta(seconds=31)
    expired = service.get_command_for_user(owner, identifier)
    assert expired['data']['status'] == 'unconfirmed'
    stored = connection.execute('SELECT status_envelope FROM aiot_commands WHERE command_id=%s',
                                (identifier,)).fetchone()[0]
    assert expired == stored
    assert service.get_command_for_user(owner, identifier) == stored
    restarted = AiotEventService(service.settings, service.catalog, str(owner))
    restarted._cursor, restarted._now = service._cursor, service._now
    assert restarted.get_command_for_user(owner, identifier) == stored
    assert service.get_command_for_user(owner, uuid4()) is None
    connection.execute('UPDATE devices SET is_active=false WHERE id=%s', (record,))
    assert service.get_command_for_user(owner, identifier) is None
