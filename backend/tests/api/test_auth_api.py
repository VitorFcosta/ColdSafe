from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4
from types import SimpleNamespace
import secrets
import jwt
import pytest
from pydantic import SecretStr
from pwdlib import PasswordHash

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
        self.rates = {}
        self.audits = []
        self.roles = {}

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
            session_id, user_id, token_hash, created_at, expires_at = params
            self.sessions[token_hash] = [user_id, created_at, expires_at, None, session_id, "jwt"]
            return Cursor()
        if statement.startswith("UPDATE USERS SET PASSWORD_HASH"):
            password_hash, user_id, old_hash = params
            self.users = {email: (uid, password_hash if uid == user_id and value == old_hash else value)
                          for email, (uid, value) in self.users.items()}
            return Cursor()
        if statement.startswith("INSERT INTO LOGIN_RATE_LIMITS"):
            key, now = params
            count, started = self.rates.get(key, (0, now))
            if now >= started + timedelta(minutes=15):
                count, started = 0, now
            self.rates[key] = (count + 1, started)
            return Cursor(self.rates[key])
        if statement.startswith("INSERT INTO AUDIT_EVENTS"):
            self.audits.append(params)
            return Cursor()
        if statement.startswith("SELECT S.ID, S.USER_ID"):
            value, now, cutoff = params
            session = self.sessions.get(value) if "TOKEN_HASH" in statement else next(
                (row for row in self.sessions.values() if row[4] == value), None)
            if not session or session[2] <= now or session[3] is not None:
                return Cursor()
            email = next(email for email, row in self.users.items() if row[0] == session[0])
            return Cursor((session[4], session[0], email, self.roles.get(session[0], "operator"),
                           session[2], session[5], session[1]))
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
    auth = AuthService(SimpleNamespace(auth_jwt_secret=SecretStr(secrets.token_urlsafe(32))), clock=lambda: clock[0])
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
    assert database.users["user@example.com"][1].startswith("$2b$")
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


def test_me_and_role_are_current_database_values(monkeypatch):
    client, database, _clock = make_client(monkeypatch)
    payload = {"email": "user@example.com", "password": "correct-horse"}
    user = client.post("/api/v1/auth/register", json=payload).json()["data"]["user_id"]
    token = client.post("/api/v1/auth/login", json=payload).json()["data"]["token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/v1/auth/me", headers=headers).json()["data"] == {
        "user_id": user, "email": payload["email"], "role": "operator"}
    database.roles[database.users[payload["email"]][0]] = "viewer"
    assert client.get("/api/v1/auth/me", headers=headers).json()["data"]["role"] == "viewer"


def test_registration_rejects_more_than_72_utf8_bytes(monkeypatch):
    client, _db, _clock = make_client(monkeypatch)
    assert client.post("/api/v1/auth/register", json={"email": "a@example.com", "password": "á" * 37}).status_code == 422
    assert client.post("/api/v1/auth/register", json={"email": "a@example.com", "password": "x" * 72}).status_code == 201


@pytest.mark.parametrize("password", ["old-password", "á" * 40])
def test_argon2_login_rehashes_only_safe_passwords(monkeypatch, password):
    client, database, _clock = make_client(monkeypatch)
    old_hash = PasswordHash.recommended().hash(password)
    database.users["old@example.com"] = (uuid4(), old_hash)
    assert client.post("/api/v1/auth/login", json={"email": "old@example.com", "password": "wrong"}).status_code == 401
    assert database.users["old@example.com"][1] == old_hash
    assert client.post("/api/v1/auth/login", json={"email": "old@example.com", "password": password}).status_code == 200
    new_hash = database.users["old@example.com"][1]
    assert new_hash == old_hash if len(password.encode()) > 72 else new_hash.startswith("$2b$")


def test_unknown_or_malformed_hash_returns_invalid_credentials(monkeypatch):
    client, database, _clock = make_client(monkeypatch)
    for hash_value in ("broken", "$argon2id$malformed", "$2b$malformed"):
        database.users["old@example.com"] = (uuid4(), hash_value)
        response = client.post("/api/v1/auth/login", json={"email": "old@example.com", "password": "wrong"})
        assert response.status_code == 401


def test_login_limit_persists_invalid_attempts_and_resets(monkeypatch):
    client, database, clock = make_client(monkeypatch)
    for _ in range(10):
        assert client.post("/api/v1/auth/login", json={"email": "missing@example.com", "password": "wrong"}).status_code == 401
    limited = client.post("/api/v1/auth/login", json={"email": "MISSING@example.com", "password": "wrong"}, headers={"X-Forwarded-For": "new-ip"})
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "RATE_LIMITED"
    assert limited.headers["retry-after"] == "900"
    assert "missing@example.com" not in str(database.audits)
    assert "wrong" not in str(database.audits)
    clock[0] += timedelta(minutes=15)
    assert client.post("/api/v1/auth/login", json={"email": "missing@example.com", "password": "wrong"}).status_code == 401


def test_tampered_jwt_is_rejected(monkeypatch):
    client, _database, _clock = make_client(monkeypatch)
    payload = {"email": "user@example.com", "password": "correct-horse"}
    client.post("/api/v1/auth/register", json=payload)
    token = client.post("/api/v1/auth/login", json=payload).json()["data"]["token"]
    claims = jwt.decode(token, options={"verify_signature": False})
    assert claims["iss"] == "coldsafe" and claims["aud"] == "coldsafe-api"
    assert claims["iat"] == int(NOW.timestamp())
    assert claims["nbf"] == claims["iat"]
    assert client.get("/private", headers={"Authorization": f"Bearer {token[:-8]}badtoken"}).status_code == 401
