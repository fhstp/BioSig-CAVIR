"""
GSR data sanity checks and validation.
"""
import pandas as pd
import numpy as np


def sanity_check_gsr_raw(df, time_col="Timestamp", value_col="GSR_CONDUCTANCE",
                         valid_range_us=(0.05, 60.0), max_slope_us_per_s=10.0,
                         slope_bin_s=0.25, gap_threshold_s=1.0, min_duration_s=1.0):
    """
    Perform basic sanity checks on raw GSR data.

    Quality figures follow the EDA artifact rules of Kleckner et al. (2018):
    conductance outside `valid_range_us` and sample-to-sample slopes above
    `max_slope_us_per_s` are counted (not removed).

    Parameters
    ----------
    df : pd.DataFrame
        Raw GSR data
    time_col : str, default "Timestamp"
        Column name for timestamps (seconds; milliseconds are detected)
    value_col : str, default "GSR_CONDUCTANCE"
        Column name for GSR conductance values (µS)
    valid_range_us : tuple, default (0.05, 60.0)
        Physiologically plausible skin conductance range in µS
    max_slope_us_per_s : float, default 10.0
        Faster changes are counted as artifacts (electrode movement, contact loss)
    slope_bin_s : float, default 0.25
        Slopes are computed between means of bins of this length
    gap_threshold_s : float, default 1.0
        Time steps longer than this are counted as gaps
    min_duration_s : float, default 1.0
        Shorter segments are rejected (stream ended before the task)

    Returns
    -------
    df_clean : pd.DataFrame
        Cleaned dataframe with valid rows only (not NaN, > 0)
    stats : dict
        Statistics about the data quality
    """
    if time_col not in df.columns or value_col not in df.columns:
        raise KeyError(f"Missing '{time_col}' or '{value_col}' in GSR dataframe.")

    t = pd.to_numeric(df[time_col], errors="coerce")
    x = pd.to_numeric(df[value_col], errors="coerce")

    mask_valid = t.notna() & x.notna() & (x > 0)  # GSR should be positive
    df_clean = df.loc[mask_valid].copy()

    stats = {
        "nan_ratio_raw": float(1.0 - mask_valid.mean()),
        "std_raw": float(x[mask_valid].std()) if mask_valid.any() else 0.0,
        "mean_raw": float(x[mask_valid].mean()) if mask_valid.any() else 0.0,
        "min_raw": float(x[mask_valid].min()) if mask_valid.any() else 0.0,
        "max_raw": float(x[mask_valid].max()) if mask_valid.any() else 0.0,
    }

    if not mask_valid.any():
        raise ValueError("Raw GSR is entirely NaN / invalid.")
    if stats["std_raw"] < 1e-6:
        raise ValueError("Raw GSR seems flatlined (very low variance).")
    # small ranges (< 0.05 µS) occur in low responders as well as with poor contact,
    # so they are only reported, not rejected
    stats["range_raw"] = stats["max_raw"] - stats["min_raw"]

    tv = t[mask_valid].to_numpy(dtype=float)
    xv = x[mask_valid].to_numpy(dtype=float)
    dt = np.diff(tv)
    dt_pos = dt[dt > 0]
    if dt_pos.size and np.median(dt_pos) > 0.5:     # timestamps in ms
        tv, dt, dt_pos = tv / 1000.0, dt / 1000.0, dt_pos / 1000.0

    stats["duration_s"] = float(tv.max() - tv.min())
    # the preparser repeats the last sample into later tasks once a stream has stopped
    if stats["duration_s"] < min_duration_s:
        raise ValueError(f"gsr_ends_before_task: segment covers only {stats['duration_s']:.2f} s")
    # samples per second over the segment; the median time step is unreliable for chunked LSL streams
    stats["fs_est_hz"] = float((tv.size - 1) / stats["duration_s"]) if stats["duration_s"] > 0 else None
    gaps = dt_pos[dt_pos > gap_threshold_s]
    stats["n_gaps"] = int(gaps.size)
    stats["gap_time_s"] = float(gaps.sum())

    stats["frac_out_of_range"] = float(np.mean((xv < valid_range_us[0]) | (xv > valid_range_us[1])))
    # slope between 0.25 s bin means: LSL timestamps arrive in chunks (~10 µs apart
    # inside a chunk), so sample-to-sample slopes would be meaningless
    bins = np.floor((tv - tv.min()) / slope_bin_s).astype(int)
    binned = pd.Series(xv).groupby(bins).mean()
    adjacent = np.diff(binned.index.to_numpy()) == 1
    slope = np.abs(np.diff(binned.to_numpy()))[adjacent] / slope_bin_s
    stats["frac_steep_slope"] = float(np.mean(slope > max_slope_us_per_s)) if slope.size else 0.0
    stats["qc_params"] = {
        "valid_range_us": list(valid_range_us),
        "max_slope_us_per_s": max_slope_us_per_s,
        "slope_bin_s": slope_bin_s,
        "gap_threshold_s": gap_threshold_s,
    }

    return df_clean, stats
