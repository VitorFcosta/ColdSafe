"""Executable v3 contract fixtures; these checks do not change the application."""

from copy import deepcopy
from datetime import datetime, timedelta
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker


CONTRACTS = Path(__file__).resolve().parents[3] / "contracts"
SCOPE = ("device_id", "device_record_id", "environment_id")
ROLES = (
    "ambient_temperature", "humidity", "light", "vibration",
    "motor_current", "motor_temperature",
)


def load_json(name):
    return json.loads((CONTRACTS / name).read_text(encoding="utf-8"))


@pytest.fixture
def contract():
    return {
        "schema": load_json("aiot.schema.json"),
        "valid": load_json("examples/aiot.valid.json"),
        "invalid": load_json("examples/aiot.invalid.json"),
        "context": load_json("examples/aiot.context.json"),
    }


def validator(contract, definition):
    return Draft202012Validator(
        {**contract["schema"], "$ref": f"#/$defs/{definition}"},
        format_checker=FormatChecker(),
    )


def resolve_reference(case, examples, key="reference"):
    reference = case.get(key)
    if isinstance(reference, str):
        reference = next(item for item in examples if item["name"] == reference)
    if reference is None:
        return None
    return reference.get("payload", reference)


def check_binding(case):
    payload = case["payload"]
    if case["schema"] == "offline_row":
        assert "topic" not in case and "routing_key" not in case
        return
    event_type = payload["type"]
    if "topic" in case:
        suffix = {"telemetry": "telemetry", "command": "commands", "ack": "acks"}
        assert event_type in suffix
        assert case["topic"] == (
            f"coldsafe/v3/devices/{payload['device_id']}/{suffix[event_type]}"
        )
    if "routing_key" in case:
        if event_type == "processing_error":
            identity = payload["correlation_id"]
        elif event_type.startswith("job_"):
            identity = payload["data"]["job_id"]
        elif event_type.startswith("model_"):
            identity = payload["data"]["model_id"]
        else:
            identity = payload["device_record_id"]
        assert case["routing_key"] == f"v3.{event_type}.{identity}"


def check_reference_scope(payload, reference):
    assert all(payload[key] == reference[key] for key in SCOPE)
    equipment_id = reference["data"].get("equipment_id")
    if equipment_id is None:
        equipment_id = reference["data"].get("equipment", {}).get("equipment_id")
    if "equipment_id" in payload["data"] and equipment_id is not None:
        assert payload["data"]["equipment_id"] == equipment_id


def check_command_semantics(payload, reference, ack=None):
    data = payload["data"]
    assert payload["correlation_id"] == data["command_id"]
    if payload["type"] == "command_status" and data["status"] == "confirmed":
        assert data["desired_state"] == data["confirmed_state"]
    if payload["type"] == "command":
        assert timestamp(data["deadline_at"]) == timestamp(payload["occurred_at"]) + timedelta(seconds=30)
    if payload["type"] in {"ack", "command_status"}:
        assert reference is not None and reference["type"] == "command"
        check_reference_scope(payload, reference)
        assert data["command_id"] == reference["data"]["command_id"]
        assert data["actuator"] == reference["data"]["actuator"]
        assert data["actuator_id"] == reference["data"]["actuator_id"]
        if payload["type"] == "command_status":
            assert data["desired_state"] == reference["data"]["desired_state"]
            if data["status"] == "confirmed":
                assert ack is not None and ack["type"] == "ack"
                check_command_semantics(ack, reference)
                assert ack["data"]["result"] == "applied"
                assert ack["data"]["applied_state"] == data["desired_state"]
                assert ack["received_at"] is not None
                assert timestamp(reference["received_at"]) <= timestamp(ack["received_at"]) <= timestamp(reference["data"]["deadline_at"])
                assert timestamp(payload["occurred_at"]) >= timestamp(ack["received_at"])


def check_job_semantics(payload, reference):
    data = payload["data"]
    assert payload["correlation_id"] == data["job_id"]
    if payload["type"] == "job_progress":
        assert reference is not None
        check_reference_scope(payload, reference)
        assert data["job_id"] == reference["data"]["job_id"]
        assert data["job_type"] == reference["data"]["job_type"]
        assert data["completed_units"] <= data["total_units"]
        if data["job_type"] == "training":
            assert data["total_units"] == 2
        if data["status"] == "failed":
            assert data["error_code"] == {
                "generation": "GENERATION_FAILED", "training": "TRAINING_FAILED",
            }[data["job_type"]]
        if data["error_code"] is not None:
            expected = f"{data['job_type'].upper()}_FAILED"
            assert data["error_code"] == expected
        if data["status"] == "queued":
            assert data["completed_units"] == 0
        if data["status"] == "completed":
            assert data["completed_units"] == data["total_units"]
            assert data["result_id"] is not None


def timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def check_source_semantics(payload, reference):
    assert reference is not None
    check_reference_scope(payload, reference)
    assert payload["correlation_id"] == reference["correlation_id"]
    assert payload["data"]["source_event_id"] == reference["event_id"]
    if payload["type"] in {"prediction", "telemetry_persisted"}:
        assert reference["type"] == "telemetry" and reference["received_at"] is not None
        assert payload["data"]["input_received_at"] == reference["received_at"]
        age = (timestamp(payload["occurred_at"]) - timestamp(reference["received_at"])).total_seconds()
        assert age >= 0
    if payload["type"] == "prediction":
        if payload["data"]["status"] == "available":
            assert age <= 30
        if payload["data"]["reason"] == "stale_input":
            assert age > 30
    if payload["type"] == "alert":
        if payload["data"]["kind"].startswith("predictive_"):
            assert reference["type"] == "prediction"
            assert reference["data"]["status"] == "available"
            age = (timestamp(payload["occurred_at"]) - timestamp(reference["data"]["input_received_at"])).total_seconds()
            assert 0 <= age <= 30
        else:
            assert reference["type"] == "telemetry"


def check_model_semantics(payload, reference):
    data = payload["data"]
    assert payload["correlation_id"] == data["activation_id"]
    if payload["type"] == "model_status":
        assert reference is not None
        check_reference_scope(payload, reference)
        assert data["activation_id"] == reference["data"]["activation_id"]
        assert data["model_id"] == reference["data"]["model_id"]
        assert data["model_version"] == reference["data"]["model_version"]
        assert data["features_version"] == reference["data"]["features_version"]
        if data["status"] == "active":
            assert data["model_id"] == data["active_model_id"]
        if data["status"] in {"ready", "loading", "failed"}:
            assert data["active_model_id"] == reference["data"]["previous_active_model_id"]


def check_freshness(payload):
    data = payload["data"]
    if data["state"] == "no_data":
        assert data["last_received_at"] is None and data["age_seconds"] is None
        return
    age = (timestamp(payload["occurred_at"]) - timestamp(data["last_received_at"])).total_seconds()
    assert data["age_seconds"] == age
    assert (age <= 30) == (data["state"] == "fresh")


def check_processing_error(data):
    assert 1 <= data["attempt"] <= 3
    if data["attempt"] == 3:
        assert data["retryable"] is False
    if data["code"] == "RETRY_EXHAUSTED":
        assert data["attempt"] == 3
    permanent = {
        "INVALID_SCHEMA", "INVALID_BINDING", "IDENTITY_MISMATCH",
        "UNAUTHORIZED_SCOPE", "PAYLOAD_TOO_LARGE", "RETRY_EXHAUSTED",
    }
    if data["code"] in permanent:
        assert data["retryable"] is False


def check_semantics(case, reference, ack=None):
    payload = case["payload"]
    data = payload.get("data", {})
    event_type = payload.get("type")
    if event_type in {"command", "ack", "command_status"}:
        check_command_semantics(payload, reference, ack)
    elif event_type in {"job_requested", "job_progress"}:
        check_job_semantics(payload, reference)
    elif event_type == "telemetry":
        assert payload["correlation_id"] == payload["event_id"]
    elif event_type in {"prediction", "alert", "telemetry_persisted"}:
        check_source_semantics(payload, reference)
    elif event_type in {"model_activation", "model_status"}:
        check_model_semantics(payload, reference)
    elif event_type == "freshness":
        check_freshness(payload)
    elif event_type == "processing_error":
        check_processing_error(data)
    elif case["schema"] == "offline_row":
        labels = payload["labels"]
        if labels["rul_observed"]:
            assert labels["rul_hours_true"] is not None
        else:
            assert labels["rul_hours_true"] is None


def check_catalog(case, context):
    payload = case["payload"]
    if case["schema"] == "offline_row":
        assert payload["equipment_id"] == context["equipment_id"]
        return
    if payload["device_id"] is None:
        return
    assert all(payload[key] == context[key] for key in SCOPE)
    data = payload["data"]
    if "equipment_id" in data:
        assert data["equipment_id"] == context["equipment_id"]
    if payload["type"] == "telemetry":
        assert data["equipment"]["equipment_id"] == context["equipment_id"]
        for role in ROLES:
            assert data["measurements"][role]["sensor_id"] == context["sensors"][role]
        for actuator in ("led", "buzzer"):
            assert data["actuators"][actuator]["actuator_id"] == context["actuators"][actuator]
    elif "actuator" in data and "actuator_id" in data:
        assert data["actuator_id"] == context["actuators"][data["actuator"]]


def failure_category(case, contract):
    try:
        json.dumps(case["payload"], allow_nan=False)
    except ValueError:
        return "json"
    if list(validator(contract, case["schema"]).iter_errors(case["payload"])):
        return "schema"
    reference = resolve_reference(case, contract["valid"])
    ack = resolve_reference(case, contract["valid"], "ack_reference")
    checks = (
        ("binding", lambda: check_binding(case)),
        ("semantic", lambda: check_semantics(case, reference, ack)),
        ("catalog", lambda: check_catalog(case, contract["context"])),
    )
    for category, check in checks:
        try:
            check()
        except AssertionError:
            return category
    return None


def set_path(payload, path, value):
    parts = path.split(".")
    target = payload
    for part in parts[:-1]:
        target = target[part]
    target[parts[-1]] = value


def materialize_invalid(spec, examples):
    base = next(case for case in examples if case["name"] == spec["base"])
    case = deepcopy(base)
    case["name"] = spec["name"]
    for path, value in spec.get("set", {}).items():
        set_path(case["payload"], path, value)
    for path in spec.get("remove", []):
        parts = path.split(".")
        target = case["payload"]
        for part in parts[:-1]:
            target = target[part]
        del target[parts[-1]]
    for key in ("topic", "routing_key", "reference", "ack_reference", "schema"):
        if key in spec:
            case[key] = spec[key]
    return case


def internal_refs(node):
    if isinstance(node, dict):
        if "$ref" in node:
            yield node["$ref"]
        for value in node.values():
            yield from internal_refs(value)
    elif isinstance(node, list):
        for value in node:
            yield from internal_refs(value)


def test_aiot_schema_is_draft_2020_12_and_self_contained(contract):
    schema = contract["schema"]
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["$ref"] == "#/$defs/event"
    Draft202012Validator.check_schema(schema)
    assert all(reference.startswith("#/") for reference in internal_refs(schema))


def test_all_valid_aiot_examples(contract):
    for case in contract["valid"]:
        category = failure_category(case, contract)
        assert category is None, f"{case['name']}: unexpected {category} failure"


def test_all_invalid_aiot_examples(contract):
    for spec in contract["invalid"]:
        case = materialize_invalid(spec, contract["valid"])
        category = failure_category(case, contract)
        assert category == spec["expected"], (
            f"{spec['name']}: expected {spec['expected']}, got {category}"
        )


def test_v1_and_v2_remain_valid_and_are_rejected_by_v3(contract):
    v1 = load_json("examples/telemetry.valid.json")
    Draft202012Validator(load_json("telemetry.schema.json")).validate(v1)
    assert list(validator(contract, "event").iter_errors(v1))
    v2_schema = load_json("evolution.schema.json")
    for case in load_json("examples/evolution.valid.json"):
        Draft202012Validator(
            {**v2_schema, "$ref": f"#/$defs/{case['schema']}"},
            format_checker=FormatChecker(),
        ).validate(case["payload"])
        assert list(validator(contract, "event").iter_errors(case["payload"]))


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_non_finite_measurements_are_rejected_before_schema(value, contract):
    base = next(case for case in contract["valid"] if case["payload"].get("type") == "telemetry")
    case = deepcopy(base)
    set_path(case["payload"], "data.measurements.ambient_temperature.value", value)
    assert failure_category(case, contract) == "json"


def reject_json_constant(value):
    raise ValueError(f"Non-JSON numeric constant: {value}")


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_raw_non_json_constants_are_rejected(constant):
    with pytest.raises(ValueError, match="Non-JSON numeric constant"):
        json.loads('{"value":' + constant + '}', parse_constant=reject_json_constant)


def test_swapping_same_unit_sensors_is_a_catalog_error(contract):
    base = next(case for case in contract["valid"] if case["payload"].get("type") == "telemetry")
    case = deepcopy(base)
    readings = case["payload"]["data"]["measurements"]
    ambient = readings["ambient_temperature"]["sensor_id"]
    motor = readings["motor_temperature"]["sensor_id"]
    readings["ambient_temperature"]["sensor_id"] = motor
    readings["motor_temperature"]["sensor_id"] = ambient
    assert failure_category(case, contract) == "catalog"


def test_ack_reports_actual_state_even_when_command_was_not_applied(contract):
    base = next(
        case for case in contract["valid"]
        if case["payload"].get("type") == "ack" and case.get("reference")
        and isinstance(case["payload"]["data"]["applied_state"], bool)
    )
    case = deepcopy(base)
    command = resolve_reference(case, contract["valid"])
    desired = command["data"]["desired_state"]
    case["payload"]["data"]["applied_state"] = not desired
    assert failure_category(case, contract) is None


def test_zero_rul_is_a_valid_observed_label(contract):
    base = next(case for case in contract["valid"] if case["schema"] == "offline_row")
    case = deepcopy(base)
    case["payload"]["labels"] = {
        **case["payload"]["labels"], "rul_observed": True, "rul_hours_true": 0,
    }
    assert failure_category(case, contract) is None
