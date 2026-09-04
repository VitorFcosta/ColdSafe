import subprocess
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ENV_EXAMPLE_PATH = REPOSITORY_ROOT / ".env.example"
FIRMWARE_SECRETS_EXAMPLE_PATH = (
    REPOSITORY_ROOT / "firmware" / "include" / "secrets.example.h"
)

EXPECTED_ENVIRONMENT_KEYS = {
    "APP_ENV",
    "LOG_LEVEL",
    "CORS_ORIGINS",
    "MQTT_HOST",
    "MQTT_PORT",
    "MQTT_TOPIC",
    "MQTT_QOS",
    "MQTT_CLIENT_ID",
    "MQTT_BACKEND_USERNAME",
    "MQTT_BACKEND_PASSWORD",
    "MQTT_DEVICE_USERNAME",
    "MQTT_DEVICE_PASSWORD",
    "INFLUXDB_URL",
    "INFLUXDB_ORG",
    "INFLUXDB_BUCKET",
    "INFLUXDB_TOKEN",
    "DOCKER_INFLUXDB_INIT_MODE",
    "DOCKER_INFLUXDB_INIT_USERNAME",
    "DOCKER_INFLUXDB_INIT_PASSWORD",
    "DOCKER_INFLUXDB_INIT_ORG",
    "DOCKER_INFLUXDB_INIT_BUCKET",
    "DOCKER_INFLUXDB_INIT_ADMIN_TOKEN",
    "TEMP_MIN_C",
    "TEMP_MAX_C",
    "ATTENTION_MARGIN_C",
    "STALE_AFTER_SECONDS",
    "VITE_API_BASE_URL",
    "VITE_POLL_INTERVAL_MS",
}

SENSITIVE_ENVIRONMENT_KEYS = {
    "MQTT_BACKEND_PASSWORD",
    "MQTT_DEVICE_PASSWORD",
    "INFLUXDB_TOKEN",
    "DOCKER_INFLUXDB_INIT_USERNAME",
    "DOCKER_INFLUXDB_INIT_PASSWORD",
    "DOCKER_INFLUXDB_INIT_ADMIN_TOKEN",
}


def parse_environment_example():
    values = {}

    for raw_line in ENV_EXAMPLE_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        key, separator, value = line.partition("=")
        assert separator, f"Linha inválida em .env.example: {raw_line}"
        values[key] = value

    return values


def test_environment_example_contains_exactly_the_planned_keys():
    assert set(parse_environment_example()) == EXPECTED_ENVIRONMENT_KEYS


def test_environment_example_does_not_contain_secret_values():
    values = parse_environment_example()

    assert all(values[key] == "" for key in SENSITIVE_ENVIRONMENT_KEYS)


def test_environment_defaults_match_the_frozen_contracts():
    values = parse_environment_example()

    assert values["MQTT_TOPIC"] == "coldsafe/v1/telemetry"
    assert values["MQTT_QOS"] == "1"
    assert values["MQTT_BACKEND_USERNAME"] == "coldsafe-backend"
    assert values["MQTT_DEVICE_USERNAME"] == "coldsafe-device"
    assert values["TEMP_MIN_C"] == "2"
    assert values["TEMP_MAX_C"] == "8"
    assert values["ATTENTION_MARGIN_C"] == "0.5"
    assert values["STALE_AFTER_SECONDS"] == "30"
    assert values["VITE_POLL_INTERVAL_MS"] == "5000"


def test_firmware_secret_template_uses_explicit_placeholders():
    content = FIRMWARE_SECRETS_EXAMPLE_PATH.read_text(encoding="utf-8")

    assert 'WIFI_SSID[] = "Wokwi-GUEST"' in content
    assert 'MQTT_HOST[] = "host.wokwi.internal"' in content
    assert 'DEVICE_ID[] = "esp32-lab-01"' in content
    assert 'MQTT_USERNAME[] = "coldsafe-device"' in content
    assert 'MQTT_PASSWORD[] = "REPLACE_WITH_MQTT_DEVICE_PASSWORD"' in content


def test_runtime_versions_are_pinned():
    assert (REPOSITORY_ROOT / ".python-version").read_text().strip() == "3.13.15"
    assert (REPOSITORY_ROOT / ".nvmrc").read_text().strip() == "24.20.0"


def git_ignores(path):
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "--quiet", path],
        cwd=REPOSITORY_ROOT,
        check=False,
    )
    return result.returncode == 0


def test_real_secret_files_are_ignored_but_examples_are_versionable():
    assert git_ignores(".env")
    assert git_ignores(".env.local")
    assert git_ignores("firmware/include/secrets.h")
    assert git_ignores("infra/mosquitto/config/passwords")
    assert not git_ignores(".env.example")
    assert not git_ignores("firmware/include/secrets.example.h")
