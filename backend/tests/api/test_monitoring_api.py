from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

from fastapi.testclient import TestClient

from backend.app.api.app import create_app
from backend.app.errors import DependencyUnavailableError
from backend.app.domain.reading_classification import ReadingStatus
from backend.app.repositories.influxdb import StoredReading


NOW = datetime(2026, 9, 6, 21, 0, tzinfo=UTC)
DEVICE_ID = "esp32-lab-01"


def make_client(repository: Mock) -> TestClient:
    return TestClient(
        create_app(
            repository=repository,
            readiness_check=lambda: True,
            clock=lambda: NOW,
        ),
        raise_server_exceptions=False,
    )


def reading(*, received_at: datetime, temperature_c: float = 5.4) -> StoredReading:
    return StoredReading(
        schema_version=1,
        device_id=DEVICE_ID,
        temperature_c=temperature_c,
        humidity_percent=62.1,
        status=ReadingStatus.NORMAL,
        received_at=received_at,
    )


def test_summary_returns_no_data_as_valid_domain_state() -> None:
    repository = Mock()
    repository.get_latest.return_value = None

    response = make_client(repository).get("/api/v1/monitoring/summary")

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "data": {
            "environment": {
                "id": "lab-cold-room-01",
                "name": "Laboratório Refrigerado",
            },
            "device": {"id": DEVICE_ID},
            "reading": None,
            "status": "no_data",
            "freshness": None,
            "thresholds": {
                "min_c": 2.0,
                "max_c": 8.0,
                "attention_margin_c": 0.5,
            },
        },
        "meta": {"schema_version": 1},
    }


def test_summary_recalculates_freshness_instead_of_trusting_stored_status() -> None:
    repository = Mock()
    repository.get_latest.return_value = reading(received_at=NOW - timedelta(seconds=31))

    response = make_client(repository).get("/api/v1/monitoring/summary")

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "stale"
    assert response.json()["data"]["freshness"] == {
        "is_stale": True,
        "age_seconds": 31.0,
    }


def test_history_uses_default_period_and_limit_and_returns_metadata() -> None:
    repository = Mock()
    repository.list_history.return_value = (
        reading(received_at=NOW - timedelta(minutes=2), temperature_c=5.1),
        reading(received_at=NOW - timedelta(minutes=1), temperature_c=7.8),
    )

    response = make_client(repository).get(
        "/api/v1/readings", params={"device_id": DEVICE_ID}
    )

    assert response.status_code == 200
    repository.list_history.assert_called_once_with(
        device_id=DEVICE_ID,
        start=NOW - timedelta(hours=1),
        end=NOW,
        limit=300,
    )
    body = response.json()
    assert body["meta"] == {
        "schema_version": 1,
        "device_id": DEVICE_ID,
        "start": "2026-09-06T20:00:00Z",
        "end": "2026-09-06T21:00:00Z",
        "count": 2,
        "limit": 300,
    }
    assert [item["temperature_c"] for item in body["data"]["readings"]] == [
        5.1,
        7.8,
    ]


def test_history_rejects_unknown_device_with_contract_error() -> None:
    repository = Mock()

    response = make_client(repository).get(
        "/api/v1/readings", params={"device_id": "unknown-device"}
    )

    assert response.status_code == 404
    assert response.json()["error"] == {
        "code": "DEVICE_NOT_FOUND",
        "message": "O dispositivo informado não foi encontrado.",
    }
    repository.list_history.assert_not_called()


def test_history_validation_uses_the_contract_error_envelope() -> None:
    repository = Mock()

    response = make_client(repository).get(
        "/api/v1/readings",
        params={"device_id": DEVICE_ID, "period": "2h", "limit": 0},
    )

    assert response.status_code == 422
    assert response.json()["error"] == {
        "code": "VALIDATION_ERROR",
        "message": "Um ou mais parâmetros são inválidos.",
    }


def test_repository_unavailability_is_exposed_without_internal_details() -> None:
    repository = Mock()
    repository.get_latest.side_effect = DependencyUnavailableError(
        "http://influxdb:8086 failed with token secret-value"
    )

    response = make_client(repository).get("/api/v1/monitoring/summary")

    assert response.status_code == 503
    assert response.json()["error"] == {
        "code": "DEPENDENCY_UNAVAILABLE",
        "message": "Não foi possível consultar as leituras agora.",
    }
    assert "secret-value" not in response.text


def test_unexpected_failure_uses_generic_internal_error() -> None:
    repository = Mock()
    repository.get_latest.side_effect = RuntimeError("sensitive implementation detail")

    response = make_client(repository).get("/api/v1/monitoring/summary")

    assert response.status_code == 500
    assert response.json()["error"] == {
        "code": "INTERNAL_ERROR",
        "message": "Ocorreu um erro interno.",
    }
    assert "sensitive implementation detail" not in response.text
