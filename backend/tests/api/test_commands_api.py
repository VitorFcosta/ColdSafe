from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.app.api.commands import create_command_router


@pytest.mark.parametrize("desired_state", [True, False])
def test_led_command_checks_owner_and_returns_pending(desired_state: bool) -> None:
    owner, device_id, command_id = uuid4(), uuid4(), uuid4()
    catalog = Mock()
    catalog.get_device.return_value = {
        "mqtt_device_id": "esp32-lab-01", "is_active": True,
    }
    commands = Mock()
    commands.request.return_value = {
        "schema_version": 2, "command_id": str(command_id), "device_id": "esp32-lab-01",
        "actuator": "led", "desired_state": desired_state, "confirmed_state": None,
        "status": "pending",
    }
    app = FastAPI()
    app.include_router(create_command_router(catalog, commands, lambda: owner))

    response = TestClient(app).post(
        f"/api/v1/devices/{device_id}/led/commands", json={"desired_state": desired_state}
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "pending"
    catalog.get_device.assert_called_once_with(owner, device_id)
    commands.request.assert_called_once_with(
        device_id, "esp32-lab-01", "led", desired_state, "manual", owner,
    )


def test_foreign_device_cannot_issue_command() -> None:
    catalog, commands = Mock(), Mock()
    catalog.get_device.side_effect = HTTPException(404, "DEVICE_NOT_FOUND")
    app = FastAPI()
    app.include_router(create_command_router(catalog, commands, lambda: uuid4()))

    response = TestClient(app).post(
        f"/api/v1/devices/{uuid4()}/led/commands", json={"desired_state": False}
    )

    assert response.status_code == 404
    commands.request.assert_not_called()


def test_status_lookup_uses_owner_scoped_query() -> None:
    owner, command_id = uuid4(), uuid4()
    commands = Mock()
    commands.get_for_user.return_value = None
    app = FastAPI()
    app.include_router(create_command_router(Mock(), commands, lambda: owner))

    response = TestClient(app).get(f"/api/v1/commands/{command_id}")

    assert response.status_code == 404
    commands.get_for_user.assert_called_once_with(command_id, owner)
