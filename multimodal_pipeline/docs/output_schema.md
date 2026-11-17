# Output Schema (Per Run)

Audience: users interpreting pipeline outputs and downstream analysis.

Outputs are written under the `run_root` directory created by `make_run_root`.
Within each run, files are organized by participant and task, then by modality
folder name (see `file_structure`).

## Common outputs

Each modality may produce:

- `features.csv`: per participant-task metrics.
- `meta.json`: parameters and QC notes.
- Diagnostic plots (PNG).

Some modalities also write run-level summaries under `_summaries/<modality>/`.

## ECG outputs



Folder: `ecg/`

- `ecg_clean.csv`: cleaned RR table with validity flags.
- `features.csv`: HRV metrics (RMSSD, SDNN, pNN50).
- `meta.json`: input mode, params, QC. `qc` holds `valid_frac`, `duration_s`,
  `covered_s` (time covered by ECG rows, intervals > `coverage_max_gap_s` excluded),
  `frac_rr_kubios_artifacts` (Kubios-flagged beats; excluded for Polar RRI, corrected
  by NeuroKit for raw ECG, see `kubios_artifact_handling`). `rr_cleaning_qc` holds the
  RR counts after `trim_start_sec` (`n_rr_trimmed` = beats removed by trimming).
- `rr_timeseries.png`: quick-look plot.
- `_summaries/ecg/features_by_task.csv`: aggregated summary (if any metrics).

## GSR outputs

Folder: `gsr/`

- `gsr_clean.csv`: conductance with `deviation` column.
- `gsr_phasic_responses.csv`: rows that pass the phasic threshold.
- `features.csv`: requested GSR metrics.
- `meta.json`: baseline, params, QC stats. `qc` holds `duration_s`, `fs_est_hz`,
  `n_gaps`, `gap_time_s`, `frac_out_of_range` (outside 0.05-60 µS), `frac_steep_slope`
  (> 10 µS/s between 0.25 s bins), `range_raw`.
- `gsr_timeseries_raw.png`, `gsr_processed.png`, `gsr_deviations.png`
- `_summaries/gsr/features_by_task.csv`: aggregated summary (if any metrics).

## Eye-tracking outputs

Folder: `eye_tracking/`

- `eyetracking_clean.csv`: unified columns on the regular tracker-rate grid (`ts` = grid
  time, `ts_orig` = delivered row time, empty slots = signal loss) + `vel_calc` (angular gaze
  velocity, deg/s) + segmentation labels.
- `features.csv`: fixation/saccade + blink + pupil metrics (if available).
- `meta.json`: params, QC, unit conversion info. `qc.timebase` holds the estimated
  sampling rate (also used for I-VT), gaps and duration; `qc.validity` holds sample
  fractions (`valid_sample_frac`, `track_loss_frac`, `track_loss_excl_blink_frac`,
  `blink_time_prop`, `valid_pupil_frac`, `pupil_both_eyes_valid_frac`); `qc.resampling` holds
  `tracker_hz`, `render_rate_hz`, `repeat_frac`, `unique_sample_rate_hz` and how far samples were
  shifted onto the grid (`shift_median_ms`, `shift_max_ms`); `qc.velocity_check` compares the
  median own velocity with the device velocity. Segments that fail
  the sanity check still get a `meta.json` with the `qc` block.
- `gaze_velocity_timeseries.png`
- `event_timeline.png`
- `pupil_diameter_timeseries.png` (if pupil data exists)
- `gaze_2d_scanpath.png` (if 2D gaze data exists)

## Head movement outputs

Folder: `HEAD_MOVEMENT/`

- `head_movement_features.csv`: processed and derived features.
- `head_movement_metrics.json`: requested metrics (if any).

## EEG outputs

Folder: `eeg/`

- `eeg_clean.csv`: quality-filtered, outlier-trimmed samples with `theta_frontal`, `alpha_parietal`, and `idx_theta_alpha` columns.
- `features.csv`: requested EEG metrics (e.g. `theta_frontal_mean`, `idx_mean`).
- `meta.json`: processing parameters, raw row counts, quality filter stats, and outlier trim counts.
  `qc` holds `duration_s`, `covered_s` (intervals > `coverage_max_gap_s` excluded),
  `coverage_max_gap_s`, `n_samples`, `fs_est_hz`. With `compute_features: false` (default for
  preparsed input) only `meta.json` is written, with `features_disabled_reason`.
- `_summaries/eeg/features_by_task.csv`: all participants × tasks in one file (includes `z_idx_vs_baseline` if baseline tasks are configured).

## PAAS outputs

- `_summaries/paas/features_by_task.csv`: `score` (raw rating, 1-9), `score_pomp`
  ((score - 1) / 8 x 100), `score_int` (rounded half up to whole points, for sensitivity
  analyses only), `resolution` (0.5 for the in-app version, else 1), `source`, `error`, `note`.

## Data-quality summary

Folder: `_summaries/qc/` (written by `modules/qc/qc_summary.py` at the end of a run;
can also be run on an existing run folder with `build_qc_summary("results/<run>")`).

- `qc_by_segment.csv`: one row per cohort x participant x task x modality with
  `status` (ok / failed / missing / not_recorded), `reason`, `quality`, `duration_s`,
  `coverage` (time covered by the modality's rows, gaps excluded, as share of the eye-tracking
  segment duration), `usable`, `flags` and
  modality-specific QC figures.
- `qc_by_cohort_modality.csv`: counts (expected / ok / failed / missing / usable segments,
  participants with data and with all tasks usable), quality median [IQR], sampling rate,
  most frequent exclusion reasons.
- `qc_modality_combinations.csv`: usable segments and participants per modality combination.
- `qc_thresholds.json`: thresholds used.
- `qc_report.md`: criteria, results per cohort, tables, PAAS harmonisation text, references.

Float columns in the QC CSV files are rounded to 4 decimal places.

## Run metadata

At the run root:

- `run_metadata.json`: config snapshot and input check results.
