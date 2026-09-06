from datetime import UTC, datetime
from unittest.mock import Mock, call, patch

import pytest
from influxdb_client.client.write_api import SYNCHRONOUS

from backend.app.domain.reading_classification import ReadingStatus
from backend.app.domain.telemetry import TelemetryPayload
from backend.app.repositories.influxdb_client import (
    InfluxRepositoryResources,
    InfluxSettings,
    create_influx_repository,
)


def settings():
    return InfluxSettings(
        url="http://influxdb:8086",
        org="coldsafe",
        bucket="telemetry",
        token="test-token",
    )


def test_settings_hide_token_from_representations():
    configuration = settings()

    assert configuration.token not in repr(configuration)
    assert configuration.token not in str(configuration)


@pytest.mark.parametrize("field", ["url", "org", "bucket", "token"])
def test_settings_reject_empty_required_values(field):
    values = {
        "url": "http://influxdb:8086",
        "org": "coldsafe",
        "bucket": "telemetry",
        "token": "test-token",
    }

    with pytest.raises(ValueError, match=f"{field} must not be empty"):
        InfluxSettings(**(values | {field: "  "}))


@pytest.mark.parametrize("url", ["influxdb:8086", "http://"])
def test_settings_reject_invalid_url(url):
    with pytest.raises(ValueError, match="url must use http or https"):
        InfluxSettings(
            url=url,
            org="coldsafe",
            bucket="telemetry",
            token="test-token",
        )


def test_settings_reject_url_with_embedded_credentials():
    with pytest.raises(ValueError, match="url must not contain credentials"):
        InfluxSettings(
            url="http://user:password@influxdb:8086",
            org="coldsafe",
            bucket="telemetry",
            token="test-token",
        )


@pytest.mark.parametrize(
    "url",
    [
        "http://influxdb:8086?token=secret",
        "http://influxdb:8086#secret",
    ],
)
def test_settings_reject_url_with_query_or_fragment(url):
    with pytest.raises(ValueError, match="url must not contain query or fragment"):
        InfluxSettings(
            url=url,
            org="coldsafe",
            bucket="telemetry",
            token="test-token",
        )


@patch("backend.app.repositories.influxdb_client.InfluxDBClient")
def test_factory_creates_synchronous_repository_resources(client_factory):
    client = client_factory.return_value
    write_api = client.write_api.return_value
    query_api = client.query_api.return_value

    resources = create_influx_repository(settings())

    client_factory.assert_called_once_with(
        url="http://influxdb:8086",
        token="test-token",
        org="coldsafe",
    )
    client.write_api.assert_called_once_with(write_options=SYNCHRONOUS)
    client.query_api.assert_called_once_with()
    resources.repository.save(
        payload=TelemetryPayload(
            schema_version=1,
            device_id="esp32-lab-01",
            temperature_c=5.4,
            humidity_percent=62.1,
        ),
        received_at=datetime(2026, 9, 6, 12, 0, tzinfo=UTC),
        status=ReadingStatus.NORMAL,
    )
    write_api.write.assert_called_once()

    query_api.query.return_value = []
    assert resources.repository.get_latest("esp32-lab-01") is None
    query_api.query.assert_called_once()


def test_resources_close_write_api_before_client():
    calls = Mock()
    write_api = calls.write_api
    client = calls.client
    resources = InfluxRepositoryResources(
        repository=Mock(),
        write_api=write_api,
        client=client,
    )

    resources.close()

    assert calls.mock_calls == [
        call.write_api.close(),
        call.client.close(),
    ]


def test_resources_report_readiness_from_influxdb_ping():
    client = Mock()
    client.ping.return_value = True
    resources = InfluxRepositoryResources(
        repository=Mock(),
        write_api=Mock(),
        client=client,
    )

    assert resources.is_ready() is True


def test_resources_report_not_ready_when_influxdb_ping_fails():
    client = Mock()
    client.ping.side_effect = OSError("connection refused")
    resources = InfluxRepositoryResources(
        repository=Mock(),
        write_api=Mock(),
        client=client,
    )

    assert resources.is_ready() is False


def test_resources_close_client_even_when_write_api_close_fails():
    write_api = Mock()
    client = Mock()
    write_api.close.side_effect = RuntimeError("flush failed")
    resources = InfluxRepositoryResources(
        repository=Mock(),
        write_api=write_api,
        client=client,
    )

    with pytest.raises(RuntimeError, match="flush failed"):
        resources.close()

    client.close.assert_called_once_with()


@patch("backend.app.repositories.influxdb_client.InfluxDBClient")
def test_factory_closes_created_resources_when_query_api_creation_fails(
    client_factory,
):
    client = client_factory.return_value
    write_api = client.write_api.return_value
    client.query_api.side_effect = RuntimeError("query setup failed")

    with pytest.raises(RuntimeError, match="query setup failed"):
        create_influx_repository(settings())

    write_api.close.assert_called_once_with()
    client.close.assert_called_once_with()


@patch("backend.app.repositories.influxdb_client.InfluxDBClient")
def test_factory_closes_client_when_write_api_creation_fails(client_factory):
    client = client_factory.return_value
    client.write_api.side_effect = RuntimeError("write setup failed")

    with pytest.raises(RuntimeError, match="write setup failed"):
        create_influx_repository(settings())

    client.close.assert_called_once_with()
