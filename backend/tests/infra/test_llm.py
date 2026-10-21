"""Local-only Ollama transport and bounded preload/unload protocol."""
import json
from io import BytesIO
from unittest.mock import Mock
from urllib.error import HTTPError, URLError

import pytest
from pydantic import ValidationError

from backend.app.services.llm import MODEL, OllamaClient, OllamaUnavailable
from backend.tests.api.test_runtime_lifecycle import settings


def resident(**values):
    return {'name': MODEL, 'size_vram': 0, 'context_length': 1024} | values


@pytest.mark.parametrize('url', [
    'https://ollama.com', 'http://example.com', 'http://ollama.evil.test',
    'http://user:pass@ollama:11434', 'http://ollama:11434/path',
    'http://ollama:11434?token=private', 'http://ollama:11434#fragment',
    'http://ollama:bogus', 'http://ollama:0', 'http://ollama:65536',
])
def test_settings_reject_external_or_ambiguous_ollama_url(url):
    with pytest.raises(ValidationError):
        settings().__class__(**(settings().model_dump() | {'ollama_url': url}))


def test_optional_settings_preserve_existing_runtime():
    assert settings().ollama_url is None


def test_preload_uses_empty_local_prompt_bounded_context_and_cpu():
    client = OllamaClient('http://ollama:11434')
    client.request = Mock(side_effect=[{'done': True}, {'models': [resident()]}])
    client.preload()
    assert client.request.call_args_list[0].args == ('/api/generate', {
        'model': MODEL, 'prompt': '', 'stream': False, 'keep_alive': -1,
        'options': {'num_ctx': 1024, 'num_gpu': 0, 'num_thread': 2},
    })
    assert client.request.call_args_list[0].kwargs['timeout'] == 180


@pytest.mark.parametrize('models', [[resident(size_vram=1)], [resident(context_length=2048)], []])
def test_preload_requires_confirmed_cpu_runner_and_context(models):
    client = OllamaClient('http://ollama:11434')
    client.request = Mock(side_effect=[{'done': True}, {'models': models}])
    with pytest.raises(OllamaUnavailable):
        client.preload()


def test_unload_verifies_no_model_remains_before_returning():
    client = OllamaClient('http://ollama:11434')
    client.request = Mock(side_effect=[{'models': [resident()]}, {'done': True, 'done_reason': 'unload'}, {'models': []}])
    client.unload()
    assert client.request.call_args_list[1].args == ('/api/generate', {
        'model': MODEL, 'prompt': '', 'stream': False, 'keep_alive': 0,
    })
    assert client.request.call_args_list[-1].args == ('/api/ps',)


def test_unload_is_noop_when_model_is_absent():
    client = OllamaClient('http://ollama:11434')
    client.request = Mock(return_value={'models': []})
    client.unload()
    client.request.assert_called_once_with('/api/ps')


def test_unload_refuses_success_while_runner_remains():
    client = OllamaClient('http://ollama:11434')
    client.request = Mock(side_effect=[{'models': [resident()]}, {'done': True, 'done_reason': 'unload'}, {'models': [resident()]}])
    with pytest.raises(OllamaUnavailable):
        client.unload()


@pytest.mark.parametrize('payload', [{}, {'models': None}, {'models': [None]}, {'models': [{'name': ''}]}])
def test_invalid_server_state_fails_closed(payload):
    client = OllamaClient('http://ollama:11434')
    client.request = Mock(return_value=payload)
    with pytest.raises(OllamaUnavailable):
        client.loaded()


def test_transport_disables_proxies_and_redirects_and_sanitizes_errors(monkeypatch):
    from backend.app.services import llm
    opener = Mock()
    factory = Mock(return_value=opener)
    monkeypatch.setattr(llm, 'build_opener', factory)
    client = OllamaClient('http://ollama:11434')
    assert factory.call_args.args[0].proxies == {}
    response = Mock()
    response.__enter__ = Mock(return_value=BytesIO(b'{"models":[]}'))
    response.__exit__ = Mock(return_value=False)
    opener.open.return_value = response
    assert client.loaded() == []
    assert opener.open.call_args.kwargs['timeout'] == 2
    for error in [URLError('private token'), HTTPError('private', 302, 'redirect', {}, None)]:
        opener.open.side_effect = error
        with pytest.raises(OllamaUnavailable) as caught:
            client.loaded()
        assert 'private' not in str(caught.value)
    with pytest.raises(HTTPError):
        factory.call_args.args[1].redirect_request(None, None, 302, '', {}, 'http://external')


def test_settings_accepts_private_service_or_loopback():
    for url in ('http://ollama:11434', 'http://127.0.0.1:11434/', 'http://[::1]:11434'):
        assert settings().__class__(**(settings().model_dump() | {'ollama_url': url})).ollama_url == url.rstrip('/')


def test_transport_rejects_invalid_and_oversized_json(monkeypatch):
    from backend.app.services import llm
    opener = Mock()
    monkeypatch.setattr(llm, 'build_opener', Mock(return_value=opener))
    client = OllamaClient('http://ollama:11434')
    for body in (b'not json', b'[]', b'{"error":"private details"}', b'x' * 65_537):
        response = Mock()
        response.__enter__ = Mock(return_value=BytesIO(body))
        response.__exit__ = Mock(return_value=False)
        opener.open.return_value = response
        with pytest.raises(OllamaUnavailable):
            client.loaded()


def test_transport_posts_json_and_uses_explicit_timeout(monkeypatch):
    from backend.app.services import llm
    opener = Mock()
    response = Mock()
    response.__enter__ = Mock(return_value=BytesIO(b'{"done":true}'))
    response.__exit__ = Mock(return_value=False)
    opener.open.return_value = response
    monkeypatch.setattr(llm, 'build_opener', Mock(return_value=opener))
    OllamaClient('http://ollama:11434').request('/api/generate', {'model': MODEL}, timeout=180)
    request = opener.open.call_args.args[0]
    assert request.full_url == 'http://ollama:11434/api/generate'
    assert json.loads(request.data) == {'model': MODEL}
    assert opener.open.call_args.kwargs['timeout'] == 180


def test_inventory_rejects_invalid_payloads():
    client = OllamaClient('http://ollama:11434')
    for payload in ({}, {'models': [None]}):
        client.request = Mock(return_value=payload)
        with pytest.raises(OllamaUnavailable):
            client.installed()
    client.request = Mock(return_value={'models': [{'name': MODEL}]})
    assert client.installed()


def test_unload_requires_explicit_acknowledgment():
    client = OllamaClient('http://ollama:11434')
    client.request = Mock(side_effect=[{'models': [resident()]}, {'done': True}])
    with pytest.raises(OllamaUnavailable):
        client.unload()
