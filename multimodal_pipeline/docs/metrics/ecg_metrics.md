# ECG Metrics Documentation

This document describes all metrics computed by the ECG pipeline.

---

## Overview

The ECG pipeline computes heart rate variability (HRV) metrics from ECG signals or RR intervals. The pipeline supports multiple input formats:
- Raw ECG signals (processed to extract RR intervals)
- Pre-computed RR intervals
- Heart rate (BPM) data

---

## HRV Time-Domain Metrics

### `RMSSD`
**Type:** Float  
**Description:** Root Mean Square of Successive Differences between adjacent RR intervals. A primary measure of short-term HRV, reflecting parasympathetic (vagal) activity. Higher values indicate better cardiovascular health and stress recovery.  
**Units:** milliseconds (ms)  
**Note:** Only computed from valid RR intervals, not from BPM data.

### `SDNN`
**Type:** Float  
**Description:** Standard Deviation of all NN (Normal-to-Normal) intervals. Represents overall HRV and reflects all cyclic components responsible for variability. Lower values may indicate reduced cardiac autonomic function.  
**Units:** milliseconds (ms)  
**Note:** Only computed from valid RR intervals, not from BPM data.

### `pNN50`
**Type:** Float  
**Description:** Percentage of successive RR intervals that differ by more than 50 ms. A measure of short-term HRV associated with parasympathetic activity. Higher values indicate greater heart rate variability.  
**Units:** percentage (%)  
**Note:** Only computed from valid RR intervals, not from BPM data.

---

## Data Quality Metrics

### `valid_frac`
**Type:** Float (0.0 to 1.0)  
**Description:** Proportion of RR intervals that passed quality checks. Indicates the reliability of the computed HRV metrics.  
**Units:** proportion (0-1)  
**Note:** Found in metadata file (`meta.json`), not in features CSV.

---

## Input Modes

The ECG pipeline supports three input modes:

### Raw ECG Signal
- **Source:** Continuous ECG voltage signal
- **Processing:** R-peak detection → RR interval extraction → cleaning → HRV computation
- **Metrics available:** All HRV metrics
- **Quality control:** Includes R-peak detection validation and RR interval cleaning

### RR Intervals (RRI)
- **Source:** Pre-computed RR intervals from external devices (e.g., Polar H10)
- **Processing:** Unit detection → cleaning → HRV computation
- **Metrics available:** All HRV metrics
- **Quality control:** RR interval validation and outlier removal

### BPM (Beats Per Minute)
- **Source:** Heart rate values
- **Processing:** Limited (BPM is already averaged)
- **Metrics available:** None (HRV cannot be computed from averaged heart rate)
- **Note:** Pipeline records data but does not compute HRV metrics

---

## RR Interval Cleaning

Before computing HRV metrics, RR intervals undergo quality control:

1. **Unit Detection:** Automatically detects if intervals are in milliseconds or seconds
2. **Outlier Removal:** Removes physiologically implausible RR intervals based on heart rate range
3. **Artifact Detection:** Identifies and removes artifacts from sensor issues
4. **Validity Marking:** Labels each interval as valid or invalid

**Default HR range:** 40-200 BPM (configurable via `hr_outlier_range_bpm`)

---

## Metadata

Additional information saved in `meta.json`:

### Processing Parameters
```json
{
  "sampling_rate_hz": 1000,
  "hr_outlier_range_bpm": [40, 200],
  "bandpass_hz": [0.5, 35.0]
}
```

### Data Source Information
- `source_file_mode`: Input format (raw_ecg, rri, or bpm)
- `rri_source`: How RR intervals were obtained
- `library_versions`: Versions of processing libraries (e.g., heartpy)

### Quality Control Statistics
- `valid_frac`: Proportion of valid RR intervals
- `rr_cleaning_qc`: Detailed cleaning statistics
  - Number of outliers removed
  - Number of artifacts detected
  - Final valid interval count

---

## Important Notes

### RMSSD vs. SDNN
- **RMSSD:** Reflects short-term, high-frequency HRV (parasympathetic activity)
- **SDNN:** Reflects total HRV across all time scales (sympathetic + parasympathetic)
- Both are important but measure different aspects of cardiac autonomic function

### When Metrics Cannot Be Computed
If the input is BPM data, HRV metrics will not be computed because:
- BPM represents averaged heart rate
- HRV requires beat-to-beat variability information
- Successive differences cannot be calculated from averaged values

The pipeline will note this in the metadata and features file.

### Minimum Data Requirements
For reliable HRV metrics:
- At least 60 seconds of continuous data recommended
- At least 50 valid RR intervals
- Valid fraction > 0.5 (50% valid data)

---

## References

### HRV Standards
- Task Force of the European Society of Cardiology and the North American Society of Pacing and Electrophysiology. (1996). Heart rate variability: Standards of measurement, physiological interpretation, and clinical use. *Circulation*, 93(5), 1043-1065.

### R-Peak Detection
- Van Gent, P., et al. (2019). HeartPy: A novel heart rate algorithm for the analysis of noisy signals. *Transportation Research Part F*, 66, 368-378.

---

## Column Order in Output

The metrics appear in `features.csv` as:

1. `participant` - Participant identifier
2. `task` - Task name
3. HRV metrics (RMSSD, SDNN, pNN50, etc.)

**Note:** If metrics cannot be computed, an error field may appear: `error_ECG: "BPM input mode"` or `error_ECG: "Unknown ECG input format"`

---

## Version History

- **v1.0** (2026-03-10): Initial documentation
  - Documented RMSSD, SDNN, pNN50 metrics
  - Described three input modes (raw ECG, RRI, BPM)
  - Added data quality and cleaning information
