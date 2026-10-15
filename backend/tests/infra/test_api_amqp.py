"""Strict AMQP boundaries and durable-before-ACK delivery without network services."""
from datetime import datetime, timezone
import json
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock
from uuid import uuid4

import pika
import psycopg
import pytest

from backend.app.amqp.consumer import ApiAmqpConsumer
from backend.tests.infra.test_gateway import catalog
from gateway.bridge import PermanentError, encode
from simulator.model import Simulator, utc


@pytest.fixture
def worker(catalog):
    service = Mock()
    service.pending_outputs.return_value = []
    service.persisted_telemetry.return_value = None
    service.linked_prediction.return_value = None
    service.prediction_for_source.return_value = None
    service.trusted_output.return_value = False
    worker = ApiAmqpConsumer(service, catalog, Mock(return_value=True), Mock(),
                             amqp_host='rabbitmq', amqp_port=5672,
                             password_commands='private-c', password_delivery='private-d')
    worker.channels = {role: MagicMock() for role in ('commands', 'delivery')}
    return worker


def deliver(worker, catalog, role='commands', event=None, headers=None):
    event = event or Simulator(catalog).sample(1)
    event['received_at'] = event['received_at'] or utc(datetime.now(timezone.utc))
    properties = pika.BasicProperties(content_type='application/json', delivery_mode=2,
        message_id=event['event_id'], correlation_id=event['correlation_id'], headers=headers)
    method = SimpleNamespace(delivery_tag=5,
        routing_key=f"v3.{event['type']}.{event['device_record_id']}")
    worker.channels[role].basic_get.return_value = method, properties, encode(event)
    return event, method, properties


def test_process_commits_before_ack_and_commands_never_emit(worker, catalog):
    event, _, _ = deliver(worker, catalog)
    worker.service.process.side_effect = lambda _: worker.channels['commands'].basic_ack.assert_not_called()
    worker.consume('commands')
    worker.service.process.assert_called_once_with(event)
    worker.channels['commands'].basic_ack.assert_called_once_with(5)
    worker.emit.assert_not_called()


def test_delivery_never_emits_unpersisted_telemetry(worker, catalog):
    deliver(worker, catalog, 'delivery')
    worker.consume('delivery')
    worker.emit.assert_not_called()
    worker.channels['delivery'].basic_ack.assert_called_once_with(5)


def test_receipt_releases_original_persisted_envelope(worker, catalog):
    source, _, _ = deliver(worker, catalog, 'delivery')
    receipt = {**source, 'event_id': str(uuid4()),
               'type': 'telemetry_persisted', 'correlation_id': source['event_id'],
               'data': {'source_event_id': source['event_id'],
                        'equipment_id': catalog['equipment_id'], 'input_received_at': source['received_at']}}
    deliver(worker, catalog, 'delivery', receipt)
    worker.service.persisted_telemetry.return_value = source
    worker.consume('delivery')
    worker.service.process.assert_called_once_with(receipt)
    worker.service.persisted_telemetry.assert_called_once_with(source['event_id'])
    worker.emit.assert_called_once_with(source)


def test_source_arriving_after_receipt_is_also_delivered(worker, catalog):
    source, _, _ = deliver(worker, catalog, 'delivery')
    worker.service.persisted_telemetry.return_value = source
    worker.consume('delivery')
    worker.emit.assert_called_once_with(source)


def test_duplicate_source_or_repeated_receipt_never_duplicates_web_reading(worker, catalog):
    source, _, _ = deliver(worker, catalog, 'delivery')
    worker.service.persisted_telemetry.return_value = source
    worker.consume('delivery')
    worker.consume('delivery')
    worker.emit.assert_called_once_with(source)


def test_persisted_reading_releases_deferred_prediction_only_once(worker, catalog):
    source, _, _ = deliver(worker, catalog, 'delivery')
    prediction = {**source, 'type': 'prediction', 'event_id': str(uuid4())}
    worker.service.persisted_telemetry.return_value = source
    worker.service.prediction_for_source.return_value = prediction
    worker.consume('delivery')
    worker.consume('delivery')
    assert [call.args[0] for call in worker.emit.call_args_list] == [source, prediction]


def test_outputs_without_durable_outbox_proof_never_emit(worker, catalog):
    source, _, _ = deliver(worker, catalog, 'delivery')
    event = {**source, 'type': 'freshness', 'data': {'last_event_id': source['event_id'],
             'last_received_at': source['received_at'], 'state': 'fresh', 'age_seconds': 0,
             'stale_after_seconds': 30}}
    deliver(worker, catalog, 'delivery', event)
    worker.consume('delivery')
    worker.emit.assert_not_called()
    worker.service.trusted_output.return_value = True
    worker.consume('delivery')
    worker.emit.assert_called_once_with(event)


def test_prediction_requires_linked_persisted_fresh_source(worker, catalog):
    source, _, _ = deliver(worker, catalog, 'delivery')
    cases = json.loads((Path(__file__).resolve().parents[3] / 'contracts/examples/aiot.valid.json').read_text())
    prediction = next(case['payload'] for case in cases if case['payload'].get('type') == 'prediction')
    prediction.update({key: source[key] for key in ('device_id', 'device_record_id', 'environment_id', 'correlation_id')})
    prediction['data'].update(source_event_id=source['event_id'], equipment_id=catalog['equipment_id'],
                              input_received_at=source['received_at'])
    deliver(worker, catalog, 'delivery', prediction)
    worker.consume('delivery')
    worker.emit.assert_not_called()
    worker.service.linked_prediction.assert_called_once_with(prediction['event_id'])
    worker.service.linked_prediction.return_value = prediction
    worker.consume('delivery')
    worker.emit.assert_called_once_with(prediction)


@pytest.mark.parametrize('key,value', [('content_type', None), ('delivery_mode', 1),
    ('message_id', 'private'), ('correlation_id', 'private')])
def test_message_properties_must_match_envelope(worker, catalog, key, value):
    _, _, properties = deliver(worker, catalog)
    setattr(properties, key, value)
    worker.consume('commands')
    worker.service.process.assert_not_called()
    error = json.loads(worker.channels['commands'].basic_publish.call_args.args[2])
    assert error['data']['code'] == 'INVALID_BINDING'


def test_scope_revocation_is_rechecked_before_processing(worker, catalog):
    deliver(worker, catalog)
    worker.check_scope.return_value = False
    worker.consume('commands')
    worker.service.process.assert_not_called()
    assert json.loads(worker.channels['commands'].basic_publish.call_args.args[2])['data']['code'] == 'UNAUTHORIZED_SCOPE'


@pytest.mark.parametrize('headers', [{'x-delivery-count': True}, {'x-delivery-count': -1}, {'x-delivery-count': 'private'}])
def test_invalid_retry_counter_is_terminal(worker, catalog, headers):
    deliver(worker, catalog, headers=headers)
    worker.consume('commands')
    worker.channels['commands'].basic_reject.assert_called_once_with(5, requeue=False)


def test_database_identity_rejection_is_terminal(worker, catalog):
    deliver(worker, catalog)
    worker.service.process.side_effect = PermanentError('IDENTITY_MISMATCH')
    worker.consume('commands')
    worker.channels['commands'].basic_reject.assert_called_once_with(5, requeue=False)
    worker.channels['commands'].basic_ack.assert_not_called()


def test_unconfirmed_error_keeps_original_message_unacknowledged(worker, catalog):
    deliver(worker, catalog)
    worker.service.process.side_effect = psycopg.OperationalError('private')
    channel = worker.channels['commands']
    channel.basic_publish.side_effect = pika.exceptions.NackError([])
    with pytest.raises(pika.exceptions.NackError):
        worker.consume('commands')
    channel.basic_reject.assert_not_called()
    channel.basic_ack.assert_not_called()


@pytest.mark.parametrize('mutation,code', [
    (lambda e: e.update(received_at=None), 'INVALID_BINDING'),
    (lambda e: e.update(environment_id='00000000-0000-4000-8000-000000000099'), 'UNAUTHORIZED_SCOPE'),
    (lambda e: e['data']['equipment'].update(equipment_id='00000000-0000-4000-8000-000000000099'), 'IDENTITY_MISMATCH'),
    (lambda e: e['data']['measurements']['light'].update(unit='degC'), 'INVALID_SCHEMA'),
])
def test_invalid_message_is_rejected_with_sanitized_error(worker, catalog, mutation, code):
    event, method, props = deliver(worker, catalog)
    mutation(event)
    worker.channels['commands'].basic_get.return_value = method, props, encode(event)
    worker.consume('commands')
    worker.service.process.assert_not_called()
    worker.channels['commands'].basic_reject.assert_called_once_with(5, requeue=False)
    error = json.loads(worker.channels['commands'].basic_publish.call_args.args[2])
    assert error['data']['code'] == code
    assert error['data']['source_event_id'] is None


@pytest.mark.parametrize('raw', [b'[]', b'{"type":1,"type":2}', b'{"x":NaN}', b'private' * 1400])
def test_strict_json_and_size_limit(worker, catalog, raw):
    _, method, props = deliver(worker, catalog)
    worker.channels['commands'].basic_get.return_value = method, props, raw
    worker.consume('commands')
    worker.service.process.assert_not_called()
    worker.channels['commands'].basic_reject.assert_called_once_with(5, requeue=False)


@pytest.mark.parametrize('count', [0, 1, 2])
def test_database_outage_retries_three_times_then_dlq(worker, catalog, count):
    deliver(worker, catalog, headers={'x-delivery-count': count})
    worker.service.process.side_effect = psycopg.OperationalError('private password')
    worker.consume('commands')
    worker.channels['commands'].basic_ack.assert_not_called()
    worker.channels['commands'].basic_reject.assert_called_once_with(5, requeue=count < 2)
    error = json.loads(worker.channels['commands'].basic_publish.call_args.args[2])
    assert error['data']['attempt'] == count + 1
    assert 'private' not in json.dumps(error)


def test_confirm_and_mandatory_precede_outbox_mark(worker, catalog):
    event, _, _ = deliver(worker, catalog)
    worker.service.pending_outputs.return_value = [event]
    channel = worker.channels['commands']
    channel.basic_publish.side_effect = lambda *a, **kw: worker.service.mark_published.assert_not_called()
    worker.flush_outputs(channel)
    assert channel.basic_publish.call_args.kwargs['mandatory'] is True
    worker.service.mark_published.assert_called_once_with(event['event_id'])


def test_unconfirmed_outbox_stays_pending(worker, catalog):
    event, _, _ = deliver(worker, catalog)
    worker.service.pending_outputs.return_value = [event]
    worker.channels['commands'].basic_publish.side_effect = pika.exceptions.NackError([])
    with pytest.raises(pika.exceptions.NackError):
        worker.flush_outputs(worker.channels['commands'])
    worker.service.mark_published.assert_not_called()


def test_roles_have_distinct_credentials_and_only_their_own_queues(worker):
    assert worker.parameters['commands'].credentials.username == 'coldsafe-commands'
    assert worker.parameters['delivery'].credentials.username == 'coldsafe-delivery'
    assert worker.parameters['commands'].credentials.password != worker.parameters['delivery'].credentials.password
    worker.channels['delivery'].basic_get.return_value = None, None, None
    worker.consume('delivery')
    worker.channels['delivery'].basic_get.assert_called_once_with('coldsafe.delivery', auto_ack=False)


def test_reconnect_recovers_each_private_connection(worker, monkeypatch):
    worker.connections['commands'] = None
    worker.channels['commands'] = None
    channel, connection = MagicMock(), MagicMock()
    connection.channel.return_value = channel
    channel.basic_get.return_value = None, None, None
    shutdown = Event()
    connection.process_data_events.side_effect = lambda **_: shutdown.set()
    connect = Mock(side_effect=[pika.exceptions.AMQPConnectionError('private'), connection])
    monkeypatch.setattr('backend.app.amqp.consumer.pika.BlockingConnection', connect)
    monkeypatch.setattr(shutdown, 'wait', lambda *_: None)
    worker.run_role('commands', shutdown)
    assert connect.call_count == 2
    channel.confirm_delivery.assert_called_once()
    channel.basic_qos.assert_called_once_with(prefetch_count=1)
    connection.close.assert_called_once()


def test_connection_health_and_lost_connection_shutdown(worker):
    assert not worker.is_connected
    worker.connections = {role: MagicMock(is_open=True) for role in worker.parameters}
    assert worker.is_connected
    worker.connections['commands'].close.side_effect = pika.exceptions.AMQPConnectionError('private')
    worker.close_role('commands')
    assert not worker.is_connected
    assert worker.channels['commands'] is None
    worker.close()
    assert worker.stopping.is_set()


@pytest.mark.parametrize('arguments', [
    {'amqp_host': ''}, {'amqp_port': 0}, {'password_commands': ''},
    {'password_delivery': 'private-c'}])
def test_invalid_connection_settings_fail_fast(catalog, arguments):
    settings = dict(amqp_host='rabbitmq', amqp_port=5672,
                    password_commands='private-c', password_delivery='private-d')
    with pytest.raises(ValueError):
        ApiAmqpConsumer(Mock(), catalog, Mock(), Mock(), **{**settings, **arguments})
