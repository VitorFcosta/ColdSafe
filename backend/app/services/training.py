"""Sequential isolated training, durable package registration, no activation."""
from collections.abc import Callable
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
from uuid import UUID, uuid4, uuid5

from fastapi.encoders import jsonable_encoder
from psycopg.types.json import Jsonb

from backend.app.repositories.aiot import AiotRepository
from backend.app.repositories.postgres import connect
from backend.app.services.generation import _sync_directory
from backend.app.services.jobs import public_job


LOGGER = logging.getLogger(__name__)


def run_child(arguments: list[str], checkpoint: Callable[[int], None], completed: int) -> None:
    environment = os.environ | {key: '1' for key in
        ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS')}
    child = subprocess.Popen([sys.executable, '-m', 'backend.app.services.training_runner', *arguments],
        env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        while True:
            try:
                code = child.wait(timeout=2)
                break
            except subprocess.TimeoutExpired:
                checkpoint(completed)
        if code:
            phase = arguments[0] if arguments[0] in ('prepare', 'health', 'rul') else 'unknown'
            LOGGER.warning('Training subprocess failed: phase=%s exit_code=%s', phase, code)
            raise ValueError('Training subprocess failed')
        checkpoint(completed)
    except BaseException:
        child.terminate()
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()
        raise


class TrainingHandler:
    def __init__(self, settings, *, artifact_root: Path, training_artifact_root: Path):
        self.settings = settings
        self.artifact_root = artifact_root
        self.training_artifact_root = training_artifact_root
        self.repository = AiotRepository(settings)

    def __call__(self, job: dict, checkpoint: Callable[[int], None]) -> UUID:
        from backend.app.services.training_results import build_package, read_training_result
        owner = job['owner_user_id']
        dataset = self.repository.get_dataset(owner, job['dataset_id'])
        if dataset is None or dataset['owner_user_id'] != owner:
            raise ValueError('Training dataset not found')
        generation = self.repository.get_job(owner, dataset['generation_job_id'])
        if generation is None:
            raise ValueError('Training generation not found')
        self.training_artifact_root.mkdir(parents=True, exist_ok=True)
        identifier = uuid5(UUID(str(job['id'])), 'training-package-v1')
        directory = self.training_artifact_root / f'{identifier}-{uuid4()}'
        directory.mkdir(mode=0o700)
        context = directory / 'context.json'
        context.write_text(json.dumps(jsonable_encoder({'dataset': dataset, 'job': public_job(generation)})))
        completed = job['completed_units']
        checkpoint(completed)
        run_child(['prepare', str(self.artifact_root.resolve()), str(directory / 'prepared'), str(context)], checkpoint, completed)
        context.unlink()
        for target, units in (('health', 1), ('rul', 2)):
            run_child([target, str(directory / 'prepared'), str(directory / target)], checkpoint, completed)
            completed = max(completed, units)
            checkpoint(completed)
        package = build_package(directory, job, dataset, identifier)
        temporary = directory / 'manifest.json.tmp'
        with temporary.open('x') as stream:
            json.dump(package, stream, allow_nan=False, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(directory / 'manifest.json')
        _sync_directory(directory)
        model = {'id': identifier, 'owner_user_id': owner, 'dataset_id': dataset['id'],
            'training_job_id': job['id'], 'model_version': package['model_version'],
            'features_version': package['features_version'],
            'artifact_key': str((directory / 'manifest.json').relative_to(self.training_artifact_root))}
        result = read_training_result(self.training_artifact_root, model, public_job(job), dataset)
        metrics = {'eligible': result['eligible'], **{target: {
            'status': result[target]['status'], 'metrics': result[target]['metrics']}
            for target in ('health', 'rul')}}
        with connect(self.settings) as connection:
            connection.execute('INSERT INTO models(id,owner_user_id,dataset_id,training_job_id,model_version,'
                'features_version,artifact_key,metrics) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) '
                'ON CONFLICT(id) DO UPDATE SET artifact_key=EXCLUDED.artifact_key,metrics=EXCLUDED.metrics',
                (identifier, owner, dataset['id'], job['id'], model['model_version'],
                 model['features_version'], model['artifact_key'], Jsonb(metrics)))
        return identifier
