"""B2-23: browser -> HTTP -> AMQP -> isolated training -> private result JSON."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
from threading import Event, Thread
import time
from unittest.mock import Mock

from fastapi.middleware.cors import CORSMiddleware
import pytest
import uvicorn

from backend.app.api.app import create_app
from backend.app.api.auth import AuthService
from backend.app.api.catalog import CatalogService
from backend.app.api.jobs import create_jobs_router
from backend.app.amqp.jobs import JobPublisher, JobWorker
from backend.app.repositories.postgres import connect
from backend.app.services.generation import GenerationHandler
from backend.app.services.jobs import JobService
from backend.app.services.training import TrainingHandler
from backend.tests.infra.test_dashboard_integration import free_port, wait_http
from backend.tests.integration.test_jobs_integration import broker, database, jobs

ROOT = Path(__file__).resolve().parents[3]
pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    os.environ.get('COLDSAFE_TRAINING_INTEGRATION') != '1',
    reason='Set COLDSAFE_TRAINING_INTEGRATION=1 with disposable PostgreSQL/RabbitMQ settings',
)]


def test_real_training_page_reload_private_metrics_and_roles(jobs, broker, tmp_path):
    _, config, owners, root = jobs
    service = JobService(config, artifact_root=root / 'datasets', training_artifact_root=root / 'training')
    api_url, web_url = (f'http://127.0.0.1:{free_port()}' for _ in range(2))
    auth = AuthService(config)
    password = secrets.token_urlsafe(24)
    emails = ['training-admin@example.invalid', 'training-stranger@example.invalid', 'training-viewer@example.invalid']
    with connect(config) as connection:
        hashed = auth._passwords.hash(password)
        for owner, email in zip(owners, emails[:2], strict=True):
            connection.execute('UPDATE users SET email=%s,password_hash=%s WHERE id=%s', (email, hashed, owner))
        connection.execute("INSERT INTO users(email,password_hash,role) VALUES(%s,%s,'viewer')", (emails[2], hashed))
    generation = service.create(owners[0], {'job_type': 'generation', 'total_units': 1_000_000, 'seed': 42})
    assert service.execute(generation['id'], 'generation', GenerationHandler(config, artifact_root=service.artifact_root))
    dataset_id = service.get(owners[0], generation['id'])['result_id']
    assert dataset_id is not None
    print('B2-23 isolated source: 1,000,000 generated rows, completed private generation job.', flush=True)

    app = create_app(repository=Mock(), readiness_check=lambda: True, auth=auth, catalog=CatalogService(config))
    app.add_middleware(CORSMiddleware, allow_origins=[web_url], allow_methods=['*'],
                       allow_headers=['authorization', 'content-type'])
    app.include_router(create_jobs_router(auth, service))
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1',
        port=int(api_url.rsplit(':', 1)[1]), log_level='warning'))
    api_thread = Thread(target=server.run, daemon=True)
    stop, failures = Event(), []
    release = tmp_path / 'release-rul'
    handler = TrainingHandler(config, artifact_root=service.artifact_root,
                              training_artifact_root=service.training_artifact_root)

    def controlled_training(job, checkpoint):
        paused = False

        def checked(completed):
            nonlocal paused
            if stop.is_set():
                raise RuntimeError('Integration harness stopped')
            checkpoint(completed)
            if completed == 1 and not paused:
                paused = True
                print('B2-23 health persisted; waiting for browser reload before RUL.', flush=True)
                deadline = time.monotonic() + 90
                while not release.exists():
                    if stop.wait(0.05) or time.monotonic() >= deadline:
                        raise TimeoutError('Browser did not release RUL after reload')

        return handler(job, checked)

    worker = JobWorker(service, 'training', host='127.0.0.1', port=broker['port'],
        password=broker['passwords']['training'], handler=controlled_training)
    publisher = JobPublisher(service, host='127.0.0.1', port=broker['port'], password=broker['passwords']['api'])

    def work(participant):
        try:
            participant.run(stop)
        except BaseException as error:
            failures.append(type(error).__name__)

    node = os.environ.get('COLDSAFE_NODE_BINARY') or shutil.which('node')
    assert node, 'Node 24 is required'
    environment = {**os.environ, 'VITE_API_BASE_URL': api_url, 'TRAINING_REAL_URL': web_url,
        'TRAINING_REAL_API_URL': api_url, 'TRAINING_REAL_PASSWORD': password,
        'TRAINING_REAL_EMAIL': emails[0], 'TRAINING_REAL_OTHER_EMAIL': emails[1],
        'TRAINING_REAL_VIEWER_EMAIL': emails[2], 'TRAINING_REAL_DATASET': str(dataset_id),
        'TRAINING_REAL_RELEASE': str(release),
        'PATH': str(Path(node).parent) + os.pathsep + os.environ.get('PATH', '')}
    frontend = tmp_path / 'web'
    frontend.mkdir()
    for name in ('src', 'public', 'e2e'):
        shutil.copytree(ROOT / 'frontend' / name, frontend / name)
    for name in ('index.html', 'package.json', 'vite.config.ts', 'tsconfig.app.json', 'playwright.training.config.ts'):
        shutil.copyfile(ROOT / 'frontend' / name, frontend / name)
    dependencies = Path(os.environ.get('COLDSAFE_FRONTEND_NODE_MODULES', str(ROOT / 'frontend/node_modules')))
    (frontend / 'node_modules').symlink_to(dependencies, target_is_directory=True)
    bus_threads = [Thread(target=work, args=(participant,), daemon=True) for participant in (publisher, worker)]
    vite = None
    with (tmp_path / 'servers.log').open('w+') as logs:
        try:
            api_thread.start()
            deadline = time.monotonic() + 15
            while not server.started:
                assert api_thread.is_alive() and time.monotonic() < deadline
                time.sleep(0.05)
            for thread in bus_threads:
                thread.start()
            vite = subprocess.Popen([node, 'node_modules/vite/bin/vite.js', '--host', '127.0.0.1',
                '--port', web_url.rsplit(':', 1)[1], '--strictPort'], cwd=frontend, env=environment,
                stdout=logs, stderr=logs)
            wait_http(vite, web_url)
            browser = subprocess.run([node, 'node_modules/@playwright/test/cli.js', 'test',
                '--config', 'playwright.training.config.ts'], cwd=frontend, env=environment,
                capture_output=True, text=True, timeout=360)
            assert browser.returncode == 0, (browser.stdout + browser.stderr).replace(password, '[REDACTED]')
            print(browser.stdout, flush=True)
            with connect(config) as connection:
                rows = connection.execute("SELECT id,result_model_id,status,completed_units FROM jobs "
                    "WHERE job_type='training'").fetchall()
                assert len(rows) == 1 and rows[0][2:] == ('completed', 2)
                job_id, model_id = rows[0][:2]
                key, metrics = connection.execute('SELECT artifact_key,metrics FROM models WHERE id=%s', (model_id,)).fetchone()
                assert connection.execute('SELECT count(*) FROM active_models').fetchone() == (0,)
                assert connection.execute('SELECT count(*) FROM model_activations').fetchone() == (0,)
            directory = (service.training_artifact_root / key).parent
            reports = {target: json.loads((directory / target / 'report.json').read_text()) for target in ('health', 'rul')}
            for target, report in reports.items():
                assert report['metrics'] == metrics[target]['metrics']
                assert report['diagnostics']['sample_count'] == 500
                assert len(report['diagnostics']['permutation']['features']) == 48
                if report['status'] == 'eligible':
                    with (directory / target / 'model.pkl').open('rb') as stream:
                        assert hashlib.file_digest(stream, 'sha256').hexdigest() == report['model_sha256']
            evidence = {'job_id': str(job_id), 'model_id': str(model_id), 'dataset_id': str(dataset_id),
                'generated_rows': 1_000_000, 'job_completed_units': 2, 'training_posts': 1,
                'http_amqp_postgres_browser_real': True, 'reload_without_repost': True,
                'owner_isolation_and_viewer_denial': True, 'active_model_count': 0,
                'reports': reports}
            destination = os.environ.get('COLDSAFE_TRAINING_EVIDENCE_DIR')
            if destination:
                output = Path(destination)
                output.mkdir(mode=0o700, parents=True, exist_ok=True)
                (output / 'integration.json').write_text(json.dumps(evidence, allow_nan=False, indent=2) + '\n')
                for screenshot in frontend.glob('test-results/**/training-*.png'):
                    shutil.copyfile(screenshot, output / screenshot.name)
            print('B2-23 real browser/HTTP/PostgreSQL/AMQP: two regressors, bounded diagnostics, '
                  'reload without repost, private owner and viewer denial verified; zero activations.', flush=True)
        finally:
            release.touch()
            stop.set()
            for thread in bus_threads:
                if thread.ident is not None:
                    thread.join(timeout=20)
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
            assert not failures, f'AMQP training worker failed: {failures}'
            assert not any(thread.is_alive() for thread in bus_threads) and not api_thread.is_alive()
