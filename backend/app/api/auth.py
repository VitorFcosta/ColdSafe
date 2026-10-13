from __future__ import annotations

import re
import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from math import ceil
from typing import Annotated, Literal
from uuid import UUID, uuid4

import psycopg
from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import Field, SecretStr, field_validator
from pwdlib import PasswordHash, exceptions as password_errors
from pwdlib.hashers.argon2 import Argon2Hasher
from pwdlib.hashers.bcrypt import BcryptHasher
from psycopg.types.json import Jsonb

from backend.app.api.schemas import ApiModel, ErrorResponse, SuccessMeta
from backend.app.config.settings import RuntimeSettings
from backend.app.repositories.postgres import connect
from backend.app.security.tokens import SessionPrincipal, issue_token, verify_token


SESSION_TTL = timedelta(hours=24)
LOGIN_WINDOW = timedelta(minutes=15)
SESSION_COLUMNS = "s.id, s.user_id, u.email, u.role, s.expires_at, s.token_kind, s.created_at"
ACTIVE_SESSION = """s.expires_at > %s AND s.revoked_at IS NULL AND (
    s.token_kind = 'jwt' OR (s.token_kind = 'opaque' AND EXISTS (
        SELECT 1 FROM schema_migrations m WHERE m.version = 6
        AND s.created_at <= m.applied_at AND %s < m.applied_at + interval '24 hours')))
"""
_bearer = HTTPBearer(auto_error=False)


class LoginPayload(ApiModel):
    email: str = Field(min_length=3, max_length=254)
    password: SecretStr = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        email = value.strip().lower()
        if len(email) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            raise ValueError("invalid email")
        return email


class RegisterPayload(LoginPayload):
    password: SecretStr = Field(min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def bcrypt_byte_limit(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value().encode("utf-8")) > 72:
            raise ValueError("password must contain at most 72 UTF-8 bytes")
        return value


class RegisterData(ApiModel):
    user_id: UUID
    email: str


class RegisterResponse(ApiModel):
    success: Literal[True] = True
    data: RegisterData
    meta: SuccessMeta = SuccessMeta()


class LoginData(ApiModel):
    token: str
    token_type: Literal["Bearer"] = "Bearer"
    expires_at: datetime


class LoginResponse(ApiModel):
    success: Literal[True] = True
    data: LoginData
    meta: SuccessMeta = SuccessMeta()


class LogoutData(ApiModel):
    revoked: Literal[True] = True


class LogoutResponse(ApiModel):
    success: Literal[True] = True
    data: LogoutData = LogoutData()
    meta: SuccessMeta = SuccessMeta()


class MeData(ApiModel):
    user_id: UUID
    email: str
    role: Literal["viewer", "operator", "admin"]


class MeResponse(ApiModel):
    success: Literal[True] = True
    data: MeData
    meta: SuccessMeta = SuccessMeta()


class AuthError(Exception):
    def __init__(self, code: str, message: str, status_code: int, *, headers: dict | None = None):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.headers = headers


def _unauthorized() -> AuthError:
    return AuthError("UNAUTHORIZED", "Autenticação necessária ou sessão inválida.", 401)


class AuthService:
    def __init__(
        self,
        settings: RuntimeSettings,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        self._settings = settings
        self._clock = clock
        self._key = settings.auth_jwt_secret.get_secret_value()
        if len(self._key) < 32:
            raise ValueError("AUTH_JWT_SECRET must contain at least 32 characters")
        self._passwords = PasswordHash((BcryptHasher(), Argon2Hasher()))
        self._dummy_hash = self._passwords.hash(secrets.token_urlsafe(32))
        self.router = APIRouter(
            prefix="/api/v1/auth", tags=["Auth"],
            responses={422: {"model": ErrorResponse}},
        )

        @self.router.post(
            "/register", response_model=RegisterResponse, status_code=201,
            responses={409: {"model": ErrorResponse}},
        )
        def register(payload: RegisterPayload) -> RegisterResponse:
            user_id = self.register(payload.email, payload.password.get_secret_value())
            return RegisterResponse(data=RegisterData(user_id=user_id, email=payload.email))

        @self.router.post("/login", response_model=LoginResponse,
                          responses={401: {"model": ErrorResponse}, 429: {"model": ErrorResponse}})
        def login(payload: LoginPayload, request: Request) -> LoginResponse:
            token, expires_at = self.login(payload.email, payload.password.get_secret_value(),
                                           ip=request.client.host if request.client else "unknown")
            return LoginResponse(data=LoginData(token=token, expires_at=expires_at))

        @self.router.post("/logout", response_model=LogoutResponse,
                          responses={401: {"model": ErrorResponse}})
        def logout(
            credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
        ) -> LogoutResponse:
            if credentials is None or not self.logout(credentials.credentials):
                raise _unauthorized()
            return LogoutResponse()

        @self.router.get("/me", response_model=MeResponse,
                         responses={401: {"model": ErrorResponse}})
        def me(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]) -> MeResponse:
            principal = self._require_principal(credentials)
            return MeResponse(data=MeData(user_id=principal.user_id, email=principal.email, role=principal.role))

    def register(self, email: str, password: str) -> UUID:
        payload = RegisterPayload(email=email, password=password)
        password_hash = self._passwords.hash(payload.password.get_secret_value())
        try:
            with connect(self._settings) as connection:
                row = connection.execute(
                    "INSERT INTO users (email, password_hash) VALUES (%s, %s) RETURNING id",
                    (payload.email, password_hash),
                ).fetchone()
        except psycopg.errors.UniqueViolation as exc:
            raise AuthError("EMAIL_ALREADY_REGISTERED", "Este email já está cadastrado.", 409) from exc
        return row[0]

    def _audit(self, connection, event: str, user_id: UUID | None = None, **details) -> None:
        connection.execute(
            "INSERT INTO audit_events (actor_user_id, event_type, details, occurred_at) VALUES (%s, %s, %s, %s)",
            (user_id, event, Jsonb(details), self._clock()),
        )

    def _limit_login(self, email: str, ip: str) -> None:
        now = self._clock()
        keys = ((self._token_hash("email:" + email), 10), (self._token_hash("ip:" + ip), 50))
        retry_after = 0
        with connect(self._settings) as connection:
            # One transaction, same key order for every request; UPSERT serializes concurrent attempts.
            for key, limit in sorted(keys):
                count, started = connection.execute(
                    "INSERT INTO login_rate_limits (key_hash, attempts, window_started_at) VALUES (%s, 1, %s) "
                    "ON CONFLICT (key_hash) DO UPDATE SET "
                    "attempts = CASE WHEN EXCLUDED.window_started_at >= login_rate_limits.window_started_at "
                    "+ interval '15 minutes' THEN 1 ELSE login_rate_limits.attempts + 1 END, "
                    "window_started_at = CASE WHEN EXCLUDED.window_started_at >= login_rate_limits.window_started_at "
                    "+ interval '15 minutes' THEN EXCLUDED.window_started_at ELSE login_rate_limits.window_started_at END "
                    "RETURNING attempts, window_started_at", (key, now),
                ).fetchone()
                if count > limit:
                    retry_after = max(retry_after, ceil((started + LOGIN_WINDOW - now).total_seconds()))
            if retry_after:
                self._audit(connection, "auth.login_limited", email_hash=keys[0][0], ip_hash=keys[1][0])
        # Raising after commit keeps failures counted.
        if retry_after:
            raise AuthError("RATE_LIMITED", "Muitas tentativas de login. Tente novamente mais tarde.", 429,
                            headers={"Retry-After": str(max(1, retry_after))})

    def _verify_password(self, password: str, password_hash: str) -> tuple[bool, str | None]:
        try:
            if len(password.encode("utf-8")) > 72:
                return self._passwords.verify(password, password_hash), None
            return self._passwords.verify_and_update(password, password_hash)
        except (password_errors.PwdlibError, ValueError, TypeError):
            self._passwords.verify("invalid-password", self._dummy_hash)
            return False, None

    def login(self, email: str, password: str, *, ip: str = "unknown") -> tuple[str, datetime]:
        email = LoginPayload(email=email, password=password).email
        self._limit_login(email, ip)
        with connect(self._settings) as connection:
            row = connection.execute(
                "SELECT id, password_hash FROM users WHERE lower(email) = lower(%s)", (email,),
            ).fetchone()
        valid, replacement = self._verify_password(password, row[1] if row else self._dummy_hash)
        if row is None or not valid:
            with connect(self._settings) as connection:
                self._audit(connection, "auth.login_failed", row[0] if row else None,
                            email_hash=self._token_hash("email:" + email), ip_hash=self._token_hash("ip:" + ip))
            raise AuthError("INVALID_CREDENTIALS", "Email ou senha inválidos.", 401)
        now = self._clock().replace(microsecond=0)
        expires_at = now + SESSION_TTL
        session_id = uuid4()
        token = issue_token(self._key, row[0], session_id, now, expires_at)
        with connect(self._settings) as connection:
            if replacement:
                connection.execute("UPDATE users SET password_hash=%s WHERE id=%s AND password_hash=%s",
                                   (replacement, row[0], row[1]))
            connection.execute(
                "INSERT INTO sessions (id, user_id, token_hash, created_at, expires_at, token_kind) "
                "VALUES (%s, %s, %s, %s, %s, 'jwt')",
                (session_id, row[0], self._token_hash(token), now, expires_at),
            )
            self._audit(connection, "auth.login_succeeded", row[0])
        return token, expires_at

    def session_for_token(self, token: str) -> SessionPrincipal | None:
        if not token or len(token) > 4096:
            return None
        now = self._clock()
        claims = verify_token(token, self._key, now) if "." in token else None
        if "." in token and claims is None:
            return None
        with connect(self._settings) as connection:
            row = connection.execute(
                f"SELECT {SESSION_COLUMNS} FROM sessions s JOIN users u ON u.id=s.user_id "
                f"WHERE s.token_hash=%s AND {ACTIVE_SESSION}",
                (self._token_hash(token), now, now),
            ).fetchone()
        if row is None:
            return None
        if row[5] == "jwt":
            if claims is None or claims["sub"] != str(row[1]) or claims["jti"] != str(row[0]):
                return None
            if claims["iat"] != int(row[6].timestamp()) or claims["exp"] != int(row[4].timestamp()):
                return None
        elif claims is not None:
            return None
        return SessionPrincipal(*row[:5])

    def session_for_id(self, session_id: UUID) -> SessionPrincipal | None:
        now = self._clock()
        with connect(self._settings) as connection:
            row = connection.execute(
                f"SELECT {SESSION_COLUMNS} FROM sessions s JOIN users u ON u.id=s.user_id "
                f"WHERE s.id=%s AND {ACTIVE_SESSION}", (session_id, now, now),
            ).fetchone()
        return SessionPrincipal(*row[:5]) if row else None

    def current_user(self, token: str) -> UUID | None:
        principal = self.session_for_token(token)
        return principal.user_id if principal else None

    def logout(self, token: str) -> bool:
        principal = self.session_for_token(token)
        if principal is None:
            return False
        now = self._clock()
        with connect(self._settings) as connection:
            row = connection.execute(
                "UPDATE sessions SET revoked_at = %s WHERE token_hash = %s "
                "AND expires_at > %s AND revoked_at IS NULL RETURNING user_id",
                (now, self._token_hash(token), now),
            ).fetchone()
            if row:
                self._audit(connection, "auth.logout", row[0])
        return row is not None

    def create_ws_ticket(self, token: str, device_id: UUID) -> tuple[str, datetime]:
        principal = self.session_for_token(token)
        if principal is None:
            raise _unauthorized()
        now = self._clock()
        expires_at = min(now + timedelta(seconds=60), principal.expires_at)
        ticket = secrets.token_urlsafe(32)
        with connect(self._settings) as connection:
            row = connection.execute(
                "INSERT INTO websocket_tickets (token_hash, session_id, device_id, issued_at, expires_at) "
                "SELECT %s, s.id, d.id, %s, %s FROM sessions s "
                "JOIN devices d ON d.id=%s JOIN environments e ON e.id=d.environment_id "
                "JOIN users u ON u.id=s.user_id WHERE s.id=%s AND e.owner_user_id=s.user_id "
                f"AND d.is_active AND {ACTIVE_SESSION} RETURNING token_hash",
                (self._token_hash(ticket), now, expires_at, device_id, principal.session_id, now, now),
            ).fetchone()
            if row:
                self._audit(connection, "auth.ws_ticket_issued", principal.user_id, device_id=str(device_id))
        if not row:
            raise AuthError("FORBIDDEN", "Sem permissão para acessar este dispositivo.", 403)
        return ticket, expires_at

    def consume_ws_ticket(self, ticket: str, mqtt_device_id: str) -> SessionPrincipal | None:
        if not ticket or len(ticket) > 128:
            return None
        now = self._clock()
        with connect(self._settings) as connection:
            row = connection.execute(
                "UPDATE websocket_tickets t SET consumed_at=%s FROM sessions s, users u, devices d, environments e "
                "WHERE t.token_hash=%s AND t.consumed_at IS NULL AND t.expires_at>%s AND t.issued_at<=%s "
                "AND t.session_id=s.id AND u.id=s.user_id AND t.device_id=d.id "
                "AND d.mqtt_device_id=%s AND d.is_active AND e.id=d.environment_id "
                f"AND e.owner_user_id=s.user_id AND {ACTIVE_SESSION} "
                "RETURNING s.id, s.user_id, u.email, u.role, s.expires_at",
                (now, self._token_hash(ticket), now, now, mqtt_device_id, now, now),
            ).fetchone()
            if row:
                self._audit(connection, "auth.ws_ticket_consumed", row[1], device=mqtt_device_id)
        return SessionPrincipal(*row) if row else None

    def _require_principal(self, credentials) -> SessionPrincipal:
        principal = self.session_for_token(credentials.credentials) if credentials else None
        if principal is None:
            raise _unauthorized()
        return principal

    def require_user(
        self, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    ) -> UUID:
        return self._require_principal(credentials).user_id

    def require_operator(
        self, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    ) -> UUID:
        principal = self._require_principal(credentials)
        if principal.role not in ("operator", "admin"):
            raise AuthError("FORBIDDEN", "Permissão de operador necessária.", 403)
        return principal.user_id

    def require_admin(
        self, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    ) -> UUID:
        principal = self._require_principal(credentials)
        if principal.role != "admin":
            raise AuthError("FORBIDDEN", "Permissão de administrador necessária.", 403)
        return principal.user_id

    def change_role(self, actor: UUID, user_id: UUID, role: str) -> None:
        with connect(self._settings) as connection:
            roles = dict(connection.execute(
                "SELECT id, role FROM users WHERE id=ANY(%s) ORDER BY id FOR UPDATE",
                ([actor, user_id],),
            ).fetchall())
            if roles.get(actor) != "admin":
                raise AuthError("FORBIDDEN", "Permissão de administrador necessária.", 403)
            if user_id not in roles:
                raise AuthError("USER_NOT_FOUND", "O usuário informado não foi encontrado.", 404)
            connection.execute("UPDATE users SET role=%s WHERE id=%s", (role, user_id))
            self._audit(connection, "user_role_changed", actor,
                        target_user_id=str(user_id), before=roles[user_id], after=role)

    @staticmethod
    def install_exception_handlers(app: FastAPI) -> None:
        @app.exception_handler(AuthError)
        def auth_error_handler(_request, exc: AuthError) -> JSONResponse:
            return JSONResponse(
                status_code=exc.status_code,
                headers=exc.headers,
                content={
                    "success": False,
                    "error": {"code": exc.code, "message": exc.message},
                    "meta": {"request_id": str(uuid4())},
                },
            )

    @staticmethod
    def _token_hash(token: str) -> str:
        return sha256(token.encode("utf-8")).hexdigest()
