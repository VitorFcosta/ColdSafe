"""Authenticated REST entry points for manual LED commands."""

from collections.abc import Callable
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from backend.app.api.catalog import CatalogService
from backend.app.api.schemas import ErrorResponse
from backend.app.services.commands import CommandService


class LedCommandInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    desired_state: bool


class CommandData(BaseModel):
    schema_version: Literal[2]
    command_id: UUID
    device_id: str
    actuator: Literal["led", "buzzer"]
    desired_state: bool
    confirmed_state: bool | None
    status: Literal["pending", "confirmed", "rejected", "unconfirmed"]


class CommandMeta(BaseModel):
    schema_version: Literal[2] = 2


class CommandApiResponse(BaseModel):
    success: Literal[True] = True
    data: CommandData
    meta: CommandMeta = CommandMeta()


def create_command_router(
    catalog: CatalogService,
    commands: CommandService | None,
    require_user: Callable[..., UUID],
) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1", tags=["Commands"],
        responses={code: {"model": ErrorResponse} for code in (401, 404, 422, 503)},
    )

    @router.post("/devices/{device_id}/led/commands", response_model=CommandApiResponse)
    def request_led(
        device_id: UUID, body: LedCommandInput, user_id: UUID = Depends(require_user)
    ) -> CommandApiResponse:
        if commands is None:
            raise HTTPException(status_code=503, detail="DEPENDENCY_UNAVAILABLE")
        device = catalog.get_device(user_id, device_id)
        if not device["is_active"]:
            raise HTTPException(status_code=404, detail="DEVICE_NOT_FOUND")
        try:
            data = commands.request(
                device_id, device["mqtt_device_id"], "led", body.desired_state,
                "manual", user_id,
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="DEVICE_NOT_FOUND") from exc
        return CommandApiResponse(data=CommandData.model_validate(data))

    @router.get("/commands/{command_id}", response_model=CommandApiResponse)
    def get_command(
        command_id: UUID, user_id: UUID = Depends(require_user)
    ) -> CommandApiResponse:
        if commands is None:
            raise HTTPException(status_code=503, detail="DEPENDENCY_UNAVAILABLE")
        data = commands.get_for_user(command_id, user_id)
        if data is None:
            raise HTTPException(status_code=404, detail="DEVICE_NOT_FOUND")
        return CommandApiResponse(data=CommandData.model_validate(data))

    return router
