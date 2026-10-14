"""Exercise the static frontend and proxy against the real disposable stack."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from websockets.sync.client import connect
import yaml


ROOT = Path(__file__).resolve().parents[3]
pytestmark = pytest.mark.integration


def command(base, *args, input=None):
    # pytest's per-test JWT key must not override the disposable Compose env file.
    keys = {line.split("=", 1)[0] for line in (ROOT / ".env.example").read_text().splitlines()
            if line and not line.startswith("#") and "=" in line}
    env = {key: value for key, value in os.environ.items() if key not in keys} if base[:2] == ["docker", "compose"] else None
    result = subprocess.run([*base, *args], input=input, env=env,
                            capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, result.stderr + "\n" + result.stdout
    return result.stdout


def request(base, path, *, method="GET", data=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(base + path, method=method, headers=headers,
                  data=json.dumps(data).encode() if data is not None else None)
    with urlopen(req, timeout=10) as response:
        return response.status, response.read()


@pytest.fixture(scope="module")
def stack():
    if os.environ.get("COLDSAFE_PROXY_INTEGRATION") != "1":
        pytest.skip("Set COLDSAFE_PROXY_INTEGRATION=1 to run a disposable full stack")
    project = "coldsafe-b208-" + secrets.token_hex(4)
    with tempfile.TemporaryDirectory(prefix="coldsafe-b208-") as folder:
        temporary = Path(folder)
        env = temporary / ".env"
        command([sys.executable, str(ROOT / "scripts/generate-secrets.py")], "--env-file", str(env))
        # A placeholder permits parsing while only InfluxDB starts; never run backend with it.
        env.write_text(env.read_text().replace("INFLUXDB_TOKEN=\n", "INFLUXDB_TOKEN=bootstrap-not-used\n"))
        config = yaml.safe_load((ROOT / "compose.yaml").read_text())
        services = config["services"]
        for role, service in services.items():
            if "build" in service:
                services[role] = {**service, "image": f"{project}-{role}",
                                  "build": {**service["build"], "context": str(ROOT / service["build"]["context"])}}
        config["services"]["frontend"] = {**services["frontend"], "ports": ["127.0.0.1::8080"]}
        file = temporary / "compose.yaml"
        file.write_text(yaml.safe_dump(config))
        base = ["docker", "compose", "-p", project, "--env-file", str(env), "-f", str(file)]
        try:
            command(base, "up", "-d", "--wait", "--wait-timeout", "120", "influxdb")
            bootstrap = '''
import json,os,urllib.request
url='http://127.0.0.1:8086/api/v2/'
headers={'Authorization':'Token '+os.environ['ADMIN_TOKEN'],'Content-Type':'application/json'}
def get(path):
 return json.load(urllib.request.urlopen(urllib.request.Request(url+path,headers=headers)))
org=get('orgs')['orgs'][0]['id']
bucket=get('buckets')['buckets']
bucket=next(b for b in bucket if b['name']=='telemetry')['id']
body={'orgID':org,'description':'coldsafe-proxy-test','permissions':[{'action':action,'resource':{'type':'buckets','id':bucket,'orgID':org}} for action in ['read','write']]}
r=urllib.request.Request(url+'authorizations',data=json.dumps(body).encode(),headers=headers)
print(json.load(urllib.request.urlopen(r))['token'])
'''
            values = dict(line.split("=", 1) for line in env.read_text().splitlines() if line and not line.startswith("#"))
            # Execute inside InfluxDB's network namespace without publishing its port.
            container = command(base, "ps", "-q", "influxdb").strip()
            process_env = {**os.environ, "ADMIN_TOKEN": values["DOCKER_INFLUXDB_INIT_ADMIN_TOKEN"]}
            result = subprocess.run(["docker", "run", "--rm", "--network", "container:" + container,
                                     "--env", "ADMIN_TOKEN", "python:3.13.15-slim", "python", "-c", bootstrap],
                                    env=process_env, capture_output=True, text=True, timeout=30)
            assert result.returncode == 0, "Unable to provision restricted InfluxDB test token"
            env.write_text(env.read_text().replace("INFLUXDB_TOKEN=bootstrap-not-used", "INFLUXDB_TOKEN=" + result.stdout.strip()))
            env.chmod(0o600)
            command(base, "up", "-d", "--build", "--wait", "--wait-timeout", "180")
            port = command(base, "port", "frontend", "8080").strip().rsplit(":", 1)[1]
            yield {"base": base, "url": "http://127.0.0.1:" + port, "env": env, "values": values}
        finally:
            command(base, "down", "--volumes", "--remove-orphans")


def test_static_spa_docs_openapi_and_health_are_available_via_frontend(stack):
    for path in ("/", "/dashboard", "/manage", "/docs", "/redoc", "/health/live", "/health/ready", "/openapi.json"):
        status, body = request(stack["url"], path)
        assert status == 200 and body
        if path in ("/", "/dashboard", "/manage"):
            assert b'id="app"' in body
            assert b"@vite/client" not in body
    spec = json.loads(request(stack["url"], "/openapi.json")[1])
    assert "/api/v1/auth/ws-ticket" in spec["paths"]
    with pytest.raises(HTTPError) as error:
        request(stack["url"], "/api/v1/not-a-route")
    assert error.value.code == 404
    assert b"id=\"app\"" not in error.value.read()


def test_rest_ticket_websocket_and_second_start_preserve_data_and_secrets(stack):
    url = stack["url"]
    account = {"email": "proxy-" + secrets.token_hex(4) + "@example.invalid", "password": secrets.token_urlsafe(18)}
    assert request(url, "/api/v1/auth/register", method="POST", data=account)[0] == 201
    token = json.loads(request(url, "/api/v1/auth/login", method="POST", data=account)[1])["data"]["token"]
    environment = json.loads(request(url, "/api/v1/environments", method="POST", data={"name": "Preserved proxy lab"}, token=token)[1])["data"]["id"]
    device = json.loads(request(url, f"/api/v1/environments/{environment}/devices", method="POST",
                                data={"name": "ESP32", "mqtt_device_id": "esp32-lab-01"}, token=token)[1])["data"]
    ticket = json.loads(request(url, "/api/v1/auth/ws-ticket", method="POST", data={"device_id": "esp32-lab-01"}, token=token)[1])["data"]["ticket"]
    with connect(url.replace("http://", "ws://") + "/api/v1/events?device_id=esp32-lab-01", open_timeout=10) as ws:
        ws.send(json.dumps({"ticket": ticket}))
        reading = {"schema_version": 2, "device_id": "esp32-lab-01", "temperature_c": 5.4321,
                   "humidity_percent": 61.234, "light_percent": 42}
        # Device password enters through stdin, never in the host command arguments/output.
        publish = 'read -r password; exec mosquitto_pub -h 127.0.0.1 -u coldsafe-device -P "$password" -t coldsafe/v2/devices/esp32-lab-01/telemetry -q 1 -m '\
                  + "'" + json.dumps(reading) + "'"
        received = []
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            # The stream has no ready frame; publish after authentication can settle.
            command(stack["base"], "exec", "-T", "mosquitto", "sh", "-ec", publish,
                    input=stack["values"]["MQTT_DEVICE_PASSWORD"] + "\n")
            try:
                event = json.loads(ws.recv(timeout=1))
            except TimeoutError:
                continue
            received.append(event)
            if event.get("type") == "reading":
                assert event["data"]["temperature_c"] == reading["temperature_c"]
                break
        assert any(event.get("type") == "reading" for event in received)
    before = hashlib.sha256(stack["env"].read_bytes()).hexdigest()
    command([sys.executable, str(ROOT / "scripts/generate-secrets.py")], "--env-file", str(stack["env"]))
    assert hashlib.sha256(stack["env"].read_bytes()).hexdigest() == before
    command(stack["base"], "down")
    command(stack["base"], "up", "-d", "--wait", "--wait-timeout", "180")
    port = command(stack["base"], "port", "frontend", "8080").strip().rsplit(":", 1)[1]
    restarted = "http://127.0.0.1:" + port
    # Verify both the secret on disk and the effective runtime configuration.
    assert hashlib.sha256(stack["env"].read_bytes()).hexdigest() == before
    key_hash = command(stack["base"], "exec", "-T", "backend", "python", "-c",
                       "import os,hashlib; print(hashlib.sha256(os.environ['AUTH_JWT_SECRET'].encode()).hexdigest())").strip()
    assert key_hash == hashlib.sha256(stack["values"]["AUTH_JWT_SECRET"].encode()).hexdigest()
    fresh = json.loads(request(restarted, "/api/v1/auth/login", method="POST", data=account)[1])["data"]["token"]
    assert json.loads(request(restarted, "/api/v1/auth/me", token=fresh)[1])["success"] is True
    saved = json.loads(request(restarted, f"/api/v1/devices/{device['id']}", token=token)[1])["data"]
    assert saved["id"] == device["id"]
    history = json.loads(request(restarted, "/api/v1/readings?device_id=esp32-lab-01&period=1h&limit=10", token=token)[1])["data"]["readings"]
    assert any(item["temperature_c"] == 5.4321 for item in history)
    for role in ("frontend", "backend"):
        user = command(stack["base"], "exec", "-T", role, "id", "-u").strip()
        assert user != "0"
    for role in ("backend", "mosquitto", "postgres", "influxdb", "rabbitmq"):
        container = command(stack["base"], "ps", "-q", role).strip()
        bindings = subprocess.check_output(["docker", "inspect", "--format", "{{json .HostConfig.PortBindings}}", container], text=True).strip()
        assert json.loads(bindings) in ({}, None)
