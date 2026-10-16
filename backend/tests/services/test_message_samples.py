from datetime import UTC, datetime, timedelta
import json
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pika
import psycopg
import pytest

from backend.app.services.message_samples import MessageSamples
from backend.app.services.messaging import MessagingUnavailable
from backend.tests.api.test_runtime_lifecycle import settings


@pytest.fixture
def samples():
    service = MessageSamples(settings())
    event = {
        'schema_version': 3, 'type': 'telemetry', 'event_id': str(uuid4()),
        'correlation_id': str(uuid4()), 'device_record_id': str(uuid4()),
        'environment_id': str(uuid4()), 'device_id': 'sample-device',
        'occurred_at': datetime.now(UTC).isoformat(),
        'data': {'secret': 'never-expose-me'},
    }
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.execute.return_value.fetchall.return_value = [
        (event['device_record_id'], event['environment_id'], event['device_id'])]
    with patch('backend.app.services.message_samples.connect', return_value=connection):
        yield service, event, connection


def record(service, event, *, exchange='coldsafe.events', headers=None):
    service.record(exchange, pika.BasicProperties(headers=headers), json.dumps(event).encode())


def test_samples_only_allowlisted_metadata_and_current_owner(samples):
    service, event, connection = samples
    actor = uuid4()
    record(service, event)
    snapshot = service.snapshot(actor)
    assert len(snapshot.messages) == 1
    assert snapshot.messages[0].event_id == event['event_id']
    assert 'never-expose-me' not in repr(snapshot)
    sql, parameters = connection.execute.call_args.args
    assert 'e.owner_user_id = %s' in sql and 'd.is_active' in sql
    assert parameters[0] == actor
    connection.execute.return_value.fetchall.return_value = []
    assert service.snapshot(actor).messages == ()
    assert service.snapshot(actor).last_observed_at is None


def test_scope_checks_all_three_identifiers_and_database_failure_fails_closed(samples):
    service, event, connection = samples
    record(service, event)
    connection.execute.return_value.fetchall.return_value = [
        (event['device_record_id'], str(uuid4()), event['device_id'])]
    assert service.snapshot(uuid4()).messages == ()
    connection.execute.side_effect = psycopg.OperationalError('private database secret')
    with pytest.raises(MessagingUnavailable, match='Message samples unavailable'):
        service.snapshot(uuid4())


def test_dead_letter_copies_keep_safe_source_reason_and_invalid_schema(samples):
    service, event, _ = samples
    headers = {'x-death': [{'queue': 'coldsafe.writer', 'reason': 'rejected', 'private': 'secret'}]}
    record(service, event, exchange='coldsafe.dlx', headers=headers)
    snapshot = service.snapshot(uuid4())
    assert snapshot.messages == ()
    dead = snapshot.dead_letters[0]
    assert (dead.source_queue, dead.reason, dead.error_code) == (
        'coldsafe.writer', 'rejected', 'INVALID_SCHEMA')
    record(service, event, headers=headers)
    normal = service.snapshot(uuid4()).messages[0]
    assert (normal.source_queue, normal.reason, normal.error_code) == (None, None, None)


def test_unroutable_and_untrusted_death_headers(samples):
    service, event, _ = samples
    record(service, event, exchange='coldsafe.jobs.unrouted', headers={'x-death': 'secret'})
    dead = service.snapshot(uuid4()).dead_letters[0]
    assert dead.source_queue is None and dead.reason == 'unroutable'
    event['event_id'] = str(uuid4())
    record(service, event, exchange='coldsafe.dlx', headers={
        'x-death': [{'queue': 'private-token', 'reason': 'private-error'}]})
    dead = service.snapshot(uuid4()).dead_letters[0]
    assert dead.source_queue is None and dead.reason is None


@pytest.mark.parametrize('override', [
    {'device_record_id': None}, {'environment_id': 'not-uuid'}, {'type': 'private-secret'},
    {'device_id': '<script>'}, {'event_id': str(uuid4()) * 20},
    {'occurred_at': '2026-10-16T10:00:00'}, {'schema_version': True},
])
def test_malformed_or_unprovable_envelopes_are_omitted(samples, override):
    service, event, _ = samples
    record(service, {**event, **override})
    assert service.snapshot(uuid4()).messages == ()


def test_payload_limits_duplicate_keys_and_non_json_are_discarded(samples):
    service, _, connection = samples
    for raw in (b'x' * 8193, b'[]', b'{', b'{"x":1,"x":2}', b'\xff', b'{"x":NaN}'):
        service.record('coldsafe.events', pika.BasicProperties(), raw)
    assert service.snapshot(uuid4()).messages == ()
    connection.execute.assert_not_called()


def test_bounded_samples_deduplicate_and_track_connection_and_age(samples):
    service, event, _ = samples
    now = datetime.now(UTC)
    with patch('backend.app.services.message_samples.datetime') as clock:
        clock.now.return_value = now - timedelta(seconds=31)
        clock.fromisoformat.side_effect = datetime.fromisoformat
        for _ in range(105):
            event['event_id'] = str(uuid4())
            record(service, event)
        record(service, event)
        clock.now.return_value = now
        service.set_connected(True)
        snapshot = service.snapshot(uuid4())
        assert len(snapshot.messages) == 100
        assert len({item.event_id for item in snapshot.messages}) == 100
        assert snapshot.connected and snapshot.stale
        service.set_connected(False)
        assert not service.snapshot(uuid4()).connected
        assert snapshot.capacity_per_kind == 100
        assert snapshot.stale_after_seconds == 30
