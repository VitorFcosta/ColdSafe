from datetime import UTC, datetime
from unittest.mock import Mock

import yaml
from pathlib import Path

from backend.app.api.app import create_app
from backend.app.api.auth import AuthService
from backend.app.api.catalog import CatalogService
from backend.app.config.settings import RuntimeSettings
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
        "401",
        "404",
        "422",
        "500",
        "503",
    }
    assert set(runtime_paths["/api/v1/readings"]["get"]["responses"]) == {
        "200",
        "401",
        "404",
        "422",
        "500",
        "503",
    }
    assert set(runtime_paths["/health/live"]["get"]["responses"]) == {"200"}
    assert set(runtime_paths["/health/ready"]["get"]["responses"]) == {"200", "503"}


def test_static_contract_includes_every_runtime_path() -> None:
    settings = RuntimeSettings.model_construct()
    application = create_app(
        repository=Mock(), readiness_check=lambda: True,
        auth=AuthService(settings), catalog=CatalogService(settings),
    )
    static = yaml.safe_load(
        (Path(__file__).resolve().parents[3] / "contracts" / "openapi.yaml").read_text()
    )
    runtime = application.openapi()

    assert set(static["paths"]) == set(runtime["paths"])
    for path in runtime["paths"]:
        assert set(static["paths"][path]) == set(runtime["paths"][path])
        for method in runtime["paths"][path]:
            assert set(static["paths"][path][method]["responses"]) == set(
                runtime["paths"][path][method]["responses"]
            )
            if "422" in runtime["paths"][path][method]["responses"] and path.startswith("/api/v1/"):
                expected = runtime["paths"][path][method]["responses"]["422"]
                actual = static["paths"][path][method]["responses"]["422"]
                if "content" in expected and "content" in actual:
                    assert actual["content"]["application/json"]["schema"] == expected["content"]["application/json"]["schema"]
