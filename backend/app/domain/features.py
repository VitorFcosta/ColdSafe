"""Causal rolling features shared by offline preparation and online inference.

Each window is [cutoff - duration, cutoff): the prediction instant never enters
its own features. Missing sensors and fewer than two distinct finite observation
times produce NaN in all four statistics. Temporal sufficiency is independent
of sensor missingness; the training-only preprocessor handles those NaNs later.
"""
from dataclasses import dataclass
import hashlib
import json
from numbers import Integral

import numpy as np

from backend.app.domain.jobs import SENSOR_TYPES


_STATS = ('mean', 'std', 'trend', 'max')
_INT64 = np.iinfo(np.int64)


@dataclass(frozen=True)
class FeatureSpec:
    sensors: tuple[str, ...] = SENSOR_TYPES
    windows_seconds: tuple[int, ...] = (900, 3600)

    def __post_init__(self) -> None:
        if (not isinstance(self.sensors, tuple) or not self.sensors
                or any(sensor not in SENSOR_TYPES for sensor in self.sensors)
                or len(set(self.sensors)) != len(self.sensors)):
            raise ValueError('sensors must be distinct canonical sensor names in a tuple')
        windows = self.windows_seconds
        if (not isinstance(windows, tuple) or not windows
                or any(isinstance(w, bool) or not isinstance(w, Integral)
                       or not 0 < w <= _INT64.max // 1000 for w in windows)
                or any(a >= b for a, b in zip(windows, windows[1:]))):
            raise ValueError('windows_seconds must be distinct increasing positive integer seconds')
        object.__setattr__(self, 'sensors', tuple(s for s in SENSOR_TYPES if s in self.sensors))
        object.__setattr__(self, 'windows_seconds', tuple(int(w) for w in windows))

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(f'{sensor}__{stat}__{window}s'
                     for window in self.windows_seconds for sensor in self.sensors for stat in _STATS)

    @property
    def version(self) -> str:
        contract = {'algorithm': 'rolling-v1', 'sensors': self.sensors,
                    'windows_seconds': self.windows_seconds, 'stats': _STATS,
                    'interval': '[cutoff-window,cutoff)', 'std_ddof': 0,
                    'trend': 'centered-ols-sensor-unit-per-hour',
                    'minimum': 'two-finite-values-at-distinct-times'}
        digest = hashlib.sha256(json.dumps(contract, sort_keys=True).encode()).hexdigest()[:16]
        return f'rolling-v1-{digest}'


@dataclass(frozen=True)
class FeatureBatch:
    values: np.ndarray
    sufficient: np.ndarray


def _timestamps(values: np.ndarray, name: str) -> None:
    if (not isinstance(values, np.ndarray) or values.ndim != 1 or values.dtype.kind not in 'iu'
            or np.any(values <= _INT64.min) or np.any(values > _INT64.max)):
        raise ValueError(f'{name} must be a one-dimensional int64-compatible millisecond array without NaT')
    if np.any(values[1:] < values[:-1]):
        raise ValueError(f'{name} must be ordered nondecreasing')


def _statistics(times: np.ndarray, values: np.ndarray) -> np.ndarray:
    """Reduce one local window; center before products to avoid epoch cancellation."""
    values = values.astype(np.float64, copy=False)
    finite = np.isfinite(values)
    count = finite.sum(axis=0)
    denominator = np.maximum(count, 1)
    mean = np.where(finite, values, 0).sum(axis=0) / denominator
    centered_y = np.where(finite, values - mean, 0)
    std = np.sqrt(np.square(centered_y).sum(axis=0) / denominator)
    # Subtract integer milliseconds first: converting the epoch to float loses precision.
    hours = ((times - times[0]).astype(np.float64) / 3_600_000)[:, None]
    centered_x = np.where(finite, hours - (hours * finite).sum(axis=0) / denominator, 0)
    sum_xx = np.square(centered_x).sum(axis=0)
    trend = np.divide((centered_x * centered_y).sum(axis=0), sum_xx,
                      out=np.full(values.shape[1], np.nan), where=sum_xx > 0)
    maximum = np.where(finite, values, -np.inf).max(axis=0)
    stats = np.column_stack((mean, std, trend, maximum))
    minimum_time = np.where(finite, times[:, None], _INT64.max).min(axis=0)
    maximum_time = np.where(finite, times[:, None], _INT64.min).max(axis=0)
    stats[(count < 2) | (minimum_time == maximum_time) | (sum_xx == 0)] = np.nan
    return stats.ravel()


def extract_features(
    times_ms: np.ndarray,
    measurements: np.ndarray,
    cutoffs_ms: np.ndarray,
    spec: FeatureSpec = FeatureSpec(),
) -> FeatureBatch:
    """Extract a single equipment's canonical sensor columns without mutation.

    Memory beyond the output is bounded by one window, without an N×F expansion
    or cumulative sums polluted by distant observations. Runtime scales with the
    number of samples inside the requested windows.
    """
    if not isinstance(spec, FeatureSpec):
        raise ValueError('spec must be a FeatureSpec')
    _timestamps(times_ms, 'times_ms')
    _timestamps(cutoffs_ms, 'cutoffs_ms')
    if (not isinstance(measurements, np.ndarray)
            or measurements.shape != (len(times_ms), len(spec.sensors))
            or measurements.dtype.kind != 'f' or np.isinf(measurements).any()):
        raise ValueError('measurements must be a float N×S array; NaN is allowed, infinity is not')
    times = times_ms.astype(np.int64, copy=False)
    cutoffs = cutoffs_ms.astype(np.int64, copy=False)
    result = np.full((len(cutoffs), len(spec.names)), np.nan)
    sufficient = np.zeros(len(cutoffs), dtype=bool)
    if not len(times) or not len(cutoffs):
        return FeatureBatch(result, sufficient)

    ends = np.searchsorted(times, cutoffs, side='left')
    width = len(spec.sensors) * len(_STATS)
    sufficient[:] = True
    for index, window in enumerate(spec.windows_seconds):
        duration = window * 1000
        # Python integers avoid signed overflow when a cutoff is near int64.min.
        lower = np.array([max(int(cutoff) - duration, _INT64.min + 1)
                          for cutoff in cutoffs], dtype=np.int64)
        starts = np.searchsorted(times, lower, side='left')
        full_span = np.array([int(times[0]) <= int(cutoff) - duration for cutoff in cutoffs])
        sufficient &= full_span
        for row, (start, end) in enumerate(zip(starts, ends, strict=True)):
            if end - start < 2 or times[start] == times[end - 1]:
                sufficient[row] = False
                continue
            try:
                with np.errstate(over='raise', invalid='raise', divide='raise'):
                    stats = _statistics(times[start:end], measurements[start:end])
            except FloatingPointError as exc:
                raise ValueError('Measurements exceed the numerical range of rolling features') from exc
            if np.isinf(stats).any():
                raise ValueError('Measurements exceed the numerical range of rolling features')
            result[row, index * width:(index + 1) * width] = stats
    return FeatureBatch(result, sufficient)
