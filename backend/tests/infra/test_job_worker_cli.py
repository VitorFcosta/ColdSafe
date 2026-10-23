from unittest.mock import Mock

import pytest
from pydantic import SecretStr

from backend.app import job_worker
from backend.tests.api.test_runtime_lifecycle import settings


@pytest.mark.parametrize('role', ['generation', 'training'])
def test_worker_cli_selects_private_credential_and_initializes_schema(role, monkeypatch):
    config = settings().model_copy(update={f'rabbitmq_{role}_password': SecretStr('test-private')})
    worker, migrate = Mock(), Mock()
    monkeypatch.setattr('sys.argv', ['job_worker', '--role', role])
    monkeypatch.setattr(job_worker, 'RuntimeSettings', lambda: config)
    monkeypatch.setattr(job_worker, 'initialize_schema', migrate)
    monkeypatch.setattr(job_worker, 'JobWorker', worker)
    monkeypatch.setattr(job_worker.signal, 'signal', Mock())
    job_worker.main()
    migrate.assert_called_once_with(config)
    assert worker.call_args.args[1] == role
    assert worker.call_args.kwargs['password'] == 'test-private'
    from backend.app.services.generation import GenerationHandler
    if role == 'generation':
        assert isinstance(worker.call_args.kwargs['handler'], GenerationHandler)
    else:
        from backend.app.services.training import TrainingHandler
        assert isinstance(worker.call_args.kwargs['handler'], TrainingHandler)
    worker.return_value.run.assert_called_once()


def test_worker_cli_requires_role_credential(monkeypatch):
    monkeypatch.setattr('sys.argv', ['job_worker', '--role', 'generation'])
    monkeypatch.setattr(job_worker, 'RuntimeSettings', settings)
    with pytest.raises(SystemExit) as error:
        job_worker.main()
    assert error.value.code == 2


def test_job_artifact_volume_is_persistent_and_only_generation_can_write():
    from pathlib import Path
    import yaml
    config = yaml.safe_load(Path('compose.jobs.yaml').read_text())
    assert 'job-artifacts' in config['volumes']
    services = config['services']
    assert services['generation']['volumes'] == ['job-artifacts:/app/artifacts']
    assert services['backend']['volumes'] == ['job-artifacts:/app/artifacts:ro',
                                               'training-artifacts:/app/training-artifacts:ro']
    assert services['training']['volumes'] == ['job-artifacts:/app/artifacts:ro',
                                                'training-artifacts:/app/training-artifacts']
    assert services['training']['mem_limit'] == '1g'
    assert services['training']['cpus'] == 1.0
    assert services['generation']['mem_limit'] == '512m'


@pytest.mark.parametrize('role', ['generation', 'training', 'models'])
def test_compose_workers_check_their_own_successful_loop(role):
    from pathlib import Path
    import yaml
    worker = yaml.safe_load(Path('compose.jobs.yaml').read_text())['services'][role]
    assert worker['environment']['COLDSAFE_HEALTHCHECK'] == '1'
    assert worker['healthcheck']['test'] == ['CMD', 'python', '-m', 'simulator.health']
    assert worker['healthcheck']['interval'] == '10s'
    assert worker['healthcheck']['timeout'] == '3s'
