"""Durable job outbox and private workers; only the Pika thread touches AMQP."""
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import logging
from threading import Event
from uuid import UUID

from jsonschema import Draft202012Validator, FormatChecker, ValidationError
import pika
import psycopg

from gateway.bridge import PermanentError, encode
from simulator.health import mark_healthy
from simulator.model import SCHEMA, strict_json

LOGGER = logging.getLogger(__name__)
REQUESTED = Draft202012Validator({**SCHEMA, '$ref': '#/$defs/job_requested_event'},
                                 format_checker=FormatChecker())


class JobPublisher:
    def __init__(self, service, *, host: str, port: int, password: str):
        self._initialize(service, 'api', host, port, password)

    def _initialize(self, service, role: str, host: str, port: int, password: str) -> None:
        if not host or not 1 <= port <= 65535 or not password:
            raise ValueError('AMQP host, port and private password required')
        self.service, self.role = service, role
        self.parameters = pika.ConnectionParameters(host, port, virtual_host='coldsafe',
            credentials=pika.PlainCredentials(f'coldsafe-{role}', password),
            heartbeat=30, blocked_connection_timeout=3, socket_timeout=3, stack_timeout=5)
        self.connection = self.channel = None
        self.stopping = Event()

    @property
    def is_connected(self) -> bool:
        return self.connection is not None and self.connection.is_open

    def flush_outputs(self, channel) -> None:
        for event in self.service.pending_outputs(self.role):
            channel.basic_publish('coldsafe.events',
                f"v3.{event['type']}.{event['data']['job_id']}", encode(event),
                pika.BasicProperties(content_type='application/json', delivery_mode=2,
                    message_id=event['event_id'], correlation_id=event['correlation_id'],
                    headers={'job_type': event['data']['job_type']}), mandatory=True)
            self.service.mark_published(event['event_id'])

    def step(self, channel) -> None:
        self.flush_outputs(channel)

    def disconnect(self) -> None:
        if self.is_connected:
            try:
                self.connection.close()
            except (pika.exceptions.AMQPError, OSError):
                LOGGER.warning('Job AMQP disconnected before shutdown confirmation')
        self.connection = self.channel = None

    def run(self, shutdown: Event) -> None:
        delay = 1
        try:
            while not shutdown.is_set() and not self.stopping.is_set():
                try:
                    if self.connection is None:
                        self.connection = pika.BlockingConnection(self.parameters)
                        self.channel = self.connection.channel()
                        self.channel.confirm_delivery()
                        self.channel.basic_qos(prefetch_count=1)
                    self.connection.process_data_events(time_limit=0)
                    self.step(self.channel)
                    self.connection.process_data_events(time_limit=0)
                    mark_healthy()
                    delay = 1
                except (pika.exceptions.AMQPError, OSError, psycopg.Error) as error:
                    LOGGER.warning('Job dependency unavailable; durable work remains pending')
                    if not isinstance(error, psycopg.Error):
                        self.disconnect()
                    shutdown.wait(delay)
                    delay = min(10, delay * 2)
                    continue
                shutdown.wait(0.05)
        finally:
            self.disconnect()
            self.close()

    def close(self) -> None:
        # The owner thread closes Pika in run's finally block.
        self.stopping.set()


class JobWorker(JobPublisher):
    def __init__(self, service, role: str, *, host: str, port: int, password: str, handler=None):
        if role not in ('generation', 'training'):
            raise ValueError('Job worker must be generation or training')
        self._initialize(service, role, host, port, password)
        self.handler = handler
        self.pending = None
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f'job-{role}')

    def validate(self, route: str, properties: pika.BasicProperties, raw: bytes) -> dict:
        try:
            event = strict_json(raw)
            REQUESTED.validate(event)
        except (ValueError, TypeError, UnicodeError, RecursionError, ValidationError):
            raise PermanentError('INVALID_SCHEMA') from None
        job_id, job_type = event['data']['job_id'], event['data']['job_type']
        headers = properties.headers or {}
        count = headers.get('x-delivery-count', 0)
        if (route != f'v3.job_requested.{job_id}' or event['correlation_id'] != job_id or
                job_type != self.role or headers.get('job_type') != job_type or
                properties.content_type != 'application/json' or properties.delivery_mode != 2 or
                properties.message_id != event['event_id'] or properties.correlation_id != job_id or
                not isinstance(count, int) or isinstance(count, bool) or count < 0):
            raise PermanentError('INVALID_BINDING')
        if event != self.service.get_requested(UUID(job_id)):
            raise PermanentError('UNAUTHORIZED_SCOPE')
        return event

    def execute(self, event: dict, channel) -> bool:
        future = self.executor.submit(self.service.execute, UUID(event['data']['job_id']),
                                      self.role, self.handler)
        try:
            while True:
                try:
                    return future.result(timeout=0.1)
                except TimeoutError:
                    if future.done():
                        raise
                    if self.connection is not None:
                        self.connection.process_data_events(time_limit=0)
                    self.flush_outputs(channel)
                    mark_healthy()
        finally:
            # A lost broker connection must not leave a second live handler behind on reconnect.
            if not future.done():
                try:
                    future.result()
                except Exception:
                    LOGGER.warning('Job execution stopped after connection loss')

    def step(self, channel) -> None:
        self.flush_outputs(channel)
        if self.pending is None:
            self.pending = channel.basic_get(f'coldsafe.{self.role}', auto_ack=False)
        method, properties, raw = self.pending
        if method is None:
            self.pending = None
            return
        try:
            event = self.validate(method.routing_key, properties, raw)
            handled = self.execute(event, channel)
        except PermanentError:
            channel.basic_reject(method.delivery_tag, requeue=False)
            self.pending = None
        except (psycopg.Error, OSError):
            # PostgreSQL outage is not a business failure: preserve delivery until recovery.
            raise psycopg.OperationalError('Job storage temporarily unavailable') from None
        else:
            if handled:
                self.flush_outputs(channel)
                channel.basic_ack(method.delivery_tag)
                self.pending = None
            # Busy PostgreSQL lock: retain the delivery, without increasing broker retry count.

    def disconnect(self) -> None:
        super().disconnect()
        self.pending = None

    def close(self) -> None:
        super().close()
        self.executor.shutdown(wait=True)
