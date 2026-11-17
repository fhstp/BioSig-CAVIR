# Eye Tracking Metrics Documentation

This document describes all metrics computed by the eye tracking pipeline.

---

## Overview

The eye tracking pipeline computes metrics in four main categories:
1. **Fixation Metrics** - Counts, rates, and durations of fixations
2. **Saccade Metrics** - Counts, rates, and durations of saccades
3. **Pupil Metrics** - Pupil diameter statistics
4. **Blink Metrics** - Blink counts and rates (if available)
5. **Device Metrics** - Raw device-reported fixation/saccade counts (for validation)

---

## Fixation Metrics

### `fixation_count`
**Type:** Integer  
**Description:** Total number of fixations detected using I-VT (Velocity-Threshold) segmentation algorithm. A fixation is counted at its onset (when gaze velocity drops below threshold).  
**Units:** count  

### `fixation_rate_per_s`
**Type:** Float  
**Description:** Rate of fixations per second, calculated as `fixation_count / total_duration_s`. Normalized by recording duration to allow comparison across different task lengths.  
**Units:** fixations/second  

### `avg_fixation_duration_ms`
**Type:** Float  
**Description:** Average duration of fixations in milliseconds. Calculated as `fixation_total_ms / fixation_count`.  
**Units:** milliseconds (ms)  

### `fixation_total_ms`
**Type:** Float  
**Description:** Total time spent in fixations across the entire recording.  
**Units:** milliseconds (ms)  

### `fixation_time_fraction`
**Type:** Float (0.0 to 1.0)  
**Description:** Proportion of recording time spent in fixations. Calculated as `fixation_samples / total_samples`. A value of 0.17 means 17% of the recording was spent fixating.  
**Units:** proportion (0-1)  

---

## Saccade Metrics

### `saccade_count`
**Type:** Integer  
**Description:** Total number of saccades detected using I-VT segmentation. A saccade is counted at its onset (when gaze velocity exceeds threshold).  
**Units:** count  

### `saccade_rate_per_s`
**Type:** Float  
**Description:** Rate of saccades per second, calculated as `saccade_count / total_duration_s`. Normalized by recording duration.  
**Units:** saccades/second  

### `avg_saccade_duration_ms`
**Type:** Float  
**Description:** Average duration of saccades in milliseconds. Calculated as `saccade_total_ms / saccade_count`.  
**Units:** milliseconds (ms)  

### `saccade_total_ms`
**Type:** Float  
**Description:** Total time spent in saccades across the entire recording.  
**Units:** milliseconds (ms)  

### `saccade_time_fraction`
**Type:** Float (0.0 to 1.0)  
**Description:** Proportion of recording time spent in saccades. Calculated as `saccade_samples / total_samples`. A value of 0.60 means 60% of the recording was spent in saccadic movement.  
**Units:** proportion (0-1)  

---

## Pupil Metrics

### `pupil_mean_mm`
**Type:** Float  
**Description:** Mean pupil diameter across the recording. If both eyes are available, this is the average of left and right pupils.  
**Units:** millimeters (mm)  

### `pupil_std_mm`
**Type:** Float  
**Description:** Standard deviation of pupil diameter, indicating variability in pupil size.  
**Units:** millimeters (mm)  

### `pupil_min_mm`
**Type:** Float  
**Description:** Minimum pupil diameter observed during the recording.  
**Units:** millimeters (mm)  

### `pupil_max_mm`
**Type:** Float  
**Description:** Maximum pupil diameter observed during the recording.  
**Units:** millimeters (mm)  

### `pupil_median_mm`
**Type:** Float  
**Description:** Median pupil diameter, less sensitive to outliers than mean.  
**Units:** millimeters (mm)  

### `pupil_valid_fraction`
**Type:** Float (0.0 to 1.0)  
**Description:** Proportion of samples with valid pupil data (non-NaN values). Indicates data quality.  
**Units:** proportion (0-1)  

### `pupil_source`
**Type:** String  
**Description:** Indicates which eye(s) were used for pupil metrics. Possible values: `"left_eye"`, `"right_eye"`, `"mean_both_eyes"`.  

---

## Blink Metrics

### `blink_count`
**Type:** Integer  
**Description:** Total number of blinks detected during the recording. Counted at blink onset.  
**Units:** count  
**Note:** Only available if device provides blink detection. If unavailable, this field will contain a note.

### `blink_rate_per_s`
**Type:** Float  
**Description:** Rate of blinks per second, calculated as `blink_count / total_duration_s`.  
**Units:** blinks/second  
**Note:** Only available if device provides blink detection.

### `blink_time_prop`
**Type:** Float (0.0 to 1.0)  
**Description:** Proportion of recording time spent blinking.  
**Units:** proportion (0-1)  
**Note:** Only available if device provides blink detection.

### `avg_blink_duration_ms`
**Type:** Float  
**Description:** Average blink duration in milliseconds.  
**Units:** milliseconds (ms)  
**Note:** Only available if device provides blink detection.

### `blink_total_ms`
**Type:** Float  
**Description:** Total time spent blinking across the entire recording.  
**Units:** milliseconds (ms)  
**Note:** Only available if device provides blink detection.

---

## Device Metrics (Validation)

These metrics are extracted from raw device-reported fixation/saccade classifications (if available). They are provided for comparison and validation against the I-VT algorithm results.

### `fixation_count_device_left`
**Type:** Integer  
**Description:** Number of samples classified as fixations by the device for the left eye. This is the raw device classification, not computed by our I-VT algorithm.  
**Units:** sample count  
**Note:** This is sample count, not event count (different from `fixation_count`).

### `fixation_count_device_right`
**Type:** Integer  
**Description:** Number of samples classified as fixations by the device for the right eye.  
**Units:** sample count  

### `fixation_count_device_mean`
**Type:** Float  
**Description:** Average of left and right eye device fixation counts: `(left + right) / 2`.  
**Units:** sample count  

### `saccade_count_device_left`
**Type:** Integer  
**Description:** Number of samples classified as saccades by the device for the left eye.  
**Units:** sample count  

### `saccade_count_device_right`
**Type:** Integer  
**Description:** Number of samples classified as saccades by the device for the right eye.  
**Units:** sample count  

### `saccade_count_device_mean`
**Type:** Float  
**Description:** Average of left and right eye device saccade counts: `(left + right) / 2`.  
**Units:** sample count  

---

## Timing Metrics

### `total_time_ms`
**Type:** Float  
**Description:** Total recording duration in milliseconds, estimated from sample count × sampling rate.  
**Units:** milliseconds (ms)  

### `total_duration_s`
**Type:** Float  
**Description:** Total recording duration in seconds, used for normalizing rate metrics (e.g., `fixation_rate_per_s`). Preferentially calculated from timestamps if available, otherwise estimated from sample count.  
**Units:** seconds (s)  

---

## Notes and Missing Data

### `_notes`
**Type:** Dictionary (JSON)  
**Description:** Contains notes about any missing or unavailable data types. For example: `{"blink": "Blink data not available"}`.  
**Purpose:** Helps identify which metrics could not be computed and why.

### `_blink_note`, `_pupil_note`, etc.
**Type:** String  
**Description:** Individual note fields for specific missing data types, extracted from `_notes` for easier filtering.  

---

## Segmentation Algorithm

### I-VT (Velocity-Threshold Identification)

All fixation and saccade metrics are computed using the I-VT algorithm with the following default parameters:

- **Velocity Threshold:** 30 deg/s (configurable via `velocity_threshold_deg_s`)
- **Minimum Fixation Duration:** 60 ms (configurable via `fixation_min_duration_ms`)
- **Minimum Saccade Duration:** 22 ms (configurable via `min_saccade_duration_ms`)
- **Smoothing Window:** 10 ms (configurable via `smooth_win_ms`)
- **Fixation Merge Gap:** 20 ms (configurable via `merge_fix_gap_ms`)

**Reference:** Salvucci, D. D., & Goldberg, J. H. (2000). Identifying fixations and saccades in eye-tracking protocols. *Proceedings of the Eye Tracking Research and Applications Symposium*, 71-78.

---

## Important Distinctions

### Event Count vs. Sample Count

- **Event Count** (`fixation_count`, `saccade_count`): Number of distinct fixation/saccade events (onsets)
- **Sample Count** (`fixation_count_device_*`): Number of samples/frames classified as fixation/saccade


### I-VT Algorithm vs. Device Classification

- **I-VT metrics** (`fixation_count`, `saccade_count`): Computed by our pipeline using velocity thresholds
- **Device metrics** (`*_device_*`): Raw classifications from the eye tracking hardware

These may differ due to different algorithms, thresholds, or preprocessing. Both are provided for validation and comparison purposes.

---

## Column Order in Output

The metrics appear in the following order in `features.csv`:

1. Participant and task identifiers
2. Fixation metrics (count, rate, duration, proportion)
3. Saccade metrics (count, rate, duration, proportion)
4. Timing metrics (total_time_ms, total_duration_s)
5. Pupil metrics (mean, std, min, max, median, validity, source)
6. Blink metrics (if available)
7. Device metrics (left, right, mean for both fixations and saccades)
8. Notes (missing data information)

---

## Version History

- **v1.0** (2026-03-10): Initial documentation with cleaned metric names
  - Removed duplicate metrics (`*_total`, `*_normalized`)
  - Renamed `fixation_time_prop` → `fixation_time_fraction`
  - Renamed `duration_s_used` → `total_duration_s`
  - Added `*_device_mean` metrics for both fixations and saccades
