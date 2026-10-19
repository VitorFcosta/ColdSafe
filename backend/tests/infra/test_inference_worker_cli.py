"""CLI restores the owner model and preserves the existing worker identity."""
from unittest.mock import Mock
from uuid import UUID

import pytest
from jsonschema import ValidationError
from pydantic import SecretStr

from backend.app import inference_worker
from backend.tests.api.test_runtime_lifecycle import settings
from backend.tests.infra.test_gateway import catalog
from gateway.bridge import encode


@pytest.fixture
def configured(monkeypatch, tmp_path, catalog):
    path = tmp_path / 'catalog.json'
    path.write_bytes(encode(catalog))
    config = settings().model_copy(update={
        'rabbitmq_inference_password': SecretStr('private'), 'aiot_catalog_path': path,
        'aiot_owner_user_id': UUID('00000000-0000-4000-8000-000000000009'),
    })
    monkeypatch.setattr('sys.argv', ['inference_worker'])
    monkeypatch.setattr(inference_worker, 'RuntimeSettings', lambda: config)
    for name in ('initialize_schema', 'PostgresScope', 'ModelService', 'InferenceService', 'InferenceWorker'):
        monkeypatch.setattr(inference_worker, name, Mock())
    monkeypatch.setattr(inference_worker.signal, 'signal', Mock())
    return config


def test_restores_same_model_service_before_start_with_readonly_catalog(configured, catalog):
    config = configured
    inference_worker.main()
    inference_worker.initialize_schema.assert_called_once_with(config)
    models = inference_worker.ModelService
    models.assert_called_once_with(config, artifact_root=config.training_artifact_root)
    models.return_value.sync_active.assert_called_once_with(config.aiot_owner_user_id)
    inference_worker.InferenceService.assert_called_once_with(config, catalog,
        config.aiot_owner_user_id, models.return_value)
    inference_worker.InferenceWorker.assert_called_once_with(models.return_value,
        inference_worker.InferenceService.return_value, catalog,
        inference_worker.PostgresScope.return_value, host=config.rabbitmq_host,
        port=config.rabbitmq_port, password='private')
    scope_args = inference_worker.PostgresScope.call_args.args
    assert scope_args[0] == {
        'host': config.postgres_host, 'port': config.postgres_port, 'dbname': config.postgres_db,
        'user': config.postgres_user, 'password': config.postgres_password.get_secret_value(),
    }
    assert scope_args[1] == str(config.aiot_owner_user_id)
    worker = inference_worker.InferenceWorker.return_value
    worker.run.assert_called_once()
    assert inference_worker.signal.signal.call_count == 2
    inference_worker.signal.signal.call_args.args[1]()
    assert worker.run.call_args.args[0].is_set()
    assert config.aiot_enabled is False


@pytest.mark.parametrize('field', ['rabbitmq_inference_password', 'aiot_catalog_path', 'aiot_owner_user_id'])
def test_required_config_fails_before_database(configured, monkeypatch, field):
    monkeypatch.setattr(inference_worker, 'RuntimeSettings', lambda: configured.model_copy(update={field: None}))
    with pytest.raises(SystemExit) as error:
        inference_worker.main()
    assert error.value.code == 2
    inference_worker.initialize_schema.assert_not_called()


def test_invalid_catalog_is_rejected_before_database(configured):
    configured.aiot_catalog_path.write_text('{}')
    with pytest.raises(ValidationError):
        inference_worker.main()
    inference_worker.initialize_schema.assert_not_called()


def test_restore_finishes_before_worker_start(configured):
    inference_worker.ModelService.return_value.sync_active.side_effect = lambda *_: (
        inference_worker.InferenceWorker.assert_not_called())
    inference_worker.main()
    inference_worker.InferenceWorker.return_value.run.assert_called_once()
