from __future__ import annotations

import json
import os
from threading import Event
from time import monotonic, sleep
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen
from uuid import uuid4

import pytest
from paho.mqtt import client as mqtt


DEVICE_ID = "esp32-lab-01"
MQTT_TOPIC = "coldsafe/v1/telemetry"


def _required_environment(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        pytest.skip(f"{name} is required for the runtime pipeline integration test")
    return value


def _get_json(url: str) -> dict[str, object]:
    with urlopen(url, timeout=2) as response:  # noqa: S310 - local test URL
        assert response.status == 200
        return json.load(response)


@pytest.mark.integration
def test_mqtt_publication_reaches_summary_and_history_api() -> None:
    mqtt_host = _required_environment("MQTT_TEST_HOST")
    mqtt_port = int(_required_environment("MQTT_TEST_PORT"))
    device_password = _required_environment("MQTT_TEST_DEVICE_PASSWORD")
    api_url = _required_environment("API_TEST_URL").rstrip("/")
    connected = Event()
    run_id = uuid4().hex
    publisher = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"pipeline-test-{run_id}",
        protocol=mqtt.MQTTv311,
    )
    publisher.username_pw_set("coldsafe-device", device_password)
    publisher.on_connect = lambda _client, _userdata, _flags, reason_code, _props: (
        connected.set() if reason_code == 0 else None
    )
    temperature_c = round(8.1 + int(run_id[:6], 16) / 100_000_000, 8)
    humidity_percent = 61.234

    try:
        publisher.connect(mqtt_host, mqtt_port, keepalive=10)
        publisher.loop_start()
        assert connected.wait(timeout=3), "publisher did not connect to Mosquitto"

        result = publisher.publish(
            MQTT_TOPIC,
            payload=json.dumps(
                {
                    "schema_version": 1,
                    "device_id": DEVICE_ID,
                    "temperature_c": temperature_c,
                    "humidity_percent": humidity_percent,
                }
            ),
            qos=1,
            retain=False,
        )
        result.wait_for_publish(timeout=3)
        assert result.is_published(), "Mosquitto did not acknowledge the QoS 1 message"

        summary = None
        deadline = monotonic() + 10
        while monotonic() < deadline:
            try:
                candidate = _get_json(f"{api_url}/api/v1/monitoring/summary")
                reading = candidate["data"]["reading"]  # type: ignore[index]
                if reading and reading["temperature_c"] == temperature_c:
                    summary = candidate
                    break
            except (KeyError, TypeError, URLError):
                pass
            sleep(0.2)

        assert summary is not None, "published MQTT reading did not reach the summary API"
        assert summary["data"]["status"] == "critical"  # type: ignore[index]
        assert summary["data"]["reading"]["humidity_percent"] == humidity_percent  # type: ignore[index]

        query = urlencode({"device_id": DEVICE_ID, "period": "1h", "limit": 20})
        history = _get_json(f"{api_url}/api/v1/readings?{query}")
        readings = history["data"]["readings"]  # type: ignore[index]
        assert any(
            reading["temperature_c"] == temperature_c
            and reading["humidity_percent"] == humidity_percent
            for reading in readings
        )
    finally:
        publisher.loop_stop()
        publisher.disconnect()
