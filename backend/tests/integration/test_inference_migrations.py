"""Durable inference history/output migrate without altering existing tables."""
from uuid import uuid4

import psycopg
import pytest

from backend.app.repositories.postgres import MIGRATIONS, connect, initialize_schema
from backend.tests.integration.test_aiot_migrations_integration import database

pytestmark = pytest.mark.integration


def test_inference_migration_is_registered():
    assert dict(MIGRATIONS)[10].name == '010_inference_events.sql'


def test_inference_history_output_is_durable_and_constrained(database):
    initialize_schema(database)
    initialize_schema(database)
    with connect(database) as connection:
        assert connection.execute('SELECT max(version) FROM schema_migrations').fetchone() == (12,)
        assert connection.execute('SELECT count(*) FROM inference_events').fetchone() == (0,)
        with pytest.raises(psycopg.errors.ForeignKeyViolation), connection.transaction():
            connection.execute("INSERT INTO inference_events(source_event_id,owner_user_id,device_record_id,"
                "environment_id,equipment_id,received_at,source,prediction_event_id,prediction) "
                "VALUES(%s,%s,%s,%s,%s,now(),'{}',%s,'{}')",
                tuple(uuid4() for _ in range(6)))
