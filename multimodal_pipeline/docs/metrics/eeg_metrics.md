# EEG Metrics Documentation

This document describes all metrics computed by the EEG pipeline.

---

## Overview

The EEG pipeline processes band-power data from multi-channel EEG devices (e.g. EMOTIV). It computes a **theta/alpha index** — a standard cognitive load indicator — from frontal theta power and parietal alpha power. Samples failing a contact-quality (CQ) check and extreme outliers are removed before metrics are computed.

Default channel groups:
- **Frontal channels:** AF3, F7, F3, F4, F8, AF4
- **Parietal channels:** P7, P8

---

## Sample Count

### `n_samples`
**Type:** Integer  
**Description:** Number of samples remaining after quality filtering and outlier trimming. Serves as a data-quality indicator — a very low count may indicate poor electrode contact or a short recording.  
**Units:** count  
**Always included:** Yes (not gated by the metrics request list).

---

## Theta / Alpha Band Power

### `theta_frontal_mean`
**Type:** Float  
**Description:** Mean frontal theta band power across all retained samples, averaged over the configured frontal channels (default: AF3, F7, F3, F4, F8, AF4). Theta (4–8 Hz) is associated with working memory load and mental effort.  
**Units:** µV² (microvolts squared, device-dependent)

### `theta_frontal_std`
**Type:** Float  
**Description:** Standard deviation of frontal theta power across retained samples. Indicates within-task variability.  
**Units:** µV²

### `alpha_parietal_mean`
**Type:** Float  
**Description:** Mean parietal alpha band power across all retained samples, averaged over the configured parietal channels (default: P7, P8). Alpha (8–13 Hz) is associated with cortical relaxation and disengagement.  
**Units:** µV²

### `alpha_parietal_std`
**Type:** Float  
**Description:** Standard deviation of parietal alpha power across retained samples.  
**Units:** µV²

---

## Theta/Alpha Index

The theta/alpha index is a per-sample composite score:

```
idx_theta_alpha = log10( theta_frontal / (alpha_parietal + ε) )
```

where `ε = 1e-12` prevents division by zero. Higher values indicate higher cognitive load (more theta relative to alpha). The index is computed on the quality-filtered, outlier-trimmed samples.

### `idx_mean`
**Type:** Float  
**Description:** Mean theta/alpha index across all retained samples. This is the primary cognitive load metric. A higher value indicates greater mental engagement.  
**Units:** log10 scale (dimensionless)

### `idx_std`
**Type:** Float  
**Description:** Standard deviation of the theta/alpha index. Indicates variability in cognitive engagement throughout the task.  
**Units:** log10 scale (dimensionless)

---

## Baseline-Normalised Metric (optional)

These columns are added only when `cfg["params"]["eeg"]["baseline_tasks"]` is set to a non-empty list.

### `z_idx_vs_baseline`
**Type:** Float  
**Description:** Z-score of `idx_mean` relative to the participant's own baseline. Computed as:

```
z = (idx_mean − baseline_mean) / baseline_std
```

where `baseline_mean` and `baseline_std` are derived from all retained `idx_theta_alpha` samples across the baseline tasks for that participant. A positive value means higher cognitive load than baseline; a negative value means lower.  
**Units:** standard deviations (dimensionless)  
**Note:** `NaN` if no baseline samples were collected or if baseline standard deviation is zero.

### `baseline_tasks`
**Type:** String  
**Description:** Comma-separated list of task names used as the baseline (e.g. `"RestingState,Calibration"`). Stored for traceability.  
**Note:** Present in the summary row only when `z_idx_vs_baseline` is computed.

---

## Quality Filtering

Before metrics are computed, two filtering stages are applied:

### Contact Quality (CQ) Filter
Samples are retained only when:
- At least `min_good_frontal` (default: 3) frontal channels have `CQ ≥ min_cq` (default: 2.0).
- At least `min_good_parietal` (default: 1) parietal channels have `CQ ≥ min_cq`.
- Optionally (if `use_eq: true`): `EQ.OVERALL ≥ min_eq_fraction × max(EQ.OVERALL)`.

### Outlier Trimming
Samples with `idx_theta_alpha` below the `outlier_lower_q` quantile (default: 1st percentile) or above the `outlier_upper_q` quantile (default: 99th percentile) are removed.

QC statistics for both stages are recorded in `meta.json`.

---

## Config Parameters (`cfg["params"]["eeg"]`)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `frontal_channels` | `["AF3","F7","F3","F4","F8","AF4"]` | Channels used for theta |
| `parietal_channels` | `["P7","P8"]` | Channels used for alpha |
| `pow_prefix` | `"POW."` | Column prefix for band-power values |
| `apply_quality_filter` | `true` | Enable/disable CQ filtering |
| `cq_prefix` | `"CQ."` | Column prefix for contact-quality values |
| `eq_overall_col` | `"EQ.OVERALL"` | Column name for overall EEG quality |
| `use_eq` | `false` | Whether to use EQ.OVERALL as an additional filter |
| `min_eq_fraction` | `0.5` | Minimum EQ fraction of max EQ |
| `min_cq` | `2.0` | Minimum acceptable CQ value per channel |
| `min_good_frontal` | `3` | Min frontal channels that must pass CQ |
| `min_good_parietal` | `1` | Min parietal channels that must pass CQ |
| `outlier_lower_q` | `0.01` | Lower quantile for outlier removal |
| `outlier_upper_q` | `0.99` | Upper quantile for outlier removal |
| `baseline_tasks` | `[]` | Task names to use as participant baseline |
| `file_pattern` | `"*{task}*{modality}*"` | Glob pattern for locating input files |

---

## Output Files

| File | Contents |
|------|----------|
| `eeg/eeg_clean.csv` | Quality-filtered, outlier-trimmed samples with `theta_frontal`, `alpha_parietal`, `idx_theta_alpha` columns |
| `eeg/features.csv` | Requested metrics for this participant/task |
| `eeg/meta.json` | Processing parameters, row counts, quality filter stats |
| `_summaries/eeg/features_by_task.csv` | All participants × tasks in one file |

---

## Example Config

```python
cfg = {
    "metrics": {
        "eeg": ["theta_frontal_mean", "alpha_parietal_mean", "idx_mean", "idx_std"],
    },
    "params": {
        "eeg": {
            "frontal_channels": ["AF3", "F7", "F3", "F4", "F8", "AF4"],
            "parietal_channels": ["P7", "P8"],
            "min_cq": 2.0,
            "baseline_tasks": ["RestingState"],
        }
    },
}
```

---

## Version History

| Date | Change |
|------|--------|
| 2026-05-11 | Initial documentation added |
