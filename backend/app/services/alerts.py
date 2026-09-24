"""Persist temperature alert transitions and request automatic buzzer changes."""

import math
from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from backend.app.config.settings import RuntimeSettings
from backend.app.domain.reading_classification import TemperatureThresholds
from backend.app.repositories.postgres import connect


class AlertService:
    def __init__(
        self,
        settings: RuntimeSettings,
        command: Callable[[UUID, str, bool], None],
    ) -> None:
        self.settings = settings
        self.command = command

    def evaluate(
        self,
        device_id: UUID,
        mqtt_device_id: str,
        temperature_c: float,
        thresholds: TemperatureThresholds,
        received_at: datetime,
    ) -> None:
        """Apply hysteresis to one valid reading; absent readings never close alerts."""
        minimum, maximum, margin = (
            thresholds.min_c, thresholds.max_c, thresholds.attention_margin_c
        )
        if not all(math.isfinite(value) for value in (temperature_c, minimum, maximum, margin)):
            raise ValueError("temperature and thresholds must be finite")
        if minimum >= maximum or margin < 0 or 2 * margin >= maximum - minimum:
            raise ValueError("invalid temperature thresholds")
        if received_at.tzinfo is None or received_at.utcoffset() is None:
            raise ValueError("received_at must be timezone-aware")

        kind = (
            "temperature_low" if temperature_c < minimum else
            "temperature_high" if temperature_c > maximum else None
        )
        recovered = minimum + margin <= temperature_c <= maximum - margin
        command_state: bool | None = None

        with connect(self.settings) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                # The device row serializes evaluations, including the first alert.
                device = cursor.execute(
                    "SELECT id FROM devices WHERE id = %s AND mqtt_device_id = %s "
                    "AND is_active FOR UPDATE",
                    (device_id, mqtt_device_id),
                ).fetchone()
                if device is None:
                    raise LookupError("DEVICE_NOT_FOUND")

                open_alerts = cursor.execute(
                    "SELECT id, kind, opened_at FROM alerts "
                    "WHERE device_id = %s AND closed_at IS NULL FOR UPDATE",
                    (device_id,),
                ).fetchall()
                had_open_alert = bool(open_alerts)
                to_close = (
                    [alert for alert in open_alerts if alert["kind"] != kind]
                    if kind is not None else
                    open_alerts if recovered else []
                )
                for alert in to_close:
                    cursor.execute(
                        "UPDATE alerts SET closed_at = GREATEST(%s, opened_at) "
                        "WHERE id = %s AND closed_at IS NULL",
                        (received_at, alert["id"]),
                    )
                    self._audit(cursor, device_id, "alert_closed", alert["id"],
                                alert["kind"], temperature_c, received_at)

                already_open = any(alert["kind"] == kind for alert in open_alerts)
                if kind is not None and not already_open:
                    alert_id = cursor.execute(
                        "INSERT INTO alerts (device_id, kind, opened_at) "
                        "VALUES (%s, %s, %s) RETURNING id",
                        (device_id, kind, received_at),
                    ).fetchone()["id"]
                    self._audit(cursor, device_id, "alert_opened", alert_id,
                                kind, temperature_c, received_at)

                has_open_alert = bool(kind) or (had_open_alert and not recovered)
                if had_open_alert != has_open_alert:
                    command_state = has_open_alert
                else:
                    latest = cursor.execute(
                        "SELECT desired_on, status, deadline_at FROM actuator_commands "
                        "WHERE device_id = %s AND actuator = 'buzzer' "
                        "ORDER BY requested_at DESC, id DESC LIMIT 1",
                        (device_id,),
                    ).fetchone()
                    if latest is None:
                        # A previous callback may have failed before recording a command.
                        oldest_open = min((a["opened_at"] for a in open_alerts), default=None)
                        if has_open_alert and oldest_open is not None and (
                            received_at - oldest_open
                        ).total_seconds() >= 10:
                            command_state = True
                    elif latest["desired_on"] != has_open_alert or (
                        latest["status"] in ("pending", "unconfirmed", "rejected")
                        and latest["deadline_at"] <= received_at
                    ):
                        command_state = has_open_alert

        # The command service uses another PostgreSQL connection. Call after commit
        # so its device FK check cannot wait on our row lock.
        if command_state is not None:
            self.command(device_id, mqtt_device_id, command_state)

    @staticmethod
    def _audit(cursor, device_id: UUID, event_type: str, alert_id: UUID,
               kind: str, temperature_c: float, received_at: datetime) -> None:
        cursor.execute(
            "INSERT INTO audit_events (device_id, event_type, details, occurred_at) "
            "VALUES (%s, %s, %s, %s)",
            (device_id, event_type, Jsonb({
                "alert_id": str(alert_id), "kind": kind,
                "temperature_c": temperature_c,
                "received_at": received_at.isoformat(),
            }), received_at),
        )
