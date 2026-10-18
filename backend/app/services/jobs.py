"""Durable job orchestration; calculation handlers belong to generation/training."""
from collections.abc import Callable
from datetime import UTC, datetime
import logging
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from backend.app.api.auth import AuthError
from backend.app.config.settings import RuntimeSettings
from backend.app.repositories.aiot import AiotRepository
from backend.app.repositories.postgres import connect

LOGGER = logging.getLogger(__name__)
HEAVY_JOB_LOCK = 2026101701
TERMINAL = frozenset(('completed', 'failed', 'cancelled'))
JobHandler = Callable[[dict, Callable[[int], None]], UUID]


def public_job(row: dict) -> dict:
    from backend.app.domain.jobs import GenerationInput
    config = row['config'] | {'job_type': row['job_type'], 'environment_id': row['environment_id']}
    if row['job_type'] == 'generation':
        config['total_units'] = row['total_units']
        config = GenerationInput.model_construct(**config).model_dump(mode='json')
    else:
        config['dataset_id'] = str(row['dataset_id'])
    return {key: row[key] for key in (
        'id', 'owner_user_id', 'environment_id', 'dataset_id', 'job_type', 'status', 'completed_units',
        'total_units', 'error_code', 'created_at', 'updated_at',
    )} | {'result_id': row['result_dataset_id'] or row['result_model_id'], 'config': config}


class JobService:
    def __init__(self, settings: RuntimeSettings, *, artifact_root: Path = Path('/app/artifacts'),
                 training_artifact_root: Path | None = None):
        self.settings, self.artifact_root = settings, artifact_root
        self.training_artifact_root = training_artifact_root if training_artifact_root is not None else artifact_root
        self.repository = AiotRepository(settings)

    def get(self, owner: UUID, job_id: UUID) -> dict | None:
        row = self.repository.get_job(owner, job_id)
        return public_job(row) if row else None

    @staticmethod
    def _event(row: dict, kind: str) -> dict:
        now = datetime.now(UTC).isoformat().replace('+00:00', 'Z')
        data = {'job_id': str(row['id']), 'job_type': row['job_type']}
        if kind == 'job_requested':
            data['dataset_id'] = str(row['dataset_id']) if row['dataset_id'] else None
        else:
            data.update({key: row[key] for key in ('status', 'completed_units', 'total_units', 'error_code')})
            result = row['result_dataset_id'] or row['result_model_id']
            data['result_id'] = str(result) if result else None
        return {'schema_version': 3, 'event_id': str(uuid4()), 'type': kind,
                'occurred_at': now, 'received_at': now, 'device_id': None,
                'device_record_id': None,
                'environment_id': str(row['environment_id']) if row['environment_id'] else None,
                'correlation_id': str(row['id']), 'data': data}

    def _enqueue(self, connection, row: dict, kind: str) -> None:
        event = self._event(row, kind)
        connection.execute('INSERT INTO job_outbox(event_id,job_id,publisher_role,event) VALUES(%s,%s,%s,%s)',
                           (event['event_id'], row['id'], 'api' if kind == 'job_requested' else row['job_type'], Jsonb(event)))

    def create(self, owner: UUID, payload: dict) -> dict:
        from backend.app.domain.jobs import JOB_REQUEST
        request = JOB_REQUEST.validate_python(payload)
        config = request.model_dump(mode='json')
        environment_id = config.pop('environment_id', None)
        kind = config.pop('job_type')
        dataset_id = config.pop('dataset_id', None)
        total = config.pop('total_units', 2)
        with connect(self.settings) as connection, connection.cursor(row_factory=dict_row) as cursor:
            role = cursor.execute('SELECT role FROM users WHERE id=%s FOR SHARE', (owner,)).fetchone()
            if role is None or role['role'] != 'admin':
                raise AuthError('FORBIDDEN', 'Seu papel não permite esta operação.', 403)
            if environment_id and not cursor.execute('SELECT 1 FROM environments WHERE id=%s AND owner_user_id=%s',
                                                      (environment_id, owner)).fetchone():
                raise HTTPException(404, 'ENVIRONMENT_NOT_FOUND')
            if dataset_id:
                dataset = cursor.execute('SELECT * FROM datasets WHERE id=%s AND owner_user_id=%s',
                                         (dataset_id, owner)).fetchone()
                if dataset is None:
                    raise HTTPException(404, 'DATASET_NOT_FOUND')
                if not dataset['artifact_key'] or not 1 <= dataset['row_count'] <= 2_000_000:
                    raise HTTPException(422, 'VALIDATION_ERROR')
            row = cursor.execute('INSERT INTO jobs(owner_user_id,environment_id,job_type,dataset_id,config,total_units) '
                                 'VALUES(%s,%s,%s,%s,%s,%s) RETURNING *',
                                 (owner, environment_id, kind, dataset_id, Jsonb(config), total)).fetchone()
            self._enqueue(connection, row, 'job_requested')
            self._enqueue(connection, row, 'job_progress')
        return public_job(row)

    def get_requested(self, job_id: UUID) -> dict | None:
        with connect(self.settings) as connection:
            row = connection.execute("SELECT event FROM job_outbox WHERE job_id=%s AND publisher_role='api'", (job_id,)).fetchone()
            return row[0] if row else None

    def pending_outputs(self, role: str) -> list[dict]:
        with connect(self.settings) as connection:
            return [row[0] for row in connection.execute(
                'SELECT event FROM job_outbox WHERE publisher_role=%s AND published_at IS NULL ORDER BY sequence LIMIT 100', (role,))]

    def mark_published(self, event_id: str) -> None:
        with connect(self.settings) as connection:
            connection.execute('UPDATE job_outbox SET published_at=COALESCE(published_at,now()) WHERE event_id=%s', (event_id,))

    def _transition(self, connection, job_id: UUID, *, status: str, completed: int,
                    result: UUID | None = None, error: str | None = None) -> dict:
        with connection.transaction(), connection.cursor(row_factory=dict_row) as cursor:
            row = cursor.execute('SELECT * FROM jobs WHERE id=%s FOR UPDATE', (job_id,)).fetchone()
            if row['status'] in TERMINAL:
                return row
            if type(completed) is not int or not row['completed_units'] <= completed <= row['total_units']:
                raise ValueError('Checkpoint must be monotonic and within total')
            row = cursor.execute('UPDATE jobs SET status=%s,completed_units=%s,result_dataset_id=%s,result_model_id=%s,'
                                 'error_code=%s,updated_at=clock_timestamp() WHERE id=%s RETURNING *',
                                 (status, completed, result if row['job_type'] == 'generation' else None,
                                  result if row['job_type'] == 'training' else None, error, job_id)).fetchone()
            self._enqueue(connection, row, 'job_progress')
            return row

    def _verify_artifact(self, connection, job: dict, result: UUID) -> None:
        with connection.cursor(row_factory=dict_row) as cursor:
            if job['job_type'] == 'generation':
                row = cursor.execute('SELECT artifact_key,row_count FROM datasets WHERE id=%s AND owner_user_id=%s '
                                     'AND generation_job_id=%s', (result, job['owner_user_id'], job['id'])).fetchone()
                if row is None or row['row_count'] != job['total_units']:
                    raise ValueError('Generation result must match the job and row count')
            else:
                row = cursor.execute('SELECT artifact_key FROM models WHERE id=%s AND owner_user_id=%s AND training_job_id=%s '
                                     'AND dataset_id=%s', (result, job['owner_user_id'], job['id'], job['dataset_id'])).fetchone()
            if row is None or not row['artifact_key']:
                raise ValueError('Result must have a persisted artifact')
            root = (self.artifact_root if job['job_type'] == 'generation' else
                    self.training_artifact_root).resolve(strict=True)
            path = root / row['artifact_key']
            if (not path.resolve(strict=True).is_relative_to(root) or
                    any(parent.is_symlink() for parent in (path, *path.parents) if parent != root) or
                    not path.is_file() or path.stat().st_size == 0):
                raise ValueError('Result artifact must be an internal nonempty regular file')

    def execute(self, job_id: UUID, job_type: str, handler: JobHandler | None) -> bool:
        # A session lock survives checkpoint commits and disappears when this connection closes.
        with connect(self.settings) as connection:
            connection.autocommit = True
            if not connection.execute('SELECT pg_try_advisory_lock(%s)', (HEAVY_JOB_LOCK,)).fetchone()[0]:
                return False
            with connection.cursor(row_factory=dict_row) as cursor:
                job = cursor.execute('SELECT * FROM jobs WHERE id=%s', (job_id,)).fetchone()
            if job is None or job['job_type'] != job_type:
                raise ValueError('Unknown job or worker type mismatch')
            if job['status'] in TERMINAL:
                return True
            job = self._transition(connection, job_id, status='running', completed=job['completed_units'])
            def checkpoint(completed: int) -> None:
                # The executor calls only after its durable block; this query also checks lock connection health.
                self._transition(connection, job_id, status='running', completed=completed)
            try:
                if handler is None:
                    raise NotImplementedError('Executor belongs to the next generation/training tasks')
                result = handler(job, checkpoint)
                self._verify_artifact(connection, job, result)
                self._transition(connection, job_id, status='completed', completed=job['total_units'], result=result)
            except Exception as error:
                LOGGER.warning('Job execution failed: type=%s job_type=%s', type(error).__name__, job_type)
                with connection.cursor(row_factory=dict_row) as cursor:
                    current = cursor.execute('SELECT * FROM jobs WHERE id=%s', (job_id,)).fetchone()
                self._transition(connection, job_id, status='failed', completed=current['completed_units'],
                                 error=f'{job_type.upper()}_FAILED')
            return True
