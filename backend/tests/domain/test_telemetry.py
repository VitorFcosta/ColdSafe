import math

import pytest
from pydantic import ValidationError

from backend.app.domain.telemetry import (
    MAX_TELEMETRY_PAYLOAD_BYTES,
    TelemetryPayload,
    TelemetryPayloadTooLargeError,
    parse_telemetry_payload,
)


VALID_PAYLOAD = {
    "schema_version": 1,
    "device_id": "esp32-lab-01",
    "temperature_c": 5.4,
    "humidity_percent": 62.1,
}


def test_parse_valid_mqtt_payload():
    telemetry = parse_telemetry_payload(
        b'{"schema_version":1,"device_id":"esp32-lab-01",'
        b'"temperature_c":5.4,"humidity_percent":62.1}'
    )

    assert telemetry == TelemetryPayload(**VALID_PAYLOAD)


def test_parser_accepts_integer_measurements_allowed_by_json_number():
    telemetry = parse_telemetry_payload(
        b'{"schema_version":1,"device_id":"esp32-lab-01",'
        b'"temperature_c":5,"humidity_percent":62}'
    )

    assert telemetry.temperature_c == 5
    assert telemetry.humidity_percent == 62


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": 2},
        {"device_id": ""},
        {"device_id": "esp32 lab 01"},
        {"temperature_c": "5.4"},
        {"humidity_percent": "62.1"},
        {"temperature_c": True},
        {"humidity_percent": False},
        {"unexpected": "field"},
    ],
)
def test_rejects_wrong_versions_identifiers_types_and_extra_fields(change):
    with pytest.raises(ValidationError):
        TelemetryPayload.model_validate(VALID_PAYLOAD | change)


@pytest.mark.parametrize("missing_field", VALID_PAYLOAD)
def test_rejects_each_missing_required_field(missing_field):
    payload = VALID_PAYLOAD | {}
    del payload[missing_field]

    with pytest.raises(ValidationError):
        TelemetryPayload.model_validate(payload)


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
@pytest.mark.parametrize("field", ["temperature_c", "humidity_percent"])
def test_rejects_non_finite_measurements(field, value):
    with pytest.raises(ValidationError):
        TelemetryPayload.model_validate(VALID_PAYLOAD | {field: value})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("temperature_c", -40.1),
        ("temperature_c", 80.1),
        ("humidity_percent", -0.1),
        ("humidity_percent", 100.1),
    ],
)
def test_rejects_measurements_outside_technical_limits(field, value):
    with pytest.raises(ValidationError):
        TelemetryPayload.model_validate(VALID_PAYLOAD | {field: value})


@pytest.mark.parametrize(
    ("temperature_c", "humidity_percent"),
    [(-40, 0), (80, 100)],
)
def test_accepts_exact_technical_limits(temperature_c, humidity_percent):
    telemetry = TelemetryPayload.model_validate(
        VALID_PAYLOAD
        | {
            "temperature_c": temperature_c,
            "humidity_percent": humidity_percent,
        }
    )

    assert telemetry.temperature_c == temperature_c
    assert telemetry.humidity_percent == humidity_percent


@pytest.mark.parametrize(
    "raw_payload",
    [
        b"not-json",
        b'{"schema_version":1}',
        b'{"schema_version":1,"temperature_c":NaN}',
    ],
)
def test_parser_rejects_malformed_or_invalid_json_messages(raw_payload):
    with pytest.raises(ValidationError):
        parse_telemetry_payload(raw_payload)


def test_parser_rejects_oversized_message_before_json_validation():
    raw_payload = b" " * (MAX_TELEMETRY_PAYLOAD_BYTES + 1)

    with pytest.raises(TelemetryPayloadTooLargeError):
        parse_telemetry_payload(raw_payload)


def test_validated_payload_is_immutable():
    telemetry = TelemetryPayload(**VALID_PAYLOAD)

    with pytest.raises(ValidationError):
        telemetry.temperature_c = 7.0
