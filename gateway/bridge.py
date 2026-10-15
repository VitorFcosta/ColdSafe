"""Strict v3 boundaries and a private, durable bridge journal."""
from datetime import datetime, timedelta, timezone
from collections.abc import Callable
import json
from pathlib import Path
import sqlite3
from uuid import UUID, uuid4

from jsonschema import Draft202012Validator, FormatChecker, ValidationError
import psycopg

from simulator.model import SCHEMA, strict_json, utc, validate_catalog

VALIDATORS = {kind: Draft202012Validator({**SCHEMA, '$ref': f'#/$defs/{kind}_event'},
                                       format_checker=FormatChecker())
              for kind in ('telemetry', 'command', 'ack', 'processing_error')}


def encode(event: dict) -> bytes:
    return json.dumps(event, separators=(',', ':'), allow_nan=False).encode('utf-8')


class PermanentError(ValueError):
    """Only a closed, sanitized contract code leaves the validation boundary."""


class PostgresScope:
    def __init__(self, parameters: dict, owner: str, *, connect=psycopg.connect):
        if str(UUID(owner)) != owner:
            raise ValueError('Canonical owner UUID required')
        self.parameters, self.owner, self.connect = parameters, owner, connect

    def __call__(self, catalog: dict) -> bool:
        with self.connect(**self.parameters, connect_timeout=3,
                          options='-c default_transaction_read_only=on -c statement_timeout=3000') as connection:
            return connection.execute(
                'SELECT 1 FROM devices d JOIN environments e ON e.id=d.environment_id '
                'JOIN users u ON u.id=e.owner_user_id WHERE d.id=%s AND d.mqtt_device_id=%s '
                'AND e.id=%s AND u.id=%s AND d.is_active',
                (catalog['device_record_id'], catalog['device_id'], catalog['environment_id'], self.owner),
            ).fetchone() is not None


class Bridge:
    def __init__(self, catalog: dict, path: Path, check_scope: Callable[[dict], bool]):
        validate_catalog(catalog)
        if catalog['device_id'] != 'sim-lab-01':
            raise ValueError('Current MQTT ACL supports only sim-lab-01')
        self.catalog, self.path, self.check_scope = catalog, path, check_scope
        self.db = sqlite3.connect(path)
        # shortcut: retain identities/errors up to 64 MiB; add archival before sustained production.
        self.db.execute('PRAGMA max_page_count=16384')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS ingress (
                event_id TEXT PRIMARY KEY, input BLOB NOT NULL, body BLOB NOT NULL, sent INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS commands (
                command_id TEXT PRIMARY KEY, event_id TEXT UNIQUE NOT NULL,
                body BLOB NOT NULL, sent INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS errors (
                id TEXT PRIMARY KEY, transport TEXT NOT NULL, route TEXT NOT NULL,
                body BLOB NOT NULL, code TEXT NOT NULL, event BLOB NOT NULL, sent INTEGER NOT NULL DEFAULT 0);
        ''')

    def parse(self, raw: bytes) -> dict:
        if len(raw) > 8192:
            raise PermanentError('PAYLOAD_TOO_LARGE')
        try:
            event = strict_json(raw)
            validator = VALIDATORS.get(event.get('type'))
            if validator is None:
                raise ValueError('Unknown type')
            validator.validate(event)
            return event
        except (ValueError, TypeError, UnicodeError, RecursionError, ValidationError):
            raise PermanentError('INVALID_SCHEMA') from None

    def scope(self, event: dict) -> None:
        if (any(event[key] != self.catalog[key] for key in ('device_id', 'device_record_id', 'environment_id'))
                or not self.check_scope(self.catalog)):
            raise PermanentError('UNAUTHORIZED_SCOPE')

    def actuator(self, data: dict) -> None:
        if data['actuator_id'] != self.catalog['actuators'][data['actuator']]:
            raise PermanentError('IDENTITY_MISMATCH')

    def accept_mqtt(self, topic: str, raw: bytes, *, retained: bool, qos: int,
                    now: datetime | None = None) -> dict:
        event = self.parse(raw)
        kind = event['type']
        suffix = {'telemetry': 'telemetry', 'ack': 'acks'}.get(kind)
        if (suffix is None or topic != f"coldsafe/v3/devices/{self.catalog['device_id']}/{suffix}"
                or retained or qos != 1 or event['received_at'] is not None):
            raise PermanentError('INVALID_BINDING')
        self.scope(event)
        if self.db.execute('SELECT 1 FROM commands WHERE event_id=?', (event['event_id'],)).fetchone():
            raise PermanentError('IDENTITY_MISMATCH')
        data = event['data']
        if kind == 'telemetry':
            if (event['correlation_id'] != event['event_id'] or
                    data['equipment']['equipment_id'] != self.catalog['equipment_id'] or
                    any(value['sensor_id'] != self.catalog['sensors'][key]
                        for key, value in data['measurements'].items()) or
                    any(value['actuator_id'] != self.catalog['actuators'][key]
                        for key, value in data['actuators'].items())):
                raise PermanentError('IDENTITY_MISMATCH')
        else:
            self.actuator(data)
            original = self.db.execute('SELECT body FROM commands WHERE command_id=?', (data['command_id'],)).fetchone()
            if (not original or event['correlation_id'] != data['command_id'] or
                    any(data[key] != json.loads(original[0])['data'][key]
                        for key in ('actuator_id', 'actuator'))):
                raise PermanentError('IDENTITY_MISMATCH')
        canonical = encode(event)
        previous = self.db.execute('SELECT input,body FROM ingress WHERE event_id=?', (event['event_id'],)).fetchone()
        if previous:
            if previous[0] != canonical:
                raise PermanentError('IDENTITY_MISMATCH')
            return json.loads(previous[1])
        event['received_at'] = utc(now or datetime.now(timezone.utc))
        body = encode(event)
        if len(body) > 8192:
            raise PermanentError('PAYLOAD_TOO_LARGE')
        with self.db:
            self.db.execute('INSERT INTO ingress(event_id,input,body) VALUES(?,?,?)',
                            (event['event_id'], canonical, body))
        return event

    def accept_command(self, route: str, raw: bytes, *, now: datetime | None = None) -> dict:
        event = self.parse(raw)
        if event['type'] != 'command' or route != f"v3.command.{self.catalog['device_record_id']}":
            raise PermanentError('INVALID_BINDING')
        self.scope(event)
        if self.db.execute('SELECT 1 FROM ingress WHERE event_id=?', (event['event_id'],)).fetchone():
            raise PermanentError('IDENTITY_MISMATCH')
        data = event['data']
        self.actuator(data)
        if event['correlation_id'] != data['command_id']:
            raise PermanentError('IDENTITY_MISMATCH')
        occurred = datetime.fromisoformat(event['occurred_at'].replace('Z', '+00:00'))
        received = datetime.fromisoformat(event['received_at'].replace('Z', '+00:00'))
        deadline = datetime.fromisoformat(data['deadline_at'].replace('Z', '+00:00'))
        now = now or datetime.now(timezone.utc)
        if deadline - occurred != timedelta(seconds=30) or not occurred <= received <= deadline or received > now:
            raise PermanentError('INVALID_BINDING')
        body = encode(event)
        previous = self.db.execute('SELECT body,sent FROM commands WHERE command_id=? OR event_id=?',
                                   (data['command_id'], event['event_id'])).fetchall()
        if previous and any(row[0] != body for row in previous):
            raise PermanentError('IDENTITY_MISMATCH')
        if now > deadline and not (previous and previous[0][1]):
            raise PermanentError('INVALID_BINDING')
        if not previous:
            with self.db:
                self.db.execute('INSERT INTO commands(command_id,event_id,body) VALUES(?,?,?)',
                                (data['command_id'], event['event_id'], body))
        return event

    def record_error(self, transport: str, route: str, raw: bytes, code: str, *,
                     attempt: int = 1, now: datetime | None = None) -> None:
        now = utc(now or datetime.now(timezone.utc))
        identifier = str(uuid4())
        event = {'schema_version': 3, 'event_id': identifier, 'type': 'processing_error',
                 'occurred_at': now, 'received_at': now, 'device_id': None,
                 'device_record_id': None, 'environment_id': None, 'correlation_id': identifier,
                 'data': {'source_event_id': None, 'code': code,
                          'retryable': code == 'PROCESSING_FAILED' and attempt < 3, 'attempt': attempt}}
        VALIDATORS['processing_error'].validate(event)
        with self.db:
            self.db.execute('INSERT INTO errors(id,transport,route,body,code,event) VALUES(?,?,?,?,?,?)',
                            (identifier, transport, route, raw, code, encode(event)))

    def flush(self, publish: Callable[[str, bytes, dict], None]) -> None:
        for table, identifier, column in (('ingress', 'event_id', 'body'), ('errors', 'id', 'event')):
            row = self.db.execute(f'SELECT {identifier},{column} FROM {table} WHERE sent=0 ORDER BY rowid LIMIT 1').fetchone()
            if row:
                event = json.loads(row[1])
                scope = event['correlation_id'] if event['type'] == 'processing_error' else event['device_record_id']
                publish(f"v3.{event['type']}.{scope}", row[1], event)
                with self.db:
                    self.db.execute(f'UPDATE {table} SET sent=1 WHERE {identifier}=?', (row[0],))
