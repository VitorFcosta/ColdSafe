"""Activation transport preserves durable work and rejects forged envelopes."""
from copy import deepcopy
from threading import Event, get_ident
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock
from uuid import UUID, uuid4

import pika
import psycopg
import pytest

from backend.app.amqp.models import ModelPublisher, ModelWorker
from gateway.bridge import encode


@pytest.fixture
def requested():
    activation_id = str(uuid4())
    return {'schema_version': 3, 'event_id': str(uuid4()), 'type': 'model_activation',
            'occurred_at': '2026-10-18T12:00:00Z', 'received_at': '2026-10-18T12:00:00Z',
            'device_id': None, 'device_record_id': None, 'environment_id': None,
            'correlation_id': activation_id,
            'data': {'activation_id': activation_id, 'model_id': str(uuid4()),
                     'model_version': 'fan-model-1', 'features_version': 'fan-features-1',
                     'previous_active_model_id': None}}


@pytest.fixture
def worker(requested):
    service = Mock()
    service.pending_outputs.return_value = []
    service.get_requested.return_value = requested
    service.execute.return_value = True
    worker = ModelWorker(service, host='rabbitmq', port=5672, password='private')
    yield worker
    worker.close()


def deliver(channel, event, *, headers=None):
    method = SimpleNamespace(delivery_tag=9, routing_key=f"v3.model_activation.{event['data']['model_id']}")
    props = pika.BasicProperties(content_type='application/json', delivery_mode=2,
        message_id=event['event_id'], correlation_id=event['correlation_id'], headers=headers)
    channel.basic_get.return_value = method, props, encode(event)
    return method, props


@pytest.mark.parametrize('role', ['api', 'inference'])
def test_publisher_marks_only_confirmed_persistent_event_and_has_no_job_header(requested, role):
    service, channel = Mock(), Mock()
    service.pending_outputs.return_value = [requested]
    publisher = ModelPublisher(service, host='rabbitmq', port=5672, password='private', role=role)
    channel.basic_publish.side_effect = lambda *a, **kw: service.mark_published.assert_not_called()
    publisher.flush_outputs(channel)
    service.pending_outputs.assert_called_once_with(role)
    call = channel.basic_publish.call_args
    assert call.args[:3] == ('coldsafe.events',
        f"v3.model_activation.{requested['data']['model_id']}", encode(requested))
    props = call.args[3]
    assert props.content_type == 'application/json' and props.delivery_mode == 2
    assert props.message_id == requested['event_id']
    assert props.correlation_id == requested['correlation_id']
    assert not props.headers
    assert call.kwargs == {'mandatory': True}
    assert publisher.parameters.credentials.username == f'coldsafe-{role}'
    service.mark_published.assert_called_once_with(requested['event_id'])


@pytest.mark.parametrize('failure', [pika.exceptions.NackError([]), pika.exceptions.UnroutableError([])])
def test_unconfirmed_event_remains_durable(requested, failure):
    service, channel = Mock(), Mock()
    service.pending_outputs.return_value = [requested]
    channel.basic_publish.side_effect = failure
    with pytest.raises(type(failure)):
        ModelPublisher(service, host='rabbitmq', port=5672, password='private').flush_outputs(channel)
    service.mark_published.assert_not_called()


def test_worker_uses_activation_queue_and_flushes_before_ack(worker, requested):
    channel = MagicMock()
    deliver(channel, requested)
    worker.service.execute.side_effect = lambda *a: channel.basic_ack.assert_not_called() or True
    worker.step(channel)
    worker.service.execute.assert_called_once_with(UUID(requested['data']['activation_id']))
    worker.service.get_requested.assert_called_once_with(UUID(requested['data']['activation_id']))
    worker.service.pending_outputs.assert_called_with('inference')
    assert worker.service.pending_outputs.call_count == 2
    channel.basic_get.assert_called_once_with('coldsafe.model-activation', auto_ack=False)
    channel.basic_ack.assert_called_once_with(9)
    assert worker.parameters.credentials.username == 'coldsafe-inference'


@pytest.mark.parametrize('attribute,value', [('content_type', None), ('delivery_mode', 1),
    ('message_id', str(uuid4())), ('correlation_id', str(uuid4())),
    ('headers', {'x-delivery-count': True}), ('headers', {'x-delivery-count': -1}),
    ('headers', {'x-delivery-count': '1'})])
def test_invalid_properties_rejected(worker, requested, attribute, value):
    channel = MagicMock()
    _, props = deliver(channel, requested)
    setattr(props, attribute, value)
    worker.step(channel)
    worker.service.execute.assert_not_called()
    channel.basic_reject.assert_called_once_with(9, requeue=False)


@pytest.mark.parametrize('mutation', [lambda event: event.update(type='telemetry'),
    lambda event: event.update(correlation_id=str(uuid4())),
    lambda event: event['data'].update(features_version='unknown'),
    lambda event: event.update(environment_id=str(uuid4()))])
def test_invalid_schema_or_scope_rejected(worker, requested, mutation):
    event, channel = deepcopy(requested), MagicMock()
    mutation(event)
    deliver(channel, event)
    worker.step(channel)
    worker.service.execute.assert_not_called()
    channel.basic_reject.assert_called_once_with(9, requeue=False)


@pytest.mark.parametrize('raw', [b'[]', b'{"type":1,"type":2}', b'{"x":NaN}', b'x' * 8193])
def test_invalid_json_rejected(worker, requested, raw):
    channel = MagicMock()
    method, props = deliver(channel, requested)
    channel.basic_get.return_value = method, props, raw
    worker.step(channel)
    channel.basic_reject.assert_called_once_with(9, requeue=False)


def test_wrong_route_and_unknown_activation_rejected(worker, requested):
    channel = MagicMock()
    method, _ = deliver(channel, requested)
    method.routing_key = f'v3.model_activation.{uuid4()}'
    worker.step(channel)
    channel.basic_reject.assert_called_once_with(9, requeue=False)
    channel.reset_mock()
    deliver(channel, requested)
    worker.service.get_requested.return_value = None
    worker.step(channel)
    channel.basic_reject.assert_called_once_with(9, requeue=False)


def test_busy_lock_keeps_delivery_without_spending_retries(worker, requested):
    channel = MagicMock()
    deliver(channel, requested, headers={'x-delivery-count': 2})
    worker.service.execute.side_effect = [False, True]
    worker.step(channel)
    channel.basic_ack.assert_not_called()
    channel.basic_reject.assert_not_called()
    worker.step(channel)
    channel.basic_get.assert_called_once()
    channel.basic_ack.assert_called_once_with(9)


@pytest.mark.parametrize('failure', [psycopg.OperationalError('private'), OSError('private')])
def test_database_outage_preserves_delivery(worker, requested, failure):
    channel = MagicMock()
    deliver(channel, requested)
    worker.service.execute.side_effect = failure
    with pytest.raises(psycopg.OperationalError):
        worker.step(channel)
    assert worker.pending is not None
    channel.basic_ack.assert_not_called()
    channel.basic_reject.assert_not_called()


def test_failed_status_publication_does_not_ack(worker, requested):
    channel = MagicMock()
    deliver(channel, requested)
    worker.service.pending_outputs.side_effect = [[], [requested]]
    channel.basic_publish.side_effect = pika.exceptions.NackError([])
    with pytest.raises(pika.exceptions.NackError):
        worker.step(channel)
    channel.basic_ack.assert_not_called()
    worker.service.mark_published.assert_not_called()


def test_loading_is_off_pika_thread_and_pumps_heartbeat(worker, requested):
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


def test_connection_loss_waits_for_loader_and_does_not_ack(worker, requested):
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


def test_loader_timeout_is_not_mistaken_for_pending_future(worker, requested):
    worker.service.execute.side_effect = TimeoutError('loader failed')
    with pytest.raises(TimeoutError):
        worker.execute(requested, MagicMock())


def test_empty_queue_and_disconnect_clear_delivery(worker):
    channel = MagicMock()
    channel.basic_get.return_value = None, None, None
    worker.step(channel)
    assert worker.pending is None
    worker.pending = (Mock(), Mock(), b'')
    worker.disconnect()
    assert worker.pending is None


def test_publisher_role_restricted():
    with pytest.raises(ValueError):
        ModelPublisher(Mock(), host='rabbitmq', port=5672, password='private', role='training')


def test_loading_status_is_published_before_loader_finishes(worker, requested):
    channel, released = MagicMock(), Event()
    deliver(channel, requested)
    worker.service.execute.side_effect = lambda *_: released.wait(2) or True
    progress = {**requested, 'type': 'model_status'}
    worker.service.pending_outputs.side_effect = [[], [progress], []]
    channel.basic_publish.side_effect = lambda *a, **kw: released.set()
    worker.step(channel)
    assert released.is_set()
    worker.service.mark_published.assert_called_once_with(progress['event_id'])
    channel.basic_ack.assert_called_once_with(9)


def test_run_retains_connection_and_delivery_during_database_outage(worker, requested, monkeypatch):
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
    channel.confirm_delivery.assert_called_once()
    channel.basic_get.assert_called_once()
    channel.basic_reject.assert_not_called()
    channel.basic_ack.assert_called_once_with(9)
    connection.close.assert_called_once()


def test_api_publisher_run_does_not_consume(requested, monkeypatch):
    service, channel, connection, shutdown = Mock(), MagicMock(), MagicMock(is_open=True), Event()
    service.pending_outputs.return_value = [requested]
    service.mark_published.side_effect = lambda *_: shutdown.set()
    connection.channel.return_value = channel
    monkeypatch.setattr('backend.app.amqp.jobs.pika.BlockingConnection', Mock(return_value=connection))
    publisher = ModelPublisher(service, host='rabbitmq', port=5672, password='private')
    publisher.run(shutdown)
    channel.confirm_delivery.assert_called_once()
    channel.basic_get.assert_not_called()
    service.mark_published.assert_called_once_with(requested['event_id'])
