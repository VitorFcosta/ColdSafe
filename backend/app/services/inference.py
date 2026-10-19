"""Causal live inference with a PostgreSQL history and durable prediction outbox."""
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid5

import numpy as np
from psycopg.types.json import Jsonb
from threadpoolctl import threadpool_limits

from backend.app.domain.features import FeatureSpec
from backend.app.repositories.postgres import connect
from backend.app.services.feature_inputs import features_version, telemetry_features
from backend.app.services.model_bundle import LoadedBundle
from backend.app.services.models import ModelService
from gateway.bridge import PermanentError


MAX_HISTORY = 10_000


def utc_now() -> datetime:
    return datetime.now(UTC)


class InferenceService:
    def __init__(self, settings, catalog: dict, owner: UUID, models: ModelService, *, clock=utc_now):
        self.settings, self.catalog, self.owner, self.models = settings, catalog, owner, models
        self.clock = clock

    def _authorize(self, connection) -> None:
        if connection.execute('SELECT 1 FROM devices d JOIN environments e ON e.id=d.environment_id '
                'WHERE d.id=%s AND d.mqtt_device_id=%s AND e.id=%s AND e.owner_user_id=%s '
                'AND d.is_active FOR SHARE OF d,e',
                (self.catalog['device_record_id'], self.catalog['device_id'],
                 self.catalog['environment_id'], self.owner)).fetchone() is None:
            raise PermanentError('UNAUTHORIZED_SCOPE')

    def _history(self, connection, source: dict, bundle: LoadedBundle) -> list[dict]:
        instant = datetime.fromisoformat(source['received_at'].replace('Z', '+00:00'))
        cutoff = instant.replace(microsecond=instant.microsecond // 1000 * 1000)
        lower = cutoff - timedelta(seconds=max(bundle.spec.windows_seconds))
        scope = (self.owner, source['device_record_id'], source['data']['equipment']['equipment_id'])
        # One anchor proves the full span; excess samples fail explicitly instead of changing the training kernel.
        return [row[0] for row in connection.execute(
            'SELECT source FROM ('
            '(SELECT source,received_at,source_event_id FROM inference_events '
            'WHERE owner_user_id=%s AND device_record_id=%s AND equipment_id=%s '
            'AND received_at >= %s AND received_at < %s) UNION ALL '
            '(SELECT source,received_at,source_event_id FROM inference_events '
            'WHERE owner_user_id=%s AND device_record_id=%s AND equipment_id=%s '
            'AND received_at < %s ORDER BY received_at DESC,source_event_id DESC LIMIT 1)'
            ') history ORDER BY received_at,source_event_id LIMIT %s',
            (*scope, lower, cutoff, *scope, lower, MAX_HISTORY + 1)).fetchall()]

    def _prediction(self, source: dict, bundle: LoadedBundle | None,
                    active: dict | None, history: list[dict]) -> dict:
        now = self.clock()
        received = datetime.fromisoformat(source['received_at'].replace('Z', '+00:00'))
        if received > now:
            raise PermanentError('INVALID_BINDING')
        data = {'equipment_id': source['data']['equipment']['equipment_id'],
            'source_event_id': source['event_id'], 'input_received_at': source['received_at'],
            'features_version': active['features_version'] if active else features_version(FeatureSpec()),
            'model_id': str(active['model_id']) if active else None,
            'model_version': active['model_version'] if active else None,
            'status': 'unavailable', 'health_score': None, 'rul_hours': None, 'reason': 'no_model'}
        if active is not None:
            data['reason'] = 'model_unavailable'
            if now - received > timedelta(seconds=30):
                data['reason'] = 'stale_input'
            elif (bundle is not None and str(bundle.model_id) == str(active['model_id'])
                    and bundle.model_version == active['model_version']
                    and bundle.features_version == active['features_version']):
                data['reason'] = 'invalid_features'
                if len(history) <= MAX_HISTORY:
                    try:
                        batch = telemetry_features(history, data['equipment_id'],
                            source['received_at'], bundle.transform, bundle.spec)
                    except (ValueError, TypeError, KeyError, OverflowError, FloatingPointError):
                        pass
                    else:
                        data['reason'] = 'insufficient_history'
                        if batch.sufficient[0]:
                            data['reason'] = 'model_unavailable'
                            try:
                                with threadpool_limits(limits=1):
                                    health = np.asarray(bundle.health.predict(batch.values))
                                    rul = np.asarray(bundle.rul.predict(batch.values))
                                if (health.shape != (1,) or rul.shape != (1,) or
                                        not np.isfinite(health).all() or not np.isfinite(rul).all()):
                                    raise ValueError('Nonfinite or invalid prediction shape')
                                data.update(status='available', reason=None,
                                    health_score=float(np.clip(health[0], 0, 100)),
                                    rul_hours=float(max(rul[0], 0)))
                            except (ValueError, TypeError, RuntimeError, AttributeError,
                                    IndexError, OverflowError, FloatingPointError):
                                pass
            now = self.clock()
            if now - received > timedelta(seconds=30):
                data.update(status='unavailable', reason='stale_input', health_score=None, rul_hours=None)
        timestamp = now.isoformat().replace('+00:00', 'Z')
        return {'schema_version': 3, 'event_id': str(uuid5(UUID(source['event_id']), 'prediction-v1')),
            'type': 'prediction', 'occurred_at': timestamp, 'received_at': timestamp,
            **{key: source[key] for key in ('device_id', 'device_record_id', 'environment_id', 'correlation_id')},
            'data': data}

    def process(self, source: dict) -> dict:
        if (any(source[key] != self.catalog[key] for key in
                ('device_id', 'device_record_id', 'environment_id')) or
                source['data']['equipment']['equipment_id'] != self.catalog['equipment_id']):
            raise PermanentError('UNAUTHORIZED_SCOPE')
        bundle = self.models.sync_active(self.owner)
        active = self.models.active(self.owner)
        with connect(self.settings) as connection:
            connection.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',
                (f'coldsafe.inference:{self.owner}:{source["device_record_id"]}',)).fetchone()
            self._authorize(connection)
            existing = connection.execute('SELECT source,prediction FROM inference_events '
                'WHERE source_event_id=%s AND owner_user_id=%s AND device_record_id=%s',
                (source['event_id'], self.owner, source['device_record_id'])).fetchone()
            if existing:
                if existing[0] != source:
                    raise PermanentError('IDENTITY_MISMATCH')
                return existing[1]
            history = self._history(connection, source, bundle) if bundle and active else []
            prediction = self._prediction(source, bundle, active, history)
            inserted = connection.execute('INSERT INTO inference_events(source_event_id,owner_user_id,device_record_id,'
                'environment_id,equipment_id,received_at,source,prediction_event_id,prediction) '
                'VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(source_event_id) DO NOTHING',
                (source['event_id'], self.owner, source['device_record_id'], source['environment_id'],
                 source['data']['equipment']['equipment_id'], source['received_at'],
                 Jsonb(source), prediction['event_id'], Jsonb(prediction)))
            if inserted.rowcount != 1:
                raise PermanentError('IDENTITY_MISMATCH')
        return prediction

    def pending_outputs(self) -> list[dict]:
        with connect(self.settings) as connection:
            self._authorize(connection)
            return [row[0] for row in connection.execute('SELECT prediction FROM inference_events '
                'WHERE owner_user_id=%s AND device_record_id=%s AND equipment_id=%s '
                'AND published_at IS NULL ORDER BY received_at,source_event_id LIMIT 100',
                (self.owner, self.catalog['device_record_id'], self.catalog['equipment_id']))]

    def mark_published(self, event_id: str) -> None:
        with connect(self.settings) as connection:
            self._authorize(connection)
            connection.execute('UPDATE inference_events SET published_at=COALESCE(published_at,now()) '
                'WHERE prediction_event_id=%s AND owner_user_id=%s AND device_record_id=%s AND equipment_id=%s',
                (event_id, self.owner, self.catalog['device_record_id'], self.catalog['equipment_id']))
