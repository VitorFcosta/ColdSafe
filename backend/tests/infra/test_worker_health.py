"""Worker health follows successful work loops, including long-running jobs."""
from concurrent.futures import TimeoutError
from threading import Event
from unittest.mock import Mock
from uuid import uuid4

import pika
import psycopg
import pytest

from backend.app.amqp import jobs, models
from backend.app.amqp.inference import InferenceWorker
from backend.app.services import llm


@pytest.mark.parametrize('worker_type', [jobs.JobWorker, models.ModelWorker, InferenceWorker])
@pytest.mark.parametrize('failure', [None, pika.exceptions.AMQPConnectionError(), psycopg.OperationalError()])
def test_amqp_health_requires_successful_iteration(worker_type, failure, monkeypatch):
    worker = object.__new__(worker_type)
    jobs.JobPublisher._initialize(worker, Mock(), 'inference', 'rabbitmq', 5672, 'private')
    connection, shutdown, heartbeat = Mock(is_open=True), Event(), Mock()
    worker.connection = connection
    worker.channel = Mock()
    worker.step = Mock(side_effect=failure)
    worker.close = Mock()
    monkeypatch.setattr(shutdown, 'wait', lambda *_: shutdown.set())
    monkeypatch.setattr(jobs, 'mark_healthy', heartbeat, raising=False)
    worker.run(shutdown)
    assert heartbeat.call_count == (1 if failure is None else 0)


@pytest.mark.parametrize('worker_type', [jobs.JobWorker, models.ModelWorker, InferenceWorker])
@pytest.mark.parametrize('failure', [None, pika.exceptions.AMQPConnectionError(), psycopg.OperationalError()])
def test_long_work_health_requires_pump_and_output_success(worker_type, failure, monkeypatch):
    worker = object.__new__(worker_type)
    worker.connection = Mock(is_open=True)
    worker.flush_outputs = Mock(side_effect=failure)
    future, heartbeat = Mock(), Mock()
    future.result.side_effect = [TimeoutError(), True]
    future.done.side_effect = [False, True]
    module = jobs if worker_type is jobs.JobWorker else models
    monkeypatch.setattr(module, 'mark_healthy', heartbeat, raising=False)
    if worker_type is jobs.JobWorker:
        worker.executor = Mock()
        worker.executor.submit.return_value = future
        worker.service, worker.role, worker.handler = Mock(), 'generation', None
        action = lambda: worker.execute({'data': {'job_id': str(uuid4())}}, Mock())
    else:
        action = lambda: worker._wait(future, Mock())
    if failure is None:
        assert action() is True
    else:
        with pytest.raises(type(failure)):
            action()
    assert heartbeat.call_count == (1 if failure is None else 0)


@pytest.mark.parametrize('result', [True, False, llm.OllamaUnavailable(), psycopg.OperationalError()])
def test_llm_health_tracks_completed_tick_and_legitimate_pause(result, monkeypatch):
    service, shutdown, heartbeat = llm.LlmService(Mock(ollama_url=None)), Event(), Mock()
    service.tick = Mock(side_effect=result) if isinstance(result, Exception) else Mock(return_value=result)
    monkeypatch.setattr(shutdown, 'wait', lambda *_: shutdown.set())
    monkeypatch.setattr(llm, 'mark_healthy', heartbeat, raising=False)
    service.run(shutdown)
    assert heartbeat.call_count == (0 if isinstance(result, Exception) else 1)
