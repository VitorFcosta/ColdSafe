from datetime import UTC, datetime
from unittest.mock import Mock

import pytest

from backend.app.domain.reading_classification import ReadingStatus
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
