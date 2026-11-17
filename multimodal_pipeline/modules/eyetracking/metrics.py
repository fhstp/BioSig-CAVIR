from __future__ import annotations
import numpy as np
import pandas as pd
from typing import Optional

# Plausible pupil diameter range, same defaults as validity_mask.add_validity_masks
PUPIL_MIN_MM = 0.5
PUPIL_MAX_MM = 12.0


def compute_statistics(
    fixation_array,
    saccade_array,
    sampling_rate_hz: float,
    duration_s: float | None = None,
) -> dict:
    """
    Fixed version of your compute_statistics:
    - Counts are TRUE COUNTS (onsets), not normalized by time.
    - Also returns rates per second separately.
    """
    fix = np.asarray(fixation_array, dtype=bool)
    sac = np.asarray(saccade_array, dtype=bool)
    if fix.shape != sac.shape:
        raise ValueError("fixation_array and saccade_array must have the same length")

    ms_per_sample = 1000.0 / float(sampling_rate_hz)
    total_ms = len(fix) * ms_per_sample
    # Prefer provided duration (timestamp-based), otherwise derive from sample count
    total_s_samples = total_ms / 1000.0 if total_ms > 0 else 0.0
    total_s = duration_s if (duration_s is not None and duration_s > 0) else total_s_samples

    def onset_count(mask_bool):
        x = mask_bool.astype(np.uint8)
        return int(np.count_nonzero(np.diff(np.concatenate(([0], x))) == 1))

    fixation_count = onset_count(fix)
    saccade_count  = onset_count(sac)

    fixation_total_ms = fix.sum() * ms_per_sample
    saccade_total_ms  = sac.sum() * ms_per_sample

    avg_fixation_duration_ms = (fixation_total_ms / fixation_count) if fixation_count > 0 else 0.0
    avg_saccade_duration_ms  = (saccade_total_ms  / saccade_count)  if saccade_count  > 0 else 0.0

    fixation_prop = fix.sum() / float(len(fix)) if len(fix) else 0.0
    saccade_prop  = sac.sum() / float(len(sac)) if len(sac) else 0.0

    return {
        # Counts
        "fixation_count": fixation_count,
        "saccade_count": saccade_count,

        # Rates per second
        "fixation_rate_per_s": (fixation_count / total_s) if total_s > 0 else 0.0,
        "saccade_rate_per_s": (saccade_count / total_s) if total_s > 0 else 0.0,

        # Durations and proportions
        "avg_fixation_duration_ms": avg_fixation_duration_ms,
        "fixation_total_ms": fixation_total_ms,
        "fixation_time_fraction": fixation_prop,

        "avg_saccade_duration_ms": avg_saccade_duration_ms,
        "saccade_total_ms": saccade_total_ms,
        "saccade_time_fraction": saccade_prop,

        # Time coverage based on samples
        "total_time_ms": total_ms,
        "total_duration_s": total_s,
    }


def compute_blink_metrics(df: pd.DataFrame, sampling_rate_hz: float) -> Optional[dict]:
    """
    Compute blink-related metrics if blink data is available.
    
    Returns dict with metrics or None if blink data not available.
    """
    if "blink" not in df.columns:
        return None
    
    blink = pd.to_numeric(df["blink"], errors="coerce").fillna(0)
    blink_bool = (blink > 0).astype(bool)
    
    if blink_bool.sum() == 0:
        # Blink column exists but no blinks detected
        return {
            "blink_count": 0,
            "blink_rate_per_s": 0.0,
            "blink_time_prop": 0.0,
            "avg_blink_duration_ms": 0.0,
        }
    
    ms_per_sample = 1000.0 / float(sampling_rate_hz)
    total_s = len(df) * ms_per_sample / 1000.0
    
    # Count blink onsets
    blink_onsets = np.diff(np.concatenate(([0], blink_bool.astype(int)))) == 1
    blink_count = int(blink_onsets.sum())
    
    blink_total_ms = blink_bool.sum() * ms_per_sample
    avg_blink_duration_ms = (blink_total_ms / blink_count) if blink_count > 0 else 0.0
    
    return {
        "blink_count": blink_count,
        "blink_rate_per_s": (blink_count / total_s) if total_s > 0 else 0.0,
        "blink_time_prop": float(blink_bool.mean()),
        "avg_blink_duration_ms": avg_blink_duration_ms,
        "blink_total_ms": blink_total_ms,
    }


def compute_pupil_metrics(df: pd.DataFrame) -> Optional[dict]:
    """
    Compute pupil diameter metrics if pupil data is available.
    
    Returns dict with metrics or None if pupil data not available.
    """
    pupil_cols = [c for c in df.columns if c.startswith("pupil") and c.endswith("_mm")]
    if not pupil_cols:
        return None

    # Invalid samples (0 / -0.1 placeholders during blinks or track loss) become NaN,
    # using the masks from validity_mask.py when present, else the same mm bounds
    def _valid_eye(eye: str) -> pd.Series:
        vals = pd.to_numeric(df[f"pupil_{eye}_mm"], errors="coerce")
        mask_col = f"valid_pupil_{eye}"
        if mask_col in df.columns:
            valid = df[mask_col].astype(bool)
        else:
            valid = (vals >= PUPIL_MIN_MM) & (vals <= PUPIL_MAX_MM)
        return vals.where(valid)

    # Mean of both eyes where both are valid, otherwise the one valid eye
    if "pupil_l_mm" in df.columns and "pupil_r_mm" in df.columns:
        pupil = pd.concat([_valid_eye("l"), _valid_eye("r")], axis=1).mean(axis=1, skipna=True)
        pupil_source = "mean_both_eyes"
    elif "pupil_l_mm" in df.columns:
        pupil = _valid_eye("l")
        pupil_source = "left_eye"
    elif "pupil_r_mm" in df.columns:
        pupil = _valid_eye("r")
        pupil_source = "right_eye"
    else:
        return None

    valid_pupil = pupil.dropna()
    
    if len(valid_pupil) == 0:
        return {
            "pupil_mean_mm": None,
            "pupil_std_mm": None,
            "pupil_min_mm": None,
            "pupil_max_mm": None,
            "pupil_median_mm": None,
            "pupil_valid_fraction": 0.0,
            "pupil_source": pupil_source,
        }
    
    return {
        "pupil_mean_mm": float(valid_pupil.mean()),
        "pupil_std_mm": float(valid_pupil.std()),
        "pupil_min_mm": float(valid_pupil.min()),
        "pupil_max_mm": float(valid_pupil.max()),
        "pupil_median_mm": float(valid_pupil.median()),
        "pupil_valid_fraction": float(len(valid_pupil) / len(pupil)),
        "pupil_source": pupil_source,
    }


def compute_device_metrics(df: pd.DataFrame) -> Optional[dict]:
    """
    Extract device-reported fixation/saccade counts from raw data columns.
    
    These are the raw classifications from the eye tracking device, provided
    for comparison and validation against the I-VT algorithm results.
    
    Parameters
    ----------
    df : pd.DataFrame
        Dataframe with device classification columns (fix_raw_l, fix_raw_r, sac_raw_l, sac_raw_r)
    
    Returns
    -------
    dict or None
        Dictionary with device metrics, or None if device data not available.
        Metrics are sample counts (not event counts).
    """
    # Check if device-reported fixation/saccade columns exist
    has_fix_raw = "fix_raw_l" in df.columns or "fix_raw_r" in df.columns
    has_sac_raw = "sac_raw_l" in df.columns or "sac_raw_r" in df.columns
    
    if not has_fix_raw and not has_sac_raw:
        return None
    
    result = {}
    
    # Fixation counts
    if has_fix_raw:
        fix_l = df["fix_raw_l"].sum() if "fix_raw_l" in df.columns else 0
        fix_r = df["fix_raw_r"].sum() if "fix_raw_r" in df.columns else 0
        
        if fix_l > 0 or fix_r > 0:
            result["fixation_count_device_left"] = int(fix_l)
            result["fixation_count_device_right"] = int(fix_r)
            result["fixation_count_device_mean"] = float((fix_l + fix_r) / 2.0)
    
    # Saccade counts
    if has_sac_raw:
        sac_l = df["sac_raw_l"].sum() if "sac_raw_l" in df.columns else 0
        sac_r = df["sac_raw_r"].sum() if "sac_raw_r" in df.columns else 0
        
        if sac_l > 0 or sac_r > 0:
            result["saccade_count_device_left"] = int(sac_l)
            result["saccade_count_device_right"] = int(sac_r)
            result["saccade_count_device_mean"] = float((sac_l + sac_r) / 2.0)
    
    return result if result else None


def compute_all_metrics(
    df: pd.DataFrame,
    sampling_rate_hz: float,
    requested_metrics: Optional[list[str]] = None,
) -> dict:
    """
    Compute all available eye-tracking metrics from a segmented dataframe.
    
    Checks for data availability and gracefully handles missing data by adding notes.
    
    Parameters
    ----------
    df : pd.DataFrame
        Segmented dataframe with columns: fix, sac, and optionally blink, pupil_*_mm
    sampling_rate_hz : float
        Sampling rate in Hz
    requested_metrics : list[str], optional
        List of metric names to compute. If None, computes all available metrics.
        Common metrics: "fixation_count", "saccade_count", "blink_rate_per_s", "pupil_mean_mm", etc.
    
    Returns
    -------
    dict
        Dictionary with computed metrics and notes about missing data.
        Format: {"metrics": {...}, "notes": {...}, "available_data": {...}}
    """
    result = {
        "metrics": {},
        "notes": {},
        "available_data": {},
    }
    
    # Check what data is available
    has_fix_sac = "fix" in df.columns and "sac" in df.columns
    has_blink = "blink" in df.columns
    has_pupil = any(c.startswith("pupil") and c.endswith("_mm") for c in df.columns)

    # Duration based on timestamps (preferred for normalization)
    duration_s_ts = None
    if "ts" in df.columns:
        ts_vals = pd.to_numeric(df["ts"], errors="coerce").dropna()
        if len(ts_vals) >= 2:
            duration_candidate = float(ts_vals.max() - ts_vals.min())
            if duration_candidate > 0:
                duration_s_ts = duration_candidate
    
    result["available_data"] = {
        "fixation_saccade": has_fix_sac,
        "blink": has_blink,
        "pupil": has_pupil,
    }
    
    # --- Fixation/Saccade metrics (always compute if available) ---
    if has_fix_sac:
        fix_sac_stats = compute_statistics(
            df["fix"].to_numpy(),
            df["sac"].to_numpy(),
            sampling_rate_hz=sampling_rate_hz,
            duration_s=duration_s_ts,
        )
        result["metrics"].update(fix_sac_stats)
    else:
        result["notes"]["fixation_saccade"] = "Fixation/saccade data not available (segmentation not performed)"
    
    # --- Blink metrics ---
    blink_stats = compute_blink_metrics(df, sampling_rate_hz)
    if blink_stats is not None:
        result["metrics"].update(blink_stats)
    else:
        result["notes"]["blink"] = "Blink data not available"
    
    # --- Pupil metrics ---
    pupil_stats = compute_pupil_metrics(df)
    if pupil_stats is not None:
        result["metrics"].update(pupil_stats)
    else:
        result["notes"]["pupil"] = "Pupil diameter data not available"
    
    # --- Device metrics (raw device classifications) ---
    device_stats = compute_device_metrics(df)
    if device_stats is not None:
        result["metrics"].update(device_stats)
    else:
        result["notes"]["device"] = "Device fixation/saccade classifications not available"
    
    # Preserve full metrics before filtering
    result["metrics_full"] = result["metrics"].copy()

    # Filter to requested metrics if specified
    if requested_metrics:
        filtered_metrics = {}
        for metric_name in requested_metrics:
            if metric_name in result["metrics_full"]:
                filtered_metrics[metric_name] = result["metrics_full"][metric_name]
            else:
                # Check if it's a note about missing data
                if metric_name.startswith("blink") and "blink" in result["notes"]:
                    result["notes"][f"{metric_name}_requested"] = result["notes"]["blink"]
                elif metric_name.startswith("pupil") and "pupil" in result["notes"]:
                    result["notes"][f"{metric_name}_requested"] = result["notes"]["pupil"]
                else:
                    result["notes"][f"{metric_name}_requested"] = f"Metric '{metric_name}' not found in computed metrics"
        result["metrics"] = filtered_metrics

        # Drop "not available" notes for categories that weren't requested at all,
        # so they don't show up as surprise columns in the summary table.
        requested_set = set(requested_metrics)
        if not any(m.startswith(("blink", "avg_blink")) for m in requested_set):
            result["notes"].pop("blink", None)
        if not any(m.startswith("pupil") for m in requested_set):
            result["notes"].pop("pupil", None)
        if not any("device" in m for m in requested_set):
            result["notes"].pop("device", None)
        if not any(m.startswith(("fixation", "saccade")) or m in {"total_time_ms", "total_duration_s"} for m in requested_set):
            result["notes"].pop("fixation_saccade", None)

    return result
