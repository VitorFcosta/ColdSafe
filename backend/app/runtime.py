from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from threading import Event, Thread
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
from backend.app.api.events import EventHub
from backend.app.domain.reading_classification import assess_reading


LOGGER = logging.getLogger(__name__)


def build_runtime_app(settings: RuntimeSettings) -> FastAPI:
    auth = AuthService(settings)
    catalog = CatalogService(settings)
    events = EventHub()

    def emit(device_id: str, event_type: str, occurred_at, data: dict) -> None:
        try:
            device = catalog.active_device(device_id)
            if device is None:
                return
            events.publish(device_id, {
                "schema_version": 2, "type": event_type,
                "environment_id": device["environment_id"], "device_id": device_id,
                "occurred_at": occurred_at.isoformat(), "data": data,
            })
        except Exception as error:  # noqa: BLE001 - notifications must not abort persisted work
            LOGGER.error("Event notification failed: error_type=%s", type(error).__name__)

    def command_status(data: dict) -> None:
        from datetime import UTC, datetime
        emit(data["device_id"], "command_status", datetime.now(UTC), data)

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
        settings, lambda device_id, payload: subscriber.publish_command(device_id, payload),
        on_status=command_status,
    )
    alerts = AlertService(
        settings,
        lambda device_id, mqtt_device_id, desired_state: commands.request(
            device_id, mqtt_device_id, "buzzer", desired_state, "automatic", None
        ),
        on_transition=lambda device_id, alert_id, status, occurred_at: emit(
            device_id, "alert", occurred_at,
            {"alert_id": str(alert_id), "status": status},
        ),
    )

    def after_save(payload, received_at, thresholds) -> None:
        device = catalog.active_device(payload.device_id)
        if device is not None:
            if payload.schema_version == 2:
                status = assess_reading(
                    temperature_c=payload.temperature_c, received_at=received_at,
                    now=received_at, thresholds=thresholds,
                ).status.value
                emit(payload.device_id, "reading", received_at, {
                    "schema_version": 2, "device_id": payload.device_id,
                    "temperature_c": payload.temperature_c,
                    "humidity_percent": payload.humidity_percent,
                    "light_percent": payload.light_percent,
                    "received_at": received_at.isoformat(), "status": status,
                })
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

    aiot = consumer = None
    aiot_events = EventHub()
    if settings.aiot_enabled:
        from backend.app.amqp.consumer import ApiAmqpConsumer
        from backend.app.services.aiot_events import AiotEventService
        from gateway.bridge import PostgresScope
        from simulator.model import strict_json

        aiot_catalog = strict_json(settings.aiot_catalog_path.read_bytes())
        owner = str(settings.aiot_owner_user_id)
        aiot = AiotEventService(settings, aiot_catalog, owner)
        scope = PostgresScope({
            'host': settings.postgres_host, 'port': settings.postgres_port,
            'dbname': settings.postgres_db, 'user': settings.postgres_user,
            'password': settings.postgres_password.get_secret_value(),
        }, owner)
        consumer = ApiAmqpConsumer(
            aiot, aiot_catalog, scope,
            lambda event: aiot_events.publish(event['device_id'], event),
            amqp_host=settings.rabbitmq_host, amqp_port=settings.rabbitmq_port,
            password_commands=settings.rabbitmq_commands_password.get_secret_value(),
            password_delivery=settings.rabbitmq_delivery_password.get_secret_value(),
        )

    samples = observer = None
    if settings.rabbitmq_observability_password is not None:
        from backend.app.amqp.observation import MessageObserver
        from backend.app.services.message_samples import MessageSamples

        samples = MessageSamples(settings)
        observer = MessageObserver(
            samples, host=settings.rabbitmq_host, port=settings.rabbitmq_port,
            password=settings.rabbitmq_observability_password.get_secret_value(),
        )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        shutdown, workers = Event(), []
        async def expire_commands() -> None:
            while True:
                await asyncio.sleep(1)
                try:
                    await asyncio.to_thread(commands.expire_pending)
                    if aiot is not None:
                        await asyncio.to_thread(aiot.expire_pending)
                except Exception as error:  # noqa: BLE001 - keep live events running
                    LOGGER.error("Command expiry failed: error_type=%s", type(error).__name__)

        try:
            initialize_schema(settings)
            commands.expire_pending()
            subscriber.start()
            for worker in (consumer, observer):
                if worker is not None:
                    thread = Thread(target=worker.run, args=(shutdown,), daemon=True)
                    thread.start()
                    workers.append((worker, thread))
        except Exception:
            resources.close()
            raise
        expiry_task = asyncio.create_task(expire_commands())
        try:
            yield
        finally:
            expiry_task.cancel()
            try:
                await expiry_task
            except asyncio.CancelledError:
                pass
            try:
                shutdown.set()
                for worker, thread in workers:
                    worker.close()
                    await asyncio.to_thread(thread.join, 10)
                    if thread.is_alive():
                        LOGGER.error('AMQP consumer did not stop within 10 seconds')
                subscriber.stop()
            finally:
                resources.close()

    app = create_app(
        repository=resources.repository,
        readiness_check=lambda: resources.is_ready()
        and postgres_is_ready(settings)
        and subscriber.is_connected()
        and (consumer is None or consumer.is_connected),
        lifespan=lifespan,
        cors_origins=settings.allowed_cors_origins,
        auth=auth,
        catalog=catalog,
        commands=commands,
        alerts=alerts,
        events=events,
    )
    if settings.rabbitmq_monitor_password is not None or samples is not None:
        from backend.app.api.messaging import create_messaging_router
        from backend.app.services.messaging import MessagingService
        monitoring = MessagingService(
            settings.rabbitmq_host, settings.rabbitmq_management_port,
            settings.rabbitmq_monitor_password.get_secret_value(),
        ) if settings.rabbitmq_monitor_password is not None else None
        app.include_router(create_messaging_router(auth, monitoring, samples))
    if aiot is not None:
        from backend.app.api.aiot import install_aiot
        install_aiot(app, aiot, aiot_events, auth, catalog)
    return app
