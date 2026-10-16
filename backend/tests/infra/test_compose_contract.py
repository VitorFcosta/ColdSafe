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


def test_messaging_overlay_keeps_legacy_dashboard_and_broker_private():
    overlay = yaml.safe_load((REPOSITORY_ROOT / 'compose.messaging.yaml').read_text())
    assert set(overlay['services']) == {'backend'}
    backend = overlay['services']['backend']
    assert backend['depends_on']['rabbitmq']['condition'] == 'service_healthy'
    assert set(backend['environment']) == {
        'RABBITMQ_HOST', 'RABBITMQ_MANAGEMENT_PORT', 'RABBITMQ_MONITOR_PASSWORD',
    }
    assert backend['environment']['RABBITMQ_HOST'] == 'rabbitmq'
    assert backend['environment']['RABBITMQ_MANAGEMENT_PORT'] == 15672
    assert 'RABBITMQ_MONITOR_PASSWORD:?' in backend['environment']['RABBITMQ_MONITOR_PASSWORD']
    assert 'ports' not in backend


def test_compose_contains_the_relational_database():
    compose = load_compose()

    assert set(compose["services"]) == {
        "rabbitmq-init",
        "rabbitmq",
        "mosquitto-init",
        "mosquitto",
        "simulator",
        "gateway",
        "writer",
        "influxdb",
        "postgres",
        "backend",
        "frontend",
    }


def test_runtime_images_are_pinned_and_have_healthchecks():
    services = load_compose()["services"]

    assert services["mosquitto-init"]["image"] == "coldsafe-mosquitto:2.0.22"
    assert services["mosquitto"]["image"] == "coldsafe-mosquitto:2.0.22"
    assert services["influxdb"]["image"] == "influxdb:2.7.12-alpine"
    assert services["postgres"]["image"] == "postgres:17.11-alpine3.24"
    assert all(
        "healthcheck" in services[name]
        for name in ("mosquitto", "influxdb", "postgres", "backend")
    )


def test_writer_is_optional_private_and_receives_only_its_influx_token():
    writer = load_compose()['services']['writer']
    assert writer['profiles'] == ['aiot']
    assert writer['build']['dockerfile'] == 'writer/Dockerfile'
    assert writer['read_only'] is True
    assert writer['user'] == '65532:65532'
    assert writer['networks'] == ['coldsafe-internal']
    assert 'ports' not in writer
    assert writer['environment']['INFLUXDB_LIVE_BUCKET'] == 'telemetry_live'
    assert 'INFLUXDB_WRITER_TOKEN' in writer['environment']
    assert 'INFLUXDB_TOKEN' not in writer['environment']
    assert 'DOCKER_INFLUXDB_INIT_ADMIN_TOKEN' not in writer['environment']
    assert 'RABBITMQ_GATEWAY_PASSWORD' not in writer['environment']


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


def test_mosquitto_security_files_are_private_and_owned_by_the_runtime_user():
    compose = load_compose()
    initializer = compose["services"]["mosquitto-init"]
    mosquitto = compose["services"]["mosquitto"]
    initializer_command = "\n".join(initializer["command"])

    assert initializer["cap_add"] == ["CHOWN"]
    assert (
        "install -m 0600 /tmp/passwords /mosquitto/auth/passwords"
        in initializer_command
    )
    assert (
        "install -m 0600 /bootstrap/acl /mosquitto/auth/acl"
        in initializer_command
    )
    assert (
        "chown 1883:1883 /mosquitto/auth/passwords /mosquitto/auth/acl"
        in initializer_command
    )
    assert (
        "COPY config/acl /bootstrap/acl"
        in (REPOSITORY_ROOT / "infra/mosquitto/Dockerfile").read_text()
    )
    assert mosquitto["user"] == "1883:1883"
    assert "./infra/mosquitto/config/acl:/mosquitto/config/acl:ro" not in mosquitto[
        "volumes"
    ]

    config = MOSQUITTO_CONFIG_PATH.read_text(encoding="utf-8")
    assert "acl_file /mosquitto/auth/acl" in config


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

    assert "ports" not in services["mosquitto"]
    assert "ports" not in services["backend"]
    assert services["frontend"]["ports"] == ["127.0.0.1:5173:8080"]
    assert "ports" not in services["influxdb"]


def test_integration_override_publishes_influxdb_only_on_loopback():
    influxdb = load_integration_compose()["services"]["influxdb"]

    assert influxdb["ports"] == ["127.0.0.1:18086:8086"]
    assert influxdb["networks"] == ["coldsafe-internal", "coldsafe-edge"]


def test_integration_override_publishes_postgres_only_on_loopback():
    postgres = load_integration_compose()["services"]["postgres"]

    assert postgres["ports"] == ["127.0.0.1:15432:5432"]
    assert postgres["networks"] == ["coldsafe-internal", "coldsafe-edge"]


def test_services_share_an_internal_network():
    compose = load_compose()

    assert compose["networks"]["coldsafe-internal"]["internal"] is True
    assert all(
        "coldsafe-internal" in compose["services"][name]["networks"]
        for name in ("mosquitto", "influxdb", "postgres", "backend")
    )


def test_only_frontend_uses_the_edge_network_needed_for_host_access():
    compose = load_compose()

    assert "coldsafe-edge" in compose["networks"]
    assert compose["services"]["frontend"]["networks"] == [
        "coldsafe-internal",
        "coldsafe-edge",
    ]
    assert compose["services"]["influxdb"]["networks"] == ["coldsafe-internal"]
    assert compose["services"]["postgres"]["networks"] == ["coldsafe-internal"]
    assert compose["services"]["backend"]["networks"] == ["coldsafe-internal"]
    assert compose["services"]["mosquitto"]["networks"] == ["coldsafe-internal"]


def test_backend_waits_for_healthy_dependencies_and_uses_hardened_image():
    backend = load_compose()["services"]["backend"]

    assert backend["build"]["dockerfile"] == "backend/Dockerfile"
    assert backend["depends_on"] == {
        "mosquitto": {"condition": "service_healthy"},
        "influxdb": {"condition": "service_healthy"},
        "postgres": {"condition": "service_healthy"},
    }
    assert backend["read_only"] is True
    assert backend["security_opt"] == ["no-new-privileges:true"]


def test_backend_receives_the_allowed_frontend_origins_from_environment():
    backend = load_compose()["services"]["backend"]

    assert backend["environment"]["CORS_ORIGINS"] == "${CORS_ORIGINS:-http://localhost:5173}"


def test_backend_requires_a_private_jwt_signing_key():
    assert load_compose()["services"]["backend"]["environment"]["AUTH_JWT_SECRET"].startswith("${AUTH_JWT_SECRET:?")


def test_frontend_uses_a_pinned_static_image_with_isolated_dependencies():
    frontend = load_compose()["services"]["frontend"]

    assert frontend["build"] == {"context": "./frontend", "dockerfile": "Dockerfile"}
    assert frontend["depends_on"] == {
        "backend": {"condition": "service_healthy"},
    }
    assert "volumes" not in frontend
    assert frontend["networks"] == ["coldsafe-internal", "coldsafe-edge"]
    assert frontend["security_opt"] == ["no-new-privileges:true"]
    assert "healthcheck" in frontend

    dockerfile = FRONTEND_DOCKERFILE_PATH.read_text(encoding="utf-8")
    assert "FROM node:24.20.0-alpine3.24" in dockerfile
    assert "USER node" in dockerfile


def test_frontend_network_allows_loopback_port_publication():
    compose = load_compose()
    frontend = compose["services"]["frontend"]

    assert frontend["ports"] == ["127.0.0.1:5173:8080"]
    assert frontend["networks"] == ["coldsafe-internal", "coldsafe-edge"]
    assert (compose["networks"]["coldsafe-edge"] or {}).get("internal", False) is False


def test_docker_build_context_excludes_local_secrets_and_environments():
    patterns = set(DOCKERIGNORE_PATH.read_text(encoding="utf-8").splitlines())

    assert {".env", ".git", ".venv", "**/__pycache__", ".pytest_cache"} <= patterns


def test_influxdb_uses_a_named_persistent_volume():
    compose = load_compose()

    assert "influxdb-data" in compose["volumes"]
    assert "influxdb-data:/var/lib/influxdb2" in compose["services"]["influxdb"][
        "volumes"
    ]


def test_postgres_uses_a_private_persistent_volume():
    compose = load_compose()
    postgres = compose["services"]["postgres"]

    assert "postgres-data:/var/lib/postgresql/data" in postgres["volumes"]
    assert "postgres-data" in compose["volumes"]
    assert "ports" not in postgres
    assert postgres["environment"]["POSTGRES_PASSWORD"].startswith("${POSTGRES_PASSWORD:?")


def test_mosquitto_uses_static_configuration_and_private_read_only_credentials():
    services = load_compose()["services"]
    mosquitto_volumes = services["mosquitto"]["volumes"]

    assert (
        "COPY config/mosquitto.conf /mosquitto/config/mosquitto.conf"
        in (REPOSITORY_ROOT / "infra/mosquitto/Dockerfile").read_text()
    )
    assert (
        "COPY config/acl /bootstrap/acl"
        in (REPOSITORY_ROOT / "infra/mosquitto/Dockerfile").read_text()
    )
    assert "mosquitto-auth:/mosquitto/auth:ro" in mosquitto_volumes
    assert services["mosquitto"]["read_only"] is True


def test_mosquitto_rejects_anonymous_clients_and_uses_passwords_and_acl():
    content = MOSQUITTO_CONFIG_PATH.read_text(encoding="utf-8")

    assert "allow_anonymous false" in content
    assert "password_file /mosquitto/auth/passwords" in content
    assert "acl_file /mosquitto/auth/acl" in content


def test_mqtt_roles_have_least_privilege():
    acl = MOSQUITTO_ACL_PATH.read_text(encoding="utf-8")

    assert "user coldsafe-device\ntopic write coldsafe/v1/telemetry" in acl
    assert "user coldsafe-backend\ntopic read coldsafe/v1/telemetry" in acl
    assert "topic read $SYS/#" in acl

    roles = {}
    for section in acl.strip().split("\n\n"):
        user, *permissions = section.splitlines()
        roles[user.removeprefix("user ")] = set(permissions)
    first = roles["coldsafe-device"]
    second = roles["coldsafe-device-02"]
    backend = roles["coldsafe-backend"]
    for device, permissions in (("esp32-lab-01", first), ("esp32-lab-02", second)):
        prefix = f"coldsafe/v2/devices/{device}"
        assert {
            f"topic write {prefix}/telemetry",
            f"topic read {prefix}/commands",
            f"topic write {prefix}/acks",
        } <= permissions
    assert not any("esp32-lab-02" in permission for permission in first)
    assert not any("esp32-lab-01" in permission for permission in second)
    assert "topic read coldsafe/v2/devices/+/telemetry" in backend
    assert "topic write coldsafe/v2/devices/+/commands" in backend
    assert "topic read coldsafe/v2/devices/+/acks" in backend
