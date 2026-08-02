from __future__ import annotations

from collections.abc import Callable

import numpy as np


Normalizer = Callable[[np.ndarray], np.ndarray]


def robust_percentile(values: np.ndarray) -> np.ndarray:
    finite = np.isfinite(values)
    if not finite.any():
        return np.zeros_like(values, dtype=float)

    center = np.nanmedian(values)
    spread = np.nanpercentile(values, 95) - np.nanpercentile(values, 5)
    if not np.isfinite(spread) or spread == 0:
        spread = np.nanstd(values)
    if not np.isfinite(spread) or spread == 0:
        spread = 1.0
    return (values - center) / spread


def min_max(values: np.ndarray) -> np.ndarray:
    finite = np.isfinite(values)
    if not finite.any():
        return np.zeros_like(values, dtype=float)

    minimum = np.nanmin(values)
    maximum = np.nanmax(values)
    spread = maximum - minimum
    if not np.isfinite(spread) or spread == 0:
        spread = 1.0
    return (values - minimum) / spread


NORMALIZATION_METHODS: dict[str, Normalizer] = {
    "min_max": min_max,
    "robust_percentile": robust_percentile,
}


def normalize_values(values: np.ndarray, method: str) -> np.ndarray:
    try:
        normalizer = NORMALIZATION_METHODS[method]
    except KeyError as exc:
        available = ", ".join(sorted(NORMALIZATION_METHODS))
        raise ValueError(f"Unknown normalization method '{method}'. Available methods: {available}") from exc
    return normalizer(values)
