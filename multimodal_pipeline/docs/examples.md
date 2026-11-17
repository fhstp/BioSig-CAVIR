# Examples and Quickstart

Audience: users running the pipeline for the first time.

## Minimal run

```
from modules.pipeline import run_pipeline

cfg = {
  "participants": ["01"],
  "tasks": ["TaskA"],
  "metrics": {
    "ecg": ["RMSSD"],
    "gsr": ["mean_baseline"],
    "eye_tracking": ["fixation_count"],
    "head_movement": ["mean_velocity"],
  },
  "params": {
    "ecg": {"hr_outlier_range_bpm": [40, 200], "sampling_rate_hz": 250},
    "gsr": {"baseline_col": "GSR_CONDUCTANCE"},
    "et":  {"sampling_rate_hz": 120},
    "head_movement": {"sampling_rate_hz": 120},
  },
  
  "input_path": "data",
  "output_path": "results",
  "file_structure": "PTM",
  "label": "demo",
}

summary = run_pipeline(cfg)
print(summary.head())
```

## Run a subset of modalities

If a modality list is empty, it is skipped:

```
cfg["metrics"] = {
  "ecg": ["RMSSD", "SDNN"],
  "gsr": [],
  "eye_tracking": [],
  "head_movement": [],
}
```

## Example input files

See `docs/input_data_schema.md` for minimal CSV examples per modality.

## Where outputs go

See `docs/output_schema.md` for the run folder layout and outputs per modality.
