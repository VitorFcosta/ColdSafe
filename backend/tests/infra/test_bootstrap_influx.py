import importlib.util
import json
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def bootstrap():
    spec = importlib.util.spec_from_file_location("bootstrap_influx", ROOT / "scripts/bootstrap-influx.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Influx:
    def __init__(self):
        self.buckets = [{"id": "legacy-id", "name": "telemetry", "orgID": "org"}]
        self.auths = []
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)
        if args[:2] == ("bucket", "list"):
            return self.buckets.copy()
        if args[:2] == ("bucket", "create"):
            bucket = {"id": "live-id", "name": "telemetry_live", "orgID": "org",
                      "retentionRules": [{"type": "expire", "everySeconds": 604800}]}
            self.buckets.append(bucket)
            return [bucket]
        if args[:2] == ("auth", "list"):
            return self.auths.copy()
        assert args[:2] == ("auth", "create")
        permissions = [f"{flag[2:].split('-')[0]}:orgs/org/buckets/{args[index + 1]}"
            for index, flag in enumerate(args) if flag in ("--read-bucket", "--write-bucket")]
        auth = {"description": args[args.index("--description") + 1], "status": "active",
                "token": f"private-token-{len(self.auths)}", "permissions": permissions}
        self.auths.append(auth)
        return [auth]


def test_bootstrap_is_idempotent_private_and_preserves_existing_configuration(bootstrap, tmp_path):
    target = tmp_path / ".env"
    target.write_text("# preserve\nDOCKER_INFLUXDB_INIT_ORG=coldsafe\nINFLUXDB_TOKEN= # pending\nCUSTOM=value\n")
    influx = Influx()
    assert bootstrap.provision(target, influx) == 2
    first = target.read_bytes()
    assert "CUSTOM=value\n" in first.decode()
    assert "# pending" in first.decode()
    assert target.stat().st_mode & 0o777 == 0o600
    assert bootstrap.provision(target, influx) == 0
    assert target.read_bytes() == first
    assert len(influx.auths) == 2
    assert len(influx.buckets) == 2
    assert len(influx.auths[1]["permissions"]) == 1
    assert influx.auths[1]["permissions"][0] == "write:orgs/org/buckets/live-id"


@pytest.mark.parametrize("failure", ["broad", "inactive", "wrong-existing", "retention"])
def test_refuses_bad_existing_resources_without_rotating_or_changing_env(bootstrap, tmp_path, failure):
    target = tmp_path / ".env"
    target.write_text("INFLUXDB_TOKEN=\n")
    influx = Influx()
    bootstrap.provision(target, influx)
    if failure == "broad":
        influx.auths[0]["permissions"][0] = "read:orgs/org/buckets"
    elif failure == "inactive":
        influx.auths[0]["status"] = "inactive"
    elif failure == "retention":
        influx.buckets[1]["retentionRules"][0]["everySeconds"] = 0
    else:
        target.write_text("INFLUXDB_TOKEN=private-invalid\n")
    original = target.read_bytes()
    with pytest.raises(ValueError) as error:
        bootstrap.provision(target, influx)
    assert "private-" not in str(error.value)
    assert target.read_bytes() == original
    assert len(influx.auths) == 2


def test_recovers_created_tokens_after_local_write_failure(bootstrap, tmp_path, monkeypatch):
    target = tmp_path / ".env"
    target.write_text("INFLUXDB_TOKEN=\n")
    influx = Influx()
    original_replace = bootstrap.os.replace
    monkeypatch.setattr(bootstrap.os, "replace", lambda *_: (_ for _ in ()).throw(OSError()))
    with pytest.raises(OSError):
        bootstrap.provision(target, influx)
    monkeypatch.setattr(bootstrap.os, "replace", original_replace)
    bootstrap.provision(target, influx)
    assert len(influx.auths) == 2
    assert list(tmp_path.iterdir()) == [target]


def test_cli_captures_secrets_uses_container_admin_and_ignores_shell_overrides(bootstrap, tmp_path, monkeypatch):
    target = tmp_path / ".env"
    target.write_text("INFLUXDB_TOKEN=\nPOSTGRES_PASSWORD=file-password\n")
    monkeypatch.setenv("POSTGRES_PASSWORD", "shell-password")
    monkeypatch.setenv("INFLUXDB_TOKEN", "shell-token")
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, json.dumps([]), "")

    monkeypatch.setattr(bootstrap.subprocess, "run", run)
    assert bootstrap.cli(target, "isolated", ["compose.yaml"])("bucket", "list") == []
    command, kwargs = calls[0]
    assert "isolated" in command
    assert "shell-password" not in str(command)
    assert "shell-token" not in str(command)
    assert "DOCKER_INFLUXDB_INIT_ADMIN_TOKEN" in str(command)
    assert "POSTGRES_PASSWORD" not in kwargs["env"]
    assert kwargs["env"]["INFLUXDB_TOKEN"] == "bootstrap-not-used"
    assert kwargs["capture_output"] is True


def test_cli_failure_does_not_expose_captured_output(bootstrap, tmp_path, monkeypatch):
    target = tmp_path / ".env"
    target.write_text("INFLUXDB_TOKEN=\n")
    monkeypatch.setattr(bootstrap.subprocess, "run", lambda command, **kwargs:
                        subprocess.CompletedProcess(command, 1, "private-token", "private-password"))
    with pytest.raises(ValueError) as error:
        bootstrap.cli(target, None, ["compose.yaml"])("bucket", "list")
    assert "private" not in str(error.value)


@pytest.mark.parametrize("content", ["INFLUXDB_TOKEN=one\nINFLUXDB_TOKEN=two\n", "private-invalid-line\n"])
def test_invalid_env_is_rejected_before_contacting_database(bootstrap, tmp_path, content):
    target = tmp_path / ".env"
    target.write_text(content)
    influx = Influx()
    with pytest.raises(ValueError):
        bootstrap.provision(target, influx)
    assert not influx.calls
    assert target.read_text() == content


def test_symlink_is_rejected_before_contacting_database(bootstrap, tmp_path):
    real = tmp_path / "real"
    real.write_text("INFLUXDB_TOKEN=\n")
    target = tmp_path / ".env"
    target.symlink_to(real)
    influx = Influx()
    with pytest.raises(ValueError):
        bootstrap.provision(target, influx)
    assert not influx.calls
    assert target.is_symlink()


def test_main_reports_counts_without_credentials(bootstrap, tmp_path, monkeypatch, capsys):
    target = tmp_path / ".env"
    target.write_text("INFLUXDB_TOKEN=\n")
    monkeypatch.setattr(bootstrap.sys, "argv", ["bootstrap-influx.py", "--env-file", str(target)])
    influx = Influx()
    monkeypatch.setattr(bootstrap, "cli", lambda *_: influx)
    assert bootstrap.main() == 0
    assert bootstrap.main() == 0
    output = capsys.readouterr()
    assert "saved 2" in output.out
    assert "saved 0" in output.out
    assert not output.err
    assert "private-token" not in output.out


@pytest.mark.parametrize("failure", [OSError("private-path"), UnicodeDecodeError("utf8", b"x", 0, 1, "private"),
                                    subprocess.TimeoutExpired("private-command", 30)])
def test_main_redacts_operating_system_and_subprocess_errors(bootstrap, tmp_path, monkeypatch, capsys, failure):
    monkeypatch.setattr(bootstrap.sys, "argv", ["bootstrap-influx.py"])
    monkeypatch.setattr(bootstrap, "cli", lambda *_: (_ for _ in ()).throw(failure))
    assert bootstrap.main() == 1
    output = capsys.readouterr()
    assert "private" not in output.out + output.err
    assert "Traceback" not in output.err


def test_wrong_response_is_sanitized(bootstrap, tmp_path, monkeypatch):
    target = tmp_path / ".env"
    target.write_text("INFLUXDB_TOKEN=\n")
    for output in ("not-json-private", '"private-response"'):
        monkeypatch.setattr(bootstrap.subprocess, "run", lambda command, **kwargs:
                            subprocess.CompletedProcess(command, 0, output, ""))
        with pytest.raises(ValueError) as error:
            bootstrap.cli(target, None, ["compose.yaml"])("bucket", "list")
        assert "private" not in str(error.value)


@pytest.mark.parametrize("permissions", [None, {}, [{"resource": "private"}], ["read:orgs/org/buckets/legacy-id"],
                                         ["read:orgs/other/buckets/legacy-id", "write:orgs/org/buckets/legacy-id"]])
def test_malformed_or_foreign_permissions_are_rejected(bootstrap, permissions):
    auth = {"token": "private", "status": "active", "permissions": permissions}
    bucket = {"id": "legacy-id", "orgID": "org"}
    assert not bootstrap.restricted(auth, bucket, ("read", "write"))
