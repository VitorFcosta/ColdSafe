import importlib.util
import os
from pathlib import Path
import re
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts/generate-secrets.py"
EXPECTED_SECRETS = {
    "AUTH_JWT_SECRET", "POSTGRES_PASSWORD", "DOCKER_INFLUXDB_INIT_PASSWORD",
    "DOCKER_INFLUXDB_INIT_ADMIN_TOKEN", "MQTT_BACKEND_PASSWORD",
    "MQTT_DEVICE_PASSWORD", "MQTT_DEVICE_02_PASSWORD",
    "MQTT_SIMULATOR_PASSWORD", "MQTT_SIMULATOR_OPERATOR_PASSWORD", "MQTT_GATEWAY_PASSWORD",
    *(f"RABBITMQ_{role}_PASSWORD" for role in (
        "GATEWAY", "WRITER", "INFERENCE", "DELIVERY", "COMMANDS", "GENERATION",
        "TRAINING", "OBSERVABILITY", "API", "AUDIT", "MONITOR")),
}


@pytest.fixture
def generator():
    spec = importlib.util.spec_from_file_location("generate_secrets", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def assignments(path):
    return dict(line.split("=", 1) for line in path.read_text().splitlines()
                if line and not line.startswith("#"))


def test_new_file_copies_example_and_generates_distinct_private_secrets(generator, tmp_path):
    example = tmp_path / "example"
    example.write_text("# preserve configuration\nAPP_ENV=development\nINFLUXDB_TOKEN=\n")
    target = tmp_path / ".env"
    assert generator.generate(target, example) == len(EXPECTED_SECRETS)
    values = assignments(target)
    assert set(EXPECTED_SECRETS) <= values.keys()
    assert values["APP_ENV"] == "development"
    assert values["DOCKER_INFLUXDB_INIT_USERNAME"] == "coldsafe-admin"
    assert values["INFLUXDB_TOKEN"] == ""
    passwords = [values[key] for key in EXPECTED_SECRETS]
    assert len(set(passwords)) == len(passwords)
    assert all(re.fullmatch(r"[A-Za-z0-9_-]{43}", value) for value in passwords)
    assert target.stat().st_mode & 0o777 == 0o600


def test_second_run_preserves_every_byte_and_only_fixes_permissions(generator, tmp_path):
    target = tmp_path / ".env"
    generator.generate(target, ROOT / ".env.example")
    target.write_bytes(target.read_bytes().replace(b"\n", b"\r\n"))
    original = target.read_bytes()
    target.chmod(0o644)
    assert generator.generate(target, tmp_path / "nonexistent") == 0
    assert target.read_bytes() == original
    assert target.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("empty", ["", "''", '""', " # empty", '"" # empty'])
def test_fills_only_empty_fields_and_preserves_other_lines(generator, tmp_path, empty):
    target = tmp_path / ".env"
    original = ("# personal settings\nCUSTOM=value\nINFLUXDB_TOKEN=restricted-existing\n"
                "MQTT_BACKEND_PASSWORD='existing password' # keep\n"
                "DOCKER_INFLUXDB_INIT_USERNAME=personal-admin\n"
                f"AUTH_JWT_SECRET={empty}\n")
    target.write_text(original)
    generator.generate(target, tmp_path / "must-not-read")
    updated = target.read_text()
    assert updated.startswith(original[:original.index("AUTH_JWT_SECRET=")])
    assert assignments(target)["AUTH_JWT_SECRET"]
    assert assignments(target)["DOCKER_INFLUXDB_INIT_USERNAME"] == "personal-admin"


@pytest.mark.parametrize("content", [
    "AUTH_JWT_SECRET=private-value\nAUTH_JWT_SECRET=another-value\n",
    "AUTH_JWT_SECRET='private-value\n", "AUTH_JWT_SECRET=\"private-value\n",
    "AUTH_JWT_SECRET='private-value' trailing\n", "private-value\n",
    "export AUTH_JWT_SECRET=private-value\nAUTH_JWT_SECRET=duplicate\n",
])
def test_invalid_input_is_rejected_without_changing_file_or_leaking_values(generator, tmp_path, content):
    target = tmp_path / ".env"
    target.write_text(content)
    with pytest.raises(ValueError) as error:
        generator.generate(target, ROOT / ".env.example")
    assert "private-value" not in str(error.value)
    assert target.read_text() == content


@pytest.mark.parametrize("broken", [False, True])
def test_refuses_target_symlink(generator, tmp_path, broken):
    linked = tmp_path / "personal"
    if not broken:
        linked.write_text("AUTH_JWT_SECRET=preserve\n")
    target = tmp_path / ".env"
    target.symlink_to(linked)
    with pytest.raises(ValueError, match="symbolic|symlink"):
        generator.generate(target, ROOT / ".env.example")
    assert target.is_symlink()
    if not broken:
        assert linked.read_text() == "AUTH_JWT_SECRET=preserve\n"


def test_refuses_example_symlink_and_nonregular_input(generator, tmp_path):
    example = tmp_path / "example"
    example.symlink_to(ROOT / ".env.example")
    with pytest.raises(ValueError):
        generator.generate(tmp_path / ".env", example)
    with pytest.raises(ValueError):
        generator.generate(tmp_path, ROOT / ".env.example")


def test_failed_atomic_replace_keeps_original_and_removes_temporary_file(generator, tmp_path, monkeypatch):
    target = tmp_path / ".env"
    target.write_text("CUSTOM=preserve\n")
    original = target.read_bytes()

    def fail_replace(source, destination):
        assert Path(source).stat().st_mode & 0o777 == 0o600
        assert Path(source).read_bytes() != original
        raise OSError("simulated replacement failure")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError):
        generator.generate(target, ROOT / ".env.example")
    assert target.read_bytes() == original
    assert list(tmp_path.iterdir()) == [target]


def test_existing_custom_mqtt_password_is_filled(generator, tmp_path):
    target = tmp_path / ".env"
    target.write_text("export MQTT_CUSTOM_PASSWORD=\n# a comment\n")
    generator.generate(target, ROOT / ".env.example")
    assert re.search(r"export MQTT_CUSTOM_PASSWORD=[A-Za-z0-9_-]{43}", target.read_text())


def test_random_collision_retries_without_reusing_existing_secret(generator, tmp_path, monkeypatch):
    target = tmp_path / ".env"
    existing = "x" * 43
    target.write_text(f"AUTH_JWT_SECRET='{existing}'\n")
    sequence = iter([existing, *(f"generated-{index}" for index in range(len(EXPECTED_SECRETS)))])
    monkeypatch.setattr(generator.secrets, "token_urlsafe", lambda size: next(sequence))
    generator.generate(target, ROOT / ".env.example")
    values = assignments(target)
    assert values["AUTH_JWT_SECRET"] == f"'{existing}'"
    assert values["POSTGRES_PASSWORD"] == "generated-0"
    assert len({values[key] for key in EXPECTED_SECRETS}) == len(EXPECTED_SECRETS)


def test_rejects_invalid_utf8_and_preserves_original_bytes(generator, tmp_path):
    target = tmp_path / ".env"
    original = b"AUTH_JWT_SECRET=\xff\n"
    target.write_bytes(original)
    with pytest.raises(ValueError, match="UTF-8"):
        generator.generate(target, ROOT / ".env.example")
    assert target.read_bytes() == original


def test_no_trailing_newline_keeps_existing_value_when_appending_keys(generator, tmp_path):
    target = tmp_path / ".env"
    target.write_text('AUTH_JWT_SECRET="existing\\\"quoted" # preserved')
    generator.generate(target, ROOT / ".env.example")
    assert target.read_text().startswith('AUTH_JWT_SECRET="existing\\\"quoted" # preserved\n')


def test_cli_reports_only_counts_and_invalid_input_does_not_leak(tmp_path):
    target = tmp_path / ".env"
    command = [sys.executable, str(SCRIPT), "--env-file", str(target),
               "--example", str(ROOT / ".env.example")]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    for key in EXPECTED_SECRETS:
        assert assignments(target)[key] not in result.stdout + result.stderr
    second = subprocess.run(command, capture_output=True, text=True)
    assert second.returncode == 0
    assert "0" in second.stdout
    target.write_text("AUTH_JWT_SECRET='private-value\n")
    invalid = subprocess.run(command, capture_output=True, text=True)
    assert invalid.returncode != 0
    assert "private-value" not in invalid.stdout + invalid.stderr
    assert "Traceback" not in invalid.stderr
