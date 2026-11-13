from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import jwt


ISSUER = "coldsafe"
AUDIENCE = "coldsafe-api"


@dataclass(frozen=True)
class SessionPrincipal:
    session_id: UUID
    user_id: UUID
    email: str
    role: str
    expires_at: datetime


def issue_token(key: str, user_id: UUID, session_id: UUID,
                issued_at: datetime, expires_at: datetime) -> str:
    return jwt.encode({
        "sub": str(user_id), "jti": str(session_id), "iss": ISSUER, "aud": AUDIENCE,
        "iat": int(issued_at.timestamp()), "nbf": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
    }, key, algorithm="HS256")


def verify_token(token: str, key: str, now: datetime) -> dict | None:
    try:
        claims = jwt.decode(
            token, key, algorithms=["HS256"], issuer=ISSUER, audience=AUDIENCE,
            options={"require": ["sub", "jti", "iat", "nbf", "exp"],
                     "verify_iat": False, "verify_nbf": False, "verify_exp": False,
                     "strict_aud": True},
        )
        # Signature/issuer/audience are library-checked; time uses the same clock as the ledger.
        if any(type(claims[name]) is not int for name in ("iat", "nbf", "exp")):
            return None
        if not claims["iat"] <= claims["nbf"] <= now.timestamp() < claims["exp"]:
            return None
        UUID(claims["sub"])
        UUID(claims["jti"])
        return claims
    except (jwt.InvalidTokenError, ValueError, TypeError, AttributeError):
        return None
