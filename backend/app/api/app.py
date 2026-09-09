from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Annotated, AsyncContextManager
from uuid import uuid4

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.api.schemas import (
    DeviceResponse,
    EnvironmentResponse,
    ErrorDetail,
    ErrorMeta,
    ErrorResponse,
    FreshnessResponse,
    HealthResponse,
    HistoricalReadingResponse,
    MonitoringSummaryData,
    MonitoringSummaryResponse,
    ReadingHistoryData,
    ReadingHistoryMeta,
    ReadingHistoryResponse,
    ReadingResponse,
    ThresholdsResponse,
)
from backend.app.errors import DependencyUnavailableError, DeviceNotFoundError
from backend.app.services.monitoring import (
    DEVICE_ID,
    ENVIRONMENT_ID,
    ENVIRONMENT_NAME,
    MonitoringService,
    Period,
    ReadingRepository,
    utc_now,
)


ERRORS: dict[str, str] = {
    "VALIDATION_ERROR": "Um ou mais parâmetros são inválidos.",
    "DEVICE_NOT_FOUND": "O dispositivo informado não foi encontrado.",
    "DEPENDENCY_UNAVAILABLE": "Não foi possível consultar as leituras agora.",
    "INTERNAL_ERROR": "Ocorreu um erro interno.",
}


def _error_response(*, status_code: int, code: str) -> JSONResponse:
    response = ErrorResponse(
        error=ErrorDetail(code=code, message=ERRORS[code]),
        meta=ErrorMeta(request_id=str(uuid4())),
    )
    return JSONResponse(status_code=status_code, content=response.model_dump())


def create_app(
    *,
    repository: ReadingRepository,
    readiness_check: Callable[[], bool],
    clock: Callable[[], datetime] = utc_now,
    lifespan: Callable[[FastAPI], AsyncContextManager[None]] | None = None,
    cors_origins: tuple[str, ...] = (),
) -> FastAPI:
    app = FastAPI(
        title="ColdSafe Monitoring API",
        version="1.0.0",
        description=(
            "API do protótipo acadêmico ColdSafe. Este sistema não é certificado "
            "para uso médico, sanitário ou regulatório."
        ),
        lifespan=lifespan,
    )
    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(cors_origins),
            allow_credentials=False,
            allow_methods=["GET"],
            allow_headers=["Accept"],
        )
    monitoring = MonitoringService(repository=repository, clock=clock)
    error_responses = {
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    }

    @app.exception_handler(RequestValidationError)
    def validation_exception_handler(
        _request: Request, _exc: RequestValidationError
    ) -> JSONResponse:
        return _error_response(status_code=422, code="VALIDATION_ERROR")

    @app.exception_handler(DeviceNotFoundError)
    def device_not_found_handler(
        _request: Request, _exc: DeviceNotFoundError
    ) -> JSONResponse:
        return _error_response(status_code=404, code="DEVICE_NOT_FOUND")

    @app.exception_handler(DependencyUnavailableError)
    def dependency_unavailable_handler(
        _request: Request, _exc: DependencyUnavailableError
    ) -> JSONResponse:
        return _error_response(status_code=503, code="DEPENDENCY_UNAVAILABLE")

    @app.exception_handler(Exception)
    def internal_error_handler(_request: Request, _exc: Exception) -> JSONResponse:
        return _error_response(status_code=500, code="INTERNAL_ERROR")

    @app.get(
        "/api/v1/monitoring/summary",
        response_model=MonitoringSummaryResponse,
        responses={500: error_responses[500], 503: error_responses[503]},
        operation_id="getMonitoringSummary",
        tags=["Monitoring"],
    )
    def get_monitoring_summary() -> MonitoringSummaryResponse:
        summary = monitoring.get_summary()
        reading = None
        if summary.reading is not None:
            reading = ReadingResponse(
                temperature_c=summary.reading.temperature_c,
                humidity_percent=summary.reading.humidity_percent,
                received_at=summary.reading.received_at,
            )
        freshness = None
        if summary.freshness is not None:
            freshness = FreshnessResponse(
                is_stale=summary.freshness.is_stale,
                age_seconds=summary.freshness.age_seconds,
            )
        return MonitoringSummaryResponse(
            data=MonitoringSummaryData(
                environment=EnvironmentResponse(
                    id=ENVIRONMENT_ID, name=ENVIRONMENT_NAME
                ),
                device=DeviceResponse(id=DEVICE_ID),
                reading=reading,
                status=summary.status,
                freshness=freshness,
                thresholds=ThresholdsResponse(
                    min_c=summary.thresholds.min_c,
                    max_c=summary.thresholds.max_c,
                    attention_margin_c=summary.thresholds.attention_margin_c,
                ),
            )
        )

    @app.get(
        "/api/v1/readings",
        response_model=ReadingHistoryResponse,
        responses=error_responses,
        operation_id="listReadings",
        tags=["Monitoring"],
    )
    def list_readings(
        device_id: Annotated[
            str,
            Query(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._-]+$"),
        ],
        period: Period = "1h",
        limit: Annotated[int, Query(ge=1, le=1000)] = 300,
    ) -> ReadingHistoryResponse:
        history = monitoring.list_history(
            device_id=device_id,
            period=period,
            limit=limit,
        )
        readings = tuple(
            HistoricalReadingResponse(
                temperature_c=reading.temperature_c,
                humidity_percent=reading.humidity_percent,
                received_at=reading.received_at,
                status=reading.status,
            )
            for reading in history.readings
        )
        return ReadingHistoryResponse(
            data=ReadingHistoryData(readings=readings),
            meta=ReadingHistoryMeta(
                device_id=history.device_id,
                start=history.start,
                end=history.end,
                count=len(readings),
                limit=history.limit,
            ),
        )

    @app.get(
        "/health/live",
        response_model=HealthResponse,
        operation_id="getLiveness",
        tags=["Health"],
    )
    def get_liveness() -> HealthResponse:
        return HealthResponse()

    @app.get(
        "/health/ready",
        response_model=HealthResponse,
        responses={503: error_responses[503]},
        operation_id="getReadiness",
        tags=["Health"],
    )
    def get_readiness() -> HealthResponse | JSONResponse:
        try:
            ready = readiness_check()
        except Exception as exc:
            raise DependencyUnavailableError("readiness check failed") from exc
        if not ready:
            return _error_response(status_code=503, code="DEPENDENCY_UNAVAILABLE")
        return HealthResponse()

    return app
