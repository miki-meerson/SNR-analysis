from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class BasicSNRResult:
    snr: float | None
    average_spike_height: float | None
    noise_std: float | None
    spike_count: int
    noise_frame_count: int


def basic_snr(
    values: np.ndarray,
    spike_frames: np.ndarray,
    padding_before: int = 2,
    padding_after: int = 2,
) -> BasicSNRResult:
    values = np.asarray(values, dtype=float)
    spike_frames = np.asarray(spike_frames, dtype=int)
    spike_frames = np.unique(spike_frames[(spike_frames >= 0) & (spike_frames < len(values))])
    padding_before = max(int(padding_before), 0)
    padding_after = max(int(padding_after), 0)

    if len(values) == 0 or len(spike_frames) == 0:
        return BasicSNRResult(None, None, None, int(len(spike_frames)), 0)

    noise_mask = np.ones(len(values), dtype=bool)
    for peak in spike_frames:
        start = max(int(peak) - padding_before, 0)
        stop = min(int(peak) + padding_after + 1, len(values))
        noise_mask[start:stop] = False

    spike_values = values[spike_frames]
    noise_values = values[noise_mask]
    finite_spikes = spike_values[np.isfinite(spike_values)]
    finite_noise = noise_values[np.isfinite(noise_values)]

    if len(finite_spikes) == 0 or len(finite_noise) < 2:
        return BasicSNRResult(None, None, None, int(len(spike_frames)), int(len(finite_noise)))

    average_spike_height = float(np.nanmean(finite_spikes))
    noise_std = float(np.nanstd(finite_noise))
    snr = None if noise_std == 0 else average_spike_height / noise_std
    return BasicSNRResult(
        float(snr) if snr is not None else None,
        average_spike_height,
        noise_std,
        int(len(spike_frames)),
        int(len(finite_noise)),
    )
