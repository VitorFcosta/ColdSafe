"""Inference envelopes and durable publication share the activation worker."""
from datetime import datetime, timezone
from threading import Event, get_ident
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock
from uuid import uuid4

import pika
import psycopg
import pytest

from backend.app.amqp.inference import InferenceWorker
from backend.tests.infra.test_gateway import catalog
from backend.tests.amqp.test_models import requested
from gateway.bridge import encode
from simulator.model import Simulator, utc


@pytest.fixture
def worker(catalog, requested):
    models, inference = Mock(), Mock()
    models.pending_outputs.return_value = []
    models.get_requested.return_value = requested
    models.execute.return_value = True
    inference.pending_outputs.return_value = []
    inference.process.return_value = {'status': 'done'}
    instance = InferenceWorker(models, inference, catalog, Mock(return_value=True),
                               host='rabbitmq', port=5672, password='private')
    yield instance
    instance.close()


def delivery(channel, catalog):
    event = Simulator(catalog).sample(1)
    event['received_at'] = utc(datetime.now(timezone.utc))
    method = SimpleNamespace(delivery_tag=12, routing_key=f"v3.telemetry.{event['device_record_id']}")
    properties = pika.BasicProperties(content_type='application/json', delivery_mode=2,
        message_id=event['event_id'], correlation_id=event['correlation_id'])
    channel.basic_get.side_effect = [(None, None, None), (method, properties, encode(event))]
    return event, method, properties


def prediction(event):
    now = utc(datetime.now(timezone.utc))
    return {**event, 'event_id': str(uuid4()), 'type': 'prediction', 'occurred_at': now,
            'received_at': now, 'correlation_id': event['event_id'], 'data': {
                'source_event_id': event['event_id'],
                'equipment_id': event['data']['equipment']['equipment_id'],
                'input_received_at': event['received_at'], 'status': 'unavailable',
                'health_score': None, 'rul_hours': None, 'model_id': None,
                'model_version': None, 'features_version': 'fan-features-1', 'reason': 'no_model'}}


def test_telemetry_is_processed_off_pika_thread_before_ack(worker, catalog):
    channel = MagicMock()
    event, _, _ = delivery(channel, catalog)
    main_thread = get_ident()
    def process(value):
        assert value == event and get_ident() != main_thread
        channel.basic_ack.assert_not_called()
        return prediction(event)
    worker.inference.process.side_effect = process
    worker.step(channel)
    worker.inference.process.assert_called_once_with(event)
    worker.check_scope.assert_called_once_with(catalog)
    assert channel.basic_get.call_args_list[-1].args == ('coldsafe.inference',)
    channel.basic_ack.assert_called_once_with(12)
    assert worker.parameters.credentials.username == 'coldsafe-inference'


@pytest.mark.parametrize('mutation', [
    lambda event: event.update(received_at=None),
    lambda event: event.update(received_at='bad'),
    lambda event: event.update(correlation_id=str(uuid4())),
    lambda event: event.update(device_id='forged-device'),
    lambda event: event.update(environment_id=str(uuid4())),
    lambda event: event['data']['equipment'].update(equipment_id=str(uuid4())),
    lambda event: event['data']['measurements']['light'].update(sensor_id=str(uuid4())),
    lambda event: event['data']['actuators']['led'].update(actuator_id=str(uuid4())),
    lambda event: event['data'].update(wear=0.5),
])
def test_invalid_telemetry_is_terminal(worker, catalog, mutation):
    channel = MagicMock()
    event, method, properties = delivery(channel, catalog)
    mutation(event)
    properties.correlation_id = event['correlation_id']
    channel.basic_get.side_effect = [(None, None, None), (method, properties, encode(event))]
    worker.step(channel)
    worker.inference.process.assert_not_called()
    channel.basic_reject.assert_called_once_with(12, requeue=False)


@pytest.mark.parametrize('key,value', [('content_type', None), ('delivery_mode', 1),
    ('message_id', str(uuid4())), ('correlation_id', str(uuid4())),
    ('headers', {'x-delivery-count': True}), ('headers', {'x-delivery-count': -1}),
    ('headers', {'x-delivery-count': '1'})])
def test_invalid_metadata_is_terminal(worker, catalog, key, value):
    channel = MagicMock()
    _, _, properties = delivery(channel, catalog)
    setattr(properties, key, value)
    worker.step(channel)
    worker.inference.process.assert_not_called()
    channel.basic_reject.assert_called_once_with(12, requeue=False)


@pytest.mark.parametrize('raw', [b'[]', b'{"x":1,"x":2}', b'{"x":NaN}', b'\xff', b'x'*8193])
def test_malformed_json_is_terminal(worker, catalog, raw):
    channel = MagicMock()
    _, method, properties = delivery(channel, catalog)
    channel.basic_get.side_effect = [(None, None, None), (method, properties, raw)]
    worker.step(channel)
    worker.inference.process.assert_not_called()
    channel.basic_reject.assert_called_once_with(12, requeue=False)


def test_wrong_route_and_revoked_owner_rejected(worker, catalog):
    channel = MagicMock()
    _, method, _ = delivery(channel, catalog)
    method.routing_key = 'v3.telemetry.' + str(uuid4())
    worker.step(channel)
    channel.basic_reject.assert_called_once_with(12, requeue=False)
    channel.reset_mock()
    delivery(channel, catalog)
    worker.check_scope.return_value = False
    worker.step(channel)
    channel.basic_reject.assert_called_once_with(12, requeue=False)
    worker.inference.process.assert_not_called()


@pytest.mark.parametrize('where', ['check_scope', 'process'])
def test_database_outage_keeps_delivery(worker, catalog, where):
    channel = MagicMock()
    delivery(channel, catalog)
    target = worker.check_scope if where == 'check_scope' else worker.inference.process
    target.side_effect = psycopg.OperationalError('private password')
    with pytest.raises(psycopg.OperationalError):
        worker.step(channel)
    assert worker.inference_pending is not None
    channel.basic_ack.assert_not_called()
    channel.basic_reject.assert_not_called()


def test_confirm_before_mark_and_ack(worker, catalog):
    channel = MagicMock()
    event, _, _ = delivery(channel, catalog)
    output = prediction(event)
    outputs = []
    worker.inference.pending_outputs.side_effect = lambda: list(outputs)
    worker.inference.process.side_effect = lambda *_: outputs.append(output) or output
    def publish(*args, **kwargs):
        worker.inference.mark_published.assert_not_called()
        channel.basic_ack.assert_not_called()
        assert args[1] == f"v3.prediction.{event['device_record_id']}"
        assert args[3].message_id == output['event_id']
        assert args[3].correlation_id == event['event_id']
        assert args[3].content_type == 'application/json' and args[3].delivery_mode == 2
        assert kwargs['mandatory'] is True
    channel.basic_publish.side_effect = publish
    worker.step(channel)
    worker.inference.mark_published.assert_called_once_with(output['event_id'])
    channel.basic_ack.assert_called_once_with(12)


@pytest.mark.parametrize('failure', [pika.exceptions.NackError([]), pika.exceptions.UnroutableError([])])
def test_unconfirmed_output_remains_pending(worker, catalog, failure):
    channel = MagicMock()
    event, _, _ = delivery(channel, catalog)
    output = prediction(event)
    worker.inference.pending_outputs.side_effect = [[], [output]]
    channel.basic_publish.side_effect = failure
    with pytest.raises(type(failure)):
        worker.step(channel)
    channel.basic_ack.assert_not_called()
    worker.inference.mark_published.assert_not_called()


def test_invalid_outgoing_prediction_is_never_published(worker, catalog):
    channel = MagicMock()
    event, _, _ = delivery(channel, catalog)
    output = prediction(event)
    output['data']['health_score'] = 99
    worker.inference.pending_outputs.return_value = [output]
    with pytest.raises(ValueError):
        worker.step(channel)
    channel.basic_publish.assert_not_called()
    worker.inference.mark_published.assert_not_called()


def test_activation_copy_uses_same_service_and_busy_delivery_is_retained(worker, requested):
    channel = MagicMock()
    method = SimpleNamespace(delivery_tag=13, routing_key=f"v3.model_activation.{requested['data']['model_id']}")
    properties = pika.BasicProperties(content_type='application/json', delivery_mode=2,
        message_id=requested['event_id'], correlation_id=requested['correlation_id'])
    channel.basic_get.side_effect = [(None, None, None), (method, properties, encode(requested)),
                                     (None, None, None)]
    worker.service.execute.side_effect = [False, True]
    worker.step(channel)
    channel.basic_ack.assert_not_called()
    worker.step(channel)
    assert channel.basic_get.call_count == 3
    channel.basic_ack.assert_called_once_with(13)
    assert worker.service.execute.call_count == 2


def test_slow_inference_pumps_heartbeat(worker, catalog):
    channel, released = MagicMock(), Event()
    delivery(channel, catalog)
    worker.connection = MagicMock(is_open=True)
    worker.connection.process_data_events.side_effect = lambda **_: released.set()
    worker.inference.process.side_effect = lambda *_: released.wait(2) or True
    worker.step(channel)
    assert released.is_set()
    channel.basic_ack.assert_called_once_with(12)


def test_disconnect_clears_both_deliveries(worker):
    worker.pending = (Mock(), Mock(), b'')
    worker.inference_pending = (Mock(), Mock(), b'')
    worker.disconnect()
    assert worker.pending is None and worker.inference_pending is None


def test_owner_lock_contention_retries_same_delivery_without_ack(worker, catalog):
    from backend.app.services.models import ModelActivationBusy
    channel = MagicMock()
    event, _, _ = delivery(channel, catalog)
    worker.inference.process.side_effect = [ModelActivationBusy('busy'), prediction(event)]
    worker.step(channel)
    assert worker.inference_pending is not None
    channel.basic_ack.assert_not_called()
    channel.basic_reject.assert_not_called()
    channel.basic_get.side_effect = [(None, None, None)]
    worker.step(channel)
    assert worker.inference.process.call_count == 2
    channel.basic_ack.assert_called_once_with(12)


def test_empty_queues_do_not_ack(worker):
    channel = MagicMock()
    channel.basic_get.return_value = None, None, None
    worker.step(channel)
    channel.basic_ack.assert_not_called()
    assert worker.inference_pending is None


def test_inference_connection_loss_waits_for_running_process(worker, catalog):
    channel, released = MagicMock(), Event()
    delivery(channel, catalog)
    worker.connection = MagicMock(is_open=True)
    def disconnect(**_):
        released.set()
        raise pika.exceptions.AMQPConnectionError('private')
    worker.connection.process_data_events.side_effect = disconnect
    worker.inference.process.side_effect = lambda *_: released.wait(2) or True
    with pytest.raises(pika.exceptions.AMQPConnectionError):
        worker.step(channel)
    assert released.is_set()
    channel.basic_ack.assert_not_called()
