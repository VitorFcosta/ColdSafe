import secrets
from dataclasses import dataclass
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg import sql
from pwdlib import PasswordHash

from backend.app.api.auth import AuthService
from backend.app.repositories import postgres
from backend.tests.integration.test_postgres_schema_integration import settings


pytestmark = pytest.mark.integration
LEGACY_TABLES = (
    "users", "sessions", "environments", "devices", "rules", "alerts",
    "actuator_commands", "audit_events", "environment_rules", "schema_migrations",
)


@pytest.fixture
def database():
    config = settings()
    name = f"b205_{uuid4().hex}"
    with postgres.connect(config) as admin:
        admin.autocommit = True
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    isolated = config.model_copy(update={"postgres_db": name})
    try:
        yield isolated
    finally:
        with postgres.connect(config) as admin:
            admin.autocommit = True
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def snapshot(connection):
    return {
        table: connection.execute(sql.SQL("SELECT to_jsonb(t) FROM {} t ORDER BY to_jsonb(t)::text")
                                  .format(sql.Identifier(table))).fetchall()
        for table in LEGACY_TABLES
    }


def seed_legacy(config):
    with postgres.connect(config) as connection:
        connection.execute("CREATE TABLE schema_migrations (version integer PRIMARY KEY, "
                           "applied_at timestamptz NOT NULL DEFAULT now())")
        for version, path in postgres.MIGRATIONS[:3]:
            connection.execute(path.read_text())
            connection.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (version,))
        owner = connection.execute("INSERT INTO users (email, password_hash) VALUES "
                                   "('legacy@example.invalid', %s) RETURNING id",
                                   (PasswordHash.recommended().hash(secrets.token_urlsafe(24)),)).fetchone()[0]
        connection.execute("INSERT INTO sessions (user_id, token_hash, expires_at, revoked_at) "
                           "VALUES (%s, %s, now() + interval '1 day', now())", (owner, "a" * 64))
        environment = connection.execute("INSERT INTO environments (owner_user_id, name) "
                                         "VALUES (%s, 'Legacy') RETURNING id", (owner,)).fetchone()[0]
        device = connection.execute("INSERT INTO devices (environment_id, mqtt_device_id, name, is_active) "
                                    "VALUES (%s, 'legacy-device', 'Legacy', false) RETURNING id",
                                    (environment,)).fetchone()[0]
        connection.execute("INSERT INTO rules (device_id, temp_min_c, temp_max_c) VALUES (%s, 1, 9)", (device,))
        connection.execute("INSERT INTO environment_rules (environment_id, temp_min_c, temp_max_c) "
                           "VALUES (%s, 1, 9)", (environment,))
        connection.execute("INSERT INTO alerts (device_id, kind) VALUES (%s, 'temperature_high')", (device,))
        command = uuid4()
        connection.execute("INSERT INTO actuator_commands (id, device_id, requested_by_user_id, actuator, "
                           "desired_on, origin, status, deadline_at) VALUES "
                           "(%s, %s, %s, 'led', true, 'manual', 'unconfirmed', now() + interval '30 seconds')",
                           (command, device, owner))
        connection.execute("INSERT INTO audit_events (actor_user_id, device_id, command_id, event_type, details) "
                           "VALUES (%s, %s, %s, 'legacy', '{\"preserved\":true}')", (owner, device, command))


@dataclass(frozen=True)
class DemoAccount:
    owner: UUID
    environment: UUID
    dataset: UUID
    job: UUID
    model: UUID


@pytest.fixture
def demo(database):
    """Small, private metadata fixtures; no fake trained artifacts or reusable passwords."""
    postgres.initialize_schema(database)
    accounts = []
    with postgres.connect(database) as connection:
        for role in ("viewer", "operator", "admin"):
            owner = connection.execute("INSERT INTO users (email, password_hash, role) "
                                       "VALUES (%s, %s, %s) RETURNING id",
                                       (f"{role}@example.invalid", PasswordHash.recommended().hash(
                                           secrets.token_urlsafe(24)), role)).fetchone()[0]
            environment = connection.execute("INSERT INTO environments (owner_user_id, name) "
                                             "VALUES (%s, %s) RETURNING id", (owner, role)).fetchone()[0]
            dataset = connection.execute("INSERT INTO datasets (owner_user_id, name, features_version) "
                                         "VALUES (%s, 'Demo', 'fan-v1') RETURNING id", (owner,)).fetchone()[0]
            job = connection.execute("INSERT INTO jobs (owner_user_id, environment_id, job_type, dataset_id, total_units) "
                                     "VALUES (%s, %s, 'training', %s, 2) RETURNING id",
                                     (owner, environment, dataset)).fetchone()[0]
            model = connection.execute("INSERT INTO models (owner_user_id, dataset_id, training_job_id, "
                                       "model_version, features_version, artifact_key) "
                                       "VALUES (%s, %s, %s, 'demo-v1', 'fan-v1', 'demo/package') RETURNING id",
                                       (owner, dataset, job)).fetchone()[0]
            accounts.append(DemoAccount(owner, environment, dataset, job, model))
    return database, tuple(accounts)


def test_new_database_and_repeatable_migrations(database):
    postgres.initialize_schema(database)
    postgres.initialize_schema(database)
    with postgres.connect(database) as connection:
        assert connection.execute("SELECT array_agg(version ORDER BY version) FROM schema_migrations").fetchone() == ([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],)
        tables = {row[0] for row in connection.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'")}
        assert {"jobs", "datasets", "models", "model_activations", "active_models"} <= tables


def test_migrates_copy_of_legacy_database_preserving_every_record(database):
    seed_legacy(database)
    copy_name = f"b205_copy_{uuid4().hex}"
    with postgres.connect(database) as connection:
        before = snapshot(connection)
    admin_config = settings()
    with postgres.connect(admin_config) as admin:
        admin.autocommit = True
        admin.execute(sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
            sql.Identifier(copy_name), sql.Identifier(database.postgres_db)))
    copied = database.model_copy(update={"postgres_db": copy_name})
    try:
        postgres.initialize_schema(copied)
        postgres.initialize_schema(copied)
        with postgres.connect(copied) as connection:
            after = snapshot(connection)
            assert [{k: v for k, v in row[0].items() if k != "role"} for row in after["users"]] == [row[0] for row in before["users"]]
            assert connection.execute("SELECT role FROM users").fetchall() == [("operator",)]
            for table in LEGACY_TABLES[1:-1]:
                if table == "sessions":
                    preserved = [{k: v for k, v in row[0].items() if k != "token_kind"}
                                 for row in after[table]]
                    assert preserved == [row[0] for row in before[table]]
                    assert all(row[0]["token_kind"] == "opaque" for row in after[table])
                else:
                    assert after[table] == before[table], table
            assert [row for row in after["schema_migrations"] if row[0]["version"] <= 3] == before["schema_migrations"]
        with postgres.connect(database) as connection:
            assert snapshot(connection) == before
    finally:
        with postgres.connect(admin_config) as admin:
            admin.autocommit = True
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(copy_name)))


def test_failed_migration_rolls_back_and_can_be_retried(database, monkeypatch, tmp_path):
    seed_legacy(database)
    with postgres.connect(database) as connection:
        before = snapshot(connection)
    failed = tmp_path / "005_broken.sql"
    failed.write_text("CREATE TABLE incomplete (id integer); SELECT missing_column FROM incomplete;")
    migrations = postgres.MIGRATIONS
    with monkeypatch.context() as patch:
        patch.setattr(postgres, "MIGRATIONS", (*migrations[:4], (5, failed)))
        with pytest.raises(psycopg.errors.UndefinedColumn):
            postgres.initialize_schema(database)
    with postgres.connect(database) as connection:
        assert snapshot(connection) == before
        assert connection.execute("SELECT to_regclass('incomplete')").fetchone() == (None,)
    postgres.initialize_schema(database)
    test_new_database_and_repeatable_migrations(database)


def test_public_registration_cannot_choose_any_role(database):
    postgres.initialize_schema(database)
    auth = AuthService(database)
    app = FastAPI()
    app.include_router(auth.router)
    auth.install_exception_handlers(app)
    client = TestClient(app)
    payload = {"email": "new@example.invalid", "password": secrets.token_urlsafe(24)}
    for role in ("admin", "operator", "viewer"):
        assert client.post("/api/v1/auth/register", json={**payload, "role": role}).status_code == 422
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    with postgres.connect(database) as connection:
        assert connection.execute("SELECT role FROM users WHERE email=%s", (payload["email"],)).fetchone() == ("operator",)
        with pytest.raises(psycopg.errors.CheckViolation), connection.transaction():
            connection.execute("UPDATE users SET role='superuser'")


def test_private_repository_filters_all_records_and_admin_has_no_bypass(demo):
    from backend.app.repositories.aiot import AiotRepository

    config, accounts = demo
    repository = AiotRepository(config)
    owner, stranger, admin = accounts
    for account in accounts:
        assert repository.get_job(account.owner, account.job)["id"] == account.job
        assert repository.get_dataset(account.owner, account.dataset)["id"] == account.dataset
        assert repository.get_model(account.owner, account.model)["id"] == account.model
        assert repository.get_active_model(account.owner) is None
    for account in (stranger, admin):
        assert repository.get_job(account.owner, owner.job) is None
        assert repository.get_dataset(account.owner, owner.dataset) is None
        assert repository.get_model(account.owner, owner.model) is None
    assert repository.get_model(owner.owner, uuid4()) is None


@pytest.mark.parametrize("statement,field", [
    ("UPDATE jobs SET dataset_id=%s WHERE id=%s", "dataset"),
    ("UPDATE jobs SET environment_id=%s WHERE id=%s", "environment"),
    ("UPDATE models SET dataset_id=%s WHERE id=%s", "dataset"),
    ("UPDATE models SET training_job_id=%s WHERE id=%s", "job"),
])
def test_cross_account_relations_are_rejected(demo, statement, field):
    config, (owner, stranger, _admin) = demo
    record_id = owner.job if statement.startswith("UPDATE jobs") else owner.model
    with postgres.connect(config) as connection:
        with pytest.raises(psycopg.errors.ForeignKeyViolation), connection.transaction():
            connection.execute(statement, (getattr(stranger, field), record_id))


def test_activations_are_private_and_active_pointer_is_unique_per_owner(demo):
    from backend.app.repositories.aiot import AiotRepository

    config, (owner, stranger, _admin) = demo
    with postgres.connect(config) as connection:
        with pytest.raises(psycopg.errors.ForeignKeyViolation), connection.transaction():
            connection.execute("INSERT INTO model_activations (owner_user_id, model_id) VALUES (%s,%s)", (stranger.owner, owner.model))
        activation = connection.execute("INSERT INTO model_activations (owner_user_id, model_id) VALUES (%s,%s) RETURNING id", (owner.owner, owner.model)).fetchone()[0]
        with pytest.raises(psycopg.errors.UniqueViolation), connection.transaction():
            connection.execute("INSERT INTO model_activations (owner_user_id, model_id) VALUES (%s,%s)", (owner.owner, owner.model))
        with pytest.raises(psycopg.errors.ForeignKeyViolation), connection.transaction():
            connection.execute("INSERT INTO active_models (owner_user_id, model_id) VALUES (%s,%s)", (stranger.owner, owner.model))
        for account in (owner, stranger):
            connection.execute("INSERT INTO active_models (owner_user_id, model_id) VALUES (%s,%s)", (account.owner, account.model))
        with pytest.raises(psycopg.errors.UniqueViolation), connection.transaction():
            connection.execute("INSERT INTO active_models (owner_user_id, model_id) VALUES (%s,%s)", (owner.owner, owner.model))
    repository = AiotRepository(config)
    assert repository.get_activation(owner.owner, activation)["id"] == activation
    assert repository.get_activation(stranger.owner, activation) is None
    assert repository.get_active_model(owner.owner)["id"] == owner.model
    assert repository.get_active_model(stranger.owner)["id"] == stranger.model


def test_model_outbox_has_one_request_per_activation_and_ordered_statuses(demo):
    config, (owner, _stranger, _admin) = demo
    with postgres.connect(config) as connection:
        activation = connection.execute(
            'INSERT INTO model_activations (owner_user_id, model_id) VALUES (%s,%s) RETURNING id',
            (owner.owner, owner.model),
        ).fetchone()[0]
        event = uuid4()
        sequence = connection.execute(
            "INSERT INTO model_outbox (event_id, activation_id, publisher_role, event) "
            "VALUES (%s,%s,'api','{}') RETURNING sequence", (event, activation),
        ).fetchone()[0]
        for role in ('api', 'inference'):
            with pytest.raises(psycopg.errors.UniqueViolation), connection.transaction():
                connection.execute(
                    'INSERT INTO model_outbox (event_id, activation_id, publisher_role, event) '
                    "VALUES (%s,%s,%s,'{}')", (event if role == 'inference' else uuid4(), activation, role),
                )
        for role, payload in (('training', '{}'), ('inference', '[]')):
            with pytest.raises(psycopg.errors.CheckViolation), connection.transaction():
                connection.execute(
                    'INSERT INTO model_outbox (event_id, activation_id, publisher_role, event) '
                    'VALUES (%s,%s,%s,%s::jsonb)', (uuid4(), activation, role, payload),
                )
        with pytest.raises(psycopg.errors.ForeignKeyViolation), connection.transaction():
            connection.execute(
                'INSERT INTO model_outbox (event_id, activation_id, publisher_role, event) '
                "VALUES (%s,%s,'inference','{}')", (uuid4(), uuid4()),
            )
        for _ in range(2):
            next_sequence, created, published = connection.execute(
                'INSERT INTO model_outbox (event_id, activation_id, publisher_role, event) '
                "VALUES (%s,%s,'inference','{}') RETURNING sequence,created_at,published_at",
                (uuid4(), activation),
            ).fetchone()
            assert next_sequence > sequence and created is not None and published is None
            sequence = next_sequence


@pytest.mark.parametrize("changes", [
    "completed_units=3", "completed_units=-1", "status='completed'", "status='failed'",
    "status='running', error_code='TRAINING_FAILED'", "job_type='generation'", "config='[]'::jsonb",
])
def test_job_constraints_reject_invalid_progress_and_types(demo, changes):
    config, (owner, _stranger, _admin) = demo
    with postgres.connect(config) as connection:
        with pytest.raises(psycopg.errors.CheckViolation), connection.transaction():
            connection.execute(sql.SQL("UPDATE jobs SET {} WHERE id=%s").format(sql.SQL(changes)), (owner.job,))


def test_generation_and_training_accept_persisted_results_and_reject_foreign_results(demo):
    config, (owner, stranger, _admin) = demo
    with postgres.connect(config) as connection:
        generation = connection.execute("INSERT INTO jobs (owner_user_id, job_type, total_units) "
                                        "VALUES (%s, 'generation', 10) RETURNING id", (owner.owner,)).fetchone()[0]
        connection.execute("UPDATE datasets SET generation_job_id=%s WHERE id=%s", (generation, owner.dataset))
        with pytest.raises(psycopg.errors.ForeignKeyViolation), connection.transaction():
            connection.execute("UPDATE jobs SET status='completed', completed_units=10, result_dataset_id=%s "
                               "WHERE id=%s", (stranger.dataset, generation))
        connection.execute("UPDATE jobs SET status='completed', completed_units=10, result_dataset_id=%s "
                           "WHERE id=%s", (owner.dataset, generation))
        with pytest.raises(psycopg.errors.ForeignKeyViolation), connection.transaction():
            connection.execute("UPDATE jobs SET status='completed', completed_units=2, result_model_id=%s "
                               "WHERE id=%s", (stranger.model, owner.job))
        connection.execute("UPDATE jobs SET status='completed', completed_units=2, result_model_id=%s "
                           "WHERE id=%s", (owner.model, owner.job))
        assert connection.execute("SELECT count(*) FROM jobs WHERE status='completed'").fetchone() == (2,)
        with pytest.raises(psycopg.errors.ForeignKeyViolation), connection.transaction():
            connection.execute("INSERT INTO model_activations (owner_user_id, model_id, previous_model_id) "
                               "VALUES (%s, %s, %s)", (owner.owner, owner.model, stranger.model))


@pytest.mark.parametrize("key", ["../model", "/tmp/model", "https://example.invalid/model", "models/../model"])
def test_artifact_references_reject_external_or_traversing_paths(demo, key):
    config, (owner, _stranger, _admin) = demo
    with postgres.connect(config) as connection:
        for table, record in (("datasets", owner.dataset), ("models", owner.model)):
            with pytest.raises(psycopg.errors.CheckViolation), connection.transaction():
                connection.execute(sql.SQL("UPDATE {} SET artifact_key=%s WHERE id=%s")
                                   .format(sql.Identifier(table)), (key, record))


def test_training_rejects_result_from_another_job_of_the_same_owner(demo):
    config, (owner, _stranger, _admin) = demo
    with postgres.connect(config) as connection:
        other = connection.execute("INSERT INTO jobs (owner_user_id, job_type, dataset_id, total_units) "
                                   "VALUES (%s, 'training', %s, 2) RETURNING id",
                                   (owner.owner, owner.dataset)).fetchone()[0]
        with pytest.raises(psycopg.errors.ForeignKeyViolation), connection.transaction():
            connection.execute("UPDATE jobs SET status='completed', completed_units=2, result_model_id=%s "
                               "WHERE id=%s", (owner.model, other))


def test_generation_rejects_result_from_another_job_of_the_same_owner(demo):
    config, (owner, _stranger, _admin) = demo
    with postgres.connect(config) as connection:
        jobs = [connection.execute("INSERT INTO jobs (owner_user_id, job_type, total_units) "
                                   "VALUES (%s, 'generation', 10) RETURNING id",
                                   (owner.owner,)).fetchone()[0] for _ in range(2)]
        connection.execute("UPDATE datasets SET generation_job_id=%s WHERE id=%s", (jobs[0], owner.dataset))
        with pytest.raises(psycopg.errors.ForeignKeyViolation), connection.transaction():
            connection.execute("UPDATE jobs SET status='completed', completed_units=10, result_dataset_id=%s "
                               "WHERE id=%s", (owner.dataset, jobs[1]))
        with pytest.raises(psycopg.errors.ForeignKeyViolation), connection.transaction():
            connection.execute("UPDATE datasets SET generation_job_id=%s WHERE id=%s", (owner.job, owner.dataset))
