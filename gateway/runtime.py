"""MQTT/AMQP bridge. The legacy API never participates in this v3 transport."""
import argparse
from datetime import datetime, timezone
import logging
import math
import os
from pathlib import Path
from queue import Empty, Full, Queue
import signal
import sqlite3
from threading import Event
import time

import paho.mqtt.client as mqtt
import pika
import psycopg
from jsonschema import ValidationError

from gateway.bridge import Bridge, PermanentError, PostgresScope
from simulator.model import strict_json
from simulator.health import mark_healthy

LOGGER = logging.getLogger(__name__)


class Gateway:
    def __init__(self, bridge: Bridge, *, mqtt_host: str, mqtt_port: int, mqtt_password: str,
                 amqp_host: str, amqp_port: int, amqp_password: str):
        if not all((mqtt_host, mqtt_password, amqp_host, amqp_password)):
            raise ValueError('Both broker hosts and private passwords required')
        if not all(1 <= port <= 65535 for port in (mqtt_port, amqp_port)):
            raise ValueError('Invalid broker port')
        self.bridge = bridge
        self.mqtt_host, self.mqtt_port = mqtt_host, mqtt_port
        self.amqp_parameters = pika.ConnectionParameters(
            amqp_host, amqp_port, virtual_host='coldsafe',
            credentials=pika.PlainCredentials('coldsafe-gateway', amqp_password),
            heartbeat=30, blocked_connection_timeout=3, socket_timeout=3, stack_timeout=5)
        self.connection = self.channel = None
        self.incoming = Queue(maxsize=32)
        self.ready, self.overflow = Event(), Event()
        self.generation = 0
        self.failed_publications = set()
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='coldsafe-gateway-v3',
                                  protocol=mqtt.MQTTv5, manual_ack=True)
        self.client.username_pw_set('coldsafe-gateway', mqtt_password)
        self.client.reconnect_delay_set(min_delay=1, max_delay=10)
        self.client.max_inflight_messages_set(1)
        self.client.max_queued_messages_set(1)
        self.client.on_connect = self.on_connect
        self.client.on_subscribe = self.on_subscribe
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message
        self.client.on_publish = self.on_publish

    def on_connect(self, client, userdata, flags, reason_code, properties):
        self.ready.clear()
        self.generation += 1
        if reason_code.is_failure:
            LOGGER.warning('MQTT connection rejected')
            return
        prefix = f"coldsafe/v3/devices/{self.bridge.catalog['device_id']}"
        options = mqtt.SubscribeOptions(qos=1, noLocal=True, retainAsPublished=True, retainHandling=2)
        client.subscribe([(prefix + '/telemetry', options), (prefix + '/acks', options)])

    def on_subscribe(self, client, userdata, mid, reason_codes, properties):
        if len(reason_codes) == 2 and all(not code.is_failure for code in reason_codes):
            self.ready.set()
        else:
            LOGGER.warning('MQTT subscriptions rejected')

    def on_disconnect(self, client, userdata, flags, reason_code, properties):
        self.ready.clear()

    def on_message(self, client, userdata, message):
        try:
            self.incoming.put_nowait((self.generation, message))
        except Full:
            # No MQTT ACK: exit and let the persistent session redeliver after restart.
            self.overflow.set()

    def on_publish(self, client, userdata, mid, reason_code, properties):
        if reason_code.is_failure:
            self.failed_publications.add(mid)

    def publish_bus(self, route: str, body: bytes, event: dict) -> None:
        self.channel.basic_publish('coldsafe.events', route, body,
                                   pika.BasicProperties(content_type='application/json', delivery_mode=2,
                                                        message_id=event['event_id'],
                                                        correlation_id=event['correlation_id']), mandatory=True)

    def deliver_command(self, event: dict, raw: bytes) -> None:
        identifier = event['data']['command_id']
        sent = self.bridge.db.execute('SELECT sent FROM commands WHERE command_id=?', (identifier,)).fetchone()[0]
        if sent:
            return
        if not self.ready.is_set():
            raise ConnectionError('MQTT unavailable')
        deadline = datetime.fromisoformat(event['data']['deadline_at'].replace('Z', '+00:00'))
        remaining = math.floor((deadline - datetime.now(timezone.utc)).total_seconds())
        if remaining < 1:
            raise PermanentError('INVALID_BINDING')
        properties = mqtt.Properties(mqtt.PacketTypes.PUBLISH)
        properties.MessageExpiryInterval = remaining
        info = self.client.publish(f"coldsafe/v3/devices/{event['device_id']}/commands", raw,
                                   qos=1, retain=False, properties=properties)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise ConnectionError('MQTT publish not queued')
        info.wait_for_publish(timeout=3)
        failed = info.mid in self.failed_publications
        self.failed_publications.discard(info.mid)
        if not info.is_published() or failed:
            raise ConnectionError('MQTT publish not confirmed')
        with self.bridge.db:
            self.bridge.db.execute('UPDATE commands SET sent=1 WHERE command_id=?', (identifier,))

    def consume_command(self) -> bool:
        method, properties, raw = self.channel.basic_get('coldsafe.gateway', auto_ack=False)
        if method is None:
            return True
        count = (properties.headers or {}).get('x-delivery-count', 0)
        attempt = min(3, 1 + count) if isinstance(count, int) and count >= 0 else 1
        try:
            event = self.bridge.parse(raw)
            if (properties.content_type != 'application/json' or properties.delivery_mode != 2 or
                    properties.message_id != event['event_id'] or
                    properties.correlation_id != event['correlation_id']):
                raise PermanentError('INVALID_BINDING')
            event = self.bridge.accept_command(method.routing_key, raw)
            self.deliver_command(event, raw)
        except PermanentError as error:
            self.bridge.record_error('amqp', method.routing_key, raw, str(error), attempt=attempt)
            self.channel.basic_reject(method.delivery_tag, requeue=False)
        except (ConnectionError, RuntimeError, psycopg.Error):
            self.bridge.record_error('amqp', method.routing_key, raw,
                                     'RETRY_EXHAUSTED' if attempt == 3 else 'PROCESSING_FAILED', attempt=attempt)
            self.channel.basic_reject(method.delivery_tag, requeue=attempt < 3)
            return False
        else:
            self.channel.basic_ack(method.delivery_tag)
        return True

    def run(self, shutdown: Event) -> None:
        properties = mqtt.Properties(mqtt.PacketTypes.CONNECT)
        properties.SessionExpiryInterval = 86400
        properties.ReceiveMaximum = 16
        properties.MaximumPacketSize = 262144
        self.client.connect_async(self.mqtt_host, self.mqtt_port, keepalive=30,
                                  clean_start=False, properties=properties)
        self.client.loop_start()
        pending = None
        next_connect = 0
        try:
            while not shutdown.is_set():
                if self.overflow.is_set():
                    raise RuntimeError('MQTT receive capacity exceeded; unacknowledged data preserved by broker')
                if pending is None:
                    try:
                        pending = self.incoming.get_nowait()
                    except Empty:
                        pass
                if pending is not None:
                    generation, message = pending
                    try:
                        self.bridge.accept_mqtt(message.topic, message.payload,
                                                retained=message.retain, qos=message.qos)
                    except PermanentError as error:
                        self.bridge.record_error('mqtt', message.topic, message.payload, str(error))
                    except psycopg.Error:
                        LOGGER.warning('Catalog database unavailable; MQTT delivery remains unacknowledged')
                        shutdown.wait(1)
                        continue
                    if generation == self.generation:
                        self.client.ack(message.mid, message.qos)
                    pending = None
                try:
                    if self.connection is None:
                        if time.monotonic() < next_connect:
                            shutdown.wait(0.05)
                            continue
                        self.connection = pika.BlockingConnection(self.amqp_parameters)
                        self.channel = self.connection.channel()
                        self.channel.confirm_delivery()
                        self.channel.basic_qos(prefetch_count=1)
                    self.bridge.flush(self.publish_bus)
                    consumed = self.consume_command()
                    self.connection.process_data_events(time_limit=0)
                    if consumed and self.ready.is_set():
                        mark_healthy()
                except (pika.exceptions.AMQPError, OSError):
                    LOGGER.warning('AMQP unavailable; journal and broker preserve pending messages')
                    self.close_amqp()
                    next_connect = time.monotonic() + 1
                shutdown.wait(0.05)
        finally:
            self.client.disconnect()
            self.client.loop_stop()
            self.close_amqp()
            self.bridge.db.close()

    def close_amqp(self) -> None:
        if self.connection is not None and self.connection.is_open:
            try:
                self.connection.close()
            except pika.exceptions.AMQPError:
                LOGGER.warning('AMQP connection closed before shutdown confirmation')
        self.connection = self.channel = None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', required=True, type=Path)
    parser.add_argument('--journal', required=True, type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    logging.getLogger('pika').setLevel(logging.CRITICAL)
    os.umask(0o077)
    try:
        scope = PostgresScope({
            'host': os.environ.get('POSTGRES_HOST', 'postgres'),
            'port': int(os.environ.get('POSTGRES_PORT', '5432')),
            'dbname': os.environ.get('POSTGRES_DB', 'coldsafe'),
            'user': os.environ.get('POSTGRES_USER', 'coldsafe'),
            'password': os.environ['POSTGRES_PASSWORD'],
        }, os.environ['GATEWAY_OWNER_USER_ID'])
        bridge = Bridge(strict_json(args.catalog.read_bytes()), args.journal, scope)
        runtime = Gateway(bridge, mqtt_host=os.environ.get('MQTT_HOST', 'mosquitto'),
                          mqtt_port=int(os.environ.get('MQTT_PORT', '1883')),
                          mqtt_password=os.environ['MQTT_GATEWAY_PASSWORD'],
                          amqp_host=os.environ.get('RABBITMQ_HOST', 'rabbitmq'),
                          amqp_port=int(os.environ.get('RABBITMQ_PORT', '5672')),
                          amqp_password=os.environ['RABBITMQ_GATEWAY_PASSWORD'])
        shutdown = Event()
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda *_: shutdown.set())
        runtime.run(shutdown)
    except (KeyError, ValueError, RuntimeError, OSError, sqlite3.Error, ValidationError) as error:
        LOGGER.error('Gateway stopped (%s); private payloads/credentials omitted', type(error).__name__)
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
