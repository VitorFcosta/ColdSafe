"""Deterministic sensor simulation; latent wear never enters live telemetry."""
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import random
from uuid import uuid4

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / 'contracts/aiot.schema.json').read_text())
TELEMETRY = Draft202012Validator({**SCHEMA, '$ref': '#/$defs/telemetry_event'}, format_checker=FormatChecker())
SENSORS = {
    'ambient_temperature': ('degC', -40, 80, 0.08),
    'humidity': ('percent', 0, 100, 0.3),
    'light': ('percent', 0, 100, 0.5),
    'vibration': ('mm/s', 0, 100, 0.03),
    'motor_current': ('A', 0, 100, 0.02),
    'motor_temperature': ('degC', -40, 200, 0.1),
}


def utc(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset().total_seconds() != 0:
        raise ValueError('UTC time required')
    return value.isoformat().replace('+00:00', 'Z')


def strict_json(payload: bytes, limit: int = 8192) -> dict:
    if len(payload) > limit:
        raise ValueError('Payload too large')

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate JSON key')
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError('Non-finite JSON number')

    value = json.loads(payload.decode('utf-8'), object_pairs_hook=pairs, parse_constant=invalid_constant)
    if not isinstance(value, dict):
        raise ValueError('JSON object required')
    return value


def validate_catalog(catalog: dict) -> None:
    uuid_schema = SCHEMA['$defs']['uuid']
    schema = {
        'type': 'object', 'additionalProperties': False,
        'required': ['device_id', 'device_record_id', 'environment_id', 'equipment_id', 'sensors', 'actuators'],
        'properties': {
            'device_id': SCHEMA['$defs']['device_id'],
            **{key: uuid_schema for key in ('device_record_id', 'environment_id', 'equipment_id')},
            'sensors': {'type': 'object', 'additionalProperties': False, 'required': list(SENSORS),
                        'properties': {key: uuid_schema for key in SENSORS}},
            'actuators': {'type': 'object', 'additionalProperties': False, 'required': ['led', 'buzzer'],
                          'properties': {key: uuid_schema for key in ('led', 'buzzer')}},
        },
    }
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(catalog)
    identities = [catalog[key] for key in ('device_record_id', 'environment_id', 'equipment_id')]
    identities += list(catalog['sensors'].values()) + list(catalog['actuators'].values())
    if len(identities) != len(set(identities)):
        raise ValueError('Catalog identities must be distinct')


class Simulator:
    def __init__(self, catalog: dict, seed: int = 42):
        validate_catalog(catalog)
        self.catalog = json.loads(json.dumps(catalog))
        self.random = random.Random(seed)
        self.bearing_wear = 0.0
        self.imbalance = 0.0
        self.faults = set()
        self.elapsed_seconds = 0.0
        self.ambient_temperature = 5.0
        self.active = True
        self.led = False
        self.buzzer = False

    def inject_fault(self, fault: str) -> None:
        if fault not in ('bearing_wear', 'imbalance'):
            raise ValueError('Unknown failure mode')
        self.faults.add(fault)

    def sample(self, step_seconds: float, now: datetime | None = None) -> dict:
        if isinstance(step_seconds, bool) or not math.isfinite(step_seconds) or not 0 < step_seconds <= 3600:
            raise ValueError('Step must be finite, positive and at most one hour')
        if not self.active:
            raise ValueError('Simulation paused')
        self.bearing_wear = min(1.0, self.bearing_wear + step_seconds / 3600 *
                                (0.6 if 'bearing_wear' in self.faults else 0.001))
        self.imbalance = min(1.0, self.imbalance + step_seconds / 3600 *
                             (0.6 if 'imbalance' in self.faults else 0.002))
        self.elapsed_seconds += step_seconds
        wear, imbalance = self.bearing_wear, self.imbalance
        efficiency_loss = 0.6 * wear + 0.4 * imbalance
        target = 5 + 14 * efficiency_loss
        self.ambient_temperature += (target - self.ambient_temperature) * (1 - math.exp(-step_seconds / 300))
        phase = 2 * math.pi * self.elapsed_seconds / 86400
        values = {
            'ambient_temperature': self.ambient_temperature,
            'humidity': 60 + 5 * math.sin(phase),
            'light': 25 + 10 * math.sin(phase) + (40 if self.led else 0),
            'vibration': 0.6 + 7 * wear + 10 * imbalance,
            'motor_current': 1.2 + 2.5 * wear + 1.5 * imbalance,
            'motor_temperature': 32 + 38 * wear + 22 * imbalance,
        }
        measurements = {}
        for key, value in values.items():
            unit, lower, upper, noise = SENSORS[key]
            measurements[key] = {'sensor_id': self.catalog['sensors'][key], 'unit': unit,
                                 'value': round(min(upper, max(lower, value + self.random.gauss(0, noise))), 4)}
        event_id = str(uuid4())
        event = {
            'schema_version': 3, 'event_id': event_id, 'type': 'telemetry',
            'occurred_at': utc(now or datetime.now(timezone.utc)), 'received_at': None,
            **{key: self.catalog[key] for key in ('device_id', 'device_record_id', 'environment_id')},
            'correlation_id': event_id,
            'data': {
                'equipment': {'equipment_id': self.catalog['equipment_id'], 'running': True},
                'measurements': measurements,
                'actuators': {key: {'actuator_id': self.catalog['actuators'][key], 'actual_state': getattr(self, key)}
                              for key in ('led', 'buzzer')},
            },
        }
        TELEMETRY.validate(event)
        return event
