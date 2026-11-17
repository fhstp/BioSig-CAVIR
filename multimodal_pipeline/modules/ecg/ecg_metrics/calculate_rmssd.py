from __future__ import annotations
import numpy as np
import pandas as pd

def rmssd_from_rr(rr_df: pd.DataFrame) -> float:
    """Native RMSSD (ms) from canonical rr_intervals (column rr_ms)."""
    rr = rr_df["rr_ms"].to_numpy(dtype=float)
    if rr.size < 3:
        return float("nan")
    diff = np.diff(rr)
    if diff.size == 0:
        return float("nan")
    return float(np.sqrt(np.mean(diff**2)))

 

# TODO windows later 
'''
def rmssd_over_windows(rr_df: pd.DataFrame, windows_df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute RMSSD per window.
    windows_df: columns [window_id, win_start_s, win_end_s]
    Returns: [window_id, rmssd]
    """
    out = []
    for _, w in windows_df.iterrows():
        win = rr_df[(rr_df["timestamp_s"] >= w.win_start_s) & (rr_df["timestamp_s"] <= w.win_end_s)]
        out.append({"window_id": w.window_id, "rmssd": rmssd_from_rr(win)})
    return pd.DataFrame(out)

'''