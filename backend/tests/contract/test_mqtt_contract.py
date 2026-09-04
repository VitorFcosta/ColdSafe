import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CONTRACTS_ROOT = REPOSITORY_ROOT / "contracts"
SCHEMA_PATH = CONTRACTS_ROOT / "telemetry.schema.json"
VALID_EXAMPLE_PATH = CONTRACTS_ROOT / "examples" / "telemetry.valid.json"
INVALID_EXAMPLES_PATH = CONTRACTS_ROOT / "examples" / "telemetry.invalid.json"


def load_json(path: Path):
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def test_telemetry_schema_is_valid_draft_2020_12():
    schema = load_json(SCHEMA_PATH)

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    Draft202012Validator.check_schema(schema)


def test_valid_telemetry_example_matches_schema():
    schema = load_json(SCHEMA_PATH)
    example = load_json(VALID_EXAMPLE_PATH)

    Draft202012Validator(schema).validate(example)


def invalid_examples():
    if not INVALID_EXAMPLES_PATH.exists():
        return []

    return load_json(INVALID_EXAMPLES_PATH)


@pytest.mark.parametrize(
    "case",
    invalid_examples(),
    ids=lambda case: case["name"],
)
def test_invalid_telemetry_examples_are_rejected(case):
    schema = load_json(SCHEMA_PATH)
    errors = list(Draft202012Validator(schema).iter_errors(case["payload"]))

    assert errors, f"O caso inválido '{case['name']}' foi aceito pelo contrato."


def test_invalid_fixture_covers_at_least_six_cases():
    assert len(invalid_examples()) >= 6
