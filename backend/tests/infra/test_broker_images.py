from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]


def test_brokers_do_not_bind_mount_files_from_the_host():
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text())
    for role in ("mosquitto", "mosquitto-init", "rabbitmq", "rabbitmq-init"):
        for volume in compose["services"][role]["volumes"]:
            assert not volume.startswith(("./", "../", "/")), (role, volume)


def test_static_configuration_is_copied_into_pinned_broker_images():
    mqtt = (ROOT / "infra/mosquitto/Dockerfile").read_text()
    rabbit = (ROOT / "infra/rabbitmq/Dockerfile").read_text()
    init = (ROOT / "infra/rabbitmq/Bootstrap.Dockerfile").read_text()
    assert "FROM eclipse-mosquitto:2.0.22" in mqtt
    assert "COPY config/acl /bootstrap/acl" in mqtt
    assert "COPY config/mosquitto.conf /mosquitto/config/mosquitto.conf" in mqtt
    assert "FROM rabbitmq:4.3.6-management-alpine" in rabbit
    assert "COPY rabbitmq.conf /etc/rabbitmq/rabbitmq.conf" in rabbit
    assert "FROM python:3.13.15-slim" in init
    assert "COPY bootstrap.py /bootstrap/bootstrap.py" in init


def test_broker_build_contexts_exclude_local_passwords_and_generated_definitions():
    mqtt = (ROOT / "infra/mosquitto/.dockerignore").read_text().splitlines()
    rabbit = (ROOT / "infra/rabbitmq/.dockerignore").read_text().splitlines()
    assert mqtt[0] == "*" and rabbit[0] == "*"
    assert set(mqtt[1:]) == {"!Dockerfile", "!config/", "!config/acl", "!config/mosquitto.conf"}
    assert set(rabbit[1:]) == {"!Dockerfile", "!Bootstrap.Dockerfile", "!bootstrap.py", "!rabbitmq.conf"}
