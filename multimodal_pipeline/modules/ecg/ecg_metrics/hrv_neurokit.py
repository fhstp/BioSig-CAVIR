import numpy as np
import pandas as pd


def hrv_time_neurokit(rr_df: pd.DataFrame,
                      rr_col: str = "rr_ms",
                      time_col: str = "timestamp_s") -> dict:
    """
    Time-domain HRV via neurokit2.hrv_time on an RR table (valid RR rows only).

    RR times are passed along so that neurokit only uses successive differences
    of truly consecutive beats (gaps from removed beats are not bridged).
    Returns a dict without the "HRV_" prefix, e.g. {"RMSSD": ..., "SDNN": ..., "pNN50": ...}.
    """
    import neurokit2 as nk

    rr = pd.to_numeric(rr_df[rr_col], errors="coerce").to_numpy(dtype=float)
    ok = np.isfinite(rr)
    if ok.sum() < 3:
        return {}

    intervals = {"RRI": rr[ok]}
    if time_col in rr_df.columns:
        intervals["RRI_Time"] = pd.to_numeric(rr_df[time_col], errors="coerce").to_numpy(dtype=float)[ok]

    res = nk.hrv_time(intervals)
    return {c.removeprefix("HRV_"): float(res[c].iloc[0]) for c in res.columns}
