"""Real PostgreSQL transitions, duplicate/order protection and private durable state."""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from backend.app.repositories.postgres import MIGRATIONS, connect, initialize_schema
from backend.app.services.aiot_events import AiotEventService
from backend.app.services.predictive_alerts import DEFAULT_RULES
from backend.tests.integration.test_aiot_migrations_integration import database
from simulator.model import utc

pytestmark = pytest.mark.integration


@pytest.fixture
def predictive(database):
    initialize_schema(database)
    examples = {item['name']: item['payload'] for item in
                json.loads(Path('contracts/examples/aiot.valid.json').read_text())}
    template = json.loads(Path('contracts/examples/aiot.context.json').read_text())
    services = []
    with connect(database) as connection:
        for index in range(2):
            owner = connection.execute('INSERT INTO users(email,password_hash,role) '
                                       "VALUES(%s,'test-only','operator') RETURNING id",
                                       (f'owner-{index}@example.invalid',)).fetchone()[0]
            catalog = {**template, 'environment_id': str(uuid4()), 'device_record_id': str(uuid4()),
                       'device_id': f'predictive-{index}'}
            connection.execute("INSERT INTO environments(id,owner_user_id,name) VALUES(%s,%s,'Test')",
                               (catalog['environment_id'], owner))
            connection.execute("INSERT INTO devices(id,environment_id,mqtt_device_id,name) VALUES(%s,%s,%s,'Test')",
                               (catalog['device_record_id'], catalog['environment_id'], catalog['device_id']))
            dataset = connection.execute("INSERT INTO datasets(owner_user_id,name,features_version) "
                                         "VALUES(%s,'Test','fan-v1') RETURNING id", (owner,)).fetchone()[0]
            job = connection.execute("INSERT INTO jobs(owner_user_id,job_type,dataset_id,total_units) "
                                     "VALUES(%s,'training',%s,2) RETURNING id", (owner, dataset)).fetchone()[0]
            model = connection.execute('INSERT INTO models(owner_user_id,dataset_id,training_job_id,'
                                       "model_version,features_version,artifact_key) VALUES(%s,%s,%s,'demo-v1','fan-v1','test/model') RETURNING id",
                                       (owner, dataset, job)).fetchone()[0]
            services.append((AiotEventService(database, catalog, str(owner)), owner, model))
    clock = {'now': datetime(2026, 10, 19, 12, tzinfo=UTC)}
    for service, _, _ in services:
        service._now = lambda: clock['now']

    def events(offset, health=20, rul=10, account=0, unavailable=False):
        service, _, model = services[account]
        clock['now'] = datetime(2026, 10, 19, 12, tzinfo=UTC) + timedelta(seconds=offset)
        source = deepcopy(examples['telemetry_received'])
        source['event_id'] = source['correlation_id'] = str(uuid4())
        source.update({key: service.catalog[key] for key in ('device_id', 'device_record_id', 'environment_id')})
        source['received_at'] = source['occurred_at'] = utc(clock['now'])
        source['data']['measurements']['ambient_temperature']['value'] = 6
        receipt = deepcopy(examples['telemetry_persisted'])
        prediction = deepcopy(examples['prediction_available_zero_rul'])
        for event in (receipt, prediction):
            event.update({key: source[key] for key in ('device_id', 'device_record_id', 'environment_id', 'received_at', 'occurred_at')})
            event['event_id'] = str(uuid4())
            event['correlation_id'] = source['event_id']
            event['data'].update(source_event_id=source['event_id'], input_received_at=source['received_at'])
        prediction['data'].update(model_id=str(model), model_version='demo-v1', features_version='fan-v1',
                                  health_score=health, rul_hours=rul)
        if unavailable:
            prediction['data'].update(status='unavailable', reason='insufficient_history', health_score=None, rul_hours=None)
        return service, source, receipt, prediction

    return database, services, clock, events


def deliver(bundle, order=(1, 2, 3)):
    service, *_ = bundle
    for index in order:
        service.process(bundle[index])


def view(account):
    service, owner, _ = account
    return service.insights(owner, service.catalog['device_id'])


def test_migration_constraints_and_repeatable_registration(predictive):
    settings, accounts, _, _ = predictive
    assert dict(MIGRATIONS)[11].name == '011_predictive_alerts.sql'
    initialize_schema(settings)
    view(accounts[0])
    with connect(settings) as connection:
        assert connection.execute('SELECT max(version) FROM schema_migrations').fetchone() == (11,)
        for change in ('health_critical=40', "rul_recovery_hours='NaN'::float8", 'open_count=0'):
            with pytest.raises(psycopg.errors.CheckViolation), connection.transaction():
                connection.execute(f'UPDATE predictive_rules SET {change}')


def test_open_oscillate_recover_duplicate_restart_and_audit(predictive):
    settings, accounts, clock, events = predictive
    for offset in range(3):
        bundle = events(offset)
        deliver(bundle)
        deliver(bundle)
    snapshot = view(accounts[0])
    assert len(snapshot['active_alerts']) == 1
    assert snapshot['trend'] == 'stable'
    service, owner, _ = accounts[0]
    restored = AiotEventService(settings, service.catalog, str(owner))
    restored._now = lambda: clock['now']
    assert restored.insights(owner, service.catalog['device_id'])['active_alerts'] == snapshot['active_alerts']
    for offset in range(3, 8):
        deliver(events(offset, 45, 60))
    deliver(events(8, 35, 30))
    for offset in range(9, 18):
        deliver(events(offset, 45, 60))
    assert len(view(accounts[0])['active_alerts']) == 1
    deliver(events(18, 45, 60))
    assert view(accounts[0])['active_alerts'] == []
    with connect(settings) as connection:
        assert connection.execute("SELECT event_type FROM audit_events WHERE event_type LIKE 'predictive_alert_%' ORDER BY occurred_at").fetchall() == [
            ('predictive_alert_opened',), ('predictive_alert_closed',)]
        assert connection.execute('SELECT count(*) FROM aiot_commands').fetchone() == (0,)


def test_unavailable_stale_and_missing_do_not_close_or_count_replayed_source(predictive):
    settings, accounts, clock, events = predictive
    for offset in range(3):
        deliver(events(offset))
    for offset in range(3, 12):
        deliver(events(offset, 80, 100))
    deliver(events(12, unavailable=True))
    assert view(accounts[0])['availability'] == 'unavailable'
    deliver(events(13, 80, 100))
    clock['now'] += timedelta(seconds=31)
    assert view(accounts[0])['availability'] == 'stale'
    assert len(view(accounts[0])['active_alerts']) == 1
    for offset in range(45, 54):
        deliver(events(offset, 80, 100))
    assert len(view(accounts[0])['active_alerts']) == 1
    bundle = events(54, 80, 100)
    deliver(bundle, (1,))
    assert view(accounts[0])['availability'] == 'no_data'
    assert len(view(accounts[0])['active_alerts']) == 1
    deliver(bundle, (3, 2))
    assert view(accounts[0])['active_alerts'] == []


def test_deferred_source_receipt_last_lag_and_old_sources_do_not_advance(predictive):
    settings, accounts, clock, events = predictive
    first = events(0)
    deliver(first, (3, 2, 1))
    old = events(1)
    current = events(2)
    deliver(current, (1,))
    deliver(old, (1,))
    clock['now'] += timedelta(seconds=1)
    deliver(current, (3, 2))
    assert view(accounts[0])['active_alerts'] == []
    replay = deepcopy(current[3])
    replay['event_id'] = str(uuid4())
    current[0].process(replay)
    assert view(accounts[0])['active_alerts'] == []
    deliver(old, (3, 2))
    assert view(accounts[0])['active_alerts'] == []
    deliver(events(4))
    assert len(view(accounts[0])['active_alerts']) == 1


def test_prediction_lag_behind_latest_telemetry_still_counts_monotonic_inputs(predictive):
    _, accounts, clock, events = predictive
    bundles = [events(offset) for offset in range(4)]
    for bundle in bundles:
        deliver(bundle, (1,))
    for bundle in bundles[:3]:
        deliver(bundle, (3, 2))
    assert len(view(accounts[0])['active_alerts']) == 1
    assert view(accounts[0])['availability'] == 'no_data'


def test_rule_permissions_scope_and_other_owner_are_isolated(predictive):
    settings, accounts, _, events = predictive
    first, second = accounts
    assert view(first)['availability'] == view(second)['availability'] == 'no_data'
    service, owner, _ = first
    assert service.insights(second[1], service.catalog['device_id']) is None
    assert service.update_predictive_rules(second[1], service.catalog['device_id'], DEFAULT_RULES) is None
    changed = {**DEFAULT_RULES, 'open_count': 1}
    assert service.update_predictive_rules(owner, service.catalog['device_id'], changed) == changed
    deliver(events(0))
    deliver(events(0, account=1))
    assert len(view(first)['active_alerts']) == 1
    assert view(second)['active_alerts'] == []
    assert view(second)['rules'] == DEFAULT_RULES
    with connect(settings) as connection:
        connection.execute("UPDATE users SET role='viewer' WHERE id=%s", (owner,))
    with pytest.raises(PermissionError):
        service.update_predictive_rules(owner, service.catalog['device_id'], DEFAULT_RULES)


def test_model_change_and_stale_gap_reset_accumulated_critical_predictions(predictive):
    settings, accounts, _, events = predictive
    for offset in range(2):
        deliver(events(offset))
    service, owner, original_model = accounts[0]
    with connect(settings) as connection:
        other_model = connection.execute('INSERT INTO models(owner_user_id,dataset_id,training_job_id,'
                                         'model_version,features_version,artifact_key) '
                                         "SELECT owner_user_id,dataset_id,training_job_id,'demo-v2',features_version,'test/model-v2' "
                                         'FROM models WHERE id=%s RETURNING id', (original_model,)).fetchone()[0]
    bundle = events(2)
    bundle[3]['data'].update(model_id=str(other_model), model_version='demo-v2')
    deliver(bundle)
    assert view(accounts[0])['active_alerts'] == []
    for offset in (3, 35, 36):
        bundle = events(offset)
        bundle[3]['data'].update(model_id=str(other_model), model_version='demo-v2')
        deliver(bundle)
    assert view(accounts[0])['active_alerts'] == []
    bundle = events(37)
    bundle[3]['data'].update(model_id=str(other_model), model_version='demo-v2')
    deliver(bundle)
    assert len(view(accounts[0])['active_alerts']) == 1


def test_alert_audit_and_prediction_ack_commit_atomically(predictive, monkeypatch):
    settings, accounts, _, events = predictive
    for offset in range(2):
        deliver(events(offset))
    bundle = events(2)
    deliver(bundle, (1, 2))
    service = bundle[0]
    original_audit = service._audit

    def fail_audit(cursor, kind, details, actor=None):
        if kind == 'predictive_alert_opened':
            raise RuntimeError('simulated audit storage failure')
        original_audit(cursor, kind, details, actor)

    monkeypatch.setattr(service, '_audit', fail_audit)
    with pytest.raises(RuntimeError, match='audit storage'):
        deliver(bundle, (3,))
    with connect(settings) as connection:
        assert connection.execute('SELECT count(*) FROM predictive_alerts').fetchone() == (0,)
        assert connection.execute('SELECT count(*) FROM aiot_inbox WHERE event_id=%s',
                                  (bundle[3]['event_id'],)).fetchone() == (0,)
    monkeypatch.setattr(service, '_audit', original_audit)
    deliver(bundle, (3,))
    assert len(view(accounts[0])['active_alerts']) == 1


def test_equal_timestamp_latest_source_does_not_inherit_other_source_trend(predictive):
    _, accounts, _, events = predictive
    deliver(events(0, 70, 100))
    deliver(events(1, 60, 90))
    assert view(accounts[0])['trend'] == 'declining'
    bundle = events(1, 90, 110)
    source_id = 'ffffffff-ffff-4fff-bfff-ffffffffffff'
    bundle[1]['event_id'] = bundle[1]['correlation_id'] = source_id
    for event in bundle[2:]:
        event['correlation_id'] = event['data']['source_event_id'] = source_id
    deliver(bundle)
    assert view(accounts[0])['availability'] == 'available'
    assert view(accounts[0])['trend'] == 'unknown'
