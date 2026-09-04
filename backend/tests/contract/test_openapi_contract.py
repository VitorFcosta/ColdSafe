from pathlib import Path

import yaml
from jsonschema import Draft202012Validator
from openapi_spec_validator import validate


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
OPENAPI_PATH = REPOSITORY_ROOT / "contracts" / "openapi.yaml"
EXPECTED_GET_PATHS = {
    "/api/v1/monitoring/summary",
    "/api/v1/readings",
    "/health/live",
    "/health/ready",
}


def load_openapi():
    with OPENAPI_PATH.open(encoding="utf-8") as file:
        return yaml.safe_load(file)


def find_references(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "$ref":
                yield child
            else:
                yield from find_references(child)
    elif isinstance(value, list):
        for child in value:
            yield from find_references(child)


def validator_for_component(specification, component_name):
    root_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "components": {"schemas": specification["components"]["schemas"]},
        "$ref": f"#/components/schemas/{component_name}",
    }
    return Draft202012Validator(root_schema)


def test_openapi_document_is_valid_version_3_1():
    specification = load_openapi()

    assert specification["openapi"] == "3.1.0"
    validate(specification)


def test_openapi_exposes_the_four_planned_get_endpoints():
    specification = load_openapi()

    assert EXPECTED_GET_PATHS == set(specification["paths"])
    assert all("get" in specification["paths"][path] for path in EXPECTED_GET_PATHS)


def test_monitoring_summary_example_matches_contract():
    specification = load_openapi()
    response = {
        "success": True,
        "data": {
            "environment": {
                "id": "lab-cold-room-01",
                "name": "Laboratório Refrigerado",
            },
            "device": {"id": "esp32-lab-01"},
            "reading": {
                "temperature_c": 5.4,
                "humidity_percent": 62.1,
                "received_at": "2026-09-03T12:00:00Z",
            },
            "status": "normal",
            "freshness": {"is_stale": False, "age_seconds": 3},
            "thresholds": {"min_c": 2, "max_c": 8, "attention_margin_c": 0.5},
        },
        "meta": {"schema_version": 1},
    }

    validator_for_component(specification, "MonitoringSummaryResponse").validate(response)


def test_reading_history_example_matches_contract():
    specification = load_openapi()
    response = {
        "success": True,
        "data": {
            "readings": [
                {
                    "temperature_c": 5.4,
                    "humidity_percent": 62.1,
                    "received_at": "2026-09-03T12:00:00Z",
                    "status": "normal",
                }
            ]
        },
        "meta": {
            "schema_version": 1,
            "device_id": "esp32-lab-01",
            "start": "2026-09-03T11:00:00Z",
            "end": "2026-09-03T12:00:00Z",
            "count": 1,
            "limit": 300,
        },
    }

    validator_for_component(specification, "ReadingHistoryResponse").validate(response)


def test_reading_status_does_not_mix_in_interface_errors():
    specification = load_openapi()
    statuses = specification["components"]["schemas"]["ReadingStatus"]["enum"]

    assert statuses == ["normal", "attention", "critical", "no_data", "stale"]
    assert "service_error" not in statuses


def test_error_contract_exposes_the_planned_codes():
    specification = load_openapi()
    error_codes = specification["components"]["schemas"]["ErrorCode"]["enum"]

    assert error_codes == [
        "VALIDATION_ERROR",
        "DEVICE_NOT_FOUND",
        "DEPENDENCY_UNAVAILABLE",
        "INTERNAL_ERROR",
    ]


def test_openapi_uses_only_internal_component_references():
    references = list(find_references(load_openapi()))

    assert references
    assert all(reference.startswith("#/components/") for reference in references)
