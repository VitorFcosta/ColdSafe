from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from backend.app.config.settings import RuntimeSettings
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

    with TestClient(application) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
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

    try:
        with TestClient(application):
            pass
    except RuntimeError as exc:
        assert str(exc) == "broker down"
    else:
        raise AssertionError("startup failure should propagate")

    resources.close.assert_called_once_with()
