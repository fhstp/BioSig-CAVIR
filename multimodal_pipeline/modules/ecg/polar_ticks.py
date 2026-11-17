# ecg/polar_rri.py
import numpy as np
import pandas as pd



def convert_polar_ticks_df(
    df: pd.DataFrame,
    ticks_col: str,
    hz: float = 1024.0,
    new_col: str = "rr_ms",
    drop_ticks: bool = False,
) -> pd.DataFrame:
    """
    Convert a Polar RRI ticks column (1/hz seconds) to milliseconds and
    perform column normalization.

    Parameters
    ----------
    df : pd.DataFrame
        Input dataframe with a column of R-R intervals in Polar ticks.
    ticks_col : str
        Name of the column containing R-R intervals in ticks. If this is
        "RRI" and the column exists, it will be renamed to
        "rri_polarticks" and that renamed column will be used.
    hz : float, optional
        Polar tick frequency (usually 1024 Hz).
    new_col : str, optional
        Name of the output column with intervals in milliseconds.
    drop_ticks : bool, optional
        If True, drop the original ticks column after conversion.

    Returns
    -------
    pd.DataFrame
        A copy of the dataframe with normalized column names and an
        added (or replaced) `new_col` in milliseconds. When present, the
        following renamed columns may appear: `rri_polarticks`,
        `timestamp_unix`.
    """
    out = df.copy()

    # Lightweight normalization: rename commonly-used original column names
    # to canonical names so downstream code can rely on stable names.
    if "RRI" in out.columns:
        out = out.rename(columns={"RRI": "rri_polarticks"})
        # if caller passed ticks_col as 'RRI', use the renamed column
        if ticks_col == "RRI":
            ticks_col = "rri_polarticks"

    if "Timestamp" in out.columns:
        out = out.rename(columns={"Timestamp": "timestamp_unix"})

    if ticks_col not in out.columns:
        raise KeyError(f"Column '{ticks_col}' not found in df after normalization.")

    ticks = out[ticks_col].to_numpy(dtype=float)

    # ticks (1/hz seconds) → ms: (ticks / hz) * 1000
    rr_ms = (ticks / float(hz)) * 1000.0
    out[new_col] = rr_ms

    if drop_ticks:
        out = out.drop(columns=[ticks_col])

    return out





