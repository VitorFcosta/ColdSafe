"""Real generation artifacts and PostgreSQL linkage, without broker fixtures."""
import hashlib
import json
from uuid import UUID

import numpy as np
import pytest

from backend.app.repositories.postgres import connect
from backend.app.services.generation import GenerationHandler
from backend.app.services.jobs import JobService
from backend.tests.integration.test_jobs_integration import amqp_connect, broker, database, jobs


pytestmark = pytest.mark.integration


def generation_job(jobs, **values):
    service, _, owners, _ = jobs
    return service.create(owners[0], {
        'job_type': 'generation', 'total_units': 1_000_000, 'seed': 42, **values,
    })['id']


def persisted_manifest(jobs, identifier):
    service, config, owners, root = jobs
    state = service.get(owners[0], identifier)
    assert state['status'] == 'completed'
    assert state['completed_units'] == state['total_units'] == 1_000_000
    result = state['result_id']
    dataset = service.repository.get_dataset(owners[0], result)
    assert dataset['generation_job_id'] == identifier
    assert dataset['row_count'] == 1_000_000
    assert service.repository.get_dataset(owners[1], result) is None
    assert service.get(owners[1], identifier) is None
    path = root / dataset['artifact_key']
    assert path.is_file() and path.name == 'manifest.json'
    manifest = json.loads(path.read_text())
    assert UUID(manifest['dataset_id']) == result
    assert manifest['storage_version'] == 'offline-numpy-v1'
    assert manifest['row_count'] == 1_000_000
    assert manifest['config']['seed'] == 42
    assert manifest['equipment']
    assert manifest['blocks']
    assert sum(block['row_count'] for block in manifest['blocks']) == 1_000_000
    rows = 0
    for block in manifest['blocks']:
        block_path = path.parent / block['file']
        assert block_path.resolve().is_relative_to(path.parent.resolve())
        assert hashlib.sha256(block_path.read_bytes()).hexdigest() == block['sha256']
        data = np.load(block_path, mmap_mode='r', allow_pickle=False)
        assert len(data) == block['row_count']
        rows += len(data)
    assert rows == 1_000_000
    with connect(config) as connection:
        assert connection.execute('SELECT count(*) FROM datasets WHERE generation_job_id=%s',
                                  (identifier,)).fetchone() == (1,)
    return result


def test_real_million_row_generation_persists_private_dataset_and_blocks(jobs):
    service, config, _, root = jobs
    with connect(config) as connection:
        environment = connection.execute('INSERT INTO environments(owner_user_id,name) VALUES(%s,%s) RETURNING id',
                                         (jobs[2][0], 'Generation scope')).fetchone()[0]
    identifier = generation_job(jobs, environment_id=environment)
    assert service.execute(identifier, 'generation', GenerationHandler(config, artifact_root=root))
    result = persisted_manifest(jobs, identifier)
    dataset = service.repository.get_dataset(jobs[2][0], result)
    manifest = json.loads((root / dataset['artifact_key']).read_text())
    assert manifest['config']['environment_id'] == str(environment)
    assert service.execute(identifier, 'generation', lambda *_: pytest.fail('completed job reran'))
    assert service.get(jobs[2][0], identifier)['result_id'] == result


def test_generation_restart_keeps_progress_monotonic_and_one_dataset(jobs):
    service, config, owners, root = jobs
    identifier = generation_job(jobs)
    handler = GenerationHandler(config, artifact_root=root)

    class Interrupted(BaseException):
        pass

    def stop_after_durable_block(job, checkpoint):
        def stop(completed):
            checkpoint(completed)
            if completed > 0:
                raise Interrupted()
        return handler(job, stop)

    with pytest.raises(Interrupted):
        service.execute(identifier, 'generation', stop_after_durable_block)
    completed = service.get(owners[0], identifier)['completed_units']
    assert completed > 0
    with connect(config) as connection:
        assert connection.execute('SELECT count(*) FROM datasets WHERE generation_job_id=%s',
                                  (identifier,)).fetchone() == (0,)
    restarted = JobService(config, artifact_root=root)
    assert restarted.execute(identifier, 'generation', GenerationHandler(config, artifact_root=root))
    persisted_manifest(jobs, identifier)
    with connect(config) as connection:
        events = connection.execute('SELECT event FROM job_outbox WHERE job_id=%s AND publisher_role=%s '
                                    'ORDER BY sequence', (identifier, 'generation')).fetchall()
    progress = [event[0]['data']['completed_units'] for event in events]
    assert progress == sorted(progress)
    assert progress[-1] == 1_000_000


def test_artifact_write_failure_cannot_complete_or_register_dataset(jobs):
    service, config, owners, root = jobs
    identifier = generation_job(jobs)
    blocked_root = root / 'not-a-directory'
    blocked_root.write_text('test write failure')
    assert service.execute(identifier, 'generation', GenerationHandler(config, artifact_root=blocked_root))
    state = service.get(owners[0], identifier)
    assert (state['status'], state['error_code'], state['result_id']) == ('failed', 'GENERATION_FAILED', None)
    with connect(config) as connection:
        assert connection.execute('SELECT count(*) FROM datasets WHERE generation_job_id=%s',
                                  (identifier,)).fetchone() == (0,)


def test_real_amqp_worker_generates_dataset_and_publishes_only_progress_metadata(jobs, broker):
    from backend.app.amqp.jobs import JobPublisher, JobWorker

    service, config, _, root = jobs
    identifier = generation_job(jobs)
    publisher = JobPublisher(service, host='127.0.0.1', port=broker['port'],
                             password=broker['passwords']['api'])
    with amqp_connect(broker, 'api') as channel:
        publisher.flush_outputs(channel)
    worker = JobWorker(service, 'generation', host='127.0.0.1', port=broker['port'],
                       password=broker['passwords']['generation'],
                       handler=GenerationHandler(config, artifact_root=root))
    try:
        with amqp_connect(broker, 'generation') as channel:
            worker.step(channel)
            assert channel.basic_get('coldsafe.generation', auto_ack=False)[0] is None
        persisted_manifest(jobs, identifier)
        assert service.pending_outputs('api') == []
        assert service.pending_outputs('generation') == []
        with connect(config) as connection:
            events = connection.execute('SELECT event FROM job_outbox WHERE job_id=%s AND publisher_role=%s '
                                        'ORDER BY sequence', (identifier, 'generation')).fetchall()
        assert events[-1][0]['data']['status'] == 'completed'
        for event, in events:
            assert set(event['data']) == {
                'job_id', 'job_type', 'status', 'completed_units', 'total_units', 'error_code', 'result_id',
            }
    finally:
        worker.close()
