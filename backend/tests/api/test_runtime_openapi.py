from datetime import UTC, datetime
from unittest.mock import Mock

from backend.app.api.app import create_app
from backend.tests.contract.test_openapi_contract import EXPECTED_GET_PATHS


def test_runtime_api_exposes_only_the_versioned_contract_paths() -> None:
    application = create_app(
        repository=Mock(),
        readiness_check=lambda: True,
        clock=lambda: datetime(2026, 9, 6, tzinfo=UTC),
    )
    runtime_specification = application.openapi()

    assert set(runtime_specification["paths"]) == EXPECTED_GET_PATHS
    assert all(
        set(runtime_specification["paths"][path]) == {"get"}
        for path in EXPECTED_GET_PATHS
    )


def test_runtime_status_codes_match_the_canonical_contract() -> None:
    application = create_app(repository=Mock(), readiness_check=lambda: True)
    runtime_paths = application.openapi()["paths"]

    assert set(runtime_paths["/api/v1/monitoring/summary"]["get"]["responses"]) == {
        "200",
        "500",
        "503",
    }
    assert set(runtime_paths["/api/v1/readings"]["get"]["responses"]) == {
        "200",
        "404",
        "422",
        "500",
        "503",
    }
    assert set(runtime_paths["/health/live"]["get"]["responses"]) == {"200"}
    assert set(runtime_paths["/health/ready"]["get"]["responses"]) == {"200", "503"}
