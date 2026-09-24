import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker


CONTRACTS = Path(__file__).resolve().parents[3] / "contracts"


def load_json(name: str):
    return json.loads((CONTRACTS / name).read_text(encoding="utf-8"))


SCHEMA = load_json("evolution.schema.json")
VALID = load_json("examples/evolution.valid.json")
INVALID = load_json("examples/evolution.invalid.json")


def validator(name: str):
    return Draft202012Validator(
        {**SCHEMA, "$ref": f"#/$defs/{name}"},
        format_checker=FormatChecker(),
    )


def test_evolution_schema_is_valid():
    Draft202012Validator.check_schema(SCHEMA)


@pytest.mark.parametrize("case", VALID, ids=lambda case: case["name"])
def test_valid_evolution_examples(case):
    validator(case["schema"]).validate(case["payload"])


@pytest.mark.parametrize("case", INVALID, ids=lambda case: case["name"])
def test_invalid_evolution_examples(case):
    assert list(validator(case["schema"]).iter_errors(case["payload"]))


def test_mqtt_examples_use_device_scoped_topics():
    for case in VALID:
        if "topic" not in case:
            continue
        assert case["topic"] == (
            f"coldsafe/v2/devices/{case['payload']['device_id']}/"
            f"{'acks' if case['schema'] == 'ack' else 'commands' if case['schema'] == 'command' else 'telemetry'}"
        )


def test_v1_telemetry_remains_separately_valid_and_has_no_light():
    legacy = load_json("examples/telemetry.valid.json")
    Draft202012Validator(load_json("telemetry.schema.json")).validate(legacy)
    assert "light_percent" not in legacy
    assert list(validator("telemetry").iter_errors(legacy))


def test_historical_projection_uses_null_for_legacy_light():
    historical = next(case["payload"] for case in VALID if case["name"] == "historical-v1-reading")
    assert historical["light_percent"] is None
    validator("historical_reading").validate(historical)
