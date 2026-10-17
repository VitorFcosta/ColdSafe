import json
from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from backend.app.domain.feature_preprocessing import FeatureTransform, fit_transformer


NAMES = ("temperature_mean", "current_max")


def test_fits_medians_and_fixed_quantiles_from_training_values_only():
    training = np.array([[1.0, 10.0], [2.0, np.nan], [3.0, 30.0]])
    original = training.copy()

    transform = fit_transformer(training, NAMES)

    assert transform.names == NAMES
    np.testing.assert_allclose(transform.medians, [2, 20])
    np.testing.assert_allclose(transform.lower, [1.02, 10.2])
    np.testing.assert_allclose(transform.upper, [2.98, 29.8])
    np.testing.assert_array_equal(training, original)


def test_validation_and_test_outliers_use_training_state_and_preserve_inputs():
    transform = fit_transformer(np.array([[0.0, 10.0], [100.0, 20.0]]), NAMES)
    state = transform.to_dict()
    validation = np.array([[np.nan, 1e100], [-1e100, np.nan]])
    original = validation.copy()

    actual = transform.apply(validation, NAMES)

    np.testing.assert_allclose(actual, [[50, 19.9], [1, 15]])
    np.testing.assert_allclose(transform.apply(np.array([[1e120, -1e120]]), NAMES), [[99, 10.1]])
    np.testing.assert_array_equal(validation, original)
    assert transform.to_dict() == state
    assert np.isfinite(actual).all()


def test_one_training_row_and_constant_columns_are_supported():
    transform = fit_transformer(np.array([[2, 3]]), NAMES)
    np.testing.assert_array_equal(transform.apply(np.array([[np.nan, 100.0]]), NAMES), [[2, 3]])


def test_fits_a_read_only_mapped_training_matrix_without_changing_the_file(tmp_path):
    path = tmp_path / "training.npy"
    np.save(path, np.array([[1.0, np.nan], [3.0, 20.0]]))
    before = path.read_bytes()
    training = np.load(path, mmap_mode="r")

    transform = fit_transformer(training, NAMES)

    np.testing.assert_array_equal(transform.medians, [2, 20])
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "values",
    [
        [[1.0, 2.0]],
        np.array([1.0, 2.0]),
        np.ones((1, 1, 2)),
        np.empty((0, 2)),
        np.empty((1, 0)),
        np.ones((2, 3)),
        np.array([[True, False]]),
        np.array([["1", "2"]]),
        np.array([[1, 2]], dtype=object),
        np.array([[1j, 2j]]),
        np.array([[np.inf, 1.0]]),
        np.array([[1.0, -np.inf]]),
    ],
)
def test_fit_and_apply_reject_invalid_matrices(values):
    transform = fit_transformer(np.ones((2, 2)), NAMES)
    with pytest.raises(ValueError):
        fit_transformer(values, NAMES)
    with pytest.raises(ValueError):
        transform.apply(values, NAMES)


@pytest.mark.parametrize(
    "names",
    [(), ("", "b"), (" ", "b"), ("a", "a"), (1, "b"), ["a", "b"], "ab"],
)
def test_fit_rejects_invalid_names(names):
    with pytest.raises(ValueError):
        fit_transformer(np.ones((2, 2)), names)


def test_apply_rejects_reordered_names_even_when_shape_matches():
    transform = fit_transformer(np.ones((2, 2)), NAMES)
    with pytest.raises(ValueError, match="names"):
        transform.apply(np.ones((2, 2)), tuple(reversed(NAMES)))


def test_all_missing_training_column_is_rejected_without_a_zero_fallback():
    with pytest.raises(ValueError, match="missing"):
        fit_transformer(np.array([[np.nan, 2.0], [np.nan, 3.0]]), NAMES)


def test_all_missing_inference_columns_use_training_medians():
    transform = fit_transformer(np.array([[2.0, 10.0], [4.0, 20.0]]), NAMES)
    np.testing.assert_allclose(transform.apply(np.full((2, 2), np.nan), NAMES), [[3, 15], [3, 15]])


def test_transform_owns_immutable_state_and_serialization_does_not_expose_it():
    source = np.array([2.0, 3.0])
    transform = FeatureTransform(NAMES, source, source, source)
    source[:] = 100

    for values in (transform.medians, transform.lower, transform.upper):
        np.testing.assert_array_equal(values, [2, 3])
        with pytest.raises(ValueError):
            values[0] = 100
        with pytest.raises(ValueError):
            values.setflags(write=True)
    with pytest.raises(FrozenInstanceError):
        transform.names = ("other", "names")

    payload = transform.to_dict()
    payload["names"][0] = "changed"
    payload["medians"][0] = 100
    assert transform.names == NAMES
    np.testing.assert_array_equal(transform.medians, [2, 3])


def test_json_roundtrip_preserves_transform_and_schema():
    transform = fit_transformer(np.array([[1.0, 2.0], [3.0, 8.0]]), NAMES)
    payload = json.loads(json.dumps(transform.to_dict(), allow_nan=False))

    assert set(payload) == {"version", "names", "medians", "lower", "upper"}
    assert payload["version"] == "median-clip-v1"
    restored = FeatureTransform.from_dict(payload)
    values = np.array([[np.nan, 100.0]])
    np.testing.assert_array_equal(
        restored.apply(values, NAMES), transform.apply(values, NAMES)
    )
    payload["lower"][0] = -100
    np.testing.assert_array_equal(restored.lower, transform.lower)


@pytest.mark.parametrize(
    "changes",
    [
        {"version": "unknown"},
        {"names": ["a", "a"]},
        {"names": ["a", 2]},
        {"names": ("a", "b")},
        {"medians": [np.nan, 1]},
        {"medians": [np.inf, 1]},
        {"medians": [True, 1]},
        {"medians": ["1", 1]},
        {"medians": [None, 1]},
        {"medians": [1]},
        {"medians": [[1, 1]]},
        {"medians": (1, 1)},
        {"lower": [2, 0]},
        {"upper": [0, 2]},
        {"extra": "unsupported"},
    ],
)
def test_rejects_invalid_serialized_state(changes):
    payload = {
        "version": "median-clip-v1",
        "names": ["a", "b"],
        "medians": [1, 1],
        "lower": [0, 0],
        "upper": [2, 2],
    }
    with pytest.raises(ValueError):
        FeatureTransform.from_dict(payload | changes)


@pytest.mark.parametrize("payload", [None, [], {}, {"version": "median-clip-v1"}])
def test_rejects_missing_or_non_mapping_serialized_state(payload):
    with pytest.raises(ValueError):
        FeatureTransform.from_dict(payload)


@pytest.mark.parametrize(
    "medians,lower,upper",
    [
        ([1], [0, 0], [2, 2]),
        ([np.nan, 1], [0, 0], [2, 2]),
        ([1, 1], [2, 0], [3, 3]),
        ([1, 1], [0, 0], [0, 2]),
        ([True, False], [0, 0], [2, 2]),
    ],
)
def test_direct_construction_rejects_invalid_state(medians, lower, upper):
    with pytest.raises(ValueError):
        FeatureTransform(NAMES, np.array(medians), np.array(lower), np.array(upper))
