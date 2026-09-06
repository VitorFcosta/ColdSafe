from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.app.api.app import create_app
from backend.app.config.settings import RuntimeSettings
from backend.app.mqtt.subscriber import MqttSubscriber, MqttSubscriberSettings
from backend.app.repositories.influxdb_client import (
    InfluxSettings,
    create_influx_repository,
)
from backend.app.services.telemetry_ingestion import TelemetryIngestionService


def build_runtime_app(settings: RuntimeSettings) -> FastAPI:
    resources = create_influx_repository(
        InfluxSettings(
            url=settings.influxdb_url,
            org=settings.influxdb_org,
            bucket=settings.influxdb_bucket,
            token=settings.influxdb_token.get_secret_value(),
        )
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
        handler=TelemetryIngestionService(repository=resources.repository),
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
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
        readiness_check=lambda: resources.is_ready() and subscriber.is_connected(),
        lifespan=lifespan,
    )
