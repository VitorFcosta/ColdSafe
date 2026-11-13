import secrets
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from psycopg import sql

from backend.app.api.app import create_app
from backend.app.api.auth import AuthService
from backend.app.api.catalog import CatalogService
from backend.app.repositories.postgres import connect, initialize_schema
from backend.tests.integration.test_postgres_schema_integration import settings


pytestmark = pytest.mark.integration


@pytest.fixture
def accounts():
    config = settings()
    name = f"b206_roles_{uuid4().hex}"
    with connect(config) as connection:
        connection.autocommit = True
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    private = config.model_copy(update={"postgres_db": name})
    try:
        initialize_schema(private)
        auth, catalog = AuthService(private), CatalogService(private)
        data = {}
        for role in ("viewer", "operator", "admin"):
            password = secrets.token_urlsafe(24)
            email = f"{role}@example.invalid"
            user = auth.register(email, password)
            with connect(private) as connection:
                connection.execute("UPDATE users SET role=%s WHERE id=%s", (role, user))
            environment = catalog.create_environment(user, role)
            device = catalog.create_device(user, environment["id"], role, role)
            token, _ = auth.login(email, password)
            data[role] = {"user": user, "environment": environment["id"],
                          "device": device["id"], "token": token}
        app = create_app(repository=Mock(), readiness_check=lambda: True,
                         auth=auth, catalog=catalog, commands=Mock())
        yield private, TestClient(app), data
    finally:
        with connect(config) as connection:
            connection.autocommit = True
            connection.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def headers(account):
    return {"Authorization": f"Bearer {account['token']}"}


def test_viewer_reads_own_data_and_cannot_write(accounts):
    _config, client, data = accounts
    viewer = data["viewer"]
    assert client.get("/api/v1/environments", headers=headers(viewer)).status_code == 200
    assert client.get(f"/api/v1/devices/{viewer['device']}", headers=headers(viewer)).status_code == 200
    for path, body in (
        ("/api/v1/environments", {"name": "Denied"}),
        (f"/api/v1/devices/{viewer['device']}/led/commands", {"desired_state": True}),
    ):
        response = client.post(path, json=body, headers=headers(viewer))
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.parametrize("role", ["viewer", "operator", "admin"])
def test_all_roles_are_denied_foreign_accounts(accounts, role):
    _config, client, data = accounts
    foreign = data["operator"] if role != "operator" else data["viewer"]
    own = data[role]
    assert client.get(f"/api/v1/devices/{foreign['device']}", headers=headers(own)).status_code == 404
    assert client.get(f"/api/v1/environments/{foreign['environment']}/rules", headers=headers(own)).status_code == 404
    if role != "viewer":
        response = client.patch(f"/api/v1/devices/{foreign['device']}", json={"name": "Denied"}, headers=headers(own))
        assert response.status_code == 404
        assert client.post("/api/v1/environments", json={"name": "Own"}, headers=headers(own)).status_code == 201


def test_only_admin_changes_roles_and_changes_apply_to_existing_token(accounts):
    config, client, data = accounts
    operator, admin = data["operator"], data["admin"]
    path = f"/api/v1/auth/users/{operator['user']}/role"
    assert client.patch(path, json={"role": "admin"}, headers=headers(operator)).status_code == 403
    response = client.patch(path, json={"role": "viewer"}, headers=headers(admin))
    assert response.status_code == 200
    assert response.json()["data"]["role"] == "viewer"
    assert client.post("/api/v1/environments", json={"name": "Denied"}, headers=headers(operator)).status_code == 403
    assert client.get("/api/v1/auth/me", headers=headers(operator)).json()["data"]["role"] == "viewer"
    assert client.patch(path, json={"role": "root"}, headers=headers(admin)).status_code == 422
    assert client.patch(f"/api/v1/auth/users/{uuid4()}/role", json={"role": "viewer"}, headers=headers(admin)).status_code == 404
    with connect(config) as connection:
        row = connection.execute("SELECT actor_user_id, details FROM audit_events "
                                 "WHERE event_type='user_role_changed'").fetchone()
        assert row[0] == admin["user"]
        assert row[1] == {"target_user_id": str(operator["user"]), "before": "operator", "after": "viewer"}
