from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from ..config import DEFAULT_HIGHPASS_CUTOFF_HZ, DEFAULT_SAMPLING_HZ, DEFAULT_SNR_BIN_SECONDS
from ..filters import highpass_frame
from ..spikes import has_spike_file, load_detected_peaks
from ..traces import count_columns, find_csvs, get_trace_type, parse_trace_selection
from .basic import basic_snr


SNRMethod = Callable[[np.ndarray, np.ndarray, int, int], Any]

SNR_METHODS: dict[str, dict[str, Any]] = {
    "basic": {
        "label": "Basic",
        "description": "Average spike height divided by the standard deviation of non-spike frames.",
        "function": basic_snr,
    }
}

SIGNAL_SOURCES = {
    "trace": "Regular trace",
    "highpass": "High-pass trace",
    "both": "Regular + high-pass",
}


def get_snr_methods() -> list[dict[str, str]]:
    return [
        {"key": key, "label": str(item["label"]), "description": str(item["description"])}
        for key, item in SNR_METHODS.items()
    ]


def _clean_float(value: float | None) -> float | None:
    if value is None or not np.isfinite(value):
        return None
    return float(value)


def _result_payload(result: Any) -> dict[str, Any]:
    return {
        "snr": _clean_float(result.snr),
        "average_spike_height": _clean_float(result.average_spike_height),
        "noise_std": _clean_float(result.noise_std),
        "spike_count": result.spike_count,
        "noise_frame_count": result.noise_frame_count,
    }


def _summarize_snr(results: list[dict[str, Any]]) -> dict[str, Any]:
    valid_snr = [item["snr"] for item in results if item["snr"] is not None]
    return {
        "cells": len(results),
        "valid_cells": len(valid_snr),
        "mean_snr": _clean_float(float(np.nanmean(valid_snr))) if valid_snr else None,
        "median_snr": _clean_float(float(np.nanmedian(valid_snr))) if valid_snr else None,
    }


def _time_bins(frame_count: int, bin_frames: int, start_frame: int, sampling_hz: float) -> list[dict[str, Any]]:
    bins = []
    for bin_index, local_start in enumerate(range(0, frame_count, bin_frames)):
        local_stop = min(local_start + bin_frames, frame_count)
        absolute_start = start_frame + local_start
        absolute_stop = start_frame + local_stop
        bins.append(
            {
                "bin_index": bin_index,
                "local_start": local_start,
                "local_stop": local_stop,
                "start_frame": absolute_start,
                "end_frame": absolute_stop - 1,
                "start_seconds": absolute_start / sampling_hz,
                "end_seconds": (absolute_stop - 1) / sampling_hz,
                "center_seconds": (absolute_start + absolute_stop - 1) / (2 * sampling_hz),
            }
        )
    return bins


def _calculate_for_signal(
    frame: pd.DataFrame,
    peaks_by_roi: dict[int, np.ndarray],
    usecols: list[int],
    signal_source: str,
    highpass_cutoff_hz: float,
    function: SNRMethod,
    padding_before: int,
    padding_after: int,
    start_frame: int,
    bins: list[dict[str, Any]],
) -> dict[str, Any]:
    signal_frame = highpass_frame(frame, highpass_cutoff_hz) if signal_source == "highpass" else frame
    signal_frame = signal_frame.iloc[start_frame:, :]
    results = []
    binned_results_by_cell = []

    for column in usecols:
        absolute_peaks = peaks_by_roi.get(column, np.asarray([], dtype=int))
        absolute_peaks = absolute_peaks[absolute_peaks >= start_frame]
        local_peaks = absolute_peaks - start_frame
        result = function(
            signal_frame[column].to_numpy(dtype=float),
            local_peaks,
            padding_before,
            padding_after,
        )
        cell_result = {"roi": column, "cell_id": column + 1, **_result_payload(result)}
        results.append(cell_result)

        bin_points = []
        values = signal_frame[column].to_numpy(dtype=float)
        for item in bins:
            local_start = item["local_start"]
            local_stop = item["local_stop"]
            bin_peaks = local_peaks[(local_peaks >= local_start) & (local_peaks < local_stop)] - local_start
            bin_result = function(values[local_start:local_stop], bin_peaks, padding_before, padding_after)
            bin_points.append({key: value for key, value in item.items() if not key.startswith("local_")} | _result_payload(bin_result))
        binned_results_by_cell.append({"roi": column, "cell_id": column + 1, "bins": bin_points})

    time_summary = []
    for item in bins:
        bin_index = item["bin_index"]
        bin_results = [
            cell["bins"][bin_index]["snr"]
            for cell in binned_results_by_cell
            if cell["bins"][bin_index]["snr"] is not None
        ]
        time_summary.append(
            {
                key: value for key, value in item.items() if not key.startswith("local_")
            }
            | {
                "valid_cells": len(bin_results),
                "mean_snr": _clean_float(float(np.nanmean(bin_results))) if bin_results else None,
                "median_snr": _clean_float(float(np.nanmedian(bin_results))) if bin_results else None,
            }
        )

    return {
        "signal_source": signal_source,
        "signal_source_label": SIGNAL_SOURCES[signal_source],
        "results": results,
        "summary": _summarize_snr(results),
        "binned_results": binned_results_by_cell,
        "time_summary": time_summary,
    }


def calculate_snr_payload(
    experiment_path: Path,
    trace_key: str,
    roi: str,
    method_key: str = "basic",
    signal_source: str = "highpass",
    highpass_cutoff_hz: float = DEFAULT_HIGHPASS_CUTOFF_HZ,
    padding_before: int = 2,
    padding_after: int = 2,
    start_frame: int = 0,
    bin_seconds: float = DEFAULT_SNR_BIN_SECONDS,
    sampling_hz: float = DEFAULT_SAMPLING_HZ,
) -> dict[str, Any]:
    trace_type = get_trace_type(trace_key)
    method = SNR_METHODS.get(method_key)
    if method is None:
        raise ValueError(f"Unknown SNR method: {method_key}")
    if signal_source not in SIGNAL_SOURCES:
        raise ValueError(f"Unknown SNR signal source: {signal_source}")

    csvs = find_csvs(experiment_path / trace_type.relative_dir)
    if not csvs:
        raise ValueError(f"No CSV traces found for {trace_type.label}")
    if not has_spike_file(experiment_path):
        raise ValueError("No detected peaks file found for this experiment")

    csv_path = csvs[0]
    total_columns = count_columns(csv_path)
    usecols = parse_trace_selection(roi, total_columns)
    frame = pd.read_csv(csv_path, header=None, usecols=usecols)
    original_points = len(frame)
    start_frame = min(max(int(start_frame), 0), original_points)
    peaks_by_roi = load_detected_peaks(experiment_path)
    function: SNRMethod = method["function"]
    padding_before = max(int(padding_before), 0)
    padding_after = max(int(padding_after), 0)
    bin_seconds = max(float(bin_seconds), 0.001)
    sampling_hz = float(sampling_hz)
    bin_frames = max(int(round(bin_seconds * sampling_hz)), 1)
    analyzed_points = original_points - start_frame
    bins = _time_bins(analyzed_points, bin_frames, start_frame, sampling_hz)
    requested_sources = ["trace", "highpass"] if signal_source == "both" else [signal_source]
    signal_results = {
        source: _calculate_for_signal(
            frame,
            peaks_by_roi,
            usecols,
            source,
            highpass_cutoff_hz,
            function,
            padding_before,
            padding_after,
            start_frame,
            bins,
        )
        for source in requested_sources
    }
    primary_source = "highpass" if "highpass" in signal_results else requested_sources[0]
    primary = signal_results[primary_source]

    return {
        "experiment_path": str(experiment_path),
        "file": str(csv_path),
        "trace_type": trace_type.label,
        "trace_key": trace_key,
        "method": method_key,
        "method_label": method["label"],
        "signal_source": signal_source,
        "signal_source_label": SIGNAL_SOURCES[signal_source],
        "highpass_cutoff_hz": float(highpass_cutoff_hz),
        "padding_before": padding_before,
        "padding_after": padding_after,
        "start_frame": start_frame,
        "analyzed_points": analyzed_points,
        "original_points": original_points,
        "sampling_hz": sampling_hz,
        "bin_seconds": bin_seconds,
        "bin_frames": bin_frames,
        "total_columns": total_columns,
        "selected_columns": usecols,
        "selected_cell_ids": [column + 1 for column in usecols],
        "results": primary["results"],
        "summary": primary["summary"],
        "binned_results": primary["binned_results"],
        "time_summary": primary["time_summary"],
        "signal_results": signal_results,
    }
