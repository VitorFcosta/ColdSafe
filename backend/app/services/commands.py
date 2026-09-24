"""Persist commands before MQTT publication and correlate actuator ACKs."""

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from backend.app.config.settings import RuntimeSettings
from backend.app.repositories.postgres import connect


LOGGER = logging.getLogger(__name__)


class CommandService:
    def __init__(
        self, settings: RuntimeSettings, publisher: Callable[[str, dict[str, Any]], bool]
    ) -> None:
        self.settings = settings
        self.publisher = publisher

    @contextmanager
    def _cursor(self) -> Iterator[psycopg.Cursor[dict[str, Any]]]:
        with connect(self.settings) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                yield cursor

    @staticmethod
    def _audit(
        cursor: psycopg.Cursor[dict[str, Any]], row: dict[str, Any], event: str,
        details: dict[str, Any],
    ) -> None:
        cursor.execute(
            "INSERT INTO audit_events (actor_user_id, device_id, command_id, event_type, details) "
            "VALUES (%s, %s, %s, %s, %s)",
            (row["requested_by_user_id"], row["device_id"], row["id"], event,
             Jsonb({"source": row["origin"], "actuator": row["actuator"],
                    "desired_state": row["desired_on"], **details})),
        )

    @staticmethod
    def _response(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "schema_version": 2,
            "command_id": str(row["id"]),
            "device_id": row["mqtt_device_id"],
            "actuator": row["actuator"],
            "desired_state": row["desired_on"],
            "confirmed_state": row["desired_on"] if row["status"] == "confirmed" else None,
            "status": row["status"],
        }

    @staticmethod
    def _expire(
        cursor: psycopg.Cursor[dict[str, Any]], row: dict[str, Any]
    ) -> dict[str, Any]:
        if row["status"] != "pending":
            return row
        expired = cursor.execute(
            "UPDATE actuator_commands SET status = 'unconfirmed' "
            "WHERE id = %s AND status = 'pending' "
            "AND deadline_at <= clock_timestamp() RETURNING id",
            (row["id"],),
        ).fetchone()
        if expired is None:
            return row
        CommandService._audit(
            cursor, row, "command_unconfirmed", {"status": "unconfirmed", "cause": "timeout"}
        )
        return {**row, "status": "unconfirmed"}

    def request(
        self, device_id: UUID, mqtt_device_id: str, actuator: str,
        desired_state: bool, source: str, user_id: UUID | None,
    ) -> dict[str, Any]:
        if (actuator, source) not in {("led", "manual"), ("buzzer", "automatic")}:
            raise ValueError("invalid actuator/source combination")
        if type(desired_state) is not bool or (source == "manual") != (user_id is not None):
            raise ValueError("invalid desired state or actor")

        command_id = uuid4()
        with self._cursor() as cursor:
            row = cursor.execute(
                "INSERT INTO actuator_commands "
                "(id, device_id, requested_by_user_id, actuator, desired_on, origin, deadline_at) "
                "SELECT %s, d.id, %s, %s, %s, %s, now() + interval '10 seconds' "
                "FROM devices d JOIN environments e ON e.id = d.environment_id "
                "WHERE d.id = %s AND d.mqtt_device_id = %s AND d.is_active "
                "AND (%s = 'automatic' OR e.owner_user_id = %s) "
                "RETURNING id, device_id, requested_by_user_id, actuator, desired_on, "
                "origin, status, requested_at, deadline_at",
                (command_id, user_id, actuator, desired_state, source, device_id,
                 mqtt_device_id, source, user_id),
            ).fetchone()
            if row is None:
                raise LookupError("DEVICE_NOT_FOUND")
            self._audit(cursor, row, "command_requested", {"status": "pending"})

        payload = {
            "schema_version": 2,
            "command_id": str(command_id),
            "device_id": mqtt_device_id,
            "actuator": actuator,
            "desired_state": desired_state,
            "source": source,
            "issued_at": row["requested_at"].isoformat(),
        }
        try:
            published = self.publisher(mqtt_device_id, payload)
        except Exception:
            LOGGER.exception("MQTT command publication failed: command_id=%s", command_id)
            published = False
        if not published:
            self._mark_unconfirmed(command_id, cause="publish_failed")
        return self.get(command_id)

    def _mark_unconfirmed(self, command_id: UUID, *, cause: str) -> None:
        with self._cursor() as cursor:
            row = cursor.execute(
                "UPDATE actuator_commands SET status = 'unconfirmed' "
                "WHERE id = %s AND status = 'pending' "
                "RETURNING id, device_id, requested_by_user_id, actuator, desired_on, origin",
                (command_id,),
            ).fetchone()
            if row is not None:
                self._audit(
                    cursor, row, "command_unconfirmed",
                    {"status": "unconfirmed", "cause": cause},
                )

    def get(self, command_id: UUID) -> dict[str, Any] | None:
        with self._cursor() as cursor:
            row = cursor.execute(
                "SELECT c.id, c.device_id, c.requested_by_user_id, c.actuator, "
                "c.desired_on, c.origin, c.status, c.deadline_at, d.mqtt_device_id "
                "FROM actuator_commands c "
                "JOIN devices d ON d.id = c.device_id WHERE c.id = %s FOR UPDATE OF c",
                (command_id,),
            ).fetchone()
            if row is None:
                return None
            row = self._expire(cursor, row)
            return self._response(row)

    def get_for_user(self, command_id: UUID, user_id: UUID) -> dict[str, Any] | None:
        with self._cursor() as cursor:
            row = cursor.execute(
                "SELECT c.id, c.device_id, c.requested_by_user_id, c.actuator, "
                "c.desired_on, c.origin, c.status, c.deadline_at, d.mqtt_device_id "
                "FROM actuator_commands c "
                "JOIN devices d ON d.id = c.device_id "
                "JOIN environments e ON e.id = d.environment_id "
                "WHERE c.id = %s AND e.owner_user_id = %s FOR UPDATE OF c",
                (command_id, user_id),
            ).fetchone()
            if row is None:
                return None
            row = self._expire(cursor, row)
            return self._response(row)

    def handle_ack(self, payload: dict[str, Any]) -> None:
        command_id = payload["command_id"]
        if not isinstance(command_id, UUID):
            command_id = UUID(command_id)
        with self._cursor() as cursor:
            row = cursor.execute(
                "SELECT c.id, c.device_id, c.requested_by_user_id, c.actuator, "
                "c.desired_on, c.origin, c.status, c.deadline_at, d.mqtt_device_id "
                "FROM actuator_commands c "
                "JOIN devices d ON d.id = c.device_id WHERE c.id = %s FOR UPDATE OF c",
                (command_id,),
            ).fetchone()
            if row is None:
                return
            if row["mqtt_device_id"] != payload["device_id"] or row["actuator"] != payload["actuator"]:
                if cursor.execute(
                    "SELECT 1 FROM audit_events WHERE command_id = %s "
                    "AND event_type = 'command_ack_mismatch' LIMIT 1", (command_id,)
                ).fetchone() is None:
                    self._audit(cursor, row, "command_ack_mismatch", {
                        "ack_device_id": payload["device_id"], "ack_actuator": payload["actuator"]
                    })
                return
            row = self._expire(cursor, row)
            if row["status"] == "unconfirmed":
                already_audited = cursor.execute(
                    "SELECT 1 FROM audit_events WHERE command_id = %s "
                    "AND event_type = 'command_ack_late' LIMIT 1", (command_id,)
                ).fetchone()
                if already_audited is None:
                    self._audit(cursor, row, "command_ack_late", {
                        "status": "unconfirmed", "result": payload["result"],
                        "applied_state": payload["applied_state"],
                        "reason": payload.get("reason"),
                    })
                return
            if row["status"] != "pending":
                return
            confirmed = payload["result"] == "applied" and payload["applied_state"] == row["desired_on"]
            status = "confirmed" if confirmed else "rejected"
            cursor.execute(
                "UPDATE actuator_commands SET status = %s, "
                "confirmed_at = CASE WHEN %s THEN clock_timestamp() ELSE NULL END WHERE id = %s",
                (status, confirmed, command_id),
            )
            self._audit(cursor, row, f"command_{status}", {
                "status": status, "result": payload["result"],
                "applied_state": payload["applied_state"], "reason": payload.get("reason"),
            })

    def expire_pending(self) -> int:
        with self._cursor() as cursor:
            rows = cursor.execute(
                "UPDATE actuator_commands SET status = 'unconfirmed' "
                "WHERE status = 'pending' AND deadline_at <= clock_timestamp() "
                "RETURNING id, device_id, requested_by_user_id, actuator, desired_on, origin"
            ).fetchall()
            for row in rows:
                self._audit(
                    cursor, row, "command_unconfirmed",
                    {"status": "unconfirmed", "cause": "timeout"},
                )
            return len(rows)
