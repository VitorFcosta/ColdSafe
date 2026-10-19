"""Read aggregate broker metrics without exposing messages or connection details."""
import base64
import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from http.client import HTTPException
from threading import Lock
from time import monotonic
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


QUEUE_NAMES = tuple(f'coldsafe.{role}' for role in (
    'gateway', 'writer', 'inference', 'delivery', 'commands', 'generation',
    'training', 'observability', 'model-activation', 'dlq',
))
MAX_RESPONSE_BYTES = 262_144


class MessagingUnavailable(Exception):
    pass


@dataclass(frozen=True)
class QueueMetrics:
    name: str
    messages: int
    messages_ready: int
    messages_unacknowledged: int
    consumers: int
    publish_rate: float | None
    deliver_rate: float | None


@dataclass(frozen=True)
class MessagingSummary:
    sampled_at: datetime
    queues: tuple[QueueMetrics, ...]


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Basic credentials must never follow a redirect to another destination.
        return None


def _count(row: dict, field: str) -> int:
    value = row.get(field)
    if type(value) is not int or value < 0:
        raise ValueError('Invalid queue count')
    return value


def _rate(stats: dict, field: str) -> float | None:
    details = stats.get(field)
    if details is None:
        return None
    if not isinstance(details, dict):
        raise ValueError('Invalid queue statistics')
    value = details.get('rate')
    if value is None:
        return None
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError('Invalid queue rate')
    return float(value)


def _metrics(payload: object) -> tuple[QueueMetrics, ...]:
    if not isinstance(payload, list):
        raise ValueError('Invalid queue response')
    queues = {}
    for row in payload:
        if not isinstance(row, dict):
            raise ValueError('Invalid queue response')
        name = row.get('name')
        if name not in QUEUE_NAMES:
            continue
        if row.get('vhost') != 'coldsafe' or name in queues:
            raise ValueError('Invalid queue scope')
        stats = row.get('message_stats')
        if stats is None:
            stats = {}
        if not isinstance(stats, dict):
            raise ValueError('Invalid queue statistics')
        queues[name] = QueueMetrics(
            name=name, messages=_count(row, 'messages'),
            messages_ready=_count(row, 'messages_ready'),
            messages_unacknowledged=_count(row, 'messages_unacknowledged'),
            consumers=_count(row, 'consumers'),
            publish_rate=_rate(stats, 'publish_details'),
            deliver_rate=_rate(stats, 'deliver_get_details'),
        )
    if set(queues) != set(QUEUE_NAMES):
        raise ValueError('Required queue is missing')
    return tuple(queues[name] for name in QUEUE_NAMES)


class MessagingService:
    def __init__(self, host: str, port: int, password: str):
        if not re.fullmatch(r'(?:[A-Za-z0-9_.-]+|\[[0-9A-Fa-f:]+\])', host):
            raise ValueError('Invalid RabbitMQ management host')
        columns = 'name,vhost,messages,messages_ready,messages_unacknowledged,consumers,message_stats'
        self._url = f'http://{host}:{port}/api/queues/coldsafe?{urlencode({"columns": columns})}'
        self._authorization = 'Basic ' + base64.b64encode(
            f'coldsafe-monitor:{password}'.encode('utf-8'),
        ).decode('ascii')
        self._opener = build_opener(ProxyHandler({}), _NoRedirect())
        self._lock = Lock()
        self._cached: MessagingSummary | None = None
        self._cached_at = 0.0

    def summary(self) -> MessagingSummary:
        with self._lock:
            if self._cached is not None and monotonic() - self._cached_at < 5:
                return self._cached
            self._cached = None
            try:
                request = Request(self._url, headers={
                    'Authorization': self._authorization, 'Accept': 'application/json',
                })
                with self._opener.open(request, timeout=3) as response:
                    if response.status != 200:
                        raise ValueError('Unexpected management response')
                    raw = response.read(MAX_RESPONSE_BYTES + 1)
                if len(raw) > MAX_RESPONSE_BYTES:
                    raise ValueError('Management response too large')
                metrics = _metrics(json.loads(raw))
            except (OSError, HTTPException, ValueError, TypeError, OverflowError, RecursionError):
                raise MessagingUnavailable('Messaging metrics unavailable') from None
            self._cached = MessagingSummary(sampled_at=datetime.now(UTC), queues=metrics)
            self._cached_at = monotonic()
            return self._cached
