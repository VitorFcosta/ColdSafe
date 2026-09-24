from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
from typing import Annotated, Any, Callable, Iterator
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from backend.app.api.schemas import ErrorResponse
from backend.app.config.settings import RuntimeSettings
from backend.app.repositories.postgres import connect


Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
MqttId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9._-]{1,64}$")]
Temperature = Annotated[Decimal, Field(max_digits=5, decimal_places=2)]


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NamedInput(InputModel):
    name: Name


class DeviceInput(NamedInput):
    mqtt_device_id: MqttId


class ThresholdInput(InputModel):
    min_c: Temperature
    max_c: Temperature
    attention_margin_c: Annotated[Temperature, Field(ge=0)]

    @model_validator(mode="after")
    def valid_range(self) -> ThresholdInput:
        if self.min_c >= self.max_c or self.attention_margin_c * 2 >= self.max_c - self.min_c:
            raise ValueError("INVALID_THRESHOLDS")
        return self


def _public(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: str(value) if isinstance(value, UUID) else float(value) if isinstance(value, Decimal) else value
        for key, value in row.items()
    }


def _found(row: dict[str, Any] | None, code: str) -> dict[str, Any]:
    if row is None:
        raise HTTPException(status_code=404, detail=code)
    return _public(row)


class CatalogService:
    def __init__(self, settings: RuntimeSettings) -> None:
        self.settings = settings

    @contextmanager
    def _cursor(self) -> Iterator[psycopg.Cursor[dict[str, Any]]]:
        with connect(self.settings) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                yield cursor

    def create_environment(self, user_id: UUID, name: str) -> dict[str, Any]:
        with self._cursor() as cursor:
            row = cursor.execute(
                "INSERT INTO environments (owner_user_id, name) VALUES (%s, %s) "
                "RETURNING id, name, created_at, updated_at",
                (user_id, name),
            ).fetchone()
            cursor.execute(
                "INSERT INTO environment_rules (environment_id) VALUES (%s)", (row["id"],)
            )
            return _public(row)

    def list_environments(self, user_id: UUID) -> list[dict[str, Any]]:
        with self._cursor() as cursor:
            rows = cursor.execute(
                "SELECT id, name, created_at, updated_at FROM environments "
                "WHERE owner_user_id = %s ORDER BY created_at, id",
                (user_id,),
            ).fetchall()
            return [_public(row) for row in rows]

    def get_environment(self, user_id: UUID, environment_id: UUID) -> dict[str, Any]:
        with self._cursor() as cursor:
            return _found(
                cursor.execute(
                    "SELECT id, name, created_at, updated_at FROM environments "
                    "WHERE id = %s AND owner_user_id = %s",
                    (environment_id, user_id),
                ).fetchone(),
                "ENVIRONMENT_NOT_FOUND",
            )

    def update_environment(self, user_id: UUID, environment_id: UUID, name: str) -> dict[str, Any]:
        with self._cursor() as cursor:
            return _found(
                cursor.execute(
                    "UPDATE environments SET name = %s, updated_at = now() "
                    "WHERE id = %s AND owner_user_id = %s "
                    "RETURNING id, name, created_at, updated_at",
                    (name, environment_id, user_id),
                ).fetchone(),
                "ENVIRONMENT_NOT_FOUND",
            )

    def create_device(
        self, user_id: UUID, environment_id: UUID, name: str, mqtt_device_id: str
    ) -> dict[str, Any]:
        try:
            with self._cursor() as cursor:
                row = cursor.execute(
                    "INSERT INTO devices (environment_id, name, mqtt_device_id) "
                    "SELECT id, %s, %s FROM environments "
                    "WHERE id = %s AND owner_user_id = %s "
                    "RETURNING id, environment_id, mqtt_device_id, name, is_active, "
                    "created_at, updated_at",
                    (name, mqtt_device_id, environment_id, user_id),
                ).fetchone()
                return _found(row, "ENVIRONMENT_NOT_FOUND")
        except psycopg.errors.UniqueViolation as exc:
            raise HTTPException(status_code=409, detail="DEVICE_ID_EXISTS") from exc

    def list_devices(self, user_id: UUID, environment_id: UUID) -> list[dict[str, Any]]:
        with self._cursor() as cursor:
            self._owned_environment(cursor, user_id, environment_id)
            rows = cursor.execute(
                "SELECT id, environment_id, mqtt_device_id, name, is_active, "
                "created_at, updated_at FROM devices WHERE environment_id = %s "
                "ORDER BY created_at, id",
                (environment_id,),
            ).fetchall()
            return [_public(row) for row in rows]

    def get_device(self, user_id: UUID, device_id: UUID) -> dict[str, Any]:
        with self._cursor() as cursor:
            return _found(
                cursor.execute(
                    "SELECT d.id, d.environment_id, d.mqtt_device_id, d.name, d.is_active, "
                    "d.created_at, d.updated_at FROM devices d "
                    "JOIN environments e ON e.id = d.environment_id "
                    "WHERE d.id = %s AND e.owner_user_id = %s",
                    (device_id, user_id),
                ).fetchone(),
                "DEVICE_NOT_FOUND",
            )

    def update_device(self, user_id: UUID, device_id: UUID, name: str) -> dict[str, Any]:
        with self._cursor() as cursor:
            return _found(
                cursor.execute(
                    "UPDATE devices d SET name = %s, updated_at = now() "
                    "FROM environments e WHERE e.id = d.environment_id "
                    "AND d.id = %s AND e.owner_user_id = %s "
                    "RETURNING d.id, d.environment_id, d.mqtt_device_id, d.name, "
                    "d.is_active, d.created_at, d.updated_at",
                    (name, device_id, user_id),
                ).fetchone(),
                "DEVICE_NOT_FOUND",
            )

    def deactivate_device(self, user_id: UUID, device_id: UUID) -> dict[str, Any]:
        with self._cursor() as cursor:
            return _found(
                cursor.execute(
                    "UPDATE devices d SET is_active = false, updated_at = now() "
                    "FROM environments e WHERE e.id = d.environment_id "
                    "AND d.id = %s AND e.owner_user_id = %s "
                    "RETURNING d.id, d.environment_id, d.mqtt_device_id, d.name, "
                    "d.is_active, d.created_at, d.updated_at",
                    (device_id, user_id),
                ).fetchone(),
                "DEVICE_NOT_FOUND",
            )

    def device_for_user(self, user_id: UUID, mqtt_device_id: str) -> dict[str, Any] | None:
        with self._cursor() as cursor:
            row = cursor.execute(
                "SELECT d.id, d.environment_id, d.mqtt_device_id, d.name, "
                "d.is_active, e.name AS environment_name FROM devices d "
                "JOIN environments e ON e.id = d.environment_id "
                "WHERE d.mqtt_device_id = %s AND e.owner_user_id = %s",
                (mqtt_device_id, user_id),
            ).fetchone()
            return _public(row) if row else None

    def active_device(self, mqtt_device_id: str) -> dict[str, Any] | None:
        with self._cursor() as cursor:
            row = cursor.execute(
                "SELECT d.id, d.environment_id, d.mqtt_device_id, d.name, "
                "d.is_active, e.name AS environment_name FROM devices d "
                "JOIN environments e ON e.id = d.environment_id "
                "WHERE d.mqtt_device_id = %s AND d.is_active",
                (mqtt_device_id,),
            ).fetchone()
            return _public(row) if row else None

    def registered_device(self, mqtt_device_id: str) -> dict[str, Any] | None:
        with self._cursor() as cursor:
            row = cursor.execute(
                "SELECT d.id, d.environment_id, d.mqtt_device_id, d.name, "
                "d.is_active, e.name AS environment_name FROM devices d "
                "JOIN environments e ON e.id = d.environment_id "
                "WHERE d.mqtt_device_id = %s",
                (mqtt_device_id,),
            ).fetchone()
            return _public(row) if row else None

    def thresholds_for_environment(self, environment_id: UUID | str) -> dict[str, float]:
        with self._cursor() as cursor:
            row = cursor.execute(
                "SELECT temp_min_c AS min_c, temp_max_c AS max_c, "
                "recovery_margin_c AS attention_margin_c "
                "FROM environment_rules WHERE environment_id = %s",
                (environment_id,),
            ).fetchone()
            return _found(row, "ENVIRONMENT_NOT_FOUND")

    def get_rules(self, user_id: UUID, environment_id: UUID) -> dict[str, float]:
        with self._cursor() as cursor:
            self._owned_environment(cursor, user_id, environment_id)
            row = cursor.execute(
                "SELECT temp_min_c AS min_c, temp_max_c AS max_c, "
                "recovery_margin_c AS attention_margin_c "
                "FROM environment_rules WHERE environment_id = %s",
                (environment_id,),
            ).fetchone()
            return _found(row, "ENVIRONMENT_NOT_FOUND")

    def update_rules(
        self, user_id: UUID, environment_id: UUID, thresholds: ThresholdInput
    ) -> dict[str, float]:
        with self._cursor() as cursor:
            self._owned_environment(cursor, user_id, environment_id)
            previous = self.get_rules_for_cursor(cursor, environment_id)
            row = cursor.execute(
                "UPDATE environment_rules SET temp_min_c = %s, temp_max_c = %s, "
                "recovery_margin_c = %s, updated_at = now() "
                "WHERE environment_id = %s "
                "RETURNING temp_min_c AS min_c, temp_max_c AS max_c, "
                "recovery_margin_c AS attention_margin_c",
                (
                    thresholds.min_c,
                    thresholds.max_c,
                    thresholds.attention_margin_c,
                    environment_id,
                ),
            ).fetchone()
            current = _found(row, "ENVIRONMENT_NOT_FOUND")
            cursor.execute(
                "INSERT INTO audit_events (actor_user_id, event_type, details) "
                "VALUES (%s, 'environment_rules_updated', %s)",
                (user_id, Jsonb({"environment_id": str(environment_id), "before": previous, "after": current})),
            )
            return current

    @staticmethod
    def _owned_environment(cursor: psycopg.Cursor, user_id: UUID, environment_id: UUID) -> None:
        if cursor.execute(
            "SELECT 1 FROM environments WHERE id = %s AND owner_user_id = %s",
            (environment_id, user_id),
        ).fetchone() is None:
            raise HTTPException(status_code=404, detail="ENVIRONMENT_NOT_FOUND")

    @staticmethod
    def get_rules_for_cursor(cursor: psycopg.Cursor, environment_id: UUID) -> dict[str, float]:
        row = cursor.execute(
            "SELECT temp_min_c AS min_c, temp_max_c AS max_c, "
            "recovery_margin_c AS attention_margin_c "
            "FROM environment_rules WHERE environment_id = %s FOR UPDATE",
            (environment_id,),
        ).fetchone()
        return _found(row, "ENVIRONMENT_NOT_FOUND")


def create_catalog_router(catalog: CatalogService, require_user: Callable[..., UUID]) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1", tags=["Catalog"],
        responses={
            401: {"model": ErrorResponse},
            404: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
        },
    )

    def ok(data: Any) -> dict[str, Any]:
        return {"success": True, "data": data, "meta": {"schema_version": 1}}

    @router.post("/environments", status_code=201)
    def create_environment(body: NamedInput, user_id: UUID = Depends(require_user)) -> dict[str, Any]:
        return ok(catalog.create_environment(user_id, body.name))

    @router.get("/environments")
    def list_environments(user_id: UUID = Depends(require_user)) -> dict[str, Any]:
        return ok(catalog.list_environments(user_id))

    @router.get("/environments/{environment_id}")
    def get_environment(environment_id: UUID, user_id: UUID = Depends(require_user)) -> dict[str, Any]:
        return ok(catalog.get_environment(user_id, environment_id))

    @router.patch("/environments/{environment_id}")
    def update_environment(
        environment_id: UUID, body: NamedInput, user_id: UUID = Depends(require_user)
    ) -> dict[str, Any]:
        return ok(catalog.update_environment(user_id, environment_id, body.name))

    @router.post(
        "/environments/{environment_id}/devices", status_code=201,
        responses={409: {"model": ErrorResponse}},
    )
    def create_device(
        environment_id: UUID, body: DeviceInput, user_id: UUID = Depends(require_user)
    ) -> dict[str, Any]:
        return ok(catalog.create_device(user_id, environment_id, body.name, body.mqtt_device_id))

    @router.get("/environments/{environment_id}/devices")
    def list_devices(environment_id: UUID, user_id: UUID = Depends(require_user)) -> dict[str, Any]:
        return ok(catalog.list_devices(user_id, environment_id))

    @router.get("/devices/{device_id}")
    def get_device(device_id: UUID, user_id: UUID = Depends(require_user)) -> dict[str, Any]:
        return ok(catalog.get_device(user_id, device_id))

    @router.patch("/devices/{device_id}")
    def update_device(
        device_id: UUID, body: NamedInput, user_id: UUID = Depends(require_user)
    ) -> dict[str, Any]:
        return ok(catalog.update_device(user_id, device_id, body.name))

    @router.delete("/devices/{device_id}")
    def deactivate_device(device_id: UUID, user_id: UUID = Depends(require_user)) -> dict[str, Any]:
        return ok(catalog.deactivate_device(user_id, device_id))

    @router.get("/environments/{environment_id}/rules")
    def get_rules(environment_id: UUID, user_id: UUID = Depends(require_user)) -> dict[str, Any]:
        return ok(catalog.get_rules(user_id, environment_id))

    @router.put("/environments/{environment_id}/rules")
    def update_rules(
        environment_id: UUID, body: ThresholdInput, user_id: UUID = Depends(require_user)
    ) -> dict[str, Any]:
        return ok(catalog.update_rules(user_id, environment_id, body))

    return router
