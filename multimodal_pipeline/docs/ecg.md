# ECG / HRV Pipeline

Audience: future collaborators and users who need to understand inputs, configuration, and outputs for the ECG pipeline.

## Inputs
- Source files live under `data/{participant}/*{task}*_preparsed.csv` as assumed by `run_pipeline`.
- Input modes (auto-detected by `detect_ecg_input_mode`):
  - Raw ECG with a heart-signal column (e.g., `HR`); treated as `raw_ecg`.
  - R-R intervals (`rr_ms`, `RRI`, or `RR`) in milliseconds or Polar ticks; treated as `rri`.
  - BPM-only streams; treated as `bpm` (metrics are skipped).
- Expected columns by mode:
  - `raw_ecg`: a numeric ECG signal column; an optional `Timestamp` column is plotted but peak detection currently runs on the signal only.
  - `rri`: `RRI`/`rr_ms`; optional `Timestamp` helps with plotting.
  - `bpm`: `HR` in beats per minute.

## Key config knobs (cfg['params']['ecg'])
- `hr_outlier_range_bpm` (list[int, int]): range used for outlier and BPM-mode detection.
- `sampling_rate_hz` (float | null): fallback sampling rate for raw ECG when timestamps are missing.
- `bandpass_hz` (tuple[float, float], default `(0.5, 35.0)`): bandpass for R-peak detection. **Note:** the same default applies to `meta.json`; if `bandpass_hz` is set explicitly in config, the stored value will match the processing default.
- `polar_ticks_hz` (float, default 1024.0): conversion factor when RRI comes in Polar ticks.

## Processing flow (per participant, per task)
1. Load input via `load_data_file`.
2. Detect input mode: `rri` → units detection; `raw_ecg` → peak detection; `bpm` → logged/recorded but metrics skipped.
3. Plot a quick-look series to `ecg_raw.png` (raw ECG/RRI signal) and `rr_timeseries.png` (RR interval timeline).
4. If `raw_ecg`:
   - Basic sanity check (`sanity_check_ecg_raw`).
   - R-peak detection (`detect_rpeaks_from_ecg`), then convert peaks to RR (`rpeaks_to_rr`).
   - Clean and flag intervals (`finalize_clean_table_from_rr`).
5. If `rri`:
   - Detect units (`detect_rri_units`) and convert ticks to ms when needed (`convert_polar_ticks_df`).
   - Build relative beat timeline and clean (`finalize_clean_table_from_rr`).
6. Skip metrics if mode is `bpm` or if cleaning fails.
7. Save cleaned table and metadata; compute requested metrics.

## Outputs (per participant/task under results run_root)
- `ecg/ecg_clean.csv`: cleaned RR table with validity flags.
- `ecg/features.csv`: metrics requested in cfg (see below).
- `ecg/meta.json`: source mode, params, QC stats, and basic counts.
- `ecg/ecg_raw.png`: quick-look plot of the raw ECG or RRI input signal.
- `ecg/rr_timeseries.png`: RR interval timeline.
- `_summaries/ecg/features_by_task.csv`: run-level aggregation when metrics exist.

## Available metrics (time-domain HRV)
Configured via `cfg['metrics']['ecg']`. Current options computed in `compute_requested_ecg_features`:
- `RMSSD`: root mean square of successive differences, uses valid RR only.
- `SDNN`: standard deviation of NN intervals, uses valid RR only.
- `pNN50`: fraction of successive differences > 50 ms, uses valid RR only.

## Adding metrics
- Wire new functions into `compute_requested_ecg_features` in `modules/ecg/ecg_pipeline.py` and ensure they operate on the cleaned RR table.
- Prefer computing on `df[df['valid'] == True]` to respect cleaning flags.

## Sanity and QC helpers
- Raw sanity: `modules/ecg/ecg_sanity.py`.
- Cleaning/QC: `modules/ecg/rr_cleaning.py` and `modules/ecg/rr_unit_detection.py`.
- Visualization: `modules/viz/ecg_plots.py` and `modules/viz/time_series.py` for quick plots.
