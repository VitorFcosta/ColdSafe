"""Writer transport boundaries, retry and ACK ordering without network services."""
from datetime import datetime, timezone
import json
import struct
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock
from uuid import uuid4

import pika
import psycopg
import pytest
from influxdb_client.client.exceptions import InfluxDBError

from backend.app.errors import DependencyUnavailableError
from backend.tests.infra.test_gateway import catalog
from gateway.bridge import VALIDATORS, encode
from simulator.model import Simulator, utc
from writer.runtime import Writer, main


@pytest.fixture
def runtime(catalog):
    worker = Writer(catalog, Mock(), Mock(return_value=True), amqp_host='rabbitmq',
                    amqp_port=5672, amqp_password='private')
    worker.channel, worker.connection = MagicMock(), MagicMock()
    return worker


def delivery(runtime, catalog, *, headers=None):
    event = Simulator(catalog).sample(1)
    event['received_at'] = utc(datetime.now(timezone.utc))
    properties = pika.BasicProperties(content_type='application/json', delivery_mode=2,
                                     message_id=event['event_id'], correlation_id=event['correlation_id'],
                                     headers=headers)
    method = SimpleNamespace(delivery_tag=123, routing_key='v3.telemetry.' + catalog['device_record_id'])
    runtime.channel.basic_get.return_value = method, properties, encode(event)
    return event, method, properties


def error_event(runtime):
    args, kwargs = runtime.channel.basic_publish.call_args
    event = json.loads(args[2])
    VALIDATORS['processing_error'].validate(event)
    assert args[0] == 'coldsafe.events'
    assert args[1] == 'v3.processing_error.' + event['correlation_id']
    assert kwargs['mandatory'] is True
    properties = args[3]
    assert properties.message_id == event['event_id']
    assert properties.correlation_id == event['correlation_id']
    assert properties.content_type == 'application/json' and properties.delivery_mode == 2
    return event


def test_ack_only_after_sync_write_and_duplicate_is_written_idempotently(runtime, catalog):
    event, _, _ = delivery(runtime, catalog)
    runtime.repository.save_event.side_effect = lambda **_: runtime.channel.basic_ack.assert_not_called()
    runtime.consume()
    runtime.repository.save_event.assert_called_once_with(event=event)
    runtime.channel.basic_ack.assert_called_once_with(123)
    runtime.channel.basic_ack.reset_mock()
    runtime.consume()
    assert runtime.repository.save_event.call_count == 2
    assert runtime.channel.basic_publish.call_count == 2
    receipts = [json.loads(call.args[2]) for call in runtime.channel.basic_publish.call_args_list]
    assert receipts[0]['event_id'] != receipts[1]['event_id']
    assert receipts[0]['data'] == receipts[1]['data']
    assert receipts[0]['type'] == 'telemetry_persisted'
    assert receipts[0]['correlation_id'] == event['event_id']
    assert receipts[0]['data'] == {
        'source_event_id': event['event_id'], 'equipment_id': catalog['equipment_id'],
        'input_received_at': event['received_at']}


def test_receipt_is_confirmed_after_write_before_ack(runtime, catalog):
    event, _, _ = delivery(runtime, catalog)
    runtime.channel.basic_publish.side_effect = lambda *_, **__: (
        runtime.repository.save_event.assert_called_once_with(event=event),
        runtime.channel.basic_ack.assert_not_called())
    runtime.consume()
    runtime.channel.basic_ack.assert_called_once_with(123)


def test_unconfirmed_receipt_leaves_saved_reading_unacknowledged(runtime, catalog):
    delivery(runtime, catalog)
    runtime.channel.basic_publish.side_effect = pika.exceptions.NackError([])
    with pytest.raises(pika.exceptions.NackError):
        runtime.consume()
    runtime.repository.save_event.assert_called_once()
    runtime.channel.basic_ack.assert_not_called()
    runtime.channel.basic_reject.assert_not_called()


@pytest.mark.parametrize('failure', [DependencyUnavailableError('private token'), psycopg.OperationalError('private password')])
@pytest.mark.parametrize('count', [0, 1, 2, 10])
def test_dependency_retry_then_dlq_with_confirmed_sanitized_error(runtime, catalog, failure, count, caplog):
    delivery(runtime, catalog, headers={'x-delivery-count': count})
    runtime.repository.save_event.side_effect = failure
    runtime.channel.basic_reject.side_effect = lambda *_, **__: runtime.channel.basic_publish.assert_called_once()
    runtime.consume()
    runtime.channel.basic_ack.assert_not_called()
    runtime.channel.basic_reject.assert_called_once_with(123, requeue=count < 2)
    event = error_event(runtime)
    assert event['data'] == {'source_event_id': None,
                             'code': 'PROCESSING_FAILED' if count < 2 else 'RETRY_EXHAUSTED',
                             'attempt': min(3, count + 1), 'retryable': count < 2}
    assert 'private' not in json.dumps(event) + caplog.text


@pytest.mark.parametrize('count', [1, 2])
def test_broker_amqp_long_retry_counter_is_an_integer(runtime, catalog, count):
    decoded, _ = pika.data.decode_value(b'l' + struct.pack('>q', count), 0)
    assert isinstance(decoded, int) and type(decoded) is not int
    delivery(runtime, catalog, headers={'x-delivery-count': decoded})
    runtime.repository.save_event.side_effect = DependencyUnavailableError()
    runtime.consume()
    assert error_event(runtime)['data']['attempt'] == count + 1
    assert error_event(runtime)['data']['code'] == ('PROCESSING_FAILED' if count == 1 else 'RETRY_EXHAUSTED')
    runtime.channel.basic_reject.assert_called_once_with(123, requeue=count == 1)


@pytest.mark.parametrize('mutation,code', [
    (lambda e: e.update(received_at=None), 'INVALID_BINDING'),
    (lambda e: e.update(received_at='bad-time'), 'INVALID_SCHEMA'),
    (lambda e: e.update(correlation_id=str(uuid4())), 'IDENTITY_MISMATCH'),
    (lambda e: e.update(environment_id=str(uuid4())), 'UNAUTHORIZED_SCOPE'),
    (lambda e: e.update(device_record_id=str(uuid4())), 'INVALID_BINDING'),
    (lambda e: e.update(device_id='different'), 'UNAUTHORIZED_SCOPE'),
    (lambda e: e['data']['equipment'].update(equipment_id=str(uuid4())), 'IDENTITY_MISMATCH'),
    (lambda e: e['data']['measurements']['light'].update(sensor_id=str(uuid4())), 'IDENTITY_MISMATCH'),
    (lambda e: e['data']['actuators']['led'].update(actuator_id=str(uuid4())), 'IDENTITY_MISMATCH'),
    (lambda e: e['data']['measurements']['light'].update(value=101), 'INVALID_SCHEMA'),
    (lambda e: e['data'].update(wear=0.5), 'INVALID_SCHEMA'),
])
def test_invalid_event_never_writes(runtime, catalog, mutation, code):
    event, method, properties = delivery(runtime, catalog)
    mutation(event)
    properties.message_id, properties.correlation_id = event['event_id'], event['correlation_id']
    runtime.channel.basic_get.return_value = method, properties, encode(event)
    runtime.consume()
    runtime.repository.save_event.assert_not_called()
    runtime.channel.basic_reject.assert_called_once_with(123, requeue=False)
    assert error_event(runtime)['data']['code'] == code


@pytest.mark.parametrize('raw,code', [(b'not-json', 'INVALID_SCHEMA'), (b'[]', 'INVALID_SCHEMA'),
    (b'{"type":1,"type":2}', 'INVALID_SCHEMA'), (b'\xff', 'INVALID_SCHEMA'),
    (b'{"v":NaN}', 'INVALID_SCHEMA'), (b'\xff' * 8193, 'PAYLOAD_TOO_LARGE')])
def test_strict_json_size_and_no_payload_leak(runtime, catalog, raw, code):
    _, method, properties = delivery(runtime, catalog)
    runtime.channel.basic_get.return_value = method, properties, raw
    runtime.consume()
    runtime.repository.save_event.assert_not_called()
    assert error_event(runtime)['data']['code'] == code


@pytest.mark.parametrize('key,value', [('content_type', None), ('delivery_mode', 1),
    ('message_id', 'private'), ('correlation_id', 'private')])
def test_invalid_amqp_metadata(runtime, catalog, key, value):
    _, _, properties = delivery(runtime, catalog)
    setattr(properties, key, value)
    runtime.consume()
    runtime.repository.save_event.assert_not_called()
    assert error_event(runtime)['data']['code'] == 'INVALID_BINDING'


def test_wrong_routing_key(runtime, catalog):
    _, method, _ = delivery(runtime, catalog)
    method.routing_key = 'v3.command.private'
    runtime.consume()
    runtime.repository.save_event.assert_not_called()
    assert error_event(runtime)['data']['code'] == 'INVALID_BINDING'


def test_scope_revocation_and_database_outage(runtime, catalog):
    delivery(runtime, catalog)
    runtime.check_scope.return_value = False
    runtime.consume()
    runtime.repository.save_event.assert_not_called()
    assert error_event(runtime)['data']['code'] == 'UNAUTHORIZED_SCOPE'
    runtime.check_scope.side_effect = psycopg.OperationalError('password')
    runtime.consume()
    runtime.channel.basic_reject.assert_called_with(123, requeue=True)


def test_unconfirmed_error_keeps_original_unacknowledged(runtime, catalog):
    delivery(runtime, catalog)
    runtime.repository.save_event.side_effect = DependencyUnavailableError()
    runtime.channel.basic_publish.side_effect = pika.exceptions.NackError([])
    with pytest.raises(pika.exceptions.NackError):
        runtime.consume()
    runtime.channel.basic_reject.assert_not_called()
    runtime.channel.basic_ack.assert_not_called()


@pytest.mark.parametrize('header', [-1, 'private', True, None])
def test_invalid_retry_count_is_terminal(runtime, catalog, header):
    delivery(runtime, catalog, headers={'x-delivery-count': header})
    runtime.consume()
    runtime.repository.save_event.assert_not_called()
    runtime.channel.basic_reject.assert_called_once_with(123, requeue=False)
    assert error_event(runtime)['data']['code'] == 'INVALID_BINDING'


def test_empty_queue(runtime):
    runtime.channel.basic_get.return_value = None, None, None
    runtime.consume()
    runtime.channel.basic_ack.assert_not_called()


def test_reconnect_confirms_prefetch_and_close(runtime, monkeypatch):
    runtime.connection = runtime.channel = None
    shutdown = Event()
    connection, channel = MagicMock(), MagicMock()
    connection.channel.return_value = channel
    channel.basic_get.return_value = None, None, None
    connect = Mock(side_effect=[pika.exceptions.AMQPConnectionError('private'), connection])
    monkeypatch.setattr('writer.runtime.pika.BlockingConnection', connect)
    waits = []
    monkeypatch.setattr(shutdown, 'wait', lambda delay: waits.append(delay))
    connection.process_data_events.side_effect = lambda **_: shutdown.set()
    runtime.run(shutdown)
    assert connect.call_count == 2
    assert 1 in waits
    channel.confirm_delivery.assert_called_once()
    channel.basic_qos.assert_called_once_with(prefetch_count=1)
    connection.close.assert_called_once()
    assert runtime.connection is None and runtime.channel is None


def test_close_handles_lost_connection(runtime):
    runtime.connection.close.side_effect = pika.exceptions.AMQPConnectionError()
    runtime.close_amqp()
    assert runtime.connection is None and runtime.channel is None


@pytest.mark.parametrize('key,value', [('amqp_host', ''), ('amqp_password', ''),
                                     ('amqp_port', 0), ('amqp_port', 65536)])
def test_invalid_config_before_network(catalog, key, value):
    options = dict(amqp_host='rabbitmq', amqp_port=5672, amqp_password='private')
    options[key] = value
    with pytest.raises(ValueError):
        Writer(catalog, Mock(), Mock(), **options)


def test_missing_config_has_sanitized_failure(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr('sys.argv', ['writer', '--catalog', str(tmp_path / 'missing')])
    monkeypatch.delenv('POSTGRES_PASSWORD', raising=False)
    with pytest.raises(SystemExit, match='1'):
        main()
    assert 'private payloads/credentials omitted' in caplog.text


@pytest.fixture
def configured_main(monkeypatch, tmp_path, catalog):
    path = tmp_path / 'catalog.json'
    path.write_bytes(encode(catalog))
    monkeypatch.setattr('sys.argv', ['writer', '--catalog', str(path)])
    for key, value in {'POSTGRES_PASSWORD': 'private-pg', 'WRITER_OWNER_USER_ID': str(uuid4()),
                       'RABBITMQ_WRITER_PASSWORD': 'private-amqp',
                       'INFLUXDB_WRITER_TOKEN': 'private-influx',
                       'INFLUXDB_LIVE_BUCKET': 'telemetry_live'}.items():
        monkeypatch.setenv(key, value)
    resources = MagicMock()
    create = Mock(return_value=resources)
    monkeypatch.setattr('writer.runtime.create_influx_repository', create)
    monkeypatch.setattr('writer.runtime.signal.signal', Mock())
    return resources, create


def test_main_closes_resources_and_registers_signals(configured_main, monkeypatch):
    resources, create = configured_main
    run = Mock()
    monkeypatch.setattr(Writer, 'run', run)
    main()
    settings = create.call_args.args[0]
    assert settings.bucket == 'telemetry_live' and settings.token == 'private-influx'
    assert 'private-influx' not in repr(settings)
    resources.close.assert_called_once()
    import writer.runtime as module
    assert module.signal.signal.call_count == 2
    module.signal.signal.call_args.args[1]()
    assert run.call_args.args[0].is_set()


@pytest.mark.parametrize('bucket', ['telemetry', 'telemetry_synthetic', 'other'])
def test_main_disallows_legacy_and_synthetic_buckets(configured_main, monkeypatch, bucket):
    resources, create = configured_main
    monkeypatch.setenv('INFLUXDB_LIVE_BUCKET', bucket)
    with pytest.raises(SystemExit, match='1'):
        main()
    create.assert_not_called()
    resources.close.assert_not_called()


@pytest.mark.parametrize('phase', ['run', 'create', 'close'])
def test_main_dependency_errors_are_sanitized(configured_main, monkeypatch, caplog, phase):
    resources, create = configured_main
    run = Mock()
    monkeypatch.setattr(Writer, 'run', run)
    {'run': run, 'create': create, 'close': resources.close}[phase].side_effect = InfluxDBError(message='private-influx')
    with pytest.raises(SystemExit, match='1'):
        main()
    assert 'private-influx' not in caplog.text
    assert 'private payloads/credentials omitted' in caplog.text
    assert resources.close.call_count == int(phase != 'create')
