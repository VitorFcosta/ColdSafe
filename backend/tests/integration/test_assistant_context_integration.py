"""Real PostgreSQL SELECT-only assistant context; event/model values are fixtures."""
import json
from datetime import timedelta
from uuid import uuid4

import pytest
from psycopg.types.json import Jsonb

from backend.app.repositories.postgres import connect
from backend.app.services.assistant_context import AssistantContext
from backend.tests.integration.test_aiot_migrations_integration import database
from backend.tests.integration.test_predictive_alerts_integration import predictive, deliver

pytestmark = pytest.mark.integration


def context(predictive, monkeypatch):
    config, accounts, clock, _ = predictive
    monkeypatch.setattr(AssistantContext, '_now', staticmethod(lambda: clock['now']))
    return AssistantContext(config)


def test_absence_is_explicit_and_context_does_not_write(predictive, monkeypatch):
    service = context(predictive, monkeypatch)
    config, accounts, _, _ = predictive
    with connect(config) as connection:
        before = {table: connection.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                  for table in ('audit_events', 'predictive_rules', 'aiot_outbox', 'aiot_commands')}
    result = service.build(accounts[0][1])
    assert result['scope']['devices'] == 1
    assert result['scope']['missing_readings'] == 1
    assert result['equipment'][0]['reading'] == 'no_data'
    assert result['equipment'][0]['prediction'] == 'no_data'
    assert result['model'] is None
    assert result['alerts'] == {'temperature': 0, 'predictive': 0}
    with connect(config) as connection:
        after = {table: connection.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                 for table in before}
    assert after == before


def test_accounts_readings_predictions_alerts_and_metrics_are_private(predictive, monkeypatch):
    service = context(predictive, monkeypatch)
    config, accounts, _, events = predictive
    for account, health in ((0, 20), (1, 1)):
        for offset in range(3):
            deliver(events(offset, health=health, rul=account + 5, account=account))
        _, owner, model = accounts[account]
        with connect(config) as connection:
            connection.execute('INSERT INTO active_models(owner_user_id,model_id) VALUES(%s,%s)', (owner, model))
            connection.execute('UPDATE models SET metrics=%s WHERE id=%s', (Jsonb({
                'health': {'metrics': {'test': {'candidate': {'mae': health, 'rmse': 3, 'r2': .9}}}},
                'rul': {'metrics': {'test': {'candidate': {'mae': account + 7, 'rmse': 10, 'r2': .8}}}},
                'private_path': '/secret/model.pkl'}), model))
    first = service.build(accounts[0][1])
    second = service.build(accounts[1][1])
    assert first['equipment'][0]['health'] == 20
    assert second['equipment'][0]['health'] == 1
    assert first['equipment'][0]['rul_h'] == 5
    assert first['model']['test_mae']['health'] == 20
    assert second['model']['test_mae']['health'] == 1
    assert first['alerts']['predictive'] == 1
    assert first['equipment'][0]['sensors']['ambient_temperature'] == [6, 'degC']
    encoded = json.dumps(first)
    for private in ('private_path', '/secret', 'owner_user_id', str(accounts[1][1]), 'predictive-1'):
        assert private not in encoded
    assert len(encoded) <= 1800


def test_stale_values_are_not_offered_as_current_predictions(predictive, monkeypatch):
    service = context(predictive, monkeypatch)
    _, accounts, clock, events = predictive
    deliver(events(0))
    clock['now'] += timedelta(seconds=31)
    result = service.build(accounts[0][1])
    assert result['scope']['stale_readings'] == 1
    item = result['equipment'][0]
    assert item['reading'] == item['prediction'] == 'stale'
    assert item['health'] is None and item['rul_h'] is None
    assert item['sensors'] == {}


def test_new_source_without_prediction_does_not_reuse_older_prediction(predictive, monkeypatch):
    service = context(predictive, monkeypatch)
    _, accounts, _, events = predictive
    deliver(events(0))
    deliver(events(1), order=(1, 2))
    result = service.build(accounts[0][1])
    assert result['scope']['fresh_predictions'] == 0
    assert result['equipment'][0]['prediction'] == 'no_data'
    assert result['equipment'][0]['health'] is None


def test_unpersisted_prediction_is_excluded(predictive, monkeypatch):
    service = context(predictive, monkeypatch)
    _, accounts, _, events = predictive
    deliver(events(0), order=(1, 3))
    assert service.build(accounts[0][1])['equipment'][0]['prediction'] == 'no_data'


def test_revoked_ownership_and_inactive_device_remove_all_operational_data(predictive, monkeypatch):
    service = context(predictive, monkeypatch)
    config, accounts, _, events = predictive
    deliver(events(0))
    with connect(config) as connection:
        connection.execute('UPDATE devices SET is_active=false WHERE id=%s', (accounts[0][0].catalog['device_record_id'],))
    assert service.build(accounts[0][1])['scope']['devices'] == 0
    assert service.build(accounts[0][1])['equipment'] == []
    assert service.build(uuid4())['scope']['devices'] == 0


def test_device_reassignment_cannot_reveal_previous_environment_events(predictive, monkeypatch):
    service = context(predictive, monkeypatch)
    config, accounts, _, events = predictive
    for offset in range(3):
        deliver(events(offset))
    original, owner, _ = accounts[0]
    other, stranger, _ = accounts[1]
    with connect(config) as connection:
        connection.execute('UPDATE devices SET environment_id=%s WHERE id=%s',
                           (other.catalog['environment_id'], original.catalog['device_record_id']))
    assert service.build(owner)['equipment'] == []
    result = service.build(stranger)
    assert result['scope']['devices'] == result['scope']['missing_readings'] == 2
    assert result['alerts'] == {'temperature': 0, 'predictive': 0}
    assert all(item['reading'] == 'no_data' and item['sensors'] == {} for item in result['equipment'])


def test_sampling_includes_both_worst_health_and_worst_rul(predictive, monkeypatch):
    from copy import deepcopy
    service = context(predictive, monkeypatch)
    config, accounts, _, events = predictive
    original, owner, _ = accounts[0]
    bundle = events(0)
    with connect(config) as connection:
        for name, health, rul in (('worst-rul', 40, 1), ('ordinary', 70, 10), ('worst-health', 10, 30)):
            device = uuid4()
            connection.execute("INSERT INTO devices(id,environment_id,mqtt_device_id,name) VALUES(%s,%s,%s,'Test')",
                               (device, original.catalog['environment_id'], name))
            source_id = uuid4()
            for template in bundle[1:]:
                event = deepcopy(template)
                event.update(event_id=str(source_id if event['type'] == 'telemetry' else uuid4()),
                             device_record_id=str(device), device_id=name)
                if event['type'] != 'telemetry':
                    event['data']['source_event_id'] = str(source_id)
                if event['type'] == 'prediction':
                    event['data'].update(health_score=health, rul_hours=rul)
                connection.execute('INSERT INTO aiot_events(event_id,device_id,kind,received_at,source_event_id,linked,envelope) '
                                   'VALUES(%s,%s,%s,%s,%s,true,%s)',
                                   (event['event_id'], device, event['type'], event['received_at'],
                                    source_id if event['type'] != 'telemetry' else None, Jsonb(event)))
    result = service.build(owner)
    assert [item['device'] for item in result['equipment']] == ['worst-health', 'worst-rul']
    assert result['scope']['devices'] == 4
    assert result['scope']['fresh_predictions'] == 3
    assert result['scope']['missing_readings'] == 1
    assert result['scope']['truncated'] is True
    assert len(json.dumps(result)) <= 1800


def test_no_model_prediction_remains_explicitly_unavailable(predictive, monkeypatch):
    service = context(predictive, monkeypatch)
    _, accounts, _, events = predictive
    bundle = events(0, unavailable=True)
    bundle[3]['data'].update(model_id=None, model_version=None, reason='no_model')
    deliver(bundle)
    result = service.build(accounts[0][1])
    assert result['equipment'][0]['prediction'] == 'unavailable'
    assert result['equipment'][0]['reason'] == 'no_model'
