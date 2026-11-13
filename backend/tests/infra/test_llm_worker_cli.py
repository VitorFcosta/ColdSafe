from unittest.mock import Mock

import pytest

from backend.app import llm_worker
from backend.tests.api.test_runtime_lifecycle import settings


def test_coordinator_cli_requires_opt_in_url(monkeypatch):
    monkeypatch.setattr('sys.argv', ['llm_worker'])
    monkeypatch.setattr(llm_worker, 'RuntimeSettings', settings)
    with pytest.raises(SystemExit) as caught:
        llm_worker.main()
    assert caught.value.code == 2


def test_coordinator_cli_runs_until_shutdown(monkeypatch):
    configured = settings().model_copy(update={'ollama_url': 'http://ollama:11434'})
    service = Mock()
    monkeypatch.setattr('sys.argv', ['llm_worker'])
    monkeypatch.setattr(llm_worker, 'RuntimeSettings', lambda: configured)
    monkeypatch.setattr(llm_worker, 'LlmService', service)
    monkeypatch.setattr(llm_worker.signal, 'signal', Mock())
    llm_worker.main()
    service.assert_called_once_with(configured)
    service.return_value.run.assert_called_once()
