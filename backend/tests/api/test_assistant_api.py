"""Assistant boundary: authenticated read-only requests, bounded input and SSE."""
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.api.auth import AuthService
from backend.app.api.app import create_app
from backend.app.api.llm import create_llm_router
from backend.app.services.assistant import AssistantError
from backend.tests.api.test_runtime_lifecycle import settings


@pytest.fixture
def api():
    auth = AuthService(settings())
    owner = uuid4()
    auth.current_user = Mock(return_value=owner)
    auth.session_for_token = Mock(return_value=Mock(user_id=owner))
    assistant = Mock()
    assistant.close = AsyncMock()

    async def events(*_):
        yield 'event: delta\ndata: {"text":"Olá"}\n\n'
        yield 'event: done\ndata: {}\n\n'

    assistant.events = events
    app = create_app(repository=Mock(), readiness_check=lambda: True)
    app.include_router(create_llm_router(auth, Mock(), assistant))
    auth.install_exception_handlers(app)
    return TestClient(app), auth, assistant, owner


def test_stream_is_authenticated_incremental_and_uncached(api):
    client, _, service, owner = api
    response = client.post('/api/v3/llm/ask', json={'question': 'Como está meu equipamento?'},
                           headers={'Authorization': 'Bearer private-token'})
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('text/event-stream')
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['x-accel-buffering'] == 'no'
    assert 'event: delta' in response.text and 'event: done' in response.text
    service.open.assert_called_once_with(owner, 'Como está meu equipamento?')
    operation = client.get('/openapi.json').json()['paths']['/api/v3/llm/ask']['post']
    assert 'text/event-stream' in operation['responses']['200']['content']


@pytest.mark.parametrize('question', ['', '   ', 'x' * 401, '🧊' * 100, 42, None])
def test_rejects_invalid_questions(api, question):
    client, _, service, _ = api
    response = client.post('/api/v3/llm/ask', json={'question': question},
                           headers={'Authorization': 'Bearer t'})
    assert response.status_code == 422
    service.open.assert_not_called()


def test_caller_cannot_choose_other_owner_context_or_tools(api):
    client, _, service, _ = api
    for key in ('owner_user_id', 'context', 'tools', 'messages'):
        response = client.post('/api/v3/llm/ask', json={'question': 'show data', key: str(uuid4())},
                               headers={'Authorization': 'Bearer t'})
        assert response.status_code == 422
    service.open.assert_not_called()


@pytest.mark.parametrize('question', ['x' * 256, '🧊' * 64])
def test_utf8_byte_limit_accepts_its_boundary(api, question):
    client, _, _, _ = api
    assert client.post('/api/v3/llm/ask', json={'question': question},
                       headers={'Authorization': 'Bearer t'}).status_code == 200


def test_missing_and_revoked_session_cannot_generate(api):
    client, auth, service, _ = api
    assert client.post('/api/v3/llm/ask', json={'question': 'oi'}).status_code == 401
    auth.session_for_token.return_value = None
    assert client.post('/api/v3/llm/ask', json={'question': 'oi'},
                       headers={'Authorization': 'Bearer revoked'}).status_code == 401
    service.open.assert_not_called()


@pytest.mark.parametrize('code,status', [
    ('LLM_UNAVAILABLE', 503), ('LLM_DISABLED', 503), ('LLM_BUSY', 503),
    ('LLM_NOT_READY', 503), ('RATE_LIMITED', 429),
])
def test_preflight_failures_have_safe_errors_and_retry_header(api, code, status):
    client, _, service, _ = api
    service.open.side_effect = AssistantError(code, status)
    response = client.post('/api/v3/llm/ask', json={'question': 'oi'},
                           headers={'Authorization': 'Bearer t'})
    assert response.status_code == status
    assert response.json()['error']['code'] == code
    if status == 429:
        assert response.headers['retry-after'] == '60'
