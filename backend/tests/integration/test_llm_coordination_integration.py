"""Real PostgreSQL locks; tiny executors and Ollama protocol doubles are explicit."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import Mock

import pytest

from backend.app.repositories.postgres import connect
from backend.app.services.jobs import JobService, HEAVY_JOB_LOCK
from backend.app.services.llm import LlmService, MODEL, OllamaUnavailable
from backend.tests.integration.test_jobs_integration import jobs, small_job, dataset_result
from backend.tests.integration.test_aiot_migrations_integration import database

pytestmark = pytest.mark.integration


def configured(jobs):
    _, database, _, root = jobs
    config = database.model_copy(update={'ollama_url': 'http://ollama:11434'})
    service = LlmService(config)
    service.client = Mock()
    service.client.ready.side_effect = lambda rows: bool(rows)
    service.client.loaded.return_value = []
    service.client.installed.return_value = True
    return JobService(config, artifact_root=root), service


def test_preload_holds_shared_lock_and_reports_loading(jobs):
    job_service, llm = configured(jobs)
    identifier = small_job(jobs)
    entered, release = Event(), Event()
    def preload():
        entered.set()
        assert release.wait(5)
    llm.client.preload.side_effect = preload
    with ThreadPoolExecutor() as pool:
        future = pool.submit(llm.tick)
        try:
            assert entered.wait(3)
            assert llm.status()['state'] == 'loading'
            assert not job_service.execute(identifier, 'generation', lambda *_: pytest.fail('overlap'))
        finally:
            release.set()
        assert future.result(timeout=5)


def test_job_unloads_before_handler_and_coordinator_resumes_after_completion(jobs, monkeypatch):
    job_service, llm = configured(jobs)
    identifier = small_job(jobs)
    unload = Mock()
    monkeypatch.setattr('backend.app.services.llm.OllamaClient.unload', unload)
    def handler(job, checkpoint):
        unload.assert_called_once_with()
        assert not llm.tick()
        assert llm.status()['state'] == 'paused'
        llm.client.preload.assert_not_called()
        return dataset_result(jobs, job, checkpoint)
    assert job_service.execute(identifier, 'generation', handler)
    assert llm.tick()
    llm.client.preload.assert_called_once_with()


def test_unconfirmed_unload_preserves_delivery_and_queued_job(jobs, monkeypatch):
    job_service, _ = configured(jobs)
    identifier = small_job(jobs)
    monkeypatch.setattr('backend.app.services.llm.OllamaClient.unload', Mock(side_effect=OllamaUnavailable('private error')))
    handler = Mock()
    assert not job_service.execute(identifier, 'generation', handler)
    handler.assert_not_called()
    assert jobs[0].get(jobs[2][0], identifier)['status'] == 'queued'


def test_orphan_running_job_blocks_preload_after_lock_session_disappears(jobs):
    _, llm = configured(jobs)
    identifier = small_job(jobs)
    with connect(llm.settings) as connection:
        connection.execute("UPDATE jobs SET status='running' WHERE id=%s", (identifier,))
        connection.execute('SELECT pg_advisory_lock(%s)', (HEAVY_JOB_LOCK,))
    # The session above is closed, but its executor may still be computing in another process.
    assert not llm.tick()
    assert llm.status()['state'] == 'paused'
    llm.client.preload.assert_not_called()
    with connect(llm.settings) as connection:
        connection.execute("UPDATE jobs SET status='failed',error_code='GENERATION_FAILED' WHERE id=%s", (identifier,))
    assert llm.tick()


@pytest.mark.parametrize('state,models,installed', [('ready', [{'name': MODEL}], True), ('loading', [], True), ('model_missing', [], False)])
def test_status_reads_state_without_loading(state, models, installed, jobs):
    _, llm = configured(jobs)
    llm.client.loaded.return_value = models
    llm.client.installed.return_value = installed
    assert llm.status() == {'state': state, 'model': MODEL}
    llm.client.preload.assert_not_called()


def test_ollama_outage_is_explicit_and_private(jobs):
    _, llm = configured(jobs)
    llm.client.loaded.side_effect = OllamaUnavailable('private network details')
    assert llm.status() == {'state': 'unavailable', 'model': MODEL}


def test_disabled_is_no_io(jobs):
    service = LlmService(jobs[1])
    assert service.status() == {'state': 'disabled', 'model': MODEL}
    assert not service.tick()


def test_running_job_exception_releases_memory_slot_for_reload(jobs, monkeypatch):
    job_service, llm = configured(jobs)
    identifier = small_job(jobs)
    monkeypatch.setattr('backend.app.services.llm.OllamaClient.unload', Mock())
    def fail(*_):
        raise ValueError('synthetic executor failure')
    assert job_service.execute(identifier, 'generation', fail)
    assert jobs[0].get(jobs[2][0], identifier)['status'] == 'failed'
    assert llm.tick()


def test_database_outage_is_unavailable_and_tick_propagates_for_retry(jobs, monkeypatch):
    import psycopg
    _, llm = configured(jobs)
    monkeypatch.setattr('backend.app.services.llm.connect', Mock(side_effect=psycopg.OperationalError('private credentials')))
    assert llm.status()['state'] == 'unavailable'
    with pytest.raises(psycopg.Error):
        llm.tick()


def test_ready_tick_is_noop_and_run_retries_failure(jobs):
    from threading import Event
    _, llm = configured(jobs)
    llm.client.loaded.return_value = [{'name': MODEL}]
    assert llm.tick()
    llm.client.preload.assert_not_called()
    stopped = Event()
    def fail_once():
        stopped.set()
        raise OllamaUnavailable('fixture')
    llm.tick = Mock(side_effect=fail_once)
    llm.run(stopped)
    llm.tick.assert_called_once_with()


def test_status_does_not_advertise_its_own_probe_as_preloading(jobs):
    from backend.app.services.llm import LOADING_LOCK
    _, llm = configured(jobs)
    def loaded():
        with connect(llm.settings) as observer:
            assert observer.execute('SELECT pg_try_advisory_lock(%s)', (LOADING_LOCK,)).fetchone()[0]
        return []
    llm.client.loaded.side_effect = loaded
    assert llm.status()['state'] == 'loading'


def test_status_revalidates_two_real_sessions_and_revocation_in_postgres(jobs):
    from uuid import uuid4
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.app.api.auth import AuthService
    from backend.app.api.llm import create_llm_router
    _, llm = configured(jobs)
    auth = AuthService(llm.settings)
    tokens = []
    for _ in range(2):
        email = f'{uuid4()}@example.invalid'
        auth.register(email, 'local-test-password')
        tokens.append(auth.login(email, 'local-test-password')[0])
    app = FastAPI()
    app.include_router(create_llm_router(auth, llm))
    auth.install_exception_handlers(app)
    with TestClient(app) as client:
        expected = {'success': True, 'data': {'state': 'loading', 'model': MODEL}, 'meta': {'schema_version': 3}}
        for token in tokens:
            response = client.get('/api/v3/llm/status', headers={'Authorization': f'Bearer {token}'})
            assert response.status_code == 200
            assert response.headers['Cache-Control'] == 'no-store'
            assert response.json() == expected
        assert client.get('/api/v3/llm/status').status_code == 401
        principal = auth.session_for_token(tokens[0])
        with connect(llm.settings) as connection:
            connection.execute('UPDATE sessions SET revoked_at=now() WHERE id=%s', (principal.session_id,))
        assert client.get('/api/v3/llm/status', headers={'Authorization': f'Bearer {tokens[0]}'}).status_code == 401
        assert client.get('/api/v3/llm/status', headers={'Authorization': f'Bearer {tokens[1]}'}).status_code == 200


def test_durable_guard_blocks_jobs_if_preload_loses_its_postgres_session(jobs, monkeypatch):
    import psycopg
    job_service, llm = configured(jobs)
    identifier = small_job(jobs)
    entered, release = Event(), Event()
    backend_pids = []
    def tracked_connect(config):
        connection = connect(config)
        backend_pids.append(connection.info.backend_pid)
        return connection
    monkeypatch.setattr('backend.app.services.llm.connect', tracked_connect)
    unload = Mock()
    monkeypatch.setattr('backend.app.services.llm.OllamaClient.unload', unload)
    def blocked_preload():
        entered.set()
        assert release.wait(5)
    llm.client.preload.side_effect = blocked_preload
    with ThreadPoolExecutor() as pool:
        future = pool.submit(llm.tick)
        try:
            assert entered.wait(3)
            with connect(llm.settings) as observer:
                assert observer.execute('SELECT count(*) FROM llm_memory_guard').fetchone() == (1,)
                assert observer.execute('SELECT pg_terminate_backend(%s)', (backend_pids[0],)).fetchone()[0]
            # The database lock disappeared, while the remote loader is still running and /ps is empty.
            assert not job_service.execute(identifier, 'generation', lambda *_: pytest.fail('overlap with loader'))
            unload.assert_not_called()
            assert llm.status()['state'] == 'unavailable'
        finally:
            release.set()
        with pytest.raises(psycopg.Error):
            future.result(timeout=5)
    with connect(llm.settings) as observer:
        assert observer.execute('SELECT count(*) FROM llm_memory_guard').fetchone() == (1,)
    assert not llm.tick()
    # Explicit recovery is allowed only after the operator has stopped/restarted Ollama.
    with connect(llm.settings) as observer:
        observer.execute('DELETE FROM llm_memory_guard WHERE id=1')
    assert job_service.execute(identifier, 'generation', lambda job, checkpoint: dataset_result(jobs, job, checkpoint))
    assert llm.tick()
    with connect(llm.settings) as observer:
        assert observer.execute('SELECT count(*) FROM llm_memory_guard').fetchone() == (0,)


def test_ambiguous_preload_failure_keeps_durable_guard_and_does_not_retry_loading(jobs):
    _, llm = configured(jobs)
    llm.client.preload.side_effect = OllamaUnavailable('request timed out')
    with pytest.raises(OllamaUnavailable):
        llm.tick()
    assert llm.status()['state'] == 'unavailable'
    assert not llm.tick()
    llm.client.preload.assert_called_once_with()


def test_guard_is_singleton_and_migration_repeatable(jobs):
    import psycopg
    from backend.app.repositories.postgres import initialize_schema
    initialize_schema(jobs[1])
    with connect(jobs[1]) as connection:
        assert connection.execute('SELECT count(*) FROM llm_memory_guard').fetchone() == (0,)
        with pytest.raises(psycopg.errors.CheckViolation), connection.transaction():
            connection.execute('INSERT INTO llm_memory_guard(id) VALUES(2)')


def test_status_does_not_hold_heavy_job_lock_during_http_reads(jobs):
    _, llm = configured(jobs)
    def assert_job_slot_available():
        with connect(llm.settings) as observer:
            assert observer.execute('SELECT pg_try_advisory_lock(%s)', (HEAVY_JOB_LOCK,)).fetchone()[0]
    def loaded():
        assert_job_slot_available()
        return []
    def installed():
        assert_job_slot_available()
        return True
    llm.client.loaded.side_effect = loaded
    llm.client.installed.side_effect = installed
    assert llm.status()['state'] == 'loading'
