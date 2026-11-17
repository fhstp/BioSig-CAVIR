# Input Data Schema (CSV)

This document describes the minimum CSV structure the pipeline expects for **GSR**, **eye-tracking**, **ECG**, **head movement**, and **EEG** data. It reflects the current code behavior in `modules/*`.

## General File Layout

- Each participant has a folder under `data_root` (configured in your run config).
- Files are located by glob pattern: `*{task}*{modality}*` within the participant folder.
  - GSR uses `modality="GSR"`.
  - Eye-tracking uses `modality="Eyetracking"`.
  - ECG uses `modality="ECG"`.
  - Head movement uses `modality="HEAD_MOVEMENT"` with pattern `*HEAD*MOVEMENT*.csv`.
  - EEG uses `modality="EEG"`.
- Example:
  - `data_root/01/TaskA_GSR.csv`
  - `data_root/01/TaskA_Eyetracking.csv`
  - `data_root/01/TaskA_ECG.csv`
  - `data_root/01/TaskA_HEAD_MOVEMENT.csv`

## Timestamp Rules by Modality

- **GSR:** `Timestamp` is optional. If missing, the first column is used as time (must be numeric).
- **Eye-tracking:** A time column is required (any alias that maps to canonical `ts`).
- **ECG:** `Timestamp` is required only for raw ECG mode (`Timestamp` + `HR`). RRI mode does not require a time column.
- **Head movement:** `Timestamp` is required.

## GSR CSV

### Required columns

- **Timestamp column**
  - Preferred name: `Timestamp`
  - If missing, the **first column** is used as time.
  - If the first column is non-numeric, the GSR sanity check fails.
- **GSR conductance column**
  - Default name: `GSR_CONDUCTANCE`
  - If missing, the pipeline searches for column names containing:
    - `GSR`, `CONDUCTANCE`, `SCL`, or `SCR` (case-insensitive)
  - If still not found, the **last column** is used.

### Data expectations

- Conductance values must be **positive**.
- Data must not be entirely NaN and must not be flatlined (very low variance).
- Units are expected in **microSiemens** (use `uS` in CSV for ASCII).

### Minimal example

```
Timestamp,GSR_CONDUCTANCE
0.000,1.235
0.008,1.239
0.016,1.241
```

## Eye-tracking CSV

### Required columns (minimum to run segmentation)

- **Time column** (must map to canonical `ts`):
  - Accepted aliases: `ts`, `Timestamp`, `timestamp`, `Time`, `time`, `world_timestamp`, `timestamp [ns]`
  - The pipeline expects **seconds**. Unit auto-conversion is enabled: common nanosecond and millisecond timestamps are automatically converted to seconds by `unify_columns_by_alias`.
- **Velocity column** (at least one):
  - Left eye: `Velocity_Left`, `vel_left`, `velocity_left`, `gaze_velocity_left`
  - Right eye: `Velocity_Right`, `vel_right`, `velocity_right`, `gaze_velocity_right`
  - These map to canonical `vel_raw_l` / `vel_raw_r`.
  - If neither is present, the pipeline skips that file.

### Optional columns (enable extra metrics and plots)

- **Pupil diameter** (mm):
  - `Pupil_Diameter_Left`, `pupil_left`, `pupil_diameter_left`, `pupil diameter left [mm]`
  - `Pupil_Diameter_Right`, `pupil_right`, `pupil_diameter_right`, `pupil diameter right [mm]`
- **3D gaze direction** (unit vector):
  - Left: `Gaze_Left_x`, `Gaze_Left_y`, `Gaze_Left_z`
  - Right: `Gaze_Right_x`, `Gaze_Right_y`, `Gaze_Right_z`
- **2D gaze position**:
  - `gaze_2d_x`, `gaze_2d_y` (used for 2D scanpath plots if present)
- **Blink**:
  - `blink` (any non-zero value is treated as a blink)
- **Device-provided events** (optional comparison only):
  - `Fixation_Left`, `Fixation_Right`, `Saccade_Left`, `Saccade_Right`

### Data expectations

- Timestamps must be numeric and **monotonically increasing**.
- Minimum rows: **10**.
- Recommended sampling rate: **30–500 Hz**.
- Units expected:
  - `ts`: seconds
  - `vel_raw_*`: degrees per second
  - `pupil_*_mm`: millimeters
  - `gaze_dir_*`: unit vector (norm ~ 1)

### Minimal example (velocity-only)

```
Time,Velocity_Left
0.000,12.4
0.008,15.1
0.016,10.8
```

### Richer example (with gaze + pupil)

```
Timestamp,Velocity_Left,Pupil_Diameter_Left,Gaze_Left_x,Gaze_Left_y,Gaze_Left_z
0.000,12.4,3.1,0.02,0.01,0.99
0.008,15.1,3.0,0.03,0.02,0.99
0.016,10.8,3.0,0.01,0.02,0.99
```

## Notes on Column Unification

Eye-tracking column names are unified using `modules/eyetracking/unifier.py`. If your device uses different names, extend `CANON_ALIASES` in that file to add the mapping.

## ECG CSV

The ECG pipeline supports two main input modes:

1) **Raw ECG** (time series)
2) **RRI / RR intervals**

### Mode 1: Raw ECG (time series)

#### Required columns

- **Timestamp column**
  - Required name: `Timestamp`
- **ECG value column**
  - Required name: `HR` (used as raw ECG signal in current implementation)

If either column is missing, the pipeline fails the raw-ECG sanity check.

#### Minimal example

```
Timestamp,HR
0.000,0.015
0.008,0.021
0.016,0.017
```

### Mode 2: RRI / RR intervals

#### Required columns

- Any of: `RRI`, `RR`, or `rr_ms`

If `RRI` is provided, units are auto-detected:
- milliseconds (`ms`) or
- Polar ticks (converted using the configured `polar_ticks_hz`)

#### Minimal example

```
RRI
812
805
798
```

### Notes

- If an `HR` column exists and looks like BPM values (mostly within 40–200), the pipeline treats it as **BPM mode** and **skips** metric extraction.
- For **raw ECG**, `Timestamp` is required. For **RRI mode**, a timestamp column is not required.

## Head Movement CSV

### Required columns

The head movement processor requires all of the following columns:

- `Timestamp`
- Position: `PosX`, `PosY`, `PosZ`
- Rotation (quaternion): `RotX`, `RotY`, `RotZ`, `RotW`
- Velocity: `VelX`, `VelY`, `VelZ`
- Angular velocity: `AngVelX`, `AngVelY`, `AngVelZ`

If any are missing, the pipeline raises a `ValueError`.

### Minimal example

```
Timestamp,PosX,PosY,PosZ,RotX,RotY,RotZ,RotW,VelX,VelY,VelZ,AngVelX,AngVelY,AngVelZ
0.000,0.01,0.02,0.03,0.0,0.0,0.0,1.0,0.1,0.0,0.0,0.01,0.0,0.0
0.008,0.01,0.02,0.03,0.0,0.0,0.0,1.0,0.1,0.0,0.0,0.01,0.0,0.0
0.016,0.01,0.02,0.03,0.0,0.0,0.0,1.0,0.1,0.0,0.0,0.01,0.0,0.0
```

## EEG CSV

The EEG pipeline expects **semicolon-delimited** files (`;`) with European decimal notation (`,` as decimal separator). The first line is treated as a title and skipped; the second line is the header.

### Required columns

The pipeline needs at least **theta** band-power columns for the configured frontal channels and **alpha** band-power columns for the configured parietal channels. Default column names follow the EMOTIV convention:

- Frontal theta (default channels AF3, F7, F3, F4, F8, AF4): `POW.AF3.Theta`, `POW.F7.Theta`, `POW.F3.Theta`, `POW.F4.Theta`, `POW.F8.Theta`, `POW.AF4.Theta`
- Parietal alpha (default channels P7, P8): `POW.P7.Alpha`, `POW.P8.Alpha`

The column prefix `POW.` and channel groups are configurable via `cfg["params"]["eeg"]`.

### Optional columns (enable quality filtering)

- Contact quality: `CQ.AF3`, `CQ.F7`, … (one per channel, prefix configurable via `cq_prefix`)
- Overall EEG quality: `EQ.OVERALL` (used if `use_eq: true`)
- `Timestamp` (UNIX ms): used for time-alignment and meta-logging.

### Data expectations

- Semicolon-separated (`;`), decimal comma (`,`).
- First row is a title/comment row and is skipped automatically.
- Band-power values must be numeric and positive.

### Minimal example

```
EEG Export - EMOTIV
Timestamp;POW.AF3.Theta;POW.F7.Theta;POW.F3.Theta;POW.F4.Theta;POW.F8.Theta;POW.AF4.Theta;POW.P7.Alpha;POW.P8.Alpha;CQ.AF3;CQ.F7
1700000000000;1,23;1,45;1,12;1,34;1,56;1,22;2,11;2,05;4,0;3,5
1700000000128;1,25;1,47;1,14;1,36;1,58;1,24;2,09;2,07;4,0;3,5
```
