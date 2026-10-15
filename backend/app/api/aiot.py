"""Explicit v3 recovery and commands; share the existing ticket/session checks."""
from datetime import UTC, datetime
from typing import Annotated, TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Path, Query

from backend.app.api.auth import AuthService
from backend.app.api.catalog import CatalogService
from backend.app.api.commands import LedCommandInput
from backend.app.api.events import EventHub, install_events
from backend.app.api.schemas import ErrorResponse
from backend.app.services.monitoring import PERIOD_DURATION, Period, utc_now

if TYPE_CHECKING:
    from backend.app.services.aiot_events import AiotEventService


DeviceId = Annotated[str, Query(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")]


def install_aiot(app: FastAPI, service: 'AiotEventService', hub: EventHub,
                 auth: AuthService, catalog: CatalogService) -> None:
    router = APIRouter(
        prefix='/api/v3', tags=['AIoT'],
        responses={code: {'model': ErrorResponse} for code in (401, 404, 422, 500, 503)},
    )

    def response(data: dict | list | None) -> dict:
        if data is None:
            raise HTTPException(status_code=404, detail='DEVICE_NOT_FOUND')
        return {'success': True, 'data': data, 'meta': {'schema_version': 3}}

    def interval(start: datetime | None, end: datetime | None,
                 period: Period | None = None) -> tuple[datetime | None, datetime | None]:
        if (start is None) != (end is None) or (
                start is not None and (start.utcoffset() is None or end.utcoffset() is None or start >= end)):
            raise HTTPException(status_code=422, detail='VALIDATION_ERROR')
        if start is not None:
            return start.astimezone(UTC), end.astimezone(UTC)
        if period is not None:
            end = utc_now()
            return end - PERIOD_DURATION[period], end
        return None, None

    @router.get('/monitoring/summary')
    def summary(device_id: DeviceId, user_id: UUID = Depends(auth.require_user)) -> dict:
        return response(service.snapshot(user_id, device_id))

    @router.get('/readings')
    def readings(device_id: DeviceId, limit: Annotated[int, Query(ge=1, le=1000)] = 300,
                 period: Period = '1h', start: datetime | None = None, end: datetime | None = None,
                 user_id: UUID = Depends(auth.require_user)) -> dict:
        start, end = interval(start, end, period)
        result = response(service.history(user_id, device_id, limit=limit, start=start, end=end))
        device = catalog.device_for_user(user_id, device_id)
        if device is None:
            raise HTTPException(status_code=404, detail='DEVICE_NOT_FOUND')
        result['meta'].update(device_id=device_id, start=start, end=end,
                              count=len(result['data']), limit=limit,
                              thresholds=catalog.thresholds_for_environment(device['environment_id']))
        return result

    @router.get('/alerts')
    def alerts(device_id: DeviceId, start: datetime | None = None, end: datetime | None = None,
               limit: Annotated[int, Query(ge=1, le=1000)] = 300,
               user_id: UUID = Depends(auth.require_user)) -> dict:
        start, end = interval(start, end)
        result = response(service.list_alerts(user_id, device_id, start=start, end=end, limit=limit))
        result['meta'].update(device_id=device_id, start=start, end=end,
                              count=len(result['data']), limit=limit)
        result['data'] = {'alerts': result['data']}
        return result

    @router.get('/commands/{command_id}')
    def command(command_id: UUID, user_id: UUID = Depends(auth.require_user)) -> dict:
        return response(service.get_command_for_user(user_id, command_id))

    @router.post('/devices/{device_id}/led/commands', responses={403: {'model': ErrorResponse}})
    def led(device_id: Annotated[str, Path(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")],
            body: LedCommandInput, user_id: UUID = Depends(auth.require_operator)) -> dict:
        try:
            return response(service.request_led(user_id, device_id, body.desired_state))
        except PermissionError:
            raise HTTPException(status_code=403, detail='FORBIDDEN') from None

    app.include_router(router)
    install_events(app, hub, auth, catalog, stream_path='/api/v3/events', include_ticket=False)
