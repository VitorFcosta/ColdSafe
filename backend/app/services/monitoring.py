from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol

from backend.app.domain.reading_classification import (
    DEFAULT_THRESHOLDS,
    Freshness,
    ReadingStatus,
    TemperatureThresholds,
    assess_reading,
)
from backend.app.errors import DeviceNotFoundError
from backend.app.repositories.influxdb import StoredReading


DEVICE_ID = "esp32-lab-01"
ENVIRONMENT_ID = "lab-cold-room-01"
ENVIRONMENT_NAME = "Laboratório Refrigerado"
Period = Literal["15m", "1h", "6h", "24h"]
PERIOD_DURATION: dict[Period, timedelta] = {
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "6h": timedelta(hours=6),
    "24h": timedelta(hours=24),
}


class ReadingRepository(Protocol):
    def get_latest(self, device_id: str) -> StoredReading | None: ...

    def list_history(
        self,
        *,
        device_id: str,
        start: datetime,
        end: datetime,
        limit: int,
    ) -> tuple[StoredReading, ...]: ...


@dataclass(frozen=True)
class MonitoringSummary:
    reading: StoredReading | None
    status: ReadingStatus
    freshness: Freshness | None
    thresholds: TemperatureThresholds


@dataclass(frozen=True)
class ReadingHistory:
    readings: tuple[StoredReading, ...]
    device_id: str
    start: datetime
    end: datetime
    limit: int


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class MonitoringService:
    repository: ReadingRepository
    clock: Callable[[], datetime] = utc_now
    thresholds: TemperatureThresholds = DEFAULT_THRESHOLDS

    def get_summary(self) -> MonitoringSummary:
        reading = self.repository.get_latest(DEVICE_ID)
        assessment = assess_reading(
            temperature_c=None if reading is None else reading.temperature_c,
            received_at=None if reading is None else reading.received_at,
            now=self.clock(),
            thresholds=self.thresholds,
        )
        return MonitoringSummary(
            reading=reading,
            status=assessment.status,
            freshness=assessment.freshness,
            thresholds=self.thresholds,
        )

    def list_history(
        self,
        *,
        device_id: str,
        period: Period,
        limit: int,
    ) -> ReadingHistory:
        if device_id != DEVICE_ID:
            raise DeviceNotFoundError(device_id)
        end = self.clock()
        start = end - PERIOD_DURATION[period]
        readings = self.repository.list_history(
            device_id=device_id,
            start=start,
            end=end,
            limit=limit,
        )
        return ReadingHistory(
            readings=readings,
            device_id=device_id,
            start=start,
            end=end,
            limit=limit,
        )
