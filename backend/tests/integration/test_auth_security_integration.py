import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from fastapi.security import HTTPAuthorizationCredentials
from pwdlib import PasswordHash

from backend.app.api.auth import AuthError, AuthService
from backend.app.repositories import postgres
from backend.tests.integration.test_aiot_migrations_integration import database


pytestmark = pytest.mark.integration


@pytest.fixture
def auth_case(database):
    postgres.initialize_schema(database)
    now = [datetime.now(UTC).replace(microsecond=0)]
    auth = AuthService(database, clock=lambda: now[0])
    password = secrets.token_urlsafe(20)
    email = f"auth-{uuid4()}@example.invalid"
    owner = auth.register(email, password)
    return database, auth, now, email, password, owner


def test_jwt_ledger_logout_current_role_and_cross_session_claims(auth_case):
    config, auth, now, email, password, owner = auth_case
    token, expires = auth.login(email, password)
    principal = auth.session_for_token(token)
    assert principal.user_id == owner
    assert principal.role == "operator"
    with postgres.connect(config) as conn:
        assert conn.execute("SELECT token_hash, token_kind FROM sessions").fetchone() == (auth._token_hash(token), "jwt")
        conn.execute("UPDATE users SET role='viewer' WHERE id=%s", (owner,))
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    assert auth.require_user(credentials) == owner
    assert auth.session_for_id(principal.session_id).role == "viewer"
    with pytest.raises(AuthError) as caught:
        auth.require_operator(credentials)
    assert caught.value.code == "FORBIDDEN"
    with pytest.raises(AuthError):
        auth.require_admin(credentials)
    with postgres.connect(config) as conn:
        conn.execute("UPDATE users SET role='admin' WHERE id=%s", (owner,))
    assert auth.require_admin(credentials) == owner
    assert auth.require_operator(credentials) == owner
    claims = jwt.decode(token, options={"verify_signature": False})
    forged = jwt.encode({**claims, "sub": str(uuid4())}, config.auth_jwt_secret.get_secret_value(), algorithm="HS256")
    with postgres.connect(config) as conn:
        conn.execute("UPDATE sessions SET token_hash=%s WHERE id=%s", (auth._token_hash(forged), principal.session_id))
    assert auth.current_user(forged) is None
    with postgres.connect(config) as conn:
        conn.execute("UPDATE sessions SET token_hash=%s WHERE id=%s", (auth._token_hash(token), principal.session_id))
    assert auth.logout(token)
    assert auth.session_for_id(principal.session_id) is None
    assert auth.current_user(token) is None
    assert not auth.logout(token)
    other, _ = auth.login(email, password)
    now[0] = expires
    assert auth.current_user(other) is None


def test_legacy_sessions_only_survive_migration_window(auth_case):
    config, auth, now, email, password, owner = auth_case
    old = secrets.token_urlsafe(32)
    with postgres.connect(config) as conn:
        applied = conn.execute("SELECT applied_at FROM schema_migrations WHERE version=6").fetchone()[0]
        conn.execute("INSERT INTO sessions (user_id, token_hash, created_at, expires_at) VALUES (%s,%s,%s,%s)",
                     (owner, auth._token_hash(old), applied - timedelta(hours=1), applied + timedelta(days=2)))
    now[0] = applied + timedelta(hours=1)
    assert auth.current_user(old) == owner
    now[0] = applied + timedelta(hours=24)
    assert auth.current_user(old) is None
    now[0] = applied + timedelta(hours=1)
    late = secrets.token_urlsafe(32)
    with postgres.connect(config) as conn:
        conn.execute("INSERT INTO sessions (user_id, token_hash, created_at, expires_at) VALUES (%s,%s,%s,%s)",
                     (owner, auth._token_hash(late), applied + timedelta(minutes=1), applied + timedelta(days=1)))
    assert auth.current_user(late) is None
    with postgres.connect(config) as conn:
        conn.execute("UPDATE sessions SET token_kind='jwt' WHERE token_hash=%s", (auth._token_hash(old),))
    assert auth.current_user(old) is None


def test_rate_limit_is_atomic_across_service_instances_and_commits_failures(auth_case):
    config, auth, now, email, password, owner = auth_case
    another = AuthService(config, clock=lambda: now[0])

    def attempt(index):
        try:
            (auth if index % 2 else another).login(email.upper(), "incorrect", ip=f"ip-{index}")
        except AuthError as exc:
            return exc.status_code
        raise AssertionError("Invalid password accepted")

    with ThreadPoolExecutor(max_workers=12) as pool:
        statuses = list(pool.map(attempt, range(12)))
    assert statuses.count(401) == 10
    assert statuses.count(429) == 2
    with postgres.connect(config) as conn:
        assert conn.execute("SELECT attempts FROM login_rate_limits WHERE key_hash=%s",
                            (auth._token_hash("email:" + email),)).fetchone() == (12,)
        rows = conn.execute("SELECT event_type, details FROM audit_events").fetchall()
    assert sum(row[0] == "auth.login_failed" for row in rows) == 10
    assert sum(row[0] == "auth.login_limited" for row in rows) == 2
    assert password not in str(rows) and "incorrect" not in str(rows) and email not in str(rows)
    now[0] += timedelta(minutes=15)
    assert another.login(email, password)[0]


def test_ip_limit_survives_email_rotation(auth_case):
    config, auth, now, *_ = auth_case
    with postgres.connect(config) as conn:
        conn.execute("INSERT INTO login_rate_limits (key_hash, attempts, window_started_at) VALUES (%s,50,%s)",
                     (auth._token_hash("ip:shared"), now[0]))
    with pytest.raises(AuthError) as caught:
        auth.login("other@example.invalid", "invalid", ip="shared")
    assert caught.value.status_code == 429


@pytest.mark.parametrize("password", ["old-password", "á" * 40])
def test_old_argon2_password_migrates_only_if_bcrypt_can_preserve_it(auth_case, password):
    config, auth, now, email, _, owner = auth_case
    old_hash = PasswordHash.recommended().hash(password)
    with postgres.connect(config) as conn:
        conn.execute("UPDATE users SET password_hash=%s WHERE id=%s", (old_hash, owner))
    with pytest.raises(AuthError):
        auth.login(email, "incorrect")
    with postgres.connect(config) as conn:
        assert conn.execute("SELECT password_hash FROM users WHERE id=%s", (owner,)).fetchone() == (old_hash,)
    auth.login(email, password)
    with postgres.connect(config) as conn:
        updated = conn.execute("SELECT password_hash FROM users WHERE id=%s", (owner,)).fetchone()[0]
    assert updated == old_hash if len(password.encode()) > 72 else updated.startswith("$2b$")
