# SNR Analysis

A local Python app for browsing imaging experiment folders, detecting available trace types, and visualizing ROI traces.

## Trace Layout

Given an experiment folder, the app looks for:

- Raw traces: `traces/*.csv`
- Motion corrected traces: `pipeline_results/motion_corrected/traces/*.csv`
- Motion corrected + spatial footprint traces: `pipeline_results/motion_corrected/spatial_footprint_traces/*.csv`

The observed CSV format is headerless, with time samples in rows and ROI traces in columns.

## Run

```powershell
python app.py
```

Then open:

```text
http://127.0.0.1:8057
```

Browse through the folder tree. When the current folder is an experiment folder, the app automatically loads the available trace types.
