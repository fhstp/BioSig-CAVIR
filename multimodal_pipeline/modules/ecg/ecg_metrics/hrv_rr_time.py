# modules/ecg/ecg_metrics/hrv_time.py
from __future__ import annotations

import numpy as np
import pandas as pd


def successive_rr_diffs(rr_df: pd.DataFrame) -> np.ndarray:
    """
    Differences between truly adjacent beats (ms).
    rr_df usually holds only the valid rows of the clean table with the original index kept,
    so an index step > 1 marks a removed beat; that pair is skipped instead of bridged.
    """
    rr = pd.to_numeric(rr_df["rr_ms"], errors="coerce")
    rr = rr[np.isfinite(rr)]
    if rr.size < 2:
        return np.array([], dtype=float)
    diff = np.diff(rr.to_numpy(dtype=float))
    if pd.api.types.is_integer_dtype(rr.index):
        diff = diff[np.diff(rr.index.to_numpy()) == 1]
    return diff


def rmssd_from_rr(rr_df: pd.DataFrame) -> float:
    """Root mean square of successive differences (ms)."""
    diff = successive_rr_diffs(rr_df)
    if diff.size < 1:
        return np.nan
    return float(np.sqrt(np.mean(diff**2)))


def sdnn_from_rr(rr_df: pd.DataFrame) -> float:
    """Standard deviation of NN intervals (ms)."""
    rr = np.asarray(rr_df["rr_ms"], dtype=float)
    rr = rr[np.isfinite(rr)]
    if rr.size < 2:
        return np.nan
    return float(np.std(rr, ddof=1))


def pnn50_from_rr(rr_df: pd.DataFrame) -> float:
    """Percentage of successive differences > 50 ms."""
    diff = np.abs(successive_rr_diffs(rr_df))
    if diff.size < 1:
        return np.nan
    return float(np.mean(diff > 50.0) * 100.0)


_METRIC_FUNCS = {
    "RMSSD": rmssd_from_rr,
    "SDNN": sdnn_from_rr,
    "pNN50": pnn50_from_rr,
}


def compute_hrv_time(rr_df: pd.DataFrame, metrics: list[str]) -> dict[str, float]:
    """Compute selected time-domain HRV metrics from rr_df."""
    results: dict[str, float] = {}
    for name in metrics:
        func = _METRIC_FUNCS.get(name)
        if func is None:
            # print(f"[hrv_time] Unknown metric requested: {name}")
            continue
        results[name] = func(rr_df)
    return results
