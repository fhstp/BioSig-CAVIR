# Head Movement Metrics Documentation

This document describes all metrics computed by the head movement pipeline.

---

## Overview

The head movement pipeline analyzes head position and rotation data from VR/AR headsets or motion tracking systems. Metrics capture:
- Movement intensity and frequency
- Positional stability
- Rotational behavior
- Activity patterns

---

## Velocity Metrics

### `mean_velocity`
**Type:** Float  
**Description:** Average magnitude of head velocity across the recording. Indicates overall movement intensity.  
**Units:** units/second (depends on tracking system)  
**Note:** Computed from smoothed velocity to reduce noise.

### `max_velocity`
**Type:** Float  
**Description:** Maximum head velocity observed during the recording. Captures peak movement speed.  
**Units:** units/second (depends on tracking system)

### `mean_angular_velocity`
**Type:** Float  
**Description:** Average magnitude of angular velocity (rotation speed) across the recording.  
**Units:** degrees/second or radians/second (depends on tracking system)

### `max_angular_velocity`
**Type:** Float  
**Description:** Maximum angular velocity observed during the recording. Captures fastest rotation.  
**Units:** degrees/second or radians/second (depends on tracking system)

---

## Movement Characterization Metrics

### `movement_intensity`
**Type:** Float  
**Description:** Average velocity magnitude, representing overall movement intensity. Identical to `mean_velocity` but may be computed with different smoothing parameters.  
**Units:** units/second

### `movement_frequency`
**Type:** Float  
**Description:** Number of distinct movement events per minute. A movement event is defined as a transition from stationary to moving state.  
**Units:** events/minute  
**Note:** Requires `is_moving` classification in the processed data.

### `movement_range`
**Type:** Float  
**Description:** Total spatial range of head movement, calculated as the difference between maximum and minimum distance from origin.  
**Units:** distance units (depends on tracking system)  
**Note:** Indicates how far the head moved from its initial position.

### `activity_level`
**Type:** Float  
**Description:** Percentage of recording time spent in motion (head velocity above threshold).  
**Units:** percentage (0-100)  
**Note:** Values near 100% indicate constant movement; near 0% indicates mostly stationary.

---

## Stability Metrics

### `positional_stability`
**Type:** Float  
**Description:** Inverse of position variance. Higher values indicate more stable head position (less wandering or drift).  
**Units:** 1/variance (higher = more stable)  
**Note:** May be infinite if head position never changes. Very low values indicate high variability/instability.

### `rotation_smoothness`
**Type:** Float  
**Description:** Smoothness of rotational movement, computed via spectral analysis. Smoother motion has more power at low frequencies.  
**Units:** proportion (0-1, higher = smoother)  
**Note:** Based on FFT of angular velocity. Values near 1 indicate smooth, controlled rotations; near 0 indicate jerky or erratic rotations.

---

## Processed Data Columns

The pipeline generates these intermediate features (available in cleaned data):

- `velocity_magnitude_smooth`: Smoothed velocity magnitude
- `angular_velocity_magnitude_smooth`: Smoothed angular velocity magnitude
- `distance_from_origin`: Euclidean distance from starting position
- `is_moving`: Boolean flag indicating movement vs. stationary periods

---

## Movement Detection

Head movement is classified using velocity thresholds:

**Default threshold:** Configurable in pipeline parameters  
**Classification:**
- `is_moving = True`: Velocity exceeds threshold
- `is_moving = False`: Velocity below threshold

This binary classification enables:
- Activity level calculation
- Movement frequency counting
- Movement/rest period analysis

---

## Important Notes

### Unit Dependencies
Head tracking systems use different coordinate systems and units:
- **VR headsets (e.g., Pico):** Typically meters and degrees
- **Optical tracking:** May use millimeters and radians
- **IMU sensors:** May use arbitrary units

Always verify units in your tracking system's documentation.

### Smoothing
Most metrics use smoothed velocity to reduce noise from:
- Sensor jitter
- Quantization artifacts
- High-frequency vibrations

Raw values are preserved in cleaned data files for custom analysis.

### Coordinate System
Head position typically measured relative to:
- Initial position (distance from origin)
- World coordinates (if tracking system provides)
- Sensor mounting position

---

## Typical Metric Ranges

### During Active Tasks
- `mean_velocity`: 0.1-0.5 units/s
- `activity_level`: 30-70%
- `movement_frequency`: 5-20 events/min
- `rotation_smoothness`: 0.4-0.7

### During Passive Viewing
- `mean_velocity`: 0.01-0.1 units/s
- `activity_level`: 10-30%
- `movement_frequency`: 1-5 events/min
- `rotation_smoothness`: 0.6-0.9 (smoother)

**Note:** Actual values depend heavily on task type and tracking system units.

---

## Summary Row Output Columns

The pipeline writes one row per participant/task to `_summaries/head_movement/features_by_task.csv` (and to `head_movement_metrics.json` per participant/task). In addition to the ten requested metrics above, the summary row always contains the following columns:

### Identifiers
| Column | Type | Description |
|--------|------|-------------|
| `participant` | str | Participant identifier |
| `task` | str | Task name |
| `duration_sec` | float | Recording duration in seconds, derived from `num_samples / sampling_rate_hz` |

### QC / Sanity Fields (from `sanity_check_head_movement_raw`)
| Column | Type | Description |
|--------|------|-------------|
| `num_samples` | int | Number of raw samples loaded |
| `has_missing_values` | bool | Whether any cell in the raw data is NaN |
| `num_missing_values` | int | Total count of NaN cells |
| `timestamp_monotonic` | bool / None | Whether timestamps are strictly increasing (`None` if no Timestamp column) |
| `velocity_plausible` | bool / None | Whether all velocity magnitudes are below 100,000 units/s (`None` if velocity columns absent) |
| `position_plausible` | bool / None | Whether no single inter-sample position jump exceeds 10,000 units (`None` if position columns absent) |
| `rotation_valid` | bool / None | Whether all quaternion magnitudes are close to 1 (or 10,000 for fixed-point encodings) (`None` if rotation columns absent) |

---

## Version History

- **v1.0** (2026-03-10): Initial documentation
  - Documented 10 core head movement metrics
  - Added movement detection and stability metrics
  - Included typical ranges and unit considerations
