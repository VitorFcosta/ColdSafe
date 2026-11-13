"""Boundary checks for facts sent to the local model."""
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
from uuid import uuid4
import json

import pytest

from backend.app.services.assistant_context import AssistantContext, equipment, number


@pytest.mark.parametrize('value', [None, '2', True, float('inf'), float('nan'), 10 ** 1000])
def test_nonfinite_or_non_numeric_values_are_absent(value):
    assert number(value) is None


def test_numeric_values_are_compact_without_changing_units():
    assert number(12.3456789) == 12.3457
    assert number(0) == 0


def test_explicitly_unavailable_prediction_never_exposes_numbers():
    now = datetime.now(UTC)
    item = equipment({'device': 'a', 'reading': {'data': {}}, 'received_at': now,
                      'prediction': {'status': 'unavailable', 'health_score': 90, 'rul_hours': 100}}, now)
    assert item['prediction'] == 'unavailable'
    assert item['health'] is item['rul_h'] is None


@pytest.mark.parametrize('elapsed,reading,display_age', [
    (-.5, 'fresh', 0), (0, 'fresh', 0), (30, 'fresh', 30),
    (30.000001, 'stale', 30), (30.5, 'stale', 30), (31, 'stale', 31),
])
def test_freshness_uses_exact_age_while_display_age_remains_whole_seconds(elapsed, reading, display_age):
    now = datetime.now(UTC)
    item = equipment({
        'device': 'boundary-device', 'received_at': now - timedelta(seconds=elapsed),
        'reading': {'data': {'measurements': {'ambient_temperature': {'value': 7.25, 'unit': 'degC'}}}},
        'prediction': {'status': 'available', 'health_score': 32.5, 'rul_hours': 18.75},
    }, now)
    assert item['reading'] == reading
    assert item['age_s'] == display_age
    assert item['health'] == (32.5 if reading == 'fresh' else None)
    assert item['rul_h'] == (18.75 if reading == 'fresh' else None)
    assert item['sensors'] == ({'ambient_temperature': [7.25, 'degC']} if reading == 'fresh' else {})


def test_maximum_sized_context_stays_bounded_and_only_known_fields_survive(monkeypatch):
    now = datetime.now(UTC)
    row = {'device': 'a' * 64, 'reading': {'data': {'measurements': {
        key: {'value': 1.23456789e308, 'unit': unit}
        for key, unit in {'ambient_temperature': 'degC', 'humidity': 'percent', 'light': 'percent',
                          'vibration': 'mm/s', 'motor_current': 'A', 'motor_temperature': 'degC'}.items()}}},
           'received_at': now - timedelta(seconds=1),
           'prediction': {'status': 'available', 'health_score': 100, 'rul_hours': 1e308,
                          'model_version': 'v' * 80, 'secret': 'private'},
           'devices': 100, 'missing_readings': 90, 'stale_readings': 8, 'fresh_predictions': 2}
    cursor = MagicMock()
    cursor.execute.return_value.fetchall.return_value = [row, {**row, 'device': 'b' * 64}]
    cursor.execute.return_value.fetchone.side_effect = [
        {'temperature': 123, 'predictive': 456},
        {'model_version': 'v' * 80, 'health_mae': 1e308, 'rul_mae': 1e308}]
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    connection.__enter__.return_value = connection
    monkeypatch.setattr('backend.app.services.assistant_context.connect', lambda _: connection)
    monkeypatch.setattr(AssistantContext, '_now', staticmethod(lambda: now))
    result = AssistantContext(None).build(uuid4())
    encoded = json.dumps(result)
    assert len(encoded) <= 1800
    assert 'secret' not in encoded and 'private' not in encoded
    assert len(result['equipment']) == 2
    assert len(result['equipment'][0]['sensors']) == 6
    assert result['equipment'][1]['sensors'] == {}
    assert result['scope']['truncated'] is True
    assert result['model']['test_mae']['rul'] == 1e308
