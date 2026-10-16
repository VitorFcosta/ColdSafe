import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import UTC
from http.client import BadStatusLine, IncompleteRead
from io import BytesIO
from unittest.mock import Mock
from urllib.error import HTTPError, URLError

import pytest

from backend.app.services.messaging import (
    MAX_RESPONSE_BYTES, QUEUE_NAMES, MessagingService, MessagingUnavailable,
)


def queues():
    return [{
        'name': name, 'vhost': 'coldsafe', 'messages': 4,
        'messages_ready': 3, 'messages_unacknowledged': 1, 'consumers': 2,
        'message_stats': {'publish_details': {'rate': 1.5}, 'deliver_get_details': {'rate': 2.5}},
        'arguments': {'secret': 'private'}, 'consumer_details': [{'connection_name': 'private'}],
    } for name in QUEUE_NAMES]


def service(payload=None, *, error=None):
    transport = Mock()
    if error:
        transport.open.side_effect = error
    else:
        response = BytesIO(json.dumps(payload if payload is not None else queues()).encode())
        response.status = 200
        transport.open.return_value = response
    monitor = MessagingService('rabbitmq', 15672, 'private-password')
    monitor._opener = transport
    return monitor, transport


def test_only_fixed_queue_metrics_leave_the_service():
    payload = queues() + [{'name': 'other-owner-queue', 'secret': 'private'}]
    monitor, transport = service(payload)
    result = monitor.summary()
    assert [queue.name for queue in result.queues] == list(QUEUE_NAMES)
    assert result.queues[0].publish_rate == 1.5
    assert result.queues[0].deliver_rate == 2.5
    assert result.sampled_at.tzinfo == UTC
    assert 'private' not in repr(result)
    request = transport.open.call_args.args[0]
    assert request.full_url.startswith('http://rabbitmq:15672/api/queues/coldsafe?')
    assert transport.open.call_args.kwargs['timeout'] == 3


@pytest.mark.parametrize('stats', [None, {}, {'publish_details': {}, 'deliver_get_details': None}])
def test_missing_statistics_are_unknown_not_zero(stats):
    payload = queues()
    for queue in payload:
        queue['message_stats'] = stats
    result = service(payload)[0].summary()
    assert result.queues[0].publish_rate is None
    assert result.queues[0].deliver_rate is None


@pytest.mark.parametrize('field,value', [
    ('messages', -1), ('messages_ready', True), ('consumers', 1.2),
    ('messages_unacknowledged', None), ('messages', '4'),
])
def test_invalid_counts_fail_closed(field, value):
    payload = queues()
    payload[0][field] = value
    with pytest.raises(MessagingUnavailable):
        service(payload)[0].summary()


@pytest.mark.parametrize('value', [-1, float('nan'), float('inf'), '1', True])
def test_invalid_rates_fail_closed(value):
    payload = queues()
    payload[0]['message_stats']['publish_details']['rate'] = value
    with pytest.raises(MessagingUnavailable):
        service(payload)[0].summary()


@pytest.mark.parametrize('mutate', [
    lambda rows: rows.pop(),
    lambda rows: rows.append(deepcopy(rows[0])),
    lambda rows: rows[0].update(vhost='another-owner'),
    lambda rows: rows[0].update(message_stats=[]),
    lambda rows: rows[0].update(message_stats={'publish_details': []}),
    lambda rows: rows.append(None),
])
def test_missing_duplicate_or_malformed_queues_are_unavailable(mutate):
    payload = queues()
    mutate(payload)
    with pytest.raises(MessagingUnavailable):
        service(payload)[0].summary()


@pytest.mark.parametrize('error', [TimeoutError('private'), URLError('private'),
    HTTPError('http://private', 403, 'private', {}, None)])
def test_transport_failures_are_sanitized(error):
    monitor, _ = service(error=error)
    with pytest.raises(MessagingUnavailable) as exc:
        monitor.summary()
    assert str(exc.value) == 'Messaging metrics unavailable'


@pytest.mark.parametrize('error', [IncompleteRead(b'private', 10), BadStatusLine('private')])
def test_broken_http_responses_are_sanitized(error):
    monitor, transport = service()
    transport.open.return_value.read = Mock(side_effect=error)
    with pytest.raises(MessagingUnavailable) as exc:
        monitor.summary()
    assert str(exc.value) == 'Messaging metrics unavailable'


@pytest.mark.parametrize('raw', [b'{', b'null', b'{}', b'\xff', b' ' * (MAX_RESPONSE_BYTES + 1)])
def test_invalid_json_and_oversized_responses_are_unavailable(raw):
    monitor, transport = service()
    response = BytesIO(raw)
    response.status = 200
    transport.open.return_value = response
    with pytest.raises(MessagingUnavailable):
        monitor.summary()


def test_unexpected_management_status_is_unavailable():
    monitor, transport = service()
    transport.open.return_value.status = 204
    with pytest.raises(MessagingUnavailable):
        monitor.summary()


def test_concurrent_polling_reuses_one_fresh_sample():
    monitor, transport = service()
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _: monitor.summary(), range(12)))
    assert all(result is results[0] for result in results)
    transport.open.assert_called_once()


def test_cache_expires_and_never_serves_old_success_after_failure(monkeypatch):
    now = [10.0]
    monkeypatch.setattr('backend.app.services.messaging.monotonic', lambda: now[0])
    monitor, transport = service()
    first = monitor.summary()
    now[0] = 14.9
    assert monitor.summary() is first
    transport.open.assert_called_once()
    now[0] = 15.0
    transport.open.side_effect = TimeoutError()
    with pytest.raises(MessagingUnavailable):
        monitor.summary()
    with pytest.raises(MessagingUnavailable):
        monitor.summary()
    assert transport.open.call_count == 3


def test_redirect_and_environment_proxy_are_disabled(monkeypatch):
    monkeypatch.setenv('http_proxy', 'http://credential-thief.invalid:8080')
    monitor = MessagingService('rabbitmq', 15672, 'private-password')
    handlers = monitor._opener.handlers
    assert not any(handler.__class__.__name__ == 'ProxyHandler' for handler in handlers)
    redirect = next(handler for handler in handlers if hasattr(handler, 'redirect_request'))
    assert redirect.redirect_request(None, None, 302, 'Found', {}, 'http://other') is None


@pytest.mark.parametrize('host', ['rabbitmq/secret', 'user@rabbitmq', 'rabbitmq?leak', 'rabbitmq#leak'])
def test_host_cannot_change_the_fixed_management_destination(host):
    with pytest.raises(ValueError):
        MessagingService(host, 15672, 'private-password')
