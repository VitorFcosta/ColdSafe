"""Real PostgreSQL + HTTP/SSE/disconnect; Ollama is an explicit protocol double.

No language-model quality or physical telemetry claims are made by these tests.
"""
import asyncio
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread
import time
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
import httpx
import pytest
import uvicorn

from backend.app.api.auth import AuthService
from backend.app.api.llm import create_llm_router
from backend.app.repositories.postgres import connect
from backend.app.services.assistant import AssistantService
from backend.app.services.llm import MODEL, LlmService
from backend.tests.infra.test_dashboard_integration import free_port
from backend.tests.integration.test_aiot_migrations_integration import database
from backend.tests.integration.test_jobs_integration import jobs

pytestmark = pytest.mark.integration


def eventually(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.02)
    pytest.fail('Expected state was not observed before timeout')


@pytest.fixture
def runtime(jobs):
    state = SimpleNamespace(entered=Event(), release=Event(), unloaded=Event(),
                            loaded=True, failure=None, payload=None)

    class Ollama(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *_args):
            pass

        def reply(self, payload):
            raw = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            assert self.path == '/api/ps'
            self.reply({'models': [{'name': MODEL, 'size_vram': 0, 'context_length': 1024}]
                        if state.loaded else []})

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if self.path == '/api/generate':
                assert payload['keep_alive'] == 0
                state.loaded = False
                state.unloaded.set()
                self.reply({'done': True, 'done_reason': 'unload'})
                state.release.set()
                return
            assert self.path == '/api/chat'
            state.payload = payload
            state.entered.set()
            if state.failure == 'http':
                self.send_response(503)
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
            self.send_response(200)
            self.send_header('Content-Type', 'application/x-ndjson')
            self.send_header('Connection', 'close')
            self.end_headers()
            self.close_connection = True
            try:
                if state.failure == 'protocol':
                    self.wfile.write(b'{"error":"private upstream credentials"}\n')
                    self.wfile.flush()
                    return
                if state.failure != 'timeout':
                    self.wfile.write((json.dumps({'model': MODEL, 'done': False, 'message': {
                        'role': 'assistant', 'content': 'Primeira parte'}}) + '\n').encode())
                    self.wfile.flush()
                assert state.release.wait(8)
                self.wfile.write((json.dumps({'model': MODEL, 'done': True, 'message': {
                    'role': 'assistant', 'content': ''}}) + '\n').encode())
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass

    upstream = ThreadingHTTPServer(('127.0.0.1', 0), Ollama)
    upstream.daemon_threads = True
    upstream_thread = Thread(target=upstream.serve_forever, daemon=True)
    upstream_thread.start()
    config = jobs[1].model_copy(update={'ollama_url': f'http://127.0.0.1:{upstream.server_port}'})
    auth = AuthService(config)
    email = f'{uuid4()}@example.invalid'
    owner = auth.register(email, 'disposable-local-password')
    token, _ = auth.login(email, 'disposable-local-password')
    assistant = AssistantService(config)
    app = FastAPI()
    app.include_router(create_llm_router(auth, LlmService(config), assistant))
    auth.install_exception_handlers(app)
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port,
                                          log_level='critical', ws='none'))
    thread = Thread(target=server.run, daemon=True)
    thread.start()
    eventually(lambda: server.started)
    try:
        with httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=5,
                          headers={'Authorization': f'Bearer {token}'}, trust_env=False) as client:
            yield SimpleNamespace(config=config, owner=owner, client=client, state=state)
    finally:
        state.release.set()
        server.should_exit = True
        thread.join(5)
        upstream.shutdown()
        upstream.server_close()
        upstream_thread.join(5)
        assert not thread.is_alive() and not upstream_thread.is_alive()


def outcome(runtime):
    with connect(runtime.config) as connection:
        return connection.execute("SELECT details->>'outcome' FROM audit_events "
                                  "WHERE actor_user_id=%s AND event_type='assistant.finished' "
                                  'ORDER BY occurred_at DESC LIMIT 1', (runtime.owner,)).fetchone()


def assert_released(runtime, expected):
    eventually(lambda: outcome(runtime) == (expected,))
    with connect(runtime.config) as connection:
        assert connection.execute('SELECT count(*) FROM llm_memory_guard').fetchone() == (0,)
        from backend.app.services.jobs import HEAVY_JOB_LOCK
        assert connection.execute('SELECT pg_try_advisory_lock(%s)', (HEAVY_JOB_LOCK,)).fetchone()[0]


def test_real_http_sse_delivers_first_delta_before_upstream_finishes(runtime):
    with runtime.client.stream('POST', '/api/v3/llm/ask', json={'question': 'Qual o estado?'}) as response:
        assert response.status_code == 200
        assert response.headers['content-type'].startswith('text/event-stream')
        assert response.headers['cache-control'] == 'no-store'
        assert response.headers['x-accel-buffering'] == 'no'
        lines = response.iter_lines()
        assert next(lines) == 'event: delta'
        assert json.loads(next(lines)[6:]) == {'text': 'Primeira parte'}
        assert runtime.state.entered.is_set() and not runtime.state.release.is_set()
        runtime.state.release.set()
        rest = '\n'.join(lines)
        assert 'event: done' in rest and 'event: error' not in rest
    assert_released(runtime, 'completed')
    assert not runtime.state.unloaded.is_set()


def test_real_client_disconnect_unloads_and_releases_guard(runtime):
    with runtime.client.stream('POST', '/api/v3/llm/ask', json={'question': 'Estado?'}) as response:
        lines = response.iter_lines()
        assert next(lines) == 'event: delta'
        assert 'Primeira parte' in next(lines)
    assert runtime.state.unloaded.wait(5)
    assert_released(runtime, 'cancelled')


def test_revocation_during_real_stream_prevents_success(runtime):
    with runtime.client.stream('POST', '/api/v3/llm/ask', json={'question': 'Estado?'}) as response:
        lines = response.iter_lines()
        assert next(lines) == 'event: delta'
        next(lines)
        with connect(runtime.config) as connection:
            connection.execute('UPDATE sessions SET revoked_at=now() WHERE user_id=%s', (runtime.owner,))
        runtime.state.release.set()
        rest = '\n'.join(lines)
        assert 'event: error' in rest and 'UNAUTHORIZED' in rest
        assert 'event: done' not in rest
    assert runtime.state.unloaded.is_set()
    assert_released(runtime, 'UNAUTHORIZED')


@pytest.mark.parametrize('failure', ['http', 'protocol'])
def test_real_upstream_failures_have_private_sse_and_audit(runtime, failure):
    runtime.state.failure = failure
    response = runtime.client.post('/api/v3/llm/ask', json={'question': 'Estado?'})
    assert response.status_code == 200
    assert response.text == 'event: error\ndata: {"code": "LLM_UNAVAILABLE"}\n\n'
    assert 'private' not in response.text and 'credentials' not in response.text
    assert runtime.state.unloaded.is_set()
    assert_released(runtime, 'LLM_UNAVAILABLE')


def test_total_timeout_cancels_real_pending_http_and_recovers(runtime, monkeypatch):
    import backend.app.services.assistant as module
    # Keep the production 60-second boundary; shorten only this test's clock budget.
    monkeypatch.setattr(module, 'asyncio', SimpleNamespace(
        timeout=lambda seconds: asyncio.timeout(.15 if seconds == 60 else seconds)))
    runtime.state.failure = 'timeout'
    started = time.monotonic()
    response = runtime.client.post('/api/v3/llm/ask', json={'question': 'Estado?'})
    assert time.monotonic() - started < 5
    assert response.status_code == 200
    assert response.text == 'event: error\ndata: {"code": "LLM_TIMEOUT"}\n\n'
    assert runtime.state.unloaded.is_set()
    assert_released(runtime, 'LLM_TIMEOUT')
