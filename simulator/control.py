"""Operator CLI: control the simulation, without controlling a physical fan."""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from threading import Event
from uuid import uuid4

import paho.mqtt.client as mqtt

from simulator.model import utc


def make_control(device: str, action: str, fault: str | None = None) -> dict:
    if action not in ('start', 'stop', 'inject_fault') or (action == 'inject_fault') != (fault is not None):
        raise ValueError('Fault is required only for inject_fault')
    if fault not in (None, 'bearing_wear', 'imbalance'):
        raise ValueError('Unknown failure mode')
    # Operational controls do not need sub-second precision across host/VM clocks.
    now = datetime.now(timezone.utc).replace(microsecond=0)
    return {'command_id': str(uuid4()), 'device_id': device, 'action': action, 'fault': fault,
            'issued_at': utc(now), 'expires_at': utc(now + timedelta(seconds=30))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['start', 'stop', 'inject_fault'])
    parser.add_argument('--fault', choices=['bearing_wear', 'imbalance'])
    parser.add_argument('--device', default='sim-lab-01', choices=['sim-lab-01'])
    args = parser.parse_args()
    password = os.environ.get('MQTT_SIMULATOR_OPERATOR_PASSWORD', '')
    if not password:
        parser.error('Private MQTT_SIMULATOR_OPERATOR_PASSWORD required')
    try:
        payload = make_control(args.device, args.action, args.fault)
    except ValueError as error:
        parser.error(str(error))
    connected, published = Event(), Event()
    accepted = []
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv5)
    client.username_pw_set('coldsafe-simulator-operator', password)

    def on_connect(client, userdata, flags, reason, properties):
        if not reason.is_failure:
            connected.set()

    def on_publish(client, userdata, mid, reason, properties):
        accepted.append(not reason.is_failure)
        published.set()

    client.on_connect, client.on_publish = on_connect, on_publish
    try:
        client.connect_async(os.environ.get('MQTT_HOST', 'mosquitto'), int(os.environ.get('MQTT_PORT', '1883')))
        client.loop_start()
        if not connected.wait(10):
            return 1
        result = client.publish(f'coldsafe/simulator/devices/{args.device}/control',
                                json.dumps(payload), qos=1, retain=False)
        if result.rc != mqtt.MQTT_ERR_SUCCESS or not published.wait(10) or not accepted[0]:
            return 1
        print('Control accepted by broker; confirm effect through telemetry (no actuator ACK).')
        return 0
    finally:
        client.disconnect()
        client.loop_stop()


if __name__ == '__main__':
    raise SystemExit(main())
