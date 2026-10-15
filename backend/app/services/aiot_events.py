"""Transactional v3 inbox, rules and outbox, isolated from legacy MQTT effects."""
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from backend.app.config.settings import RuntimeSettings
from backend.app.domain.reading_classification import TemperatureThresholds
from backend.app.repositories.postgres import connect
from gateway.bridge import PermanentError, encode
from simulator.model import SCHEMA, utc, validate_catalog


def instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def freshness(telemetry: dict | None, now: datetime) -> dict:
    age = max(0.0, (now - instant(telemetry['received_at'])).total_seconds()) if telemetry else None
    return {
        'last_event_id': telemetry['event_id'] if telemetry else None,
        'last_received_at': telemetry['received_at'] if telemetry else None,
        'state': 'no_data' if age is None else 'fresh' if age <= 30 else 'stale',
        'age_seconds': age, 'stale_after_seconds': 30,
    }


def ack_status(command: dict, data: dict, received_at: datetime) -> str | None:
    if command['status'] != 'pending' or received_at < command['accepted_at']:
        return None
    if received_at > command['deadline_at']:
        return 'unconfirmed'
    return ('confirmed' if data['result'] == 'applied'
            and data['applied_state'] == command['desired_state'] else 'rejected')


class AiotEventService:
    def __init__(self, settings: RuntimeSettings, catalog: dict, owner_user_id: str):
        validate_catalog(catalog)
        if str(UUID(owner_user_id)) != owner_user_id:
            raise ValueError('Canonical owner UUID required')
        self.settings, self.catalog, self.owner_user_id = settings, catalog, owner_user_id

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)

    @contextmanager
    def _cursor(self) -> Iterator:
        with connect(self.settings) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                yield cursor

    def _scope(self, cursor, user_id: UUID | str | None = None) -> bool:
        return cursor.execute(
            'SELECT d.id FROM devices d JOIN environments e ON e.id=d.environment_id '
            'WHERE d.id=%s AND d.mqtt_device_id=%s AND e.id=%s AND e.owner_user_id=%s '
            'AND e.owner_user_id=%s AND d.is_active FOR UPDATE OF d,e',
            (self.catalog['device_record_id'], self.catalog['device_id'],
             self.catalog['environment_id'], self.owner_user_id, user_id or self.owner_user_id),
        ).fetchone() is not None

    def _validate(self, event: dict) -> None:
        try:
            if len(encode(event)) > 8192:
                raise PermanentError('PAYLOAD_TOO_LARGE')
            kind = event['type']
            if kind not in ('telemetry', 'ack', 'prediction', 'telemetry_persisted',
                            'alert', 'freshness', 'command_status'):
                raise PermanentError('INVALID_BINDING')
            Draft202012Validator({**SCHEMA, '$ref': f'#/$defs/{kind}_event'},
                                 format_checker=FormatChecker()).validate(event)
            if event['received_at'] is None or instant(event['received_at']) > self._now():
                raise PermanentError('INVALID_BINDING')
            if any(event[key] != self.catalog[key]
                   for key in ('device_id', 'device_record_id', 'environment_id')):
                raise PermanentError('UNAUTHORIZED_SCOPE')
            data = event['data']
            if kind == 'telemetry':
                if (event['correlation_id'] != event['event_id']
                        or data['equipment']['equipment_id'] != self.catalog['equipment_id']
                        or any(v['sensor_id'] != self.catalog['sensors'][k]
                               for k, v in data['measurements'].items())
                        or any(v['actuator_id'] != self.catalog['actuators'][k]
                               for k, v in data['actuators'].items())):
                    raise PermanentError('IDENTITY_MISMATCH')
            elif kind in ('prediction', 'telemetry_persisted'):
                if (data['equipment_id'] != self.catalog['equipment_id']
                        or event['correlation_id'] != data['source_event_id']):
                    raise PermanentError('IDENTITY_MISMATCH')
            elif kind == 'ack':
                if (data['actuator_id'] != self.catalog['actuators'][data['actuator']]
                        or event['correlation_id'] != data['command_id']):
                    raise PermanentError('IDENTITY_MISMATCH')
        except PermanentError:
            raise
        except (KeyError, TypeError, ValueError, ValidationError, RecursionError):
            raise PermanentError('INVALID_SCHEMA') from None

    def _event(self, kind: str, data: dict, correlation_id: str, now: datetime) -> dict:
        return {'schema_version': 3, 'event_id': str(uuid4()), 'type': kind,
                'occurred_at': utc(now), 'received_at': utc(now),
                **{key: self.catalog[key] for key in ('device_id', 'device_record_id', 'environment_id')},
                'correlation_id': correlation_id, 'data': data}

    def _output(self, cursor, event: dict) -> None:
        cursor.execute('INSERT INTO aiot_outbox (event_id,device_id,envelope) VALUES (%s,%s,%s)',
                       (event['event_id'], self.catalog['device_record_id'], Jsonb(event)))

    def _audit(self, cursor, kind: str, details: dict, actor: UUID | None = None) -> None:
        cursor.execute('INSERT INTO audit_events (actor_user_id,device_id,event_type,details) '
                       'VALUES (%s,%s,%s,%s)',
                       (actor, self.catalog['device_record_id'], kind, Jsonb(details)))

    @staticmethod
    def _latest(cursor, device_id: str) -> dict | None:
        row = cursor.execute(
            "SELECT envelope FROM aiot_events WHERE device_id=%s AND kind='telemetry' "
            'ORDER BY received_at DESC,event_id DESC LIMIT 1', (device_id,),
        ).fetchone()
        return row['envelope'] if row else None

    def process(self, event: dict) -> None:
        self._validate(event)
        with self._cursor() as cursor:
            if not self._scope(cursor):
                raise PermanentError('UNAUTHORIZED_SCOPE')
            if event['type'] in ('alert', 'freshness', 'command_status'):
                output = cursor.execute('SELECT envelope FROM aiot_outbox WHERE event_id=%s AND device_id=%s',
                                        (event['event_id'], event['device_record_id'])).fetchone()
                if output is None or output['envelope'] != event:
                    raise PermanentError('IDENTITY_MISMATCH')
            previous = cursor.execute(
                "SELECT envelope FROM aiot_inbox WHERE consumer='api-v3' AND event_id=%s",
                (event['event_id'],),
            ).fetchone()
            if previous:
                if previous['envelope'] != event:
                    raise PermanentError('IDENTITY_MISMATCH')
                return
            cursor.execute('INSERT INTO aiot_inbox (consumer,event_id,device_id,envelope) '
                           "VALUES ('api-v3',%s,%s,%s)",
                           (event['event_id'], event['device_record_id'], Jsonb(event)))
            kind, data = event['type'], event['data']
            cursor.execute('INSERT INTO aiot_events '
                           '(event_id,device_id,kind,received_at,source_event_id,envelope) '
                           'VALUES (%s,%s,%s,%s,%s,%s)',
                           (event['event_id'], event['device_record_id'], kind,
                            event['received_at'], data.get('source_event_id'), Jsonb(event)))
            if kind == 'telemetry':
                # A receipt or prediction can arrive before its source on independent queues.
                deferred = cursor.execute('SELECT envelope FROM aiot_events '
                                          'WHERE source_event_id=%s AND NOT linked',
                                          (event['event_id'],)).fetchall()
                for row in deferred:
                    try:
                        self._link(cursor, row['envelope'])
                    except PermanentError as error:
                        self._audit(cursor, 'aiot_link_rejected', {
                            'event_id': row['envelope']['event_id'], 'code': str(error)})
                if self._latest(cursor, event['device_record_id'])['event_id'] == event['event_id']:
                    if freshness(event, self._now())['state'] == 'fresh':
                        self._evaluate(cursor, event)
                    self._freshness(cursor)
            elif kind in ('prediction', 'telemetry_persisted'):
                self._link(cursor, event)
            elif kind == 'ack':
                self._ack(cursor, event)

    def _link(self, cursor, event: dict) -> None:
        data = event['data']
        source = cursor.execute("SELECT envelope FROM aiot_events WHERE event_id=%s "
                                "AND kind='telemetry'", (data['source_event_id'],)).fetchone()
        if source is None:
            return
        telemetry = source['envelope']
        if (any(event[key] != telemetry[key] for key in
                ('device_id', 'device_record_id', 'environment_id', 'correlation_id'))
                or data['equipment_id'] != telemetry['data']['equipment']['equipment_id']
                or instant(data['input_received_at']) != instant(telemetry['received_at'])):
            raise PermanentError('IDENTITY_MISMATCH')
        if event['type'] == 'telemetry_persisted' and (
                instant(event['occurred_at']) < instant(telemetry['received_at'])
                or instant(event['received_at']) < instant(telemetry['received_at'])):
            raise PermanentError('IDENTITY_MISMATCH')
        if event['type'] == 'prediction':
            if (instant(event['occurred_at']) < instant(telemetry['received_at'])
                    or instant(event['received_at']) < instant(telemetry['received_at'])):
                raise PermanentError('IDENTITY_MISMATCH')
            if data['model_id'] is not None:
                model = cursor.execute('SELECT model_version,features_version FROM models '
                                       'WHERE id=%s AND owner_user_id=%s',
                                       (data['model_id'], self.owner_user_id)).fetchone()
                if (model is None or model['model_version'] != data['model_version']
                        or model['features_version'] != data['features_version']):
                    raise PermanentError('UNAUTHORIZED_SCOPE')
            age = (instant(event['occurred_at']) - instant(data['input_received_at'])).total_seconds()
            if data['reason'] == 'stale_input' and age <= 30:
                raise PermanentError('IDENTITY_MISMATCH')
            if data['status'] == 'available' and age > 30:
                raise PermanentError('IDENTITY_MISMATCH')
        cursor.execute('UPDATE aiot_events SET linked=true WHERE event_id=%s',
                       (event['event_id'],))

    def _freshness(self, cursor) -> None:
        telemetry = self._latest(cursor, self.catalog['device_record_id'])
        now = self._now()
        data = freshness(telemetry, now)
        previous = cursor.execute('SELECT state FROM aiot_freshness WHERE device_id=%s',
                                  (self.catalog['device_record_id'],)).fetchone()
        if previous and previous['state'] == data['state']:
            return
        cursor.execute('INSERT INTO aiot_freshness (device_id,state) VALUES (%s,%s) '
                       'ON CONFLICT (device_id) DO UPDATE SET state=EXCLUDED.state',
                       (self.catalog['device_record_id'], data['state']))
        event = self._event('freshness', data, telemetry['correlation_id'] if telemetry else str(uuid4()), now)
        self._output(cursor, event)

    def _command(self, cursor, actuator: str, desired_state: bool, user_id: UUID | None) -> dict:
        now, command_id = self._now(), str(uuid4())
        command = self._event('command', {
            'command_id': command_id, 'actuator_id': self.catalog['actuators'][actuator],
            'actuator': actuator, 'desired_state': desired_state,
            'source': 'manual' if actuator == 'led' else 'automatic',
            'deadline_at': utc(now + timedelta(seconds=30)),
        }, command_id, now)
        status = self._status_event(command, 'pending', now)
        cursor.execute('INSERT INTO aiot_commands (command_id,device_id,actuator,desired_state,status,'
                       'accepted_at,deadline_at,envelope,status_envelope) '
                       "VALUES (%s,%s,%s,%s,'pending',%s,%s,%s,%s)",
                       (command_id, command['device_record_id'], actuator, desired_state,
                        now, now + timedelta(seconds=30), Jsonb(command), Jsonb(status)))
        self._audit(cursor, 'aiot_command_requested', command['data'], user_id)
        self._output(cursor, command)
        self._output(cursor, status)
        return status

    def _status_event(self, command: dict, status: str, now: datetime) -> dict:
        data = command['data']
        return self._event('command_status', {
            **{key: data[key] for key in ('command_id', 'actuator_id', 'actuator', 'desired_state')},
            'confirmed_state': data['desired_state'] if status == 'confirmed' else None,
            'status': status,
        }, data['command_id'], now)

    def request_led(self, user_id: UUID, device_id: str, desired_state: bool) -> dict | None:
        if type(desired_state) is not bool:
            raise ValueError('desired_state must be boolean')
        with self._cursor() as cursor:
            if device_id != self.catalog['device_id'] or not self._scope(cursor, user_id):
                return None
            role = cursor.execute('SELECT role FROM users WHERE id=%s', (user_id,)).fetchone()
            if role is None or role['role'] not in ('operator', 'admin'):
                raise PermissionError('FORBIDDEN')
            return self._command(cursor, 'led', desired_state, user_id)

    def _set_status(self, cursor, row: dict, status: str) -> None:
        event = self._status_event(row['envelope'], status, self._now())
        cursor.execute('UPDATE aiot_commands SET status=%s,status_envelope=%s WHERE command_id=%s',
                       (status, Jsonb(event), row['command_id']))
        self._audit(cursor, f'aiot_command_{status}', event['data'])
        self._output(cursor, event)

    def _ack(self, cursor, event: dict) -> None:
        data = event['data']
        row = cursor.execute('SELECT * FROM aiot_commands WHERE command_id=%s AND device_id=%s '
                             'FOR UPDATE', (data['command_id'], event['device_record_id'])).fetchone()
        if row is None:
            raise PermanentError('IDENTITY_MISMATCH')
        if (data['actuator'] != row['actuator']
                or data['actuator_id'] != row['envelope']['data']['actuator_id']):
            self._audit(cursor, 'aiot_ack_mismatch', {'event_id': event['event_id'], **data})
            return
        received = instant(event['received_at'])
        if row['status'] == 'unconfirmed' or received > row['deadline_at']:
            self._audit(cursor, 'aiot_ack_late', {'event_id': event['event_id'], **data})
        status = ack_status(row, data, received)
        if status is not None:
            self._set_status(cursor, row, status)
        elif received < row['accepted_at']:
            self._audit(cursor, 'aiot_ack_before_command', {'event_id': event['event_id'], **data})

    def _evaluate(self, cursor, event: dict) -> None:
        rule = cursor.execute('SELECT temp_min_c,temp_max_c,recovery_margin_c FROM environment_rules '
                              'WHERE environment_id=%s', (self.catalog['environment_id'],)).fetchone()
        thresholds = (TemperatureThresholds(float(rule['temp_min_c']), float(rule['temp_max_c']),
                                           float(rule['recovery_margin_c'])) if rule else TemperatureThresholds())
        temperature = event['data']['measurements']['ambient_temperature']['value']
        kind = ('temperature_low' if temperature < thresholds.min_c else
                'temperature_high' if temperature > thresholds.max_c else None)
        recovered = thresholds.min_c + thresholds.attention_margin_c <= temperature <= thresholds.max_c - thresholds.attention_margin_c
        opened = cursor.execute('SELECT * FROM aiot_alerts WHERE device_id=%s AND closed_at IS NULL '
                                'FOR UPDATE', (self.catalog['device_record_id'],)).fetchall()
        for alert in opened:
            if (kind is not None and alert['kind'] != kind) or (kind is None and recovered):
                self._alert(cursor, event, str(alert['alert_id']), alert['kind'], 'closed')
        if kind is not None and not any(alert['kind'] == kind for alert in opened):
            self._alert(cursor, event, str(uuid4()), kind, 'opened')
        desired = bool(kind) or (bool(opened) and not recovered)
        latest = cursor.execute("SELECT desired_state,status,deadline_at FROM aiot_commands "
                                "WHERE device_id=%s AND actuator='buzzer' "
                                'ORDER BY accepted_at DESC,command_id DESC LIMIT 1',
                                (self.catalog['device_record_id'],)).fetchone()
        if ((latest is None and desired) or (latest is not None and (
                latest['desired_state'] != desired or (latest['status'] in ('unconfirmed', 'rejected', 'pending')
                and latest['deadline_at'] < self._now())))):
            self._command(cursor, 'buzzer', desired, None)

    def _alert(self, cursor, source: dict, alert_id: str, kind: str, state: str) -> None:
        event = self._event('alert', {'alert_id': alert_id, 'equipment_id': self.catalog['equipment_id'],
                            'kind': kind, 'state': state, 'source_event_id': source['event_id']},
                            source['correlation_id'], self._now())
        if state == 'opened':
            cursor.execute('INSERT INTO aiot_alerts (alert_id,device_id,kind,opened_at,envelope) '
                           'VALUES (%s,%s,%s,%s,%s)',
                           (alert_id, source['device_record_id'], kind, source['received_at'], Jsonb(event)))
        else:
            cursor.execute('UPDATE aiot_alerts SET closed_at=%s,envelope=%s WHERE alert_id=%s',
                           (source['received_at'], Jsonb(event), alert_id))
        self._audit(cursor, f'aiot_alert_{state}', event['data'])
        self._output(cursor, event)

    def expire_pending(self) -> None:
        with self._cursor() as cursor:
            if not self._scope(cursor):
                return
            self._expire(cursor)
            self._freshness(cursor)

    def _expire(self, cursor) -> None:
        rows = cursor.execute("SELECT * FROM aiot_commands WHERE device_id=%s AND status='pending' "
                              'AND deadline_at < %s FOR UPDATE',
                              (self.catalog['device_record_id'], self._now())).fetchall()
        for row in rows:
            self._set_status(cursor, row, 'unconfirmed')

    def pending_outputs(self) -> list[dict]:
        with self._cursor() as cursor:
            if not self._scope(cursor):
                return []
            rows = cursor.execute('SELECT envelope FROM aiot_outbox WHERE device_id=%s '
                                  'AND published_at IS NULL ORDER BY sequence LIMIT 100',
                                  (self.catalog['device_record_id'],)).fetchall()
            return [row['envelope'] for row in rows]

    def mark_published(self, event_id: str) -> None:
        with self._cursor() as cursor:
            cursor.execute('UPDATE aiot_outbox SET published_at=now() '
                           'WHERE event_id=%s AND device_id=%s AND published_at IS NULL',
                           (event_id, self.catalog['device_record_id']))

    def _reading(self, cursor, telemetry: dict) -> dict:
        related = cursor.execute('SELECT kind,envelope FROM aiot_events WHERE source_event_id=%s '
                                 'AND linked ORDER BY received_at DESC,event_id DESC',
                                 (telemetry['event_id'],)).fetchall()
        prediction = next((row['envelope'] for row in related if row['kind'] == 'prediction'), None)
        return {'telemetry': telemetry, 'prediction': prediction,
                'persistence': 'persisted' if any(row['kind'] == 'telemetry_persisted' for row in related) else 'pending'}

    def snapshot(self, user_id: UUID, device_id: str) -> dict | None:
        with self._cursor() as cursor:
            if device_id != self.catalog['device_id'] or not self._scope(cursor, user_id):
                return None
            metadata = cursor.execute(
                'SELECT e.id,e.name,r.temp_min_c AS min_c,r.temp_max_c AS max_c,'
                'r.recovery_margin_c AS attention_margin_c FROM environments e '
                'JOIN environment_rules r ON r.environment_id=e.id WHERE e.id=%s',
                (self.catalog['environment_id'],),
            ).fetchone()
            if metadata is None:
                raise RuntimeError('Commissioned environment rules are missing')
            self._expire(cursor)
            telemetry = self._latest(cursor, self.catalog['device_record_id'])
            result = self._reading(cursor, telemetry) if telemetry else {
                'telemetry': None, 'prediction': None, 'persistence': None}
            commands = cursor.execute('SELECT DISTINCT ON (actuator) actuator,status_envelope '
                                      'FROM aiot_commands WHERE device_id=%s '
                                      'ORDER BY actuator,accepted_at DESC,command_id DESC',
                                      (self.catalog['device_record_id'],)).fetchall()
            alerts = cursor.execute('SELECT envelope FROM aiot_alerts WHERE device_id=%s '
                                    'ORDER BY opened_at DESC,alert_id DESC LIMIT 100',
                                    (self.catalog['device_record_id'],)).fetchall()
            state = freshness(telemetry, self._now())
            if state['state'] == 'stale':
                result['prediction'] = None
            return {**result, 'environment': {'id': str(metadata['id']), 'name': metadata['name']},
                    'device': {'id': device_id},
                    'thresholds': {key: float(metadata[key]) for key in
                                   ('min_c', 'max_c', 'attention_margin_c')},
                    'freshness': state,
                    'prediction_unavailable_reason': 'stale_input' if state['state'] == 'stale' else None,
                    'commands': {'led': None, 'buzzer': None, **{
                        row['actuator']: row['status_envelope'] for row in commands}},
                    'alerts': [row['envelope'] for row in alerts]}

    @staticmethod
    def _validate_range(start: datetime | None, end: datetime | None, limit: int) -> None:
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError('limit must be between 1 and 1000')
        if (start is None) != (end is None) or (
                start is not None and (start.utcoffset() is None or end.utcoffset() is None or start >= end)):
            raise ValueError('invalid time interval')

    def history(self, user_id: UUID, device_id: str, limit: int, *,
                start: datetime | None = None, end: datetime | None = None) -> list[dict] | None:
        self._validate_range(start, end, limit)
        with self._cursor() as cursor:
            if device_id != self.catalog['device_id'] or not self._scope(cursor, user_id):
                return None
            rows = cursor.execute("SELECT envelope FROM aiot_events WHERE device_id=%s AND kind='telemetry' "
                                  'AND (%s::timestamptz IS NULL OR received_at >= %s) '
                                  'AND (%s::timestamptz IS NULL OR received_at < %s) '
                                  'ORDER BY received_at DESC,event_id DESC LIMIT %s',
                                  (self.catalog['device_record_id'], start, start, end, end, limit)).fetchall()
            return [self._reading(cursor, row['envelope']) for row in rows]

    def get_command_for_user(self, user_id: UUID, command_id: UUID) -> dict | None:
        with self._cursor() as cursor:
            if not self._scope(cursor, user_id):
                return None
            self._expire(cursor)
            row = cursor.execute('SELECT status_envelope FROM aiot_commands '
                                 'WHERE command_id=%s AND device_id=%s',
                                 (command_id, self.catalog['device_record_id'])).fetchone()
            return row['status_envelope'] if row else None

    def list_alerts(self, user_id: UUID, device_id: str, *, start: datetime | None,
                    end: datetime | None, limit: int) -> list[dict] | None:
        self._validate_range(start, end, limit)
        with self._cursor() as cursor:
            if device_id != self.catalog['device_id'] or not self._scope(cursor, user_id):
                return None
            rows = cursor.execute(
                'SELECT alert_id,kind,opened_at,closed_at FROM aiot_alerts WHERE device_id=%s '
                'AND (%s::timestamptz IS NULL OR opened_at < %s) '
                'AND (%s::timestamptz IS NULL OR closed_at IS NULL OR closed_at > %s) '
                'ORDER BY opened_at DESC,alert_id DESC LIMIT %s',
                (self.catalog['device_record_id'], end, end, start, start, limit),
            ).fetchall()
            return [{'alert_id': str(row['alert_id']), 'device_id': device_id,
                     'kind': row['kind'], 'opened_at': row['opened_at'], 'closed_at': row['closed_at'],
                     'status': 'open' if row['closed_at'] is None else 'closed'} for row in rows]

    def persisted_telemetry(self, source_event_id: str) -> dict | None:
        with self._cursor() as cursor:
            if not self._scope(cursor):
                return None
            row = cursor.execute("SELECT t.envelope FROM aiot_events t WHERE t.event_id=%s "
                                 "AND t.device_id=%s AND t.kind='telemetry' AND EXISTS ("
                                 "SELECT 1 FROM aiot_events p WHERE p.source_event_id=t.event_id "
                                 "AND p.kind='telemetry_persisted' AND p.linked)",
                                 (source_event_id, self.catalog['device_record_id'])).fetchone()
            return row['envelope'] if row else None

    def trusted_output(self, event: dict) -> bool:
        with self._cursor() as cursor:
            if not self._scope(cursor):
                return False
            row = cursor.execute('SELECT envelope FROM aiot_outbox WHERE event_id=%s AND device_id=%s',
                                 (event['event_id'], self.catalog['device_record_id'])).fetchone()
            return row is not None and row['envelope'] == event

    def _deliverable_prediction(self, cursor, event: dict) -> dict | None:
        source = cursor.execute("SELECT t.envelope FROM aiot_events t WHERE t.event_id=%s "
                                "AND t.device_id=%s AND t.kind='telemetry' AND EXISTS ("
                                "SELECT 1 FROM aiot_events p WHERE p.source_event_id=t.event_id "
                                "AND p.kind='telemetry_persisted' AND p.linked)",
                                (event['data']['source_event_id'], self.catalog['device_record_id'])).fetchone()
        if source is None:
            return None
        if (event['data']['status'] == 'available'
                and freshness(source['envelope'], self._now())['state'] == 'stale'):
            return None
        return event

    def linked_prediction(self, event_id: str) -> dict | None:
        with self._cursor() as cursor:
            if not self._scope(cursor):
                return None
            row = cursor.execute("SELECT envelope FROM aiot_events WHERE event_id=%s AND device_id=%s "
                                 "AND kind='prediction' AND linked",
                                 (event_id, self.catalog['device_record_id'])).fetchone()
            return self._deliverable_prediction(cursor, row['envelope']) if row else None

    def prediction_for_source(self, source_event_id: str) -> dict | None:
        with self._cursor() as cursor:
            if not self._scope(cursor):
                return None
            row = cursor.execute("SELECT envelope FROM aiot_events WHERE source_event_id=%s AND device_id=%s "
                                 "AND kind='prediction' AND linked ORDER BY received_at DESC,event_id DESC LIMIT 1",
                                 (source_event_id, self.catalog['device_record_id'])).fetchone()
            return self._deliverable_prediction(cursor, row['envelope']) if row else None
