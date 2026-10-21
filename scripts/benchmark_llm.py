"""Assert the B2-30 lifecycle inside a disposable, offline Docker test client.

Run with the backend image, current app/migrations mounted read-only, writable
artifact volumes, OLLAMA_URL=http://ollama:11434 and private PostgreSQL settings.
POSTGRES_DB must start with coldsafe_b230_; never target personal databases.
Phases: initial, workloads, unavailable, recovered, restarted, automatic, model_missing.
The caller controls Compose stop/restart/empty-volume transitions between phases.
Each phase writes its measured result to stdout; no credentials are printed.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import resource
import time
from urllib.request import Request
from uuid import UUID, uuid4


STATE = Path('/tmp/coldsafe-b230-state.json')


def settings():
    from backend.app.config.settings import RuntimeSettings
    result = RuntimeSettings(_env_file=None)
    if not result.postgres_db.startswith('coldsafe_b230_') or result.ollama_url != 'http://ollama:11434':
        raise ValueError('Use only the private disposable B2-30 Compose test infrastructure')
    return result


def save(state):
    STATE.write_text(json.dumps(state))


def timed(operation):
    start = time.perf_counter()
    result = operation()
    return result, round(time.perf_counter() - start, 6)


def response_probe(client):
    from backend.app.services.llm import MODEL
    payload = {'model': MODEL, 'prompt': 'Responda apenas com a palavra pronto.',
               'keep_alive': -1, 'stream': True,
               'options': {'num_ctx': 1024, 'num_gpu': 0, 'num_thread': 2,
                           'num_predict': 32, 'temperature': 0, 'seed': 42}}
    request = Request(client.url + '/api/generate', data=json.dumps(payload).encode(),
                      headers={'Content-Type': 'application/json'})
    start = time.perf_counter()
    first = None
    fragments = []
    with client.opener.open(request, timeout=180) as stream:
        for line in stream:
            event = json.loads(line)
            if event.get('response'):
                first = first if first is not None else time.perf_counter() - start
                fragments.append(event['response'])
            if event.get('done'):
                final = event
                break
        else:
            raise AssertionError('Incomplete local model response')
    assert first is not None and fragments
    return {'first_token_seconds': round(first, 6),
            'total_seconds': round(time.perf_counter() - start, 6),
            'text': ''.join(fragments), 'eval_count': final.get('eval_count'),
            'load_duration_ns': final.get('load_duration'),
            'prompt_is_fixed_public_fixture': True}


def initial(config):
    from backend.app.repositories.postgres import connect
    from backend.app.services.llm import LlmService
    service = LlmService(config)
    assert service.client.loaded() == []
    assert service.status()['state'] == 'loading'
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(timed, service.tick)
        observed_loading = False
        deadline = time.monotonic() + 180
        while not future.done() and time.monotonic() < deadline:
            observed_loading |= service.status()['state'] == 'loading'
            time.sleep(0.05)
        ok, seconds = future.result(timeout=5)
    assert ok and observed_loading and service.status()['state'] == 'ready'
    with connect(config) as connection:
        owner = connection.execute("INSERT INTO users(email,password_hash,role) "
            "VALUES(%s,'test-fixture','admin') RETURNING id", (f'{uuid4()}@example.invalid',)).fetchone()[0]
    save({'owner': str(owner)})
    return {'preload_seconds': seconds, 'loading_observed': observed_loading,
            'ps': service.client.loaded(), 'tags': service.client.request('/api/tags'),
            'response': response_probe(service.client)}


def workloads(config):
    from backend.app.services.generation import GenerationHandler
    from backend.app.services.jobs import JobService
    from backend.app.services.llm import LlmService
    from backend.app.services.training import TrainingHandler
    state = json.loads(STATE.read_text())
    owner = UUID(state['owner'])
    jobs = JobService(config, artifact_root=config.job_artifact_root,
                      training_artifact_root=config.training_artifact_root)
    llm = LlmService(config)
    report = {}

    def execute(kind, payload, handler):
        job = jobs.create(owner, payload)
        checks = []

        def check():
            assert llm.client.loaded() == [], 'LLM remained loaded during a heavy job'
            assert llm.status()['state'] == 'paused'
            assert llm.tick() is False, 'Coordinator preloaded while job held the lock'
            checks.append(time.monotonic())

        def checked(row, checkpoint):
            check()

            def checked_checkpoint(completed):
                check()
                checkpoint(completed)
            return handler(row, checked_checkpoint)

        handled, seconds = timed(lambda: jobs.execute(job['id'], kind, checked))
        assert handled
        result = jobs.get(owner, job['id'])
        assert result['status'] == 'completed', result
        assert checks and llm.client.loaded() == []
        loaded, reload_seconds = timed(llm.tick)
        assert loaded and llm.status()['state'] == 'ready'
        report[kind] = {'job_id': str(job['id']), 'result_id': str(result['result_id']),
                        'seconds': seconds, 'unloaded_checks': len(checks),
                        'reload_seconds': reload_seconds, 'status': result['status']}
        return result

    generation = execute('generation', {'job_type': 'generation', 'total_units': 1_000_000,
        'seed': 42}, GenerationHandler(config, artifact_root=config.job_artifact_root))
    execute('training', {'job_type': 'training', 'dataset_id': generation['result_id']},
        TrainingHandler(config, artifact_root=config.job_artifact_root,
                        training_artifact_root=config.training_artifact_root))
    failed = jobs.create(owner, {'job_type': 'generation', 'total_units': 1_000_000})

    def fail(row, checkpoint):
        assert llm.client.loaded() == [] and llm.status()['state'] == 'paused'
        raise RuntimeError('Intentional executor failure fixture')
    assert jobs.execute(failed['id'], 'generation', fail)
    assert jobs.get(owner, failed['id'])['status'] == 'failed'
    assert llm.tick() and llm.status()['state'] == 'ready'
    report['executor_failure_recovers'] = True
    report['self_peak_rss_bytes'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
    report['child_peak_rss_bytes'] = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss * 1024
    return report


def unavailable(config):
    from backend.app.services.jobs import JobService
    from backend.app.services.llm import LlmService
    state = json.loads(STATE.read_text())
    owner = UUID(state['owner'])
    jobs = JobService(config, artifact_root=config.job_artifact_root)
    job = jobs.create(owner, {'job_type': 'generation', 'total_units': 1_000_000})
    assert LlmService(config).status()['state'] == 'unavailable'

    def forbidden(*args):
        raise AssertionError('Heavy handler must not start if unload cannot be confirmed')
    for _ in range(2):
        assert jobs.execute(job['id'], 'generation', forbidden) is False
        assert jobs.get(owner, job['id'])['status'] == 'queued'
    state['pending_job'] = str(job['id'])
    save(state)
    return {'state': 'unavailable', 'attempts': 2, 'job_still_queued': True,
            'handler_never_entered': True}


def recovered(config):
    from backend.app.services.generation import GenerationHandler
    from backend.app.services.jobs import JobService
    from backend.app.services.llm import LlmService
    state = json.loads(STATE.read_text())
    owner = UUID(state['owner'])
    jobs = JobService(config, artifact_root=config.job_artifact_root)
    assert jobs.execute(UUID(state['pending_job']), 'generation',
        GenerationHandler(config, artifact_root=config.job_artifact_root))
    assert jobs.get(owner, UUID(state['pending_job']))['status'] == 'completed'
    llm = LlmService(config)
    ok, seconds = timed(llm.tick)
    assert ok and llm.status()['state'] == 'ready'
    return {'pending_job_completed': True, 'preload_seconds': seconds}


def restarted(config):
    from backend.app.services.llm import LlmService
    llm = LlmService(config)
    assert llm.client.loaded() == [] and llm.client.installed()
    assert llm.status()['state'] == 'loading'
    ok, seconds = timed(llm.tick)
    assert ok and llm.status()['state'] == 'ready'
    return {'preload_seconds': seconds, 'weights_survived_restart': True,
            'ps': llm.client.loaded(), 'response': response_probe(llm.client)}


def automatic(config):
    from backend.app.services.generation import GenerationHandler
    from backend.app.services.jobs import JobService
    from backend.app.services.llm import LlmService
    state = json.loads(STATE.read_text())
    owner = UUID(state['owner'])
    jobs = JobService(config, artifact_root=config.job_artifact_root)
    llm = LlmService(config)
    assert llm.status()['state'] == 'ready'
    job = jobs.create(owner, {'job_type': 'generation', 'total_units': 1_000_000})
    handler = GenerationHandler(config, artifact_root=config.job_artifact_root)
    checks = []

    def checked(row, checkpoint):
        assert llm.client.loaded() == [] and llm.status()['state'] == 'paused'
        checks.append(True)
        return handler(row, checkpoint)
    assert jobs.execute(job['id'], 'generation', checked)
    assert checks and jobs.get(owner, job['id'])['status'] == 'completed'
    start = time.perf_counter()
    deadline = time.monotonic() + 180
    while llm.status()['state'] != 'ready' and time.monotonic() < deadline:
        time.sleep(0.1)
    assert llm.status()['state'] == 'ready'
    return {'real_llm_worker_process_running': True, 'no_manual_tick': True,
            'job_completed': True, 'automatic_reload_seconds': round(time.perf_counter() - start, 6)}


def model_missing(config):
    from backend.app.services.llm import LlmService
    llm = LlmService(config)
    assert llm.client.loaded() == []
    assert llm.status()['state'] == 'model_missing'
    assert llm.tick() is False
    assert not llm.client.installed()
    return {'state': 'model_missing', 'no_automatic_download': True}


def main():
    phases = {function.__name__: function for function in
              (initial, workloads, unavailable, recovered, restarted, automatic, model_missing)}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=tuple(phases))
    args = parser.parse_args()
    from backend.app.repositories.postgres import initialize_schema
    config = settings()
    initialize_schema(config)
    report = json.dumps(phases[args.phase](config), allow_nan=False, indent=2)
    Path(f'/tmp/coldsafe-b230-{args.phase}.json').write_text(report + '\n')
    print(report)


if __name__ == '__main__':
    main()
