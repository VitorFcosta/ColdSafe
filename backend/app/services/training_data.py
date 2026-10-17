"""Private, disk-backed feature preparation; no model fitting or live writes."""
from collections.abc import Iterable, Sequence
import json
from pathlib import Path
from uuid import UUID

import numpy as np

from backend.app.domain.features import FeatureSpec, extract_features
from backend.app.domain.feature_preprocessing import FeatureTransform, fit_transformer
from backend.app.services.datasets import _internal_file, read_dataset
from backend.app.services.feature_inputs import features_version
from backend.app.services.generation import DTYPE

BATCH_SIZE = 5000
TARGET_DTYPE = np.dtype([('equipment_index', '<i4'), ('observed_at', '<M8[ms]'),
    ('health_score_true', '<f8'), ('rul_hours_true', '<f8'), ('rul_observed', '?')])


def split_equipment(equipment_ids: Sequence[str], seed: int = 42) -> dict[str, tuple[str, ...]]:
    if type(seed) is not int or not 0 <= seed <= 2**32 - 1:
        raise ValueError('Split seed must be an unsigned 32-bit integer')
    if isinstance(equipment_ids, str) or any(not isinstance(item, str) for item in equipment_ids):
        raise ValueError('Equipment IDs must be canonical UUID strings')
    identifiers = sorted(equipment_ids)
    if (len(identifiers) < 3 or len(set(identifiers)) != len(identifiers) or
            any(str(UUID(item)) != item for item in identifiers)):
        raise ValueError('Three or more distinct canonical equipment UUIDs are required')
    shuffled = np.random.default_rng(seed).permutation(identifiers).tolist()
    train_count = min(max(1, int(len(shuffled) * 0.7)), len(shuffled) - 2)
    validation_count = min(max(1, int(len(shuffled) * 0.15)), len(shuffled) - train_count - 1)
    return {'train': tuple(shuffled[:train_count]),
            'validation': tuple(shuffled[train_count:train_count + validation_count]),
            'test': tuple(shuffled[train_count + validation_count:])}


def prepare_dataset(artifact_root: Path, dataset: dict, job: dict, directory: Path,
                    *, seed: int = 42, spec: FeatureSpec | None = None) -> dict:
    if (job['status'] != 'completed' or job['job_type'] != 'generation' or
            job['owner_user_id'] != dataset['owner_user_id'] or
            job['result_id'] != dataset['id'] or job['id'] != dataset['generation_job_id']):
        raise ValueError('Preparation requires the owner-linked completed generation result')
    summary, _ = read_dataset(artifact_root, dataset, job)
    root = artifact_root.resolve(strict=True)
    path = _internal_file(root, dataset['artifact_key'])
    manifest = json.loads(path.read_bytes())
    spec = spec or FeatureSpec(sensors=tuple(summary['config']['sensor_types']))
    if set(spec.sensors) != set(summary['config']['sensor_types']):
        raise ValueError('Feature sensors must match the generated dataset configuration')
    # Completed generation artifacts are immutable; reuse the B2-19 full validation above.
    blocks = (np.load(_internal_file(root, str(path.parent.relative_to(root) / block['file'])),
                      mmap_mode='r', allow_pickle=False) for block in manifest['blocks'])
    return _prepare_blocks(blocks, summary['row_count'],
        tuple(row['id'] for row in manifest['equipment']), directory, spec, seed,
        source={'dataset_id': str(dataset['id']), 'owner_user_id': str(dataset['owner_user_id']),
                'generation_job_id': str(job['id'])})


def _fit_training_chunks(paths: Sequence[Path], row_count: int, names: tuple[str, ...]) -> FeatureTransform:
    fitted = []
    for index, name in enumerate(names):
        column = np.empty((row_count, 1), dtype=np.float64)
        offset = 0
        for path in paths:
            chunk = np.load(path, mmap_mode='r', allow_pickle=False)
            column[offset:offset + len(chunk), 0] = chunk['features'][:, index]
            offset += len(chunk)
            del chunk
        fitted.append(fit_transformer(column, (name,)))
    return FeatureTransform(names, *(np.array([getattr(state, field)[0] for state in fitted])
                                    for field in ('medians', 'lower', 'upper')))


def _prepare_blocks(blocks: Iterable[np.ndarray], row_count: int, equipment_ids: tuple[str, ...],
                    directory: Path, spec: FeatureSpec, seed: int, *, source: dict | None = None) -> dict:
    split = split_equipment(equipment_ids, seed)
    if type(row_count) is not int or not 0 < row_count <= 2_000_000:
        raise ValueError('Invalid source row count')
    directory.mkdir(mode=0o700, exist_ok=False)
    raw_directory = directory / 'raw'
    raw_directory.mkdir(mode=0o700)
    source_path = directory / 'source.npy'
    raw = np.lib.format.open_memmap(source_path, mode='w+', dtype=DTYPE, shape=(row_count,))
    count = 0
    for block in blocks:
        if (not isinstance(block, np.ndarray) or block.ndim != 1 or block.dtype != DTYPE or
                count + len(block) > row_count or np.any(block['equipment_index'] < 0) or
                np.any(block['equipment_index'] >= len(equipment_ids))):
            raise ValueError('Invalid source block')
        raw[count:count + len(block)] = block
        count += len(block)
    if count != row_count:
        raise ValueError('Source count mismatch')
    raw.flush()
    del raw
    raw = np.load(source_path, mmap_mode='r', allow_pickle=False)
    order = np.lexsort((raw['observed_at'].astype(np.int64), raw['equipment_index']))
    indices = raw['equipment_index'][order]
    boundaries = np.r_[0, np.flatnonzero(np.diff(indices)) + 1, row_count]
    chunks = {part: [] for part in split}
    counts = dict.fromkeys(split, 0)
    dropped = 0
    for start, end in zip(boundaries[:-1], boundaries[1:], strict=True):
        equipment_index = int(indices[start])
        identifier = equipment_ids[equipment_index]
        part = next(name for name, identifiers in split.items() if identifier in identifiers)
        rows = raw[order[start:end]]
        times = rows['observed_at'].astype(np.int64)
        values = np.column_stack([rows[name] for name in spec.sensors])
        if int(times[-1]) - int(times[0]) < spec.windows_seconds[-1] * 1000:
            dropped += len(rows)
            continue
        chunk_dtype = np.dtype([('features', '<f8', (len(spec.names),)), *TARGET_DTYPE.descr])
        for offset in range(0, len(rows), BATCH_SIZE):
            query = times[offset:offset + BATCH_SIZE]
            batch = extract_features(times, values, query, spec)
            selected = rows[offset:offset + BATCH_SIZE][batch.sufficient]
            dropped += len(query) - len(selected)
            if not len(selected):
                continue
            chunk = np.empty(len(selected), dtype=chunk_dtype)
            chunk['features'] = batch.values[batch.sufficient]
            for field in TARGET_DTYPE.names:
                chunk[field] = selected[field]
            path = raw_directory / f'{part}-{equipment_index:05d}-{offset:07d}.npy'
            np.save(path, chunk, allow_pickle=False)
            chunks[part].append(path)
            counts[part] += len(chunk)
    del raw, rows, values, indices, order
    source_path.unlink()
    if any(count == 0 for count in counts.values()):
        raise ValueError('Insufficient history in one or more equipment partitions')

    partitions = {}
    transform = _fit_training_chunks(chunks['train'], counts['train'], spec.names)
    for part in ('train', 'validation', 'test'):
        part_directory = directory / part
        part_directory.mkdir(mode=0o700)
        feature_path, target_path = part_directory / 'features.npy', part_directory / 'targets.npy'
        features = np.lib.format.open_memmap(feature_path, mode='w+', dtype='<f8',
                                             shape=(counts[part], len(spec.names)))
        targets = np.lib.format.open_memmap(target_path, mode='w+', dtype=TARGET_DTYPE, shape=(counts[part],))
        del features, targets
        offset = 0
        observed = 0
        for path in chunks[part]:
            chunk = np.load(path, mmap_mode='r', allow_pickle=False)
            end = offset + len(chunk)
            features = np.load(feature_path, mmap_mode='r+', allow_pickle=False)
            targets = np.load(target_path, mmap_mode='r+', allow_pickle=False)
            features[offset:end] = transform.apply(chunk['features'], spec.names)
            for field in TARGET_DTYPE.names:
                targets[field][offset:end] = chunk[field]
            observed += int(np.count_nonzero(chunk['rul_observed']))
            offset = end
            features.flush()
            targets.flush()
            del features, targets, chunk
            path.unlink()
        partitions[part] = {'features': str(feature_path.relative_to(directory)),
            'targets': str(target_path.relative_to(directory)), 'row_count': counts[part],
            'rul_observed_rows': observed, 'rul_censored_rows': counts[part] - observed}
    raw_directory.rmdir()
    manifest = {'storage_version': 'training-numpy-v1', 'features_version': features_version(spec),
        'sensors': list(spec.sensors), 'windows_seconds': list(spec.windows_seconds),
        'feature_names': list(spec.names), 'source': source,
        'source_row_count': row_count, 'row_count': sum(counts.values()),
        'dropped_insufficient_history': dropped, 'split_seed': seed,
        'equipment_split': {part: list(ids) for part, ids in split.items()},
        'partitions': partitions, 'transform': transform.to_dict()}
    temporary = directory / 'manifest.json.tmp'
    temporary.write_text(json.dumps(manifest, allow_nan=False, sort_keys=True, indent=2) + '\n')
    temporary.replace(directory / 'manifest.json')
    return manifest
