from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import FastAPI

from backend.app.api.app import create_app
from backend.app.api.auth import AuthService
from backend.app.api.catalog import CatalogService
from backend.app.config.settings import RuntimeSettings
from backend.app.domain.reading_classification import DEFAULT_THRESHOLDS, TemperatureThresholds
from backend.app.errors import DeviceNotFoundError
from backend.app.mqtt.subscriber import MqttSubscriber, MqttSubscriberSettings
from backend.app.repositories.influxdb_client import (
    InfluxSettings,
    create_influx_repository,
)
from backend.app.repositories.postgres import initialize_schema, is_ready as postgres_is_ready
from backend.app.services.telemetry_ingestion import TelemetryIngestionService
from backend.app.services.commands import CommandService
from backend.app.services.alerts import AlertService


def build_runtime_app(settings: RuntimeSettings) -> FastAPI:
    auth = AuthService(settings)
    catalog = CatalogService(settings)

    def thresholds_for_device(device_id: str) -> TemperatureThresholds:
        device = catalog.active_device(device_id)
        if device is not None:
            return TemperatureThresholds(
                **catalog.thresholds_for_environment(device["environment_id"])
            )
        if catalog.registered_device(device_id) is not None:
            raise DeviceNotFoundError(device_id)
        # Preserve unclaimed v1 simulator telemetry until its owner registers it.
        if device_id in {"esp32-lab-01", "esp32-lab-02"}:
            return DEFAULT_THRESHOLDS
        raise DeviceNotFoundError(device_id)

    resources = create_influx_repository(
        InfluxSettings(
            url=settings.influxdb_url,
            org=settings.influxdb_org,
            bucket=settings.influxdb_bucket,
            token=settings.influxdb_token.get_secret_value(),
        )
    )

    commands = CommandService(
        settings, lambda device_id, payload: subscriber.publish_command(device_id, payload)
    )
    alerts = AlertService(
        settings,
        lambda device_id, mqtt_device_id, desired_state: commands.request(
            device_id, mqtt_device_id, "buzzer", desired_state, "automatic", None
        ),
    )

    def after_save(payload, received_at, thresholds) -> None:
        device = catalog.active_device(payload.device_id)
        if device is not None:
            commands.expire_pending()
            alerts.evaluate(
                UUID(device["id"]), payload.device_id, payload.temperature_c,
                thresholds, received_at,
            )

    subscriber = MqttSubscriber(
        settings=MqttSubscriberSettings(
            host=settings.mqtt_host,
            port=settings.mqtt_port,
            topic=settings.mqtt_topic,
            qos=settings.mqtt_qos,
            client_id=settings.mqtt_client_id,
            username=settings.mqtt_backend_username,
            password=settings.mqtt_backend_password.get_secret_value(),
        ),
        handler=TelemetryIngestionService(
            repository=resources.repository,
            thresholds_for_device=thresholds_for_device,
            after_save=after_save,
        ),
        ack_handler=commands.handle_ack,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            initialize_schema(settings)
            commands.expire_pending()
            subscriber.start()
        except Exception:
            resources.close()
            raise
        try:
            yield
        finally:
            try:
                subscriber.stop()
            finally:
                resources.close()

    return create_app(
        repository=resources.repository,
        readiness_check=lambda: resources.is_ready()
        and postgres_is_ready(settings)
        and subscriber.is_connected(),
        lifespan=lifespan,
        cors_origins=settings.allowed_cors_origins,
        auth=auth,
        catalog=catalog,
        commands=commands,
    )
