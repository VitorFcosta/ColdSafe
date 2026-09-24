import os
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
from uuid import uuid4

import pytest

from backend.app.config.settings import RuntimeSettings
from backend.app.domain.reading_classification import TemperatureThresholds
from backend.app.repositories.postgres import connect, initialize_schema
from backend.app.services.alerts import AlertService
from backend.app.services.commands import CommandService


def postgres_settings() -> RuntimeSettings:
    password = os.getenv("POSTGRES_TEST_PASSWORD")
    if not password:
        pytest.skip("POSTGRES_TEST_PASSWORD is required for PostgreSQL integration")
    return RuntimeSettings(
        mqtt_host="unused", mqtt_port=1883, mqtt_topic="unused", mqtt_qos=1,
        mqtt_client_id="unused", mqtt_backend_username="unused", mqtt_backend_password="unused",
        influxdb_url="http://localhost:8086", influxdb_org="unused",
        influxdb_bucket="unused", influxdb_token="unused",
        postgres_host=os.getenv("POSTGRES_TEST_HOST", "127.0.0.1"),
        postgres_port=int(os.getenv("POSTGRES_TEST_PORT", "15432")),
        postgres_db=os.getenv("POSTGRES_TEST_DB", "coldsafe"),
        postgres_user=os.getenv("POSTGRES_TEST_USER", "coldsafe"),
        postgres_password=password, _env_file=None,
    )


@pytest.mark.integration
def test_alert_lifecycle_hysteresis_and_buzzer_transitions() -> None:
    settings = postgres_settings()
    initialize_schema(settings)
    mqtt_id = f"alert-{uuid4().hex}"
    with connect(settings) as connection:
        user_id = connection.execute(
            "INSERT INTO users (email, password_hash) VALUES (%s, 'hash') RETURNING id",
            (f"{mqtt_id}@example.invalid",),
        ).fetchone()[0]
        environment_id = connection.execute(
            "INSERT INTO environments (owner_user_id, name) "
            "VALUES (%s, 'Alerts') RETURNING id", (user_id,),
        ).fetchone()[0]
        device_id = connection.execute(
            "INSERT INTO devices (environment_id, mqtt_device_id, name) "
            "VALUES (%s, %s, 'Sensor') RETURNING id", (environment_id, mqtt_id),
        ).fetchone()[0]

    publisher = Mock(return_value=True)
    command_service = CommandService(settings, publisher)
    command = Mock(side_effect=lambda device, mqtt, state: command_service.request(
        device, mqtt, "buzzer", state, "automatic", None
    ))
    service = AlertService(settings, command)
    thresholds = TemperatureThresholds(min_c=2, max_c=8, attention_margin_c=0.5)
    start = datetime.now(UTC)

    try:
        # One low occurrence survives repeated readings and the recovery margin.
        for offset, temperature in enumerate((1.0, 1.0, 2.2)):
            service.evaluate(device_id, mqtt_id, temperature, thresholds,
                             start + timedelta(seconds=offset))
        with connect(settings) as connection:
            low_id = connection.execute(
                "SELECT id FROM alerts WHERE device_id = %s AND kind = 'temperature_low' "
                "AND closed_at IS NULL", (device_id,),
            ).fetchone()[0]
        command.assert_called_once_with(device_id, mqtt_id, True)

        # An opposite violation replaces the occurrence without toggling the buzzer.
        service.evaluate(device_id, mqtt_id, 9.0, thresholds, start + timedelta(seconds=3))
        service.evaluate(device_id, mqtt_id, 7.8, thresholds, start + timedelta(seconds=4))
        with connect(settings) as connection:
            assert connection.execute(
                "SELECT closed_at FROM alerts WHERE id = %s", (low_id,),
            ).fetchone()[0] is not None
            assert connection.execute(
                "SELECT count(*) FROM alerts WHERE device_id = %s AND closed_at IS NULL",
                (device_id,),
            ).fetchone()[0] == 1
        command.assert_called_once_with(device_id, mqtt_id, True)

        service.evaluate(device_id, mqtt_id, 7.5, thresholds, start + timedelta(seconds=5))
        service.evaluate(device_id, mqtt_id, 7.5, thresholds, start + timedelta(seconds=6))
        assert [call.args[2] for call in command.call_args_list] == [True, False]
        with connect(settings) as connection:
            assert connection.execute(
                "SELECT kind, count(*) FROM alerts WHERE device_id = %s GROUP BY kind ORDER BY kind",
                (device_id,),
            ).fetchall() == [("temperature_high", 1), ("temperature_low", 1)]
            assert connection.execute(
                "SELECT event_type, count(*) FROM audit_events WHERE device_id = %s "
                "AND event_type IN ('alert_opened', 'alert_closed') "
                "GROUP BY event_type ORDER BY event_type", (device_id,),
            ).fetchall() == [("alert_closed", 2), ("alert_opened", 2)]

        # A failed publication is retried after its 10-second deadline, not per reading.
        publisher.reset_mock()
        publisher.side_effect = [False, True]
        service.evaluate(device_id, mqtt_id, 9.0, thresholds, start + timedelta(seconds=7))
        service.evaluate(device_id, mqtt_id, 9.0, thresholds, start + timedelta(seconds=8))
        assert publisher.call_count == 1
        service.evaluate(device_id, mqtt_id, 9.0, thresholds, start + timedelta(seconds=18))
        assert publisher.call_count == 2
    finally:
        with connect(settings) as connection:
            connection.execute("DELETE FROM audit_events WHERE device_id = %s", (device_id,))
            connection.execute("DELETE FROM actuator_commands WHERE device_id = %s", (device_id,))
            connection.execute("DELETE FROM alerts WHERE device_id = %s", (device_id,))
            connection.execute("DELETE FROM devices WHERE id = %s", (device_id,))
            connection.execute("DELETE FROM environment_rules WHERE environment_id = %s", (environment_id,))
            connection.execute("DELETE FROM environments WHERE id = %s", (environment_id,))
            connection.execute("DELETE FROM users WHERE id = %s", (user_id,))


def test_rejects_invalid_reading_before_database_access() -> None:
    service = AlertService(Mock(), Mock())
    with pytest.raises(ValueError, match="finite"):
        service.evaluate(uuid4(), "device", float("nan"), TemperatureThresholds(),
                         datetime.now(UTC))
    with pytest.raises(ValueError, match="thresholds"):
        service.evaluate(uuid4(), "device", 4, TemperatureThresholds(2, 8, 3),
                         datetime.now(UTC))
