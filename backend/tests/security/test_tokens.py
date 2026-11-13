import secrets
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest

from backend.app.security.tokens import issue_token, verify_token


NOW = datetime(2026, 10, 13, 12, tzinfo=UTC)


@pytest.fixture
def token_case():
    key = secrets.token_urlsafe(64)
    user, session = uuid4(), uuid4()
    return key, issue_token(key, user, session, NOW, NOW + timedelta(hours=24))


def test_jwt_round_trip_and_expiration_use_injected_clock(token_case):
    key, token = token_case
    assert verify_token(token, key, NOW)
    assert verify_token(token, key, NOW - timedelta(seconds=1)) is None
    assert verify_token(token, key, NOW + timedelta(hours=24)) is None
    assert verify_token(token, secrets.token_urlsafe(32), NOW) is None
    assert verify_token("broken", key, NOW) is None


@pytest.mark.parametrize("changes", [
    {"iss": "other"}, {"aud": "other"}, {"aud": ["coldsafe-api", "other"]},
    {"sub": "not-a-uuid"}, {"jti": "not-a-uuid"}, {"exp": None},
    {"iat": True}, {"nbf": "1"}, {"exp": 10.5},
    {"iat": int(NOW.timestamp()) + 1}, {"nbf": int(NOW.timestamp()) + 1},
    {"exp": int(NOW.timestamp())},
])
def test_signed_invalid_claims_are_rejected(token_case, changes):
    key, token = token_case
    claims = jwt.decode(token, options={"verify_signature": False})
    mutated = jwt.encode({**claims, **changes}, key, algorithm="HS256")
    assert verify_token(mutated, key, NOW) is None


@pytest.mark.parametrize("claim", ["sub", "jti", "iat", "nbf", "exp", "iss", "aud"])
def test_required_claims_cannot_be_omitted(token_case, claim):
    key, token = token_case
    claims = jwt.decode(token, options={"verify_signature": False})
    mutated = jwt.encode({k: v for k, v in claims.items() if k != claim}, key, algorithm="HS256")
    assert verify_token(mutated, key, NOW) is None


@pytest.mark.parametrize("algorithm", ["none", "HS384", "HS512"])
def test_only_hs256_is_accepted(token_case, algorithm):
    key, token = token_case
    claims = jwt.decode(token, options={"verify_signature": False})
    mutated = jwt.encode(claims, "" if algorithm == "none" else key, algorithm=algorithm)
    assert verify_token(mutated, key, NOW) is None
