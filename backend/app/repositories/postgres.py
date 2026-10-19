from pathlib import Path

import psycopg

from backend.app.config.settings import RuntimeSettings


MIGRATIONS = (
    (1, Path(__file__).resolve().parents[2] / "migrations" / "001_initial.sql"),
    (2, Path(__file__).resolve().parents[2] / "migrations" / "002_command_status.sql"),
    (3, Path(__file__).resolve().parents[2] / "migrations" / "003_environment_rules.sql"),
    (4, Path(__file__).resolve().parents[2] / "migrations" / "004_user_roles.sql"),
    (5, Path(__file__).resolve().parents[2] / "migrations" / "005_aiot_records.sql"),
    (6, Path(__file__).resolve().parents[2] / "migrations" / "006_auth_security.sql"),
    (7, Path(__file__).resolve().parents[2] / "migrations" / "007_aiot_events.sql"),
    (8, Path(__file__).resolve().parents[2] / "migrations" / "008_job_outbox.sql"),
    (9, Path(__file__).resolve().parents[2] / "migrations" / "009_model_activation_outbox.sql"),
    (10, Path(__file__).resolve().parents[2] / "migrations" / "010_inference_events.sql"),
    (11, Path(__file__).resolve().parents[2] / "migrations" / "011_predictive_alerts.sql"),
)


def connect(settings: RuntimeSettings) -> psycopg.Connection:
    return psycopg.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        dbname=settings.postgres_db,
        user=settings.postgres_user,
        password=settings.postgres_password.get_secret_value(),
        connect_timeout=3,
    )


def initialize_schema(settings: RuntimeSettings) -> None:
    with connect(settings) as connection:
        connection.execute("SELECT pg_advisory_xact_lock(2026092301)")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version integer PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        )
        for version, path in MIGRATIONS:
            applied = connection.execute(
                "SELECT 1 FROM schema_migrations WHERE version = %s", (version,)
            ).fetchone()
            if applied is None:
                connection.execute(path.read_text(encoding="utf-8"))
                connection.execute(
                    "INSERT INTO schema_migrations (version) VALUES (%s)", (version,)
                )


def is_ready(settings: RuntimeSettings) -> bool:
    try:
        with connect(settings) as connection:
            return connection.execute("SELECT 1").fetchone() == (1,)
    except psycopg.Error:
        return False
