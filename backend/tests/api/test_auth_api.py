from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4

import psycopg
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from backend.app.api.auth import AuthService


NOW = datetime(2026, 9, 24, 12, tzinfo=UTC)


class Cursor:
    def __init__(self, row=None):
        self.row = row

    def fetchone(self):
        return self.row


class FakeDatabase:
    def __init__(self):
        self.users = {}
        self.sessions = {}

    def __call__(self, _settings):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params):
        statement = " ".join(sql.split()).upper()
        if statement.startswith("INSERT INTO USERS"):
            email, password_hash = params
            if email.lower() in self.users:
                raise psycopg.errors.UniqueViolation("email already registered")
            user_id = uuid4()
            self.users[email.lower()] = (user_id, password_hash)
            return Cursor((user_id,))
        if statement.startswith("SELECT ID, PASSWORD_HASH FROM USERS"):
            return Cursor(self.users.get(params[0].lower()))
        if statement.startswith("INSERT INTO SESSIONS"):
            user_id, token_hash, created_at, expires_at = params
            self.sessions[token_hash] = [user_id, created_at, expires_at, None]
            return Cursor()
        if statement.startswith("SELECT USER_ID FROM SESSIONS"):
            token_hash, now = params
            session = self.sessions.get(token_hash)
            return Cursor((session[0],) if session and session[2] > now and session[3] is None else None)
        if statement.startswith("UPDATE SESSIONS"):
            revoked_at, token_hash, now = params
            session = self.sessions.get(token_hash)
            if session and session[2] > now and session[3] is None:
                session[3] = revoked_at
                return Cursor((session[0],))
            return Cursor()
        raise AssertionError(f"Unexpected SQL: {sql}")


def make_client(monkeypatch):
    database = FakeDatabase()
    clock = [NOW]
    monkeypatch.setattr("backend.app.api.auth.connect", database)
    auth = AuthService(object(), clock=lambda: clock[0])
    app = FastAPI()
    app.include_router(auth.router)
    auth.install_exception_handlers(app)

    @app.get("/private")
    def private(user_id=Depends(auth.require_user)):
        return {"user_id": str(user_id)}

    return TestClient(app), database, clock


def test_registration_login_and_protected_route(monkeypatch):
    client, database, _clock = make_client(monkeypatch)
    registered = client.post("/api/v1/auth/register", json={"email": " User@Example.com ", "password": "correct-horse"})
    assert registered.status_code == 201
    assert registered.json()["success"] is True
    assert registered.json()["data"]["email"] == "user@example.com"
    assert database.users["user@example.com"][1].startswith("$argon2")
    assert "correct-horse" not in database.users["user@example.com"][1]

    logged_in = client.post("/api/v1/auth/login", json={"email": "USER@example.com", "password": "correct-horse"})
    assert logged_in.status_code == 200
    token = logged_in.json()["data"]["token"]
    token_hash = sha256(token.encode()).hexdigest()
    assert logged_in.json()["data"]["expires_at"] == "2026-09-25T12:00:00Z"
    assert list(database.sessions) == [token_hash]
    assert token not in str(database.sessions)
    assert token_hash not in logged_in.text
    assert logged_in.json()["data"]["token_type"] == "Bearer"
    assert client.get("/private", headers={"Authorization": f"Bearer {token}"}).json()["user_id"] == registered.json()["data"]["user_id"]


def test_duplicate_email_and_wrong_password_have_contract_errors(monkeypatch):
    client, _database, _clock = make_client(monkeypatch)
    payload = {"email": "user@example.com", "password": "correct-horse"}
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    duplicate = client.post("/api/v1/auth/register", json={**payload, "email": "USER@example.com"})
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "EMAIL_ALREADY_REGISTERED"
    assert duplicate.json()["meta"]["request_id"]
    wrong = client.post("/api/v1/auth/login", json={**payload, "password": "wrong-password"})
    assert wrong.status_code == 401
    assert wrong.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert "correct-horse" not in wrong.text
    oversized = client.post("/api/v1/auth/login", json={**payload, "password": "x" * 129})
    assert oversized.status_code == 422


def test_session_expires_and_logout_revokes_it(monkeypatch):
    client, _database, clock = make_client(monkeypatch)
    payload = {"email": "user@example.com", "password": "correct-horse"}
    client.post("/api/v1/auth/register", json=payload)
    token = client.post("/api/v1/auth/login", json=payload).json()["data"]["token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 200
    assert client.get("/private", headers=headers).status_code == 401
    another = client.post("/api/v1/auth/login", json=payload).json()["data"]["token"]
    clock[0] = NOW + timedelta(hours=24)
    assert client.get("/private", headers={"Authorization": f"Bearer {another}"}).status_code == 401
    assert client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {another}"}).status_code == 401
