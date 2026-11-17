# Pipeline Config Reference

Audience: users writing or editing the run config passed to `run_pipeline`.

This document describes the top-level config keys and the main modality params used in the current code.

## Top-level config keys

Required keys:

- `participants`: list of participant folder names (strings), or a dict `{cohort_name: [participant, ...]}`.
  With the dict form, each participant gets its cohort name in a `cohort` column of
  `_summaries/summary_all_modalities.csv`, and the mapping is stored under `cohorts` in the run metadata.
  A participant may only appear in one cohort.

  ```
  "participants": {
    "data_acquisition_2024": ["1c9042c3-...", "252f4485-..."],
    "data_acquisition_2025": ["3881219c-...", "9101207d-..."],
  }
  ```
- `tasks`: list of task names (strings).
- `metrics`: dict of modality -> list of metric names. If a list is empty, that modality is skipped.
- `params`: dict of modality -> param dict. Each modality reads its own keys.

Optional keys:

- `input_path`: root folder with participant subfolders. Default: `"data"`.
- `output_path`: base folder for results. Default: `"results"`.
- `label`: optional run label, appended to the run folder name.
- `file_structure`: output directory structure key (e.g. `"PTM"`).

## Example config (minimal)

```
run_cfg = {
  "participants": ["01", "02"],
  "tasks": ["TaskA", "TaskB"],
  "metrics": {
    "ecg": ["RMSSD", "SDNN"],
    "gsr": ["mean_baseline"],
    "eye_tracking": ["fixation_count"],
    "head_movement": ["mean_velocity"],
    "eeg": ["idx_mean", "idx_std"],
  },
  "params": {
    "ecg": {"hr_outlier_range_bpm": [40, 200], "sampling_rate_hz": 250},
    "gsr": {"baseline_col": "GSR_CONDUCTANCE"},
    "et":  {"sampling_rate_hz": 120},
    "head_movement": {"sampling_rate_hz": 120},
    "eeg": {"min_cq": 2.0},
  },
  "input_path": "data",
  "output_path": "results",
  "file_structure": "PTM",
  "label": "pilot",
}
```

## Modality params (used by current pipelines)

### ECG (`cfg["params"]["ecg"]`)

- `hr_outlier_range_bpm` (list[int, int]): used for BPM detection and outlier handling.
- `sampling_rate_hz` (float): fallback sampling rate for raw ECG.
- `bandpass_hz` (tuple[float, float]): bandpass filter for peak detection.
- `polar_ticks_hz` (float): conversion factor for Polar tick RRI.
- `rri_artifact_correction` (`"kubios"` | `"none"`): artifact flagging for RRI files.
- `coverage_max_gap_s` (float): intervals between ECG rows longer than this count as missing data
  in the coverage. Default: `3.0` (Polar via iMotions delivers about one row per second).

### GSR (`cfg["params"]["gsr"]`)

- `baseline_col` (str): name of the conductance column. Default `GSR_CONDUCTANCE`.
- `min_deviation` (float): minimum phasic deviation threshold (uS).
- `max_deviation` (float): maximum phasic deviation threshold (uS).
- `deviation_bins` (list[float]): bin edges for categorization.
- `deviation_categories` (list[str]): labels for bins.

### Eye-tracking (`cfg["params"]["et"]`)

- `tracker_rate_hz` (float, default `60`): eye-tracker sampling rate. The headsets deliver
  one row per rendered frame (72 or 90 Hz) and repeat the previous sample to fill the gaps;
  repeats are removed and samples placed on a regular grid at this rate
  (`modules/eyetracking/resample.py`). Blinks, validity, I-VT and all metrics run on that grid.
  Set to `None` to keep the delivered rows (then the rate is estimated from the timestamps).
- `sampling_rate_hz` (float): fallback only, used when `tracker_rate_hz` is `None` and no
  rate can be estimated. Segments with an implausible timestamp rate (outside 30-500 Hz) or
  > 5% non-increasing timestamps are rejected.
- I-VT uses the angular gaze velocity computed from the gaze direction vectors
  (`vel_calc`, binocular mean); the device velocity columns are kept for comparison only.

I-VT segmentation parameters must be nested under a `"segmentation"` sub-dict:

```python
"et": {
    "sampling_rate_hz": 120,
    "segmentation": {
        "velocity_threshold_deg_s": 30,
        "min_fixation_duration_ms": 60,
        "min_saccade_duration_ms": 22,
        "smooth_win_ms": 0,
        "merge_fix_gap_ms": 0,
    }
}
```

| Key (under `segmentation`) | Default | Description |
|----------------------------|---------|-------------|
| `velocity_threshold_deg_s` | `30` | Saccade velocity threshold for I-VT (°/s) |
| `min_fixation_duration_ms` | `60` | Minimum fixation duration to keep |
| `min_saccade_duration_ms` | `22` | Minimum saccade duration to keep |
| `smooth_win_ms` | `0` | Velocity smoothing window (0 = disabled) |
| `merge_fix_gap_ms` | `0` | Merge fixations separated by ≤ this gap (0 = disabled) |

Blink detection parameters go under an optional `"blinks"` sub-dict. The VR devices do not report blinks; they are derived from runs where **both** eyes have pupil diameter 0 and a zero gaze vector. Runs touching the start/end of a recording are ignored. If the input already contains a `blink` column, it is kept and detection is skipped.

| Key (under `blinks`) | Default | Description |
|----------------------|---------|-------------|
| `enabled` | `true` | Derive the `blink` column from bilateral signal loss |
| `min_duration_ms` | `50` | Shorter loss runs are treated as noise |
| `max_duration_ms` | `500` | Longer loss runs are track loss, not blinks |

### EEG (`cfg["params"]["eeg"]`)

See [docs/metrics/eeg_metrics.md](metrics/eeg_metrics.md) for the full parameter table. Key parameters:

- `frontal_channels` (list[str]): channels used for theta power. Default: `["AF3","F7","F3","F4","F8","AF4"]`.
- `parietal_channels` (list[str]): channels used for alpha power. Default: `["P7","P8"]`.
- `pow_prefix` (str): column prefix for band-power values. Default: `"POW."`.
- `min_cq` (float): minimum contact quality per channel. Default: `2.0`.
- `apply_quality_filter` (bool): enable/disable CQ filtering. Default: `true`.
- `baseline_tasks` (list[str]): tasks to use as participant baseline for z-scoring. Default: `[]`.
- `input_format` (str): `"preparsed"` (DataPreParser `*_EEGEmotiv_preparsed.csv`, comma separated)
  or `"emotiv_raw"` (Emotiv export split per task, `;` separated, title line). Default: `"preparsed"`.
- `compute_features` (bool): compute CQ filter and theta/alpha features. Default: `false` for
  `"preparsed"` (the preparser header does not match the row values, only `Timestamp` is reliable),
  `true` for `"emotiv_raw"`. With `false`, only `meta.json` with the coverage `qc` block is written.
- `coverage_max_gap_s` (float): intervals between EEG rows longer than this count as missing data
  in the coverage. Default: `0.5` (band-power rows at 8 Hz).

### Head movement (`cfg["params"]["head_movement"]`)

- `sampling_rate_hz` (float): sampling rate used for feature windows.
- `velocity_threshold` (float): velocity threshold for movement events.
- `position_smoothing_window` (int): smoothing window (samples).

### Data-quality summary (`cfg["params"]["qc"]`, optional)

| Key | Default | Description |
|-----|---------|-------------|
| `enabled` | `true` | Write `_summaries/qc/` at the end of the run |
| `thresholds` | see below | Per-modality overrides, e.g. `{"ecg": {"max_artifact_frac": 0.1}}` |
| `expected_modalities` | `None` | `{cohort: [modalities]}` recorded by design. Without it, a cohort with no data at all for a modality counts as `not_recorded` |

Default thresholds (`modules/qc/qc_summary.py`, `DEFAULT_THRESHOLDS`):

| Modality | Key | Default |
|----------|-----|---------|
| eye_tracking | `max_track_loss` | `0.25` (share of samples, blinks excluded) |
| eeg | `min_coverage` | `0.8` (time covered by EEG rows / task duration) |
| ecg | `max_artifact_frac` | `0.05` (Kubios-flagged beats) |
| ecg | `min_valid_duration_s` | `30` |
| ecg | `min_coverage` | `0.8` (time covered by ECG rows / task duration) |
| gsr | `max_out_of_range_frac` | `0.05` |
| gsr | `max_steep_slope_frac` | `0.05` |
| gsr | `min_coverage` | `0.8` |
| gsr | `low_variability_range_us` | `0.05` (flag only) |

## Metrics selection

Metrics are requested via `cfg["metrics"]`. If a modality list is empty, that modality is skipped entirely.

Example:

```
metrics = {
  "ecg": ["RMSSD", "SDNN", "pNN50"],
  "gsr": ["mean_baseline"],
  "eye_tracking": ["fixation_count", "blink_rate_per_s"],
  "head_movement": ["mean_velocity"],
}
```

### Available GSR metrics

| Config string    | What it measures                      |
|------------------|---------------------------------------|
| `mean_baseline`  | Mean tonic skin conductance level     |
| `std_baseline`   | Variability of tonic conductance      |
| `mean_phasic`    | Average phasic response amplitude     |
| `max_phasic`     | Peak phasic response amplitude        |
| `phasic_count`   | Number of phasic events detected      |

Full descriptions, units, and configuration options: [docs/metrics/gsr_metrics.md](metrics/gsr_metrics.md)

### Available EEG metrics

| Config string | What it measures |
|---|---|
| `theta_frontal_mean` | Mean frontal theta band power |
| `theta_frontal_std` | Variability of frontal theta |
| `alpha_parietal_mean` | Mean parietal alpha band power |
| `alpha_parietal_std` | Variability of parietal alpha |
| `idx_mean` | Mean theta/alpha index (cognitive load) |
| `idx_std` | Variability of theta/alpha index |
| `n_samples` | Sample count after quality filtering |

Full descriptions, units, and config options: [docs/metrics/eeg_metrics.md](metrics/eeg_metrics.md)

### Available ECG / eye-tracking metrics

See the dedicated metric reference files in [docs/metrics/](metrics/README.md).
