"""B2-19: browser -> authenticated HTTP -> real AMQP worker -> private NPY data."""
import os
from pathlib import Path
import secrets
import shutil
import subprocess
from threading import Event, Thread
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import pytest
import uvicorn

from backend.app.api.auth import AuthService
from backend.app.api.jobs import create_jobs_router
from backend.app.amqp.jobs import JobPublisher, JobWorker
from backend.app.repositories.postgres import connect
from backend.app.services.generation import GenerationHandler
from backend.tests.infra.test_dashboard_integration import free_port, wait_http
from backend.tests.integration.test_jobs_integration import amqp_connect, broker, database, jobs

ROOT = Path(__file__).resolve().parents[3]
pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    os.environ.get('COLDSAFE_LAB_INTEGRATION') != '1',
    reason='Set COLDSAFE_LAB_INTEGRATION=1 and disposable PostgreSQL/RabbitMQ settings',
)]


def test_web_million_rows_reload_quality_sample_failure_and_author(jobs, broker, tmp_path):
    service, config, owners, root = jobs
    api_url, web_url = (f'http://127.0.0.1:{free_port()}' for _ in range(2))
    auth = AuthService(config)
    password = secrets.token_urlsafe(24)
    emails = ['lab-admin@example.invalid', 'lab-stranger@example.invalid']
    with connect(config) as connection:
        for owner, email in zip(owners, emails, strict=True):
            connection.execute('UPDATE users SET email=%s,password_hash=%s WHERE id=%s',
                               (email, auth._passwords.hash(password), owner))
    app = FastAPI()
    app.add_middleware(CORSMiddleware, allow_origins=[web_url], allow_methods=['*'],
                       allow_headers=['authorization', 'content-type'])
    app.include_router(auth.router)
    app.include_router(create_jobs_router(auth, service))
    auth.install_exception_handlers(app)
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1',
                             port=int(api_url.rsplit(':', 1)[1]), log_level='warning'))
    api_thread = Thread(target=server.run, daemon=True)
    stop, failures = Event(), []
    release = tmp_path / 'release-generation'
    handler = GenerationHandler(config, artifact_root=root)

    def controlled_generation(job, checkpoint):
        def durable_block(completed):
            checkpoint(completed)
            if job['config']['seed'] == 43:
                raise OSError('Deliberate disk failure after a durable block')
            if completed == 50_000:
                deadline = time.monotonic() + 90
                while not release.exists():
                    if stop.wait(0.05) or time.monotonic() >= deadline:
                        raise TimeoutError('Browser did not release the generation checkpoint')
        return handler(job, durable_block)

    def work():
        worker = JobWorker(service, 'generation', host='127.0.0.1', port=broker['port'],
            password=broker['passwords']['generation'], handler=controlled_generation)
        publisher = JobPublisher(service, host='127.0.0.1', port=broker['port'],
                                 password=broker['passwords']['api'])
        try:
            with amqp_connect(broker, 'api') as api_channel, amqp_connect(broker, 'generation') as channel:
                while not stop.is_set():
                    publisher.flush_outputs(api_channel)
                    worker.step(channel)
                    stop.wait(0.05)
        except BaseException as error:
            failures.append(type(error).__name__)
        finally:
            worker.close()

    node = os.environ.get('COLDSAFE_NODE_BINARY') or shutil.which('node')
    assert node, 'Node is required for the browser integration'
    environment = {**os.environ, 'VITE_API_BASE_URL': api_url, 'LAB_REAL_URL': web_url,
        'LAB_REAL_API_URL': api_url, 'LAB_REAL_PASSWORD': password,
        'LAB_REAL_EMAIL': emails[0], 'LAB_REAL_OTHER_EMAIL': emails[1],
        'LAB_REAL_OWNER': str(owners[0]), 'LAB_REAL_RELEASE': str(release),
        'PATH': str(Path(node).parent) + os.pathsep + os.environ.get('PATH', '')}
    frontend = tmp_path / 'web'
    frontend.mkdir()
    for name in ('src', 'public', 'e2e'):
        shutil.copytree(ROOT / 'frontend' / name, frontend / name)
    for name in ('index.html', 'package.json', 'vite.config.ts', 'tsconfig.app.json',
                 'playwright.laboratory.config.ts'):
        shutil.copyfile(ROOT / 'frontend' / name, frontend / name)
    dependencies = Path(os.environ.get('COLDSAFE_FRONTEND_NODE_MODULES', str(ROOT / 'frontend/node_modules')))
    (frontend / 'node_modules').symlink_to(dependencies, target_is_directory=True)
    worker_thread = Thread(target=work, daemon=True)
    vite = None
    with (tmp_path / 'servers.log').open('w+') as logs:
        try:
            api_thread.start()
            deadline = time.monotonic() + 15
            while not server.started:
                assert api_thread.is_alive() and time.monotonic() < deadline
                time.sleep(0.05)
            worker_thread.start()
            vite = subprocess.Popen([node, 'node_modules/vite/bin/vite.js', '--host', '127.0.0.1',
                '--port', web_url.rsplit(':', 1)[1], '--strictPort'], cwd=frontend,
                env=environment, stdout=logs, stderr=logs)
            wait_http(vite, web_url)
            result = subprocess.run([node, 'node_modules/@playwright/test/cli.js', 'test',
                '--config', 'playwright.laboratory.config.ts'], cwd=frontend,
                env=environment, capture_output=True, text=True, timeout=180)
            assert result.returncode == 0, (result.stdout + result.stderr).replace(password, '[REDACTED]')
            print(result.stdout)
            with connect(config) as connection:
                rows = connection.execute('SELECT j.owner_user_id,j.status,j.completed_units,d.row_count,'
                    'd.owner_user_id,j.config FROM jobs j LEFT JOIN datasets d ON d.generation_job_id=j.id '
                    'ORDER BY j.created_at').fetchall()
            assert len(rows) == 2
            assert rows[0][:5] == (owners[0], 'completed', 1_000_000, 1_000_000, owners[0])
            assert rows[0][5]['seed'] == 42
            assert rows[1][:5] == (owners[0], 'failed', 50_000, None, None)
            assert rows[1][5]['seed'] == 43
            print('Real HTTP/AMQP/NPY: 1,000,000 rows, reload without repost, private sample, '
                  'quality and author verified; partial failure kept 50,000 units without dataset.')
        finally:
            release.touch()
            stop.set()
            if worker_thread.ident is not None:
                worker_thread.join(timeout=15)
            server.should_exit = True
            if api_thread.ident is not None:
                api_thread.join(timeout=15)
            if vite:
                vite.terminate()
                try:
                    vite.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    vite.kill()
                    vite.wait(timeout=5)
            assert not failures, f'AMQP worker failed: {failures}'
            assert not worker_thread.is_alive() and not api_thread.is_alive()
