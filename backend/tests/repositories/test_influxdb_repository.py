from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock
import copy
import json
from pathlib import Path

import pytest

from backend.app.domain.reading_classification import ReadingStatus
from backend.app.domain.telemetry import TelemetryPayload
from backend.app.errors import DependencyUnavailableError
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


def test_v2_light_is_written_and_legacy_rows_remain_readable(repository, write_api, query_api):
    payload = TelemetryPayload(schema_version=2, device_id="esp32-lab-02",
                               temperature_c=4.2, humidity_percent=55, light_percent=43.2)
    repository.save(payload=payload, received_at=RECEIVED_AT, status=ReadingStatus.NORMAL)
    assert write_api.write.call_args.kwargs["record"]["fields"]["light_percent"] == 43.2
    query_api.query.return_value = flux_tables({
        "_time": RECEIVED_AT, "device_id": "esp32-lab-02", "status": "normal",
        "schema_version": 2, "temperature_c": 4.2, "humidity_percent": 55,
        "light_percent": 43.2,
    })
    assert repository.get_latest("esp32-lab-02").light_percent == 43.2


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


def test_save_translates_influx_client_failure(repository, write_api):
    write_api.write.side_effect = OSError("connection refused")

    with pytest.raises(DependencyUnavailableError, match="write failed"):
        repository.save(
            payload=TelemetryPayload(
                schema_version=1,
                device_id="esp32-lab-01",
                temperature_c=5.4,
                humidity_percent=62.1,
            ),
            received_at=RECEIVED_AT,
            status=ReadingStatus.NORMAL,
        )


def test_query_translates_influx_client_failure(repository, query_api):
    query_api.query.side_effect = OSError("connection refused")

    with pytest.raises(DependencyUnavailableError, match="query failed"):
        repository.get_latest("esp32-lab-01")


def accepted_event():
    examples = json.loads((Path(__file__).resolve().parents[3] /
                           'contracts/examples/aiot.valid.json').read_text())
    event = next(item['payload'] for item in examples if item['name'] == 'telemetry_edge')
    event['received_at'] = '2026-10-12T18:00:00.123456Z'
    return event


def test_save_event_keeps_six_sensors_identity_states_and_stable_point(repository, write_api):
    event = accepted_event()
    original = copy.deepcopy(event)
    repository.save_event(event=event)
    repository.save_event(event=event)
    assert write_api.write.call_args_list[0] == write_api.write.call_args_list[1]
    record = write_api.write.call_args.kwargs['record']
    assert record['measurement'] == 'equipment_reading_v3'
    assert record['tags'] == {key: event[key] for key in
                              ('device_id', 'device_record_id', 'environment_id', 'event_id')} | {
                                  'equipment_id': event['data']['equipment']['equipment_id']}
    assert record['time'] == event['received_at']
    fields = record['fields']
    for role, field in (
        ('ambient_temperature', 'ambient_temperature_c'), ('humidity', 'humidity_percent'),
        ('light', 'light_percent'), ('vibration', 'vibration_rms_mm_s'),
        ('motor_current', 'motor_current_a'), ('motor_temperature', 'motor_temperature_c'),
    ):
        assert fields[field] == event['data']['measurements'][role]['value']
        assert type(fields[field]) is float  # JSON integers must not create Influx field conflicts.
        assert fields[role + '_sensor_id'] == event['data']['measurements'][role]['sensor_id']
    assert fields['running'] is True
    for role in ('led', 'buzzer'):
        assert fields[role + '_actual_state'] == event['data']['actuators'][role]['actual_state']
        assert fields[role + '_actuator_id'] == event['data']['actuators'][role]['actuator_id']
    assert fields['occurred_at'] == event['occurred_at']
    assert fields['received_at'] == event['received_at']
    assert fields['correlation_id'] == event['event_id']
    assert event == original


def test_save_event_translates_failure_without_exposing_details(repository, write_api):
    write_api.write.side_effect = OSError('private-token-payload')
    with pytest.raises(DependencyUnavailableError, match='^InfluxDB write failed$'):
        repository.save_event(event=accepted_event())
