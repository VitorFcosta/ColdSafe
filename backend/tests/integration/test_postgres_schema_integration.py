import os
from uuid import uuid4

import psycopg
import pytest

from backend.app.config.settings import RuntimeSettings
from backend.app.repositories.postgres import connect, initialize_schema


def settings() -> RuntimeSettings:
    password = os.getenv("POSTGRES_TEST_PASSWORD")
    if not password:
        pytest.skip("POSTGRES_TEST_PASSWORD is required for PostgreSQL integration")
    return RuntimeSettings(
        mqtt_host="unused",
        mqtt_port=1883,
        mqtt_topic="unused",
        mqtt_qos=1,
        mqtt_client_id="unused",
        mqtt_backend_username="unused",
        mqtt_backend_password="unused",
        influxdb_url="http://localhost:8086",
        influxdb_org="unused",
        influxdb_bucket="unused",
        influxdb_token="unused",
        postgres_host=os.getenv("POSTGRES_TEST_HOST", "127.0.0.1"),
        postgres_port=int(os.getenv("POSTGRES_TEST_PORT", "15432")),
        postgres_db=os.getenv("POSTGRES_TEST_DB", "coldsafe"),
        postgres_user=os.getenv("POSTGRES_TEST_USER", "coldsafe"),
        postgres_password=password,
        _env_file=None,
    )


@pytest.mark.integration
def test_migration_is_repeatable_and_relations_reject_invalid_data() -> None:
    config = settings()
    initialize_schema(config)
    initialize_schema(config)

    connection = connect(config)
    try:
        assert connection.execute(
            "SELECT array_agg(version ORDER BY version) FROM schema_migrations"
        ).fetchone() == ([1, 2, 3],)
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            ).fetchall()
        }
        assert {
            "users", "sessions", "environments", "devices", "rules",
            "alerts", "actuator_commands", "audit_events", "environment_rules",
        } <= tables

        email = f"test-{uuid4().hex}@example.invalid"
        user_id = connection.execute(
            "INSERT INTO users (email, password_hash) VALUES (%s, %s) RETURNING id",
            (email, "test-hash"),
        ).fetchone()[0]
        environment_id = connection.execute(
            "INSERT INTO environments (owner_user_id, name) "
            "VALUES (%s, %s) RETURNING id",
            (user_id, "Laboratório"),
        ).fetchone()[0]
        mqtt_device_id = f"test-{uuid4().hex}"
        device_id = connection.execute(
            "INSERT INTO devices (environment_id, mqtt_device_id, name) "
            "VALUES (%s, %s, %s) RETURNING id",
            (environment_id, mqtt_device_id, "ESP32"),
        ).fetchone()[0]
        assert connection.execute(
            "SELECT e.owner_user_id FROM devices d JOIN environments e "
            "ON e.id = d.environment_id WHERE d.id = %s", (device_id,)
        ).fetchone() == (user_id,)

        connection.execute(
            "INSERT INTO rules (device_id, temp_min_c, temp_max_c, recovery_margin_c) "
            "VALUES (%s, 2, 8, 0.5)", (device_id,)
        )
        connection.execute(
            "INSERT INTO actuator_commands "
            "(id, device_id, requested_by_user_id, actuator, desired_on, origin, "
            "status, deadline_at) VALUES (%s, %s, %s, 'led', true, 'manual', "
            "'rejected', now() + interval '10 seconds')",
            (uuid4(), device_id, user_id),
        )

        with pytest.raises(psycopg.errors.UniqueViolation):
            with connection.transaction():
                connection.execute(
                    "INSERT INTO devices (environment_id, mqtt_device_id, name) "
                    "VALUES (%s, %s, %s)",
                    (environment_id, mqtt_device_id, "Duplicado"),
                )
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            with connection.transaction():
                connection.execute(
                    "INSERT INTO environments (owner_user_id, name) VALUES (%s, %s)",
                    (uuid4(), "Sem dono"),
                )
        with pytest.raises(psycopg.errors.CheckViolation):
            with connection.transaction():
                connection.execute(
                    "UPDATE rules SET temp_min_c = 9 WHERE device_id = %s",
                    (device_id,),
                )
    finally:
        connection.rollback()
        connection.close()
