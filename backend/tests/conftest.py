import secrets

import pytest


@pytest.fixture(autouse=True)
def private_test_jwt_key(monkeypatch):
    """Tests get a private key; production settings still require configuration."""
    monkeypatch.setenv("AUTH_JWT_SECRET", secrets.token_urlsafe(48))
