from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend.app.api.aiot import install_aiot
from backend.tests.api.test_events_api import make_client, wait_subscribed
from backend.app.api.events import EventHub


def client_v3():
    client, legacy, auth, state = make_client()
    catalog = Mock()
    catalog.device_for_user.side_effect = lambda user, device: (
        {'id': str(uuid4()), 'environment_id': str(uuid4()), 'is_active': True}
        if user == state['owner'] and device == 'owned' else None)
    catalog.thresholds_for_environment.return_value = {'min_c': 2.0, 'max_c': 8.0, 'attention_margin_c': 0.5}
    service, hub = Mock(), EventHub()
    service.snapshot.return_value = {'telemetry': None, 'freshness': {'state': 'no_data'}}
    service.history.return_value = []
    install_aiot(client.app, service, hub, auth, catalog)
    return client, service, hub, legacy, state


def test_v3_rest_requires_auth_and_propagates_owner_to_recovery():
    client, service, *_rest, state = client_v3()
    assert client.get('/api/v3/monitoring/summary?device_id=owned').status_code == 401
    headers = {'Authorization': 'Bearer owner'}
    result = client.get('/api/v3/monitoring/summary?device_id=owned', headers=headers)
    assert result.status_code == 200
    assert result.json()['meta']['schema_version'] == 3
    assert result.json()['data']['freshness']['state'] == 'no_data'
    service.snapshot.assert_called_once_with(state['owner'], 'owned')
    service.snapshot.return_value = None
    assert client.get('/api/v3/monitoring/summary?device_id=other', headers=headers).status_code == 404
    assert client.get('/api/v3/readings?device_id=owned&limit=1001', headers=headers).status_code == 422
    assert client.get('/api/v3/readings?device_id=owned&limit=10', headers=headers).json()['data'] == []
    from unittest.mock import ANY
    service.history.assert_called_once_with(state['owner'], 'owned', limit=10, start=ANY, end=ANY)


def test_v3_led_requires_operator_and_strict_boolean():
    from dataclasses import replace
    client, service, *_rest, state = client_v3()
    endpoint = '/api/v3/devices/owned/led/commands'
    headers = {'Authorization': 'Bearer owner'}
    assert client.post(endpoint, headers=headers, json={'desired_state': True}).status_code == 403
    state['principal'] = replace(state['principal'], role='operator')
    service.request_led.return_value = {'type': 'command_status', 'data': {'status': 'pending'}}
    for payload in ({'desired_state': 1}, {'desired_state': 'true'}, {'desired_state': True, 'actuator': 'buzzer'}):
        assert client.post(endpoint, headers=headers, json=payload).status_code == 422
    result = client.post(endpoint, headers=headers, json={'desired_state': True})
    assert result.status_code == 200
    assert result.json()['data']['data']['status'] == 'pending'
    service.request_led.assert_called_once_with(state['owner'], 'owned', True)
    service.request_led.side_effect = PermissionError('FORBIDDEN')
    assert client.post(endpoint, headers=headers, json={'desired_state': False}).status_code == 403


def test_v3_stream_is_separate_and_rechecks_session():
    client, service, hub, legacy, state = client_v3()
    with client.websocket_connect('/api/v3/events?device_id=owned') as ws:
        ws.send_json({'ticket': 'one-use-ticket'})
        wait_subscribed(hub)
        assert not legacy._subscribers
        event = {'schema_version': 3, 'type': 'telemetry', 'device_id': 'owned', 'data': {}}
        hub.publish('someone-else', {'secret': True})
        hub.publish('owned', event)
        assert ws.receive_json() == event
        state['principal'] = None
        with pytest.raises(WebSocketDisconnect) as error:
            ws.receive_json()
        assert error.value.code == 4401
    assert not hub._subscribers
