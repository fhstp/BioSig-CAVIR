# Device Mapping Guide

Audience: users adding new devices or custom column names.

## Eye-tracking column mapping

Eye-tracking data is unified by `modules/eyetracking/unifier.py`. The mapping
is defined in `CANON_ALIASES`.

If your device uses different column names, add them under the appropriate
canonical key.

Canonical names used by the pipeline:

- `ts`
- `vel_raw_l`, `vel_raw_r`
- `pupil_l_mm`, `pupil_r_mm`
- `gaze_dir_l_x`, `gaze_dir_l_y`, `gaze_dir_l_z`
- `gaze_dir_r_x`, `gaze_dir_r_y`, `gaze_dir_r_z`
- `fix_raw_l`, `fix_raw_r`, `sac_raw_l`, `sac_raw_r`

### Example: add a new alias

```
CANON_ALIASES = {
  "vel_raw_l": ["Velocity_Left", "LeftVel", "my_device_vel_left"],
  "pupil_l_mm": ["Pupil_Diameter_Left", "PupilLeftMM"],
}
```

## GSR column detection

The GSR pipeline expects `GSR_CONDUCTANCE` but will fall back to columns
containing `GSR`, `CONDUCTANCE`, `SCL`, or `SCR` (case-insensitive).

If your device uses different names, either:

- rename the column in the CSV, or
- set `cfg["params"]["gsr"]["baseline_col"]` to your column name.

## ECG column detection

ECG mode detection uses:

- `RRI` / `RR` / `rr_ms` for RRI mode
- `HR` for raw ECG or BPM mode

If your raw ECG column is not named `HR`, rename it before running the pipeline.

## Head movement columns

Head movement currently requires fixed column names (see `input_data_schema.md`).
Rename columns to match the expected names if needed.
