from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from backend.app.domain.reading_classification import (
    ReadingStatus,
    TemperatureThresholds,
    assess_reading,
)
from backend.app.domain.telemetry import TelemetryPayload


class ReadingWriter(Protocol):
    def save(
        self,
        *,
        payload: TelemetryPayload,
        received_at: datetime,
        status: ReadingStatus,
    ) -> None: ...


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class TelemetryIngestionService:
    """Classify validated MQTT telemetry and persist it as one atomic step."""

    repository: ReadingWriter
    clock: Callable[[], datetime] = utc_now
    thresholds_for_device: Callable[[str], TemperatureThresholds] | None = None

    def __call__(self, payload: TelemetryPayload) -> None:
        received_at = self.clock()
        thresholds = (
            self.thresholds_for_device(payload.device_id)
            if self.thresholds_for_device is not None
            else TemperatureThresholds()
        )
        assessment = assess_reading(
            temperature_c=payload.temperature_c,
            received_at=received_at,
            now=received_at,
            thresholds=thresholds,
        )
        self.repository.save(
            payload=payload,
            received_at=received_at,
            status=assessment.status,
        )
