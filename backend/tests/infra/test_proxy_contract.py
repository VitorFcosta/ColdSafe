from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]


def test_frontend_is_the_only_normal_published_service():
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text())
    published = {name: service["ports"] for name, service in compose["services"].items() if "ports" in service}
    assert published == {"frontend": ["127.0.0.1:5173:8080"]}
    assert compose["services"]["frontend"]["networks"] == ["coldsafe-internal", "coldsafe-edge"]
    for name in ("backend", "mosquitto", "influxdb", "postgres", "rabbitmq"):
        assert compose["services"][name]["networks"] == ["coldsafe-internal"]


def test_frontend_serves_static_build_non_root_with_no_source_mounts():
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text())
    frontend = compose["services"]["frontend"]
    assert "volumes" not in frontend
    assert "environment" not in frontend
    assert frontend["user"] == "101:101"
    assert frontend["read_only"] is True
    dockerfile = (ROOT / "frontend/Dockerfile").read_text()
    assert "RUN npm run build" in dockerfile
    assert "nginxinc/nginx-unprivileged:" in dockerfile
    assert "@sha256:" in dockerfile
    assert "USER 101:101" in dockerfile
    assert 'ENTRYPOINT ["nginx"]' in dockerfile


def test_proxy_handles_api_docs_health_and_websocket_without_logging_credentials():
    config = (ROOT / "frontend/nginx.conf").read_text()
    for location in ("api/", "health/", "docs", "redoc", "openapi\\.json"):
        assert location in config
    assert "proxy_pass http://api_backend;" in config
    assert "proxy_set_header Upgrade $http_upgrade;" in config
    assert "proxy_set_header Connection $connection_upgrade;" in config
    assert "proxy_set_header X-Forwarded-For $remote_addr;" in config
    assert "try_files $uri $uri/ /index.html;" in config
    assert "$request_uri" not in config
    assert "$args" not in config


def test_optional_diagnostics_are_loopback_only():
    debug = yaml.safe_load((ROOT / "compose.debug.yaml").read_text())
    assert debug["services"]["backend"]["ports"] == ["127.0.0.1:8000:8000"]
    assert debug["services"]["mosquitto"]["ports"] == ["127.0.0.1:1883:1883"]
    assert debug["services"]["rabbitmq"]["ports"] == ["127.0.0.1:15672:15672"]
    assert all(port.startswith("127.0.0.1:") for service in debug["services"].values()
               for port in service.get("ports", []))
