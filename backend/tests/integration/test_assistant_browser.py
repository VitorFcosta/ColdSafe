"""B2-32: real PostgreSQL, JWT, HTTP/SSE and Chromium; Ollama is a protocol double."""
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread
import time
from types import SimpleNamespace
from uuid import uuid4

from fastapi.middleware.cors import CORSMiddleware
import pytest
import uvicorn

from backend.app.api.app import create_app
from backend.app.api.auth import AuthService
from backend.app.api.catalog import CatalogService
from backend.app.api.llm import create_llm_router
from backend.app.repositories.postgres import connect
from backend.app.services.assistant import AssistantService
from backend.app.services.llm import LlmService, MODEL
from backend.tests.infra.test_dashboard_integration import free_port, wait_http
from backend.tests.integration.test_aiot_migrations_integration import database
from backend.tests.integration.test_jobs_integration import jobs

ROOT = Path(__file__).resolve().parents[3]
pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    os.environ.get('COLDSAFE_ASSISTANT_BROWSER') != '1',
    reason='Set COLDSAFE_ASSISTANT_BROWSER=1 with disposable PostgreSQL and Node24',
)]


def test_assistant_real_http_streaming_text_safety_cancel_and_private_accounts(jobs, tmp_path):
    state = SimpleNamespace(loaded=True, entered=Event(), release=Event(), unloaded=Event(), summaries=[])

    class Ollama(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *_args):
            pass

        def reply(self, payload):
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == '/test/state':
                return self.reply({'entered': state.entered.is_set(), 'released': state.release.is_set(),
                                   'unloaded': state.unloaded.is_set()})
            if self.path == '/api/tags':
                return self.reply({'models': [{'name': MODEL}]})
            assert self.path == '/api/ps'
            self.reply({'models': [{'name': MODEL, 'size_vram': 0, 'context_length': 1024}]
                        if state.loaded else []})

        def do_POST(self):
            length = int(self.headers.get('Content-Length', '0'))
            payload = json.loads(self.rfile.read(length)) if length else {}
            if self.path == '/test/release':
                state.release.set()
                return self.reply({'released': True})
            if self.path == '/test/reset':
                state.entered.clear()
                state.release.clear()
                state.unloaded.clear()
                state.loaded = True
                return self.reply({'reset': True})
            if self.path == '/api/generate':
                assert payload['keep_alive'] == 0
                state.loaded = False
                state.unloaded.set()
                state.release.set()
                return self.reply({'done': True, 'done_reason': 'unload'})
            assert self.path == '/api/chat'
            summary = json.loads(payload['messages'][1]['content'])['resumo']
            state.summaries.append(summary)
            device = summary['equipment'][0]['device']
            state.entered.set()
            self.send_response(200)
            self.send_header('Content-Type', 'application/x-ndjson')
            self.send_header('Connection', 'close')
            self.end_headers()
            self.close_connection = True
            try:
                text = f'Contexto: {device}. <script>window.__assistantExecuted=1</script> <img src="https://remote.invalid/pixel">'
                for text, completed in ((text, False), (' Concluído.', True)):
                    self.wfile.write((json.dumps({'model': MODEL, 'done': completed, 'message': {
                        'role': 'assistant', 'content': text}}) + '\n').encode())
                    self.wfile.flush()
                    if not completed:
                        assert state.release.wait(30), 'Browser never released the protocol fixture'
            except (BrokenPipeError, ConnectionResetError):
                pass

    upstream = ThreadingHTTPServer(('127.0.0.1', 0), Ollama)
    upstream.daemon_threads = True
    upstream_thread = Thread(target=upstream.serve_forever, daemon=True)
    upstream_thread.start()
    config = jobs[1].model_copy(update={'ollama_url': f'http://127.0.0.1:{upstream.server_port}'})
    auth, catalog = AuthService(config), CatalogService(config)
    password = secrets.token_urlsafe(24)
    emails = [f'assistant-{uuid4()}@example.invalid' for _ in range(2)]
    owners = [auth.register(email, password) for email in emails]
    with connect(config) as connection:
        for owner, suffix in zip(owners, ('a', 'b'), strict=True):
            environment = connection.execute("INSERT INTO environments(owner_user_id,name) VALUES(%s,'Test') RETURNING id",
                                             (owner,)).fetchone()[0]
            connection.execute('INSERT INTO devices(environment_id,mqtt_device_id,name) VALUES(%s,%s,%s)',
                               (environment, f'browser-private-{suffix}', f'Test {suffix}'))
    api_url, web_url = (f'http://127.0.0.1:{free_port()}' for _ in range(2))
    app = create_app(repository=None, readiness_check=lambda: True, auth=auth, catalog=catalog)
    app.add_middleware(CORSMiddleware, allow_origins=[web_url], allow_methods=['*'],
                       allow_headers=['authorization', 'content-type'])
    app.include_router(create_llm_router(auth, LlmService(config), AssistantService(config)))
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1',
        port=int(api_url.rsplit(':', 1)[1]), log_level='critical', ws='none'))
    api_thread = Thread(target=server.run, daemon=True)
    node = os.environ.get('COLDSAFE_NODE_BINARY') or shutil.which('node')
    assert node, 'Node24 required'
    frontend = tmp_path / 'web'
    frontend.mkdir()
    for name in ('src', 'public', 'e2e'):
        shutil.copytree(ROOT / 'frontend' / name, frontend / name)
    for name in ('index.html', 'package.json', 'package-lock.json', 'vite.config.ts',
                 'tsconfig.app.json', 'playwright.assistant.config.ts'):
        shutil.copyfile(ROOT / 'frontend' / name, frontend / name)
    dependencies = Path(os.environ.get('COLDSAFE_FRONTEND_NODE_MODULES', str(ROOT / 'frontend/node_modules')))
    (frontend / 'node_modules').symlink_to(dependencies, target_is_directory=True)
    output = Path(os.environ.get('COLDSAFE_ASSISTANT_EVIDENCE_DIR', '/tmp/coldsafe-b232'))
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    environment = {**os.environ, 'VITE_API_BASE_URL': api_url,
        'ASSISTANT_REAL_URL': web_url, 'ASSISTANT_REAL_API_URL': api_url,
        'ASSISTANT_REAL_CONTROL_URL': f'http://127.0.0.1:{upstream.server_port}',
        'ASSISTANT_REAL_EMAIL': emails[0], 'ASSISTANT_REAL_OTHER_EMAIL': emails[1],
        'ASSISTANT_REAL_PASSWORD': password, 'ASSISTANT_REAL_EVIDENCE_DIR': str(output),
        'PATH': str(Path(node).parent) + os.pathsep + os.environ.get('PATH', '')}
    vite = None
    with (tmp_path / 'servers.log').open('w+') as logs:
        try:
            api_thread.start()
            deadline = time.monotonic() + 15
            while not server.started:
                assert api_thread.is_alive() and time.monotonic() < deadline
                time.sleep(.02)
            vite = subprocess.Popen([node, 'node_modules/vite/bin/vite.js', '--host', '127.0.0.1',
                '--port', web_url.rsplit(':', 1)[1], '--strictPort'], cwd=frontend, env=environment,
                stdout=logs, stderr=logs)
            wait_http(vite, web_url)
            browser = subprocess.run([node, 'node_modules/@playwright/test/cli.js', 'test',
                '--config', 'playwright.assistant.config.ts'], cwd=frontend, env=environment,
                capture_output=True, text=True, timeout=150)
            assert browser.returncode == 0, (browser.stdout + browser.stderr).replace(password, '[REDACTED]')
            with connect(config) as connection:
                outcomes = dict(connection.execute("SELECT details->>'outcome',count(*) FROM audit_events "
                    "WHERE event_type='assistant.finished' GROUP BY details->>'outcome'").fetchall())
                assert outcomes == {'completed': 2, 'cancelled': 1}
                assert connection.execute('SELECT count(*) FROM aiot_commands').fetchone() == (0,)
                assert connection.execute('SELECT count(*) FROM llm_memory_guard').fetchone() == (0,)
            assert len(state.summaries) == 3
            for summary, suffix in zip(state.summaries, ('a', 'a', 'b'), strict=True):
                assert summary['equipment'][0]['device'] == f'browser-private-{suffix}'
                assert f'browser-private-{"b" if suffix == "a" else "a"}' not in json.dumps(summary)
            evidence = json.loads((output / 'browser-wire.json').read_text())
            evidence.update(completed_audits=2, cancelled_audits=1, commands_created=0,
                            memory_guard_rows=0, owner_contexts_checked=3)
            (output / 'browser-wire.json').write_text(json.dumps(evidence, indent=2) + '\n')
            print(browser.stdout, flush=True)
        finally:
            state.release.set()
            server.should_exit = True
            if api_thread.ident is not None:
                api_thread.join(10)
            if vite:
                vite.terminate()
                try:
                    vite.wait(10)
                except subprocess.TimeoutExpired:
                    vite.kill()
                    vite.wait(5)
            upstream.shutdown()
            upstream.server_close()
            upstream_thread.join(5)
            assert not api_thread.is_alive() and not upstream_thread.is_alive()
