from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from backend.app.api.auth import AuthService
from backend.app.api.llm import create_llm_router
from backend.app.security.tokens import SessionPrincipal
from backend.app.services.llm import MODEL
from backend.tests.api.test_runtime_lifecycle import settings


@pytest.fixture
def api():
    auth = AuthService(settings())
    principal = SessionPrincipal(uuid4(), uuid4(), 'viewer@example.invalid', 'viewer',
                                 datetime.now(UTC) + timedelta(hours=1))
    auth.session_for_token = Mock(return_value=principal)
    service = Mock()
    service.status.return_value = {'state': 'paused', 'model': MODEL}
    app = FastAPI()
    app.include_router(create_llm_router(auth, service))
    auth.install_exception_handlers(app)
    return TestClient(app), auth, service


def test_status_is_private_uncached_and_contains_no_job_metadata(api):
    client, _, service = api
    response = client.get('/api/v3/llm/status', headers={'Authorization': 'Bearer test'})
    assert response.status_code == 200
    assert response.headers['Cache-Control'] == 'no-store'
    assert response.json() == {'success': True, 'data': {'state': 'paused', 'model': MODEL}, 'meta': {'schema_version': 3}}
    service.status.assert_called_once_with()


@pytest.mark.parametrize('suffix', ['', '?token=test'])
def test_status_requires_valid_bearer(api, suffix):
    client, _, service = api
    assert client.get('/api/v3/llm/status' + suffix).status_code == 401
    service.status.assert_not_called()


def test_revoked_session_cannot_read_global_state(api):
    client, auth, service = api
    auth.session_for_token.return_value = None
    assert client.get('/api/v3/llm/status', headers={'Authorization': 'Bearer test'}).status_code == 401
    service.status.assert_not_called()
