from datetime import UTC, datetime
from unittest.mock import Mock

from backend.app.domain.reading_classification import ReadingStatus, TemperatureThresholds
from backend.app.repositories.influxdb import StoredReading
from backend.app.services.monitoring import MonitoringService


NOW = datetime(2026, 9, 24, 12, tzinfo=UTC)


def test_summary_uses_selected_device_and_its_limits() -> None:
    repository = Mock()
    repository.get_latest.return_value = StoredReading(
        schema_version=1,
        device_id="esp32-lab-02",
        temperature_c=7,
        humidity_percent=60,
        status=ReadingStatus.NORMAL,
        received_at=NOW,
    )
    service = MonitoringService(repository=repository, clock=lambda: NOW)

    summary = service.get_summary(
        device_id="esp32-lab-02",
        thresholds=TemperatureThresholds(min_c=4, max_c=6, attention_margin_c=0.5),
    )

    repository.get_latest.assert_called_once_with("esp32-lab-02")
    assert summary.status == ReadingStatus.CRITICAL
    assert summary.thresholds.max_c == 6


def test_history_queries_selected_device() -> None:
    repository = Mock()
    repository.list_history.return_value = ()

    MonitoringService(repository=repository, clock=lambda: NOW).list_history(
        device_id="esp32-lab-02", period="1h", limit=20
    )

    assert repository.list_history.call_args.kwargs["device_id"] == "esp32-lab-02"
