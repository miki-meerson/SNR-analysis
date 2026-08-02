from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import signal


DEFAULT_SAMPLING_HZ = 500.0
DEFAULT_HIGHPASS_CUTOFF_HZ = 100.0
HIGHPASS_FILTER_ORDER = 3


def highpass_frame(
    frame: pd.DataFrame,
    cutoff_hz: float = DEFAULT_HIGHPASS_CUTOFF_HZ,
    sampling_hz: float = DEFAULT_SAMPLING_HZ,
) -> pd.DataFrame:
    cutoff_hz = max(float(cutoff_hz), 0.0)
    nyquist_hz = sampling_hz / 2.0
    if cutoff_hz <= 0 or cutoff_hz >= nyquist_hz:
        return frame - frame.mean(axis=0)

    sos = signal.butter(
        HIGHPASS_FILTER_ORDER,
        cutoff_hz,
        btype="highpass",
        fs=sampling_hz,
        output="sos",
    )
    values = frame.to_numpy(dtype=float)
    filtered = signal.sosfiltfilt(sos, values, axis=0)
    return pd.DataFrame(filtered, index=frame.index, columns=frame.columns)
