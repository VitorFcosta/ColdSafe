"""Lifecycle-managed MQTT telemetry subscriber."""

import logging
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import paho.mqtt.client as mqtt
from pydantic import ValidationError

from backend.app.domain.telemetry import (
    TelemetryPayload,
    TelemetryPayloadTooLargeError,
    parse_telemetry_payload,
)
from backend.app.domain.commands import parse_ack_payload
from backend.app.errors import DeviceNotFoundError


LOGGER = logging.getLogger(__name__)
V2_TOPIC = re.compile(r"^coldsafe/v2/devices/([A-Za-z0-9._-]{1,64})/(telemetry|acks)$")


@dataclass(frozen=True, slots=True)
class MqttSubscriberSettings:
    """Validated connection values required by the subscriber."""

    host: str
    port: int
    topic: str
    qos: int
    client_id: str
    username: str
    password: str = field(repr=False)
    keepalive_seconds: int = 60

    def __post_init__(self) -> None:
        for name in ("host", "topic", "client_id", "username", "password"):
            if not getattr(self, name):
                raise ValueError(f"{name} must not be empty")
        if not 1 <= self.port <= 65_535:
            raise ValueError("port must be between 1 and 65535")
        if self.qos != 1:
            raise ValueError("qos must be 1 for the ColdSafe telemetry contract")
        if self.keepalive_seconds <= 0:
            raise ValueError("keepalive_seconds must be positive")


class MqttSubscriber:
    """Own one Paho network loop and deliver only validated telemetry."""

    def __init__(
        self,
        *,
        settings: MqttSubscriberSettings,
        handler: Callable[[TelemetryPayload], None],
        ack_handler: Callable[[dict], None] | None = None,
        client: Any | None = None,
    ) -> None:
        self._settings = settings
        self._handler = handler
        self._ack_handler = ack_handler
        self._client = client or mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=settings.client_id,
            protocol=mqtt.MQTTv311,
            manual_ack=True,
        )
        self._started = False
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message

    def start(self) -> None:
        """Start Paho's background network loop once."""

        if self._started:
            return
        self._client.username_pw_set(
            self._settings.username,
            self._settings.password,
        )
        self._client.connect_async(
            self._settings.host,
            self._settings.port,
            self._settings.keepalive_seconds,
        )
        self._client.loop_start()
        self._started = True

    def stop(self) -> None:
        """Request a clean disconnect and stop the network loop once."""

        if not self._started:
            return
        try:
            self._client.disconnect()
        finally:
            self._client.loop_stop()
            self._started = False

    def is_connected(self) -> bool:
        """Report the broker connection used by application readiness."""

        return bool(self._client.is_connected())

    def _on_connect(
        self,
        client: Any,
        userdata: Any,
        flags: Any,
        reason_code: Any,
        properties: Any,
    ) -> None:
        del userdata, flags, properties
        if reason_code.is_failure:
            LOGGER.error("MQTT connection rejected: %s", reason_code)
            return

        for topic in (self._settings.topic, "coldsafe/v2/devices/+/telemetry",
                      "coldsafe/v2/devices/+/acks"):
            result, _message_id = client.subscribe(topic, qos=self._settings.qos)
            if result != mqtt.MQTT_ERR_SUCCESS:
                LOGGER.error("MQTT subscription request failed: code=%s", result)

    def _on_message(self, client: Any, userdata: Any, message: Any) -> None:
        del client, userdata
        match = V2_TOPIC.fullmatch(message.topic)
        if message.topic != self._settings.topic and match is None:
            LOGGER.warning("Ignored MQTT message from unexpected topic")
            self._acknowledge(message)
            return

        if match is not None and match.group(2) == "acks":
            try:
                ack = parse_ack_payload(message.payload)
                if ack.device_id != match.group(1):
                    raise ValueError("MQTT topic and ack device differ")
                if self._ack_handler is not None:
                    self._ack_handler(ack.model_dump())
            except (ValidationError, ValueError):
                LOGGER.warning("Rejected invalid MQTT acknowledgment")
            except Exception as error:  # noqa: BLE001 - keep QoS1 delivery on storage failure
                LOGGER.error("MQTT acknowledgment handler failed: error_type=%s", type(error).__name__)
                return
            self._acknowledge(message)
            return

        try:
            telemetry = parse_telemetry_payload(message.payload)
            if match is not None and (telemetry.schema_version != 2 or
                                      telemetry.device_id != match.group(1)):
                raise ValueError("MQTT topic and telemetry device/version differ")
            if match is None and (telemetry.schema_version != 1 or
                                  telemetry.device_id != "esp32-lab-01"):
                raise ValueError("MQTT topic and telemetry version differ")
        except (ValidationError, TelemetryPayloadTooLargeError, ValueError):
            LOGGER.warning("Rejected invalid MQTT telemetry")
            self._acknowledge(message)
            return

        try:
            self._handler(telemetry)
        except DeviceNotFoundError:
            LOGGER.warning("Rejected telemetry from unregistered or inactive device")
            self._acknowledge(message)
            return
        except Exception as error:  # noqa: BLE001 - callback boundary containment
            LOGGER.error(
                "MQTT telemetry handler failed: error_type=%s",
                type(error).__name__,
            )
            return

        self._acknowledge(message)

    def publish_command(self, device_id: str, payload: dict) -> bool:
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", device_id):
            raise ValueError("invalid MQTT device ID")
        topic = f"coldsafe/v2/devices/{device_id}/commands"
        result = self._client.publish(topic, json.dumps(payload, separators=(",", ":")),
                                      qos=1, retain=False)
        return result.rc == mqtt.MQTT_ERR_SUCCESS

    def _acknowledge(self, message: Any) -> None:
        result = self._client.ack(message.mid, message.qos)
        if result != mqtt.MQTT_ERR_SUCCESS:
            LOGGER.error("MQTT acknowledgement failed: code=%s", result)
