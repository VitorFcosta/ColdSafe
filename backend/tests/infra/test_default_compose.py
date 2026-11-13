"""Validate Compose discovery/merging without a daemon or personal settings."""

import json
import os
from pathlib import Path
import re
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[3]
LAYERS = ("compose.yaml", "compose.aiot.yaml", "compose.jobs.yaml",
          "compose.inference.yaml", "compose.ollama.yaml")
SERVICES = {"frontend", "backend", "simulator", "gateway", "writer", "mosquitto",
            "rabbitmq", "postgres", "influxdb", "generation", "training", "models",
            "ollama", "llm", "mosquitto-init", "rabbitmq-init"}


@pytest.fixture
def compose_model(tmp_path):
    if not shutil.which("docker"):
        pytest.skip("Docker Compose CLI is required; no daemon is used")
    text = "\n".join((ROOT / name).read_text() for name in LAYERS)
    variables = set(re.findall(r"\$\{([A-Z][A-Z0-9_]*)", text))
    required = set(re.findall(r"\$\{([A-Z][A-Z0-9_]*):\?", text))
    values = {key: "fixture-" + "a" * 48 for key in required}
    values.update(GATEWAY_OWNER_USER_ID="00000000-0000-4000-8000-000000000001",
                  WRITER_OWNER_USER_ID="00000000-0000-4000-8000-000000000001")
    env_file = tmp_path / "synthetic.env"
    env_file.write_text("\n".join(key + "=" + value for key, value in values.items()) + "\n")
    env = {key: value for key, value in os.environ.items()
           if key not in variables and not key.startswith("COMPOSE_")}
    env["COMPOSE_DISABLE_ENV_FILE"] = "1"

    def load(*args):
        result = subprocess.run(
            ["docker", "compose", "--env-file", str(env_file), *args,
             "config", "--format", "json"], cwd=ROOT, env=env,
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    return load


def normalized(model):
    return {**model, "services": {
        name: {key: sorted(value, key=lambda mount: mount["target"])
               if key == "volumes" else value
               for key, value in service.items() if key != "profiles"}
        for name, service in model["services"].items()
    }}


def test_plain_compose_includes_the_complete_application(compose_model):
    model = compose_model()
    assert set(model["services"]) == SERVICES
    for name in SERVICES - {"mosquitto-init", "rabbitmq-init"}:
        assert model["services"][name]["healthcheck"]["test"], name
    assert model["services"]["models"]["command"] == [
        "python", "-m", "backend.app.inference_worker"]
    assert model["services"]["backend"]["environment"]["AIOT_ENABLED"] == "true"
    assert model["services"]["frontend"]["build"]["args"]["VITE_AIOT_ENABLED"] == "true"


def test_plain_compose_preserves_the_previous_complete_configuration(compose_model):
    flags = [arg for name in LAYERS for arg in ("-f", name)]
    previous = compose_model(*flags, "--profile", "aiot", "--profile", "simulator")
    assert normalized(compose_model()) == normalized(previous)


def test_explicit_base_still_supports_initial_commissioning(compose_model):
    base = compose_model("-f", "compose.yaml")
    assert set(base["services"]) == {
        "frontend", "backend", "mosquitto", "rabbitmq", "postgres", "influxdb",
        "mosquitto-init", "rabbitmq-init"}
    assert "AIOT_ENABLED" not in base["services"]["backend"]["environment"]


def test_weight_download_remains_an_explicit_preparation(compose_model):
    assert "ollama-prepare" not in compose_model()["services"]
    setup = compose_model("--profile", "llm-setup")
    assert set(setup["services"]) == SERVICES | {"ollama-prepare"}
    assert setup["services"]["ollama-prepare"]["restart"] == "no"
    assert setup["services"]["ollama-prepare"]["networks"] == {"coldsafe-llm-download": None}
