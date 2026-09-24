from __future__ import annotations

import re
import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Annotated, Literal
from uuid import UUID, uuid4

import psycopg
from fastapi import APIRouter, Depends, FastAPI
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import Field, SecretStr, field_validator
from pwdlib import PasswordHash

from backend.app.api.schemas import ApiModel, ErrorResponse, SuccessMeta
from backend.app.config.settings import RuntimeSettings
from backend.app.repositories.postgres import connect


SESSION_TTL = timedelta(hours=24)
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


class AuthError(Exception):
    def __init__(self, code: str, message: str, status_code: int):
        self.code = code
        self.message = message
        self.status_code = status_code


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
        self._passwords = PasswordHash.recommended()
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
                          responses={401: {"model": ErrorResponse}})
        def login(payload: LoginPayload) -> LoginResponse:
            token, expires_at = self.login(payload.email, payload.password.get_secret_value())
            return LoginResponse(data=LoginData(token=token, expires_at=expires_at))

        @self.router.post("/logout", response_model=LogoutResponse,
                          responses={401: {"model": ErrorResponse}})
        def logout(
            credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
        ) -> LogoutResponse:
            if credentials is None or not self.logout(credentials.credentials):
                raise _unauthorized()
            return LogoutResponse()

    def register(self, email: str, password: str) -> UUID:
        password_hash = self._passwords.hash(password)
        try:
            with connect(self._settings) as connection:
                row = connection.execute(
                    "INSERT INTO users (email, password_hash) VALUES (%s, %s) RETURNING id",
                    (email, password_hash),
                ).fetchone()
        except psycopg.errors.UniqueViolation as exc:
            raise AuthError("EMAIL_ALREADY_REGISTERED", "Este email já está cadastrado.", 409) from exc
        return row[0]

    def login(self, email: str, password: str) -> tuple[str, datetime]:
        with connect(self._settings) as connection:
            row = connection.execute(
                "SELECT id, password_hash FROM users WHERE lower(email) = lower(%s)",
                (email,),
            ).fetchone()
        if row is None or not self._passwords.verify(password, row[1]):
            raise AuthError("INVALID_CREDENTIALS", "Email ou senha inválidos.", 401)
        token = secrets.token_urlsafe(32)
        now = self._clock()
        expires_at = now + SESSION_TTL
        with connect(self._settings) as connection:
            connection.execute(
                "INSERT INTO sessions (user_id, token_hash, created_at, expires_at) "
                "VALUES (%s, %s, %s, %s)",
                (row[0], self._token_hash(token), now, expires_at),
            )
        return token, expires_at

    def current_user(self, token: str) -> UUID | None:
        if not token:
            return None
        with connect(self._settings) as connection:
            row = connection.execute(
                "SELECT user_id FROM sessions WHERE token_hash = %s "
                "AND expires_at > %s AND revoked_at IS NULL",
                (self._token_hash(token), self._clock()),
            ).fetchone()
        return row[0] if row else None

    def logout(self, token: str) -> bool:
        if not token:
            return False
        now = self._clock()
        with connect(self._settings) as connection:
            row = connection.execute(
                "UPDATE sessions SET revoked_at = %s WHERE token_hash = %s "
                "AND expires_at > %s AND revoked_at IS NULL RETURNING user_id",
                (now, self._token_hash(token), now),
            ).fetchone()
        return row is not None

    def require_user(
        self,
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    ) -> UUID:
        user_id = self.current_user(credentials.credentials) if credentials else None
        if user_id is None:
            raise _unauthorized()
        return user_id

    @staticmethod
    def install_exception_handlers(app: FastAPI) -> None:
        @app.exception_handler(AuthError)
        def auth_error_handler(_request, exc: AuthError) -> JSONResponse:
            return JSONResponse(
                status_code=exc.status_code,
                content={
                    "success": False,
                    "error": {"code": exc.code, "message": exc.message},
                    "meta": {"request_id": str(uuid4())},
                },
            )

    @staticmethod
    def _token_hash(token: str) -> str:
        return sha256(token.encode("utf-8")).hexdigest()
