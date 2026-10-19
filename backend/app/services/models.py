"""Private model promotion; durable requests precede loading and atomic swaps."""
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from backend.app.api.auth import AuthError
from backend.app.repositories.aiot import AiotRepository
from backend.app.repositories.postgres import connect
from backend.app.services.jobs import public_job
from backend.app.services.model_bundle import LoadedBundle, ModelBundleUnavailable, load_model_bundle
from backend.app.services.training_results import read_training_result


class ModelActivationBusy(RuntimeError):
    """The owner is loading another bundle; retain the source for retry."""


class ModelService:
    def __init__(self, settings, *, artifact_root: Path):
        self.settings, self.artifact_root = settings, artifact_root
        self.repository = AiotRepository(settings)
        self.loaded = {}

    @staticmethod
    def _lock(connection, owner: UUID, *, session: bool) -> bool:
        function = 'pg_try_advisory_lock' if session else 'pg_try_advisory_xact_lock'
        return connection.execute(f"SELECT {function}(hashtextextended(%s,0))",
                                  (f'coldsafe.models:{owner}',)).fetchone()[0]

    @staticmethod
    def _previous(connection, owner: UUID) -> UUID | None:
        row = connection.execute('SELECT model_id FROM active_models WHERE owner_user_id=%s', (owner,)).fetchone()
        return row[0] if row else None

    @staticmethod
    def _context(connection, owner: UUID, model_id: UUID) -> tuple[dict, dict, dict]:
        with connection.cursor(row_factory=dict_row) as cursor:
            model = cursor.execute('SELECT * FROM models WHERE id=%s AND owner_user_id=%s FOR SHARE',
                                   (model_id, owner)).fetchone()
            if model is None:
                raise HTTPException(404, 'MODEL_NOT_FOUND')
            job = cursor.execute('SELECT * FROM jobs WHERE id=%s AND owner_user_id=%s FOR SHARE',
                                 (model['training_job_id'], owner)).fetchone()
            dataset = cursor.execute('SELECT * FROM datasets WHERE id=%s AND owner_user_id=%s FOR SHARE',
                                     (model['dataset_id'], owner)).fetchone()
        if (job is None or dataset is None or job['job_type'] != 'training' or
                job['status'] != 'completed' or job['result_model_id'] != model_id or
                job['dataset_id'] != dataset['id']):
            raise HTTPException(404, 'MODEL_NOT_FOUND')
        return model, public_job(job), dataset

    @staticmethod
    def _event(row: dict, model: dict, kind: str) -> dict:
        now = datetime.now(UTC).isoformat().replace('+00:00', 'Z')
        data = {'activation_id': str(row['id']), 'model_id': str(row['model_id']),
                'model_version': model['model_version'], 'features_version': model['features_version']}
        previous = str(row['previous_model_id']) if row['previous_model_id'] else None
        if kind == 'model_activation':
            data['previous_active_model_id'] = previous
        else:
            data.update(status=row['status'], error_code=row['error_code'],
                        active_model_id=str(row['model_id']) if row['status'] == 'active' else previous)
        return {'schema_version': 3, 'event_id': str(uuid4()), 'type': kind,
                'occurred_at': now, 'received_at': now, 'device_id': None,
                'device_record_id': None, 'environment_id': None,
                'correlation_id': str(row['id']), 'data': data}

    def _enqueue(self, connection, row: dict, model: dict, kind: str) -> None:
        event = self._event(row, model, kind)
        connection.execute('INSERT INTO model_outbox(event_id,activation_id,publisher_role,event) VALUES(%s,%s,%s,%s)',
                           (event['event_id'], row['id'], 'api' if kind == 'model_activation' else 'inference', Jsonb(event)))

    def request(self, owner: UUID, model_id: UUID) -> dict:
        with connect(self.settings) as connection:
            if not self._lock(connection, owner, session=False):
                raise HTTPException(409, 'ACTIVATION_PENDING')
            role = connection.execute('SELECT role FROM users WHERE id=%s FOR SHARE', (owner,)).fetchone()
            if role is None or role[0] != 'admin':
                raise AuthError('FORBIDDEN', 'Seu papel não permite esta operação.', 403)
            model, job, dataset = self._context(connection, owner, model_id)
            if model['metrics'].get('eligible') is not True:
                raise HTTPException(409, 'MODEL_NOT_ELIGIBLE')
            result = read_training_result(self.artifact_root, model, job, dataset)
            if not result['eligible']:
                raise HTTPException(409, 'MODEL_NOT_ELIGIBLE')
            if connection.execute("SELECT 1 FROM model_activations WHERE owner_user_id=%s "
                                  "AND status IN ('ready','loading')", (owner,)).fetchone():
                raise HTTPException(409, 'ACTIVATION_PENDING')
            with connection.cursor(row_factory=dict_row) as cursor:
                row = cursor.execute('INSERT INTO model_activations(owner_user_id,model_id,previous_model_id) '
                                     'VALUES(%s,%s,%s) RETURNING *',
                                     (owner, model_id, self._previous(connection, owner))).fetchone()
            self._enqueue(connection, row, model, 'model_activation')
        return self.get(owner, row['id'])

    def get(self, owner: UUID, activation_id: UUID) -> dict | None:
        with connect(self.settings) as connection, connection.cursor(row_factory=dict_row) as cursor:
            return cursor.execute('SELECT a.id,a.model_id,a.previous_model_id,a.status,a.error_code,'
                'a.created_at,a.updated_at,m.model_version,m.features_version FROM model_activations a '
                'JOIN models m ON (m.id,m.owner_user_id)=(a.model_id,a.owner_user_id) '
                'WHERE a.id=%s AND a.owner_user_id=%s', (activation_id, owner)).fetchone()

    def active(self, owner: UUID) -> dict | None:
        with connect(self.settings) as connection, connection.cursor(row_factory=dict_row) as cursor:
            return cursor.execute('SELECT a.model_id,a.activated_at,m.model_version,m.features_version '
                'FROM active_models a JOIN models m ON (m.id,m.owner_user_id)=(a.model_id,a.owner_user_id) '
                'WHERE a.owner_user_id=%s', (owner,)).fetchone()

    def sync_active(self, owner: UUID) -> LoadedBundle | None:
        """Restore after startup and reload only when the authorized pointer changes."""
        with connect(self.settings) as connection:
            connection.autocommit = True
            if not self._lock(connection, owner, session=True):
                raise ModelActivationBusy('Model activation is in progress')
            with connection.transaction():
                model_id = self._previous(connection, owner)
                if model_id is None:
                    return None
                previous = self.loaded.get(owner)
                if previous is not None and previous.model_id == model_id:
                    return previous
                try:
                    model, job, dataset = self._context(connection, owner, model_id)
                    bundle = load_model_bundle(self.artifact_root, model, job, dataset)
                except (ModelBundleUnavailable, HTTPException):
                    return None
                self.loaded[owner] = bundle
                return bundle

    def list_models(self, owner: UUID) -> list[dict]:
        with connect(self.settings) as connection, connection.cursor(row_factory=dict_row) as cursor:
            return cursor.execute('SELECT m.id,m.model_version,m.features_version,m.training_job_id,m.dataset_id,'
                'm.metrics,m.created_at FROM models m JOIN jobs j ON '
                '(j.id,j.owner_user_id,j.result_model_id)=(m.training_job_id,m.owner_user_id,m.id) '
                "WHERE m.owner_user_id=%s AND j.status='completed' AND j.job_type='training' "
                'ORDER BY m.created_at DESC,m.id DESC LIMIT 50', (owner,)).fetchall()

    def get_requested(self, activation_id: UUID) -> dict | None:
        with connect(self.settings) as connection:
            row = connection.execute("SELECT event FROM model_outbox WHERE activation_id=%s AND publisher_role='api'",
                                     (activation_id,)).fetchone()
            return row[0] if row else None

    def pending_outputs(self, role: str) -> list[dict]:
        with connect(self.settings) as connection:
            return [row[0] for row in connection.execute('SELECT event FROM model_outbox WHERE publisher_role=%s '
                'AND published_at IS NULL ORDER BY sequence LIMIT 100', (role,))]

    def mark_published(self, event_id: str) -> None:
        with connect(self.settings) as connection:
            connection.execute('UPDATE model_outbox SET published_at=COALESCE(published_at,now()) WHERE event_id=%s', (event_id,))

    def _transition(self, connection, activation_id: UUID, model: dict, status: str) -> dict:
        with connection.cursor(row_factory=dict_row) as cursor:
            row = cursor.execute('UPDATE model_activations SET status=%s,error_code=%s,'
                'updated_at=clock_timestamp() WHERE id=%s RETURNING *',
                (status, 'MODEL_LOAD_FAILED' if status == 'failed' else None, activation_id)).fetchone()
        self._enqueue(connection, row, model, 'model_status')
        return row

    def execute(self, activation_id: UUID) -> bool:
        with connect(self.settings) as connection:
            connection.autocommit = True
            with connection.cursor(row_factory=dict_row) as cursor:
                row = cursor.execute('SELECT * FROM model_activations WHERE id=%s', (activation_id,)).fetchone()
            if row is None:
                return True
            owner = row['owner_user_id']
            # Session lock survives the visible loading checkpoint and dies with this connection.
            if not self._lock(connection, owner, session=True):
                return False
            with connection.cursor(row_factory=dict_row) as cursor:
                row = cursor.execute('SELECT * FROM model_activations WHERE id=%s', (activation_id,)).fetchone()
            if row['status'] in ('active', 'failed'):
                return True
            requested = self.get_requested(activation_id)
            model = self.repository.get_model(owner, row['model_id'])
            if requested is None or model is None:
                raise ValueError('Activation lacks registered request or model')
            if row['status'] == 'ready':
                with connection.transaction():
                    self._transition(connection, activation_id, requested['data'], 'loading')
            try:
                with connection.transaction():
                    model, job, dataset = self._context(connection, owner, row['model_id'])
                    if (self._previous(connection, owner) != row['previous_model_id'] or
                            requested['data']['model_version'] != model['model_version'] or
                            requested['data']['features_version'] != model['features_version']):
                        raise ModelBundleUnavailable('Model bundle unavailable')
                    bundle = load_model_bundle(self.artifact_root, model, job, dataset)
                    connection.execute('INSERT INTO active_models(owner_user_id,model_id) VALUES(%s,%s) '
                        'ON CONFLICT(owner_user_id) DO UPDATE SET model_id=EXCLUDED.model_id,activated_at=clock_timestamp()',
                        (owner, model['id']))
                    self._transition(connection, activation_id, requested['data'], 'active')
            except (ModelBundleUnavailable, HTTPException):
                with connection.transaction():
                    self._transition(connection, activation_id, requested['data'], 'failed')
            else:
                self.loaded[owner] = bundle
            return True
