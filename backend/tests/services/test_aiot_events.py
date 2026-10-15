from datetime import UTC, datetime, timedelta

import pytest

from backend.app.services.aiot_events import freshness, ack_status


def test_freshness_uses_received_time_with_inclusive_thirty_seconds():
    now = datetime(2026, 10, 15, tzinfo=UTC)
    assert freshness(None, now)['state'] == 'no_data'
    telemetry = {'event_id': 'source', 'received_at': now.isoformat()}
    assert freshness(telemetry, now + timedelta(seconds=30))['state'] == 'fresh'
    assert freshness(telemetry, now + timedelta(seconds=30, microseconds=1))['state'] == 'stale'


@pytest.mark.parametrize(('offset', 'status'), [(-1, None), (0, 'confirmed'), (30, 'confirmed'), (31, 'unconfirmed')])
def test_ack_window_uses_trusted_receipt_and_includes_both_endpoints(offset, status):
    start = datetime(2026, 10, 15, tzinfo=UTC)
    command = {'status': 'pending', 'accepted_at': start, 'deadline_at': start + timedelta(seconds=30), 'desired_state': True}
    ack = {'result': 'applied', 'applied_state': True}
    assert ack_status(command, ack, start + timedelta(seconds=offset)) == status


def test_timeout_is_terminal_and_state_divergence_rejects():
    start = datetime(2026, 10, 15, tzinfo=UTC)
    command = {'status': 'unconfirmed', 'accepted_at': start, 'deadline_at': start + timedelta(seconds=30), 'desired_state': True}
    assert ack_status(command, {'result': 'applied', 'applied_state': True}, start) is None
    command['status'] = 'pending'
    assert ack_status(command, {'result': 'applied', 'applied_state': False}, start) == 'rejected'


@pytest.fixture
def service():
    import json
    from pathlib import Path
    from uuid import uuid4
    from backend.app.services.aiot_events import AiotEventService

    catalog = json.loads(Path('contracts/examples/aiot.context.json').read_text())
    return AiotEventService(None, catalog, str(uuid4()))


@pytest.fixture
def examples():
    import json
    from pathlib import Path
    return {row['name']: row['payload'] for row in json.loads(Path('contracts/examples/aiot.valid.json').read_text())}


def test_boundary_accepts_telemetry_but_rejects_wrong_sensor_scope_and_correlation(service, examples):
    from copy import deepcopy
    from gateway.bridge import PermanentError

    original = examples['telemetry_received']
    service._validate(original)
    for mutate, code in (
        (lambda event: event.update(environment_id='00000000-0000-4000-8000-000000000099'), 'UNAUTHORIZED_SCOPE'),
        (lambda event: event.update(correlation_id='00000000-0000-4000-8000-000000000099'), 'IDENTITY_MISMATCH'),
        (lambda event: event['data']['measurements']['humidity'].update(sensor_id='00000000-0000-4000-8000-000000000099'), 'IDENTITY_MISMATCH'),
        (lambda event: event['data']['measurements']['humidity'].update(value=float('nan')), 'INVALID_SCHEMA'),
        (lambda event: event.update(received_at=None), 'INVALID_BINDING'),
        (lambda event: event.update(unexpected=1), 'INVALID_SCHEMA'),
    ):
        event = deepcopy(original)
        mutate(event)
        with pytest.raises(PermanentError, match=code):
            service._validate(event)


class LinkCursor:
    def __init__(self, source, model=None):
        self.source, self.model = source, model
        self.normalized = None
        self.result = None

    def execute(self, sql, params=()):
        if sql.startswith(('SELECT envelope', 'SELECT t.envelope')):
            self.result = {'envelope': self.source} if self.source else None
        elif sql.startswith('SELECT model_version'):
            self.result = self.model
        elif sql.startswith('UPDATE aiot_events'):
            self.normalized = self.source if len(params) == 1 else params[0].obj
            self.linked_event_id = params[-1]
        else:
            raise AssertionError(sql)
        return self

    def fetchone(self):
        return self.result


def test_prediction_can_wait_for_source_and_no_model_remains_explicit(service, examples):
    prediction = examples['prediction_unavailable_no_model']
    cursor = LinkCursor(None)
    service._link(cursor, prediction)
    assert cursor.normalized is None
    cursor.source = examples['telemetry_received']
    service._link(cursor, prediction)
    assert cursor.linked_event_id == prediction['event_id']
    assert prediction['data']['health_score'] is None


@pytest.mark.parametrize('field', ('input_received_at', 'equipment_id', 'environment_id', 'correlation_id'))
def test_prediction_never_links_to_mismatched_source(service, examples, field):
    from copy import deepcopy
    from gateway.bridge import PermanentError

    prediction = deepcopy(examples['prediction_unavailable_no_model'])
    if field == 'input_received_at':
        prediction['data'][field] = '2026-10-12T18:00:01Z'
    elif field == 'equipment_id':
        prediction['data'][field] = '00000000-0000-4000-8000-000000000099'
    else:
        prediction[field] = '00000000-0000-4000-8000-000000000099'
    with pytest.raises(PermanentError, match='IDENTITY_MISMATCH'):
        service._link(LinkCursor(examples['telemetry_received']), prediction)


def test_available_prediction_checks_private_model_and_preserves_zero_after_expiry(service, examples, monkeypatch):
    from gateway.bridge import PermanentError
    from backend.app.services.aiot_events import instant

    source = examples['telemetry_received']
    prediction = examples['prediction_available_zero_rul']
    with pytest.raises(PermanentError, match='UNAUTHORIZED_SCOPE'):
        service._link(LinkCursor(source), prediction)
    cursor = LinkCursor(source, {'model_version': prediction['data']['model_version'],
                                 'features_version': prediction['data']['features_version']})
    monkeypatch.setattr(service, '_now', lambda: instant(source['received_at']) + timedelta(seconds=30))
    service._link(cursor, prediction)
    assert cursor.linked_event_id == prediction['event_id']
    assert prediction['data']['rul_hours'] == 0
    assert prediction['data']['status'] == 'available'
    monkeypatch.setattr(service, '_now', lambda: instant(source['received_at']) + timedelta(seconds=31))
    service._link(cursor, prediction)
    assert prediction['data']['rul_hours'] == 0
    assert prediction['data']['status'] == 'available'
    assert cursor.source == source


def test_generated_commands_and_statuses_validate_against_v3_schema(service):
    from jsonschema import Draft202012Validator, FormatChecker
    from simulator.model import SCHEMA

    class CommandsCursor:
        def execute(self, *args):
            pass

    status = service._command(CommandsCursor(), 'led', False, None)
    Draft202012Validator({**SCHEMA, '$ref': '#/$defs/command_status_event'},
                         format_checker=FormatChecker()).validate(status)
    assert status['data']['desired_state'] is False
    assert status['data']['confirmed_state'] is None


def test_prediction_with_stale_input_cannot_claim_available(service, examples):
    from copy import deepcopy
    from gateway.bridge import PermanentError
    from backend.app.services.aiot_events import instant
    from simulator.model import utc

    prediction = deepcopy(examples['prediction_available_zero_rul'])
    prediction['occurred_at'] = utc(instant(prediction['data']['input_received_at']) + timedelta(seconds=31))
    cursor = LinkCursor(examples['telemetry_received'], {
        'model_version': prediction['data']['model_version'],
        'features_version': prediction['data']['features_version']})
    with pytest.raises(PermanentError, match='IDENTITY_MISMATCH'):
        service._link(cursor, prediction)
    assert prediction['data']['status'] == 'available'


def test_prediction_delivery_requires_proof_and_freshness_without_rewriting(service, examples, monkeypatch):
    from copy import deepcopy
    from backend.app.services.aiot_events import instant

    prediction = examples['prediction_available_zero_rul']
    original = deepcopy(prediction)
    cursor = LinkCursor(None)
    assert service._deliverable_prediction(cursor, prediction) is None
    cursor.source = examples['telemetry_received']
    monkeypatch.setattr(service, '_now', lambda: instant(cursor.source['received_at']) + timedelta(seconds=30))
    assert service._deliverable_prediction(cursor, prediction) == original
    monkeypatch.setattr(service, '_now', lambda: instant(cursor.source['received_at']) + timedelta(seconds=31))
    assert service._deliverable_prediction(cursor, prediction) is None
    assert prediction == original
