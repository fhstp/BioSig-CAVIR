# Metrics Documentation

This folder contains detailed documentation for all metrics computed by the processing pipeline.

---

## Available Documentation

### [Eye Tracking Metrics](eye_tracking_metrics.md)
Complete reference for all eye tracking metrics including:
- Fixation metrics (count, rate, duration)
- Saccade metrics (count, rate, duration)
- Pupil diameter metrics
- Blink metrics
- Device validation metrics

### [ECG Metrics](ecg_metrics.md)
Heart rate variability and cardiac metrics including:
- HRV time-domain metrics (RMSSD, SDNN, pNN50)
- Data quality metrics
- Input mode handling (raw ECG, RRI, BPM)

### [GSR Metrics](gsr_metrics.md)
Galvanic skin response metrics including:
- Tonic (baseline) metrics (mean_baseline, std_baseline)
- Phasic (response) metrics (mean_phasic, max_phasic, phasic_count)

### [Head Movement Metrics](head_movement_metrics.md)
Head position and rotation metrics including:
- Velocity metrics (linear and angular)
- Movement characterization (intensity, frequency, range)
- Stability metrics (positional stability, rotation smoothness)

### [EEG Metrics](eeg_metrics.md)
EEG band-power and cognitive load metrics including:
- Theta/alpha index (cognitive load indicator)
- Frontal theta and parietal alpha band power
- Baseline-normalised z-score (`z_idx_vs_baseline`)
- Quality filtering and QC statistics

---

## Metric Categories

Each modality documentation includes:
- **Metric name** and type
- **Description** of what it measures
- **Units** of measurement
- **Examples** with typical values
- **Calculation methods** and algorithms used
- **Notes** about data availability and quality

---

## Conventions

### Naming Conventions
- **Counts** end in `_count` (e.g., `fixation_count`)
- **Rates** end in `_rate_per_s` (e.g., `fixation_rate_per_s`)
- **Durations** end in `_ms` or `_s` (e.g., `avg_fixation_duration_ms`)
- **Proportions/Fractions** end in `_fraction` or `_prop` (e.g., `fixation_time_fraction`)
- **Statistical measures** use standard prefixes: `avg_`, `std_`, `min_`, `max_`, `median_`

### Units
- Time: seconds (s) or milliseconds (ms)
- Rates: events per second (e.g., fixations/second)
- Proportions: 0.0 to 1.0 (not percentages)
- Physiological: standard units (mm for pupil, bpm for heart rate, etc.)

### Missing Data
- Metrics that cannot be computed are omitted or contain `None`/`NaN`
- `_notes` fields explain why data is missing
- Device-specific metrics are only present if the device provides them

---

## Output Files

Metrics are saved in the following structure:

```
results/
└── <run_timestamp>/
    └── <participant_id>/
        └── <task_name>/
            └── <modality>/
                ├── features.csv        # All metrics for this task
                ├── meta.json          # Processing parameters and QC info
                └── *_clean.csv        # Cleaned raw data
```

For cross-task summaries, see:
```
results/
└── <run_timestamp>/
    └── _summaries/
        └── <modality>/
            └── features_by_task.csv   # All participants × tasks
```

---

## Version Information

This documentation reflects the current state of the processing pipeline as of **May 11, 2026**.

For changes and updates, see the **Version History** section in each individual modality documentation file.

### Maintaining Documentation

**Important:** When adding or modifying metrics, always:
1. Update the metric entry in the relevant `<modality>_metrics.md` file
2. Add an entry to the **Version History** section at the bottom
3. Include date, version number, and description of changes

See [`docs/development/ADDING_METRICS.md`](../development/ADDING_METRICS.md) for detailed guidelines.
