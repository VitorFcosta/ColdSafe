import base64
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from infra.rabbitmq.bootstrap import SERVICE_ROLES, build_definitions


ROOT = Path(__file__).resolve().parents[3]


def passwords():
    return {role: f"test-only-{role}-{'x' * 32}" for role in SERVICE_ROLES}


def test_topology_has_no_guest_or_admin_and_uses_private_vhost():
    definitions = build_definitions(passwords())
    assert definitions["vhosts"] == [{"name": "coldsafe"}]
    assert {user["name"] for user in definitions["users"]} == {
        f"coldsafe-{role}" for role in SERVICE_ROLES
    }
    for user in definitions["users"]:
        assert user["tags"] == (["management"] if user["name"] == "coldsafe-monitor" else [])
        raw = base64.b64decode(user["password_hash"])
        role = user["name"].removeprefix("coldsafe-")
        assert raw[4:] == hashlib.sha256(raw[:4] + passwords()[role].encode()).digest()
        assert passwords()[role] not in json.dumps(definitions)


@pytest.mark.parametrize("invalid", ["", "guest", "REPLACE_WITH_password_" + "x" * 30])
def test_rejects_missing_short_or_placeholder_passwords(invalid):
    values = {**passwords(), "gateway": invalid}
    with pytest.raises(ValueError, match="RABBITMQ_GATEWAY_PASSWORD"):
        build_definitions(values)


def test_rejects_shared_passwords_and_missing_roles():
    with pytest.raises(ValueError, match="distinct"):
        build_definitions({role: "x" * 32 for role in SERVICE_ROLES})
    with pytest.raises(ValueError, match="RABBITMQ_GATEWAY_PASSWORD"):
        build_definitions({role: value for role, value in passwords().items() if role != "gateway"})


def test_services_cannot_configure_or_read_other_queues():
    definitions = build_definitions(passwords())
    for permission in definitions["permissions"]:
        assert permission["configure"] == "^$"
        role = permission["user"].removeprefix("coldsafe-")
        for queue in definitions["queues"]:
            expected = queue["name"] == f"coldsafe.{role}" or (
                role == "audit" and queue["name"] == "coldsafe.dlq"
            )
            assert bool(re.fullmatch(permission["read"], queue["name"])) == expected
        assert not re.fullmatch(permission["write"], "amq.default")
        assert not re.fullmatch(permission["write"], "coldsafe.dlx")


def test_monitor_can_inspect_metrics_but_cannot_access_or_change_messages():
    definitions = build_definitions(passwords())
    monitor = next(user for user in definitions["users"] if user["name"] == "coldsafe-monitor")
    assert monitor["tags"] == ["management"]
    permission = next(item for item in definitions["permissions"] if item["user"] == monitor["name"])
    assert {key: permission[key] for key in ("configure", "write", "read")} == {
        "configure": "^$", "write": "^$", "read": "^$",
    }
    assert "coldsafe.monitor" not in {queue["name"] for queue in definitions["queues"]}
    assert "RABBITMQ_MONITOR_PASSWORD" in yaml.safe_load((ROOT / "compose.yaml").read_text())["services"]["rabbitmq-init"]["environment"]


def test_queues_limit_failed_deliveries_and_preserve_dead_letters():
    definitions = build_definitions(passwords())
    assert len(definitions["queues"]) == 9
    assert all(queue["durable"] and queue["arguments"]["x-queue-type"] == "quorum"
               for queue in definitions["queues"])
    policy = definitions["policies"][0]
    assert not re.fullmatch(policy["pattern"], "coldsafe.dlq")
    assert policy["definition"]["delivery-limit"] == 2
    assert policy["definition"]["dead-letter-strategy"] == "at-least-once"
    assert policy["definition"]["overflow"] == "reject-publish"
    assert policy["definition"]["delayed-retry-type"] == "failed"
    assert policy["definition"]["delayed-retry-min"] == 1000
    assert policy["definition"]["delayed-retry-max"] == 2000


def test_observer_gets_dead_letter_copies_without_a_dead_letter_cycle():
    definitions = build_definitions(passwords())
    for source in ('coldsafe.dlx', 'coldsafe.jobs.unrouted'):
        assert {item['destination'] for item in definitions['bindings']
                if item['source'] == source} == {'coldsafe.dlq', 'coldsafe.observability'}
    policies = [policy for policy in definitions['policies']
                if re.fullmatch(policy['pattern'], 'coldsafe.observability')]
    assert len(policies) == 1
    assert policies[0]['definition'] == {
        'max-length-bytes': 8388608, 'overflow': 'drop-head', 'delivery-limit': 2,
    }


def test_only_writer_can_publish_persistence_proof_and_both_api_roles_receive_it():
    definitions = build_definitions(passwords())
    route = 'v3.telemetry_persisted.00000000-0000-4000-8000-000000000001'
    for permissions in definitions['topic_permissions']:
        assert bool(re.fullmatch(permissions['write'], route)) == (permissions['user'] == 'coldsafe-writer')
    destinations = {item['destination'] for item in definitions['bindings']
                    if item['routing_key'] == 'v3.telemetry_persisted.*'}
    assert destinations == {'coldsafe.commands', 'coldsafe.delivery'}


def test_bootstrap_writes_private_hashes_atomically(tmp_path):
    import os
    env = {**os.environ, **{f"RABBITMQ_{role.upper()}_PASSWORD": value
                              for role, value in passwords().items()}}
    target = tmp_path / "definitions.json"
    result = subprocess.run([sys.executable, str(ROOT / "infra/rabbitmq/bootstrap.py"),
                             str(target)], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert target.stat().st_mode & 0o777 == 0o440
    assert len(json.loads(target.read_text())["users"]) == len(SERVICE_ROLES)
    assert not target.with_suffix(".tmp").exists()


def test_rabbitmq_is_internal_and_bootstrap_is_offline():
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text())
    broker = compose["services"]["rabbitmq"]
    init = compose["services"]["rabbitmq-init"]
    assert broker["image"] == "coldsafe-rabbitmq:4.3.6-management-alpine"
    assert "ports" not in broker
    assert broker["networks"] == ["coldsafe-internal"]
    assert broker["depends_on"]["rabbitmq-init"]["condition"] == "service_completed_successfully"
    assert broker["mem_limit"] == "512m"
    assert init["network_mode"] == "none"
    assert init["read_only"] is True
    assert all("PASSWORD" not in key for key in broker.get("environment", {}))
    assert len(init["environment"]) == len(SERVICE_ROLES)
    config = (ROOT / "infra/rabbitmq/rabbitmq.conf").read_text()
    assert "definitions.local.path = /etc/rabbitmq/bootstrap/definitions.json" in config
