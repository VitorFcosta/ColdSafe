from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from backend.app.config.settings import RuntimeSettings
from backend.app.domain.reading_classification import ReadingStatus
from backend.app.domain.telemetry import TelemetryPayload
from backend.app.errors import DeviceNotFoundError
from backend.app.runtime import build_runtime_app


def settings() -> RuntimeSettings:
    return RuntimeSettings(
        mqtt_host="mosquitto",
        mqtt_port=1883,
        mqtt_topic="coldsafe/v1/telemetry",
        mqtt_qos=1,
        mqtt_client_id="coldsafe-backend",
        mqtt_backend_username="coldsafe-backend",
        mqtt_backend_password="mqtt-secret",
        influxdb_url="http://influxdb:8086",
        influxdb_org="coldsafe",
        influxdb_bucket="telemetry",
        influxdb_token="influx-secret",
        postgres_host="postgres",
        postgres_port=5432,
        postgres_db="coldsafe",
        postgres_user="coldsafe",
        postgres_password="postgres-secret",
    )


@patch("backend.app.runtime.MqttSubscriber")
@patch("backend.app.runtime.create_influx_repository")
def test_runtime_starts_and_closes_infrastructure(
    create_repository: Mock, subscriber_factory: Mock
) -> None:
    resources = create_repository.return_value
    resources.is_ready.return_value = True
    subscriber = subscriber_factory.return_value
    application = build_runtime_app(settings())

    with patch("backend.app.runtime.initialize_schema") as initialize, patch(
        "backend.app.runtime.postgres_is_ready", return_value=True
    ) as postgres_ready:
        with TestClient(application) as client:
            response = client.get("/health/ready")

    assert response.status_code == 200
    initialize.assert_called_once()
    postgres_ready.assert_called_once()
    subscriber.start.assert_called_once_with()
    subscriber.stop.assert_called_once_with()
    resources.close.assert_called_once_with()


@patch("backend.app.runtime.MqttSubscriber")
@patch("backend.app.runtime.create_influx_repository")
def test_runtime_closes_repository_when_subscriber_start_fails(
    create_repository: Mock, subscriber_factory: Mock
) -> None:
    resources = create_repository.return_value
    subscriber_factory.return_value.start.side_effect = RuntimeError("broker down")
    application = build_runtime_app(settings())

    with patch("backend.app.runtime.initialize_schema"):
        try:
            with TestClient(application):
                pass
        except RuntimeError as exc:
            assert str(exc) == "broker down"
        else:
            raise AssertionError("startup failure should propagate")

    resources.close.assert_called_once_with()


@patch("backend.app.runtime.MqttSubscriber")
@patch("backend.app.runtime.create_influx_repository")
def test_runtime_closes_repository_when_postgres_start_fails(
    create_repository: Mock, subscriber_factory: Mock
) -> None:
    resources = create_repository.return_value
    application = build_runtime_app(settings())

    with patch("backend.app.runtime.initialize_schema", side_effect=RuntimeError("database down")):
        try:
            with TestClient(application):
                pass
        except RuntimeError as exc:
            assert str(exc) == "database down"
        else:
            raise AssertionError("startup failure should propagate")

    subscriber_factory.return_value.start.assert_not_called()
    resources.close.assert_called_once_with()


@patch("backend.app.runtime.CatalogService")
@patch("backend.app.runtime.MqttSubscriber")
@patch("backend.app.runtime.create_influx_repository")
def test_runtime_ingestion_uses_registered_rules_and_rejects_inactive_device(
    create_repository: Mock, subscriber_factory: Mock, catalog_factory: Mock
) -> None:
    build_runtime_app(settings())
    handler = subscriber_factory.call_args.kwargs["handler"]
    catalog = catalog_factory.return_value
    catalog.active_device.return_value = {"environment_id": "owned-environment"}
    catalog.thresholds_for_environment.return_value = {
        "min_c": 4, "max_c": 6, "attention_margin_c": 0.5,
    }
    payload = TelemetryPayload(
        schema_version=1, device_id="owned-device", temperature_c=7,
        humidity_percent=60,
    )

    handler(payload)

    assert create_repository.return_value.repository.save.call_args.kwargs["status"] == ReadingStatus.CRITICAL
    catalog.thresholds_for_environment.assert_called_once_with("owned-environment")

    catalog.active_device.return_value = None
    catalog.registered_device.return_value = {"is_active": False}
    try:
        handler(payload)
    except DeviceNotFoundError:
        pass
    else:
        raise AssertionError("inactive device telemetry must be rejected")
    create_repository.return_value.repository.save.assert_called_once()
