"""Jobs reject forged transport and keep durable work pending until confirmed."""
from copy import deepcopy
from threading import Event, get_ident
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock
from uuid import UUID, uuid4

import pika
import psycopg
import pytest

from backend.app.amqp.jobs import JobPublisher, JobWorker
from gateway.bridge import encode


@pytest.fixture
def requested():
    job_id = str(uuid4())
    return {'schema_version': 3, 'event_id': str(uuid4()), 'type': 'job_requested',
            'occurred_at': '2026-10-16T12:00:00Z', 'received_at': '2026-10-16T12:00:00Z',
            'device_id': None, 'device_record_id': None, 'environment_id': str(uuid4()),
            'correlation_id': job_id,
            'data': {'job_id': job_id, 'job_type': 'generation', 'dataset_id': None}}


@pytest.fixture
def worker(requested):
    service = Mock()
    service.pending_outputs.return_value = []
    service.get_requested.return_value = requested
    service.execute.return_value = True
    worker = JobWorker(service, 'generation', host='rabbitmq', port=5672, password='private')
    yield worker
    worker.close()


def deliver(channel, event, *, headers=None):
    method = SimpleNamespace(delivery_tag=9, routing_key=f"v3.job_requested.{event['data']['job_id']}")
    properties = pika.BasicProperties(content_type='application/json', delivery_mode=2,
        message_id=event['event_id'], correlation_id=event['correlation_id'],
        headers={'job_type': 'generation', **(headers or {})})
    channel.basic_get.return_value = method, properties, encode(event)
    return method, properties


def test_publisher_confirms_before_mark_and_includes_job_type(requested):
    service, channel = Mock(), MagicMock()
    service.pending_outputs.return_value = [requested]
    publisher = JobPublisher(service, host='rabbitmq', port=5672, password='private')
    channel.basic_publish.side_effect = lambda *a, **kw: service.mark_published.assert_not_called()
    publisher.flush_outputs(channel)
    service.pending_outputs.assert_called_once_with('api')
    call = channel.basic_publish.call_args
    assert call.args[:3] == ('coldsafe.events', f"v3.job_requested.{requested['data']['job_id']}", encode(requested))
    assert call.args[3].headers == {'job_type': 'generation'}
    assert call.args[3].delivery_mode == 2
    assert call.kwargs == {'mandatory': True}
    service.mark_published.assert_called_once_with(requested['event_id'])
    assert publisher.parameters.credentials.username == 'coldsafe-api'


@pytest.mark.parametrize('failure', [pika.exceptions.NackError([]), pika.exceptions.UnroutableError([])])
def test_unconfirmed_publication_stays_durable(requested, failure):
    service, channel = Mock(), Mock()
    service.pending_outputs.return_value = [requested]
    channel.basic_publish.side_effect = failure
    with pytest.raises(type(failure)):
        JobPublisher(service, host='rabbitmq', port=5672, password='private').flush_outputs(channel)
    service.mark_published.assert_not_called()


def test_worker_commits_and_flushes_before_ack(worker, requested):
    channel = MagicMock()
    deliver(channel, requested)
    worker.service.execute.side_effect = lambda *a: channel.basic_ack.assert_not_called() or True
    worker.step(channel)
    worker.service.execute.assert_called_once_with(UUID(requested['data']['job_id']), 'generation', None)
    channel.basic_ack.assert_called_once_with(9)
    assert worker.service.pending_outputs.call_count == 2
    worker.service.pending_outputs.assert_called_with('generation')
    channel.basic_get.assert_called_once_with('coldsafe.generation', auto_ack=False)
    assert worker.parameters.credentials.username == 'coldsafe-generation'


@pytest.mark.parametrize('attribute,value', [('content_type', None), ('delivery_mode', 1),
    ('message_id', str(uuid4())), ('correlation_id', str(uuid4())), ('headers', {}),
    ('headers', {'job_type': 'training'}), ('headers', {'job_type': 'generation', 'x-delivery-count': True}),
    ('headers', {'job_type': 'generation', 'x-delivery-count': -1})])
def test_invalid_metadata_is_rejected(worker, requested, attribute, value):
    channel = MagicMock()
    _, properties = deliver(channel, requested)
    setattr(properties, attribute, value)
    worker.step(channel)
    worker.service.execute.assert_not_called()
    channel.basic_reject.assert_called_once_with(9, requeue=False)


@pytest.mark.parametrize('mutation', [lambda event: event.update(type='telemetry'),
    lambda event: event.update(correlation_id=str(uuid4())),
    lambda event: event['data'].update(dataset_id=str(uuid4())),
    lambda event: event.update(environment_id=str(uuid4()))])
def test_invalid_schema_or_persisted_scope_is_rejected(worker, requested, mutation):
    event, channel = deepcopy(requested), MagicMock()
    mutation(event)
    deliver(channel, event)
    worker.step(channel)
    worker.service.execute.assert_not_called()
    channel.basic_reject.assert_called_once_with(9, requeue=False)


@pytest.mark.parametrize('raw', [b'[]', b'{"type":1,"type":2}', b'{"x":NaN}', b'x' * 8193])
def test_invalid_json_and_size_are_rejected(worker, requested, raw):
    channel = MagicMock()
    method, props = deliver(channel, requested)
    channel.basic_get.return_value = method, props, raw
    worker.step(channel)
    channel.basic_reject.assert_called_once_with(9, requeue=False)


def test_route_and_unknown_job_are_rejected(worker, requested):
    channel = MagicMock()
    method, _ = deliver(channel, requested)
    method.routing_key = f'v3.job_requested.{uuid4()}'
    worker.step(channel)
    channel.basic_reject.assert_called_once_with(9, requeue=False)
    channel.reset_mock()
    deliver(channel, requested)
    worker.service.get_requested.return_value = None
    worker.step(channel)
    channel.basic_reject.assert_called_once_with(9, requeue=False)


def test_contention_keeps_same_delivery_without_spending_retries(worker, requested):
    channel = MagicMock()
    deliver(channel, requested, headers={'x-delivery-count': 2})
    worker.service.execute.side_effect = [False, False, True]
    worker.step(channel)
    worker.step(channel)
    channel.basic_get.assert_called_once()
    channel.basic_reject.assert_not_called()
    channel.basic_ack.assert_not_called()
    worker.step(channel)
    channel.basic_ack.assert_called_once_with(9)
    assert worker.service.execute.call_count == 3


@pytest.mark.parametrize('count', [0, 1, 2])
@pytest.mark.parametrize('failure', [psycopg.OperationalError('private'), OSError('private')])
def test_transient_execution_error_keeps_last_attempt_recoverable(worker, requested, count, failure):
    channel = MagicMock()
    deliver(channel, requested, headers={'x-delivery-count': count})
    worker.service.execute.side_effect = failure
    with pytest.raises(psycopg.OperationalError):
        worker.step(channel)
    channel.basic_reject.assert_not_called()
    assert worker.pending is not None
    channel.basic_ack.assert_not_called()


def test_post_execution_publish_failure_does_not_ack(worker, requested):
    channel = MagicMock()
    deliver(channel, requested)
    worker.service.pending_outputs.side_effect = [[], [requested]]
    channel.basic_publish.side_effect = pika.exceptions.NackError([])
    with pytest.raises(pika.exceptions.NackError):
        worker.step(channel)
    channel.basic_ack.assert_not_called()
    worker.service.mark_published.assert_not_called()


def test_duplicate_terminal_job_is_acked_without_calling_handler(worker, requested):
    channel, handler = MagicMock(), Mock()
    worker.handler = handler
    deliver(channel, requested)
    # execute owns durable terminal-state checking; transport must not invoke handler itself.
    worker.step(channel)
    worker.step(channel)
    handler.assert_not_called()
    assert worker.service.execute.call_count == 2
    assert channel.basic_ack.call_count == 2


def test_long_handler_runs_off_pika_thread_and_pumps_connection(worker, requested):
    channel, released = MagicMock(), Event()
    deliver(channel, requested)
    main_thread = get_ident()
    worker.connection = MagicMock(is_open=True)
    worker.connection.process_data_events.side_effect = lambda **_: released.set()
    def execute(*_):
        assert get_ident() != main_thread
        assert released.wait(2)
        return True
    worker.service.execute.side_effect = execute
    worker.step(channel)
    worker.connection.process_data_events.assert_called()
    channel.basic_ack.assert_called_once_with(9)


def test_run_reconnects_confirms_and_closes(worker, monkeypatch):
    channel, connection, shutdown = MagicMock(), MagicMock(is_open=True), Event()
    connection.channel.return_value = channel
    channel.basic_get.return_value = None, None, None
    connection.process_data_events.side_effect = lambda **_: shutdown.set()
    connect = Mock(side_effect=[pika.exceptions.AMQPConnectionError('private'), connection])
    monkeypatch.setattr('backend.app.amqp.jobs.pika.BlockingConnection', connect)
    monkeypatch.setattr(shutdown, 'wait', lambda *_: None)
    worker.run(shutdown)
    assert connect.call_count == 2
    channel.confirm_delivery.assert_called_once()
    channel.basic_qos.assert_called_once_with(prefetch_count=1)
    connection.close.assert_called_once()
    assert not worker.is_connected


@pytest.mark.parametrize('settings', [{'host': ''}, {'port': 0}, {'password': ''}])
def test_invalid_connection_settings_fail_fast(settings):
    with pytest.raises(ValueError):
        JobPublisher(Mock(), **{'host': 'rabbitmq', 'port': 5672, 'password': 'private', **settings})


def test_worker_role_is_restricted():
    with pytest.raises(ValueError):
        JobWorker(Mock(), 'api', host='rabbitmq', port=5672, password='private')


def test_running_progress_is_published_before_handler_finishes(worker, requested):
    channel, released = MagicMock(), Event()
    deliver(channel, requested)
    worker.service.execute.side_effect = lambda *_: released.wait(2) or True
    progress = {**requested, 'type': 'job_progress'}
    worker.service.pending_outputs.side_effect = [[], [progress], []]
    channel.basic_publish.side_effect = lambda *a, **kw: released.set()
    worker.step(channel)
    assert released.is_set()
    worker.service.mark_published.assert_called_once_with(progress['event_id'])
    channel.basic_ack.assert_called_once_with(9)


def test_database_outage_in_run_keeps_delivery_and_connection(worker, requested, monkeypatch):
    channel, connection, shutdown = MagicMock(), MagicMock(is_open=True), Event()
    connection.channel.return_value = channel
    deliver(channel, requested)
    worker.service.execute.side_effect = [psycopg.OperationalError('private'), True]
    channel.basic_ack.side_effect = lambda *_: shutdown.set()
    connect = Mock(return_value=connection)
    monkeypatch.setattr('backend.app.amqp.jobs.pika.BlockingConnection', connect)
    monkeypatch.setattr(shutdown, 'wait', lambda *_: None)
    worker.run(shutdown)
    connect.assert_called_once()
    channel.basic_get.assert_called_once()
    channel.basic_reject.assert_not_called()
    channel.basic_ack.assert_called_once_with(9)
    connection.close.assert_called_once()


def test_lost_connection_waits_for_handler_and_does_not_ack(worker, requested):
    channel, released = MagicMock(), Event()
    deliver(channel, requested)
    worker.connection = MagicMock(is_open=True)
    def disconnect(**_):
        released.set()
        raise pika.exceptions.AMQPConnectionError('private')
    worker.connection.process_data_events.side_effect = disconnect
    worker.service.execute.side_effect = lambda *_: released.wait(2) or True
    with pytest.raises(pika.exceptions.AMQPConnectionError):
        worker.step(channel)
    assert released.is_set()
    channel.basic_ack.assert_not_called()


def test_handler_timeout_exception_is_not_mistaken_for_pending_future(worker, requested):
    channel = MagicMock()
    deliver(channel, requested)
    worker.service.execute.side_effect = TimeoutError('handler failed')
    with pytest.raises(TimeoutError):
        worker.execute(requested, channel)
    channel.basic_ack.assert_not_called()


def test_publisher_run_flushes_without_consuming(requested, monkeypatch):
    service, channel, connection, shutdown = Mock(), MagicMock(), MagicMock(is_open=True), Event()
    service.pending_outputs.return_value = [requested]
    service.mark_published.side_effect = lambda *_: shutdown.set()
    connection.channel.return_value = channel
    monkeypatch.setattr('backend.app.amqp.jobs.pika.BlockingConnection', Mock(return_value=connection))
    publisher = JobPublisher(service, host='rabbitmq', port=5672, password='private')
    publisher.run(shutdown)
    channel.confirm_delivery.assert_called_once()
    channel.basic_get.assert_not_called()
    service.mark_published.assert_called_once_with(requested['event_id'])


def test_disconnect_failure_clears_health(worker):
    worker.connection = MagicMock(is_open=True)
    worker.connection.close.side_effect = pika.exceptions.AMQPConnectionError('private')
    worker.disconnect()
    assert not worker.is_connected
