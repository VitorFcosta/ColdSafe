"""Gateway boundaries and crash-safe identity without network dependencies."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from unittest.mock import MagicMock, Mock
from uuid import uuid4

import pytest

from gateway.bridge import Bridge, PermanentError, PostgresScope, encode
from simulator.model import Simulator, utc
from simulator.runtime import MqttSimulator

ROOT = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 10, 14, 20, tzinfo=timezone.utc)


@pytest.fixture
def catalog():
    return json.loads((ROOT / 'simulator/catalog.example.json').read_text())


@pytest.fixture
def bridge(tmp_path, catalog):
    instance = Bridge(catalog, tmp_path / 'journal.sqlite3', Mock(return_value=True))
    yield instance
    instance.db.close()


def command(catalog, now=NOW, actuator='led'):
    identifier = str(uuid4())
    return {
        'schema_version': 3, 'event_id': str(uuid4()), 'type': 'command',
        'occurred_at': utc(now), 'received_at': utc(now),
        **{key: catalog[key] for key in ('device_id', 'device_record_id', 'environment_id')},
        'correlation_id': identifier,
        'data': {'command_id': identifier, 'actuator_id': catalog['actuators'][actuator],
                 'actuator': actuator, 'desired_state': True,
                 'source': 'manual' if actuator == 'led' else 'automatic',
                 'deadline_at': utc(now + timedelta(seconds=30))},
    }


def accept(bridge, event, **kwargs):
    suffix = 'telemetry' if event['type'] == 'telemetry' else 'acks'
    return bridge.accept_mqtt(f'coldsafe/v3/devices/sim-lab-01/{suffix}', encode(event),
                              retained=False, qos=1, now=NOW, **kwargs)


def test_telemetry_received_once_and_dedup_survives_restart(bridge, catalog):
    event = Simulator(catalog).sample(1, NOW)
    first = accept(bridge, event)
    assert first['received_at'] == utc(NOW)
    assert first['event_id'] == event['event_id']
    bridge.db.close()
    restarted = Bridge(catalog, bridge.path, Mock(return_value=True))
    try:
        assert accept(restarted, event) == first
        assert restarted.db.execute('select count(*) from ingress').fetchone()[0] == 1
    finally:
        restarted.db.close()


@pytest.mark.parametrize('mutation,code', [
    (lambda x: x.update(received_at=utc(NOW)), 'INVALID_BINDING'),
    (lambda x: x.update(correlation_id=str(uuid4())), 'IDENTITY_MISMATCH'),
    (lambda x: x.update(environment_id=str(uuid4())), 'UNAUTHORIZED_SCOPE'),
    (lambda x: x['data']['equipment'].update(equipment_id=str(uuid4())), 'IDENTITY_MISMATCH'),
    (lambda x: x['data']['measurements']['light'].update(sensor_id=str(uuid4())), 'IDENTITY_MISMATCH'),
    (lambda x: x['data']['actuators']['led'].update(actuator_id=str(uuid4())), 'IDENTITY_MISMATCH'),
    (lambda x: x['data'].update(labels={}), 'INVALID_SCHEMA'),
    (lambda x: x['data']['measurements']['light'].update(value=float('inf')), 'INVALID_SCHEMA'),
])
def test_invalid_telemetry_does_not_enter_bus(bridge, catalog, mutation, code):
    event = Simulator(catalog).sample(1, NOW)
    mutation(event)
    raw = json.dumps(event).encode()
    with pytest.raises(PermanentError, match=code):
        bridge.accept_mqtt('coldsafe/v3/devices/sim-lab-01/telemetry', raw,
                           retained=False, qos=1, now=NOW)


@pytest.mark.parametrize('raw', [b'not-json', b'[]', b'{"type":1,"type":2}', b'\xff', b'{"v":NaN}'])
def test_strict_parse(bridge, raw):
    with pytest.raises(PermanentError, match='INVALID_SCHEMA'):
        bridge.parse(raw)


def test_size_limit_before_decode(bridge):
    with pytest.raises(PermanentError, match='PAYLOAD_TOO_LARGE'):
        bridge.parse(b'\xff' * 8193)


@pytest.mark.parametrize('topic,retained,qos', [
    ('coldsafe/v2/devices/sim-lab-01/telemetry', False, 1),
    ('coldsafe/v3/devices/other/telemetry', False, 1),
    ('coldsafe/v3/devices/sim-lab-01/telemetry', True, 1),
    ('coldsafe/v3/devices/sim-lab-01/telemetry', False, 0),
])
def test_transport_binding(bridge, catalog, topic, retained, qos):
    with pytest.raises(PermanentError, match='INVALID_BINDING'):
        bridge.accept_mqtt(topic, encode(Simulator(catalog).sample(1, NOW)),
                           retained=retained, qos=qos, now=NOW)


def test_scope_revoked_or_unavailable_is_never_accepted(bridge, catalog):
    bridge.check_scope.return_value = False
    with pytest.raises(PermanentError, match='UNAUTHORIZED_SCOPE'):
        accept(bridge, Simulator(catalog).sample(1, NOW))
    bridge.check_scope.side_effect = ConnectionError('private connection information')
    with pytest.raises(ConnectionError):
        accept(bridge, Simulator(catalog).sample(1, NOW))
    assert bridge.db.execute('select count(*) from ingress').fetchone()[0] == 0


def test_reused_event_id_with_changed_body_is_rejected(bridge, catalog):
    event = Simulator(catalog).sample(1, NOW)
    accept(bridge, event)
    event['data']['equipment']['running'] = False
    with pytest.raises(PermanentError, match='IDENTITY_MISMATCH'):
        accept(bridge, event)


def test_command_and_correlated_ack(bridge, catalog):
    event = command(catalog)
    assert bridge.accept_command(f"v3.command.{catalog['device_record_id']}", encode(event), now=NOW) == event
    simulator = MqttSimulator(Simulator(catalog), host='localhost', port=1883, password='private')
    ack = simulator.apply_command(simulator.command_topic, encode(event), retained=False, qos=1, now=NOW)
    assert accept(bridge, ack)['correlation_id'] == event['data']['command_id']
    ack['data']['actuator_id'] = str(uuid4())
    with pytest.raises(PermanentError, match='IDENTITY_MISMATCH'):
        accept(bridge, ack)


def test_unsolicited_ack_rejected(bridge, catalog):
    event = command(catalog)
    simulator = MqttSimulator(Simulator(catalog), host='localhost', port=1883, password='private')
    ack = simulator.command_ack(event, NOW)
    with pytest.raises(PermanentError, match='IDENTITY_MISMATCH'):
        accept(bridge, ack)


@pytest.mark.parametrize('mutation,code', [
    (lambda x: x['data'].update(source='automatic'), 'INVALID_SCHEMA'),
    (lambda x: x['data'].update(actuator_id=str(uuid4())), 'IDENTITY_MISMATCH'),
    (lambda x: x.update(correlation_id=str(uuid4())), 'IDENTITY_MISMATCH'),
    (lambda x: x['data'].update(deadline_at=utc(NOW + timedelta(seconds=31))), 'INVALID_BINDING'),
    (lambda x: x.update(received_at=utc(NOW - timedelta(seconds=1))), 'INVALID_BINDING'),
])
def test_invalid_command(bridge, catalog, mutation, code):
    event = command(catalog)
    mutation(event)
    with pytest.raises(PermanentError, match=code):
        bridge.accept_command(f"v3.command.{catalog['device_record_id']}", encode(event), now=NOW)


def test_wrong_route_and_expired_command(bridge, catalog):
    event = command(catalog)
    with pytest.raises(PermanentError, match='INVALID_BINDING'):
        bridge.accept_command('v3.command.other', encode(event), now=NOW)
    with pytest.raises(PermanentError, match='INVALID_BINDING'):
        bridge.accept_command(f"v3.command.{catalog['device_record_id']}", encode(event), now=NOW + timedelta(seconds=31))


def test_command_duplicate_and_conflicts(bridge, catalog):
    event = command(catalog)
    route = f"v3.command.{catalog['device_record_id']}"
    assert bridge.accept_command(route, encode(event), now=NOW) == event
    assert bridge.accept_command(route, encode(event), now=NOW) == event
    conflict = deepcopy(event)
    conflict['data']['desired_state'] = False
    with pytest.raises(PermanentError, match='IDENTITY_MISMATCH'):
        bridge.accept_command(route, encode(conflict), now=NOW)
    conflict = deepcopy(event)
    conflict['data']['command_id'] = conflict['correlation_id'] = str(uuid4())
    with pytest.raises(PermanentError, match='IDENTITY_MISMATCH'):
        bridge.accept_command(route, encode(conflict), now=NOW)


def test_event_identity_cannot_be_reused_between_transports(bridge, catalog):
    event = Simulator(catalog).sample(1, NOW)
    accept(bridge, event)
    requested = command(catalog)
    requested['event_id'] = event['event_id']
    with pytest.raises(PermanentError, match='IDENTITY_MISMATCH'):
        bridge.accept_command(f"v3.command.{catalog['device_record_id']}", encode(requested), now=NOW)
    requested['event_id'] = str(uuid4())
    bridge.accept_command(f"v3.command.{catalog['device_record_id']}", encode(requested), now=NOW)
    event['event_id'] = event['correlation_id'] = requested['event_id']
    with pytest.raises(PermanentError, match='IDENTITY_MISMATCH'):
        accept(bridge, event)


def test_expired_duplicate_is_acked_only_if_already_delivered(bridge, catalog):
    requested = command(catalog)
    route = f"v3.command.{catalog['device_record_id']}"
    bridge.accept_command(route, encode(requested), now=NOW)
    with pytest.raises(PermanentError, match='INVALID_BINDING'):
        bridge.accept_command(route, encode(requested), now=NOW + timedelta(seconds=31))
    bridge.db.execute('update commands set sent=1')
    bridge.db.commit()
    assert bridge.accept_command(route, encode(requested), now=NOW + timedelta(seconds=31)) == requested


def test_failed_publish_keeps_outbox_and_success_marks_it(bridge, catalog):
    accept(bridge, Simulator(catalog).sample(1, NOW))
    publisher = Mock(side_effect=ConnectionError())
    with pytest.raises(ConnectionError):
        bridge.flush(publisher)
    assert bridge.db.execute('select sent from ingress').fetchone()[0] == 0
    publisher.side_effect = None
    bridge.flush(publisher)
    bridge.flush(publisher)
    assert publisher.call_count == 2
    assert bridge.db.execute('select sent from ingress').fetchone()[0] == 1


def test_original_error_preserved_but_event_sanitized(bridge):
    raw = b'{"secret":"private-value",broken}'
    bridge.record_error('mqtt', 'private-route', raw, 'INVALID_SCHEMA', now=NOW)
    row = bridge.db.execute('select body,event from errors').fetchone()
    assert row[0] == raw
    assert b'private-value' not in row[1] and b'private-route' not in row[1]
    event = json.loads(row[1])
    assert event['device_id'] is None and event['data']['source_event_id'] is None
    assert event['data']['code'] == 'INVALID_SCHEMA'
    publisher = Mock()
    bridge.flush(publisher)
    assert publisher.call_count == 1


def test_postgres_scope_uses_bound_identifiers(catalog):
    connect = MagicMock()
    connect.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = (1,)
    scope = PostgresScope({'host': 'db'}, str(uuid4()), connect=connect)
    assert scope(catalog)
    query, params = connect.return_value.__enter__.return_value.execute.call_args.args
    assert '%s' in query and catalog['device_id'] not in query
    assert params == (catalog['device_record_id'], catalog['device_id'], catalog['environment_id'], scope.owner)


def test_compose_gateway_is_optional_private_and_separated():
    import yaml
    compose = yaml.safe_load((ROOT / 'compose.yaml').read_text())
    service = compose['services']['gateway']
    assert service['profiles'] == ['aiot']
    assert service['read_only'] and service['user'] == '65532:65532'
    assert 'ports' not in service and service['cap_drop'] == ['ALL']
    assert 'gateway-state:/state' in service['volumes']
    assert 'GATEWAY_OWNER_USER_ID' in service['environment']
    assert 'MQTT_GATEWAY_PASSWORD' in service['environment']
    assert 'RABBITMQ_GATEWAY_PASSWORD' in service['environment']
    assert 'RABBITMQ_GATEWAY_PASSWORD' not in compose['services']['backend']['environment']
