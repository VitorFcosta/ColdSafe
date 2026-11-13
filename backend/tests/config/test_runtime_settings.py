import secrets

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
        "postgres_host": "postgres",
        "postgres_port": 5432,
        "postgres_db": "coldsafe",
        "postgres_user": "coldsafe",
        "postgres_password": "postgres-secret",
        "auth_jwt_secret": secrets.token_urlsafe(48),
    }


def test_runtime_settings_hide_secrets_from_representations() -> None:
    settings = RuntimeSettings(**valid_settings())

    assert "mqtt-secret" not in repr(settings)
    assert "influx-secret" not in repr(settings)
    assert "postgres-secret" not in repr(settings)


def test_model_worker_inference_password_is_optional_private_and_not_empty(monkeypatch):
    original = RuntimeSettings(**valid_settings(), _env_file=None)
    assert original.rabbitmq_inference_password is None
    monkeypatch.setenv('RABBITMQ_INFERENCE_PASSWORD', 'private-model-worker-secret')
    configured = RuntimeSettings(**valid_settings(), _env_file=None)
    assert configured.rabbitmq_inference_password.get_secret_value() == 'private-model-worker-secret'
    assert 'private-model-worker-secret' not in repr(configured)
    with pytest.raises(ValidationError):
        RuntimeSettings(**valid_settings(), rabbitmq_inference_password='', _env_file=None)


def test_runtime_settings_parse_numeric_values_from_environment(monkeypatch) -> None:
    for name, value in valid_settings().items():
        monkeypatch.setenv(name.upper(), str(value))

    settings = RuntimeSettings(_env_file=None)

    assert settings.mqtt_port == 1883
    assert settings.mqtt_qos == 1
    assert settings.postgres_port == 5432


@pytest.mark.parametrize("field", ["mqtt_backend_password", "influxdb_token", "postgres_password", "auth_jwt_secret"])
def test_runtime_settings_fail_early_when_secret_is_missing(field: str) -> None:
    values = valid_settings() | {field: ""}

    with pytest.raises(ValidationError):
        RuntimeSettings(**values)


def test_runtime_requires_strong_jwt_secret_and_hides_it(monkeypatch) -> None:
    values = valid_settings()
    key = values["auth_jwt_secret"]
    for invalid in ("", "short-key"):
        with pytest.raises(ValidationError):
            RuntimeSettings(**(values | {"auth_jwt_secret": invalid}), _env_file=None)
    assert key not in repr(RuntimeSettings(**values, _env_file=None))
    monkeypatch.delenv("AUTH_JWT_SECRET", raising=False)
    with pytest.raises(ValidationError):
        RuntimeSettings(**{k: v for k, v in values.items() if k != "auth_jwt_secret"}, _env_file=None)
