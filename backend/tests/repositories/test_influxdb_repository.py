from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend.app.domain.reading_classification import ReadingStatus
from backend.app.domain.telemetry import TelemetryPayload
from backend.app.repositories.influxdb import InfluxReadingRepository, StoredReading


RECEIVED_AT = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)


@pytest.fixture
def write_api():
    return Mock()


@pytest.fixture
def query_api():
    return Mock()


@pytest.fixture
def repository(write_api, query_api):
    return InfluxReadingRepository(
        write_api=write_api,
        query_api=query_api,
        bucket="telemetry",
        org="coldsafe",
    )


def flux_tables(*rows):
    records = [SimpleNamespace(values=row) for row in rows]
    return [SimpleNamespace(records=records)]


def test_save_writes_valid_reading_with_utc_timestamp(repository, write_api):
    payload = TelemetryPayload(
        schema_version=1,
        device_id="esp32-lab-01",
        temperature_c=5.4,
        humidity_percent=62.1,
    )

    repository.save(
        payload=payload,
        received_at=RECEIVED_AT,
        status=ReadingStatus.NORMAL,
    )

    write_api.write.assert_called_once_with(
        bucket="telemetry",
        org="coldsafe",
        record={
            "measurement": "environment_reading",
            "tags": {
                "device_id": "esp32-lab-01",
                "status": "normal",
            },
            "fields": {
                "schema_version": 1,
                "temperature_c": 5.4,
                "humidity_percent": 62.1,
            },
            "time": RECEIVED_AT,
        },
    )


def test_save_normalizes_aware_timestamp_to_utc(repository, write_api):
    local_time = datetime(
        2026,
        9,
        5,
        9,
        0,
        tzinfo=timezone(timedelta(hours=-3)),
    )
    payload = TelemetryPayload(
        schema_version=1,
        device_id="esp32-lab-01",
        temperature_c=5.4,
        humidity_percent=62.1,
    )

    repository.save(
        payload=payload,
        received_at=local_time,
        status=ReadingStatus.NORMAL,
    )

    assert write_api.write.call_args.kwargs["record"]["time"] == RECEIVED_AT


def test_save_rejects_timestamp_without_timezone(repository):
    payload = TelemetryPayload(
        schema_version=1,
        device_id="esp32-lab-01",
        temperature_c=5.4,
        humidity_percent=62.1,
    )

    with pytest.raises(ValueError, match="received_at must be timezone-aware"):
        repository.save(
            payload=payload,
            received_at=datetime(2026, 9, 5, 12, 0),
            status=ReadingStatus.NORMAL,
        )


def test_get_latest_returns_none_when_device_has_no_reading(repository, query_api):
    query_api.query.return_value = []

    reading = repository.get_latest("esp32-lab-01")

    assert reading is None


def test_get_latest_maps_result_and_binds_device_id(repository, query_api):
    query_api.query.return_value = flux_tables(
        {
            "_time": RECEIVED_AT,
            "device_id": "esp32-lab-01",
            "status": "normal",
            "schema_version": 1,
            "temperature_c": 5.4,
            "humidity_percent": 62.1,
        }
    )

    reading = repository.get_latest("esp32-lab-01")

    assert reading == StoredReading(
        schema_version=1,
        device_id="esp32-lab-01",
        temperature_c=5.4,
        humidity_percent=62.1,
        status=ReadingStatus.NORMAL,
        received_at=RECEIVED_AT,
    )
    query_call = query_api.query.call_args.kwargs
    assert query_call["org"] == "coldsafe"
    assert query_call["params"] == {
        "_bucket": "telemetry",
        "_device_id": "esp32-lab-01",
    }
    assert "_device_id" in query_call["query"]
    assert "esp32-lab-01" not in query_call["query"]
    assert query_call["query"].index("|> group") < query_call["query"].index(
        "|> sort"
    )


def test_list_history_returns_latest_limited_rows_in_chronological_order(
    repository,
    query_api,
):
    start = datetime(2026, 9, 5, 11, 0, tzinfo=UTC)
    end = datetime(2026, 9, 5, 13, 0, tzinfo=UTC)
    earlier = RECEIVED_AT
    later = datetime(2026, 9, 5, 12, 5, tzinfo=UTC)
    query_api.query.return_value = flux_tables(
        {
            "_time": earlier,
            "device_id": "esp32-lab-01",
            "status": "normal",
            "schema_version": 1,
            "temperature_c": 5.4,
            "humidity_percent": 62.1,
        },
        {
            "_time": later,
            "device_id": "esp32-lab-01",
            "status": "attention",
            "schema_version": 1,
            "temperature_c": 7.8,
            "humidity_percent": 63.0,
        },
    )

    readings = repository.list_history(
        device_id="esp32-lab-01",
        start=start,
        end=end,
        limit=2,
    )

    assert readings == (
        StoredReading(
            schema_version=1,
            device_id="esp32-lab-01",
            temperature_c=5.4,
            humidity_percent=62.1,
            status=ReadingStatus.NORMAL,
            received_at=earlier,
        ),
        StoredReading(
            schema_version=1,
            device_id="esp32-lab-01",
            temperature_c=7.8,
            humidity_percent=63.0,
            status=ReadingStatus.ATTENTION,
            received_at=later,
        ),
    )
    query_call = query_api.query.call_args.kwargs
    assert query_call["params"] == {
        "_bucket": "telemetry",
        "_device_id": "esp32-lab-01",
        "_start": start,
        "_end": end,
        "_limit": 2,
    }
    assert "_device_id" in query_call["query"]
    assert "esp32-lab-01" not in query_call["query"]
    assert query_call["query"].index("|> group") < query_call["query"].index(
        "|> limit"
    )


@pytest.mark.parametrize("limit", [0, 1001])
def test_list_history_rejects_limits_outside_contract(repository, limit):
    with pytest.raises(ValueError, match="limit must be between 1 and 1000"):
        repository.list_history(
            device_id="esp32-lab-01",
            start=datetime(2026, 9, 5, 11, 0, tzinfo=UTC),
            end=datetime(2026, 9, 5, 13, 0, tzinfo=UTC),
            limit=limit,
        )


def test_list_history_rejects_invalid_time_range(repository):
    with pytest.raises(ValueError, match="start must be before end"):
        repository.list_history(
            device_id="esp32-lab-01",
            start=RECEIVED_AT,
            end=RECEIVED_AT,
            limit=300,
        )


def test_list_history_rejects_timestamp_without_timezone(repository):
    with pytest.raises(ValueError, match="start must be timezone-aware"):
        repository.list_history(
            device_id="esp32-lab-01",
            start=datetime(2026, 9, 5, 11, 0),
            end=datetime(2026, 9, 5, 13, 0, tzinfo=UTC),
            limit=300,
        )
