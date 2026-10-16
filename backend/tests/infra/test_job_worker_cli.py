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
    worker.return_value.run.assert_called_once()


def test_worker_cli_requires_role_credential(monkeypatch):
    monkeypatch.setattr('sys.argv', ['job_worker', '--role', 'generation'])
    monkeypatch.setattr(job_worker, 'RuntimeSettings', settings)
    with pytest.raises(SystemExit) as error:
        job_worker.main()
    assert error.value.code == 2
