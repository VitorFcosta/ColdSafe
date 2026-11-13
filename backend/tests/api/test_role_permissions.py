from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.app.api.catalog import create_catalog_router
from backend.app.api.commands import create_command_router


@pytest.mark.parametrize("method,path,body", [
    ("post", "/api/v1/environments", {"name": "Private"}),
    ("patch", "/api/v1/environments/{id}", {"name": "Private"}),
    ("post", "/api/v1/environments/{id}/devices", {"name": "Device", "mqtt_device_id": "owned"}),
    ("patch", "/api/v1/devices/{id}", {"name": "Device"}),
    ("delete", "/api/v1/devices/{id}", None),
    ("put", "/api/v1/environments/{id}/rules", {"min_c": 2, "max_c": 8, "attention_margin_c": .5}),
    ("post", "/api/v1/devices/{id}/led/commands", {"desired_state": True}),
])
def test_every_write_route_requires_operator_before_touching_data(method, path, body):
    def read_user():
        return uuid4()

    def deny_write():
        raise HTTPException(status_code=403, detail="FORBIDDEN")

    catalog, commands = Mock(), Mock()
    app = FastAPI()
    app.include_router(create_catalog_router(catalog, read_user, require_operator=deny_write))
    app.include_router(create_command_router(catalog, commands, read_user, require_operator=deny_write))
    client = TestClient(app)
    response = client.request(method, path.format(id=uuid4()), json=body)
    assert response.status_code == 403
    assert catalog.mock_calls == []
    assert commands.mock_calls == []
