"""Offline/accepted-telemetry adapters for the same causal feature kernel."""
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

import numpy as np

from backend.app.domain.features import FeatureBatch, FeatureSpec, extract_features
from backend.app.domain.feature_preprocessing import FeatureTransform, TRANSFORM_VERSION
from backend.app.services.generation import DTYPE, MEASUREMENTS

LIVE_NAMES = dict(zip(MEASUREMENTS, ('ambient_temperature', 'humidity', 'light',
    'vibration', 'motor_current', 'motor_temperature'), strict=True))


def features_version(spec: FeatureSpec) -> str:
    return f'{spec.version}+{TRANSFORM_VERSION}'


def offline_features(rows: np.ndarray, spec: FeatureSpec = FeatureSpec()) -> FeatureBatch:
    if not isinstance(rows, np.ndarray) or rows.ndim != 1 or rows.dtype != DTYPE:
        raise ValueError('Offline features require structured offline-numpy-v1 rows')
    if len(np.unique(rows['equipment_index'])) > 1:
        raise ValueError('Feature history must contain one equipment only')
    times = rows['observed_at'].astype(np.int64)
    values = np.column_stack([rows[name] for name in spec.sensors])
    return extract_features(times, values, times, spec)


def _milliseconds(value: str) -> int:
    if not isinstance(value, str):
        raise ValueError('UTC timestamp required')
    instant = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if instant.tzinfo is None or instant.utcoffset().total_seconds() != 0:
        raise ValueError('UTC timestamp required')
    delta = instant - datetime(1970, 1, 1, tzinfo=UTC)
    return delta.days * 86_400_000 + delta.seconds * 1000 + delta.microseconds // 1000


def telemetry_features(history: Sequence[dict], equipment_id: str, cutoff_received_at: str,
                       transform: FeatureTransform, spec: FeatureSpec = FeatureSpec()) -> FeatureBatch:
    """Use already-authorized telemetry; scope/schema validation remains upstream.

    Accepted received_at, truncated to milliseconds, is the online time axis.
    This adapter never uses device occurred_at, labels, IDs or future values in X.
    """
    UUID(equipment_id)
    if transform.names != spec.names:
        raise ValueError('Transform and feature layout differ')
    times, measurements = [], []
    for event in history:
        if (event['schema_version'] != 3 or event['type'] != 'telemetry' or
                event['data']['equipment']['equipment_id'] != equipment_id):
            raise ValueError('Telemetry history must belong to one equipment')
        times.append(_milliseconds(event['received_at']))
        values = []
        for sensor in spec.sensors:
            measurement = event['data']['measurements'][LIVE_NAMES[sensor]]
            value = measurement['value']
            if measurement['unit'] != MEASUREMENTS[sensor] or type(value) not in (int, float, type(None)):
                raise ValueError('Canonical telemetry measurement/unit required')
            values.append(np.nan if value is None else value)
        measurements.append(values)
    result = extract_features(np.array(times, dtype=np.int64),
        np.array(measurements, dtype=np.float64).reshape(len(times), len(spec.sensors)),
        np.array([_milliseconds(cutoff_received_at)], dtype=np.int64), spec)
    if result.sufficient[0]:
        return FeatureBatch(transform.apply(result.values, spec.names), result.sufficient)
    return result
