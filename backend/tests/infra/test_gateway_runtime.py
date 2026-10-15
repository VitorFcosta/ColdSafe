"""Transport ACKs, bounded retries and lifecycle failure regression tests."""
from datetime import datetime, timedelta, timezone
from contextlib import closing
from queue import Full
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pika
import psycopg
import pytest

from backend.tests.infra.test_gateway import bridge, catalog, command
from gateway.bridge import PermanentError, encode
from gateway.runtime import Gateway, main
from simulator.model import Simulator


@pytest.fixture
def runtime(bridge):
    gateway = Gateway(bridge, mqtt_host='mqtt', mqtt_port=1883, mqtt_password='private',
                      amqp_host='amqp', amqp_port=5672, amqp_password='separate')
    gateway.client = MagicMock()
    gateway.channel = MagicMock()
    gateway.connection = MagicMock()
    return gateway


@pytest.mark.parametrize('key,value', [('mqtt_host', ''), ('mqtt_password', ''), ('amqp_password', ''),
                                     ('mqtt_port', 0), ('amqp_port', 65536)])
def test_invalid_config_fails_before_network(bridge, key, value):
    options = dict(mqtt_host='mqtt', mqtt_port=1883, mqtt_password='secret',
                   amqp_host='amqp', amqp_port=5672, amqp_password='other')
    options[key] = value
    with pytest.raises(ValueError):
        Gateway(bridge, **options)


def test_connect_requires_both_subacks(runtime):
    success, failure = SimpleNamespace(is_failure=False), SimpleNamespace(is_failure=True)
    runtime.ready.set()
    runtime.on_connect(runtime.client, None, None, failure, None)
    assert not runtime.ready.is_set()
    runtime.client.subscribe.assert_not_called()
    runtime.on_connect(runtime.client, None, None, success, None)
    topics = runtime.client.subscribe.call_args.args[0]
    assert [item[0].rsplit('/', 1)[1] for item in topics] == ['telemetry', 'acks']
    runtime.on_subscribe(runtime.client, None, 1, [success, failure], None)
    assert not runtime.ready.is_set()
    runtime.on_subscribe(runtime.client, None, 1, [success, success], None)
    assert runtime.ready.is_set()
    runtime.on_disconnect(runtime.client, None, None, None, None)
    assert not runtime.ready.is_set()


def test_overflow_never_acknowledges_unstored_message(runtime):
    runtime.incoming.put_nowait = Mock(side_effect=Full)
    runtime.on_message(runtime.client, None, object())
    assert runtime.overflow.is_set()
    runtime.client.ack.assert_not_called()
    with pytest.raises(RuntimeError):
        runtime.run(Event())
    runtime.client.disconnect.assert_called_once()


def setup_command(runtime, catalog, *, headers=None):
    requested = command(catalog, now=datetime.now(timezone.utc) - timedelta(seconds=1))
    raw = encode(requested)
    method = SimpleNamespace(delivery_tag=123, routing_key='v3.command.' + catalog['device_record_id'])
    properties = pika.BasicProperties(content_type='application/json', delivery_mode=2, headers=headers,
                                     message_id=requested['event_id'], correlation_id=requested['correlation_id'])
    runtime.channel.basic_get.return_value = method, properties, raw
    return requested, properties


def test_command_ack_waits_for_mqtt_puback_and_duplicates_skip_publish(runtime, catalog):
    requested, _ = setup_command(runtime, catalog)
    runtime.ready.set()
    info = runtime.client.publish.return_value
    info.rc, info.mid = 0, 17
    info.is_published.return_value = True
    runtime.consume_command()
    info.wait_for_publish.assert_called_once_with(timeout=3)
    runtime.channel.basic_ack.assert_called_once_with(123)
    assert runtime.bridge.db.execute('select sent from commands').fetchone()[0] == 1
    runtime.consume_command()
    runtime.client.publish.assert_called_once()
    assert runtime.channel.basic_ack.call_count == 2


@pytest.mark.parametrize('count', [0, 1, 2])
def test_unavailable_mqtt_has_bounded_retry_and_preserves_original(runtime, catalog, count):
    requested, _ = setup_command(runtime, catalog, headers={'x-delivery-count': count})
    runtime.consume_command()
    runtime.channel.basic_ack.assert_not_called()
    runtime.channel.basic_reject.assert_called_once_with(123, requeue=count < 2)
    row = runtime.bridge.db.execute('select body,code from errors').fetchone()
    assert row[0] == encode(requested)
    assert row[1] == ('RETRY_EXHAUSTED' if count == 2 else 'PROCESSING_FAILED')


@pytest.mark.parametrize('property_name,value', [('message_id', 'different'), ('content_type', None),
                                                ('delivery_mode', 1), ('correlation_id', 'different')])
def test_invalid_metadata_does_not_reserve_command_identity(runtime, catalog, property_name, value):
    _, properties = setup_command(runtime, catalog)
    setattr(properties, property_name, value)
    runtime.consume_command()
    runtime.channel.basic_reject.assert_called_once_with(123, requeue=False)
    runtime.client.publish.assert_not_called()
    assert runtime.bridge.db.execute('select count(*) from commands').fetchone()[0] == 0


@pytest.mark.parametrize('failure', ['not_queued', 'timeout', 'negative_puback', 'runtime'])
def test_failed_mqtt_publication_never_marks_sent(runtime, catalog, failure):
    setup_command(runtime, catalog)
    runtime.ready.set()
    info = runtime.client.publish.return_value
    info.rc, info.mid = 0, 17
    info.is_published.return_value = True
    if failure == 'not_queued':
        info.rc = 4
    elif failure == 'timeout':
        info.is_published.return_value = False
    elif failure == 'negative_puback':
        runtime.on_publish(runtime.client, None, 17, SimpleNamespace(is_failure=True), None)
    else:
        info.wait_for_publish.side_effect = RuntimeError()
    runtime.consume_command()
    runtime.channel.basic_ack.assert_not_called()
    runtime.channel.basic_reject.assert_called_once_with(123, requeue=True)
    assert runtime.bridge.db.execute('select sent from commands').fetchone()[0] == 0


def test_deadline_is_rechecked_before_mqtt_publication(runtime, catalog):
    requested = command(catalog, datetime.now(timezone.utc) - timedelta(seconds=31))
    runtime.bridge.db.execute('insert into commands(command_id,event_id,body) values(?,?,?)',
                              (requested['data']['command_id'], requested['event_id'], encode(requested)))
    runtime.ready.set()
    with pytest.raises(PermanentError):
        runtime.deliver_command(requested, encode(requested))
    runtime.client.publish.assert_not_called()


@pytest.mark.parametrize('database_down,stale_session,invalid', [(False, False, False), (True, False, False),
                                                               (False, True, False), (False, False, True)])
def test_lifecycle_stores_before_ack_and_recovers_database(runtime, catalog, monkeypatch,
                                                          database_down, stale_session, invalid):
    shutdown = Event()
    monkeypatch.setattr(shutdown, 'wait', lambda *_: None)
    channel, connection = runtime.channel, runtime.connection
    connection.process_data_events.side_effect = lambda **_: shutdown.set()
    channel.basic_get.return_value = None, None, None
    if database_down:
        runtime.bridge.check_scope.side_effect = [psycopg.OperationalError(), True]
    event = Simulator(catalog).sample(1)
    message = SimpleNamespace(topic='coldsafe/v3/devices/sim-lab-01/telemetry',
                              payload=b'bad-json' if invalid else encode(event), qos=1, retain=False, mid=51)
    runtime.incoming.put((runtime.generation - int(stale_session), message))
    def check_ack(*_):
        table = 'errors' if invalid else 'ingress'
        assert runtime.bridge.db.execute('select count(*) from ' + table).fetchone()[0] == 1
    runtime.client.ack.side_effect = check_ack
    runtime.run(shutdown)
    assert runtime.client.ack.call_count == int(not stale_session)
    runtime.client.loop_stop.assert_called_once()
    connection.close.assert_called_once()
    assert channel.basic_publish.call_count == 1


def test_amqp_outage_leaves_durable_outbox_for_reconnect(runtime, catalog, monkeypatch):
    runtime.connection = None
    runtime.channel = None
    monkeypatch.setattr('gateway.runtime.pika.BlockingConnection', Mock(side_effect=pika.exceptions.AMQPConnectionError()))
    shutdown = Event()
    monkeypatch.setattr(shutdown, 'wait', lambda *_: shutdown.set())
    runtime.incoming.put((runtime.generation, SimpleNamespace(
        topic='coldsafe/v3/devices/sim-lab-01/telemetry', payload=encode(Simulator(catalog).sample(1)),
        retain=False, qos=1, mid=12)))
    path = runtime.bridge.path
    runtime.run(shutdown)
    import sqlite3
    with closing(sqlite3.connect(path)) as db:
        assert db.execute('select sent from ingress').fetchone()[0] == 0
    runtime.client.ack.assert_called_once_with(12, 1)


def test_empty_queue_and_clean_close(runtime):
    runtime.channel.basic_get.return_value = None, None, None
    runtime.consume_command()
    runtime.channel.basic_ack.assert_not_called()
    runtime.connection.close.side_effect = pika.exceptions.AMQPConnectionError()
    runtime.close_amqp()
    assert runtime.connection is None


def test_missing_config_exits_without_leaking_secret(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr('sys.argv', ['gateway', '--catalog', str(tmp_path / 'x'), '--journal', str(tmp_path / 'j')])
    monkeypatch.delenv('POSTGRES_PASSWORD', raising=False)
    with pytest.raises(SystemExit, match='1'):
        main()
    assert 'private payloads/credentials omitted' in caplog.text
