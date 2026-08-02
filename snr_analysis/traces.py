from __future__ import annotations

import re
from collections import OrderedDict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .config import TRACE_TYPES, TraceType
from .filters import highpass_frame
from .normalization import normalize_values
from .spikes import has_spike_file, load_detected_peaks


MAX_CACHED_FRAMES = 8
FrameCacheKey = tuple[str, float, int, float, tuple[int, ...] | str]
FrameCacheValue = tuple[pd.DataFrame, pd.DataFrame, int]
_FRAME_CACHE: OrderedDict[FrameCacheKey, FrameCacheValue] = OrderedDict()


def find_csvs(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.glob("*.csv") if p.is_file())


def count_columns(csv_path: Path) -> int:
    with csv_path.open("r", encoding="utf-8-sig") as handle:
        first_line = handle.readline().strip()
    if not first_line:
        return 0
    return len(first_line.split(","))


def get_trace_type(trace_key: str) -> TraceType:
    trace_type = next((item for item in TRACE_TYPES if item.key == trace_key), None)
    if trace_type is None:
        raise ValueError(f"Unknown trace type: {trace_key}")
    return trace_type


def get_experiment_trace_info(experiment_path: Path) -> dict[str, Any]:
    if not experiment_path.is_dir():
        raise ValueError(f"Folder does not exist: {experiment_path}")

    trace_types = []
    for trace_type in TRACE_TYPES:
        trace_dir = experiment_path / trace_type.relative_dir
        csvs = find_csvs(trace_dir)
        first_csv = csvs[0] if csvs else None
        trace_types.append(
            {
                "key": trace_type.key,
                "label": trace_type.label,
                "relative_dir": str(trace_type.relative_dir),
                "available": bool(csvs),
                "files": [
                    {
                        "name": csv.name,
                        "path": str(csv),
                        "size_mb": round(csv.stat().st_size / 1024 / 1024, 2),
                    }
                    for csv in csvs
                ],
                "columns": count_columns(first_csv) if first_csv else 0,
            }
        )

    return {
        "experiment_path": str(experiment_path),
        "name": experiment_path.name,
        "trace_types": trace_types,
        "spikes_available": has_spike_file(experiment_path),
        "spike_roi_indices": sorted(load_detected_peaks(experiment_path)),
    }


def parse_trace_selection(selection: str, total_columns: int) -> list[int]:
    if total_columns <= 0:
        return []
    cleaned = selection.strip().lower()
    if not cleaned or cleaned == "all":
        return list(range(total_columns))

    indices: set[int] = set()
    for token in re.split(r"[\s,]+", cleaned):
        if not token:
            continue
        match = re.fullmatch(r"(\d+)(?:-(\d+))?", token)
        if not match:
            raise ValueError(f"Invalid trace selection: {token}")
        start = int(match.group(1))
        end = int(match.group(2) or start)
        if end < start:
            start, end = end, start
        indices.update(range(start - 1, end))

    valid = sorted(i for i in indices if 0 <= i < total_columns)
    if not valid:
        raise ValueError(f"No selected cells exist in 1-{total_columns}")
    return valid[:80]


def cache_key(csv_path: Path, start_frame: int, highpass_cutoff_hz: float, columns: list[int] | str) -> FrameCacheKey:
    column_key = columns if columns == "all" else tuple(columns)
    return (str(csv_path), csv_path.stat().st_mtime, start_frame, float(highpass_cutoff_hz), column_key)


def get_cached_frame(csv_path: Path, start_frame: int, highpass_cutoff_hz: float, columns: list[int]) -> FrameCacheValue | None:
    all_key = cache_key(csv_path, start_frame, highpass_cutoff_hz, "all")
    if all_key in _FRAME_CACHE:
        frame, hp_frame, original_points = _FRAME_CACHE[all_key]
        _FRAME_CACHE.move_to_end(all_key)
        return frame.loc[:, columns].copy(), hp_frame.loc[:, columns].copy(), original_points

    key = cache_key(csv_path, start_frame, highpass_cutoff_hz, columns)
    if key not in _FRAME_CACHE:
        return None
    frame, hp_frame, original_points = _FRAME_CACHE[key]
    _FRAME_CACHE.move_to_end(key)
    return frame.copy(), hp_frame.copy(), original_points


def store_cached_frame(
    csv_path: Path,
    start_frame: int,
    highpass_cutoff_hz: float,
    columns: list[int],
    frame: pd.DataFrame,
    hp_frame: pd.DataFrame,
    original_points: int,
) -> None:
    key_columns: list[int] | str = "all" if len(columns) == count_columns(csv_path) else columns
    key = cache_key(csv_path, start_frame, highpass_cutoff_hz, key_columns)
    _FRAME_CACHE[key] = (frame.copy(), hp_frame.copy(), original_points)
    _FRAME_CACHE.move_to_end(key)
    while len(_FRAME_CACHE) > MAX_CACHED_FRAMES:
        _FRAME_CACHE.popitem(last=False)


def decimate_frame(frame: pd.DataFrame, point_limit: int) -> pd.DataFrame:
    if point_limit <= 0 or len(frame) <= point_limit:
        return frame
    step = int(np.ceil(len(frame) / point_limit))
    return frame.iloc[::step, :]


def load_trace_payload(
    experiment_path: Path,
    trace_key: str,
    roi: str,
    point_limit: int,
    normalize: bool,
    normalization_method: str,
    show_spikes: bool,
    start_frame: int,
    highpass_cutoff_hz: float,
    offset: float,
) -> dict[str, Any]:
    trace_type = get_trace_type(trace_key)
    csvs = find_csvs(experiment_path / trace_type.relative_dir)
    if not csvs:
        raise ValueError(f"No CSV traces found for {trace_type.label}")

    csv_path = csvs[0]
    total_columns = count_columns(csv_path)
    usecols = parse_trace_selection(roi, total_columns)
    start_frame = max(start_frame, 0)
    highpass_cutoff_hz = max(float(highpass_cutoff_hz), 0.0)
    cached = get_cached_frame(csv_path, start_frame, highpass_cutoff_hz, usecols)
    cache_hit = cached is not None
    if cached is None:
        frame = pd.read_csv(csv_path, header=None, usecols=usecols)
        original_points = len(frame)
        hp_frame = highpass_frame(frame, highpass_cutoff_hz)
        if start_frame > 0:
            frame = frame.iloc[start_frame:, :]
            hp_frame = hp_frame.iloc[start_frame:, :]
        store_cached_frame(csv_path, start_frame, highpass_cutoff_hz, usecols, frame, hp_frame, original_points)
    else:
        frame, hp_frame, original_points = cached

    display_point_limit = 0 if len(usecols) == 1 else point_limit
    display_frame = decimate_frame(frame, display_point_limit)
    display_hp_frame = hp_frame.loc[display_frame.index, :]
    x = display_frame.index.to_numpy(dtype=float).tolist()
    x_values = frame.index.to_numpy(dtype=float)
    spikes_match_displayed_trace = trace_key == "mcsf"
    detected_peaks = load_detected_peaks(experiment_path) if show_spikes and spikes_match_displayed_trace else {}
    traces = []
    hp_traces = []
    spike_traces = []
    summaries = []
    for order, column in enumerate(usecols):
        full_values = frame[column].to_numpy(dtype=float)
        full_hp_values = hp_frame[column].to_numpy(dtype=float)
        full_y_values = normalize_values(full_values, normalization_method) if normalize else full_values
        full_hp_y_values = normalize_values(full_hp_values, normalization_method) if normalize else full_hp_values
        full_y_series = pd.Series(full_y_values, index=frame.index)
        full_hp_y_series = pd.Series(full_hp_y_values, index=hp_frame.index)
        y_values = full_y_series.loc[display_frame.index].to_numpy(dtype=float)
        hp_y_values = full_hp_y_series.loc[display_hp_frame.index].to_numpy(dtype=float)
        if offset:
            y_values = y_values + order * offset
            hp_y_values = hp_y_values + order * offset
        cell_id = column + 1
        traces.append({"name": f"Cell {cell_id}", "y": y_values.tolist()})
        hp_traces.append({"name": f"Cell {cell_id} HP", "y": hp_y_values.tolist()})

        peaks = detected_peaks.get(column)
        if peaks is not None and len(peaks):
            visible = peaks[(peaks >= x_values[0]) & (peaks <= x_values[-1])]
            if len(visible):
                spike_y = full_y_series.loc[visible].to_numpy(dtype=float)
                spike_hp_y = full_hp_y_series.loc[visible].to_numpy(dtype=float)
                if offset:
                    spike_y = spike_y + order * offset
                    spike_hp_y = spike_hp_y + order * offset
                spike_traces.append(
                    {
                        "name": f"Cell {cell_id} spikes",
                        "roi": column,
                        "cell_id": cell_id,
                        "x": visible.astype(int).tolist(),
                        "y": spike_y.tolist(),
                        "hp_y": spike_hp_y.tolist(),
                    }
                )

        summaries.append(
            {
                "roi": column,
                "mean": float(np.nanmean(full_values)),
                "std": float(np.nanstd(full_values)),
                "min": float(np.nanmin(full_values)),
                "max": float(np.nanmax(full_values)),
            }
        )

    return {
        "file": str(csv_path),
        "trace_type": trace_type.label,
        "total_columns": total_columns,
        "selected_columns": usecols,
        "selected_cell_ids": [column + 1 for column in usecols],
        "original_points": original_points,
        "frames_skipped": 0,
        "start_frame": start_frame,
        "plotted_points": len(display_frame),
        "display_point_limit": display_point_limit,
        "cache_hit": cache_hit,
        "normalized": normalize,
        "normalization_method": normalization_method if normalize else None,
        "highpass_cutoff_hz": highpass_cutoff_hz,
        "spikes_available": has_spike_file(experiment_path),
        "spikes_source_trace_type": "mcsf",
        "spikes_match_displayed_trace": spikes_match_displayed_trace,
        "x": x,
        "traces": traces,
        "highpass_traces": hp_traces,
        "spikes": spike_traces,
        "summaries": summaries,
    }
