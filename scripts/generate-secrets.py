#!/usr/bin/env python3
"""Fill missing local credentials without rotating existing secrets."""

import argparse
import os
from pathlib import Path
import re
import secrets
import stat
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
SECRET_KEYS = (
    "AUTH_JWT_SECRET", "POSTGRES_PASSWORD", "DOCKER_INFLUXDB_INIT_PASSWORD",
    "DOCKER_INFLUXDB_INIT_ADMIN_TOKEN", "MQTT_BACKEND_PASSWORD",
    "MQTT_DEVICE_PASSWORD", "MQTT_DEVICE_02_PASSWORD",
    "MQTT_SIMULATOR_PASSWORD", "MQTT_SIMULATOR_OPERATOR_PASSWORD", "MQTT_GATEWAY_PASSWORD",
    *(f"RABBITMQ_{role}_PASSWORD" for role in (
        "GATEWAY", "WRITER", "INFERENCE", "DELIVERY", "COMMANDS", "GENERATION",
        "TRAINING", "OBSERVABILITY", "API", "AUDIT", "MONITOR")),
)
ASSIGNMENT = re.compile(
    r"(?P<prefix>[ \t]*(?:export[ \t]+)?(?P<key>[A-Za-z_][A-Za-z0-9_]*)"
    r"[ \t]*=[ \t]*)(?P<raw>.*?)(?P<newline>\r?\n)?"
)


def read_regular(path):
    if path.is_symlink():
        raise ValueError("Refusing symbolic link input.")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    if not stat.S_ISREG(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise ValueError("Input must be a regular file.")
    with os.fdopen(descriptor, "rb") as source:
        return source.read()


def parse(lines):
    entries = {}
    for index, line in enumerate(lines):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = ASSIGNMENT.fullmatch(line)
        if not match:
            raise ValueError(f"Invalid .env assignment on line {index + 1}.")
        key, raw = match["key"], match["raw"].strip()
        if key in entries:
            raise ValueError(f"Duplicate .env key on line {index + 1}.")
        if raw.startswith(("'", '"')):
            quoted = re.fullmatch(r"(['\"])((?:\\.|(?!\1).)*)\1(?:[ \t]+#.*)?", raw)
            if not quoted:
                raise ValueError(f"Invalid quoted .env value on line {index + 1}.")
            value = quoted[2]
        else:
            value = re.split(r"(?:^|[ \t]+)#", raw, maxsplit=1)[0].strip()
        entries[key] = (index, value, match)
    return entries


def generate(env_file, example):
    env_file, example = Path(env_file), Path(example)
    if env_file.is_symlink():
        raise ValueError("Refusing symbolic link target.")
    exists = env_file.exists()
    original = read_regular(env_file if exists else example)
    try:
        content = original.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("The .env file must be UTF-8.") from None
    lines = content.splitlines(keepends=True)
    entries = parse(lines)
    newline = "\r\n" if "\r\n" in content else "\n"
    keys = dict.fromkeys((*SECRET_KEYS, *(key for key in entries
                                        if key.startswith("MQTT_") and key.endswith("PASSWORD"))))
    used = {entry[1] for entry in entries.values()}
    updates = {}
    for key in keys:
        if key in entries and entries[key][1]:
            continue
        value = secrets.token_urlsafe(32)
        while value in used:
            value = secrets.token_urlsafe(32)
        used.add(value)
        updates[key] = value
    generated = len(updates)
    if not entries.get("DOCKER_INFLUXDB_INIT_USERNAME", (None, ""))[1]:
        updates["DOCKER_INFLUXDB_INIT_USERNAME"] = "coldsafe-admin"
    for key, value in updates.items():
        if key in entries:
            index, _, match = entries[key]
            comment = re.search(r"[ \t]*#.*$", match["raw"])
            suffix = " " + comment[0].lstrip() if comment else ""
            lines[index] = match["prefix"] + value + suffix + (match["newline"] or "")
        else:
            if lines and not lines[-1].endswith("\n"):
                lines[-1] += newline
            lines.append(f"{key}={value}{newline}")
    updated = "".join(lines).encode("utf-8")
    if exists and updated == original:
        descriptor = os.open(env_file, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            os.fchmod(descriptor, 0o600)
        finally:
            os.close(descriptor)
        return generated
    descriptor, temporary = tempfile.mkstemp(prefix=f".{env_file.name}.", dir=env_file.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(updated)
            output.flush()
            os.fsync(output.fileno())
        if env_file.is_symlink():
            raise ValueError("Refusing symbolic link target.")
        os.replace(temporary, env_file)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return generated


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--example", type=Path, default=ROOT / ".env.example")
    args = parser.parse_args()
    try:
        count = generate(args.env_file, args.example)
    except (OSError, ValueError) as error:
        message = str(error) if isinstance(error, ValueError) else "Unable to access or save the .env file."
        print(message, file=sys.stderr)
        return 1
    print(f"Generated {count} missing secrets; .env permissions: 0600.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
