"""Real PostgreSQL checks for the job infrastructure, with tiny test executors."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from psycopg.rows import dict_row

from backend.app.repositories.postgres import connect, initialize_schema
from backend.tests.integration.test_aiot_migrations_integration import database
from backend.tests.infra.test_rabbitmq_integration import broker, connect as amqp_connect


pytestmark = pytest.mark.integration


@pytest.fixture
def jobs(database, tmp_path):
    from backend.app.services.jobs import JobService
    initialize_schema(database)
    with connect(database) as conn:
        owners = [conn.execute("INSERT INTO users(email,password_hash,role) VALUES(%s,'test','admin') RETURNING id",
                               (f'{uuid4()}@example.invalid',)).fetchone()[0] for _ in range(2)]
    return JobService(database, artifact_root=tmp_path), database, owners, tmp_path


def small_job(jobs, kind='generation', owner_index=0):
    service, config, owners, _ = jobs
    # A tiny executor fixture exercises orchestration, never mass generation or ML.
    with connect(config) as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            job = cursor.execute("INSERT INTO jobs(owner_user_id,job_type,total_units) VALUES(%s,'generation',3) RETURNING *",
                                 (owners[owner_index],)).fetchone()
        service._enqueue(conn, job, 'job_requested')
        service._enqueue(conn, job, 'job_progress')
    return UUID(str(job['id']))


def dataset_result(jobs, job, checkpoint):
    _, config, _, root = jobs
    checkpoint(2)
    key = f"{job['id']}.txt"
    (root / key).write_text('one\ntwo\nthree\n')
    with connect(config) as conn:
        result = conn.execute("INSERT INTO datasets(owner_user_id,generation_job_id,name,features_version,row_count,artifact_key) "
                              "VALUES(%s,%s,'test fixture','test-v1',3,%s) RETURNING id",
                              (job['owner_user_id'], job['id'], key)).fetchone()[0]
    return result


def test_create_is_durable_private_and_has_one_request(jobs):
    service, config, owners, _ = jobs
    job = service.create(owners[0], {'job_type': 'generation', 'total_units': 1_000_000, 'seed': 42})
    assert job['status'] == 'queued'
    assert service.get(owners[1], job['id']) is None
    requested = service.get_requested(job['id'])
    assert requested['correlation_id'] == str(job['id'])
    assert requested['data'] == {'job_id': str(job['id']), 'job_type': 'generation', 'dataset_id': None}
    assert service.pending_outputs('api') == [requested]
    service.mark_published(requested['event_id'])
    assert service.pending_outputs('api') == []
    assert service.get_requested(job['id']) == requested


def test_two_simultaneous_jobs_share_one_global_lock(jobs):
    service, _, owners, _ = jobs
    first, second = small_job(jobs), small_job(jobs, owner_index=1)
    entered, release = Event(), Event()
    def slow(job, checkpoint):
        entered.set()
        assert release.wait(5)
        return dataset_result(jobs, job, checkpoint)
    with ThreadPoolExecutor(max_workers=2) as pool:
        running = pool.submit(service.execute, first, 'generation', slow)
        try:
            assert entered.wait(3)
            assert not service.execute(second, 'generation', lambda *_: pytest.fail('concurrent execution'))
            assert service.get(owners[1], second)['status'] == 'queued'
        finally:
            release.set()
        assert running.result(timeout=5)
    assert service.get(owners[0], first)['status'] == 'completed'
    assert service.execute(first, 'generation', lambda *_: pytest.fail('terminal job reopened'))


def test_missing_executor_or_artifact_is_explicit_failure(jobs):
    service, _, owners, _ = jobs
    for handler in (None, lambda *_: uuid4()):
        job_id = small_job(jobs)
        assert service.execute(job_id, 'generation', handler)
        state = service.get(owners[0], job_id)
        assert (state['status'], state['error_code'], state['result_id']) == ('failed', 'GENERATION_FAILED', None)


def test_checkpoint_survives_interruption_and_new_service_resumes(jobs):
    from backend.app.services.jobs import JobService
    service, config, owners, root = jobs
    identifier = small_job(jobs)
    class Interrupted(BaseException):
        pass
    def stop(job, checkpoint):
        checkpoint(1)
        raise Interrupted()
    with pytest.raises(Interrupted):
        service.execute(identifier, 'generation', stop)
    assert service.get(owners[0], identifier)['completed_units'] == 1
    restarted = JobService(config, artifact_root=root)
    def resume(job, checkpoint):
        assert job['completed_units'] == 1
        return dataset_result(jobs, job, checkpoint)
    assert restarted.execute(identifier, 'generation', resume)
    assert restarted.get(owners[0], identifier)['status'] == 'completed'


def test_worker_process_crash_releases_lock_and_preserves_checkpoint(jobs):
    import subprocess
    import sys
    service, config, owners, root = jobs
    identifier = small_job(jobs)
    script = f'''
import os
from pathlib import Path
from uuid import UUID
from backend.tests.integration.test_postgres_schema_integration import settings
from backend.app.services.jobs import JobService
config = settings().model_copy(update={{'postgres_db': {config.postgres_db!r}}})
service = JobService(config, artifact_root=Path({str(root)!r}))
def interrupted(job, checkpoint):
    checkpoint(1)
    os._exit(17)
service.execute(UUID({str(identifier)!r}), 'generation', interrupted)
'''
    process = subprocess.run([sys.executable, '-c', script], capture_output=True, timeout=10)
    assert process.returncode == 17
    assert service.get(owners[0], identifier)['completed_units'] == 1
    assert service.execute(identifier, 'generation', lambda job, checkpoint: dataset_result(jobs, job, checkpoint))
    assert service.get(owners[0], identifier)['status'] == 'completed'


def test_checkpoint_cannot_move_backwards(jobs):
    service, _, owners, _ = jobs
    identifier = small_job(jobs)
    def invalid(job, checkpoint):
        checkpoint(2)
        checkpoint(1)
    assert service.execute(identifier, 'generation', invalid)
    assert service.get(owners[0], identifier)['status'] == 'failed'


def test_scope_and_training_input_are_validated(jobs):
    service, config, owners, _ = jobs
    with connect(config) as conn:
        environment = conn.execute("INSERT INTO environments(owner_user_id,name) VALUES(%s,'private') RETURNING id", (owners[1],)).fetchone()[0]
        dataset = conn.execute("INSERT INTO datasets(owner_user_id,name,features_version) VALUES(%s,'private','test') RETURNING id", (owners[1],)).fetchone()[0]
    with pytest.raises(HTTPException):
        service.create(owners[0], {'job_type': 'generation', 'total_units': 1_000_000, 'seed': 42, 'environment_id': environment})
    with pytest.raises(HTTPException):
        service.create(owners[0], {'job_type': 'training', 'dataset_id': dataset})


def test_outbox_progress_conforms_to_contract(jobs):
    from backend.tests.contract.test_aiot_contract import check_job_semantics
    from jsonschema import Draft202012Validator, FormatChecker
    from simulator.model import SCHEMA
    service, _, _, _ = jobs
    identifier = small_job(jobs)
    service.execute(identifier, 'generation', None)
    events = service.pending_outputs('generation')
    assert [e['data']['status'] for e in events] == ['queued', 'running', 'failed']
    validator = Draft202012Validator({**SCHEMA, '$ref': '#/$defs/job_progress_event'}, format_checker=FormatChecker())
    for event in events:
        validator.validate(event)
        check_job_semantics(event, service.get_requested(identifier))


def test_generation_and_training_share_lock_and_both_can_finish(jobs):
    service, config, owners, root = jobs
    generation = small_job(jobs)
    service.execute(generation, 'generation', lambda job, checkpoint: dataset_result(jobs, job, checkpoint))
    dataset = service.get(owners[0], generation)['result_id']
    training = service.create(owners[0], {'job_type': 'training', 'dataset_id': dataset})
    next_generation = small_job(jobs, owner_index=1)
    entered, release = Event(), Event()
    def train(job, checkpoint):
        checkpoint(1)
        entered.set()
        assert release.wait(5)
        key = f"{job['id']}.json"
        (root / key).write_text('{"test_fixture":true}')
        with connect(config) as conn:
            return conn.execute("INSERT INTO models(owner_user_id,dataset_id,training_job_id,model_version,features_version,artifact_key) "
                                "VALUES(%s,%s,%s,'test-model','test-v1',%s) RETURNING id",
                                (owners[0], dataset, job['id'], key)).fetchone()[0]
    with ThreadPoolExecutor(max_workers=1) as pool:
        running = pool.submit(service.execute, training['id'], 'training', train)
        try:
            assert entered.wait(3)
            assert not service.execute(next_generation, 'generation', None)
        finally:
            release.set()
        assert running.result(timeout=5)
    assert service.get(owners[0], training['id'])['status'] == 'completed'


@pytest.mark.parametrize('artifact', ['missing', 'empty', 'symlink', 'wrong_origin'])
def test_registered_result_without_safe_artifact_cannot_complete(jobs, artifact):
    service, config, owners, root = jobs
    identifier = small_job(jobs)
    def invalid(job, checkpoint):
        result = dataset_result(jobs, job, checkpoint)
        path = root / f"{job['id']}.txt"
        if artifact == 'missing':
            path.unlink()
        elif artifact == 'empty':
            path.write_bytes(b'')
        elif artifact == 'symlink':
            target = root.parent / f'{uuid4()}.txt'
            target.write_text('outside')
            path.unlink()
            path.symlink_to(target)
        else:
            with connect(config) as conn:
                conn.execute('UPDATE datasets SET generation_job_id=NULL WHERE id=%s', (result,))
        return result
    assert service.execute(identifier, 'generation', invalid)
    assert service.get(owners[0], identifier)['status'] == 'failed'


def test_job_and_request_rollback_together(jobs, monkeypatch):
    service, config, owners, _ = jobs
    enqueue = service._enqueue
    def fail_after_request(conn, row, kind):
        enqueue(conn, row, kind)
        if kind == 'job_progress':
            raise RuntimeError('test transaction interruption')
    monkeypatch.setattr(service, '_enqueue', fail_after_request)
    with pytest.raises(RuntimeError):
        service.create(owners[0], {'job_type': 'generation', 'total_units': 1_000_000})
    with connect(config) as conn:
        assert conn.execute('SELECT count(*) FROM jobs').fetchone() == (0,)
        assert conn.execute('SELECT count(*) FROM job_outbox').fetchone() == (0,)


def test_real_http_202_sse_and_account_isolation(jobs):
    import secrets
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.app.api.auth import AuthService
    from backend.app.api.jobs import create_jobs_router
    service, config, owners, _ = jobs
    auth = AuthService(config)
    password = secrets.token_urlsafe(24)
    with connect(config) as conn:
        conn.execute('UPDATE users SET password_hash=%s', (auth._passwords.hash(password),))
        emails = [conn.execute('SELECT email FROM users WHERE id=%s', (owner,)).fetchone()[0] for owner in owners]
    headers = [{'Authorization': 'Bearer ' + auth.login(email, password, ip='test')[0]} for email in emails]
    app = FastAPI()
    auth.install_exception_handlers(app)
    app.include_router(create_jobs_router(auth, service))
    with TestClient(app) as client:
        response = client.post('/api/v3/jobs', headers=headers[0], json={'job_type': 'generation', 'total_units': 1_000_000})
        assert response.status_code == 202
        job = response.json()['data']
        assert job['status'] == 'queued'
        identifier = UUID(job['id'])
        service.execute(identifier, 'generation', None)
        response = client.get(f'/api/v3/jobs/{identifier}/events', headers=headers[0])
        assert response.status_code == 200
        assert 'event: job_progress' in response.text and 'GENERATION_FAILED' in response.text
        assert client.get(f'/api/v3/jobs/{identifier}/events', headers=headers[1]).status_code == 404
        with connect(config) as conn:
            conn.execute("UPDATE users SET role='operator' WHERE id=%s", (owners[0],))
        assert client.post('/api/v3/jobs', headers=headers[0], json={'job_type': 'generation', 'total_units': 1_000_000}).status_code == 403


def test_real_amqp_publish_confirmation_loss_duplicates_only_transport(jobs, broker, monkeypatch):
    import psycopg
    from backend.app.amqp.jobs import JobPublisher, JobWorker
    service, config, owners, _ = jobs
    identifier = small_job(jobs)
    publisher = JobPublisher(service, host='127.0.0.1', port=broker['port'], password=broker['passwords']['api'])
    with amqp_connect(broker, 'api') as channel:
        with monkeypatch.context() as patch:
            patch.setattr(service, 'mark_published', lambda *_: (_ for _ in ()).throw(psycopg.OperationalError('test lost confirmation')))
            with pytest.raises(psycopg.OperationalError):
                publisher.flush_outputs(channel)
        assert len(service.pending_outputs('api')) == 1
        publisher.flush_outputs(channel)
    calls = []
    def handler(job, checkpoint):
        calls.append(job['id'])
        return dataset_result(jobs, job, checkpoint)
    worker = JobWorker(service, 'generation', host='127.0.0.1', port=broker['port'],
                       password=broker['passwords']['generation'], handler=handler)
    try:
        with amqp_connect(broker, 'generation') as channel:
            worker.step(channel)
            worker.step(channel)
            assert channel.basic_get('coldsafe.generation', auto_ack=False)[0] is None
        assert calls == [identifier]
        assert service.get(owners[0], identifier)['status'] == 'completed'
        assert service.pending_outputs('generation') == []
        with connect(config) as conn:
            assert conn.execute('SELECT count(*) FROM datasets WHERE generation_job_id=%s', (identifier,)).fetchone() == (1,)
    finally:
        worker.close()


def test_real_amqp_worker_restart_recovers_unacked_checkpoint(jobs, broker):
    from backend.app.amqp.jobs import JobPublisher, JobWorker
    service, _, owners, _ = jobs
    identifier = small_job(jobs)
    publisher = JobPublisher(service, host='127.0.0.1', port=broker['port'], password=broker['passwords']['api'])
    with amqp_connect(broker, 'api') as channel:
        publisher.flush_outputs(channel)
    class Interrupted(BaseException):
        pass
    def stop(job, checkpoint):
        checkpoint(1)
        raise Interrupted()
    worker = JobWorker(service, 'generation', host='127.0.0.1', port=broker['port'],
                       password=broker['passwords']['generation'], handler=stop)
    try:
        with amqp_connect(broker, 'generation') as channel:
            with pytest.raises(Interrupted):
                worker.step(channel)
        assert service.get(owners[0], identifier)['completed_units'] == 1
    finally:
        worker.close()
    def resume(job, checkpoint):
        assert job['completed_units'] == 1
        return dataset_result(jobs, job, checkpoint)
    restarted = JobWorker(service, 'generation', host='127.0.0.1', port=broker['port'],
                          password=broker['passwords']['generation'], handler=resume)
    try:
        with amqp_connect(broker, 'generation') as channel:
            import time
            deadline = time.monotonic() + 5
            while service.get(owners[0], identifier)['status'] != 'completed' and time.monotonic() < deadline:
                restarted.step(channel)
                channel.connection.sleep(0.05)
        assert service.get(owners[0], identifier)['status'] == 'completed'
    finally:
        restarted.close()
