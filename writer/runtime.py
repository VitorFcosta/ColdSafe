"""Consume validated v3 telemetry; acknowledge only synchronous InfluxDB writes."""
import argparse
from collections.abc import Callable
from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import signal
from threading import Event
from uuid import uuid4

from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from influxdb_client.client.exceptions import InfluxDBError
import pika
import psycopg
from urllib3.exceptions import HTTPError

from backend.app.errors import DependencyUnavailableError
from backend.app.repositories.influxdb import InfluxReadingRepository
from backend.app.repositories.influxdb_client import InfluxSettings, create_influx_repository
from gateway.bridge import PermanentError, PostgresScope, VALIDATORS as GATEWAY_VALIDATORS, encode
from simulator.model import SCHEMA, strict_json, utc, validate_catalog
from simulator.health import mark_healthy

LOGGER = logging.getLogger(__name__)
VALIDATORS = {**GATEWAY_VALIDATORS, 'telemetry_persisted': Draft202012Validator(
    {**SCHEMA, '$ref': '#/$defs/telemetry_persisted_event'}, format_checker=FormatChecker())}


class Writer:
    def __init__(self, catalog: dict, repository: InfluxReadingRepository,
                 check_scope: Callable[[dict], bool], *, amqp_host: str,
                 amqp_port: int, amqp_password: str):
        validate_catalog(catalog)
        if not amqp_host or not amqp_password or not 1 <= amqp_port <= 65535:
            raise ValueError('AMQP host, port and private writer password required')
        self.catalog, self.repository, self.check_scope = catalog, repository, check_scope
        self.amqp_parameters = pika.ConnectionParameters(
            amqp_host, amqp_port, virtual_host='coldsafe',
            credentials=pika.PlainCredentials('coldsafe-writer', amqp_password),
            heartbeat=30, blocked_connection_timeout=3, socket_timeout=3, stack_timeout=5)
        self.connection = self.channel = None

    def validate(self, route: str, properties: pika.BasicProperties, raw: bytes) -> dict:
        if len(raw) > 8192:
            raise PermanentError('PAYLOAD_TOO_LARGE')
        try:
            event = strict_json(raw)
            VALIDATORS['telemetry'].validate(event)
        except (ValueError, TypeError, UnicodeError, RecursionError, ValidationError):
            raise PermanentError('INVALID_SCHEMA') from None
        if (route != f"v3.telemetry.{event['device_record_id']}" or event['received_at'] is None or
                properties.content_type != 'application/json' or properties.delivery_mode != 2 or
                properties.message_id != event['event_id'] or
                properties.correlation_id != event['correlation_id']):
            raise PermanentError('INVALID_BINDING')
        if any(event[key] != self.catalog[key] for key in ('device_id', 'device_record_id', 'environment_id')):
            raise PermanentError('UNAUTHORIZED_SCOPE')
        data = event['data']
        if (event['correlation_id'] != event['event_id'] or
                data['equipment']['equipment_id'] != self.catalog['equipment_id'] or
                any(value['sensor_id'] != self.catalog['sensors'][key]
                    for key, value in data['measurements'].items()) or
                any(value['actuator_id'] != self.catalog['actuators'][key]
                    for key, value in data['actuators'].items())):
            raise PermanentError('IDENTITY_MISMATCH')
        if not self.check_scope(self.catalog):
            raise PermanentError('UNAUTHORIZED_SCOPE')
        return event

    def publish_error(self, code: str, attempt: int) -> None:
        now, identifier = utc(datetime.now(timezone.utc)), str(uuid4())
        event = {'schema_version': 3, 'event_id': identifier, 'type': 'processing_error',
                 'occurred_at': now, 'received_at': now, 'device_id': None,
                 'device_record_id': None, 'environment_id': None, 'correlation_id': identifier,
                 'data': {'source_event_id': None, 'code': code,
                          'retryable': code == 'PROCESSING_FAILED' and attempt < 3, 'attempt': attempt}}
        VALIDATORS['processing_error'].validate(event)
        self.channel.basic_publish(
            'coldsafe.events', f'v3.processing_error.{identifier}', encode(event),
            pika.BasicProperties(content_type='application/json', delivery_mode=2,
                                 message_id=identifier, correlation_id=identifier), mandatory=True)

    def publish_persisted(self, source: dict) -> None:
        now = utc(datetime.now(timezone.utc))
        identifier = str(uuid4())
        event = {**source, 'event_id': identifier, 'type': 'telemetry_persisted',
                 'occurred_at': now, 'received_at': now,
                 'correlation_id': source['event_id'],
                 'data': {'source_event_id': source['event_id'],
                          'equipment_id': source['data']['equipment']['equipment_id'],
                          'input_received_at': source['received_at']}}
        VALIDATORS['telemetry_persisted'].validate(event)
        self.channel.basic_publish(
            'coldsafe.events', f"v3.telemetry_persisted.{event['device_record_id']}", encode(event),
            pika.BasicProperties(content_type='application/json', delivery_mode=2,
                                 message_id=identifier, correlation_id=source['event_id']), mandatory=True)

    def consume(self) -> bool:
        method, properties, raw = self.channel.basic_get('coldsafe.writer', auto_ack=False)
        if method is None:
            return True
        attempt = 1
        try:
            count = (properties.headers or {}).get('x-delivery-count', 0)
            if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                raise PermanentError('INVALID_BINDING')
            attempt = min(3, count + 1)
            event = self.validate(method.routing_key, properties, raw)
            self.repository.save_event(event=event)
            self.publish_persisted(event)
        except PermanentError as error:
            self.publish_error(str(error), attempt)
            self.channel.basic_reject(method.delivery_tag, requeue=False)
        except (DependencyUnavailableError, psycopg.Error):
            self.publish_error('RETRY_EXHAUSTED' if attempt == 3 else 'PROCESSING_FAILED', attempt)
            self.channel.basic_reject(method.delivery_tag, requeue=attempt < 3)
            return False
        else:
            self.channel.basic_ack(method.delivery_tag)
        return True

    def run(self, shutdown: Event) -> None:
        delay = 1
        try:
            while not shutdown.is_set():
                try:
                    if self.connection is None:
                        self.connection = pika.BlockingConnection(self.amqp_parameters)
                        self.channel = self.connection.channel()
                        self.channel.confirm_delivery()
                        self.channel.basic_qos(prefetch_count=1)
                    consumed = self.consume()
                    self.connection.process_data_events(time_limit=0)
                    if consumed:
                        mark_healthy()
                    delay = 1
                except (pika.exceptions.AMQPError, OSError):
                    LOGGER.warning('AMQP unavailable; unacknowledged telemetry remains with broker')
                    self.close_amqp()
                    shutdown.wait(delay)
                    delay = min(10, delay * 2)
                    continue
                shutdown.wait(0.05)
        finally:
            self.close_amqp()

    def close_amqp(self) -> None:
        if self.connection is not None and self.connection.is_open:
            try:
                self.connection.close()
            except (pika.exceptions.AMQPError, OSError):
                LOGGER.warning('AMQP connection lost before shutdown confirmation')
        self.connection = self.channel = None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', required=True, type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    logging.getLogger('pika').setLevel(logging.CRITICAL)
    resources = None
    try:
        scope = PostgresScope({
            'host': os.environ.get('POSTGRES_HOST', 'postgres'),
            'port': int(os.environ.get('POSTGRES_PORT', '5432')),
            'dbname': os.environ.get('POSTGRES_DB', 'coldsafe'),
            'user': os.environ.get('POSTGRES_USER', 'coldsafe'),
            'password': os.environ['POSTGRES_PASSWORD'],
        }, os.environ['WRITER_OWNER_USER_ID'])
        settings = InfluxSettings(url=os.environ.get('INFLUXDB_URL', 'http://influxdb:8086'),
                                  org=os.environ.get('INFLUXDB_ORG', 'coldsafe'),
                                  bucket=os.environ.get('INFLUXDB_LIVE_BUCKET', 'telemetry_live'),
                                  token=os.environ['INFLUXDB_WRITER_TOKEN'])
        if settings.bucket != 'telemetry_live':
            raise ValueError('Writer requires the isolated telemetry_live bucket')
        catalog = strict_json(args.catalog.read_bytes())
        validate_catalog(catalog)
        resources = create_influx_repository(settings)
        worker = Writer(catalog, resources.repository, scope,
                        amqp_host=os.environ.get('RABBITMQ_HOST', 'rabbitmq'),
                        amqp_port=int(os.environ.get('RABBITMQ_PORT', '5672')),
                        amqp_password=os.environ['RABBITMQ_WRITER_PASSWORD'])
        shutdown = Event()
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda *_: shutdown.set())
        worker.run(shutdown)
    except (KeyError, ValueError, RuntimeError, OSError, ValidationError,
            InfluxDBError, HTTPError, psycopg.Error, DependencyUnavailableError) as error:
        LOGGER.error('Writer stopped (%s); private payloads/credentials omitted', type(error).__name__)
        raise SystemExit(1) from None
    finally:
        if resources is not None:
            try:
                resources.close()
            except (InfluxDBError, HTTPError, OSError) as error:
                LOGGER.error('Writer close failed (%s); private payloads/credentials omitted', type(error).__name__)
                raise SystemExit(1) from None


if __name__ == '__main__':
    main()
