from __future__ import annotations

import os
import json
from datetime import UTC, datetime, timedelta
from threading import Event
from time import monotonic, sleep
from uuid import uuid4

import pytest
from paho.mqtt import client as mqtt

from backend.app.domain.reading_classification import ReadingStatus
from backend.app.domain.telemetry import TelemetryPayload
from backend.app.repositories.influxdb_client import (
    InfluxSettings,
    create_influx_repository,
)
from backend.app.mqtt.subscriber import MqttSubscriber, MqttSubscriberSettings
from backend.app.services.telemetry_ingestion import TelemetryIngestionService


def _required_environment(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        pytest.skip(f"{name} is required for the InfluxDB integration test")
    return value


@pytest.mark.integration
def test_repository_round_trip_against_real_influxdb() -> None:
    settings = InfluxSettings(
        url=_required_environment("INFLUXDB_TEST_URL"),
        org=_required_environment("INFLUXDB_TEST_ORG"),
        bucket=_required_environment("INFLUXDB_TEST_BUCKET"),
        token=_required_environment("INFLUXDB_TEST_TOKEN"),
    )
    resources = create_influx_repository(settings)
    device_id = f"integration-{uuid4().hex}"
    latest_time = datetime.now(UTC)
    first_time = latest_time - timedelta(seconds=1)

    try:
        resources.repository.save(
            payload=TelemetryPayload(
                schema_version=1,
                device_id=device_id,
                temperature_c=5.1,
                humidity_percent=60.0,
            ),
            received_at=first_time,
            status=ReadingStatus.NORMAL,
        )
        resources.repository.save(
            payload=TelemetryPayload(
                schema_version=1,
                device_id=device_id,
                temperature_c=8.2,
                humidity_percent=61.0,
            ),
            received_at=latest_time,
            status=ReadingStatus.CRITICAL,
        )

        deadline = monotonic() + 5
        latest = None
        while latest is None and monotonic() < deadline:
            latest = resources.repository.get_latest(device_id)
            if latest is None:
                sleep(0.1)

        assert latest is not None
        assert latest.device_id == device_id
        assert latest.temperature_c == 8.2
        assert latest.humidity_percent == 61.0
        assert latest.status is ReadingStatus.CRITICAL
        assert latest.received_at == latest_time

        history = resources.repository.list_history(
            device_id=device_id,
            start=first_time - timedelta(seconds=1),
            end=latest_time + timedelta(seconds=1),
            limit=10,
        )

        assert [reading.temperature_c for reading in history] == [5.1, 8.2]
        assert [reading.status for reading in history] == [
            ReadingStatus.NORMAL,
            ReadingStatus.CRITICAL,
        ]
    finally:
        resources.close()


@pytest.mark.integration
def test_mqtt_message_is_classified_and_persisted_in_real_influxdb() -> None:
    resources = create_influx_repository(
        InfluxSettings(
            url=_required_environment("INFLUXDB_TEST_URL"),
            org=_required_environment("INFLUXDB_TEST_ORG"),
            bucket=_required_environment("INFLUXDB_TEST_BUCKET"),
            token=_required_environment("INFLUXDB_TEST_TOKEN"),
        )
    )
    mqtt_host = _required_environment("MQTT_TEST_HOST")
    mqtt_port = int(_required_environment("MQTT_TEST_PORT"))
    backend_password = _required_environment("MQTT_TEST_BACKEND_PASSWORD")
    device_password = _required_environment("MQTT_TEST_DEVICE_PASSWORD")
    device_id = f"integration-{uuid4().hex}"
    connected = Event()
    publisher = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"publisher-{uuid4().hex}",
        protocol=mqtt.MQTTv311,
    )
    publisher.username_pw_set("coldsafe-device", device_password)
    publisher.on_connect = lambda _client, _userdata, _flags, reason_code, _properties: (
        connected.set() if reason_code == 0 else None
    )
    subscriber = MqttSubscriber(
        settings=MqttSubscriberSettings(
            host=mqtt_host,
            port=mqtt_port,
            topic="coldsafe/v1/telemetry",
            qos=1,
            client_id=f"backend-{uuid4().hex}",
            username="coldsafe-backend",
            password=backend_password,
        ),
        handler=TelemetryIngestionService(repository=resources.repository),
    )

    try:
        subscriber.start()
        publisher.connect(mqtt_host, mqtt_port, keepalive=10)
        publisher.loop_start()
        assert connected.wait(timeout=3), "publisher did not connect to Mosquitto"

        message = json.dumps(
            {
                "schema_version": 1,
                "device_id": device_id,
                "temperature_c": 8.2,
                "humidity_percent": 61.0,
            }
        )
        latest = None
        deadline = monotonic() + 5
        while latest is None and monotonic() < deadline:
            publish_result = publisher.publish(
                "coldsafe/v1/telemetry",
                payload=message,
                qos=1,
                retain=False,
            )
            publish_result.wait_for_publish(timeout=2)
            sleep(0.1)
            latest = resources.repository.get_latest(device_id)

        assert latest is not None
        assert latest.device_id == device_id
        assert latest.status is ReadingStatus.CRITICAL
        assert latest.temperature_c == 8.2
    finally:
        publisher.loop_stop()
        publisher.disconnect()
        subscriber.stop()
        resources.close()
