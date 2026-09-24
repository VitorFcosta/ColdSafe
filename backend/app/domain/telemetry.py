from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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

    schema_version: Literal[1, 2]
    device_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    temperature_c: float = Field(ge=-40, le=80)
    humidity_percent: float = Field(ge=0, le=100)
    light_percent: float | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def validate_light_version(self) -> "TelemetryPayload":
        if (self.schema_version == 2) != (self.light_percent is not None):
            raise ValueError("light_percent is required only for telemetry v2")
        return self


def parse_telemetry_payload(raw_payload: bytes) -> TelemetryPayload:
    """Validate untrusted MQTT bytes before they reach application services."""

    if len(raw_payload) > MAX_TELEMETRY_PAYLOAD_BYTES:
        raise TelemetryPayloadTooLargeError(
            f"MQTT telemetry payload exceeds {MAX_TELEMETRY_PAYLOAD_BYTES} bytes"
        )

    return TelemetryPayload.model_validate_json(raw_payload)
