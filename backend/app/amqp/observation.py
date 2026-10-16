"""Consume copies from the dedicated observation queue, never business queues."""
import logging
from threading import Event

import pika

from backend.app.services.message_samples import MessageSamples

LOGGER = logging.getLogger(__name__)


class MessageObserver:
    def __init__(self, samples: MessageSamples, *, host: str, port: int, password: str):
        self.samples = samples
        self.parameters = pika.ConnectionParameters(
            host, port, virtual_host='coldsafe',
            credentials=pika.PlainCredentials('coldsafe-observability', password),
            heartbeat=30, blocked_connection_timeout=3, socket_timeout=3, stack_timeout=5,
        )
        self.stopping = Event()

    def receive(self, channel, method, properties: pika.BasicProperties, raw: bytes) -> None:
        self.samples.record(method.exchange, properties, raw)
        channel.basic_ack(method.delivery_tag)

    def run(self, shutdown: Event) -> None:
        delay = 1
        while not shutdown.is_set() and not self.stopping.is_set():
            connection = None
            try:
                connection = pika.BlockingConnection(self.parameters)
                channel = connection.channel()
                channel.basic_qos(prefetch_count=20)
                channel.basic_consume(queue='coldsafe.observability',
                                      on_message_callback=self.receive, auto_ack=False)
                self.samples.set_connected(True)
                delay = 1
                while not shutdown.is_set() and not self.stopping.is_set():
                    connection.process_data_events(time_limit=0.2)
            except (pika.exceptions.AMQPError, OSError):
                LOGGER.warning('Message observer unavailable; reconnecting')
            finally:
                self.samples.set_connected(False)
                if connection is not None and connection.is_open:
                    try:
                        connection.close()
                    except (pika.exceptions.AMQPError, OSError):
                        LOGGER.warning('Message observer disconnected before shutdown confirmation')
            if not shutdown.is_set() and not self.stopping.is_set():
                shutdown.wait(delay)
                delay = min(10, delay * 2)

    def close(self) -> None:
        self.stopping.set()
