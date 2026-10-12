from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch
from uuid import uuid4

from backend.app.services.alerts import AlertService


def test_alert_history_scopes_owner_and_intersects_requested_period() -> None:
    owner, alert_id = uuid4(), uuid4()
    start = datetime(2026, 9, 24, 10, tzinfo=UTC)
    end = start + timedelta(hours=1)
    cursor = Mock()
    cursor.execute.return_value = cursor
    cursor.fetchall.return_value = [{
        "id": alert_id, "kind": "temperature_high",
        "opened_at": start - timedelta(minutes=5), "closed_at": start + timedelta(minutes=5),
    }]

    @contextmanager
    def fake_connection(_settings):
        class Connection:
            def cursor(self, **_kwargs):
                return contextmanager(lambda: (yield cursor))()
        yield Connection()

    with patch("backend.app.services.alerts.connect", fake_connection):
        rows = AlertService(Mock(), Mock()).list_for_device(
            "owned", owner, start=start, end=end, limit=300,
        )

    sql, params = cursor.execute.call_args.args
    assert "e.owner_user_id = %s" in sql
    assert "a.opened_at < %s" in sql
    assert "a.closed_at > %s" in sql
    assert params == ("owned", owner, end, end, start, start, 300)
    assert rows[0]["alert_id"] == str(alert_id)
    assert rows[0]["status"] == "closed"
