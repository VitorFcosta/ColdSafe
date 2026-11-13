import json

import numpy as np
import pytest
from sklearn.dummy import DummyRegressor

from backend.app.services.regression_diagnostics import regression_diagnostics


class FeatureModel:
    def __init__(self, *, offset=0, coefficient=1):
        self.offset, self.coefficient = offset, coefficient

    def fit(self, x, y):
        return self

    def predict(self, x):
        return self.offset + self.coefficient * x[:, 0]


def test_sample_is_bounded_seeded_ordered_reproducible_and_readonly():
    targets = np.linspace(0, 100, 1100)
    features = np.column_stack((targets, np.ones(len(targets))))
    before_x, before_y = features.copy(), targets.copy()
    baseline = DummyRegressor().fit(features, targets)
    model = FeatureModel()
    report = regression_diagnostics(model, baseline, features, targets, ['signal', 'constant'], seed=42)
    assert report == regression_diagnostics(model, baseline, features, targets, ['signal', 'constant'], seed=42)
    assert report['partition'] == 'test'
    assert report['total_rows'] == 1100
    assert report['sample_count'] == report['sample_max'] == 500
    assert report['sample_seed'] == 42
    assert report['sampling'] == 'seeded_without_replacement'
    expected = np.sort(np.random.default_rng(42).choice(1100, 500, replace=False))
    assert [point['actual'] for point in report['scatter']] == targets[expected].tolist()
    assert len({point['actual'] for point in report['scatter']}) == 500
    assert report != regression_diagnostics(model, baseline, features, targets, ['signal', 'constant'], seed=43)
    assert np.array_equal(features, before_x) and np.array_equal(targets, before_y)
    assert json.loads(json.dumps(report, allow_nan=False)) == report
    importance = report['permutation']
    assert importance['scoring'] == 'mae_increase'
    assert importance['sample_count'] == 500 and importance['repeats'] == 3
    assert importance['reference_mae'] == 0
    assert [item['name'] for item in importance['features']] == ['signal', 'constant']
    assert importance['features'][0]['mean'] > 0
    assert importance['features'][1] == {'name': 'constant', 'mean': 0., 'std': 0.}


@pytest.mark.parametrize('upper_bound,predicted,reference_mae', [(100, [0., 100.], 70.), (None, [0., 240.], 0.)])
def test_clipping_and_units_match_evaluation(upper_bound, predicted, reference_mae):
    features = np.array([[-5.], [240.]])
    targets = np.array([0., 240.])
    baseline = DummyRegressor(strategy='constant', constant=300).fit(features, targets)
    report = regression_diagnostics(FeatureModel(), baseline, features, targets, ['signal'], seed=0,
                                    upper_bound=upper_bound)
    assert report['sample_count'] == report['total_rows'] == 2
    assert [point['predicted'] for point in report['scatter']] == predicted
    assert [point['error'] for point in report['scatter']] == (np.array(predicted) - targets).tolist()
    assert [point['baseline'] for point in report['scatter']] == ([100., 100.] if upper_bound else [300., 300.])
    assert report['permutation']['reference_mae'] == reference_mae


def test_negative_importance_is_preserved_for_misleading_feature():
    targets = np.linspace(0, 100, 100)
    features = targets[:, None]
    baseline = DummyRegressor().fit(features, targets)
    report = regression_diagnostics(FeatureModel(offset=100, coefficient=-1), baseline,
                                    features, targets, ['misleading'], seed=42)
    assert report['permutation']['features'][0]['mean'] < 0


def test_single_row_constant_target_stays_finite():
    features, targets = np.array([[5.]]), np.array([5.])
    baseline = DummyRegressor().fit(features, targets)
    report = regression_diagnostics(FeatureModel(), baseline, features, targets, ['signal'], seed=42)
    assert report['scatter'] == [{'actual': 5., 'predicted': 5., 'baseline': 5., 'error': 0.}]
    assert report['permutation']['features'] == [{'name': 'signal', 'mean': 0., 'std': 0.}]
    json.dumps(report, allow_nan=False)


@pytest.mark.parametrize('value', [np.nan, np.inf])
def test_nonfinite_predictions_are_explicit_errors(value):
    features, targets = np.array([[5.]]), np.array([5.])
    baseline = DummyRegressor().fit(features, targets)
    with pytest.raises(ValueError, match='nonfinite'):
        regression_diagnostics(FeatureModel(offset=value), baseline, features, targets,
                               ['signal'], seed=42, upper_bound=None)


@pytest.mark.parametrize('features,targets,names', [
    (np.zeros((0, 1)), np.zeros(0), ['signal']),
    (np.zeros((2, 1)), np.zeros(1), ['signal']),
    (np.zeros((2, 1)), np.zeros(2), ['signal', 'extra']),
])
def test_invalid_layout_is_rejected(features, targets, names):
    with pytest.raises(ValueError, match='layout'):
        regression_diagnostics(FeatureModel(), FeatureModel(), features, targets, names, seed=42)


@pytest.mark.parametrize('features,targets', [
    (np.array([[np.nan]]), np.array([0.])),
    (np.array([[0.]]), np.array([np.inf])),
])
def test_nonfinite_sample_is_rejected(features, targets):
    with pytest.raises(ValueError, match='nonfinite'):
        regression_diagnostics(FeatureModel(), FeatureModel(), features, targets, ['signal'], seed=42)
