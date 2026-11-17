"""
Time coverage of a segment: how much of it is actually covered by samples.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def covered_duration_s(timestamps, max_gap_s: float) -> float:
    """
    Seconds covered by samples: sum of the intervals between consecutive samples,
    intervals longer than max_gap_s count as missing data (dropout).
    """
    ts = pd.to_numeric(pd.Series(timestamps), errors="coerce").dropna().to_numpy(dtype=float)
    if ts.size < 2:
        return 0.0
    d = np.diff(np.sort(ts))
    return float(d[d <= max_gap_s].sum())


def coverage_qc(timestamps, max_gap_s: float) -> dict:
    """QC block for meta.json: span, covered time and the gap threshold used."""
    ts = pd.to_numeric(pd.Series(timestamps), errors="coerce").dropna()
    span = float(ts.max() - ts.min()) if len(ts) > 1 else 0.0
    return {
        "duration_s": span,
        "covered_s": covered_duration_s(ts, max_gap_s),
        "coverage_max_gap_s": float(max_gap_s),
        "n_samples": int(len(ts)),
        "fs_est_hz": float(1.0 / np.median(np.diff(np.sort(ts.to_numpy())))) if len(ts) > 1 else np.nan,
    }
