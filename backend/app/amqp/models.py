"""Durable model activation outbox and its private inference consumer."""
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import logging
from uuid import UUID

from jsonschema import Draft202012Validator, FormatChecker, ValidationError
import pika
import psycopg

from backend.app.amqp.jobs import JobPublisher
from gateway.bridge import PermanentError, encode
from simulator.model import SCHEMA, strict_json

LOGGER = logging.getLogger(__name__)
REQUESTED = Draft202012Validator({**SCHEMA, '$ref': '#/$defs/model_activation_event'},
                                 format_checker=FormatChecker())


class ModelPublisher(JobPublisher):
    def __init__(self, service, *, host: str, port: int, password: str, role: str = 'api'):
        if role not in ('api', 'inference'):
            raise ValueError('Model publisher must be api or inference')
        self._initialize(service, role, host, port, password)

    def flush_outputs(self, channel) -> None:
        for event in self.service.pending_outputs(self.role):
            channel.basic_publish('coldsafe.events',
                f"v3.{event['type']}.{event['data']['model_id']}", encode(event),
                pika.BasicProperties(content_type='application/json', delivery_mode=2,
                    message_id=event['event_id'], correlation_id=event['correlation_id']),
                mandatory=True)
            self.service.mark_published(event['event_id'])


class ModelWorker(ModelPublisher):
    def __init__(self, service, *, host: str, port: int, password: str):
        super().__init__(service, host=host, port=port, password=password, role='inference')
        self.pending = None
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='model-inference')

    def validate(self, route: str, properties: pika.BasicProperties, raw: bytes) -> dict:
        try:
            event = strict_json(raw)
            REQUESTED.validate(event)
        except (ValueError, TypeError, UnicodeError, RecursionError, ValidationError):
            raise PermanentError('INVALID_SCHEMA') from None
        activation_id, model_id = event['data']['activation_id'], event['data']['model_id']
        count = (properties.headers or {}).get('x-delivery-count', 0)
        if (route != f'v3.model_activation.{model_id}' or event['correlation_id'] != activation_id or
                properties.content_type != 'application/json' or properties.delivery_mode != 2 or
                properties.message_id != event['event_id'] or
                properties.correlation_id != activation_id or not isinstance(count, int) or
                isinstance(count, bool) or count < 0):
            raise PermanentError('INVALID_BINDING')
        if event != self.service.get_requested(UUID(activation_id)):
            raise PermanentError('UNAUTHORIZED_SCOPE')
        return event

    def execute(self, event: dict, channel) -> bool:
        future = self.executor.submit(self.service.execute, UUID(event['data']['activation_id']))
        return self._wait(future, channel)

    def _wait(self, future, channel):
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
        finally:
            # Reconnect must not start another loader while the previous one is still running.
            if not future.done():
                try:
                    future.result()
                except Exception:
                    LOGGER.warning('Model loading stopped after connection loss')

    def step(self, channel) -> None:
        self.flush_outputs(channel)
        if self.pending is None:
            self.pending = channel.basic_get('coldsafe.model-activation', auto_ack=False)
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
            # A storage outage keeps the same delivery available for recovery.
            raise psycopg.OperationalError('Model storage temporarily unavailable') from None
        else:
            if handled:
                self.flush_outputs(channel)
                channel.basic_ack(method.delivery_tag)
                self.pending = None

    def disconnect(self) -> None:
        super().disconnect()
        self.pending = None

    def close(self) -> None:
        super().close()
        self.executor.shutdown(wait=True)
