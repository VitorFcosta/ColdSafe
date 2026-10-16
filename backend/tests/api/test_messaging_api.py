from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from backend.app.api.auth import AuthService
from backend.app.api.messaging import create_messaging_router
from backend.app.security.tokens import SessionPrincipal
from backend.tests.api.test_runtime_lifecycle import settings
from backend.tests.services.test_messaging import service


def client_for(role):
    auth = AuthService(settings())
    auth.session_for_token = Mock(return_value=SessionPrincipal(
        uuid4(), uuid4(), 'admin@example.test', role, datetime.now(UTC) + timedelta(hours=1),
    ) if role else None)
    monitor, transport = service()
    application = FastAPI()
    application.include_router(create_messaging_router(auth, monitor))
    auth.install_exception_handlers(application)
    return TestClient(application), transport


@pytest.mark.parametrize('role,status', [(None, 401), ('viewer', 403), ('operator', 403)])
def test_only_admin_can_access_infrastructure_metrics(role, status):
    client, transport = client_for(role)
    response = client.get('/api/v3/messaging', headers={'Authorization': 'Bearer test'} if role else {})
    assert response.status_code == status
    transport.open.assert_not_called()


def test_admin_receives_only_aggregate_metrics_without_browser_cache():
    client, _ = client_for('admin')
    response = client.get('/api/v3/messaging', headers={'Authorization': 'Bearer test'})
    assert response.status_code == 200
    assert response.headers['Cache-Control'] == 'no-store'
    assert response.json()['success'] is True
    assert 'sampled_at' in response.json()['data']
    assert len(response.json()['data']['queues']) == 9
    assert 'private' not in response.text
    assert set(response.json()['data']['queues'][0]) == {
        'name', 'messages', 'messages_ready', 'messages_unacknowledged',
        'consumers', 'publish_rate', 'deliver_rate',
    }


def test_broker_failure_returns_sanitized_503():
    client, transport = client_for('admin')
    transport.open.side_effect = TimeoutError('private broker connection and credentials')
    response = client.get('/api/v3/messaging', headers={'Authorization': 'Bearer test'})
    assert response.status_code == 503
    assert response.headers['Cache-Control'] == 'no-store'
    assert response.json()['error']['code'] == 'DEPENDENCY_UNAVAILABLE'
    assert 'private' not in response.text


def test_runtime_installs_metrics_only_when_monitor_password_is_configured():
    from backend.app.runtime import build_runtime_app
    from pydantic import SecretStr
    with patch('backend.app.runtime.MqttSubscriber'), patch('backend.app.runtime.create_influx_repository'):
        assert '/api/v3/messaging' not in build_runtime_app(settings()).openapi()['paths']
        configured = settings().model_copy(update={'rabbitmq_monitor_password': SecretStr('private-monitor')})
        assert '/api/v3/messaging' in build_runtime_app(configured).openapi()['paths']
