"""Bounded, metadata-only samples; PostgreSQL proves private scope on every read."""
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
import re
from threading import Lock
from uuid import UUID

from jsonschema import Draft202012Validator, FormatChecker
import pika
import psycopg

from backend.app.config.settings import RuntimeSettings
from backend.app.repositories.postgres import connect
from backend.app.services.messaging import MessagingUnavailable, QUEUE_NAMES
from simulator.model import SCHEMA, strict_json

CAPACITY = 100
STALE_AFTER_SECONDS = 30
EVENT_TYPES = frozenset(key.removesuffix('_event') for key in SCHEMA['$defs'] if key.endswith('_event'))
ERROR_CODES = frozenset(SCHEMA['$defs']['processing_error_data']['properties']['code']['enum'])
DEATH_REASONS = frozenset(('rejected', 'expired', 'maxlen', 'delivery_limit'))
VALIDATORS = {kind: Draft202012Validator({**SCHEMA, '$ref': f'#/$defs/{kind}_event'},
                                       format_checker=FormatChecker()) for kind in EVENT_TYPES}


@dataclass(frozen=True)
class MessageSample:
    event_id: str
    type: str
    occurred_at: datetime
    observed_at: datetime
    device_record_id: str
    device_id: str
    environment_id: str
    correlation_id: str
    source_queue: str | None
    reason: str | None
    error_code: str | None


@dataclass(frozen=True)
class MessageSnapshot:
    sampled_at: datetime
    connected: bool
    last_observed_at: datetime | None
    stale: bool
    messages: tuple[MessageSample, ...]
    dead_letters: tuple[MessageSample, ...]
    stale_after_seconds: int = STALE_AFTER_SECONDS
    capacity_per_kind: int = CAPACITY


def _sample(exchange: str, properties: pika.BasicProperties, raw: bytes) -> MessageSample:
    event = strict_json(raw)
    kind = event.get('type')
    if (type(event.get('schema_version')) is not int or event['schema_version'] != 3
            or not isinstance(kind, str) or kind not in EVENT_TYPES):
        raise ValueError('Invalid envelope')
    for key in ('event_id', 'correlation_id', 'device_record_id', 'environment_id'):
        value = event.get(key)
        if not isinstance(value, str) or len(value) != 36 or str(UUID(value)) != value:
            raise ValueError('Unproven identity')
    device = event.get('device_id')
    if not isinstance(device, str) or re.fullmatch(r'[A-Za-z0-9._-]{1,64}', device) is None:
        raise ValueError('Invalid device identity')
    instant = event.get('occurred_at')
    if not isinstance(instant, str) or len(instant) > 40:
        raise ValueError('Invalid event time')
    occurred_at = datetime.fromisoformat(instant)
    if occurred_at.tzinfo is None or occurred_at.utcoffset().total_seconds() != 0:
        raise ValueError('UTC event time required')
    source_queue = reason = error_code = None
    if exchange == 'coldsafe.dlx':
        headers = properties.headers if isinstance(properties.headers, dict) else {}
        deaths = headers.get('x-death')
        if isinstance(deaths, list) and deaths and isinstance(deaths[0], dict):
            death = deaths[0]
            queue, candidate_reason = death.get('queue'), death.get('reason')
            if isinstance(queue, str) and queue in QUEUE_NAMES and queue not in ('coldsafe.observability', 'coldsafe.dlq'):
                source_queue = queue
            if isinstance(candidate_reason, str) and candidate_reason in DEATH_REASONS:
                reason = candidate_reason
        if not VALIDATORS[kind].is_valid(event):
            error_code = 'INVALID_SCHEMA'
    elif exchange == 'coldsafe.jobs.unrouted':
        reason = 'unroutable'
    elif exchange not in ('coldsafe.events', 'coldsafe.jobs'):
        raise ValueError('Unexpected observation exchange')
    if kind == 'processing_error' and isinstance(event.get('data'), dict):
        code = event['data'].get('code')
        if isinstance(code, str) and code in ERROR_CODES:
            error_code = code
    return MessageSample(
        event_id=event['event_id'], type=kind, occurred_at=occurred_at,
        observed_at=datetime.now(UTC), device_record_id=event['device_record_id'],
        device_id=device, environment_id=event['environment_id'], correlation_id=event['correlation_id'],
        source_queue=source_queue, reason=reason, error_code=error_code,
    )


class MessageSamples:
    def __init__(self, settings: RuntimeSettings):
        self.settings = settings
        self._messages: deque[MessageSample] = deque(maxlen=CAPACITY)
        self._dead_letters: deque[MessageSample] = deque(maxlen=CAPACITY)
        self._connected = False
        self._lock = Lock()

    def set_connected(self, connected: bool) -> None:
        with self._lock:
            self._connected = connected

    def record(self, exchange: str, properties: pika.BasicProperties, raw: bytes) -> None:
        try:
            sample = _sample(exchange, properties, raw)
        except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
            # Unprovable envelopes cannot become private samples; only their observation copy is ACKed.
            return
        with self._lock:
            target = self._dead_letters if exchange in ('coldsafe.dlx', 'coldsafe.jobs.unrouted') else self._messages
            for previous in tuple(target):
                if (previous.event_id, previous.source_queue) == (sample.event_id, sample.source_queue):
                    target.remove(previous)
                    break
            target.append(sample)

    def snapshot(self, actor: UUID) -> MessageSnapshot:
        with self._lock:
            messages, dead_letters = tuple(reversed(self._messages)), tuple(reversed(self._dead_letters))
            connected = self._connected
        candidates = {UUID(sample.device_record_id) for sample in messages + dead_letters}
        allowed = set()
        if candidates:
            try:
                with connect(self.settings) as connection:
                    rows = connection.execute(
                        'SELECT d.id, d.environment_id, d.mqtt_device_id FROM devices d '
                        'JOIN environments e ON e.id = d.environment_id '
                        'WHERE e.owner_user_id = %s AND d.is_active AND d.id = ANY(%s)',
                        (actor, list(candidates)),
                    ).fetchall()
                allowed = {(str(device), str(environment), mqtt_id) for device, environment, mqtt_id in rows}
            except psycopg.Error:
                raise MessagingUnavailable('Message samples unavailable') from None
        messages, dead_letters = tuple(
            tuple(sample for sample in collection
                  if (sample.device_record_id, sample.environment_id, sample.device_id) in allowed)
            for collection in (messages, dead_letters)
        )
        last_observed_at = max((sample.observed_at for sample in messages + dead_letters), default=None)
        now = datetime.now(UTC)
        return MessageSnapshot(
            sampled_at=now, connected=connected, last_observed_at=last_observed_at,
            stale=last_observed_at is None or (now - last_observed_at).total_seconds() > STALE_AFTER_SECONDS,
            messages=messages, dead_letters=dead_letters,
        )
