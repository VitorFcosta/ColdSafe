"""Offline RUL regression in hours, using only observed failures for fitting."""
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

from backend.app.services.datasets import _internal_file
from backend.app.services.health_training import BATCH_SIZE, PARTITIONS, _evaluate, _manifest, _partition, _sha256

NEAR_FAILURE_HOURS = 24


def _rul_partition(root: Path, manifest: dict, part: str, hashes: dict) -> tuple[np.ndarray, np.ndarray, set[int]]:
    features, _, groups = _partition(root, manifest, part, hashes)
    path = _internal_file(root, manifest['partitions'][part]['targets'])
    targets = np.load(path, mmap_mode='r', allow_pickle=False, max_header_size=10_000)
    for start in range(0, len(targets), BATCH_SIZE):
        batch = targets[start:start + BATCH_SIZE]
        observed, rul = batch['rul_observed'], batch['rul_hours_true']
        if (not np.isfinite(rul[observed]).all() or np.any(rul[observed] < 0) or
                not np.isnan(rul[~observed]).all()):
            raise ValueError('Invalid prepared RUL labels: observed must be finite/nonnegative; censored must be NaN')
    observed = targets['rul_observed']
    if not observed.any():
        raise ValueError(f'Partition {part} has no observed RUL targets')
    return features[observed], targets['rul_hours_true'][observed], groups


def _near_failure(baseline, candidate, features: np.ndarray, targets: np.ndarray) -> dict:
    mask = targets <= NEAR_FAILURE_HOURS
    count = int(np.count_nonzero(mask))
    return {'row_count': count,
        'baseline': _evaluate(baseline, features[mask], targets[mask], upper_bound=None) if count else None,
        'candidate': _evaluate(candidate, features[mask], targets[mask], upper_bound=None) if count else None}


def train_rul(prepared: Path, directory: Path, *, seed: int = 42) -> dict:
    """Select/gate independent RUL on validation before opening the reserved test.

    Censored machines remain in leakage checks but cannot supply known failure
    targets. Pickle output is trusted internal data; this module never reads it.
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
        training, y_train, train_groups = _rul_partition(root, manifest, 'train', hashes)
        validation, y_validation, validation_groups = _rul_partition(root, manifest, 'validation', hashes)
        if train_groups & validation_groups:
            raise ValueError('Equipment leakage between partitions')
        timings = {}
        with threadpool_limits(limits=1):
            phase = perf_counter()
            baseline = DummyRegressor(strategy='mean').fit(training, y_train)
            timings['baseline_fit_seconds'] = perf_counter() - phase
            phase = perf_counter()
            baseline_validation = _evaluate(baseline, validation, y_validation, upper_bound=None)
            timings['baseline_validation_seconds'] = perf_counter() - phase
            selected, selected_metrics, choices = None, None, []
            for leaves in (15, 31):
                model = HistGradientBoostingRegressor(max_leaf_nodes=leaves, max_iter=100,
                    early_stopping=False, random_state=seed)
                phase = perf_counter()
                model.fit(training, y_train)
                fit_seconds = perf_counter() - phase
                phase = perf_counter()
                metrics = _evaluate(model, validation, y_validation, upper_bound=None)
                evaluation_seconds = perf_counter() - phase
                choices.append({'parameters': model.get_params(), 'validation': metrics,
                    'fit_seconds': fit_seconds, 'validation_seconds': evaluation_seconds})
                if selected_metrics is None or metrics['mae'] < selected_metrics['mae']:
                    selected, selected_metrics = model, metrics
            eligible = selected_metrics['mae'] < baseline_validation['mae']
            near_failure = {'threshold_hours': NEAR_FAILURE_HOURS,
                'validation': _near_failure(baseline, selected, validation, y_validation)}
            del training, y_train, validation, y_validation
            # Test cannot choose parameters; release train/validation copies before loading it.
            phase = perf_counter()
            test, y_test, test_groups = _rul_partition(root, manifest, 'test', hashes)
            if test_groups & (train_groups | validation_groups):
                raise ValueError('Equipment leakage between partitions')
            test_metrics = {'baseline': _evaluate(baseline, test, y_test, upper_bound=None),
                            'candidate': _evaluate(selected, test, y_test, upper_bound=None)}
            near_failure['test'] = _near_failure(baseline, selected, test, y_test)
            timings['test_load_and_evaluation_seconds'] = perf_counter() - phase
    except (KeyError, TypeError, IndexError, OverflowError, EOFError) as error:
        raise ValueError('Invalid prepared training artifact') from error

    report = {'storage_version': 'rul-training-v1', 'status': 'eligible' if eligible else 'rejected',
        'target': 'rul_hours_true', 'unit': 'hours', 'prediction_range': [0, None],
        'selection': {'parameters': selected.get_params(), 'metric': 'mae', 'partition': 'validation',
            'gate': 'candidate_mae < baseline_mae', 'tie_policy': 'first candidate, reject baseline tie'},
        'metrics': {'validation': {'baseline': baseline_validation, 'candidate': selected_metrics},
                    'test': test_metrics}, 'candidates': choices, 'near_failure': near_failure,
        'censoring_policy': 'fit and metrics use observed failures only; censored RUL remains NaN, never zero',
        'r2_policy': 'null for fewer than two targets, constant targets or zero numerical variance; otherwise 1 - SSE/SST',
        'baseline': {'parameters': baseline.get_params(), 'training_mean': float(baseline.constant_[0, 0])},
        'features_version': manifest['features_version'], 'feature_names': manifest['feature_names'],
        'sensors': manifest['sensors'], 'windows_seconds': manifest['windows_seconds'],
        'transform': transform.to_dict(), 'source': manifest['source'],
        'seed': seed, 'split_seed': manifest['split_seed'], 'equipment_split': manifest['equipment_split'],
        'partition_rows': {part: {'full': manifest['partitions'][part]['row_count'],
            'observed': manifest['partitions'][part]['rul_observed_rows'],
            'censored': manifest['partitions'][part]['rul_censored_rows']} for part in PARTITIONS},
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
                'features_version': manifest['features_version'], 'target': 'rul_hours_true',
                'unit': 'hours', 'prediction_range': (0, None)}, stream, protocol=pickle.HIGHEST_PROTOCOL)
        temporary.replace(directory / 'model.pkl')
        report['model_sha256'] = _sha256(directory / 'model.pkl')
    timings['total_seconds'] = perf_counter() - started
    temporary = directory / 'report.json.tmp'
    temporary.write_text(json.dumps(report, allow_nan=False, sort_keys=True, indent=2) + '\n')
    temporary.replace(directory / 'report.json')
    return report
