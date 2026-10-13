from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
from uuid import uuid4

from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.app.api.app import create_app
from backend.app.api.auth import AuthService
from backend.app.api.catalog import CatalogService
from backend.app.security.tokens import SessionPrincipal
from backend.tests.api.test_events_api import settings


def make_client():
    owner, stranger, device_id = uuid4(), uuid4(), uuid4()
    auth, catalog = AuthService(settings()), CatalogService(settings())
    auth.current_user = lambda token: {"owner": owner, "stranger": stranger}.get(token)
    auth.session_for_token = lambda token: (
        SessionPrincipal(uuid4(), {"owner": owner, "stranger": stranger}[token],
                         "unit@example.invalid", "operator", datetime.now(UTC) + timedelta(hours=1))
        if token in {"owner", "stranger"} else None
    )
    catalog.device_for_user = lambda user, mqtt: (
        {"id": str(device_id), "environment_id": str(uuid4()),
         "environment_name": "Lab", "is_active": True}
        if user == owner and mqtt == "owned" else None
    )

    def get_device(user, requested):
        if user != owner or requested != device_id:
            raise HTTPException(status_code=404, detail="DEVICE_NOT_FOUND")
        return {"mqtt_device_id": "owned", "is_active": True}

    catalog.get_device = get_device
    catalog.thresholds_for_environment = lambda _environment: {
        "min_c": 2, "max_c": 8, "attention_margin_c": 0.5,
    }
    readings, alerts, commands = Mock(), Mock(), Mock()
    readings.list_history.return_value = ()
    alerts.list_for_device.return_value = []
    commands.latest_for_device.return_value = {"led": None, "buzzer": None}
    app = create_app(repository=readings, readiness_check=lambda: True,
                     auth=auth, catalog=catalog, alerts=alerts, commands=commands)
    return TestClient(app), readings, alerts, commands, device_id


def test_alert_periods_and_account_isolation() -> None:
    client, _readings, alerts, _commands, _device = make_client()
    start = datetime(2026, 9, 24, 12, tzinfo=UTC)
    end = start + timedelta(hours=1)
    params = {"device_id": "owned", "start": start.isoformat(), "end": end.isoformat()}
    assert client.get("/api/v1/alerts", params=params).status_code == 401
    assert client.get("/api/v1/alerts", params=params,
                      headers={"Authorization": "Bearer stranger"}).status_code == 404
    response = client.get("/api/v1/alerts", params=params,
                          headers={"Authorization": "Bearer owner"})
    assert response.status_code == 200
    assert response.json()["meta"]["count"] == 0
    assert alerts.list_for_device.call_args.args[0] == "owned"
    assert alerts.list_for_device.call_args.kwargs == {"start": start, "end": end, "limit": 300}
    assert client.get("/api/v1/alerts", params={"device_id": "owned", "start": start.isoformat()},
                      headers={"Authorization": "Bearer owner"}).status_code == 422


def test_actuator_snapshot_keeps_unconfirmed_state_null() -> None:
    client, _readings, _alerts, commands, device = make_client()
    commands.latest_for_device.return_value = {
        "led": {"schema_version": 2, "command_id": str(uuid4()), "device_id": "owned",
                "actuator": "led", "desired_state": True, "confirmed_state": None,
                "status": "unconfirmed"},
        "buzzer": None,
    }
    url = f"/api/v1/devices/{device}/actuators"
    assert client.get(url, headers={"Authorization": "Bearer stranger"}).status_code == 404
    response = client.get(url, headers={"Authorization": "Bearer owner"})
    assert response.status_code == 200
    assert response.json()["data"]["led"]["confirmed_state"] is None
    assert response.json()["data"]["buzzer"] is None
    assert response.json()["meta"] == {"schema_version": 2}
