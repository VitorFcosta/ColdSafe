"""Bounded reserved-test diagnostics; never participates in model selection."""
from collections.abc import Sequence

import numpy as np
from sklearn.inspection import permutation_importance
from threadpoolctl import threadpool_limits

SAMPLE_MAX = 500
PERMUTATION_REPEATS = 3


def regression_diagnostics(model, baseline, features: np.ndarray, targets: np.ndarray,
                           feature_names: Sequence[str], *, seed: int,
                           upper_bound: float | None = 100) -> dict:
    """Use the same ordered sample for scatter and permutation MAE increase."""
    if (features.ndim != 2 or targets.ndim != 1 or not len(targets) or
            features.shape != (len(targets), len(feature_names))):
        raise ValueError('Invalid diagnostic feature or target layout')
    count = min(len(targets), SAMPLE_MAX)
    indices = np.sort(np.random.default_rng(seed).choice(len(targets), count, replace=False))
    sample, actual = features[indices], targets[indices]
    if not np.isfinite(sample).all() or not np.isfinite(actual).all():
        raise ValueError('Diagnostic sample contains nonfinite values')

    def predict(estimator, values):
        prediction = np.clip(estimator.predict(values), 0, upper_bound)
        if not np.isfinite(prediction).all():
            raise ValueError('Model produced nonfinite predictions')
        return prediction

    def score(estimator, values, target):
        return -float(np.mean(np.abs(target - predict(estimator, values))))

    with threadpool_limits(limits=1):
        predicted, reference = predict(model, sample), predict(baseline, sample)
        importance = permutation_importance(model, sample, actual, scoring=score,
            n_repeats=PERMUTATION_REPEATS, random_state=seed, n_jobs=1)
    return {'partition': 'test', 'total_rows': len(targets), 'sample_count': count,
        'sample_seed': seed, 'sample_max': SAMPLE_MAX, 'sampling': 'seeded_without_replacement',
        'scatter': [{'actual': float(a), 'predicted': float(p), 'baseline': float(b), 'error': float(p - a)}
                    for a, p, b in zip(actual, predicted, reference, strict=True)],
        'permutation': {'scoring': 'mae_increase', 'repeats': PERMUTATION_REPEATS,
            'sample_count': count, 'reference_mae': float(np.mean(np.abs(actual - predicted))),
            'features': [{'name': name, 'mean': float(mean), 'std': float(std)}
                for name, mean, std in zip(feature_names, importance.importances_mean,
                                            importance.importances_std, strict=True)]}}
