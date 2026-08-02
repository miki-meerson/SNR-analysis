from __future__ import annotations

from collections import OrderedDict
from pathlib import Path

import numpy as np
import pandas as pd


SPIKE_FILE_NAME = "detected_peaks.parquet"
SPIKE_DIR_NAME = "spike_detection"
MAX_CACHED_SPIKE_FILES = 8
_SPIKE_CACHE: OrderedDict[tuple[str, float], dict[int, np.ndarray]] = OrderedDict()


def spike_file_path(experiment_path: Path) -> Path:
    return experiment_path / SPIKE_DIR_NAME / SPIKE_FILE_NAME


def has_spike_file(experiment_path: Path) -> bool:
    return spike_file_path(experiment_path).is_file()


def _cache_key(path: Path) -> tuple[str, float]:
    return (str(path), path.stat().st_mtime)


def load_detected_peaks(experiment_path: Path) -> dict[int, np.ndarray]:
    path = spike_file_path(experiment_path)
    if not path.is_file():
        return {}

    key = _cache_key(path)
    if key in _SPIKE_CACHE:
        _SPIKE_CACHE.move_to_end(key)
        return _SPIKE_CACHE[key]

    frame = pd.read_parquet(path)
    required_columns = {"cell_idx", "detected_peaks"}
    if not required_columns.issubset(frame.columns):
        raise ValueError(f"Unexpected detected peaks schema in {path}")

    peaks_by_roi: dict[int, np.ndarray] = {}
    for row in frame.itertuples(index=False):
        if pd.isna(row.cell_idx):
            continue
        roi_index = int(row.cell_idx) - 1
        peaks = np.asarray(row.detected_peaks if row.detected_peaks is not None else [], dtype=int)
        peaks_by_roi[roi_index] = np.unique(peaks)

    _SPIKE_CACHE[key] = peaks_by_roi
    _SPIKE_CACHE.move_to_end(key)
    while len(_SPIKE_CACHE) > MAX_CACHED_SPIKE_FILES:
        _SPIKE_CACHE.popitem(last=False)
    return peaks_by_roi
