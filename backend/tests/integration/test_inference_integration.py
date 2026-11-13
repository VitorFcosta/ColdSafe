"""Real PostgreSQL history, causal parity, replay and model recovery."""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from uuid import uuid4

import numpy as np
from jsonschema import Draft202012Validator, FormatChecker
import pytest
from threadpoolctl import threadpool_limits

from backend.app.repositories.postgres import connect
from backend.app.services.feature_inputs import LIVE_NAMES, offline_features, telemetry_features
from backend.app.services.generation import DTYPE
from backend.app.services.inference import InferenceService
from backend.app.services.models import ModelService
from backend.tests.integration.test_aiot_migrations_integration import database
from backend.tests.infra.test_rabbitmq_integration import broker, connect as amqp_connect, publish
from backend.tests.integration.test_models_integration import registry
from backend.tests.services.test_training import package
from gateway.bridge import PermanentError
from simulator.model import SCHEMA, utc

pytestmark = pytest.mark.integration
PREDICTION = Draft202012Validator({**SCHEMA, '$ref': '#/$defs/prediction_event'}, format_checker=FormatChecker())


@pytest.fixture
def live(registry):
    models, settings, owner, stranger, register = registry
    catalog = json.loads(Path('contracts/examples/aiot.context.json').read_text())
    with connect(settings) as connection:
        connection.execute('INSERT INTO environments(id,owner_user_id,name) VALUES(%s,%s,%s)',
                           (catalog['environment_id'], owner, 'Inference fixture'))
        connection.execute('INSERT INTO environment_rules(environment_id) VALUES(%s)', (catalog['environment_id'],))
        connection.execute('INSERT INTO devices(id,environment_id,mqtt_device_id,name) VALUES(%s,%s,%s,%s)',
                           (catalog['device_record_id'], catalog['environment_id'], catalog['device_id'], 'Fixture'))
    origin = datetime(2026, 10, 19, 12, tzinfo=UTC)
    clock = {'now': origin + timedelta(seconds=10)}
    inference = InferenceService(settings, catalog, owner, models, clock=lambda: clock['now'])
    template = next(item['payload'] for item in json.loads(Path('contracts/examples/aiot.valid.json').read_text())
                    if item['name'] == 'telemetry_received')

    def source(offset):
        event = deepcopy(template)
        event['event_id'] = event['correlation_id'] = str(uuid4())
        event['received_at'] = event['occurred_at'] = utc(origin + timedelta(seconds=offset))
        event['data']['measurements']['ambient_temperature']['value'] = 6 + offset / 10
        return event

    def activate(model):
        request = models.request(owner, model['id'])
        assert models.execute(request['id'])
        return request

    return inference, models, settings, owner, stranger, register, source, activate, clock


def test_real_history_warmup_default_kernel_parity_and_loaded_predictions(live):
    inference, models, _, owner, _, register, source, activate, _ = live
    events = [source(index) for index in range(3)]
    no_model = inference.process(events[0])
    PREDICTION.validate(no_model)
    assert no_model['data']['reason'] == 'no_model'
    model, _ = register()
    activate(model)
    warmup = inference.process(events[1])
    assert warmup['data']['reason'] == 'insufficient_history'
    result = inference.process(events[2])
    PREDICTION.validate(result)
    assert result['data']['status'] == 'available'
    bundle = models.loaded[owner]
    # Compare the exact same rows through the existing offline/online adapters.
    rows = np.zeros(3, dtype=DTYPE)
    for index, event in enumerate(events):
        rows['observed_at'][index] = np.datetime64(event['received_at'].removesuffix('Z'), 'ms')
        for sensor, live_name in LIVE_NAMES.items():
            rows[sensor][index] = event['data']['measurements'][live_name]['value']
    offline = offline_features(rows, bundle.spec)
    online = telemetry_features(events, inference.catalog['equipment_id'], events[-1]['received_at'],
                                bundle.transform, bundle.spec)
    expected = bundle.transform.apply(offline.values[-1:], bundle.spec.names)
    np.testing.assert_array_equal(online.values, expected)
    with threadpool_limits(limits=1):
        assert result['data']['health_score'] == float(np.clip(bundle.health.predict(expected)[0], 0, 100))
        assert result['data']['rul_hours'] == float(max(bundle.rul.predict(expected)[0], 0))
    assert result['data']['source_event_id'] == events[2]['event_id']


def test_live_swap_duplicate_replay_restart_and_failed_candidate(live):
    inference, models, config, owner, _, register, source, activate, _ = live
    first, _ = register()
    activate(first)
    events = [source(index) for index in range(4)]
    for event in events[:2]:
        inference.process(event)
    original = inference.process(events[2])
    original_bundle = models.loaded[owner]
    second, _ = register()
    activate(second)
    result = inference.process(events[3])
    assert result['data']['model_version'] == second['model_version']
    assert models.loaded[owner] is not original_bundle
    assert inference.process(events[2]) == original
    restored = ModelService(config, artifact_root=models.artifact_root)
    restarted = InferenceService(config, inference.catalog, owner, restored, clock=inference.clock)
    assert restarted.process(source(5))['data']['model_version'] == second['model_version']
    assert restored.loaded[owner].model_id == second['id']
    assert restarted.process(events[2]) == original
    broken, directory = register()
    request = models.request(owner, broken['id'])
    (directory / 'rul/model.pkl').unlink()
    assert models.execute(request['id'])
    assert models.get(owner, request['id'])['error_code'] == 'MODEL_LOAD_FAILED'
    assert inference.process(source(6))['data']['model_id'] == str(second['id'])


def test_late_prediction_never_replaces_new_api_reading(live):
    from backend.app.services.aiot_events import AiotEventService
    inference, models, settings, owner, stranger, register, source, activate, clock = live
    model, _ = register()
    activate(model)
    events = [source(index) for index in range(4)]
    predictions = [inference.process(event) for event in events]
    api = AiotEventService(settings, inference.catalog, str(owner))
    api._now = lambda: clock['now']
    # New source/prediction reaches the API first; an older pair arrives later.
    for event in (events[3], predictions[3], events[2], predictions[2]):
        api.process(event)
    state = api.snapshot(owner, inference.catalog['device_id'])
    assert state['telemetry']['event_id'] == events[3]['event_id']
    assert state['prediction'] == predictions[3]
    assert api.snapshot(stranger, inference.catalog['device_id']) is None


def test_durable_output_and_authorization_before_replay_or_publication(live):
    inference, models, settings, _, stranger, register, source, activate, _ = live
    model, _ = register()
    activate(model)
    event = source(0)
    prediction = inference.process(event)
    assert inference.pending_outputs() == [prediction]
    inference.mark_published(prediction['event_id'])
    assert inference.pending_outputs() == []
    assert inference.process(event) == prediction
    altered = deepcopy(event)
    altered['data']['measurements']['humidity']['value'] += 1
    with pytest.raises(PermanentError, match='IDENTITY_MISMATCH'):
        inference.process(altered)
    other = InferenceService(settings, inference.catalog, stranger, models, clock=inference.clock)
    with pytest.raises(PermanentError, match='UNAUTHORIZED_SCOPE'):
        other.process(event)
    with connect(settings) as connection:
        connection.execute('UPDATE devices SET is_active=false WHERE id=%s', (inference.catalog['device_record_id'],))
    for operation in (lambda: inference.process(event), inference.pending_outputs,
                      lambda: inference.mark_published(prediction['event_id'])):
        with pytest.raises(PermanentError, match='UNAUTHORIZED_SCOPE'):
            operation()


def test_stale_input_and_unloadable_active_after_restart_are_explicit(live):
    inference, models, settings, owner, _, register, source, activate, clock = live
    model, directory = register()
    activate(model)
    assert inference.process(source(-30))['data']['reason'] == 'stale_input'
    (directory / 'health/model.pkl').unlink()
    restored = ModelService(settings, artifact_root=models.artifact_root)
    restarted = InferenceService(settings, inference.catalog, owner, restored, clock=inference.clock)
    result = restarted.process(source(1))
    assert result['data']['reason'] == 'model_unavailable'
    assert result['data']['model_id'] == str(model['id'])
    assert result['data']['health_score'] is None and result['data']['rul_hours'] is None
    PREDICTION.validate(result)


def test_sql_history_is_strict_past_ignores_inverted_delivery_and_same_millisecond(live):
    inference, _, _, _, _, register, source, activate, _ = live
    model, _ = register()
    activate(model)
    future, anchor, middle, current = (source(offset) for offset in (8, 0, 1, 2))
    inference.process(future)
    inference.process(anchor)
    inference.process(middle)
    inference.process(current)
    same_millisecond = source(2.0008)
    same_millisecond['data']['measurements']['ambient_temperature']['value'] = 8
    actual = inference.process(same_millisecond)
    bundle = inference.models.loaded[inference.owner]
    past = telemetry_features([anchor, middle], inference.catalog['equipment_id'], same_millisecond['received_at'],
                              bundle.transform, bundle.spec)
    with threadpool_limits(limits=1):
        assert actual['data']['health_score'] == float(np.clip(bundle.health.predict(past.values)[0], 0, 100))
        assert actual['data']['rul_hours'] == float(max(bundle.rul.predict(past.values)[0], 0))


def test_default_hour_window_from_real_sql_matches_offline_without_shortening_warmup(live):
    from types import SimpleNamespace
    from psycopg.types.json import Jsonb
    from backend.app.domain.features import FeatureSpec
    from backend.app.domain.feature_preprocessing import FeatureTransform
    inference, _, settings, _, _, _, source, _, clock = live
    events = [source(offset) for offset in range(3601)]
    clock['now'] = datetime.fromisoformat(events[-1]['received_at'].replace('Z', '+00:00'))
    for event in events:
        event['data']['measurements']['ambient_temperature']['value'] = 6
    values = []
    for event in events:
        prediction = inference._prediction(event, None, None, [])
        values.append((event['event_id'], inference.owner, event['device_record_id'], event['environment_id'],
            inference.catalog['equipment_id'], event['received_at'], Jsonb(event), prediction['event_id'], Jsonb(prediction)))
    with connect(settings) as connection, connection.cursor() as cursor:
        cursor.executemany('INSERT INTO inference_events(source_event_id,owner_user_id,device_record_id,'
            'environment_id,equipment_id,received_at,source,prediction_event_id,prediction) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)', values)
    spec = FeatureSpec()
    transform = FeatureTransform(spec.names, np.zeros(len(spec.names)),
                                 np.full(len(spec.names), -1e6), np.full(len(spec.names), 1e6))
    with connect(settings) as connection:
        history = inference._history(connection, events[-1], SimpleNamespace(spec=spec))
    assert len(history) == 3600
    rows = np.zeros(len(events), dtype=DTYPE)
    for index, event in enumerate(events):
        rows['observed_at'][index] = np.datetime64(event['received_at'].removesuffix('Z'), 'ms')
        for sensor, live_name in LIVE_NAMES.items():
            rows[sensor][index] = event['data']['measurements'][live_name]['value']
    offline = offline_features(rows, spec)
    online = telemetry_features(history, inference.catalog['equipment_id'], events[-1]['received_at'], transform, spec)
    assert spec.windows_seconds == (900, 3600)
    assert offline.sufficient[-2:].tolist() == [False, True]
    assert online.sufficient.tolist() == [True]
    np.testing.assert_array_equal(online.values, transform.apply(offline.values[-1:], spec.names))


def test_real_broker_confirmation_loss_replays_identical_prediction_without_recalculation(live, broker, monkeypatch):
    import time
    import psycopg
    from backend.app.amqp.inference import InferenceWorker
    inference, models, settings, _, _, register, source, activate, _ = live
    model, _ = register()
    activate(model)
    events = [source(offset) for offset in range(3)]
    worker = InferenceWorker(models, inference, inference.catalog, lambda _: True,
        host='127.0.0.1', port=broker['port'], password=broker['passwords']['inference'])
    try:
        with amqp_connect(broker, 'gateway') as ingress, amqp_connect(broker, 'inference') as channel:
            for event in events[:2]:
                publish(ingress, {'payload': event, 'routing_key': f"v3.telemetry.{event['device_record_id']}"})
            deadline = time.monotonic() + 10
            while True:
                worker.step(channel)
                with connect(settings) as connection:
                    count = connection.execute('SELECT count(*) FROM inference_events').fetchone()[0]
                if count == 2:
                    break
                assert time.monotonic() < deadline
                channel.connection.process_data_events(time_limit=0.01)
            publish(ingress, {'payload': events[2], 'routing_key': f"v3.telemetry.{events[2]['device_record_id']}"})
            with monkeypatch.context() as patch:
                def lost_confirmation(_):
                    raise psycopg.OperationalError('Lost publication marker')
                patch.setattr(inference, 'mark_published', lost_confirmation)
                with pytest.raises(psycopg.OperationalError):
                    while True:
                        worker.step(channel)
                        assert time.monotonic() < deadline
            pending = inference.pending_outputs()
            assert len(pending) == 1 and pending[0]['data']['status'] == 'available'
            # A replay after the output was published must not execute either estimator again.
            with monkeypatch.context() as patch:
                patch.setattr(models.loaded[inference.owner].health, 'predict',
                              lambda _: pytest.fail('Duplicate recalculated model'))
                worker.step(channel)
            assert inference.pending_outputs() == []
        outputs = []
        with amqp_connect(broker, 'delivery') as channel:
            while True:
                method, _, body = channel.basic_get('coldsafe.delivery', auto_ack=True)
                if method is None:
                    break
                event = json.loads(body)
                if event['type'] == 'prediction' and event['data']['source_event_id'] == events[2]['event_id']:
                    PREDICTION.validate(event)
                    outputs.append(event)
        assert outputs == [pending[0], pending[0]]
        with connect(settings) as connection:
            assert connection.execute('SELECT count(*) FROM inference_events').fetchone() == (3,)
    finally:
        worker.close()
