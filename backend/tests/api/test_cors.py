from datetime import UTC, datetime
from unittest.mock import Mock

from fastapi.testclient import TestClient

from backend.app.api.app import create_app


def test_allows_the_configured_frontend_origin_to_request_the_api() -> None:
    app = create_app(
        repository=Mock(),
        readiness_check=lambda: True,
        clock=lambda: datetime(2026, 9, 9, tzinfo=UTC),
        cors_origins=("http://localhost:5173",),
    )

    response = TestClient(app).options(
        "/api/v1/monitoring/summary",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
