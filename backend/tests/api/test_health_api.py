from unittest.mock import Mock

from fastapi.testclient import TestClient

from backend.app.api.app import create_app


def make_client(readiness_check: Mock) -> TestClient:
    return TestClient(
        create_app(repository=Mock(), readiness_check=readiness_check),
        raise_server_exceptions=False,
    )


def test_liveness_only_proves_that_the_process_responds() -> None:
    readiness_check = Mock(return_value=False)

    response = make_client(readiness_check).get("/health/live")

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "data": {"status": "ok"},
        "meta": {"schema_version": 1},
    }
    readiness_check.assert_not_called()


def test_readiness_returns_ok_when_dependencies_are_ready() -> None:
    readiness_check = Mock(return_value=True)

    response = make_client(readiness_check).get("/health/ready")

    assert response.status_code == 200
    assert response.json()["data"] == {"status": "ok"}


def test_readiness_returns_503_when_dependency_is_unavailable() -> None:
    readiness_check = Mock(return_value=False)

    response = make_client(readiness_check).get("/health/ready")

    assert response.status_code == 503
    assert response.json()["error"] == {
        "code": "DEPENDENCY_UNAVAILABLE",
        "message": "Não foi possível consultar as leituras agora.",
    }
