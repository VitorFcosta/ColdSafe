from datetime import UTC, datetime, timedelta
from dataclasses import replace
from threading import Thread
from time import monotonic, sleep
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend.app.api.app import create_app
from backend.app.api.auth import AuthService
from backend.app.api.catalog import CatalogService
from backend.app.api.events import EventHub
from backend.app.config.settings import RuntimeSettings
from backend.app.security.tokens import SessionPrincipal


def settings() -> RuntimeSettings:
    return RuntimeSettings(
        mqtt_host="unused", mqtt_port=1883, mqtt_topic="unused", mqtt_qos=1,
        mqtt_client_id="unused", mqtt_backend_username="unused", mqtt_backend_password="unused",
        influxdb_url="http://localhost:8086", influxdb_org="unused", influxdb_bucket="unused",
        influxdb_token="unused", postgres_host="localhost", postgres_port=5432,
        postgres_db="unused", postgres_user="unused", postgres_password="unused", _env_file=None,
    )


def make_client():
    owner, stranger, session_id, device_id = uuid4(), uuid4(), uuid4(), uuid4()
    auth, catalog = AuthService(settings()), CatalogService(settings())
    state = {
        "owner": owner, "active": True, "principal": SessionPrincipal(
            session_id=session_id, user_id=owner, role="viewer",
            email="owner@example.com", expires_at=datetime.now(UTC) + timedelta(hours=1),
        ),
    }
    auth.session_for_token = lambda token: (
        state["principal"] if token == "owner" else
        replace(state["principal"], user_id=stranger) if token == "stranger" else None
    )
    auth.session_for_id = lambda _session: state["principal"]
    auth.create_ws_ticket = Mock(return_value=("one-use-ticket", datetime.now(UTC) + timedelta(seconds=30)))
    tickets = {"one-use-ticket": state["principal"]}
    auth.consume_ws_ticket = Mock(side_effect=lambda ticket, _device: tickets.pop(ticket, None))
    catalog.device_for_user = lambda user, device: (
        {"id": str(device_id), "is_active": state["active"], "environment_id": str(uuid4()), "environment_name": "Lab"}
        if user == state["owner"] and device == "owned" else None
    )
    hub = EventHub()
    app = create_app(repository=Mock(), readiness_check=lambda: True,
                     auth=auth, catalog=catalog, events=hub)
    return TestClient(app), hub, auth, state


def wait_subscribed(hub):
    deadline = monotonic() + 2
    while "owned" not in hub._subscribers and monotonic() < deadline:
        sleep(0.01)
    assert "owned" in hub._subscribers


def test_ticket_issuance_requires_owner_and_valid_payload() -> None:
    client, _hub, auth, state = make_client()
    endpoint = "/api/v1/auth/ws-ticket"
    authorized = client.post(endpoint, json={"device_id": "owned"}, headers={"Authorization": "Bearer owner"})
    assert authorized.status_code == 200
    assert authorized.json()["data"]["ticket"] == "one-use-ticket"
    assert authorized.json()["data"]["expires_at"]
    assert authorized.json()["meta"] == {"schema_version": 1}
    auth.create_ws_ticket.assert_called_once()
    assert auth.create_ws_ticket.call_args.args[0] == "owner"
    auth.create_ws_ticket.reset_mock()
    for headers, payload, expected in [
        ({}, {"device_id": "owned"}, 401),
        ({"Authorization": "Bearer stranger"}, {"device_id": "owned"}, 404),
        ({"Authorization": "Bearer owner"}, {"device_id": "bad/device"}, 422),
        ({"Authorization": "Bearer owner"}, {"device_id": "owned", "token": "owner"}, 422),
        ({"Authorization": "Bearer owner"}, {"device_id": 123}, 422),
    ]:
        response = client.post(endpoint, json=payload, headers=headers)
        assert response.status_code == expected
        assert response.json()["success"] is False
    state["active"] = False
    response = client.post(endpoint, json={"device_id": "owned"}, headers={"Authorization": "Bearer owner"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    auth.create_ws_ticket.assert_not_called()
    contract = client.get("/openapi.json").json()
    documented = contract["paths"][endpoint]["post"]["responses"]
    assert {"200", "401", "403", "404", "422"} <= set(documented)


@pytest.mark.parametrize("frame", [
    '{"token":"owner"}', '{"ticket":"one-use-ticket","extra":true}',
    '{"ticket":42}', '{"ticket":""}', '[]', '{', '{"ticket":"' + 'x' * 2048 + '"}',
    '[' * 1000 + ']' * 1000,
])
def test_invalid_credentials_frames_are_rejected(frame) -> None:
    client, hub, auth, _state = make_client()
    with client.websocket_connect("/api/v1/events?device_id=owned") as ws:
        ws.send_text(frame)
        with pytest.raises(WebSocketDisconnect) as error:
            ws.receive_json()
        assert error.value.code == 4401
    auth.consume_ws_ticket.assert_not_called()
    assert not hub._subscribers


@pytest.mark.parametrize("query", ["device_id=bad/device", "device_id=owned&token=owner", "device_id=owned&device_id=owned", ""])
def test_invalid_websocket_urls_are_rejected(query) -> None:
    client, hub, auth, _state = make_client()
    with client.websocket_connect("/api/v1/events?" + query) as ws:
        with pytest.raises(WebSocketDisconnect) as error:
            ws.receive_json()
        assert error.value.code == 1008
    auth.consume_ws_ticket.assert_not_called()
    assert not hub._subscribers


def test_binary_credentials_and_unknown_ticket_are_rejected() -> None:
    client, hub, _auth, _state = make_client()
    for binary in (True, False):
        with client.websocket_connect("/api/v1/events?device_id=owned") as ws:
            if binary:
                ws.send_bytes(b'{"ticket":"one-use-ticket"}')
            else:
                ws.send_json({"ticket": "unknown"})
            with pytest.raises(WebSocketDisconnect) as error:
                ws.receive_json()
            assert error.value.code == 4401
    assert not hub._subscribers


@pytest.mark.parametrize("revoked,expected", [("session", 4401), ("owner", 4403), ("active", 4403), ("role", 4403)])
def test_stream_revalidates_session_owner_device_and_role(revoked, expected) -> None:
    client, hub, _auth, state = make_client()
    with client.websocket_connect("/api/v1/events?device_id=owned") as ws:
        ws.send_json({"ticket": "one-use-ticket"})
        wait_subscribed(hub)
        event = {"schema_version": 2, "type": "alert", "device_id": "owned", "data": {"status": "opened"}}
        worker = Thread(target=hub.publish, args=("owned", event))
        worker.start()
        worker.join()
        assert ws.receive_json() == event
        if revoked == "session":
            state["principal"] = None
        elif revoked == "owner":
            state["owner"] = uuid4()
        elif revoked == "active":
            state["active"] = False
        else:
            state["principal"] = replace(state["principal"], role="unknown")
        with pytest.raises(WebSocketDisconnect) as error:
            ws.receive_json()
        assert error.value.code == expected
    assert not hub._subscribers


def test_disconnect_and_replay_clean_up_subscriptions() -> None:
    client, hub, _auth, _state = make_client()
    with client.websocket_connect("/api/v1/events?device_id=owned") as ws:
        ws.send_json({"ticket": "one-use-ticket"})
        wait_subscribed(hub)
    assert not hub._subscribers
    with client.websocket_connect("/api/v1/events?device_id=owned") as ws:
        ws.send_json({"ticket": "one-use-ticket"})
        with pytest.raises(WebSocketDisconnect) as error:
            ws.receive_json()
        assert error.value.code == 4401
    assert not hub._subscribers


def test_credentials_timeout_and_extra_authenticated_frame_close_cleanly() -> None:
    client, hub, _auth, _state = make_client()
    with client.websocket_connect("/api/v1/events?device_id=owned") as ws:
        with pytest.raises(WebSocketDisconnect) as error:
            ws.receive_json()
        assert error.value.code == 4401
    with client.websocket_connect("/api/v1/events?device_id=owned") as ws:
        ws.send_json({"ticket": "one-use-ticket"})
        wait_subscribed(hub)
        ws.send_json({"ticket": "one-use-ticket"})
        with pytest.raises(WebSocketDisconnect) as error:
            ws.receive_json()
        assert error.value.code == 1008
    assert not hub._subscribers
