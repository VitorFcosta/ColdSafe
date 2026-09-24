import os
from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4

import pytest
import psycopg
from fastapi import FastAPI, HTTPException, Header
from fastapi.testclient import TestClient
from psycopg import sql

from backend.app.api.catalog import CatalogService, ThresholdInput, create_catalog_router
from backend.app.config.settings import RuntimeSettings
from backend.app.repositories.postgres import connect, initialize_schema


MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"


def settings() -> RuntimeSettings:
    password = os.getenv("POSTGRES_TEST_PASSWORD")
    if not password:
        pytest.skip("POSTGRES_TEST_PASSWORD is required for PostgreSQL integration")
    return RuntimeSettings(
        mqtt_host="unused", mqtt_port=1883, mqtt_topic="unused", mqtt_qos=1,
        mqtt_client_id="unused", mqtt_backend_username="unused", mqtt_backend_password="unused",
        influxdb_url="http://localhost:8086", influxdb_org="unused",
        influxdb_bucket="unused", influxdb_token="unused",
        postgres_host=os.getenv("POSTGRES_TEST_HOST", "127.0.0.1"),
        postgres_port=int(os.getenv("POSTGRES_TEST_PORT", "15432")),
        postgres_db=os.getenv("POSTGRES_TEST_DB", "coldsafe"),
        postgres_user=os.getenv("POSTGRES_TEST_USER", "coldsafe"),
        postgres_password=password, _env_file=None,
    )


@pytest.mark.integration
def test_owner_isolation_unique_devices_rules_and_soft_deactivation() -> None:
    config = settings()
    initialize_schema(config)
    catalog = CatalogService(config)
    token = uuid4().hex
    with connect(config) as connection:
        owner = connection.execute(
            "INSERT INTO users (email, password_hash) VALUES (%s, 'hash') RETURNING id",
            (f"catalog-owner-{token}@example.invalid",),
        ).fetchone()[0]
        stranger = connection.execute(
            "INSERT INTO users (email, password_hash) VALUES (%s, 'hash') RETURNING id",
            (f"catalog-stranger-{token}@example.invalid",),
        ).fetchone()[0]

    environment_id: UUID | None = None
    try:
        environment = catalog.create_environment(owner, "Câmara A")
        environment_id = UUID(environment["id"])
        assert [item["id"] for item in catalog.list_environments(owner)] == [environment["id"]]
        assert catalog.list_environments(stranger) == []

        def current_user(x_test_user: Annotated[UUID, Header()]) -> UUID:
            return x_test_user

        app = FastAPI()
        app.include_router(create_catalog_router(catalog, current_user))
        client = TestClient(app)
        headers = {"X-Test-User": str(stranger)}
        assert client.get(f"/api/v1/environments/{environment_id}", headers=headers).status_code == 404
        assert client.patch(
            f"/api/v1/environments/{environment_id}", headers=headers, json={"name": "Invadido"}
        ).status_code == 404
        assert catalog.get_rules(owner, environment_id) == {
            "min_c": 2.0, "max_c": 8.0, "attention_margin_c": 0.5,
        }

        for operation in (
            lambda: catalog.get_environment(stranger, environment_id),
            lambda: catalog.update_environment(stranger, environment_id, "Invadido"),
            lambda: catalog.list_devices(stranger, environment_id),
            lambda: catalog.create_device(stranger, environment_id, "Outro", f"other-{token}"),
            lambda: catalog.get_rules(stranger, environment_id),
            lambda: catalog.update_rules(
                stranger, environment_id,
                ThresholdInput(min_c=1, max_c=9, attention_margin_c=0.5),
            ),
        ):
            with pytest.raises(HTTPException) as exc:
                operation()
            assert exc.value.status_code == 404

        mqtt_id = f"catalog-{token}"
        device = catalog.create_device(owner, environment_id, "ESP32", mqtt_id)
        device_id = UUID(device["id"])
        assert catalog.active_device(mqtt_id)["id"] == device["id"]
        assert catalog.device_for_user(stranger, mqtt_id) is None
        with pytest.raises(HTTPException) as duplicate:
            catalog.create_device(owner, environment_id, "Duplicado", mqtt_id)
        assert duplicate.value.status_code == 409
        with pytest.raises(HTTPException) as foreign_device:
            catalog.get_device(stranger, device_id)
        assert foreign_device.value.status_code == 404
        assert catalog.update_device(owner, device_id, "ESP32 atualizado")["name"] == "ESP32 atualizado"

        changed = ThresholdInput(min_c=1, max_c=9, attention_margin_c=1)
        assert catalog.update_rules(owner, environment_id, changed) == {
            "min_c": 1.0, "max_c": 9.0, "attention_margin_c": 1.0,
        }
        assert CatalogService(config).thresholds_for_environment(environment_id)["max_c"] == 9.0
        with connect(config) as connection:
            audit = connection.execute(
                "SELECT details FROM audit_events WHERE actor_user_id = %s "
                "AND event_type = 'environment_rules_updated'",
                (owner,),
            ).fetchone()[0]
            assert audit["before"]["max_c"] == 8.0
            assert audit["after"]["max_c"] == 9.0

        assert catalog.deactivate_device(owner, device_id)["is_active"] is False
        assert catalog.active_device(mqtt_id) is None
        assert catalog.registered_device(mqtt_id)["id"] == device["id"]
        assert catalog.device_for_user(owner, mqtt_id)["id"] == device["id"]
        assert catalog.get_device(owner, device_id)["is_active"] is False
    finally:
        with connect(config) as connection:
            if environment_id:
                connection.execute(
                    "DELETE FROM audit_events WHERE actor_user_id IN (%s, %s)",
                    (owner, stranger),
                )
                connection.execute(
                    "DELETE FROM devices WHERE environment_id = %s", (environment_id,)
                )
                connection.execute(
                    "DELETE FROM environment_rules WHERE environment_id = %s", (environment_id,)
                )
                connection.execute("DELETE FROM environments WHERE id = %s", (environment_id,))
            connection.execute("DELETE FROM users WHERE id IN (%s, %s)", (owner, stranger))


@pytest.mark.integration
def test_environment_rules_migration_preserves_old_values_and_defaults() -> None:
    config = settings()
    with connect(config) as connection:
        schema = f"catalog_migration_{uuid4().hex}"
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        connection.execute(sql.SQL("SET LOCAL search_path TO {}").format(sql.Identifier(schema)))
        connection.execute((MIGRATIONS / "001_initial.sql").read_text())
        user = connection.execute(
            "INSERT INTO users (email, password_hash) VALUES ('test@example.invalid', 'hash') "
            "RETURNING id"
        ).fetchone()[0]
        custom = connection.execute(
            "INSERT INTO environments (owner_user_id, name) VALUES (%s, 'Custom') RETURNING id",
            (user,),
        ).fetchone()[0]
        default = connection.execute(
            "INSERT INTO environments (owner_user_id, name) VALUES (%s, 'Default') RETURNING id",
            (user,),
        ).fetchone()[0]
        device = connection.execute(
            "INSERT INTO devices (environment_id, mqtt_device_id, name) "
            "VALUES (%s, 'test-device', 'ESP32') RETURNING id",
            (custom,),
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO rules (device_id, temp_min_c, temp_max_c, recovery_margin_c) "
            "VALUES (%s, 1, 9, 1)",
            (device,),
        )

        conflicting_device = connection.execute(
            "INSERT INTO devices (environment_id, mqtt_device_id, name) "
            "VALUES (%s, 'conflicting-device', 'ESP32 2') RETURNING id",
            (custom,),
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO rules (device_id, temp_min_c, temp_max_c, recovery_margin_c) "
            "VALUES (%s, 2, 8, 0.5)", (conflicting_device,),
        )
        with pytest.raises(psycopg.errors.RaiseException):
            with connection.transaction():
                connection.execute((MIGRATIONS / "003_environment_rules.sql").read_text())
        connection.execute("DELETE FROM rules WHERE device_id = %s", (conflicting_device,))

        connection.execute((MIGRATIONS / "003_environment_rules.sql").read_text())
        assert connection.execute(
            "SELECT temp_min_c, temp_max_c, recovery_margin_c FROM environment_rules "
            "WHERE environment_id = %s",
            (custom,),
        ).fetchone() == (1, 9, 1)
        assert connection.execute(
            "SELECT temp_min_c, temp_max_c, recovery_margin_c FROM environment_rules "
            "WHERE environment_id = %s",
            (default,),
        ).fetchone() == (2, 8, 0.5)
        assert connection.execute("SELECT count(*) FROM rules").fetchone() == (1,)
        connection.rollback()
