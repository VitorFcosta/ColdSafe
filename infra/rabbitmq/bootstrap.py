"""Generate private RabbitMQ definitions; no credentials belong in Git."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sys


VHOST = "coldsafe"
UUID_KEY = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
# One transport identity per future service; no business consumers start here.
SERVICE_ROLES = {
    "gateway": (("command",), ("telemetry", "ack", "processing_error")),
    "writer": (("telemetry",), ("processing_error",)),
    "inference": (("telemetry", "model_activation"), ("prediction", "model_status", "processing_error")),
    "delivery": (("telemetry", "ack", "prediction", "command_status", "alert", "freshness",
                  "job_progress", "model_status", "processing_error"), ("processing_error",)),
    "commands": (("telemetry", "ack", "prediction", "freshness"),
                 ("command", "command_status", "alert", "freshness", "processing_error")),
    "generation": ((), ("job_progress", "processing_error")),
    "training": ((), ("job_progress", "model_status", "processing_error")),
    "observability": (("#",), ()),
    "api": ((), ("command", "job_requested", "model_activation", "processing_error")),
    "audit": ((), ()),
}


def password_hash(password):
    salt = secrets.token_bytes(4)
    return base64.b64encode(salt + hashlib.sha256(salt + password.encode()).digest()).decode()


def build_definitions(passwords):
    for role in SERVICE_ROLES:
        value = passwords.get(role, "")
        if not isinstance(value, str) or len(value) < 32 or value.startswith("REPLACE_WITH_"):
            raise ValueError(f"Set RABBITMQ_{role.upper()}_PASSWORD (at least 32 characters)")
    if len(set(passwords[role] for role in SERVICE_ROLES)) != len(SERVICE_ROLES):
        raise ValueError("RabbitMQ service passwords must be distinct")
    queue_roles = tuple(role for role in SERVICE_ROLES if role not in ("api", "audit"))
    return {
        "vhosts": [{"name": VHOST}],
        "users": [{"name": f"coldsafe-{role}", "password_hash": password_hash(passwords[role]),
                   "hashing_algorithm": "rabbit_password_hashing_sha256", "tags": []}
                  for role in SERVICE_ROLES],
        "permissions": [resource_permissions(role) for role in SERVICE_ROLES],
        "topic_permissions": [topic_permissions(role, writes) for role, (_, writes) in SERVICE_ROLES.items()],
        "exchanges": [exchange("events", "topic"), exchange("dlx", "topic"),
                      exchange("jobs", "headers", {"alternate-exchange": "coldsafe.jobs.unrouted"}),
                      exchange("jobs.unrouted", "fanout")],
        "queues": [{"name": f"coldsafe.{role}", "vhost": VHOST, "durable": True,
                    "auto_delete": False, "arguments": {"x-queue-type": "quorum"}}
                   for role in (*queue_roles, "dlq")],
        "bindings": bindings(queue_roles),
        "policies": [{"name": "bounded-failures", "vhost": VHOST,
                      "pattern": r"^coldsafe\.(gateway|writer|inference|delivery|commands|generation|training|observability)$",
                      "apply-to": "quorum_queues", "priority": 10,
                      "definition": {"dead-letter-exchange": "coldsafe.dlx",
                                     "dead-letter-strategy": "at-least-once", "overflow": "reject-publish",
                                     "delivery-limit": 2, "delayed-retry-type": "failed",
                                     "delayed-retry-min": 1000, "delayed-retry-max": 2000,
                                     "max-length-bytes": 67108864}}],
    }


def resource_permissions(role):
    writes = SERVICE_ROLES[role][1]
    queue = "dlq" if role == "audit" else role
    return {"user": f"coldsafe-{role}", "vhost": VHOST, "configure": "^$",
            "write": r"^coldsafe\.events$" if writes else "^$",
            "read": rf"^coldsafe\.{queue}$" if role != "api" else "^$"}


def topic_permissions(role, writes):
    types = "|".join(re.escape(kind) for kind in writes)
    return {"user": f"coldsafe-{role}", "vhost": VHOST, "exchange": "coldsafe.events",
            "write": rf"^v3\.({types})\.{UUID_KEY}$" if types else "^$", "read": "^$"}


def exchange(name, kind, arguments=None):
    return {"name": f"coldsafe.{name}", "vhost": VHOST, "type": kind, "durable": True,
            "auto_delete": False, "internal": False, "arguments": arguments or {}}


def binding(source, destination, key, kind="queue", arguments=None):
    return {"source": f"coldsafe.{source}", "vhost": VHOST, "destination": f"coldsafe.{destination}",
            "destination_type": kind, "routing_key": key, "arguments": arguments or {}}


def bindings(queue_roles):
    event_bindings = [binding("events", role, "v3.#" if kind == "#" else f"v3.{kind}.*")
                      for role in queue_roles for kind in SERVICE_ROLES[role][0]]
    return [*event_bindings, binding("events", "jobs", "v3.job_requested.*", "exchange"),
            *[binding("jobs", role, "", arguments={"x-match": "all", "job_type": role})
              for role in ("generation", "training")],
            binding("dlx", "dlq", "#"), binding("jobs.unrouted", "dlq", "")]


def main():
    definitions = build_definitions({role: os.environ.get(f"RABBITMQ_{role.upper()}_PASSWORD", "")
                                    for role in SERVICE_ROLES})
    target = Path(sys.argv[1])
    temporary = target.with_suffix(".tmp")
    os.umask(0o077)
    temporary.write_text(json.dumps(definitions))
    temporary.chmod(0o440)
    temporary.replace(target)


if __name__ == "__main__":
    main()
