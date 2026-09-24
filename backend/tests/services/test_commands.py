import json
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.app.domain.commands import parse_ack_payload
from backend.app.services.commands import CommandService


class FakeCursor:
    def __init__(self):
        self.now = datetime(2026, 9, 24, tzinfo=UTC)
        self.row = None
        self.audits = []
        self.result = None
        self.statements = []

    def execute(self, sql, params=()):
        self.statements.append(sql)
        if sql.startswith("INSERT INTO actuator_commands"):
            command_id, user_id, actuator, desired, source, device_id, mqtt_id, *_ = params
            self.row = {
                "id": command_id, "device_id": device_id,
                "requested_by_user_id": user_id, "actuator": actuator,
                "desired_on": desired, "origin": source, "status": "pending",
                "requested_at": self.now, "deadline_at": self.now + timedelta(seconds=10),
                "mqtt_device_id": mqtt_id,
            }
            self.result = dict(self.row)
        elif sql.startswith("INSERT INTO audit_events"):
            self.audits.append((params[3], params[4].obj))
            self.result = None
        elif sql.startswith("SELECT c.id"):
            permitted = self.row and (
                "e.owner_user_id" not in sql or params[1] == self.row["requested_by_user_id"]
            )
            self.result = dict(self.row) if permitted else None
        elif sql.startswith("SELECT 1 FROM audit_events"):
            self.result = (1,) if any(event == sql.split("event_type = '")[1].split("'")[0] for event, _ in self.audits) else None
        elif sql.startswith("UPDATE actuator_commands"):
            if "RETURNING" in sql and "WHERE status = 'pending'" in sql:
                rows = []
                if self.row and self.row["status"] == "pending" and self.row["deadline_at"] <= self.now:
                    self.row["status"] = "unconfirmed"
                    rows.append(dict(self.row))
                self.result = rows
            elif "deadline_at <= clock_timestamp()" in sql:
                if self.row and self.row["status"] == "pending" and self.row["deadline_at"] <= self.now:
                    self.row["status"] = "unconfirmed"
                    self.result = {"id": self.row["id"]}
                else:
                    self.result = None
            elif "RETURNING" in sql:
                if self.row and self.row["status"] == "pending":
                    self.row["status"] = "unconfirmed"
                    self.result = dict(self.row)
                else:
                    self.result = None
            elif "status = %s" in sql:
                self.row["status"] = params[0]
                self.result = None
            else:
                self.row["status"] = "unconfirmed"
                self.result = None
        else:
            raise AssertionError(sql)
        return self

    def fetchone(self):
        return self.result

    def fetchall(self):
        return self.result


class FakeService(CommandService):
    def __init__(self, publisher):
        super().__init__(settings=None, publisher=publisher)
        self.db = FakeCursor()
        self.commits = 0

    @contextmanager
    def _cursor(self):
        yield self.db
        self.commits += 1


def request(service, *, desired=True):
    return service.request(uuid4(), "esp32-lab-01", "led", desired, "manual", uuid4())


def ack(command_id, *, state=True, result="applied", device_id="esp32-lab-01", actuator="led"):
    return {
        "schema_version": 2, "command_id": command_id, "device_id": device_id,
        "actuator": actuator, "result": result, "applied_state": state,
        "reason": "ACTUATOR_FAILURE" if result == "rejected" else None,
    }


def test_command_is_committed_pending_before_publication_and_response_stays_pending():
    service = None

    def publish(device_id, payload):
        assert service.commits == 1
        assert service.db.row["status"] == "pending"
        assert service.db.audits[0][0] == "command_requested"
        assert payload["command_id"] == str(service.db.row["id"])
        assert payload["device_id"] == device_id
        assert payload["issued_at"] == service.db.now.isoformat()
        return True

    service = FakeService(publish)
    response = request(service)
    assert response["status"] == "pending"
    assert response["confirmed_state"] is None
    assert service.db.row["deadline_at"] - service.db.row["requested_at"] == timedelta(seconds=10)


@pytest.mark.parametrize(
    ("applied_state", "result", "expected"),
    [(True, "applied", "confirmed"), (False, "applied", "rejected"),
     (None, "rejected", "rejected")],
)
def test_ack_result_requires_matching_applied_state_and_duplicate_is_idempotent(
    applied_state, result, expected
):
    service = FakeService(lambda *_: True)
    response = request(service)
    payload = ack(response["command_id"], state=applied_state, result=result)
    service.handle_ack(payload)
    count = len(service.db.audits)
    service.handle_ack(payload)

    assert service.get(service.db.row["id"])["status"] == expected
    assert service.get(service.db.row["id"])["confirmed_state"] == (True if expected == "confirmed" else None)
    assert len(service.db.audits) == count == 2
    assert service.db.audits[-1][0] == f"command_{expected}"


def test_wrong_device_and_actuator_cannot_confirm_and_mismatch_is_audited_once():
    service = FakeService(lambda *_: True)
    response = request(service)
    invalid = ack(response["command_id"], device_id="esp32-lab-02", actuator="buzzer")
    service.handle_ack(invalid)
    service.handle_ack(invalid)

    assert service.db.row["status"] == "pending"
    assert [name for name, _ in service.db.audits].count("command_ack_mismatch") == 1


def test_timeout_and_late_ack_keep_unconfirmed_and_audit_only_once():
    service = FakeService(lambda *_: True)
    response = request(service)
    service.db.now += timedelta(seconds=11)
    assert service.get(service.db.row["id"])["status"] == "unconfirmed"
    service.handle_ack(ack(response["command_id"]))
    service.handle_ack(ack(response["command_id"]))

    assert service.db.row["status"] == "unconfirmed"
    assert [name for name, _ in service.db.audits] == [
        "command_requested", "command_unconfirmed", "command_ack_late"
    ]
    assert service.expire_pending() == 0


def test_user_query_checks_ownership_before_expiring_or_returning_command():
    service = FakeService(lambda *_: True)
    request(service)
    service.db.now += timedelta(seconds=11)

    assert service.get_for_user(service.db.row["id"], uuid4()) is None
    assert service.db.row["status"] == "pending"
    assert service.get_for_user(
        service.db.row["id"], service.db.row["requested_by_user_id"]
    )["status"] == "unconfirmed"


def test_failed_publish_is_unconfirmed_and_audited():
    service = FakeService(lambda *_: False)
    response = request(service)
    assert response["status"] == "unconfirmed"
    assert service.db.audits[-1] == (
        "command_unconfirmed",
        {"source": "manual", "actuator": "led", "desired_state": True,
         "status": "unconfirmed", "cause": "publish_failed"},
    )


def test_expire_pending_marks_all_due_commands_once():
    service = FakeService(lambda *_: True)
    request(service)
    service.db.now += timedelta(seconds=11)

    assert service.expire_pending() == 1
    assert service.expire_pending() == 0
    assert service.db.row["status"] == "unconfirmed"
    assert [event for event, _ in service.db.audits].count("command_unconfirmed") == 1


def test_ack_parser_rejects_invalid_result_extra_fields_and_oversize():
    valid = {
        "schema_version": 2, "command_id": str(uuid4()), "device_id": "esp32-lab-01",
        "actuator": "led", "result": "applied", "applied_state": True,
    }
    assert parse_ack_payload(json.dumps(valid).encode()).applied_state is True
    for invalid in (
        {**valid, "reason": None},
        {**valid, "applied_state": None},
        {**valid, "device_id": "../other"},
        {**valid, "unexpected": 1},
    ):
        with pytest.raises(ValidationError):
            parse_ack_payload(json.dumps(invalid).encode())
    with pytest.raises(ValueError, match="too large"):
        parse_ack_payload(b"x" * 1025)
