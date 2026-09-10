from pathlib import Path

import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
COMPOSE_PATH = REPOSITORY_ROOT / "compose.yaml"
INTEGRATION_COMPOSE_PATH = REPOSITORY_ROOT / "compose.integration.yaml"
DOCKERIGNORE_PATH = REPOSITORY_ROOT / ".dockerignore"
FRONTEND_DOCKERFILE_PATH = REPOSITORY_ROOT / "frontend" / "Dockerfile"
MOSQUITTO_CONFIG_PATH = (
    REPOSITORY_ROOT / "infra" / "mosquitto" / "config" / "mosquitto.conf"
)
MOSQUITTO_ACL_PATH = (
    REPOSITORY_ROOT / "infra" / "mosquitto" / "config" / "acl"
)


def load_compose():
    return yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))


def load_integration_compose():
    return yaml.safe_load(INTEGRATION_COMPOSE_PATH.read_text(encoding="utf-8"))


def test_compose_contains_only_the_services_that_exist_today():
    compose = load_compose()

    assert set(compose["services"]) == {
        "mosquitto-init",
        "mosquitto",
        "influxdb",
        "backend",
        "frontend",
    }


def test_runtime_images_are_pinned_and_have_healthchecks():
    services = load_compose()["services"]

    assert services["mosquitto-init"]["image"] == "eclipse-mosquitto:2.0.22"
    assert services["mosquitto"]["image"] == "eclipse-mosquitto:2.0.22"
    assert services["influxdb"]["image"] == "influxdb:2.7.12-alpine"
    assert all(
        "healthcheck" in services[name]
        for name in ("mosquitto", "influxdb", "backend")
    )


def test_mosquitto_password_file_is_generated_in_a_private_volume():
    compose = load_compose()
    initializer = compose["services"]["mosquitto-init"]
    mosquitto = compose["services"]["mosquitto"]

    assert initializer["network_mode"] == "none"
    assert initializer["restart"] == "no"
    assert initializer["read_only"] is True
    assert initializer["tmpfs"] == ["/tmp:rw,noexec,nosuid,size=1m"]
    assert "mosquitto-auth:/mosquitto/auth" in initializer["volumes"]
    assert "mosquitto-auth:/mosquitto/auth:ro" in mosquitto["volumes"]
    assert "mosquitto-auth" in compose["volumes"]
    assert not (MOSQUITTO_CONFIG_PATH.parent / "passwords").exists()


def test_mosquitto_waits_for_password_initialization():
    mosquitto = load_compose()["services"]["mosquitto"]

    assert mosquitto["depends_on"]["mosquitto-init"]["condition"] == (
        "service_completed_successfully"
    )


def test_mqtt_backend_role_name_is_not_overridable_without_changing_the_acl():
    mosquitto = load_compose()["services"]["mosquitto"]

    assert mosquitto["environment"]["MQTT_BACKEND_USERNAME"] == "coldsafe-backend"


def test_published_runtime_ports_are_loopback_only():
    services = load_compose()["services"]

    assert services["mosquitto"]["ports"] == ["127.0.0.1:1883:1883"]
    assert services["backend"]["ports"] == ["127.0.0.1:8000:8000"]
    assert services["frontend"]["ports"] == ["127.0.0.1:5173:5173"]
    assert "ports" not in services["influxdb"]


def test_integration_override_publishes_influxdb_only_on_loopback():
    influxdb = load_integration_compose()["services"]["influxdb"]

    assert influxdb["ports"] == ["127.0.0.1:18086:8086"]
    assert influxdb["networks"] == ["coldsafe-internal", "coldsafe-edge"]


def test_services_share_an_internal_network():
    compose = load_compose()

    assert compose["networks"]["coldsafe-internal"]["internal"] is True
    assert all(
        "coldsafe-internal" in compose["services"][name]["networks"]
        for name in ("mosquitto", "influxdb", "backend")
    )


def test_only_mosquitto_uses_the_edge_network_needed_for_host_access():
    compose = load_compose()

    assert "coldsafe-edge" in compose["networks"]
    assert compose["services"]["mosquitto"]["networks"] == [
        "coldsafe-internal",
        "coldsafe-edge",
    ]
    assert compose["services"]["influxdb"]["networks"] == ["coldsafe-internal"]
    assert compose["services"]["backend"]["networks"] == [
        "coldsafe-internal",
        "coldsafe-edge",
    ]


def test_backend_waits_for_healthy_dependencies_and_uses_hardened_image():
    backend = load_compose()["services"]["backend"]

    assert backend["build"]["dockerfile"] == "backend/Dockerfile"
    assert backend["depends_on"] == {
        "mosquitto": {"condition": "service_healthy"},
        "influxdb": {"condition": "service_healthy"},
    }
    assert backend["read_only"] is True
    assert backend["security_opt"] == ["no-new-privileges:true"]


def test_backend_receives_the_allowed_frontend_origins_from_environment():
    backend = load_compose()["services"]["backend"]

    assert backend["environment"]["CORS_ORIGINS"] == "${CORS_ORIGINS:-http://localhost:5173}"


def test_frontend_uses_a_pinned_development_image_with_isolated_dependencies():
    frontend = load_compose()["services"]["frontend"]

    assert frontend["build"] == {"context": "./frontend", "dockerfile": "Dockerfile"}
    assert frontend["depends_on"] == {
        "backend": {"condition": "service_healthy"},
    }
    assert frontend["volumes"] == [
        "./frontend:/app",
        "frontend-node-modules:/app/node_modules",
    ]
    assert frontend["networks"] == ["coldsafe-frontend"]
    assert frontend["security_opt"] == ["no-new-privileges:true"]
    assert "healthcheck" in frontend

    dockerfile = FRONTEND_DOCKERFILE_PATH.read_text(encoding="utf-8")
    assert "FROM node:24.20.0-alpine3.24" in dockerfile
    assert "USER node" in dockerfile


def test_frontend_network_allows_loopback_port_publication():
    compose = load_compose()
    frontend = compose["services"]["frontend"]

    assert frontend["ports"] == ["127.0.0.1:5173:5173"]
    assert frontend["networks"] == ["coldsafe-frontend"]
    assert compose["networks"]["coldsafe-frontend"].get("internal", False) is False


def test_docker_build_context_excludes_local_secrets_and_environments():
    patterns = set(DOCKERIGNORE_PATH.read_text(encoding="utf-8").splitlines())

    assert {".env", ".git", ".venv", "**/__pycache__", ".pytest_cache"} <= patterns


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
    assert "mosquitto-auth:/mosquitto/auth:ro" in volumes


def test_mosquitto_rejects_anonymous_clients_and_uses_passwords_and_acl():
    content = MOSQUITTO_CONFIG_PATH.read_text(encoding="utf-8")

    assert "allow_anonymous false" in content
    assert "password_file /mosquitto/auth/passwords" in content
    assert "acl_file /mosquitto/config/acl" in content


def test_mqtt_roles_have_least_privilege():
    acl = MOSQUITTO_ACL_PATH.read_text(encoding="utf-8")

    assert "user coldsafe-device\ntopic write coldsafe/v1/telemetry" in acl
    assert "user coldsafe-backend\ntopic read coldsafe/v1/telemetry" in acl
    assert "topic read $SYS/#" in acl
