from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.app.domain.reading_classification import ReadingStatus


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EnvironmentResponse(ApiModel):
    id: str
    name: str


class DeviceResponse(ApiModel):
    id: str


class ReadingResponse(ApiModel):
    temperature_c: float
    humidity_percent: float = Field(ge=0, le=100)
    received_at: datetime


class HistoricalReadingResponse(ReadingResponse):
    status: ReadingStatus


class FreshnessResponse(ApiModel):
    is_stale: bool
    age_seconds: float = Field(ge=0)


class ThresholdsResponse(ApiModel):
    min_c: float
    max_c: float
    attention_margin_c: float = Field(ge=0)


class MonitoringSummaryData(ApiModel):
    environment: EnvironmentResponse
    device: DeviceResponse
    reading: ReadingResponse | None
    status: ReadingStatus
    freshness: FreshnessResponse | None
    thresholds: ThresholdsResponse


class SuccessMeta(ApiModel):
    schema_version: Literal[1] = 1


class MonitoringSummaryResponse(ApiModel):
    success: Literal[True] = True
    data: MonitoringSummaryData
    meta: SuccessMeta = SuccessMeta()


class ReadingHistoryData(ApiModel):
    readings: tuple[HistoricalReadingResponse, ...]


class ReadingHistoryMeta(SuccessMeta):
    device_id: str
    start: datetime
    end: datetime
    count: int = Field(ge=0)
    limit: int = Field(ge=1, le=1000)


class ReadingHistoryResponse(ApiModel):
    success: Literal[True] = True
    data: ReadingHistoryData
    meta: ReadingHistoryMeta


class HealthData(ApiModel):
    status: Literal["ok"] = "ok"


class HealthResponse(ApiModel):
    success: Literal[True] = True
    data: HealthData = HealthData()
    meta: SuccessMeta = SuccessMeta()


class ErrorDetail(ApiModel):
    code: Literal[
        "VALIDATION_ERROR",
        "DEVICE_NOT_FOUND",
        "DEPENDENCY_UNAVAILABLE",
        "INTERNAL_ERROR",
    ]
    message: str


class ErrorMeta(ApiModel):
    request_id: str


class ErrorResponse(ApiModel):
    success: Literal[False] = False
    error: ErrorDetail
    meta: ErrorMeta
