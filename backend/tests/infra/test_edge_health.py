"""Heartbeat checks reflect progress in the application loop, including idle queues."""
from pathlib import Path
from threading import Event
from unittest.mock import MagicMock, Mock

import pika
import pytest
import yaml

from backend.app.errors import DependencyUnavailableError
from backend.tests.infra.test_gateway import catalog, bridge
from gateway.runtime import Gateway
from simulator.model import Simulator
from simulator.runtime import MqttSimulator
from writer.runtime import Writer


def test_disabled_heartbeat_does_not_touch_disk(monkeypatch, tmp_path):
    from simulator import health
    path = tmp_path / 'heartbeat'
    monkeypatch.setattr(health, 'HEARTBEAT', path)
    monkeypatch.delenv('COLDSAFE_HEALTHCHECK', raising=False)
    health.mark_healthy()
    assert not path.exists()


@pytest.mark.parametrize('stored,expected', [(None, 1), ('invalid', 1), ('nan', 1),
    ('inf', 1), ('101', 1), ('69', 1), ('70', 0), ('100', 0)])
def test_cli_rejects_missing_corrupt_future_and_stale(monkeypatch, tmp_path, stored, expected):
    from simulator import health
    path = tmp_path / 'heartbeat'
    monkeypatch.setattr(health, 'HEARTBEAT', path)
    monkeypatch.setattr(health.time, 'monotonic', lambda: 100)
    monkeypatch.setattr('sys.argv', ['health'])
    if stored is not None:
        path.write_text(stored)
    assert health.main() == expected


def test_enabled_heartbeat_and_custom_threshold(monkeypatch, tmp_path):
    from simulator import health
    path = tmp_path / 'heartbeat'
    monkeypatch.setattr(health, 'HEARTBEAT', path)
    monkeypatch.setenv('COLDSAFE_HEALTHCHECK', '1')
    monkeypatch.setattr(health.time, 'monotonic', lambda: 100)
    health.mark_healthy()
    assert float(path.read_text()) == 100
    monkeypatch.setattr(health.time, 'monotonic', lambda: 160)
    monkeypatch.setattr('sys.argv', ['health', '90'])
    assert health.main() == 0


@pytest.mark.parametrize('threshold', ['0', '-1', 'nan', 'inf'])
def test_cli_rejects_invalid_threshold(monkeypatch, threshold):
    from simulator import health
    monkeypatch.setattr('sys.argv', ['health', threshold])
    with pytest.raises(SystemExit, match='2'):
        health.main()


@pytest.mark.parametrize('connected,active,delivered', [(False, True, False), (True, False, False),
                                                       (True, True, False), (True, True, True)])
def test_simulator_updates_only_connected_idle_or_confirmed_publish(catalog, monkeypatch, connected, active, delivered):
    service = MqttSimulator(Simulator(catalog), host='mqtt', port=1883, password='unit')
    service.simulator.active = active
    service.client = MagicMock()
    service.client.publish.return_value.rc = 0
    service.client.publish.return_value.is_published.return_value = delivered
    if connected:
        service.connected.set()
    heartbeat = Mock()
    monkeypatch.setattr('simulator.runtime.mark_healthy', heartbeat)
    shutdown = Event()
    monkeypatch.setattr(shutdown, 'wait', lambda *_: shutdown.set())
    service.run(shutdown)
    assert heartbeat.call_count == int(connected and (not active or delivered))


@pytest.mark.parametrize('connected,amqp_ok', [(False, True), (True, False), (True, True)])
def test_gateway_requires_both_transport_connections(bridge, monkeypatch, connected, amqp_ok):
    service = Gateway(bridge, mqtt_host='mqtt', mqtt_port=1883, mqtt_password='unit',
                      amqp_host='amqp', amqp_port=5672, amqp_password='unit')
    service.client, service.connection, service.channel = MagicMock(), MagicMock(), MagicMock()
    service.channel.basic_get.return_value = None, None, None
    if connected:
        service.ready.set()
    if not amqp_ok:
        service.connection.process_data_events.side_effect = pika.exceptions.AMQPConnectionError()
    heartbeat = Mock()
    monkeypatch.setattr('gateway.runtime.mark_healthy', heartbeat)
    shutdown = Event()
    monkeypatch.setattr(shutdown, 'wait', lambda *_: shutdown.set())
    service.run(shutdown)
    assert heartbeat.call_count == int(connected and amqp_ok)


@pytest.mark.parametrize('consumed,amqp_ok', [(False, True), (True, False), (True, True)])
def test_writer_updates_only_after_successful_loop(catalog, monkeypatch, consumed, amqp_ok):
    service = Writer(catalog, Mock(), Mock(), amqp_host='amqp', amqp_port=5672, amqp_password='unit')
    service.connection, service.channel = MagicMock(), MagicMock()
    monkeypatch.setattr(service, 'consume', lambda: consumed)
    if not amqp_ok:
        service.connection.process_data_events.side_effect = pika.exceptions.AMQPConnectionError()
    heartbeat = Mock()
    monkeypatch.setattr('writer.runtime.mark_healthy', heartbeat)
    shutdown = Event()
    monkeypatch.setattr(shutdown, 'wait', lambda *_: shutdown.set())
    service.run(shutdown)
    assert heartbeat.call_count == int(consumed and amqp_ok)


def test_writer_dependency_failure_does_not_report_progress(catalog, monkeypatch):
    from backend.tests.infra.test_writer_runtime import delivery
    service = Writer(catalog, Mock(), Mock(return_value=True), amqp_host='amqp',
                     amqp_port=5672, amqp_password='unit')
    service.channel = MagicMock()
    delivery(service, catalog)
    service.repository.save_event.side_effect = DependencyUnavailableError()
    assert service.consume() is False
    service.channel.basic_ack.assert_not_called()
    service.channel.basic_reject.assert_called_once_with(123, requeue=True)


def test_edge_compose_healthchecks_can_write_as_container_user():
    root = Path(__file__).resolve().parents[3]
    services = yaml.safe_load((root / 'compose.yaml').read_text())['services']
    for name in ('simulator', 'gateway', 'writer'):
        service = services[name]
        assert service['environment']['COLDSAFE_HEALTHCHECK'] == '1'
        assert service['healthcheck']['test'][:4] == ['CMD', 'python', '-m', 'simulator.health']
        assert service['read_only'] and service['user'] == '65532:65532'
        assert service['tmpfs'] == ['/tmp:rw,noexec,nosuid,size=1m,uid=65532,gid=65532']
        assert 'simulator/health.py' in (root / name / 'Dockerfile').read_text()
