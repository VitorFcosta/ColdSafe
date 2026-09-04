from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest

from backend.app.domain.telemetry import TelemetryPayload
from backend.app.mqtt.subscriber import MqttSubscriber, MqttSubscriberSettings


VALID_PAYLOAD = (
    b'{"schema_version":1,"device_id":"esp32-lab-01",'
    b'"temperature_c":5.4,"humidity_percent":62.1}'
)


@pytest.fixture
def settings():
    return MqttSubscriberSettings(
        host="mosquitto",
        port=1883,
        topic="coldsafe/v1/telemetry",
        qos=1,
        client_id="coldsafe-backend",
        username="coldsafe-backend",
        password="placeholder",
    )


@pytest.fixture
def client():
    mqtt_client = Mock()
    mqtt_client.subscribe.return_value = (0, 1)
    return mqtt_client


@pytest.fixture
def handler():
    return Mock()


@pytest.fixture
def subscriber(settings, client, handler):
    return MqttSubscriber(settings=settings, handler=handler, client=client)


def test_start_configures_credentials_connection_and_network_loop(
    subscriber,
    settings,
    client,
):
    subscriber.start()

    assert client.method_calls == [
        call.username_pw_set(settings.username, settings.password),
        call.connect_async(settings.host, settings.port, settings.keepalive_seconds),
        call.loop_start(),
    ]


def test_start_is_idempotent(subscriber, client):
    subscriber.start()
    subscriber.start()

    assert client.connect_async.call_count == 1
    assert client.loop_start.call_count == 1


def test_successful_connection_subscribes_again_after_reconnection(
    subscriber,
    settings,
    client,
):
    success = SimpleNamespace(is_failure=False)

    client.on_connect(client, None, {}, success, None)
    client.on_connect(client, None, {}, success, None)

    assert client.subscribe.call_args_list == [
        call(settings.topic, qos=settings.qos),
        call(settings.topic, qos=settings.qos),
    ]


def test_failed_connection_does_not_subscribe(subscriber, client, caplog):
    failure = SimpleNamespace(is_failure=True)

    client.on_connect(client, None, {}, failure, None)

    client.subscribe.assert_not_called()
    assert "MQTT connection rejected" in caplog.text


def test_valid_message_reaches_handler_as_validated_model(
    subscriber,
    client,
    handler,
):
    message = SimpleNamespace(
        topic="coldsafe/v1/telemetry",
        payload=VALID_PAYLOAD,
    )

    client.on_message(client, None, message)

    telemetry = handler.call_args.args[0]
    assert telemetry == TelemetryPayload.model_validate_json(VALID_PAYLOAD)


def test_invalid_message_is_rejected_without_logging_payload(
    subscriber,
    client,
    handler,
    caplog,
):
    invalid_payload = b'{"password":"must-not-appear-in-logs"}'
    message = SimpleNamespace(
        topic="coldsafe/v1/telemetry",
        payload=invalid_payload,
    )

    client.on_message(client, None, message)

    handler.assert_not_called()
    assert "Rejected invalid MQTT telemetry" in caplog.text
    assert invalid_payload.decode() not in caplog.text


def test_message_from_unexpected_topic_is_ignored(subscriber, client, handler):
    message = SimpleNamespace(topic="unexpected/topic", payload=VALID_PAYLOAD)

    client.on_message(client, None, message)

    handler.assert_not_called()


def test_handler_failure_is_contained_by_callback(
    subscriber,
    client,
    handler,
    caplog,
):
    handler.side_effect = RuntimeError("persistence unavailable")
    message = SimpleNamespace(
        topic="coldsafe/v1/telemetry",
        payload=VALID_PAYLOAD,
    )

    client.on_message(client, None, message)

    assert "MQTT telemetry handler failed" in caplog.text


def test_stop_disconnects_before_stopping_loop_and_is_idempotent(
    subscriber,
    client,
):
    subscriber.start()
    client.reset_mock()

    subscriber.stop()
    subscriber.stop()

    assert client.method_calls == [call.disconnect(), call.loop_stop()]
