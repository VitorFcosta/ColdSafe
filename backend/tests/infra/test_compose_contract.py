from pathlib import Path

import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
COMPOSE_PATH = REPOSITORY_ROOT / "compose.yaml"
MOSQUITTO_CONFIG_PATH = (
    REPOSITORY_ROOT / "infra" / "mosquitto" / "config" / "mosquitto.conf"
)
MOSQUITTO_ACL_PATH = (
    REPOSITORY_ROOT / "infra" / "mosquitto" / "config" / "acl"
)


def load_compose():
    return yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))


def test_compose_contains_only_the_services_that_exist_today():
    compose = load_compose()

    assert set(compose["services"]) == {"mosquitto", "influxdb"}


def test_runtime_images_are_pinned_and_have_healthchecks():
    services = load_compose()["services"]

    assert services["mosquitto"]["image"] == "eclipse-mosquitto:2.0.22"
    assert services["influxdb"]["image"] == "influxdb:2.7.12-alpine"
    assert all("healthcheck" in service for service in services.values())


def test_mqtt_backend_role_name_is_not_overridable_without_changing_the_acl():
    mosquitto = load_compose()["services"]["mosquitto"]

    assert mosquitto["environment"]["MQTT_BACKEND_USERNAME"] == "coldsafe-backend"


def test_only_mqtt_is_published_and_only_on_loopback():
    services = load_compose()["services"]

    assert services["mosquitto"]["ports"] == ["127.0.0.1:1883:1883"]
    assert "ports" not in services["influxdb"]


def test_services_share_an_internal_network():
    compose = load_compose()

    assert compose["networks"]["coldsafe-internal"]["internal"] is True
    assert all(
        "coldsafe-internal" in service["networks"]
        for service in compose["services"].values()
    )


def test_only_mosquitto_uses_the_edge_network_needed_for_host_access():
    compose = load_compose()

    assert "coldsafe-edge" in compose["networks"]
    assert compose["services"]["mosquitto"]["networks"] == [
        "coldsafe-internal",
        "coldsafe-edge",
    ]
    assert compose["services"]["influxdb"]["networks"] == ["coldsafe-internal"]


def test_influxdb_uses_a_named_persistent_volume():
    compose = load_compose()

    assert "influxdb-data" in compose["volumes"]
    assert "influxdb-data:/var/lib/influxdb2" in compose["services"]["influxdb"][
        "volumes"
    ]


def test_mosquitto_mounts_versioned_security_configuration_read_only():
    volumes = load_compose()["services"]["mosquitto"]["volumes"]

    assert "./infra/mosquitto/config/mosquitto.conf:/mosquitto/config/mosquitto.conf:ro" in volumes
    assert "./infra/mosquitto/config/acl:/mosquitto/config/acl:ro" in volumes
    assert "./infra/mosquitto/config/passwords:/mosquitto/config/passwords:ro" in volumes


def test_mosquitto_rejects_anonymous_clients_and_uses_passwords_and_acl():
    content = MOSQUITTO_CONFIG_PATH.read_text(encoding="utf-8")

    assert "allow_anonymous false" in content
    assert "password_file /mosquitto/config/passwords" in content
    assert "acl_file /mosquitto/config/acl" in content


def test_mqtt_roles_have_least_privilege():
    acl = MOSQUITTO_ACL_PATH.read_text(encoding="utf-8")

    assert "user coldsafe-device\ntopic write coldsafe/v1/telemetry" in acl
    assert "user coldsafe-backend\ntopic read coldsafe/v1/telemetry" in acl
    assert "topic read $SYS/#" in acl
