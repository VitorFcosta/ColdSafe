#!/usr/bin/env python3
"""Provision missing restricted InfluxDB credentials without exposing or rotating secrets."""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("generate_secrets", ROOT / "scripts/generate-secrets.py")
CONFIG = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONFIG)


def cli(env_file, project_name, compose_files):
    entries = CONFIG.parse(CONFIG.read_regular(env_file).decode("utf-8").splitlines(keepends=True))
    environment = {key: value for key, value in os.environ.items()
                   if key not in entries and not key.startswith("COMPOSE_")}
    if not entries.get("INFLUXDB_TOKEN", (None, ""))[1]:
        environment["INFLUXDB_TOKEN"] = "bootstrap-not-used"
    command = ["docker", "compose", "--env-file", str(Path(env_file).absolute())]
    if project_name:
        command += ["--project-name", project_name]
    for compose_file in compose_files:
        command += ["-f", str(compose_file)]

    def run(*arguments):
        result = subprocess.run([
            *command, "exec", "-T", "influxdb", "sh", "-ec",
            'export INFLUX_TOKEN="$DOCKER_INFLUXDB_INIT_ADMIN_TOKEN"; exec influx "$@"',
            "influx", *arguments, "--host", "http://127.0.0.1:8086", "--json",
        ], cwd=ROOT, env=environment, capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise ValueError("InfluxDB command failed; check service health and original administrative credentials.")
        try:
            data = json.loads(result.stdout)
        except (ValueError, TypeError):
            raise ValueError("InfluxDB returned invalid JSON.") from None
        if not isinstance(data, (list, dict)):
            raise ValueError("InfluxDB returned an unexpected response.")
        rows = data if isinstance(data, list) else [data]
        if not all(isinstance(row, dict) for row in rows):
            raise ValueError("InfluxDB returned an unexpected response.")
        return rows

    return run


def restricted(auth, bucket, actions):
    permissions = auth.get("permissions", [])
    expected = {f"{action}:orgs/{bucket['orgID']}/buckets/{bucket['id']}" for action in actions}
    return (auth.get("status") == "active" and isinstance(auth.get("token"), str) and bool(auth["token"])
            and isinstance(permissions, list) and all(isinstance(item, str) for item in permissions)
            and len(permissions) == len(expected) and set(permissions) == expected)


def token(run, auths, existing, description, bucket, actions, org):
    matches = [auth for auth in auths if
               (auth.get("token") == existing if existing else auth.get("description") == description)]
    if existing or matches:
        if len(matches) != 1 or not restricted(matches[0], bucket, actions):
            raise ValueError("Existing InfluxDB authorization is missing, inactive or has unexpected permissions; no rotation performed.")
        return matches[0]["token"]
    arguments = ["auth", "create", "--org", org, "--description", description]
    for action in actions:
        arguments += [f"--{action}-bucket", bucket["id"]]
    created = run(*arguments)
    if len(created) != 1 or not restricted(created[0], bucket, actions):
        raise ValueError("New InfluxDB authorization has unexpected permissions.")
    return created[0]["token"]


def save(env_file, original, lines, entries, updates):
    newline = "\r\n" if b"\r\n" in original else "\n"
    for key, value in updates.items():
        # InfluxDB 2.7 tokens are base64 strings, safe for a literal .env assignment.
        if not re.fullmatch(r"[A-Za-z0-9_+/=-]+", value):
            raise ValueError("InfluxDB returned an unsupported token format.")
        if key in entries:
            index, _, match = entries[key]
            comment = re.search(r"[ \t]*#.*$", match["raw"])
            suffix = " " + comment[0].lstrip() if comment else ""
            lines[index] = match["prefix"] + value + suffix + (match["newline"] or "")
        else:
            if lines and not lines[-1].endswith("\n"):
                lines[-1] += newline
            lines.append(f"{key}={value}{newline}")
    descriptor, temporary = tempfile.mkstemp(prefix=f".{env_file.name}.", dir=env_file.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write("".join(lines).encode("utf-8"))
            output.flush()
            os.fsync(output.fileno())
        if CONFIG.read_regular(env_file) != original:
            raise ValueError("The .env file changed during bootstrap; rerun without concurrent editors.")
        os.replace(temporary, env_file)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def provision(env_file, run):
    env_file = Path(env_file)
    original = CONFIG.read_regular(env_file)
    lines = original.decode("utf-8").splitlines(keepends=True)
    entries = CONFIG.parse(lines)
    org = entries.get("DOCKER_INFLUXDB_INIT_ORG", (None, "coldsafe"))[1] or "coldsafe"
    legacy_name = entries.get("DOCKER_INFLUXDB_INIT_BUCKET", (None, "telemetry"))[1] or "telemetry"
    if legacy_name == "telemetry_live":
        raise ValueError("Legacy and live buckets must be distinct.")
    buckets = run("bucket", "list", "--org", org)
    legacy = [bucket for bucket in buckets if bucket.get("name") == legacy_name]
    live = [bucket for bucket in buckets if bucket.get("name") == "telemetry_live"]
    if len(legacy) != 1 or len(live) > 1:
        raise ValueError("Expected legacy bucket is missing or bucket names are ambiguous.")
    if not legacy[0].get("id") or not legacy[0].get("orgID"):
        raise ValueError("InfluxDB returned an invalid legacy bucket.")
    if not live:
        live = run("bucket", "create", "--org", org, "--name", "telemetry_live", "--retention", "168h")
    if (len(live) != 1 or live[0].get("orgID") != legacy[0].get("orgID")
            or len(live[0].get("retentionRules", [])) != 1
            or live[0]["retentionRules"][0].get("everySeconds") != 604800):
        raise ValueError("Existing live bucket must have 168h retention in the expected organization; no changes performed.")
    auths = run("auth", "list", "--org", org)
    updates = {}
    for key, description, bucket, actions in (
        ("INFLUXDB_TOKEN", "coldsafe-backend-telemetry", legacy[0], ("read", "write")),
        ("INFLUXDB_WRITER_TOKEN", "coldsafe-writer-live", live[0], ("write",)),
    ):
        existing = entries.get(key, (None, ""))[1]
        value = token(run, auths, existing, description, bucket, actions, org)
        if not existing:
            updates[key] = value
    if updates:
        save(env_file, original, lines, entries, updates)
    else:
        descriptor = os.open(env_file, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            os.fchmod(descriptor, 0o600)
        finally:
            os.close(descriptor)
    return len(updates)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--project-name")
    parser.add_argument("--compose-file", action="append")
    args = parser.parse_args()
    try:
        count = provision(args.env_file, cli(args.env_file, args.project_name,
                                            args.compose_file or [ROOT / "compose.yaml"]))
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        message = str(error) if isinstance(error, ValueError) and not isinstance(error, UnicodeError) else "Unable to access .env or complete the InfluxDB command."
        print(message, file=sys.stderr)
        return 1
    print(f"InfluxDB bootstrap verified; saved {count} missing restricted credentials; .env permissions: 0600.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
