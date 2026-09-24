"""Version 2 actuator acknowledgments received from MQTT."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


MAX_ACK_BYTES = 1024


class AckPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[2]
    command_id: UUID
    device_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,64}$")
    actuator: Literal["led", "buzzer"]
    result: Literal["applied", "rejected"]
    applied_state: bool | None
    reason: Literal["INVALID_COMMAND", "ACTUATOR_FAILURE"] | None = None

    @model_validator(mode="after")
    def valid_result(self) -> "AckPayload":
        if self.result == "applied" and (
            self.applied_state is None or "reason" in self.model_fields_set
        ):
            raise ValueError("applied ACK needs a boolean state and no reason")
        if self.result == "rejected" and (self.applied_state is not None or self.reason is None):
            raise ValueError("rejected ACK needs a reason and a null state")
        return self


def parse_ack_payload(raw: bytes) -> AckPayload:
    if len(raw) > MAX_ACK_BYTES:
        raise ValueError("ACK payload is too large")
    return AckPayload.model_validate_json(raw)
