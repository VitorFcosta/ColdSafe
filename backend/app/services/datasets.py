"""Private offline dataset inspection, bounded to one persisted NumPy block."""
import hashlib
import json
import math
from pathlib import Path
from uuid import UUID, uuid5

import numpy as np

from backend.app.domain.jobs import GenerationInput
from backend.app.services.generation import BLOCK_SIZE, DTYPE, MEASUREMENTS, STORAGE_VERSION


class DatasetUnavailable(Exception):
    """A registered offline artifact is missing, unsafe or inconsistent."""


def _internal_file(root: Path, key: str) -> Path:
    relative = Path(key)
    if relative.is_absolute() or not relative.parts or any(part in ('.', '..') for part in relative.parts):
        raise ValueError('Invalid artifact key')
    path = root / relative
    if any(part.is_symlink() for part in (path, *path.parents) if part != root):
        raise ValueError('Artifact symlink')
    if not path.resolve(strict=True).is_relative_to(root) or not path.is_file():
        raise ValueError('Invalid artifact file')
    return path


def read_dataset(artifact_root: Path, dataset: dict, job: dict) -> tuple[dict, dict]:
    try:
        return _read_dataset(artifact_root, dataset, job)
    except (OSError, ValueError, TypeError, KeyError, IndexError, OverflowError, EOFError, RecursionError) as error:
        raise DatasetUnavailable('Offline dataset unavailable') from error


def _read_dataset(artifact_root: Path, dataset: dict, job: dict) -> tuple[dict, dict]:
    root = artifact_root.resolve(strict=True)
    path = _internal_file(root, dataset['artifact_key'])
    if not 0 < path.stat().st_size <= 4 * 1_048_576:
        raise ValueError('Manifest size')
    manifest = json.loads(path.read_bytes())
    config = GenerationInput.model_validate(manifest['config'])
    expected = GenerationInput.model_validate(job['config'] | {
        'job_type': 'generation', 'total_units': job['total_units'],
        'environment_id': job['environment_id'],
    })
    total = config.total_units
    if (config != expected or manifest['schema_version'] != 3 or
            manifest['storage_version'] != STORAGE_VERSION or
            manifest['dataset_id'] != str(dataset['id']) or
            manifest['row_count'] != total or dataset['row_count'] != total or
            manifest['block_size'] != BLOCK_SIZE or manifest['units'] != MEASUREMENTS):
        raise ValueError('Manifest mismatch')
    equipment = manifest['equipment']
    if (len(equipment) != config.equipment_count or
            any(row['id'] != str(uuid5(UUID(str(dataset['id'])), str(i)))
                for i, row in enumerate(equipment))):
        raise ValueError('Equipment mismatch')
    blocks = manifest['blocks']
    if len(blocks) != math.ceil(total / BLOCK_SIZE):
        raise ValueError('Block count')
    missing = dict.fromkeys(config.sensor_types, 0)
    ranges = {name: {'min': None, 'max': None} for name in config.sensor_types}
    observed_rows, rows = 0, []
    for index, block in enumerate(blocks):
        count = min(BLOCK_SIZE, total - index * BLOCK_SIZE)
        if (block['file'] != f'block-{index:04d}.npy' or block['row_count'] != count or
                not isinstance(block['sha256'], str) or len(block['sha256']) != 64):
            raise ValueError('Block metadata')
        key = str(path.parent.relative_to(root) / block['file'])
        block_path = _internal_file(root, key)
        if not count * DTYPE.itemsize < block_path.stat().st_size <= count * DTYPE.itemsize + 10_000:
            raise ValueError('Block size')
        with block_path.open('rb') as stream:
            if stream.read(6) != b'\x93NUMPY':
                raise ValueError('Block must use NPY storage')
            stream.seek(0)
            if hashlib.file_digest(stream, 'sha256').hexdigest() != block['sha256']:
                raise ValueError('Block checksum')
        data = np.load(block_path, mmap_mode='r', allow_pickle=False, max_header_size=10_000)
        if not isinstance(data, np.ndarray) or data.dtype != DTYPE or data.shape != (count,):
            raise ValueError('Block schema')
        indices = data['equipment_index']
        observed = data['rul_observed']
        rul = data['rul_hours_true']
        if (np.any(indices < 0) or np.any(indices >= len(equipment)) or
                np.any(np.isnat(data['observed_at'])) or
                not np.all(np.isfinite(data['degradation_true'])) or
                np.any((data['degradation_true'] < 0) | (data['degradation_true'] > 1)) or
                not np.all(np.isfinite(data['health_score_true'])) or
                np.any((data['health_score_true'] < 0) | (data['health_score_true'] > 100)) or
                np.any(~np.isfinite(rul[observed])) or np.any(rul[observed] < 0) or
                np.any(~np.isnan(rul[~observed]))):
            raise ValueError('Invalid offline values')
        observed_rows += int(np.count_nonzero(observed))
        for name in config.sensor_types:
            values = data[name]
            if np.any(np.isinf(values)):
                raise ValueError('Invalid measurement')
            present = values[~np.isnan(values)]
            missing[name] += count - len(present)
            if present.size:
                low, high = float(np.min(present)), float(np.max(present))
                ranges[name]['min'] = min(ranges[name]['min'], low) if ranges[name]['min'] is not None else low
                ranges[name]['max'] = max(ranges[name]['max'], high) if ranges[name]['max'] is not None else high
        if not rows:
            for row in data[:10]:
                rows.append({
                    'equipment_id': equipment[int(row['equipment_index'])]['id'],
                    'observed_at': str(row['observed_at']) + 'Z',
                    'measurements': {name: None if np.isnan(row[name]) else float(row[name]) for name in config.sensor_types},
                    'degradation_true': float(row['degradation_true']),
                    'health_score_true': float(row['health_score_true']),
                    'rul_hours_true': float(row['rul_hours_true']) if row['rul_observed'] else None,
                    'rul_observed': bool(row['rul_observed']),
                })
        del data
    summary = {key: dataset[key] for key in ('id', 'owner_user_id', 'generation_job_id', 'created_at', 'row_count')}
    summary.update(config=config.model_dump(mode='json'), storage_version=STORAGE_VERSION,
                   units={name: MEASUREMENTS[name] for name in config.sensor_types},
                   quality={'missing_by_sensor': missing, 'range_by_sensor': ranges,
                            'rul_observed_rows': observed_rows, 'rul_censored_rows': total - observed_rows})
    return summary, {'dataset_id': dataset['id'], 'rows': rows}
