"""Live predictions share the training kernel and preserve durable identities."""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import numpy as np
import pytest
from jsonschema import Draft202012Validator, FormatChecker

from backend.app.domain.feature_preprocessing import FeatureTransform
from backend.app.domain.features import FeatureSpec
from backend.app.services.feature_inputs import features_version, telemetry_features
from backend.app.services.inference import InferenceService, MAX_HISTORY
from backend.app.services.model_bundle import LoadedBundle
from gateway.bridge import PermanentError


@pytest.fixture
def source():
    cases = json.loads(Path('contracts/examples/aiot.valid.json').read_text())
    return deepcopy(next(case['payload'] for case in cases if case['name'] == 'telemetry_received'))


@pytest.fixture
def bundle():
    spec = FeatureSpec(('ambient_temperature_c',), (2, 4))
    transform = FeatureTransform(spec.names, np.zeros(len(spec.names)),
        np.full(len(spec.names), -1e9), np.full(len(spec.names), 1e9))
    health, rul = MagicMock(), MagicMock()
    health.predict.return_value, rul.predict.return_value = np.array([105.]), np.array([0.])
    return LoadedBundle(uuid4(), 'live-1', features_version(spec), health, rul, spec, transform,
                        {'health': 'score', 'rul': 'h'})


@pytest.fixture
def setup(source, bundle):
    now = datetime.fromisoformat(source['received_at'].replace('Z', '+00:00'))
    models = MagicMock()
    models.sync_active.return_value = bundle
    models.active.return_value = {'model_id': bundle.model_id, 'model_version': bundle.model_version,
                                 'features_version': bundle.features_version}
    service = InferenceService(None, {key: source[key] for key in
        ('device_id', 'device_record_id', 'environment_id')} |
        {'equipment_id': source['data']['equipment']['equipment_id']}, uuid4(), models, clock=lambda: now)
    history = []
    for seconds in (4, 3, 2, 1):
        event = deepcopy(source)
        event['event_id'] = str(uuid4())
        event['received_at'] = (now - timedelta(seconds=seconds)).isoformat().replace('+00:00', 'Z')
        history.append(event)
    return service, models.active.return_value, history, now


def predict(setup, source, bundle):
    service, metadata, history, _ = setup
    return service._prediction(source, bundle, metadata, history)


def test_shared_kernel_zero_rul_and_complete_canonical_event(setup, source, bundle):
    event = predict(setup, source, bundle)
    expected = telemetry_features(setup[2], source['data']['equipment']['equipment_id'],
                                  source['received_at'], bundle.transform, bundle.spec)
    np.testing.assert_array_equal(bundle.health.predict.call_args.args[0], expected.values)
    assert event['data']['health_score'] == 100
    assert event['data']['rul_hours'] == 0
    assert event['data']['status'] == 'available'
    assert event['data']['source_event_id'] == source['event_id']
    schema = json.loads(Path('contracts/aiot.schema.json').read_text())
    Draft202012Validator({**schema, '$ref': '#/$defs/prediction_event'},
                         format_checker=FormatChecker()).validate(event)


@pytest.mark.parametrize('case,reason', [('empty', 'insufficient_history'),
    ('overflow', 'invalid_features'), ('nan', 'model_unavailable'),
    ('shape', 'model_unavailable'), ('raise', 'model_unavailable'),
    ('bad_features', 'invalid_features'), ('missing', 'model_unavailable'),
    ('swapped', 'model_unavailable'), ('stale', 'stale_input'), ('no_model', 'no_model')])
def test_unavailable_states_are_explicit(setup, source, bundle, case, reason):
    service, metadata, history, now = setup
    if case == 'empty':
        history = []
    elif case == 'overflow':
        history = history * (MAX_HISTORY // len(history) + 1)
    elif case == 'nan':
        bundle.rul.predict.return_value = np.array([np.nan])
    elif case == 'shape':
        bundle.health.predict.return_value = np.array([1, 2])
    elif case == 'raise':
        bundle.health.predict.side_effect = RuntimeError('private error')
    elif case == 'bad_features':
        history[0]['data']['measurements']['ambient_temperature']['unit'] = 'invalid'
    elif case == 'missing':
        bundle = None
    elif case == 'swapped':
        metadata = {**metadata, 'model_id': uuid4()}
    elif case == 'stale':
        service.clock = lambda: now + timedelta(seconds=31)
    elif case == 'no_model':
        metadata = None
        service.clock = lambda: now + timedelta(seconds=31)
    event = service._prediction(source, bundle, metadata, history)
    assert event['data']['reason'] == reason
    assert event['data']['health_score'] is None and event['data']['rul_hours'] is None


def test_input_can_expire_during_prediction(setup, source, bundle):
    service, _, _, now = setup
    bundle.rul.predict.side_effect = lambda _: (setattr(service, 'clock',
        lambda: now + timedelta(seconds=31)) or np.array([0.]))
    assert predict(setup, source, bundle)['data']['reason'] == 'stale_input'


def test_future_input_is_not_accepted(setup, source, bundle):
    setup[0].clock = lambda: setup[3] - timedelta(microseconds=1)
    with pytest.raises(PermanentError, match='INVALID_BINDING'):
        predict(setup, source, bundle)


@pytest.fixture
def connection(monkeypatch):
    connection = MagicMock()
    monkeypatch.setattr('backend.app.services.inference.connect', lambda _: connection)
    connection.__enter__.return_value = connection
    connection.execute.return_value.rowcount = 1
    return connection


def test_durable_redelivery_never_recalculates_after_swap(setup, source, connection):
    service = setup[0]
    stored = {'event_id': str(uuid4()), 'data': {'model_version': 'old'}}
    connection.execute.return_value.fetchone.side_effect = [None, (1,), (source, stored)]
    service._prediction = MagicMock()
    assert service.process(source) == stored
    service._prediction.assert_not_called()


def test_reused_identity_with_changed_envelope_is_rejected(setup, source, connection):
    changed = {**source, 'occurred_at': '2026-10-12T00:00:00Z'}
    connection.execute.return_value.fetchone.side_effect = [None, (1,), (changed, {})]
    with pytest.raises(PermanentError, match='IDENTITY_MISMATCH'):
        setup[0].process(source)


def test_ownership_is_checked_before_history_and_outbox(setup, source, connection):
    connection.execute.return_value.fetchone.side_effect = [None, None]
    with pytest.raises(PermanentError, match='UNAUTHORIZED_SCOPE'):
        setup[0].process(source)
    assert not any('inference_events' in call.args[0] for call in connection.execute.call_args_list)


def test_new_source_and_result_commit_together(setup, source, connection):
    service = setup[0]
    connection.execute.return_value.fetchone.side_effect = [None, (1,), None]
    connection.execute.return_value.fetchall.return_value = [(event,) for event in setup[2]]
    prediction = service.process(source)
    insert = next(call for call in connection.execute.call_args_list if call.args[0].startswith('INSERT'))
    assert insert.args[1][-1].obj == prediction
    assert insert.args[1][-3].obj == source
    assert prediction['data']['status'] == 'available'


def test_outbox_publishes_persisted_output_and_marks_confirmation(setup, connection):
    service = setup[0]
    connection.execute.return_value.__iter__.return_value = iter([({'event_id': 'saved'},)])
    assert service.pending_outputs() == [{'event_id': 'saved'}]
    service.mark_published('saved')
    assert 'COALESCE' in connection.execute.call_args.args[0]


def test_conflicting_global_source_id_never_returns_another_owners_prediction(setup, source, connection):
    connection.execute.return_value.fetchone.side_effect = [None, (1,), None]
    connection.execute.return_value.fetchall.return_value = []
    connection.execute.return_value.rowcount = 0
    with pytest.raises(PermanentError, match='IDENTITY_MISMATCH'):
        setup[0].process(source)


@pytest.mark.parametrize('field', ['device_id', 'device_record_id', 'environment_id', 'equipment_id'])
def test_catalog_mismatch_never_reads_the_model_cache(setup, source, field):
    service = setup[0]
    if field == 'equipment_id':
        source['data']['equipment'][field] = str(uuid4())
    else:
        source[field] = str(uuid4())
    with pytest.raises(PermanentError, match='UNAUTHORIZED_SCOPE'):
        service.process(source)
    service.models.sync_active.assert_not_called()


@pytest.mark.parametrize('operation', ['pending_outputs', 'mark_published'])
def test_revoked_owner_cannot_release_durable_predictions(setup, connection, operation):
    connection.execute.return_value.fetchone.return_value = None
    with pytest.raises(PermanentError, match='UNAUTHORIZED_SCOPE'):
        getattr(setup[0], operation)(*(['saved'] if operation == 'mark_published' else []))
    assert not any('inference_events' in call.args[0] for call in connection.execute.call_args_list)
