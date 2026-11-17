# GSR Metrics Documentation

This document describes all metrics computed by the GSR pipeline.

---

## Overview

The GSR (Galvanic Skin Response) pipeline computes metrics from skin conductance signals. GSR reflects sympathetic nervous system activity and is commonly used as a measure of arousal and emotional responses.

The pipeline separates the signal into two components:
- **Tonic (baseline):** The slow-changing background conductance level
- **Phasic (responses):** Short-lived increases above the baseline, indicating discrete arousal responses

---

## Tonic (Baseline) Metrics

### `mean_baseline`
**Type:** Float  
**Description:** Mean skin conductance level across the entire recording. Reflects the overall tonic arousal state during the task. Higher values indicate greater sympathetic activation.  
**Units:** microsiemens (µS)

### `std_baseline`
**Type:** Float  
**Description:** Standard deviation of the skin conductance baseline. Reflects how much the tonic level fluctuates over time. Higher values suggest more variable arousal.  
**Units:** microsiemens (µS)

---

## Phasic (Response) Metrics

### `mean_phasic`
**Type:** Float  
**Description:** Mean amplitude of phasic responses (conductance deviations above the tonic baseline). Reflects the average strength of discrete arousal events.  
**Units:** microsiemens (µS)

### `max_phasic`
**Type:** Float  
**Description:** Maximum phasic response amplitude observed during the task. Reflects the peak arousal event.  
**Units:** microsiemens (µS)

### `phasic_count`
**Type:** Integer  
**Description:** Number of phasic response events detected above the minimum deviation threshold. Reflects how frequently arousal events occurred during the task.  
**Units:** count

---

## Configuration

GSR metrics require a `"gsr"` entry in `cfg["params"]`:

```python
cfg["params"]["gsr"] = {
    "baseline_col":        "GSR_CONDUCTANCE",  # column name in the input CSV
    "min_deviation":       0.1,                # µS — minimum threshold to count as phasic event
    "max_deviation":       3.0,                # µS — upper clamp for phasic responses
    "deviation_bins":      [0, 0.5, 1.0, 2.0, 3.0, 10],
    "deviation_categories": ["Very Low", "Low", "High", "Very High", "Extremely High"],
}
```

Minimal required entry (all other params use defaults):

```python
cfg["params"]["gsr"] = {"baseline_col": "GSR_CONDUCTANCE"}
```

---

## Metric Names Reference

| Config string      | What it measures                        |
|--------------------|-----------------------------------------|
| `mean_baseline`    | Mean tonic conductance level            |
| `std_baseline`     | Variability of tonic conductance        |
| `mean_phasic`      | Average phasic response amplitude       |
| `max_phasic`       | Peak phasic response amplitude          |
| `phasic_count`     | Number of phasic events                 |

Metric names are **case-insensitive** (`"MEAN_BASELINE"` and `"mean_baseline"` both work).

---

## Output Files

Per participant/task under the run root:

- `gsr/gsr_clean.csv` — cleaned conductance data with deviation column added
- `gsr/gsr_phasic_responses.csv` — detected phasic events with categories
- `gsr/features.csv` — requested metrics for this participant/task
- `gsr/meta.json` — processing parameters, baseline value, phasic response count
- `gsr/gsr_timeseries_raw.png` — quick-look plot of the raw signal
- `gsr/gsr_processed.png` — processed signal with baseline and phasic responses overlaid
- `gsr/gsr_deviations.png` — phasic deviations over time

---

## Version History

- **v1.0** (2026-04-30): Initial documentation
  - Documented mean_baseline, std_baseline, mean_phasic, max_phasic, phasic_count
  - Described tonic/phasic signal separation
  - Added configuration reference and output file listing
