"""Lifecycle-managed MQTT telemetry subscriber."""

import logging
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


LOGGER = logging.getLogger(__name__)


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
        client: Any | None = None,
    ) -> None:
        self._settings = settings
        self._handler = handler
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

        result, _message_id = client.subscribe(
            self._settings.topic,
            qos=self._settings.qos,
        )
        if result != mqtt.MQTT_ERR_SUCCESS:
            LOGGER.error("MQTT subscription request failed: code=%s", result)

    def _on_message(self, client: Any, userdata: Any, message: Any) -> None:
        del client, userdata
        if message.topic != self._settings.topic:
            LOGGER.warning("Ignored MQTT message from unexpected topic")
            self._acknowledge(message)
            return

        try:
            telemetry = parse_telemetry_payload(message.payload)
        except (ValidationError, TelemetryPayloadTooLargeError):
            LOGGER.warning("Rejected invalid MQTT telemetry")
            self._acknowledge(message)
            return

        try:
            self._handler(telemetry)
        except Exception as error:  # noqa: BLE001 - callback boundary containment
            LOGGER.error(
                "MQTT telemetry handler failed: error_type=%s",
                type(error).__name__,
            )
            return

        self._acknowledge(message)

    def _acknowledge(self, message: Any) -> None:
        result = self._client.ack(message.mid, message.qos)
        if result != mqtt.MQTT_ERR_SUCCESS:
            LOGGER.error("MQTT acknowledgement failed: code=%s", result)
