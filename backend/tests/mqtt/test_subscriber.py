from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import pytest
from paho.mqtt.client import MQTTv311
from paho.mqtt.enums import CallbackAPIVersion

from backend.app.domain.telemetry import TelemetryPayload
from backend.app.errors import DeviceNotFoundError
from backend.app.mqtt.subscriber import MqttSubscriber, MqttSubscriberSettings
from backend.app.services.telemetry_ingestion import TelemetryIngestionService


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
    mqtt_client.ack.return_value = 0
    return mqtt_client


@pytest.fixture
def handler():
    return Mock()


@pytest.fixture
def subscriber(settings, client, handler):
    return MqttSubscriber(settings=settings, handler=handler, client=client)


@pytest.mark.parametrize(
    "change",
    [
        {"host": ""},
        {"port": 0},
        {"port": 65_536},
        {"topic": ""},
        {"qos": 0},
        {"client_id": ""},
        {"username": ""},
        {"password": ""},
        {"keepalive_seconds": 0},
    ],
)
def test_settings_reject_invalid_connection_values(change):
    values = {
        "host": "mosquitto",
        "port": 1883,
        "topic": "coldsafe/v1/telemetry",
        "qos": 1,
        "client_id": "coldsafe-backend",
        "username": "coldsafe-backend",
        "password": "placeholder",
        "keepalive_seconds": 60,
    }

    with pytest.raises(ValueError):
        MqttSubscriberSettings(**(values | change))


def test_settings_do_not_expose_password_in_representation(settings):
    assert settings.password not in repr(settings)


@patch("backend.app.mqtt.subscriber.mqtt.Client")
def test_default_client_uses_callback_api_v2(factory, settings, handler):
    MqttSubscriber(settings=settings, handler=handler)

    factory.assert_called_once_with(
        CallbackAPIVersion.VERSION2,
        client_id=settings.client_id,
        protocol=MQTTv311,
        manual_ack=True,
    )


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
        call("coldsafe/v2/devices/+/telemetry", qos=settings.qos),
        call("coldsafe/v2/devices/+/acks", qos=settings.qos),
        call(settings.topic, qos=settings.qos),
        call("coldsafe/v2/devices/+/telemetry", qos=settings.qos),
        call("coldsafe/v2/devices/+/acks", qos=settings.qos),
    ]


def test_failed_connection_does_not_subscribe(subscriber, client, caplog):
    failure = SimpleNamespace(is_failure=True)

    client.on_connect(client, None, {}, failure, None)

    client.subscribe.assert_not_called()
    assert "MQTT connection rejected" in caplog.text


def test_subscription_request_failure_is_reported(subscriber, client, caplog):
    client.subscribe.return_value = (1, 1)
    success = SimpleNamespace(is_failure=False)

    client.on_connect(client, None, {}, success, None)

    assert "MQTT subscription request failed" in caplog.text


def test_valid_message_reaches_handler_as_validated_model(
    subscriber,
    client,
    handler,
):
    message = SimpleNamespace(
        topic="coldsafe/v1/telemetry",
        payload=VALID_PAYLOAD,
        mid=41,
        qos=1,
    )

    client.on_message(client, None, message)

    telemetry = handler.call_args.args[0]
    assert telemetry == TelemetryPayload.model_validate_json(VALID_PAYLOAD)
    client.ack.assert_called_once_with(message.mid, message.qos)


def test_v2_telemetry_requires_topic_identity_and_version(subscriber, client, handler):
    payload = (b'{"schema_version":2,"device_id":"esp32-lab-02",'
               b'"temperature_c":5.4,"humidity_percent":62.1,"light_percent":43.2}')
    message = SimpleNamespace(topic="coldsafe/v2/devices/esp32-lab-02/telemetry",
                              payload=payload, mid=47, qos=1)
    client.on_message(client, None, message)
    assert handler.call_args.args[0].light_percent == 43.2
    message.topic = "coldsafe/v2/devices/esp32-lab-01/telemetry"
    client.on_message(client, None, message)
    assert handler.call_count == 1
    assert client.ack.call_count == 2


def test_legacy_topic_cannot_impersonate_second_device(subscriber, client, handler):
    message = SimpleNamespace(
        topic="coldsafe/v1/telemetry",
        payload=VALID_PAYLOAD.replace(b"esp32-lab-01", b"esp32-lab-02"),
        mid=49, qos=1,
    )
    client.on_message(client, None, message)
    handler.assert_not_called()
    client.ack.assert_called_once_with(49, 1)


def test_v2_ack_is_validated_and_delivered(settings, client, handler):
    ack_handler = Mock()
    subscriber = MqttSubscriber(settings=settings, handler=handler,
                                ack_handler=ack_handler, client=client)
    message = SimpleNamespace(
        topic="coldsafe/v2/devices/esp32-lab-01/acks",
        payload=(b'{"schema_version":2,"command_id":"550e8400-e29b-41d4-a716-446655440000",'
                 b'"device_id":"esp32-lab-01","actuator":"led",'
                 b'"result":"applied","applied_state":true}'), mid=48, qos=1)
    client.on_message(client, None, message)
    assert ack_handler.call_count == 1
    handler.assert_not_called()
    client.ack.assert_called_once_with(48, 1)


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
        mid=42,
        qos=1,
    )

    client.on_message(client, None, message)

    handler.assert_not_called()
    client.ack.assert_called_once_with(message.mid, message.qos)
    assert "Rejected invalid MQTT telemetry" in caplog.text
    assert invalid_payload.decode() not in caplog.text


def test_message_from_unexpected_topic_is_ignored(subscriber, client, handler):
    message = SimpleNamespace(
        topic="unexpected/topic",
        payload=VALID_PAYLOAD,
        mid=43,
        qos=1,
    )

    client.on_message(client, None, message)

    handler.assert_not_called()
    client.ack.assert_called_once_with(message.mid, message.qos)


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
        mid=44,
        qos=1,
    )

    client.on_message(client, None, message)

    assert "MQTT telemetry handler failed" in caplog.text
    client.ack.assert_not_called()


def test_post_save_automation_failure_still_acks_telemetry(settings, client):
    repository = Mock()
    subscriber = MqttSubscriber(
        settings=settings,
        handler=TelemetryIngestionService(
            repository=repository,
            after_save=Mock(side_effect=RuntimeError("automation failed")),
        ),
        client=client,
    )
    message = SimpleNamespace(topic="coldsafe/v1/telemetry", payload=VALID_PAYLOAD,
                              mid=52, qos=1)

    client.on_message(client, None, message)

    repository.save.assert_called_once()
    client.ack.assert_called_once_with(52, 1)


def test_unregistered_device_is_rejected_and_acknowledged(subscriber, client, handler, caplog):
    handler.side_effect = DeviceNotFoundError("unknown")
    message = SimpleNamespace(
        topic="coldsafe/v1/telemetry", payload=VALID_PAYLOAD, mid=46, qos=1,
    )

    client.on_message(client, None, message)

    client.ack.assert_called_once_with(message.mid, message.qos)
    assert "Rejected telemetry" in caplog.text


def test_acknowledgement_failure_is_reported(subscriber, client, handler, caplog):
    client.ack.return_value = 1
    message = SimpleNamespace(
        topic="coldsafe/v1/telemetry",
        payload=VALID_PAYLOAD,
        mid=45,
        qos=1,
    )

    client.on_message(client, None, message)

    handler.assert_called_once()
    assert "MQTT acknowledgement failed" in caplog.text


def test_connection_state_comes_from_mqtt_client(subscriber, client):
    client.is_connected.return_value = True

    assert subscriber.is_connected() is True


def test_stop_disconnects_before_stopping_loop_and_is_idempotent(
    subscriber,
    client,
):
    subscriber.start()
    client.reset_mock()

    subscriber.stop()
    subscriber.stop()

    assert client.method_calls == [call.disconnect(), call.loop_stop()]
