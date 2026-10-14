"""Authenticated MQTT edge producer and operator-only simulation controls."""
import argparse
from datetime import datetime, timedelta, timezone
import json
import logging
import math
import os
from pathlib import Path
import signal
from threading import Event, Lock
from uuid import uuid4

from jsonschema import Draft202012Validator, FormatChecker, ValidationError
import paho.mqtt.client as mqtt

from simulator.model import SCHEMA, Simulator, strict_json, utc

LOGGER = logging.getLogger(__name__)
COMMAND = Draft202012Validator({**SCHEMA, '$ref': '#/$defs/command_event'}, format_checker=FormatChecker())
ACK = Draft202012Validator({**SCHEMA, '$ref': '#/$defs/ack_event'}, format_checker=FormatChecker())
CONTROL = Draft202012Validator({
    'type': 'object', 'additionalProperties': False,
    'required': ['command_id', 'device_id', 'action', 'fault', 'issued_at', 'expires_at'],
    'properties': {
        'command_id': SCHEMA['$defs']['uuid'], 'device_id': SCHEMA['$defs']['device_id'],
        'action': {'enum': ['start', 'stop', 'inject_fault']},
        'fault': {'enum': [None, 'bearing_wear', 'imbalance']},
        'issued_at': SCHEMA['$defs']['utc_time'], 'expires_at': SCHEMA['$defs']['utc_time'],
    },
}, format_checker=FormatChecker())


class MqttSimulator:
    def __init__(self, simulator: Simulator, *, host: str, port: int, password: str,
                 interval: float = 1, step_seconds: float = 1):
        if not host or not password or not 1 <= port <= 65535:
            raise ValueError('MQTT host, port and private password required')
        if not math.isfinite(interval) or not 0.1 <= interval <= 60:
            raise ValueError('Interval must be between 0.1 and 60 seconds')
        if not math.isfinite(step_seconds) or not 0 < step_seconds <= 3600:
            raise ValueError('Step must be between zero and one hour')
        self.simulator = simulator
        self.host, self.port = host, port
        self.interval, self.step_seconds = interval, step_seconds
        device = simulator.catalog['device_id']
        if device != 'sim-lab-01':
            raise ValueError('Current MQTT ACL supports only sim-lab-01')
        self.telemetry_topic = f'coldsafe/v3/devices/{device}/telemetry'
        self.command_topic = f'coldsafe/v3/devices/{device}/commands'
        self.ack_topic = f'coldsafe/v3/devices/{device}/acks'
        self.control_topic = f'coldsafe/simulator/devices/{device}/control'
        self.lock = Lock()
        self.seen = {}
        self.commands = {}
        self.connected = Event()
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f'simulator-{device}', protocol=mqtt.MQTTv5)
        self.client.username_pw_set(device, password)
        self.client.reconnect_delay_set(min_delay=1, max_delay=10)
        self.client.max_queued_messages_set(16)
        self.client.max_inflight_messages_set(1)
        self.client.on_connect = self.on_connect
        self.client.on_subscribe = self.on_subscribe
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message

    def on_connect(self, client, userdata, flags, reason_code, properties):
        self.connected.clear()
        if reason_code.is_failure:
            LOGGER.warning('MQTT authentication/connection rejected')
            return
        options = mqtt.SubscribeOptions(qos=1, retainAsPublished=True, retainHandling=2)
        client.subscribe([(self.control_topic, options), (self.command_topic, options)])

    def on_subscribe(self, client, userdata, mid, reason_codes, properties):
        if len(reason_codes) == 2 and all(not code.is_failure for code in reason_codes):
            self.connected.set()
        else:
            LOGGER.warning('MQTT subscriptions rejected')

    def on_disconnect(self, client, userdata, flags, reason_code, properties):
        self.connected.clear()

    def apply_control(self, topic: str, payload: bytes, *, retained: bool, qos: int,
                      now: datetime | None = None) -> bool:
        if topic != self.control_topic or retained or qos != 1:
            return False
        try:
            control = strict_json(payload)
            CONTROL.validate(control)
            issued = datetime.fromisoformat(control['issued_at'].replace('Z', '+00:00'))
            expires = datetime.fromisoformat(control['expires_at'].replace('Z', '+00:00'))
            now = now or datetime.now(timezone.utc)
            if issued > now or now > expires:
                LOGGER.warning('Simulation control is future-dated' if issued > now else 'Simulation control is expired')
                return False
            if (control['device_id'] != self.simulator.catalog['device_id'] or
                    expires - issued != timedelta(seconds=30) or
                    (control['action'] == 'inject_fault') != (control['fault'] is not None)):
                return False
        except (ValueError, ValidationError, UnicodeError, RecursionError):
            return False
        with self.lock:
            self.seen = {key: deadline for key, deadline in self.seen.items() if deadline >= now}
            if control['command_id'] in self.seen or len(self.seen) >= 256:
                return False
            if control['action'] == 'inject_fault':
                self.simulator.inject_fault(control['fault'])
            else:
                self.simulator.active = control['action'] == 'start'
            self.seen[control['command_id']] = expires
        return True

    def command_ack(self, command: dict, now: datetime, reason: str | None = None) -> dict:
        data = command['data']
        ack = {
            'schema_version': 3, 'event_id': str(uuid4()), 'type': 'ack',
            'occurred_at': utc(now), 'received_at': None,
            **{key: self.simulator.catalog[key] for key in ('device_id', 'device_record_id', 'environment_id')},
            'correlation_id': data['command_id'],
            'data': {
                **{key: data[key] for key in ('command_id', 'actuator_id', 'actuator')},
                'result': 'rejected' if reason else 'applied',
                'applied_state': None if reason else data['desired_state'], 'reason': reason,
            },
        }
        ACK.validate(ack)
        return ack

    def apply_command(self, topic: str, payload: bytes, *, retained: bool, qos: int,
                      now: datetime | None = None) -> dict | None:
        if topic != self.command_topic or retained or qos != 1:
            return None
        try:
            command = strict_json(payload)
            COMMAND.validate(command)
        except (ValueError, ValidationError, UnicodeError, RecursionError):
            return None
        catalog = self.simulator.catalog
        if any(command[key] != catalog[key] for key in ('device_id', 'device_record_id', 'environment_id')):
            return None
        now = now or datetime.now(timezone.utc)
        data = command['data']
        occurred = datetime.fromisoformat(command['occurred_at'].replace('Z', '+00:00'))
        received = datetime.fromisoformat(command['received_at'].replace('Z', '+00:00'))
        deadline = datetime.fromisoformat(data['deadline_at'].replace('Z', '+00:00'))
        if (command['correlation_id'] != data['command_id'] or
                data['actuator_id'] != catalog['actuators'][data['actuator']] or
                deadline - occurred != timedelta(seconds=30) or not occurred <= received <= now or
                received > deadline):
            return self.command_ack(command, now, 'INVALID_COMMAND')
        with self.lock:
            previous = self.commands.get(data['command_id'])
            if (previous and previous[0] != command) or any(
                    original['event_id'] == command['event_id'] and original['data']['command_id'] != data['command_id']
                    for original, _ in self.commands.values()):
                return self.command_ack(command, now, 'INVALID_COMMAND')
            if now > deadline:
                return self.command_ack(command, now, 'EXPIRED_COMMAND')
            if previous:
                return previous[1]
            # shortcut: 256 commands per process in memory; persist state/dedup before production scale.
            if len(self.commands) >= 256:
                return self.command_ack(command, now, 'ACTUATOR_FAILURE')
            setattr(self.simulator, data['actuator'], data['desired_state'])
            ack = self.command_ack(command, now)
            self.commands[data['command_id']] = (command, ack)
            return ack

    def on_message(self, client, userdata, message):
        if message.topic == self.command_topic:
            ack = self.apply_command(message.topic, message.payload, retained=message.retain, qos=message.qos)
            if ack is None:
                LOGGER.warning('Actuator command dropped; payload omitted')
                return
            info = client.publish(self.ack_topic, json.dumps(ack, separators=(',', ':'), allow_nan=False),
                                  qos=1, retain=False)
            if info.rc != mqtt.MQTT_ERR_SUCCESS:
                LOGGER.warning('ACK not queued; actuation is not delivery confirmation')
        elif not self.apply_control(message.topic, message.payload, retained=message.retain, qos=message.qos):
            LOGGER.warning('Simulation control rejected; payload omitted')

    def run(self, shutdown: Event) -> None:
        self.client.connect_async(self.host, self.port, keepalive=30)
        self.client.loop_start()
        try:
            while not shutdown.is_set():
                if self.connected.is_set():
                    with self.lock:
                        event = self.simulator.sample(self.step_seconds) if self.simulator.active else None
                    if event is not None:
                        payload = json.dumps(event, separators=(',', ':'), allow_nan=False)
                        if len(payload.encode('utf-8')) > 8192:
                            raise ValueError('Telemetry exceeds contract limit')
                        info = self.client.publish(self.telemetry_topic, payload, qos=1, retain=False)
                        if info.rc != mqtt.MQTT_ERR_SUCCESS:
                            LOGGER.warning('MQTT telemetry not queued')
                        else:
                            try:
                                info.wait_for_publish(timeout=5)
                                if not info.is_published():
                                    LOGGER.warning('MQTT telemetry awaiting broker; outgoing queue limited to 16')
                            except RuntimeError:
                                LOGGER.warning('MQTT disconnected before publish confirmation')
                shutdown.wait(self.interval)
        finally:
            self.client.disconnect()
            self.client.loop_stop()
            self.connected.clear()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    shutdown = Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: shutdown.set())
    try:
        simulator = Simulator(strict_json(args.catalog.read_bytes()), seed=args.seed)
        runtime = MqttSimulator(simulator, host=os.environ.get('MQTT_HOST', 'mosquitto'),
                                port=int(os.environ.get('MQTT_PORT', '1883')),
                                password=os.environ.get('MQTT_SIMULATOR_PASSWORD', ''),
                                interval=float(os.environ.get('SIMULATOR_INTERVAL_SECONDS', '1')),
                                step_seconds=float(os.environ.get('SIMULATOR_STEP_SECONDS', '1')))
        runtime.run(shutdown)
    except (OSError, ValueError, ValidationError):
        LOGGER.error('Simulator configuration/runtime failed; details omitted to protect secrets')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
