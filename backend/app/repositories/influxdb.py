"""InfluxDB persistence adapter for validated telemetry readings."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from backend.app.domain.reading_classification import ReadingStatus
from backend.app.domain.telemetry import TelemetryPayload


class WriteApi(Protocol):
    """Small portion of the InfluxDB write client used by the repository."""

    def write(self, *, bucket: str, org: str, record: dict[str, Any]) -> Any: ...


class QueryApi(Protocol):
    """Small portion of the InfluxDB query client used by the repository."""

    def query(self, *, query: str, org: str, params: dict[str, Any]) -> Any: ...


@dataclass(frozen=True, slots=True)
class StoredReading:
    """Immutable reading reconstructed from an InfluxDB query result."""

    schema_version: int
    device_id: str
    temperature_c: float
    humidity_percent: float
    status: ReadingStatus
    received_at: datetime


_BASE_QUERY = """
from(bucket: _bucket)
    |> range(start: _start, stop: _end)
    |> filter(fn: (row) => row._measurement == "environment_reading")
    |> filter(fn: (row) => row.device_id == _device_id)
    |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
    |> group(columns: ["device_id"])
""".strip()

_LATEST_QUERY = """
from(bucket: _bucket)
    |> range(start: 0)
    |> filter(fn: (row) => row._measurement == "environment_reading")
    |> filter(fn: (row) => row.device_id == _device_id)
    |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
    |> group(columns: ["device_id"])
    |> sort(columns: ["_time"], desc: true)
    |> limit(n: 1)
""".strip()

_HISTORY_QUERY = f"""
{_BASE_QUERY}
    |> sort(columns: ["_time"], desc: true)
    |> limit(n: _limit)
    |> sort(columns: ["_time"])
"""


class InfluxReadingRepository:
    """Write and query ColdSafe readings through injected InfluxDB APIs."""

    def __init__(
        self,
        *,
        write_api: WriteApi,
        query_api: QueryApi,
        bucket: str,
        org: str,
    ) -> None:
        self._write_api = write_api
        self._query_api = query_api
        self._bucket = bucket
        self._org = org

    def save(
        self,
        *,
        payload: TelemetryPayload,
        received_at: datetime,
        status: ReadingStatus,
    ) -> None:
        """Persist one reading already validated and classified by the backend."""

        normalized_received_at = _as_utc(received_at, name="received_at")
        self._write_api.write(
            bucket=self._bucket,
            org=self._org,
            record={
                "measurement": "environment_reading",
                "tags": {
                    "device_id": payload.device_id,
                    "status": status.value,
                },
                "fields": {
                    "schema_version": payload.schema_version,
                    "temperature_c": payload.temperature_c,
                    "humidity_percent": payload.humidity_percent,
                },
                "time": normalized_received_at,
            },
        )

    def get_latest(self, device_id: str) -> StoredReading | None:
        """Return the most recent reading for a device, if one exists."""

        readings = self._query(
            query=_LATEST_QUERY,
            params={
                "_bucket": self._bucket,
                "_device_id": device_id,
            },
        )
        return readings[0] if readings else None

    def list_history(
        self,
        *,
        device_id: str,
        start: datetime,
        end: datetime,
        limit: int,
    ) -> tuple[StoredReading, ...]:
        """Return the latest limited readings in chronological display order."""

        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        normalized_start = _as_utc(start, name="start")
        normalized_end = _as_utc(end, name="end")
        if normalized_start >= normalized_end:
            raise ValueError("start must be before end")

        return self._query(
            query=_HISTORY_QUERY,
            params={
                "_bucket": self._bucket,
                "_device_id": device_id,
                "_start": normalized_start,
                "_end": normalized_end,
                "_limit": limit,
            },
        )

    def _query(
        self,
        *,
        query: str,
        params: dict[str, Any],
    ) -> tuple[StoredReading, ...]:
        tables = self._query_api.query(
            query=query,
            org=self._org,
            params=params,
        )
        return tuple(
            _stored_reading(record.values)
            for table in tables
            for record in table.records
        )


def _stored_reading(values: dict[str, Any]) -> StoredReading:
    return StoredReading(
        schema_version=int(values["schema_version"]),
        device_id=str(values["device_id"]),
        temperature_c=float(values["temperature_c"]),
        humidity_percent=float(values["humidity_percent"]),
        status=ReadingStatus(values["status"]),
        received_at=values["_time"],
    )


def _as_utc(value: datetime, *, name: str) -> datetime:
    if value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)
