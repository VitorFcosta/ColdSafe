from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pika

from backend.app.amqp.observation import MessageObserver


def test_observer_acks_only_its_copy_and_closes_connection():
    samples = Mock()
    observer = MessageObserver(samples, host='rabbitmq', port=5672, password='private-observer')
    shutdown = Event()
    connection = MagicMock()
    channel = connection.channel.return_value

    def deliver(time_limit):
        callback = channel.basic_consume.call_args.kwargs['on_message_callback']
        callback(channel, SimpleNamespace(exchange='coldsafe.dlx', delivery_tag=17),
                 pika.BasicProperties(), b'invalid')
        shutdown.set()

    connection.process_data_events.side_effect = deliver
    with patch('backend.app.amqp.observation.pika.BlockingConnection', return_value=connection):
        observer.run(shutdown)
    assert channel.basic_consume.call_args.kwargs['queue'] == 'coldsafe.observability'
    assert channel.basic_consume.call_args.kwargs['auto_ack'] is False
    samples.record.assert_called_once()
    channel.basic_ack.assert_called_once_with(17)
    channel.basic_get.assert_not_called()
    channel.basic_publish.assert_not_called()
    connection.close.assert_called_once()
    assert samples.set_connected.call_args.args == (False,)


def test_observer_reconnects_and_stops_even_after_connection_loss():
    samples = Mock()
    observer = MessageObserver(samples, host='rabbitmq', port=5672, password='private-observer')
    shutdown = Mock(wraps=Event())
    shutdown.wait.return_value = False
    connection = MagicMock()
    connection.close.side_effect = pika.exceptions.AMQPConnectionError()
    connection.process_data_events.side_effect = lambda **kwargs: shutdown.set()
    with patch('backend.app.amqp.observation.pika.BlockingConnection',
               side_effect=[pika.exceptions.AMQPConnectionError(), connection]) as factory:
        observer.run(shutdown)
    assert factory.call_count == 2
    shutdown.wait.assert_called_once_with(1)
    assert any(call.args == (True,) for call in samples.set_connected.call_args_list)
    assert samples.set_connected.call_args.args == (False,)
    observer.close()
    assert observer.stopping.is_set()
