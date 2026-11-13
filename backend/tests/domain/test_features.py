from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from backend.app.domain.features import FeatureSpec, extract_features
from backend.app.domain.jobs import SENSOR_TYPES


SPEC = FeatureSpec(sensors=(SENSOR_TYPES[0],), windows_seconds=(10, 20))


def extract(times, values, cutoffs, spec=SPEC):
    return extract_features(np.array(times, dtype=np.int64),
                            np.array(values, dtype=np.float64).reshape(-1, len(spec.sensors)),
                            np.array(cutoffs, dtype=np.int64), spec)


def test_spec_is_canonical_immutable_and_versions_configuration():
    spec = FeatureSpec(sensors=(SENSOR_TYPES[2], SENSOR_TYPES[0]))
    assert spec.sensors == (SENSOR_TYPES[0], SENSOR_TYPES[2])
    assert spec.names[:5] == (
        'ambient_temperature_c__mean__900s', 'ambient_temperature_c__std__900s',
        'ambient_temperature_c__trend__900s', 'ambient_temperature_c__max__900s',
        'light_percent__mean__900s')
    assert spec.version.startswith('rolling-v1-')
    assert spec.version == FeatureSpec(sensors=tuple(reversed(spec.sensors))).version
    assert spec.version != FeatureSpec(sensors=spec.sensors, windows_seconds=(10,)).version
    with pytest.raises(FrozenInstanceError):
        spec.sensors = ()


@pytest.mark.parametrize('sensors', [(), ('id',), ('rul_hours_true',), ('health_score_true',),
                                     ('degradation_true',), ('equipment_index',),
                                     (SENSOR_TYPES[0], SENSOR_TYPES[0]), [SENSOR_TYPES[0]], (1,)])
def test_spec_rejects_non_sensor_columns_and_mutable_choices(sensors):
    with pytest.raises(ValueError):
        FeatureSpec(sensors=sensors)


@pytest.mark.parametrize('windows', [(), (0,), (-1,), (True,), (1.5,), (20, 10),
                                     (10, 10), [10], (2**63,)])
def test_spec_rejects_invalid_windows(windows):
    with pytest.raises(ValueError):
        FeatureSpec(windows_seconds=windows)


def test_half_open_windows_population_std_and_trend_per_hour():
    batch = extract([0, 10_000, 15_000, 20_000, 25_000], [0, 10, 15, 20, 1e30], [20_000])
    np.testing.assert_allclose(batch.values[0],
        [12.5, 2.5, 3600, 15, 25 / 3, np.std([0, 10, 15]), 3600, 15])
    assert batch.sufficient.tolist() == [True]


def test_future_and_cutoff_duplicates_cannot_change_features():
    before = extract([0, 10_000, 15_000], [0, 10, 15], [20_000])
    after = extract([0, 10_000, 15_000, 20_000, 20_000, 30_000],
                    [0, 10, 15, 1e30, -1e30, 1e100], [20_000])
    np.testing.assert_array_equal(before.values, after.values)
    np.testing.assert_array_equal(before.sufficient, after.sufficient)


@pytest.mark.parametrize('values', [[1e308, 1e308], [-1e200, 1e200]])
def test_finite_values_that_overflow_reductions_fail_explicitly(values):
    with pytest.raises(ValueError, match='numerical range'):
        extract([0, 1000], values, [10_000])


def test_finite_extremes_outside_windows_do_not_affect_computation():
    before = extract([10_000, 15_000], [10, 15], [20_000])
    after = extract([-10_000, 10_000, 15_000, 20_000, 30_000],
                    [1e308, 10, 15, 1e308, -1e308], [20_000])
    np.testing.assert_array_equal(before.values, after.values)


def test_offline_and_online_have_identical_results_without_mutating_inputs():
    times = np.arange(0, 40_001, 1000, dtype=np.int64)
    values = times[:, None] / 1000
    cutoffs = np.array([20_000, 30_000], dtype=np.int64)
    originals = [a.copy() for a in (times, values, cutoffs)]
    offline = extract_features(times, values, cutoffs, SPEC)
    for i, cutoff in enumerate(cutoffs):
        past = times < cutoff
        online = extract_features(times[past], values[past], np.array([cutoff]), SPEC)
        np.testing.assert_array_equal(offline.values[i], online.values[0])
        assert offline.sufficient[i] == online.sufficient[0]
    for actual, original in zip((times, values, cutoffs), originals, strict=True):
        np.testing.assert_array_equal(actual, original)


def test_missing_and_degenerate_times_remain_nan_instead_of_zero():
    spec = FeatureSpec(sensors=SENSOR_TYPES[:3], windows_seconds=(10,))
    batch = extract([0, 0, 5000], [[1, 0, np.nan], [3, np.nan, np.nan],
                                 [np.nan, 0, 8]], [10_000], spec)
    assert np.isnan(batch.values[0, :4]).all()  # finite values share one timestamp
    np.testing.assert_array_equal(batch.values[0, 4:8], [0, 0, 0, 0])
    assert np.isnan(batch.values[0, 8:]).all()  # only one finite value
    assert batch.sufficient.tolist() == [True]


def test_temporal_sufficiency_requires_full_span_and_each_window_two_distinct_times():
    batch = extract([0, 10_000, 10_000], [np.nan] * 3, [15_000, 20_000, 25_000])
    assert batch.sufficient.tolist() == [False, False, False]
    assert np.isnan(batch.values).all()
    assert extract([0, 10_000, 15_000], [np.nan] * 3, [20_000]).sufficient.tolist() == [True]


def test_empty_history_and_empty_queries_preserve_shapes():
    batch = extract([], [], [20_000])
    assert batch.values.shape == (1, 8)
    assert np.isnan(batch.values).all()
    assert batch.sufficient.tolist() == [False]
    batch = extract([0], [1], [])
    assert batch.values.shape == (0, 8)
    assert batch.sufficient.shape == (0,)


def test_rejects_unvalidated_spec():
    with pytest.raises(ValueError, match='FeatureSpec'):
        extract_features(np.array([0]), np.array([[1.]]), np.array([10_000]), None)


def test_duplicate_finite_times_after_an_earlier_missing_value_are_degenerate():
    batch = extract([0, 3, 3, 3], [np.nan, 1, 2, 3], [10_000])
    assert np.isnan(batch.values).all()


def test_float32_input_is_reduced_at_float64_precision():
    times = np.array([0, 1000, 2000])
    values = np.array([[100_000_000], [100_000_008], [100_000_016]], dtype=np.float32)
    batch = extract_features(times, values, np.array([10_000]), SPEC)
    np.testing.assert_allclose(batch.values[0, :4],
                               [100_000_008, np.std([0., 8., 16.]), 28_800, 100_000_016],
                               rtol=1e-12)


def test_long_span_high_epoch_remains_stable_and_outliers_are_not_hidden():
    epoch = 8_000_000_000_000_000_000
    spec = FeatureSpec(sensors=SPEC.sensors, windows_seconds=(10,))
    times = np.array([-epoch, epoch, epoch + 1000, epoch + 2000], dtype=np.int64)
    batch = extract_features(times, np.array([[1e30], [1e9], [1e9 + 1], [1e9 + 2]]),
                             np.array([epoch + 3000]), spec)
    np.testing.assert_allclose(batch.values[0], [1e9 + 1, np.sqrt(2 / 3), 3600, 1e9 + 2],
                               rtol=1e-12)
    assert extract([0, 1000], [1, 1e6], [10_000], spec).values[0, 3] == 1e6


@pytest.mark.parametrize(('times', 'values', 'cutoffs'), [
    (np.array([0., 1.]), np.ones((2, 1)), np.array([2])),
    (np.array([False, True]), np.ones((2, 1)), np.array([2])),
    (np.array([1, 0]), np.ones((2, 1)), np.array([2])),
    (np.array([np.iinfo(np.int64).min]), np.ones((1, 1)), np.array([2])),
    (np.array([0, 1]), np.ones((2, 1)), np.array([2., 3.])),
    (np.array([0, 1]), np.ones((2, 1)), np.array([True])),
    (np.array([0, 1]), np.ones((2, 1)), np.array([3, 2])),
    (np.array([[0, 1]]), np.ones((2, 1)), np.array([2])),
    (np.array([0, 1]), np.ones((1, 1)), np.array([2])),
    (np.array([0, 1]), np.ones((2, 2)), np.array([2])),
    (np.array([0, 1]), np.ones((2, 1), dtype=bool), np.array([2])),
    (np.array([0, 1]), np.array([[1], [np.inf]]), np.array([2])),
    (np.array([0, 1]), np.ones((2, 1)), np.array([[2]])),
    (np.array([0, 1]), np.ones((2, 1)), np.array([np.iinfo(np.int64).min])),
    (np.array([2**63], dtype=np.uint64), np.ones((1, 1)), np.array([2])),
    (np.array([0, 1]), np.array([['1'], ['2']]), np.array([2])),
])
def test_rejects_invalid_array_contracts(times, values, cutoffs):
    with pytest.raises(ValueError):
        extract_features(times, values, cutoffs, SPEC)


def test_matches_direct_reference_with_irregular_duplicate_and_missing_samples():
    rng = np.random.default_rng(12)
    times = np.cumsum(rng.integers(0, 1000, 80))
    values = rng.normal(size=(80, 2))
    values[rng.random(values.shape) < .2] = np.nan
    spec = FeatureSpec(sensors=SENSOR_TYPES[:2], windows_seconds=(3, 10))
    cutoffs = np.arange(10_000, 30_000, 1500)
    batch = extract_features(times, values, cutoffs, spec)
    for q, cutoff in enumerate(cutoffs):
        expected = []
        for window in spec.windows_seconds:
            mask = (times >= cutoff - window * 1000) & (times < cutoff)
            for column in range(2):
                finite = mask & np.isfinite(values[:, column])
                x = (times[finite] - cutoff) / 3_600_000
                y = values[finite, column]
                if len(y) < 2 or np.unique(x).size < 2:
                    expected.extend([np.nan] * 4)
                else:
                    expected.extend([y.mean(), y.std(), np.polyfit(x, y, 1)[0], y.max()])
        np.testing.assert_allclose(batch.values[q], expected, atol=1e-10, equal_nan=True)
