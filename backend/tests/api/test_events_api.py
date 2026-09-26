from datetime import UTC, datetime
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


def settings() -> RuntimeSettings:
    return RuntimeSettings(
        mqtt_host="unused", mqtt_port=1883, mqtt_topic="unused", mqtt_qos=1,
        mqtt_client_id="unused", mqtt_backend_username="unused", mqtt_backend_password="unused",
        influxdb_url="http://localhost:8086", influxdb_org="unused", influxdb_bucket="unused",
        influxdb_token="unused", postgres_host="localhost", postgres_port=5432,
        postgres_db="unused", postgres_user="unused", postgres_password="unused", _env_file=None,
    )


def make_client():
    owner, stranger = uuid4(), uuid4()
    auth, catalog = AuthService(settings()), CatalogService(settings())
    sessions = {"owner": owner, "stranger": stranger}
    auth.current_user = lambda token: sessions.get(token)
    catalog.device_for_user = lambda user, device: (
        {"is_active": True, "environment_id": str(uuid4()), "environment_name": "Lab"}
        if user == owner and device == "owned" else None
    )
    hub = EventHub()
    app = create_app(repository=Mock(), readiness_check=lambda: True,
                     auth=auth, catalog=catalog, events=hub)
    return TestClient(app), hub, sessions


def test_foreign_and_revoked_sessions_cannot_stream_and_disconnect_cleans_up() -> None:
    client, hub, sessions = make_client()
    with client.websocket_connect("/api/v1/events?device_id=owned") as ws:
        ws.send_json({"token": "stranger"})
        with pytest.raises(WebSocketDisconnect) as error:
            ws.receive_json()
        assert error.value.code == 4403

    with client.websocket_connect("/api/v1/events?device_id=owned") as ws:
        ws.send_json({"token": "owner"})
        deadline = monotonic() + 2
        while "owned" not in hub._subscribers and monotonic() < deadline:
            sleep(0.01)
        assert "owned" in hub._subscribers
        event = {"schema_version": 2, "type": "alert", "environment_id": "lab",
                 "device_id": "owned", "occurred_at": datetime.now(UTC).isoformat(),
                 "data": {"alert_id": str(uuid4()), "status": "opened"}}
        worker = Thread(target=hub.publish, args=("owned", event))
        worker.start()
        worker.join()
        assert ws.receive_json() == event
        sessions.pop("owner")
        with pytest.raises(WebSocketDisconnect) as error:
            ws.receive_json()
        assert error.value.code == 4401
    assert not hub._subscribers


def test_invalid_token_and_device_are_closed() -> None:
    client, _hub, _sessions = make_client()
    with client.websocket_connect("/api/v1/events?device_id=owned") as ws:
        ws.send_json({"token": "bad"})
        with pytest.raises(WebSocketDisconnect) as error:
            ws.receive_json()
        assert error.value.code == 4401
    with client.websocket_connect("/api/v1/events?device_id=bad/device") as ws:
        with pytest.raises(WebSocketDisconnect) as error:
            ws.receive_json()
        assert error.value.code == 1008
