"""Training-only median imputation and clipping, reusable during inference."""

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


TRANSFORM_VERSION = "median-clip-v1"
LOWER_QUANTILE = 0.01
UPPER_QUANTILE = 0.99


def _validate_names(names: tuple[str, ...]) -> None:
    if (
        not isinstance(names, tuple)
        or not names
        or any(not isinstance(name, str) or not name.strip() for name in names)
        or len(set(names)) != len(names)
    ):
        raise ValueError("Feature names must be a nonempty tuple of unique nonempty strings")


def _matrix(values: NDArray, names: tuple[str, ...]) -> NDArray[np.float64]:
    _validate_names(names)
    if (
        not isinstance(values, np.ndarray)
        or values.ndim != 2
        or values.shape[0] == 0
        or values.shape[1] != len(names)
        or values.dtype.kind not in "iuf"
    ):
        raise ValueError("Feature values must be a nonempty numeric N x F matrix matching names")
    result = values.astype(np.float64, copy=False)
    if any(np.isinf(column).any() for column in result.T):
        raise ValueError("Feature values cannot contain infinity")
    return result


@dataclass(frozen=True)
class FeatureTransform:
    names: tuple[str, ...]
    medians: NDArray[np.float64]
    lower: NDArray[np.float64]
    upper: NDArray[np.float64]

    def __post_init__(self) -> None:
        _validate_names(self.names)
        for name in ("medians", "lower", "upper"):
            values = getattr(self, name)
            if (
                not isinstance(values, np.ndarray)
                or values.shape != (len(self.names),)
                or values.dtype.kind not in "iuf"
                or not np.isfinite(values).all()
            ):
                raise ValueError(f"Transform {name} must be a finite numeric vector matching names")
            # Immutable storage prevents callers from re-enabling ndarray writes.
            immutable = np.frombuffer(values.astype(np.float64).tobytes(), dtype=np.float64)
            if not np.isfinite(immutable).all():
                raise ValueError(f"Transform {name} must fit finite float64 values")
            object.__setattr__(self, name, immutable)
        if np.any(self.lower > self.medians) or np.any(self.medians > self.upper):
            raise ValueError("Transform requires lower <= median <= upper for every feature")

    def apply(self, values: NDArray, names: tuple[str, ...]) -> NDArray[np.float64]:
        matrix = _matrix(values, names)
        if names != self.names:
            raise ValueError("Feature names and order must match the fitted transform")
        matrix = np.where(np.isnan(matrix), self.medians, matrix)
        return np.clip(matrix, self.lower, self.upper)

    def to_dict(self) -> dict[str, object]:
        return {
            "version": TRANSFORM_VERSION,
            "names": list(self.names),
            "medians": self.medians.tolist(),
            "lower": self.lower.tolist(),
            "upper": self.upper.tolist(),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "FeatureTransform":
        if (
            not isinstance(payload, dict)
            or set(payload) != {"version", "names", "medians", "lower", "upper"}
            or payload["version"] != TRANSFORM_VERSION
            or not isinstance(payload["names"], list)
        ):
            raise ValueError("Invalid transform schema or version")
        vectors = []
        for name in ("medians", "lower", "upper"):
            values = payload[name]
            if not isinstance(values, list) or any(
                type(value) not in (int, float) for value in values
            ):
                raise ValueError(f"Transform {name} must be a JSON numeric list")
            try:
                vectors.append(np.array(values, dtype=np.float64))
            except (ValueError, OverflowError) as error:
                raise ValueError(f"Transform {name} must fit finite float64 values") from error
        return cls(tuple(payload["names"]), *vectors)


def fit_transformer(training_values: NDArray, names: tuple[str, ...]) -> FeatureTransform:
    matrix = _matrix(training_values, names)
    medians = np.empty(len(names))
    lower = np.empty(len(names))
    upper = np.empty(len(names))
    # Fit one column at a time so a mapped training matrix is not copied in full.
    for index, column in enumerate(matrix.T):
        if np.isnan(column).all():
            raise ValueError("Cannot fit a feature with all training values missing")
        lower[index], upper[index] = np.nanquantile(column, (LOWER_QUANTILE, UPPER_QUANTILE))
        medians[index] = np.nanmedian(column)
    return FeatureTransform(names, medians, lower, upper)
