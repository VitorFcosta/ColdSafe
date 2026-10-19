"""A new inference process restores authorized bundles without relabeling failures."""
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

from fastapi import HTTPException
import psycopg
import pytest

from backend.app.services.model_bundle import ModelBundleUnavailable
from backend.app.services.models import ModelActivationBusy, ModelService


@pytest.fixture
def setup(monkeypatch):
    connection = MagicMock()
    connection.__enter__.return_value = connection
    monkeypatch.setattr('backend.app.services.models.connect', lambda _: connection)
    service = ModelService(None, artifact_root=Path('/unused'))
    service._lock = MagicMock(return_value=True)
    service._previous = MagicMock(return_value=uuid4())
    service._context = MagicMock(return_value=({}, {}, {}))
    loader = MagicMock(return_value=MagicMock(model_id=service._previous.return_value))
    monkeypatch.setattr('backend.app.services.models.load_model_bundle', loader)
    return service, loader, uuid4()


def test_restart_loads_once_and_reuses_until_active_pointer_changes(setup):
    service, loader, owner = setup
    first = service.sync_active(owner)
    assert first is service.sync_active(owner)
    assert service.loaded[owner] is first
    loader.assert_called_once()
    service._previous.return_value = uuid4()
    loader.return_value = MagicMock(model_id=service._previous.return_value)
    assert service.sync_active(owner) is not first
    assert loader.call_count == 2


def test_no_model_does_not_load_or_reuse_orphan_cache(setup):
    service, loader, owner = setup
    service.loaded[owner] = MagicMock()
    service._previous.return_value = None
    assert service.sync_active(owner) is None
    loader.assert_not_called()


@pytest.mark.parametrize('error', [ModelBundleUnavailable(), HTTPException(404)])
def test_failed_restore_keeps_previous_in_memory_but_returns_unavailable(setup, error):
    service, loader, owner = setup
    previous = MagicMock(model_id=uuid4())
    service.loaded[owner] = previous
    loader.side_effect = error
    assert service.sync_active(owner) is None
    assert service.loaded[owner] is previous


def test_busy_activation_is_retryable_and_never_loads(setup):
    service, loader, owner = setup
    service._lock.return_value = False
    with pytest.raises(ModelActivationBusy):
        service.sync_active(owner)
    loader.assert_not_called()


def test_database_failure_is_not_disguised_as_model_failure(setup):
    service, loader, owner = setup
    service._previous.side_effect = psycopg.OperationalError('unavailable')
    with pytest.raises(psycopg.OperationalError):
        service.sync_active(owner)
    loader.assert_not_called()
