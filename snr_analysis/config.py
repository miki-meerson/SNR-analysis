from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = PROJECT_DIR / "static"
DEFAULT_DATA_ROOT = Path(r"Z:\Adam-Lab-Shared\Data\Rotem_Imaging_Data")
DEFAULT_EXPERIMENT = (
    DEFAULT_DATA_ROOT
    / "pAce57"
    / "R1"
    / "2026-07-14-pAce57_R1-S1"
    / "FOV1"
    / "10min-60mw"
)
PLOT_POINT_LIMIT = 6000
DEFAULT_NORMALIZATION_METHOD = "min_max"
DEFAULT_SAMPLING_HZ = 500.0
DEFAULT_HIGHPASS_CUTOFF_HZ = 100.0
DEFAULT_SNR_PADDING_BEFORE = 2
DEFAULT_SNR_PADDING_AFTER = 2
DEFAULT_SNR_BIN_SECONDS = 10.0


@dataclass(frozen=True)
class TraceType:
    key: str
    label: str
    relative_dir: Path


TRACE_TYPES = (
    TraceType("raw", "Raw", Path("traces")),
    TraceType("mc", "Motion corrected", Path("pipeline_results") / "motion_corrected" / "traces"),
    TraceType(
        "mcsf",
        "Motion corrected + spatial footprint",
        Path("pipeline_results") / "motion_corrected" / "spatial_footprint_traces",
    ),
)
