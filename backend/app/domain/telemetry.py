from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


MAX_TELEMETRY_PAYLOAD_BYTES = 1024


class TelemetryPayloadTooLargeError(ValueError):
    """Raised before parsing an MQTT message that exceeds the accepted size."""


class TelemetryPayload(BaseModel):
    """Trusted representation of one MQTT telemetry message."""

    model_config = ConfigDict(
        allow_inf_nan=False,
        extra="forbid",
        frozen=True,
        strict=True,
    )

    schema_version: Literal[1]
    device_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    temperature_c: float = Field(ge=-40, le=80)
    humidity_percent: float = Field(ge=0, le=100)


def parse_telemetry_payload(raw_payload: bytes) -> TelemetryPayload:
    """Validate untrusted MQTT bytes before they reach application services."""

    if len(raw_payload) > MAX_TELEMETRY_PAYLOAD_BYTES:
        raise TelemetryPayloadTooLargeError(
            f"MQTT telemetry payload exceeds {MAX_TELEMETRY_PAYLOAD_BYTES} bytes"
        )

    return TelemetryPayload.model_validate_json(raw_payload)
