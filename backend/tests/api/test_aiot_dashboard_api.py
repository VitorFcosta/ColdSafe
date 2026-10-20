"""Dashboard v3 recovery keeps durable events and bounded private queries."""
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
from uuid import uuid4

import pytest

from backend.tests.api.test_aiot_api import client_v3
from backend.tests.services.test_aiot_events import service
from simulator.model import utc


HEADERS = {'Authorization': 'Bearer owner'}
START = datetime(2026, 10, 15, tzinfo=UTC)
END = START + timedelta(hours=1)


@pytest.mark.parametrize(('period', 'duration'), [('15m', 900), ('1h', 3600), ('6h', 21600), ('24h', 86400)])
def test_readings_period_filters_service_and_reports_range(monkeypatch, period, duration):
    monkeypatch.setattr('backend.app.api.aiot.utc_now', lambda: END, raising=False)
    client, backend, *_rest, state = client_v3()
    backend.history.return_value = [{'telemetry': {'event_id': 'source'}, 'prediction': None, 'persistence': 'pending'}]
    response = client.get('/api/v3/readings', params={'device_id': 'owned', 'period': period, 'limit': 7}, headers=HEADERS)
    assert response.status_code == 200
    backend.history.assert_called_once_with(state['owner'], 'owned', limit=7,
                                            start=END - timedelta(seconds=duration), end=END)
    body = response.json()
    assert body['data'] == backend.history.return_value
    assert body['meta'] == {'schema_version': 3, 'device_id': 'owned', 'limit': 7, 'count': 1,
                            'thresholds': {'min_c': 2.0, 'max_c': 8.0, 'attention_margin_c': 0.5},
                            'start': utc(END - timedelta(seconds=duration)), 'end': utc(END)}


def test_readings_defaults_to_one_hour_and_explicit_utc_interval_overrides_period(monkeypatch):
    monkeypatch.setattr('backend.app.api.aiot.utc_now', lambda: END, raising=False)
    client, backend, *_rest, state = client_v3()
    client.get('/api/v3/readings', params={'device_id': 'owned'}, headers=HEADERS)
    backend.history.assert_called_once_with(state['owner'], 'owned', limit=300, start=START, end=END)
    backend.history.reset_mock()
    response = client.get('/api/v3/readings', params={'device_id': 'owned', 'period': '24h',
                           'start': START.isoformat(), 'end': END.isoformat()}, headers=HEADERS)
    assert response.status_code == 200
    backend.history.assert_called_once_with(state['owner'], 'owned', limit=300, start=START, end=END)


@pytest.mark.parametrize('path', ['/api/v3/readings', '/api/v3/alerts'])
@pytest.mark.parametrize('query', [
    {'start': START.isoformat()}, {'end': END.isoformat()},
    {'start': '2026-10-15T00:00:00', 'end': END.isoformat()},
    {'start': START.isoformat(), 'end': '2026-10-15T01:00:00'},
    {'start': END.isoformat(), 'end': START.isoformat()},
    {'start': START.isoformat(), 'end': START.isoformat()}, {'limit': 0}, {'limit': 1001},
])
def test_reading_and_alert_queries_reject_invalid_ranges_and_limits(path, query):
    client, backend, *_rest = client_v3()
    response = client.get(path, params={'device_id': 'owned', **query}, headers=HEADERS)
    assert response.status_code == 422
    assert response.json()['error']['code'] == 'VALIDATION_ERROR'
    backend.history.assert_not_called()
    backend.list_alerts.assert_not_called()


def test_readings_rejects_unknown_period_and_preserves_missing_device_error():
    client, backend, *_rest = client_v3()
    assert client.get('/api/v3/readings?device_id=owned&period=7d', headers=HEADERS).status_code == 422
    backend.history.return_value = None
    assert client.get('/api/v3/readings?device_id=other', headers=HEADERS).status_code == 404


def test_ranges_normalize_explicit_offsets_to_utc():
    client, backend, *_rest, state = client_v3()
    response = client.get('/api/v3/readings', params={'device_id': 'owned',
                          'start': '2026-10-14T21:00:00-03:00', 'end': '2026-10-14T22:00:00-03:00'},
                          headers=HEADERS)
    assert response.status_code == 200
    backend.history.assert_called_once_with(state['owner'], 'owned', limit=300, start=START, end=END)
    assert response.json()['meta']['start'] == utc(START)


def test_alerts_reports_intervals_with_private_range_metadata():
    client, backend, *_rest, state = client_v3()
    alerts = [{'alert_id': str(uuid4()), 'device_id': 'owned', 'kind': 'temperature_high',
               'opened_at': START.isoformat(), 'closed_at': None, 'status': 'open'}]
    backend.list_alerts.return_value = alerts
    params = {'device_id': 'owned', 'start': START.isoformat(), 'end': END.isoformat(), 'limit': 10}
    assert client.get('/api/v3/alerts', params=params).status_code == 401
    response = client.get('/api/v3/alerts', params=params, headers=HEADERS)
    assert response.status_code == 200
    assert response.json() == {'success': True, 'data': {'alerts': alerts}, 'meta': {
        'schema_version': 3, **params, 'start': utc(START), 'end': utc(END), 'limit': 10, 'count': 1}}
    backend.list_alerts.assert_called_once_with(state['owner'], 'owned', start=START, end=END, limit=10)
    backend.list_alerts.return_value = None
    assert client.get('/api/v3/alerts?device_id=other', headers=HEADERS).status_code == 404


def test_command_lookup_returns_exact_durable_status_for_owner_and_validates_uuid():
    client, backend, *_rest, state = client_v3()
    identifier = uuid4()
    envelope = {'type': 'command_status', 'event_id': str(uuid4()), 'data': {
        'command_id': str(identifier), 'status': 'unconfirmed', 'confirmed_state': None}}
    backend.get_command_for_user.return_value = envelope
    path = '/api/v3/commands/' + str(identifier)
    assert client.get(path).status_code == 401
    response = client.get(path, headers=HEADERS)
    assert response.status_code == 200
    assert response.json()['data'] == envelope
    backend.get_command_for_user.assert_called_once_with(state['owner'], identifier)
    assert client.get('/api/v3/commands/not-a-uuid', headers=HEADERS).status_code == 422
    backend.get_command_for_user.return_value = None
    assert client.get(path, headers=HEADERS).status_code == 404


def dashboard_cursor(service, monkeypatch):
    cursor = Mock()
    monkeypatch.setattr(service, '_cursor', lambda: nullcontext(cursor))
    monkeypatch.setattr(service, '_scope', Mock(return_value=True))
    return cursor


@pytest.mark.parametrize('has_telemetry', [False, True])
def test_snapshot_includes_private_inventory_with_or_without_telemetry(service, monkeypatch, has_telemetry):
    cursor = dashboard_cursor(service, monkeypatch)
    monkeypatch.setattr(service, '_expire', Mock())
    telemetry = {'event_id': str(uuid4()), 'received_at': utc(START)} if has_telemetry else None
    monkeypatch.setattr(service, '_latest', Mock(return_value=telemetry))
    monkeypatch.setattr(service, '_now', lambda: START)
    metadata = {'id': service.catalog['environment_id'], 'name': 'Private cold room',
                'min_c': 1.0, 'max_c': 7.0, 'attention_margin_c': 0.7}
    cursor.execute.return_value.fetchone.return_value = metadata
    cursor.execute.return_value.fetchall.return_value = []
    snapshot = service.snapshot(uuid4(), service.catalog['device_id'])
    assert snapshot['freshness']['state'] == ('fresh' if has_telemetry else 'no_data')
    assert snapshot['telemetry'] == telemetry
    assert snapshot['environment'] == {'id': metadata['id'], 'name': metadata['name']}
    assert snapshot['device'] == {'id': service.catalog['device_id']}
    assert snapshot['thresholds'] == {key: metadata[key] for key in ('min_c', 'max_c', 'attention_margin_c')}
    assert snapshot['inventory'] == {key: service.catalog[key] for key in
                                     ('equipment_id', 'sensors', 'actuators')}
    snapshot['inventory']['sensors']['humidity'] = 'client-side-change'
    assert service.catalog['sensors']['humidity'] != 'client-side-change'


def test_snapshot_rejects_wrong_owner_or_device_before_inventory_queries(service, monkeypatch):
    cursor = dashboard_cursor(service, monkeypatch)
    service._scope.return_value = False
    assert service.snapshot(uuid4(), service.catalog['device_id']) is None
    cursor.execute.assert_not_called()
    service._scope.reset_mock()
    assert service.snapshot(uuid4(), 'other-device') is None
    service._scope.assert_not_called()
    cursor.execute.assert_not_called()


def test_summary_http_returns_inventory_only_to_authenticated_owner(service, monkeypatch):
    from backend.app.api.aiot import install_aiot
    from backend.app.api.events import EventHub
    from backend.tests.api.test_events_api import make_client

    client, _hub, auth, state = make_client()
    cursor = dashboard_cursor(service, monkeypatch)
    service._scope.side_effect = lambda _cursor, user: user == state['owner']
    monkeypatch.setattr(service, '_expire', Mock())
    monkeypatch.setattr(service, '_latest', Mock(return_value=None))
    cursor.execute.return_value.fetchone.return_value = {
        'id': service.catalog['environment_id'], 'name': 'Private cold room',
        'min_c': 2.0, 'max_c': 8.0, 'attention_margin_c': 0.5}
    cursor.execute.return_value.fetchall.return_value = []
    install_aiot(client.app, service, EventHub(), auth, Mock())
    endpoint = '/api/v3/monitoring/summary'
    params = {'device_id': service.catalog['device_id']}
    assert client.get(endpoint, params=params).status_code == 401
    response = client.get(endpoint, params=params, headers=HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body['meta'] == {'schema_version': 3}
    assert body['data']['telemetry'] is None
    assert body['data']['inventory'] == {key: service.catalog[key] for key in
                                       ('equipment_id', 'sensors', 'actuators')}
    for query, headers in ((params, {'Authorization': 'Bearer stranger'}),
                           ({'device_id': 'other-device'}, HEADERS)):
        response = client.get(endpoint, params=query, headers=headers)
        assert response.status_code == 404
        assert 'inventory' not in response.json()


def test_service_history_keeps_legacy_call_and_uses_half_open_range(service, monkeypatch):
    cursor = dashboard_cursor(service, monkeypatch)
    cursor.execute.return_value.fetchall.return_value = []
    owner, device = uuid4(), service.catalog['device_id']
    assert service.history(owner, device, limit=10) == []
    assert service.history(owner, device, limit=10, start=START, end=END) == []
    sql, params = cursor.execute.call_args.args
    assert 'received_at >= %s' in sql and 'received_at < %s' in sql
    assert START in params and END in params


def test_service_command_lookup_expires_before_reading_and_checks_scope(service, monkeypatch):
    cursor = dashboard_cursor(service, monkeypatch)
    expire = Mock()
    monkeypatch.setattr(service, '_expire', expire)
    identifier = uuid4()
    envelope = {'type': 'command_status', 'data': {'status': 'unconfirmed'}}
    cursor.execute.return_value.fetchone.side_effect = lambda: {'status_envelope': envelope} if expire.called else None
    assert service.get_command_for_user(uuid4(), identifier) == envelope
    expire.assert_called_once_with(cursor)
    sql, params = cursor.execute.call_args.args
    assert 'device_id=%s' in sql and identifier in params
    service._scope.return_value = False
    cursor.reset_mock()
    expire.reset_mock()
    assert service.get_command_for_user(uuid4(), identifier) is None
    expire.assert_not_called()
    cursor.execute.assert_not_called()


def test_service_alerts_uses_overlapping_intervals_and_catalog_scope(service, monkeypatch):
    cursor = dashboard_cursor(service, monkeypatch)
    identifier = uuid4()
    cursor.execute.return_value.fetchall.return_value = [
        {'alert_id': identifier, 'kind': 'temperature_low', 'opened_at': START, 'closed_at': END}]
    result = service.list_alerts(uuid4(), service.catalog['device_id'], start=START, end=END, limit=12)
    assert result == [{'alert_id': str(identifier), 'device_id': service.catalog['device_id'],
                       'kind': 'temperature_low', 'opened_at': START, 'closed_at': END, 'status': 'closed'}]
    sql, params = cursor.execute.call_args.args
    assert 'opened_at < %s' in sql and 'closed_at > %s' in sql
    assert service.catalog['device_record_id'] in params
    service._scope.return_value = False
    cursor.reset_mock()
    assert service.list_alerts(uuid4(), service.catalog['device_id'], start=START, end=END, limit=12) is None
    cursor.execute.assert_not_called()


@pytest.mark.parametrize(('start', 'end', 'limit'), [
    (START, None, 10), (None, END, 10), (END, START, 10), (START, START, 10),
    (START.replace(tzinfo=None), END, 10), (START, END.replace(tzinfo=None), 10),
    (None, None, 0), (None, None, 1001), (None, None, True),
])
def test_service_query_validation_rejects_invalid_arguments_before_database(service, monkeypatch, start, end, limit):
    cursor = dashboard_cursor(service, monkeypatch)
    for query in (service.history, service.list_alerts):
        with pytest.raises(ValueError):
            query(uuid4(), service.catalog['device_id'], start=start, end=end, limit=limit)
    cursor.execute.assert_not_called()
