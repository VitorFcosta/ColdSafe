from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from time import monotonic, sleep
from unittest.mock import Mock
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend.app.api.app import create_app
from backend.app.api.auth import AuthError, AuthService
from backend.app.api.catalog import CatalogService
from backend.app.api.events import EventHub
from backend.app.repositories.postgres import connect, initialize_schema
from backend.tests.integration.test_aiot_migrations_integration import database


pytestmark = pytest.mark.integration


@pytest.fixture
def accounts(database):
    initialize_schema(database)
    clock = [datetime.now(UTC).replace(microsecond=0)]
    auth = AuthService(database, clock=lambda: clock[0])
    owner = auth.register("ws-owner@example.invalid", "correct-horse")
    stranger = auth.register("ws-stranger@example.invalid", "correct-horse")
    token, _ = auth.login("ws-owner@example.invalid", "correct-horse")
    catalog = CatalogService(database)
    environment = catalog.create_environment(owner, "Lab")
    device = catalog.create_device(owner, UUID(environment["id"]), "ESP32", "owned-device")
    return database, auth, catalog, clock, owner, stranger, token, device


def test_ticket_is_device_bound_single_use_and_audited_without_credentials(accounts):
    config, auth, _catalog, clock, owner, _stranger, token, device = accounts
    ticket, expires_at = auth.create_ws_ticket(token, UUID(device["id"]))
    assert expires_at == clock[0] + timedelta(seconds=60)
    assert auth.consume_ws_ticket(ticket, "foreign-device") is None
    principal = auth.consume_ws_ticket(ticket, "owned-device")
    assert principal.user_id == owner
    assert principal.session_id == auth.session_for_token(token).session_id
    assert auth.consume_ws_ticket(ticket, "owned-device") is None
    with connect(config) as connection:
        row = connection.execute("SELECT token_hash, consumed_at FROM websocket_tickets").fetchone()
        assert row[0] == auth._token_hash(ticket)
        assert row[1] == clock[0]
        records = connection.execute(
            "SELECT event_type, details FROM audit_events WHERE actor_user_id=%s", (owner,),
        ).fetchall()
    assert {"auth.ws_ticket_issued", "auth.ws_ticket_consumed"} <= {row[0] for row in records}
    assert ticket not in repr(records)
    assert token not in repr(records)
    assert "correct-horse" not in repr(records)


def test_concurrent_consumers_get_exactly_one_ticket(accounts):
    _config, auth, _catalog, _clock, owner, _stranger, token, device = accounts
    ticket, _ = auth.create_ws_ticket(token, UUID(device["id"]))
    barrier = Barrier(8)

    def consume(_index):
        barrier.wait(timeout=10)
        return auth.consume_ws_ticket(ticket, "owned-device")

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(consume, range(8)))
    winners = [principal for principal in results if principal is not None]
    assert len(winners) == 1
    assert winners[0].user_id == owner


@pytest.mark.parametrize("change", ["expired_ticket", "expired_session", "revoked", "inactive", "owner"])
def test_ticket_rejects_current_invalid_state(accounts, change):
    config, auth, _catalog, clock, _owner, stranger, token, device = accounts
    ticket, expires_at = auth.create_ws_ticket(token, UUID(device["id"]))
    if change == "expired_ticket":
        clock[0] = expires_at
    elif change == "expired_session":
        clock[0] += timedelta(hours=24)
    elif change == "revoked":
        assert auth.logout(token)
    else:
        with connect(config) as connection:
            if change == "inactive":
                connection.execute("UPDATE devices SET is_active=false WHERE id=%s", (device["id"],))
            else:
                connection.execute("UPDATE environments SET owner_user_id=%s WHERE id=%s",
                                   (stranger, device["environment_id"]))
    assert auth.consume_ws_ticket(ticket, "owned-device") is None
    with connect(config) as connection:
        assert connection.execute("SELECT consumed_at FROM websocket_tickets").fetchone() == (None,)


def test_ticket_cannot_be_issued_for_foreign_or_inactive_device(accounts):
    config, auth, _catalog, _clock, _owner, _stranger, token, device = accounts
    stranger_token, _ = auth.login("ws-stranger@example.invalid", "correct-horse")
    with pytest.raises(AuthError) as error:
        auth.create_ws_ticket(stranger_token, UUID(device["id"]))
    assert error.value.status_code == 403
    with connect(config) as connection:
        connection.execute("UPDATE devices SET is_active=false WHERE id=%s", (device["id"],))
    with pytest.raises(AuthError) as error:
        auth.create_ws_ticket(token, UUID(device["id"]))
    assert error.value.status_code == 403
    with connect(config) as connection:
        assert connection.execute("SELECT count(*) FROM websocket_tickets").fetchone() == (0,)


def test_real_websocket_ticket_stream_closes_after_logout(accounts):
    _config, auth, catalog, _clock, _owner, _stranger, token, _device = accounts
    hub = EventHub()
    client = TestClient(create_app(repository=Mock(), readiness_check=lambda: True,
                                   auth=auth, catalog=catalog, events=hub))
    issued = client.post("/api/v1/auth/ws-ticket", json={"device_id": "owned-device"},
                         headers={"Authorization": f"Bearer {token}"})
    assert issued.status_code == 200
    ticket = issued.json()["data"]["ticket"]
    with client.websocket_connect("/api/v1/events?device_id=owned-device") as ws:
        ws.send_json({"ticket": ticket})
        deadline = monotonic() + 3
        while "owned-device" not in hub._subscribers and monotonic() < deadline:
            sleep(0.01)
        assert "owned-device" in hub._subscribers
        event = {"schema_version": 2, "type": "alert", "device_id": "owned-device", "data": {}}
        hub.publish("owned-device", event)
        assert ws.receive_json() == event
        assert client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"}).status_code == 200
        with pytest.raises(WebSocketDisconnect) as error:
            ws.receive_json()
        assert error.value.code == 4401
    assert not hub._subscribers
