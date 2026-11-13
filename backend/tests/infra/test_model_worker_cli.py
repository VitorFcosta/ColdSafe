from unittest.mock import Mock

import pytest
from pydantic import SecretStr

from backend.app import model_worker
from backend.tests.api.test_runtime_lifecycle import settings


def test_model_worker_uses_inference_credential_and_shared_read_volume(monkeypatch):
    config = settings().model_copy(update={'rabbitmq_inference_password': SecretStr('private')})
    worker, migrate, service = Mock(), Mock(), Mock()
    monkeypatch.setattr('sys.argv', ['model_worker'])
    monkeypatch.setattr(model_worker, 'RuntimeSettings', lambda: config)
    monkeypatch.setattr(model_worker, 'initialize_schema', migrate)
    monkeypatch.setattr(model_worker, 'ModelWorker', worker)
    monkeypatch.setattr(model_worker, 'ModelService', service)
    monkeypatch.setattr(model_worker.signal, 'signal', Mock())
    model_worker.main()
    migrate.assert_called_once_with(config)
    service.assert_called_once_with(config, artifact_root=config.training_artifact_root)
    worker.assert_called_once_with(service.return_value, host=config.rabbitmq_host,
                                   port=config.rabbitmq_port, password='private')
    worker.return_value.run.assert_called_once()
    assert model_worker.signal.signal.call_count == 2


def test_model_worker_requires_private_inference_credential(monkeypatch):
    monkeypatch.setattr('sys.argv', ['model_worker'])
    monkeypatch.setattr(model_worker, 'RuntimeSettings', settings)
    with pytest.raises(SystemExit) as error:
        model_worker.main()
    assert error.value.code == 2
