"""Real AMQP tests on a disposable Compose project, never the user's volumes."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import time

import pika
import pytest
import yaml

from infra.rabbitmq.bootstrap import SERVICE_ROLES


ROOT = Path(__file__).resolve().parents[3]
pytestmark = pytest.mark.integration
CONSUMERS = ("gateway", "writer", "inference", "delivery", "commands",
             "generation", "training", "observability", "audit")
ROUTES = {
    "telemetry_persisted": ("writer", {"delivery", "commands", "observability"}),
    "telemetry": ("gateway", {"writer", "inference", "delivery", "commands", "observability"}),
    "ack": ("gateway", {"commands", "delivery", "observability"}),
    "command": ("api", {"gateway", "observability"}),
    "command_status": ("commands", {"delivery", "observability"}),
    "alert": ("commands", {"delivery", "observability"}),
    "freshness": ("commands", {"delivery", "commands", "observability"}),
    "prediction": ("inference", {"delivery", "commands", "observability"}),
    "job_requested": ("api", {"observability"}),
    "job_progress": ("generation", {"delivery", "observability"}),
    "model_activation": ("api", {"inference", "observability"}),
    "model_status": ("training", {"delivery", "observability"}),
    "processing_error": ("writer", {"delivery", "observability"}),
}


@pytest.fixture(scope="module")
def broker():
    if os.environ.get("COLDSAFE_RABBITMQ_INTEGRATION") != "1":
        pytest.skip("Set COLDSAFE_RABBITMQ_INTEGRATION=1 to start a disposable RabbitMQ")
    project = f"coldsafe-b207-{secrets.token_hex(4)}"
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text())
    passwords = {role: secrets.token_urlsafe(32) for role in SERVICE_ROLES}
    with tempfile.TemporaryDirectory(prefix="coldsafe-b207-") as folder:
        temporary = Path(folder)
        init = compose["services"]["rabbitmq-init"]
        rabbit = compose["services"]["rabbitmq"]
        config = {
            "services": {
                "rabbitmq-init": {**init, "image": f"{project}-init",
                                  "build": {**init["build"], "context": str(ROOT / init["build"]["context"])}},
                "rabbitmq": {**rabbit, "ports": ["127.0.0.1::5672"],
                             "image": f"{project}-broker", "networks": ["test"],
                             "build": {**rabbit["build"], "context": str(ROOT / rabbit["build"]["context"])}},
            },
            "networks": {"test": {}},
            "volumes": {"rabbitmq-definitions": {}, "rabbitmq-data": {}},
        }
        file = temporary / "compose.yaml"
        file.write_text(yaml.safe_dump(config))
        env_file = temporary / ".env"
        env_file.write_text("\n".join(f"RABBITMQ_{role.upper()}_PASSWORD={value}"
                                      for role, value in passwords.items()))
        env_file.chmod(0o600)
        command = ["docker", "compose", "-p", project, "--env-file", str(env_file), "-f", str(file)]
        try:
            run(command, "up", "-d", "--build", "--wait", "--wait-timeout", "120")
            port = int(run(command, "port", "rabbitmq", "5672").strip().rsplit(":", 1)[1])
            yield {"port": port, "passwords": passwords, "command": command}
        finally:
            run(command, "down", "--volumes", "--remove-orphans")


def run(command, *arguments):
    result = subprocess.run([*command, *arguments], capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stderr
    return result.stdout


@contextmanager
def connect(broker, role, *, vhost="coldsafe", password=None):
    credentials = pika.PlainCredentials(f"coldsafe-{role}", password or broker["passwords"][role])
    connection = pika.BlockingConnection(pika.ConnectionParameters(
        "127.0.0.1", broker["port"], virtual_host=vhost, credentials=credentials,
        heartbeat=30, blocked_connection_timeout=5, socket_timeout=5))
    try:
        channel = connection.channel()
        channel.confirm_delivery()
        channel.basic_qos(prefetch_count=1)
        yield channel
    finally:
        if connection.is_open:
            connection.close()


def queue(role):
    return "coldsafe.dlq" if role == "audit" else f"coldsafe.{role}"


def publish(channel, example, headers=None):
    payload = example["payload"]
    properties = pika.BasicProperties(content_type="application/json", delivery_mode=2,
                                     message_id=payload["event_id"], correlation_id=payload["correlation_id"],
                                     headers=headers)
    body = json.dumps(payload, separators=(",", ":")).encode()
    channel.basic_publish("coldsafe.events", example["routing_key"], body, properties, mandatory=True)
    return body


def take(channel, role, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        method, properties, body = channel.basic_get(queue(role), auto_ack=False)
        if method:
            return method, properties, body
        channel.connection.sleep(0.05)
    pytest.fail(f"No message in {queue(role)} within {timeout}s")


def examples():
    return [item for item in json.loads((ROOT / "contracts/examples/aiot.valid.json").read_text())
            if item["schema"] == "bus_event"]


def telemetry():
    return next(item for item in examples() if item["payload"]["type"] == "telemetry")


def drain_other_telemetry_queues(broker):
    for role in ("inference", "delivery", "commands", "observability"):
        with connect(broker, role) as channel:
            method, _, _ = take(channel, role)
            channel.basic_ack(method.delivery_tag)


def test_every_contract_event_routes_to_the_right_queues(broker):
    cases = {item["payload"]["type"]: item for item in examples()}
    jobs = [item for item in examples() if item["payload"]["type"] == "job_requested"]
    for example in [*cases.values(), *jobs]:
        kind = example["payload"]["type"]
        publisher, destinations = ROUTES[kind]
        headers = {"job_type": example["payload"]["data"]["job_type"]} if kind == "job_requested" else None
        expected = destinations | ({headers["job_type"]} if headers else set())
        with connect(broker, publisher) as channel:
            original = publish(channel, example, headers)
        for role in CONSUMERS:
            with connect(broker, role) as channel:
                if role in expected:
                    method, properties, body = take(channel, role)
                    assert body == original
                    assert properties.message_id == example["payload"]["event_id"]
                    assert properties.delivery_mode == 2
                    channel.basic_ack(method.delivery_tag)
                assert channel.basic_get(queue(role), auto_ack=False)[0] is None
        if kind == 'model_activation':
            with connect(broker, 'inference') as channel:
                method, properties, body = take(channel, 'model-activation')
                assert body == original
                assert properties.message_id == example['payload']['event_id']
                channel.basic_ack(method.delivery_tag)
                assert channel.basic_get(queue('model-activation'), auto_ack=False)[0] is None


def test_model_activation_failure_keeps_original_in_dlq_without_consuming_telemetry(broker):
    example = next(item for item in examples() if item['payload']['type'] == 'model_activation')
    with connect(broker, 'api') as channel:
        original = publish(channel, example)
    for role in ('inference', 'observability'):
        with connect(broker, role) as channel:
            method, _, body = take(channel, role)
            assert body == original
            channel.basic_ack(method.delivery_tag)
    with connect(broker, 'inference') as channel:
        method, _, body = take(channel, 'model-activation')
        assert body == original
        channel.basic_reject(method.delivery_tag, requeue=False)
    for role in ('audit', 'observability'):
        with connect(broker, role) as channel:
            method, properties, body = take(channel, role)
            assert body == original
            assert properties.headers['x-death'][0]['queue'] == 'coldsafe.model-activation'
            channel.basic_ack(method.delivery_tag)


@pytest.mark.parametrize('role', list(SERVICE_ROLES))
def test_only_inference_identity_can_read_model_activation_queue(broker, role):
    with connect(broker, role) as channel:
        if role == 'inference':
            assert channel.basic_get(queue('model-activation'), auto_ack=False)[0] is None
        else:
            with pytest.raises(pika.exceptions.ChannelClosedByBroker) as error:
                channel.basic_get(queue('model-activation'), auto_ack=False)
            assert error.value.reply_code == 403


@pytest.mark.parametrize("role", list(SERVICE_ROLES))
def test_every_service_is_denied_reading_a_different_queue(broker, role):
    forbidden = "coldsafe.dlq" if role != "audit" else "coldsafe.writer"
    with connect(broker, role) as channel:
        with pytest.raises(pika.exceptions.ChannelClosedByBroker) as error:
            channel.basic_get(forbidden, auto_ack=False)
        assert error.value.reply_code == 403


@pytest.mark.parametrize("action", ["configure", "publish_command", "default_exchange", "wrong_device_key"])
def test_gateway_cannot_bypass_topology_or_publish_commands(broker, action):
    with connect(broker, "gateway") as channel:
        with pytest.raises(pika.exceptions.ChannelClosedByBroker) as error:
            if action == "configure":
                channel.queue_declare("coldsafe.gateway", durable=True)
            elif action == "default_exchange":
                channel.basic_publish("", "coldsafe.writer", b"bypass", mandatory=True)
            else:
                key = "v3.command.00000000-0000-4000-8000-000000000001" if action == "publish_command" else "v3.telemetry.esp32.lab-01"
                channel.basic_publish("coldsafe.events", key, b"forbidden", mandatory=True)
        assert error.value.reply_code == 403


def test_wrong_password_guest_and_default_vhost_are_denied(broker):
    for role, vhost, password in (("gateway", "coldsafe", "wrong-password"),
                                  ("gateway", "/", None), ("guest", "coldsafe", "guest")):
        with pytest.raises(pika.exceptions.AMQPConnectionError):
            with connect(broker, role, vhost=vhost, password=password):
                pytest.fail("Unauthorized connection succeeded")
    users = run(broker["command"], "exec", "-T", "rabbitmq", "rabbitmqctl", "-q", "list_users")
    assert "guest" not in users
    assert "administrator" not in users


def test_permanent_failure_preserves_original_and_death_context(broker):
    example = telemetry()
    with connect(broker, "gateway") as channel:
        original = publish(channel, example, {"test_context": "permanent"})
    drain_other_telemetry_queues(broker)
    with connect(broker, "writer") as channel:
        method, _, _ = take(channel, "writer")
        channel.basic_reject(method.delivery_tag, requeue=False)
    with connect(broker, "audit") as channel:
        method, properties, body = take(channel, "audit")
        assert body == original
        assert properties.message_id == example["payload"]["event_id"]
        assert properties.correlation_id == example["payload"]["correlation_id"]
        assert properties.headers["test_context"] == "permanent"
        assert properties.headers["x-death"][0]["reason"] == "rejected"
        assert properties.headers["x-death"][0]["queue"] == "coldsafe.writer"
        assert properties.headers["x-death"][0]["routing-keys"] == [example["routing_key"]]
        channel.basic_ack(method.delivery_tag)
    with connect(broker, "observability") as channel:
        method, properties, body = take(channel, "observability")
        assert body == original
        assert properties.headers["x-death"][0]["queue"] == "coldsafe.writer"
        channel.basic_ack(method.delivery_tag)


def test_transient_failure_has_three_attempts_with_backoff_then_dlq(broker):
    example = telemetry()
    with connect(broker, "gateway") as channel:
        original = publish(channel, example)
    drain_other_telemetry_queues(broker)
    with connect(broker, "writer") as channel:
        for attempt in range(3):
            started = time.monotonic()
            method, properties, body = take(channel, "writer")
            assert body == original
            assert (properties.headers or {}).get("x-delivery-count", 0) == attempt
            if attempt:
                assert time.monotonic() - started >= attempt * 0.9
            # basic.nack(requeue=True) does NOT increment delivery-count in 4.3.
            channel.basic_reject(method.delivery_tag, requeue=True)
        channel.connection.sleep(0.2)
        assert channel.basic_get(queue("writer"), auto_ack=False)[0] is None
    with connect(broker, "audit") as channel:
        method, properties, body = take(channel, "audit")
        assert body == original
        assert properties.headers["x-death"][0]["reason"] == "delivery_limit"
        channel.basic_ack(method.delivery_tag)
    with connect(broker, "observability") as channel:
        method, properties, body = take(channel, "observability")
        assert body == original
        assert properties.headers["x-death"][0]["reason"] == "delivery_limit"
        channel.basic_ack(method.delivery_tag)


def test_job_without_transport_type_goes_to_private_dlq(broker):
    example = next(item for item in examples() if item["payload"]["type"] == "job_requested")
    with connect(broker, "api") as channel:
        original = publish(channel, example)
    for role in ("observability", "audit"):
        with connect(broker, role) as channel:
            method, _, body = take(channel, role)
            assert body == original
            channel.basic_ack(method.delivery_tag)
    for role in ("generation", "training"):
        with connect(broker, role) as channel:
            assert channel.basic_get(queue(role), auto_ack=False)[0] is None


def test_manual_ack_and_restart_keep_unprocessed_messages(broker):
    example = telemetry()
    with connect(broker, "gateway") as channel:
        original = publish(channel, example)
    drain_other_telemetry_queues(broker)
    with connect(broker, "writer") as channel:
        method, _, body = take(channel, "writer")
        assert body == original
        # Closing with no ACK must redeliver, not silently remove the message.
    run(broker["command"], "restart", "rabbitmq")
    run(broker["command"], "up", "-d", "--wait", "--wait-timeout", "120", "rabbitmq")
    restarted = {**broker, "port": int(run(broker["command"], "port", "rabbitmq", "5672").strip().rsplit(":", 1)[1])}
    with connect(restarted, "writer") as channel:
        method, properties, body = take(channel, "writer")
        assert body == original
        assert properties.message_id == example["payload"]["event_id"]
        channel.basic_ack(method.delivery_tag)
        assert channel.basic_get(queue("writer"), auto_ack=False)[0] is None


def test_broker_limits_private_hashes_and_isolated_volumes(broker):
    container = run(broker["command"], "ps", "-q", "rabbitmq").strip()
    result = subprocess.run(["docker", "inspect", "--format",
                             '{{json .State}}|{{.HostConfig.Memory}}|{{json .Mounts}}', container],
                            capture_output=True, text=True, check=True)
    state, memory, mounts = result.stdout.strip().split("|", 2)
    assert json.loads(state)["Health"]["Status"] == "healthy"
    assert json.loads(state)["OOMKilled"] is False
    assert int(memory) == 512 * 1024 * 1024
    project = broker["command"][3]
    volumes = [mount for mount in json.loads(mounts) if mount["Type"] == "volume"]
    assert len(volumes) == 2
    assert all(mount["Name"].startswith(project + "_") for mount in volumes)
    private = run(broker["command"], "exec", "-T", "rabbitmq", "stat", "-c", "%a %u %g",
                  "/etc/rabbitmq/bootstrap/definitions.json").strip()
    assert private == "440 100 101"
