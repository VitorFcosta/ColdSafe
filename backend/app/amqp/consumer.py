"""Two private AMQP connections; PostgreSQL effects precede consumer ACKs."""
from collections.abc import Callable
from collections import deque
from datetime import datetime, timezone
import logging
from threading import Event, Thread
from uuid import uuid4

from jsonschema import Draft202012Validator, FormatChecker, ValidationError
import pika
import psycopg

from backend.app.errors import DependencyUnavailableError
from gateway.bridge import PermanentError, encode
from simulator.model import SCHEMA, strict_json, utc, validate_catalog

LOGGER = logging.getLogger(__name__)
INPUT_TYPES = frozenset(('telemetry', 'telemetry_persisted', 'ack', 'prediction', 'freshness'))
DELIVERY_TYPES = INPUT_TYPES | frozenset(('command_status', 'alert', 'processing_error',
                                        'job_progress', 'model_status'))
VALIDATORS = {kind: Draft202012Validator({**SCHEMA, '$ref': f'#/$defs/{kind}_event'},
                                       format_checker=FormatChecker())
              for kind in DELIVERY_TYPES | {'command'}}


class ApiAmqpConsumer:
    def __init__(self, service, catalog: dict, check_scope: Callable[[dict], bool],
                 emit: Callable[[dict], None], *, amqp_host: str, amqp_port: int,
                 password_commands: str, password_delivery: str):
        validate_catalog(catalog)
        if (not amqp_host or not 1 <= amqp_port <= 65535 or not password_commands
                or not password_delivery or password_commands == password_delivery):
            raise ValueError('AMQP host, port and distinct private API passwords required')
        self.service, self.catalog, self.check_scope, self.emit = service, catalog, check_scope, emit
        self.parameters = {role: pika.ConnectionParameters(
            amqp_host, amqp_port, virtual_host='coldsafe',
            credentials=pika.PlainCredentials(f'coldsafe-{role}', password),
            heartbeat=30, blocked_connection_timeout=3, socket_timeout=3, stack_timeout=5)
            for role, password in (('commands', password_commands), ('delivery', password_delivery))}
        self.connections = dict.fromkeys(self.parameters)
        self.channels = dict.fromkeys(self.parameters)
        self.stopping = Event()
        self.delivered = deque(maxlen=1024)

    def emit_once(self, event: dict) -> None:
        # shortcut: remember 1024 Web envelopes; clients recover by event_id and REST after restart.
        if event['event_id'] not in self.delivered:
            self.emit(event)
            self.delivered.append(event['event_id'])

    @property
    def is_connected(self) -> bool:
        return all(connection is not None and connection.is_open
                   for connection in self.connections.values())

    def validate(self, role: str, route: str, properties: pika.BasicProperties, raw: bytes) -> dict:
        if len(raw) > 8192:
            raise PermanentError('PAYLOAD_TOO_LARGE')
        try:
            event = strict_json(raw)
            kind = event.get('type')
            if kind not in (INPUT_TYPES if role == 'commands' else DELIVERY_TYPES):
                raise ValueError('Unsupported event')
            VALIDATORS[kind].validate(event)
        except (ValueError, TypeError, UnicodeError, RecursionError, ValidationError):
            raise PermanentError('INVALID_SCHEMA') from None
        identity = event['correlation_id'] if kind == 'processing_error' else event['device_record_id']
        if kind == 'job_progress':
            identity = event['data']['job_id']
        elif kind == 'model_status':
            identity = event['data']['model_id']
        if (route != f'v3.{kind}.{identity}' or event['received_at'] is None or
                properties.content_type != 'application/json' or properties.delivery_mode != 2 or
                properties.message_id != event['event_id'] or
                properties.correlation_id != event['correlation_id']):
            raise PermanentError('INVALID_BINDING')
        # Global diagnostics/job events carry no proven account owner, so never reach Web clients.
        if event['device_id'] is None:
            return event
        if any(event[key] != self.catalog[key] for key in ('device_id', 'device_record_id', 'environment_id')):
            raise PermanentError('UNAUTHORIZED_SCOPE')
        data = event['data']
        if kind == 'telemetry':
            if (event['correlation_id'] != event['event_id'] or
                    data['equipment']['equipment_id'] != self.catalog['equipment_id'] or
                    any(value['sensor_id'] != self.catalog['sensors'][key]
                        for key, value in data['measurements'].items()) or
                    any(value['actuator_id'] != self.catalog['actuators'][key]
                        for key, value in data['actuators'].items())):
                raise PermanentError('IDENTITY_MISMATCH')
        if ('equipment_id' in data and data['equipment_id'] != self.catalog['equipment_id'] or
                'actuator' in data and data['actuator_id'] != self.catalog['actuators'][data['actuator']] or
                kind in ('ack', 'command_status') and event['correlation_id'] != data['command_id'] or
                kind == 'telemetry_persisted' and event['correlation_id'] != data['source_event_id']):
            raise PermanentError('IDENTITY_MISMATCH')
        if not self.check_scope(self.catalog):
            raise PermanentError('UNAUTHORIZED_SCOPE')
        return event

    @staticmethod
    def publish(channel, event: dict) -> None:
        identity = event['correlation_id'] if event['type'] == 'processing_error' else event['device_record_id']
        channel.basic_publish('coldsafe.events', f"v3.{event['type']}.{identity}", encode(event),
            pika.BasicProperties(content_type='application/json', delivery_mode=2,
                                 message_id=event['event_id'], correlation_id=event['correlation_id']),
            mandatory=True)

    def publish_error(self, channel, code: str, attempt: int) -> None:
        now, identifier = utc(datetime.now(timezone.utc)), str(uuid4())
        event = {'schema_version': 3, 'event_id': identifier, 'type': 'processing_error',
                 'occurred_at': now, 'received_at': now, 'device_id': None,
                 'device_record_id': None, 'environment_id': None, 'correlation_id': identifier,
                 'data': {'source_event_id': None, 'code': code,
                          'retryable': code == 'PROCESSING_FAILED' and attempt < 3, 'attempt': attempt}}
        self.publish(channel, event)

    def consume(self, role: str) -> None:
        channel = self.channels[role]
        method, properties, raw = channel.basic_get(f'coldsafe.{role}', auto_ack=False)
        if method is None:
            return
        attempt = 1
        try:
            count = (properties.headers or {}).get('x-delivery-count', 0)
            if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                raise PermanentError('INVALID_BINDING')
            attempt = min(3, count + 1)
            event = self.validate(role, method.routing_key, properties, raw)
            if event['device_id'] is not None and event['type'] in INPUT_TYPES | {'alert', 'command_status'}:
                self.service.process(event)
                if role == 'delivery':
                    if event['type'] in ('telemetry', 'telemetry_persisted'):
                        source_id = event['event_id'] if event['type'] == 'telemetry' else event['data']['source_event_id']
                        persisted = self.service.persisted_telemetry(source_id)
                        if persisted is not None:
                            self.emit_once(persisted)
                            prediction = self.service.prediction_for_source(source_id)
                            if prediction is not None:
                                self.emit_once(prediction)
                    elif event['type'] == 'prediction':
                        prediction = self.service.linked_prediction(event['event_id'])
                        if prediction is not None:
                            self.emit_once(prediction)
                    elif event['type'] != 'ack' and self.service.trusted_output(event):
                        self.emit_once(event)
        except PermanentError as error:
            self.publish_error(channel, str(error), attempt)
            channel.basic_reject(method.delivery_tag, requeue=False)
        except (DependencyUnavailableError, psycopg.Error):
            self.publish_error(channel, 'RETRY_EXHAUSTED' if attempt == 3 else 'PROCESSING_FAILED', attempt)
            channel.basic_reject(method.delivery_tag, requeue=attempt < 3)
        else:
            channel.basic_ack(method.delivery_tag)

    def flush_outputs(self, channel) -> None:
        for event in self.service.pending_outputs():
            self.publish(channel, event)
            self.service.mark_published(event['event_id'])

    def run_role(self, role: str, shutdown: Event) -> None:
        delay = 1
        try:
            while not shutdown.is_set() and not self.stopping.is_set():
                try:
                    if self.connections[role] is None:
                        connection = pika.BlockingConnection(self.parameters[role])
                        self.connections[role] = connection
                        self.channels[role] = connection.channel()
                        self.channels[role].confirm_delivery()
                        self.channels[role].basic_qos(prefetch_count=1)
                    if role == 'commands':
                        self.service.expire_pending()
                        self.flush_outputs(self.channels[role])
                    self.consume(role)
                    self.connections[role].process_data_events(time_limit=0)
                    delay = 1
                except (pika.exceptions.AMQPError, OSError, psycopg.Error, DependencyUnavailableError):
                    LOGGER.warning('API AMQP dependency unavailable; durable messages remain pending')
                    self.close_role(role)
                    shutdown.wait(delay)
                    delay = min(10, delay * 2)
                    continue
                shutdown.wait(0.05)
        finally:
            self.close_role(role)

    def close_role(self, role: str) -> None:
        connection = self.connections[role]
        if connection is not None and connection.is_open:
            try:
                connection.close()
            except (pika.exceptions.AMQPError, OSError):
                LOGGER.warning('API AMQP disconnected before shutdown confirmation')
        self.connections[role] = self.channels[role] = None

    def run(self, shutdown: Event) -> None:
        workers = [Thread(target=self.run_role, args=(role, shutdown), daemon=True)
                   for role in self.parameters]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()

    def close(self) -> None:
        self.stopping.set()
