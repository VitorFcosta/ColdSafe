"""Offline, bounded-memory synthetic data. No live transport or InfluxDB writes."""
from collections.abc import Callable
import hashlib
import json
import os
from pathlib import Path
from uuid import UUID, uuid4, uuid5

import numpy as np

from backend.app.domain.jobs import GenerationInput, SENSOR_TYPES
from backend.app.repositories.postgres import connect

BLOCK_SIZE = 50_000
MEASUREMENTS = dict(zip(SENSOR_TYPES, ('degC', 'percent', 'percent', 'mm/s', 'A', 'degC'), strict=True))
STORAGE_VERSION = 'offline-numpy-v1'
DTYPE = np.dtype([('equipment_index', '<i4'), ('observed_at', '<M8[ms]'),
                  *[(name, '<f8') for name in MEASUREMENTS],
                  ('degradation_true', '<f8'), ('health_score_true', '<f8'),
                  ('rul_hours_true', '<f8'), ('rul_observed', '?')])


def equipment_parameters(config: GenerationInput) -> dict:
    rng = np.random.default_rng(np.random.SeedSequence([config.seed, 0]))
    n = config.equipment_count
    return {
        'observed': rng.random(n) < config.failure_fraction,
        'life_fraction': rng.uniform(0.5, 1, n),
        'censored_wear': rng.uniform(0.15, 0.8, n),
        'mode': rng.choice(config.operating_modes, n),
        'fault': rng.choice(config.failure_modes, n),
        'baseline': rng.normal(0, 1, (n, 6)),
        'phase': rng.uniform(0, 2 * np.pi, n),
        'exponent': rng.uniform(1.1, 2.2, n),
    }


def generate_block(config: GenerationInput, block_index: int) -> np.ndarray:
    start = block_index * BLOCK_SIZE
    if block_index < 0 or start >= config.total_units:
        raise ValueError('Block outside dataset')
    index = np.arange(start, min(start + BLOCK_SIZE, config.total_units))
    n = config.equipment_count
    equipment = index % n
    counts = (config.total_units - 1 - equipment) // n + 1
    fraction = (index // n) / (counts - 1)
    params = equipment_parameters(config)
    observed = params['observed'][equipment]
    duration = config.days * 24 * np.where(observed, params['life_fraction'][equipment], 1)
    hours = fraction * duration
    degradation = fraction ** params['exponent'][equipment] * np.where(observed, 1, params['censored_wear'][equipment])
    bearing = np.where(params['fault'][equipment] == 'bearing_wear', degradation, degradation * 0.2)
    imbalance = np.where(params['fault'][equipment] == 'imbalance', degradation, degradation * 0.2)
    loss = 0.6 * bearing + 0.4 * imbalance
    phase = 2 * np.pi * hours / 24 + params['phase'][equipment]
    load = np.where(params['mode'][equipment] == 'heavy', 1.25,
                    np.where(params['mode'][equipment] == 'cycling', 0.8 + 0.3 * np.sin(phase), 1))
    # Same physical directions as the edge simulator; heterogeneity prevents perfect targets.
    values = np.column_stack((
        5 + 14 * loss + 1.5 * np.sin(phase), 60 + 5 * np.sin(phase),
        25 + 10 * np.sin(phase), 0.6 + 7 * bearing + 10 * imbalance,
        (1.2 + 2.5 * bearing + 1.5 * imbalance) * load,
        32 + 38 * bearing + 22 * imbalance + 8 * (load - 1),
    ))
    rng = np.random.default_rng(np.random.SeedSequence([config.seed, 1, block_index]))
    values += params['baseline'][equipment] * np.array([0.7, 3, 5, 0.25, 0.15, 2])
    scales = np.array([0.3, 1, 2, 0.15, 0.08, 0.6])
    values += rng.normal(0, scales * config.noise_scale, values.shape)
    outliers = rng.random(values.shape) < config.outlier_rate
    values += outliers * rng.normal(0, scales * 100, values.shape)
    values[rng.random(values.shape) < config.missing_rate] = np.nan
    result = np.empty(len(index), dtype=DTYPE)
    result['equipment_index'] = equipment
    result['observed_at'] = np.datetime64('2026-01-01', 'ms') + np.rint(hours * 3_600_000).astype('timedelta64[ms]')
    for column, name in enumerate(MEASUREMENTS):
        result[name] = values[:, column] if name in config.sensor_types else np.nan
    result['degradation_true'] = degradation
    result['health_score_true'] = 100 * (1 - degradation)
    result['rul_hours_true'] = np.where(observed, np.maximum(0, duration - hours), np.nan)
    result['rul_observed'] = observed
    return result


def write_dataset(directory: Path, dataset_id: UUID, config: GenerationInput,
                  checkpoint: Callable[[int], None], *, completed_units: int = 0) -> Path:
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    _sync_directory(directory.parent)
    blocks = []
    for block_index in range((config.total_units + BLOCK_SIZE - 1) // BLOCK_SIZE):
        data = generate_block(config, block_index)
        name = f'block-{block_index:04d}.npy'
        path = directory / name
        temporary = directory / (name + '.tmp')
        with temporary.open('xb') as stream:
            np.save(stream, data, allow_pickle=False)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        blocks.append({'file': name, 'row_count': len(data), 'sha256': digest})
        del data
        _sync_directory(directory)
        completed = min((block_index + 1) * BLOCK_SIZE, config.total_units)
        checkpoint(max(completed, completed_units))
    params = equipment_parameters(config)
    manifest = {
        'storage_version': STORAGE_VERSION, 'schema_version': 3, 'dataset_id': str(dataset_id),
        'row_count': sum(block['row_count'] for block in blocks),
        'config': config.model_dump(mode='json'), 'numpy_version': np.__version__,
        'block_size': BLOCK_SIZE, 'units': MEASUREMENTS, 'missing_value': 'NaN maps to JSON null',
        'equipment': [{'id': str(uuid5(dataset_id, str(i))),
                       'operating_mode': str(params['mode'][i]), 'failure_mode': str(params['fault'][i])}
                      for i in range(config.equipment_count)],
        'blocks': blocks,
    }
    temporary = directory / 'manifest.json.tmp'
    with temporary.open('x') as stream:
        json.dump(manifest, stream, allow_nan=False, sort_keys=True, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    path = directory / 'manifest.json'
    temporary.replace(path)
    _sync_directory(directory)
    return path


def _sync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class GenerationHandler:
    def __init__(self, settings, *, artifact_root: Path):
        self.settings, self.artifact_root = settings, artifact_root

    def __call__(self, job: dict, checkpoint: Callable[[int], None]) -> UUID:
        config = GenerationInput.model_validate(job['config'] | {
            'job_type': 'generation', 'total_units': job['total_units'],
            'environment_id': job['environment_id'],
        })
        identifier = uuid5(UUID(str(job['id'])), STORAGE_VERSION)
        # Replay deterministically in an exclusive attempt directory; never share writable blocks.
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        directory = self.artifact_root / f'{identifier}-{uuid4()}'
        manifest = write_dataset(directory, identifier, config, checkpoint,
                                 completed_units=job['completed_units'])
        with connect(self.settings) as connection:
            connection.execute('INSERT INTO datasets(id,owner_user_id,generation_job_id,name,features_version,row_count,artifact_key) '
                'VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET artifact_key=EXCLUDED.artifact_key',
                (identifier, job['owner_user_id'], job['id'], f"Synthetic {job['id']}", STORAGE_VERSION,
                 config.total_units, str(manifest.relative_to(self.artifact_root))))
        return identifier
