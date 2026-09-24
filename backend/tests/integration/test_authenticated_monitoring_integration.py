import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.api.app import create_app
from backend.app.api.auth import AuthService
from backend.app.api.catalog import CatalogService
from backend.app.config.settings import RuntimeSettings
from backend.app.domain.reading_classification import ReadingStatus
from backend.app.repositories.influxdb import StoredReading
from backend.app.repositories.postgres import connect, initialize_schema


class Readings:
    def __init__(self, readings: dict[str, StoredReading]) -> None:
        self.readings = readings

    def get_latest(self, device_id: str) -> StoredReading | None:
        return self.readings.get(device_id)

    def list_history(self, *, device_id: str, **_kwargs) -> tuple[StoredReading, ...]:
        reading = self.readings.get(device_id)
        return (reading,) if reading else ()


def postgres_settings() -> RuntimeSettings:
    password = os.getenv("POSTGRES_TEST_PASSWORD")
    if not password:
        pytest.skip("POSTGRES_TEST_PASSWORD is required for PostgreSQL integration")
    return RuntimeSettings(
        mqtt_host="unused", mqtt_port=1883, mqtt_topic="unused", mqtt_qos=1,
        mqtt_client_id="unused", mqtt_backend_username="unused", mqtt_backend_password="unused",
        influxdb_url="http://localhost:8086", influxdb_org="unused", influxdb_bucket="unused",
        influxdb_token="unused", postgres_host="127.0.0.1", postgres_port=15432,
        postgres_db=os.getenv("POSTGRES_TEST_DB", "coldsafe"),
        postgres_user=os.getenv("POSTGRES_TEST_USER", "coldsafe"),
        postgres_password=password, _env_file=None,
    )


@pytest.mark.integration
def test_accounts_cannot_read_each_others_devices_and_rules_apply() -> None:
    settings = postgres_settings()
    initialize_schema(settings)
    unique = uuid4().hex
    emails = [f"block2-a-{unique}@example.invalid", f"block2-b-{unique}@example.invalid"]
    mqtt_ids = [f"block2-a-{unique}", f"block2-b-{unique}"]
    now = datetime.now(UTC)
    repository = Readings({
        mqtt_ids[0]: StoredReading(1, mqtt_ids[0], 7, 60, ReadingStatus.NORMAL, now),
        mqtt_ids[1]: StoredReading(1, mqtt_ids[1], 4, 61, ReadingStatus.NORMAL, now),
    })
    auth = AuthService(settings)
    catalog = CatalogService(settings)
    app = create_app(repository=repository, readiness_check=lambda: True,
                     clock=lambda: now, auth=auth, catalog=catalog)
    client = TestClient(app)

    try:
        headers = []
        environments = []
        devices = []
        for email, mqtt_id in zip(emails, mqtt_ids):
            credentials = {"email": email, "password": "correct-horse"}
            assert client.post("/api/v1/auth/register", json=credentials).status_code == 201
            token = client.post("/api/v1/auth/login", json=credentials).json()["data"]["token"]
            headers.append({"Authorization": f"Bearer {token}"})
            environment = client.post("/api/v1/environments", headers=headers[-1],
                                      json={"name": email}).json()["data"]["id"]
            environments.append(environment)
            device = client.post(f"/api/v1/environments/{environment}/devices",
                                 headers=headers[-1], json={"name": "ESP32", "mqtt_device_id": mqtt_id})
            assert device.status_code == 201
            devices.append(device.json()["data"]["id"])

        assert client.get(f"/api/v1/environments/{environments[1]}", headers=headers[0]).status_code == 404
        assert client.get(f"/api/v1/devices/{devices[1]}", headers=headers[0]).status_code == 404
        assert client.get("/api/v1/monitoring/summary", params={"device_id": mqtt_ids[0]}).status_code == 401
        assert client.get("/api/v1/monitoring/summary", params={"device_id": mqtt_ids[0]},
                          headers=headers[1]).status_code == 404
        assert client.get("/api/v1/readings", params={"device_id": mqtt_ids[0]},
                          headers=headers[1]).status_code == 404

        changed = client.put(f"/api/v1/environments/{environments[0]}/rules", headers=headers[0],
                             json={"min_c": 4, "max_c": 6, "attention_margin_c": 0.5})
        assert changed.status_code == 200
        first = client.get("/api/v1/monitoring/summary", params={"device_id": mqtt_ids[0]},
                           headers=headers[0]).json()["data"]
        second = client.get("/api/v1/monitoring/summary", params={"device_id": mqtt_ids[1]},
                            headers=headers[1]).json()["data"]
        assert (first["status"], first["reading"]["temperature_c"], first["thresholds"]["max_c"]) == ("critical", 7, 6)
        assert (second["status"], second["reading"]["temperature_c"]) == ("normal", 4)
        history = client.get("/api/v1/readings", params={"device_id": mqtt_ids[0]},
                             headers=headers[0]).json()["data"]["readings"]
        assert [reading["temperature_c"] for reading in history] == [7]

        assert client.delete(f"/api/v1/devices/{devices[0]}", headers=headers[0]).status_code == 200
        assert catalog.active_device(mqtt_ids[0]) is None
        assert client.get("/api/v1/readings", params={"device_id": mqtt_ids[0]},
                          headers=headers[0]).status_code == 200
        assert client.post("/api/v1/auth/logout", headers=headers[0]).status_code == 200
        assert client.get("/api/v1/readings", params={"device_id": mqtt_ids[0]},
                          headers=headers[0]).status_code == 401
    finally:
        with connect(settings) as connection:
            connection.execute("DELETE FROM sessions WHERE user_id IN "
                               "(SELECT id FROM users WHERE email = ANY(%s))", (emails,))
            connection.execute("DELETE FROM audit_events WHERE actor_user_id IN "
                               "(SELECT id FROM users WHERE email = ANY(%s))", (emails,))
            connection.execute("DELETE FROM devices WHERE environment_id IN "
                               "(SELECT id FROM environments WHERE owner_user_id IN "
                               "(SELECT id FROM users WHERE email = ANY(%s)))", (emails,))
            connection.execute("DELETE FROM environment_rules WHERE environment_id IN "
                               "(SELECT id FROM environments WHERE owner_user_id IN "
                               "(SELECT id FROM users WHERE email = ANY(%s)))", (emails,))
            connection.execute("DELETE FROM environments WHERE owner_user_id IN "
                               "(SELECT id FROM users WHERE email = ANY(%s))", (emails,))
            connection.execute("DELETE FROM users WHERE email = ANY(%s)", (emails,))
