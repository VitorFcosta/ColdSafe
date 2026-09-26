"""Two real accounts and databases through the runtime's telemetry path."""

import os
from time import monotonic, sleep
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend.app.api.events import EventHub
from backend.app.config.settings import RuntimeSettings
from backend.app.domain.telemetry import TelemetryPayload
from backend.app.repositories.postgres import connect
from backend.app.runtime import build_runtime_app


@pytest.mark.integration
def test_two_accounts_remain_isolated_across_telemetry_events_alerts_and_commands() -> None:
    if not all(os.getenv(name) for name in (
        "POSTGRES_TEST_PASSWORD", "INFLUXDB_TEST_TOKEN", "INFLUXDB_TEST_BUCKET"
    )):
        pytest.skip("PostgreSQL and a dedicated InfluxDB test bucket are required")
    settings = RuntimeSettings(
        mqtt_host="unused", mqtt_port=1883, mqtt_topic="coldsafe/v1/telemetry",
        mqtt_qos=1, mqtt_client_id="unused", mqtt_backend_username="unused",
        mqtt_backend_password="unused", influxdb_url=os.getenv(
            "INFLUXDB_TEST_URL", "http://127.0.0.1:18086"
        ), influxdb_org=os.getenv("INFLUXDB_TEST_ORG", "coldsafe"),
        influxdb_bucket=os.environ["INFLUXDB_TEST_BUCKET"],
        influxdb_token=os.environ["INFLUXDB_TEST_TOKEN"],
        postgres_host=os.getenv("POSTGRES_TEST_HOST", "127.0.0.1"),
        postgres_port=int(os.getenv("POSTGRES_TEST_PORT", "15432")),
        postgres_db=os.getenv("POSTGRES_TEST_DB", "coldsafe"),
        postgres_user=os.getenv("POSTGRES_TEST_USER", "coldsafe"),
        postgres_password=os.environ["POSTGRES_TEST_PASSWORD"], _env_file=None,
    )
    run_id = uuid4().hex
    mqtt_ids = [f"block5-a-{run_id}", f"block5-b-{run_id}"]
    emails = [f"{device}@example.invalid" for device in mqtt_ids]
    user_ids: list[UUID] = []
    hub = EventHub()

    with patch("backend.app.runtime.MqttSubscriber") as subscriber_type, patch(
        "backend.app.runtime.EventHub", return_value=hub
    ):
        subscriber = subscriber_type.return_value
        subscriber.publish_command.return_value = True
        subscriber.is_connected.return_value = True
        app = build_runtime_app(settings)
        handler = subscriber_type.call_args.kwargs["handler"]

        try:
            with TestClient(app) as client:
                headers = []
                device_ids = []
                for email, mqtt_id in zip(emails, mqtt_ids):
                    credentials = {"email": email, "password": "block5-password"}
                    registered = client.post("/api/v1/auth/register", json=credentials)
                    assert registered.status_code == 201
                    user_ids.append(UUID(registered.json()["data"]["user_id"]))
                    login = client.post("/api/v1/auth/login", json=credentials)
                    assert login.status_code == 200
                    headers.append({"Authorization": f"Bearer {login.json()['data']['token']}"})
                    environment = client.post(
                        "/api/v1/environments", headers=headers[-1], json={"name": email}
                    )
                    assert environment.status_code == 201
                    device = client.post(
                        f"/api/v1/environments/{environment.json()['data']['id']}/devices",
                        headers=headers[-1], json={"name": "Sensor", "mqtt_device_id": mqtt_id},
                    )
                    assert device.status_code == 201
                    device_ids.append(device.json()["data"]["id"])

                assert client.get("/api/v1/monitoring/summary", params={"device_id": mqtt_ids[0]},
                                  headers=headers[1]).status_code == 404
                assert client.get("/api/v1/readings", params={"device_id": mqtt_ids[0]},
                                  headers=headers[1]).status_code == 404
                assert client.get("/api/v1/alerts", params={"device_id": mqtt_ids[0]},
                                  headers=headers[1]).status_code == 404
                assert client.get(f"/api/v1/devices/{device_ids[0]}",
                                  headers=headers[1]).status_code == 404
                assert client.post(
                    f"/api/v1/devices/{device_ids[0]}/led/commands", headers=headers[1],
                    json={"desired_state": True},
                ).status_code == 404
                subscriber.publish_command.assert_not_called()

                with client.websocket_connect(f"/api/v1/events?device_id={mqtt_ids[0]}") as foreign:
                    foreign.send_json({"token": headers[1]["Authorization"].split()[1]})
                    with pytest.raises(WebSocketDisconnect) as denied:
                        foreign.receive_json()
                    assert denied.value.code == 4403

                for _ in range(2):
                    with client.websocket_connect(f"/api/v1/events?device_id={mqtt_ids[0]}") as socket:
                        socket.send_json({"token": headers[0]["Authorization"].split()[1]})
                        deadline = monotonic() + 3
                        while mqtt_ids[0] not in hub._subscribers and monotonic() < deadline:
                            sleep(0.01)
                        assert mqtt_ids[0] in hub._subscribers
                    deadline = monotonic() + 3
                    while hub._subscribers and monotonic() < deadline:
                        sleep(0.01)
                    assert not hub._subscribers

                with client.websocket_connect(f"/api/v1/events?device_id={mqtt_ids[0]}") as first, \
                     client.websocket_connect(f"/api/v1/events?device_id={mqtt_ids[1]}") as second:
                    for socket, header in zip((first, second), headers):
                        socket.send_json({"token": header["Authorization"].split()[1]})
                    deadline = monotonic() + 3
                    while set(hub._subscribers) != set(mqtt_ids) and monotonic() < deadline:
                        sleep(0.01)
                    assert set(hub._subscribers) == set(mqtt_ids)

                    for mqtt_id, temperature in zip(mqtt_ids, (9.0, 4.0)):
                        handler(TelemetryPayload(
                            schema_version=2, device_id=mqtt_id, temperature_c=temperature,
                            humidity_percent=60.0, light_percent=40.0,
                        ))
                    assert first.receive_json()["device_id"] == mqtt_ids[0]
                    assert second.receive_json()["device_id"] == mqtt_ids[1]

                for index, expected_status in enumerate(("critical", "normal")):
                    deadline = monotonic() + 5
                    while True:
                        summary = client.get("/api/v1/monitoring/summary",
                                             params={"device_id": mqtt_ids[index]},
                                             headers=headers[index])
                        if summary.status_code == 200 and summary.json()["data"]["reading"]:
                            break
                        assert monotonic() < deadline, "reading did not reach InfluxDB"
                        sleep(0.1)
                    assert summary.json()["data"]["status"] == expected_status
                    history = client.get("/api/v1/readings", params={"device_id": mqtt_ids[index]},
                                         headers=headers[index])
                    assert history.status_code == 200
                    assert [r["temperature_c"] for r in history.json()["data"]["readings"]] == [9.0 if index == 0 else 4.0]

                first_alerts = client.get("/api/v1/alerts", params={"device_id": mqtt_ids[0]},
                                          headers=headers[0]).json()["data"]["alerts"]
                second_alerts = client.get("/api/v1/alerts", params={"device_id": mqtt_ids[1]},
                                           headers=headers[1]).json()["data"]["alerts"]
                assert len(first_alerts) == 1 and first_alerts[0]["kind"] == "temperature_high"
                assert second_alerts == []
                assert subscriber.publish_command.call_count == 1
                assert subscriber.publish_command.call_args.args[0] == mqtt_ids[0]

                manual = client.post(
                    f"/api/v1/devices/{device_ids[1]}/led/commands", headers=headers[1],
                    json={"desired_state": True},
                )
                assert manual.status_code == 200
                command = manual.json()["data"]
                assert command["status"] == "pending" and command["confirmed_state"] is None
                assert subscriber.publish_command.call_args.args[0] == mqtt_ids[1]
                assert client.get(f"/api/v1/commands/{command['command_id']}",
                                  headers=headers[0]).status_code == 404
                assert client.get(f"/api/v1/devices/{device_ids[1]}/actuators",
                                  headers=headers[0]).status_code == 404
                with connect(settings) as connection:
                    connection.execute(
                        "UPDATE actuator_commands SET requested_at = now() - interval '2 minutes', "
                        "deadline_at = now() - interval '1 minute' "
                        "WHERE id = %s", (UUID(command["command_id"]),),
                    )
                expired = client.get(f"/api/v1/commands/{command['command_id']}",
                                     headers=headers[1])
                assert expired.status_code == 200
                assert expired.json()["data"]["status"] == "unconfirmed"
                assert expired.json()["data"]["confirmed_state"] is None
        finally:
            if user_ids:
                with connect(settings) as connection:
                    connection.execute("DELETE FROM sessions WHERE user_id = ANY(%s)", (user_ids,))
                    connection.execute("DELETE FROM audit_events WHERE actor_user_id = ANY(%s) OR device_id IN "
                                       "(SELECT id FROM devices WHERE environment_id IN "
                                       "(SELECT id FROM environments WHERE owner_user_id = ANY(%s)))",
                                       (user_ids, user_ids))
                    connection.execute("DELETE FROM actuator_commands WHERE device_id IN "
                                       "(SELECT id FROM devices WHERE environment_id IN "
                                       "(SELECT id FROM environments WHERE owner_user_id = ANY(%s)))", (user_ids,))
                    connection.execute("DELETE FROM alerts WHERE device_id IN "
                                       "(SELECT id FROM devices WHERE environment_id IN "
                                       "(SELECT id FROM environments WHERE owner_user_id = ANY(%s)))", (user_ids,))
                    connection.execute("DELETE FROM devices WHERE environment_id IN "
                                       "(SELECT id FROM environments WHERE owner_user_id = ANY(%s))", (user_ids,))
                    connection.execute("DELETE FROM environment_rules WHERE environment_id IN "
                                       "(SELECT id FROM environments WHERE owner_user_id = ANY(%s))", (user_ids,))
                    connection.execute("DELETE FROM environments WHERE owner_user_id = ANY(%s)", (user_ids,))
                    connection.execute("DELETE FROM users WHERE id = ANY(%s)", (user_ids,))
