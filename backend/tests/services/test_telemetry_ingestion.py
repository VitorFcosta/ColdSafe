from datetime import UTC, datetime
from unittest.mock import Mock

import pytest

from backend.app.domain.reading_classification import ReadingStatus, TemperatureThresholds
from backend.app.domain.telemetry import TelemetryPayload
from backend.app.services.telemetry_ingestion import TelemetryIngestionService


def telemetry_payload(*, temperature_c: float = 5.0) -> TelemetryPayload:
    return TelemetryPayload(
        schema_version=1,
        device_id="esp32-lab-01",
        temperature_c=temperature_c,
        humidity_percent=62.0,
    )


def test_validated_telemetry_is_classified_and_saved_with_receive_time() -> None:
    repository = Mock()
    received_at = datetime(2026, 9, 6, 21, 0, tzinfo=UTC)
    clock = Mock(return_value=received_at)
    service = TelemetryIngestionService(repository=repository, clock=clock)
    payload = telemetry_payload(temperature_c=8.2)

    service(payload)

    clock.assert_called_once_with()
    repository.save.assert_called_once_with(
        payload=payload,
        received_at=received_at,
        status=ReadingStatus.CRITICAL,
    )


def test_repository_failure_propagates_so_mqtt_message_is_not_acknowledged() -> None:
    repository = Mock()
    repository.save.side_effect = RuntimeError("InfluxDB unavailable")
    service = TelemetryIngestionService(
        repository=repository,
        clock=lambda: datetime(2026, 9, 6, 21, 0, tzinfo=UTC),
    )

    with pytest.raises(RuntimeError, match="InfluxDB unavailable"):
        service(telemetry_payload())


def test_ingestion_uses_registered_device_thresholds() -> None:
    repository = Mock()
    service = TelemetryIngestionService(
        repository=repository,
        clock=lambda: datetime(2026, 9, 6, 21, 0, tzinfo=UTC),
        thresholds_for_device=lambda device_id: TemperatureThresholds(
            min_c=4, max_c=6, attention_margin_c=0.5
        ),
    )

    service(telemetry_payload(temperature_c=7))

    assert repository.save.call_args.kwargs["status"] == ReadingStatus.CRITICAL


def test_unknown_device_is_not_persisted() -> None:
    repository = Mock()

    def unknown_device(_device_id: str) -> TemperatureThresholds:
        raise ValueError("unknown")

    service = TelemetryIngestionService(
        repository=repository,
        thresholds_for_device=unknown_device,
    )

    with pytest.raises(ValueError, match="unknown"):
        service(telemetry_payload())
    repository.save.assert_not_called()


def test_automation_runs_only_after_persistence() -> None:
    calls = []
    repository = Mock()
    repository.save.side_effect = lambda **kwargs: calls.append("saved")
    service = TelemetryIngestionService(
        repository=repository,
        after_save=lambda payload, received_at, thresholds: calls.append("automated"),
    )

    service(telemetry_payload())
    assert calls == ["saved", "automated"]


def test_failed_automation_does_not_repeat_successful_influx_write(caplog) -> None:
    repository = Mock()
    service = TelemetryIngestionService(
        repository=repository,
        after_save=Mock(side_effect=RuntimeError("database unavailable")),
    )

    service(telemetry_payload())

    repository.save.assert_called_once()
    assert "Telemetry automation failed: error_type=RuntimeError" in caplog.text
