from pydantic import ValidationError
import pytest

from backend.app.config.settings import RuntimeSettings


def valid_settings() -> dict[str, object]:
    return {
        "mqtt_host": "mosquitto",
        "mqtt_port": 1883,
        "mqtt_topic": "coldsafe/v1/telemetry",
        "mqtt_qos": 1,
        "mqtt_client_id": "coldsafe-backend",
        "mqtt_backend_username": "coldsafe-backend",
        "mqtt_backend_password": "mqtt-secret",
        "influxdb_url": "http://influxdb:8086",
        "influxdb_org": "coldsafe",
        "influxdb_bucket": "telemetry",
        "influxdb_token": "influx-secret",
    }


def test_runtime_settings_hide_secrets_from_representations() -> None:
    settings = RuntimeSettings(**valid_settings())

    assert "mqtt-secret" not in repr(settings)
    assert "influx-secret" not in repr(settings)


def test_runtime_settings_parse_numeric_values_from_environment(monkeypatch) -> None:
    for name, value in valid_settings().items():
        monkeypatch.setenv(name.upper(), str(value))

    settings = RuntimeSettings(_env_file=None)

    assert settings.mqtt_port == 1883
    assert settings.mqtt_qos == 1


@pytest.mark.parametrize("field", ["mqtt_backend_password", "influxdb_token"])
def test_runtime_settings_fail_early_when_secret_is_missing(field: str) -> None:
    values = valid_settings() | {field: ""}

    with pytest.raises(ValidationError):
        RuntimeSettings(**values)
