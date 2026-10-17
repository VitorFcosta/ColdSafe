"""Offline health selection on validation, with a separately reserved test set."""
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import pickle
import platform
import resource
import sys
from time import perf_counter

import numpy as np
import sklearn
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits

from backend.app.domain.feature_preprocessing import FeatureTransform
from backend.app.domain.features import FeatureSpec
from backend.app.services.datasets import _internal_file
from backend.app.services.feature_inputs import features_version
from backend.app.services.training_data import TARGET_DTYPE, split_equipment

PARTITIONS = ('train', 'validation', 'test')
BATCH_SIZE = 5000


def _sha256(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _manifest(root: Path) -> tuple[dict, FeatureSpec, FeatureTransform]:
    path = _internal_file(root, 'manifest.json')
    if not 0 < path.stat().st_size <= 4 * 1_048_576:
        raise ValueError('Invalid prepared manifest size')
    manifest = json.loads(path.read_bytes())
    if manifest['storage_version'] != 'training-numpy-v1':
        raise ValueError('Unsupported prepared storage version')
    spec = FeatureSpec(tuple(manifest['sensors']), tuple(manifest['windows_seconds']))
    transform = FeatureTransform.from_dict(manifest['transform'])
    if (list(spec.sensors) != manifest['sensors'] or list(spec.names) != manifest['feature_names'] or
            transform.names != spec.names or manifest['features_version'] != features_version(spec)):
        raise ValueError('Inconsistent prepared feature contract')
    split = manifest['equipment_split']
    if set(split) != set(PARTITIONS) or any(not isinstance(split[p], list) or not split[p] for p in PARTITIONS):
        raise ValueError('Invalid equipment partitions')
    ids = [identifier for part in PARTITIONS for identifier in split[part]]
    expected = split_equipment(ids, manifest['split_seed'])
    if any(tuple(split[part]) != expected[part] for part in PARTITIONS):
        raise ValueError('Equipment split does not match seed')
    if set(manifest['partitions']) != set(PARTITIONS):
        raise ValueError('Invalid prepared partitions')
    counts = []
    for part in PARTITIONS:
        info = manifest['partitions'][part]
        count = info['row_count']
        if (type(count) is not int or not 0 < count <= 2_000_000 or
                info['features'] != f'{part}/features.npy' or info['targets'] != f'{part}/targets.npy' or
                any(type(info[key]) is not int or not 0 <= info[key] <= count
                    for key in ('rul_observed_rows', 'rul_censored_rows')) or
                info['rul_observed_rows'] + info['rul_censored_rows'] != count):
            raise ValueError('Invalid partition metadata')
        counts.append(count)
    if (type(manifest['row_count']) is not int or sum(counts) != manifest['row_count'] or
            type(manifest['source_row_count']) is not int or not sum(counts) <= manifest['source_row_count'] <= 2_000_000 or
            type(manifest['dropped_insufficient_history']) is not int or
            manifest['dropped_insufficient_history'] != manifest['source_row_count'] - sum(counts) or
            manifest['source'] is not None and not isinstance(manifest['source'], dict)):
        raise ValueError('Invalid prepared source counts or metadata')
    return manifest, spec, transform


def _partition(root: Path, manifest: dict, part: str, hashes: dict) -> tuple[np.ndarray, np.ndarray, set[int]]:
    info = manifest['partitions'][part]
    arrays = []
    for key in ('features', 'targets'):
        path = _internal_file(root, info[key])
        hashes[info[key]] = _sha256(path)
        arrays.append(np.load(path, mmap_mode='r', allow_pickle=False, max_header_size=10_000))
    features, targets = arrays
    count = info['row_count']
    if (features.dtype != np.dtype('<f8') or features.shape != (count, len(manifest['feature_names'])) or
            targets.dtype != TARGET_DTYPE or targets.shape != (count,)):
        raise ValueError('Invalid prepared array layout')
    groups = set()
    observed_count = 0
    equipment_count = sum(len(ids) for ids in manifest['equipment_split'].values())
    for start in range(0, count, BATCH_SIZE):
        x, y = features[start:start + BATCH_SIZE], targets[start:start + BATCH_SIZE]
        health = y['health_score_true']
        if (not np.isfinite(x).all() or not np.isfinite(health).all() or
                np.any((health < 0) | (health > 100)) or np.any(np.isnat(y['observed_at'])) or
                np.any(y['equipment_index'] < 0) or np.any(y['equipment_index'] >= equipment_count)):
            raise ValueError('Invalid prepared feature or health values')
        groups.update(int(value) for value in np.unique(y['equipment_index']))
        observed_count += int(np.count_nonzero(y['rul_observed']))
    if (len(groups) > len(manifest['equipment_split'][part]) or
            observed_count != info['rul_observed_rows']):
        raise ValueError('Prepared partition counts do not match arrays')
    return features, targets['health_score_true'], groups


def _evaluate(model, features: np.ndarray, health: np.ndarray) -> dict:
    absolute, squared, centered = 0., 0., 0.
    mean = float(np.mean(health))
    minimum, maximum = float(np.min(health)), float(np.max(health))
    for start in range(0, len(health), BATCH_SIZE):
        target = health[start:start + BATCH_SIZE]
        prediction = np.clip(model.predict(features[start:start + BATCH_SIZE]), 0, 100)
        if not np.isfinite(prediction).all():
            raise ValueError('Model produced nonfinite health predictions')
        residual = target - prediction
        absolute += float(np.abs(residual).sum())
        squared += float(np.square(residual).sum())
        centered += float(np.square(target - mean).sum())
    return {'mae': absolute / len(health), 'rmse': float(np.sqrt(squared / len(health))),
            'r2': None if len(health) < 2 or minimum == maximum or centered == 0 else 1 - squared / centered}


def train_health(prepared: Path, directory: Path, *, seed: int = 42) -> dict:
    """Fit on full training rows; select/gate on validation before opening test arrays.

    The output pickle is an internally produced, trusted bundle. This module never
    deserializes pickle input. A report is the final completion marker.
    """
    if type(seed) is not int or not 0 <= seed <= 2**32 - 1:
        raise ValueError('Training seed must be an unsigned 32-bit integer')
    if prepared.is_symlink():
        raise ValueError('Prepared root cannot be a symlink')
    root = prepared.resolve(strict=True)
    if directory.resolve().is_relative_to(root):
        raise ValueError('Training output must not mutate prepared input')
    directory.mkdir(mode=0o700, exist_ok=False)
    started = perf_counter()
    try:
        manifest, spec, transform = _manifest(root)
        hashes = {'manifest.json': _sha256(root / 'manifest.json')}
        training, y_train, train_groups = _partition(root, manifest, 'train', hashes)
        validation, y_validation, validation_groups = _partition(root, manifest, 'validation', hashes)
        if train_groups & validation_groups:
            raise ValueError('Equipment leakage between partitions')
        timings = {}
        with threadpool_limits(limits=1):
            phase = perf_counter()
            baseline = DummyRegressor(strategy='mean').fit(training, y_train)
            timings['baseline_fit_seconds'] = perf_counter() - phase
            phase = perf_counter()
            baseline_validation = _evaluate(baseline, validation, y_validation)
            timings['baseline_validation_seconds'] = perf_counter() - phase
            selected, selected_metrics, choices = None, None, []
            for leaves in (15, 31):
                model = HistGradientBoostingRegressor(max_leaf_nodes=leaves, max_iter=100,
                    early_stopping=False, random_state=seed)
                phase = perf_counter()
                model.fit(training, y_train)
                fit_seconds = perf_counter() - phase
                phase = perf_counter()
                metrics = _evaluate(model, validation, y_validation)
                evaluation_seconds = perf_counter() - phase
                choices.append({'parameters': model.get_params(), 'validation': metrics,
                    'fit_seconds': fit_seconds, 'validation_seconds': evaluation_seconds})
                if selected_metrics is None or metrics['mae'] < selected_metrics['mae']:
                    selected, selected_metrics = model, metrics
            eligible = selected_metrics['mae'] < baseline_validation['mae']
            # Test is opened only after selection and eligibility are fixed; no refitting.
            phase = perf_counter()
            test, y_test, test_groups = _partition(root, manifest, 'test', hashes)
            if test_groups & (train_groups | validation_groups):
                raise ValueError('Equipment leakage between partitions')
            test_metrics = {'baseline': _evaluate(baseline, test, y_test),
                            'candidate': _evaluate(selected, test, y_test)}
            timings['test_load_and_evaluation_seconds'] = perf_counter() - phase
    except (KeyError, TypeError, IndexError, OverflowError, EOFError) as error:
        raise ValueError('Invalid prepared training artifact') from error

    report = {'storage_version': 'health-training-v1', 'status': 'eligible' if eligible else 'rejected',
        'target': 'health_score_true', 'prediction_range': [0, 100],
        'selection': {'parameters': selected.get_params(), 'metric': 'mae', 'partition': 'validation',
            'gate': 'candidate_mae < baseline_mae', 'tie_policy': 'first candidate, reject baseline tie'},
        'metrics': {'validation': {'baseline': baseline_validation, 'candidate': selected_metrics},
                    'test': test_metrics}, 'candidates': choices,
        'r2_policy': 'null for fewer than two targets, constant targets or zero numerical variance; otherwise 1 - SSE/SST',
        'baseline': {'parameters': baseline.get_params(), 'training_mean': float(baseline.constant_[0, 0])},
        'features_version': manifest['features_version'], 'feature_names': manifest['feature_names'],
        'sensors': manifest['sensors'], 'windows_seconds': manifest['windows_seconds'],
        'transform': transform.to_dict(), 'source': manifest['source'],
        'seed': seed, 'split_seed': manifest['split_seed'], 'equipment_split': manifest['equipment_split'],
        'partition_rows': {part: manifest['partitions'][part]['row_count'] for part in PARTITIONS},
        'versions': {'python': platform.python_version(), 'numpy': np.__version__, 'sklearn': sklearn.__version__,
            **{name: version(name) for name in ('scipy', 'joblib', 'threadpoolctl', 'narwhals', 'cloudpickle')}},
        'input_hashes': hashes, 'model_sha256': None, 'timings': timings,
        'memory': {'scope': 'process lifetime high-water RSS, includes earlier work in this process',
            'peak_rss_bytes': int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss *
                                  (1 if sys.platform == 'darwin' else 1024))}}
    if eligible:
        temporary = directory / 'model.pkl.tmp'
        with temporary.open('xb') as stream:
            pickle.dump({'model': selected, 'transform': transform, 'spec': spec,
                'features_version': manifest['features_version'], 'prediction_range': (0, 100)},
                stream, protocol=pickle.HIGHEST_PROTOCOL)
        temporary.replace(directory / 'model.pkl')
        report['model_sha256'] = _sha256(directory / 'model.pkl')
    timings['total_seconds'] = perf_counter() - started
    temporary = directory / 'report.json.tmp'
    temporary.write_text(json.dumps(report, allow_nan=False, sort_keys=True, indent=2) + '\n')
    temporary.replace(directory / 'report.json')
    return report
