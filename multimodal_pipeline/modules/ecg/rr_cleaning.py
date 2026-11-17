
import numpy as np
import pandas as pd


def finalize_clean_table_from_rr(rr_df: pd.DataFrame,
                                 source: str,
                                 bpm_range: tuple[float, float]) -> pd.DataFrame:
    """
    rr_df must have at least 'timestamp_s' (sec) and 'rr_ms' (ms).
    Returns a canonical clean_df with columns:
      timestamp_s, rr_ms, HR, valid, source
    Also returns a dict with summary statistics
    """

    df = rr_df.copy()

    if "rr_ms" not in df.columns:
        raise KeyError("finalize_clean_table_from_rr expects 'rr_ms' column")

    # bpm bounds from bpm_range
    low_hr, high_hr = bpm_range
    rr_min_ms = 60000.0 / high_hr
    rr_max_ms = 60000.0 / low_hr

    rm_ms = df["rr_ms"]

    valid = np.isfinite(rm_ms.astype(float))
    valid &= rm_ms > 0
    valid &= rm_ms.between(rr_min_ms, rr_max_ms)

    df["valid"] = valid
    df["source"] = source

    #print("[rr_cleaning] finalize_clean_table_from_rr called")
    #print("[rr_cleaning] input rr_df shape:", rr_df.shape)
    #print("[rr_cleaning] output df type:", type(df))
    #print("[rr_cleaning] output df shape:", df.shape)
    #print("[rr_cleaning] output df columns:", df.columns.tolist())

    df = flag_rr_artifacts(df, rr_col="rr_ms", valid_col="valid", min_rr=rr_min_ms, max_rr=rr_max_ms)


    return df, rr_qc_stats(df)


def rr_qc_stats(df: pd.DataFrame) -> dict:
    """Counts of invalid and artifact-flagged RR rows of a cleaned RR table."""
    if "rr_artifact_reason" in df.columns:
        n_bad = int(df["rr_artifact_reason"].notna().sum())
        frac_bad = float(n_bad / len(df)) if len(df) else 0.0
    else:
        n_bad = 0
        frac_bad = 0.0

    return {
        "n_rr_total": int(len(df)),
        "n_rr_invalid": int((~df["valid"]).sum()),
        "n_rr_artifacts": n_bad,
        "frac_rr_invalid": float((~df["valid"]).sum() / len(df)) if len(df) else 0.0,
        "frac_rr_artifacts": frac_bad,
    }


def flag_rr_artifacts_kubios(df: pd.DataFrame,
                             rr_col: str = "rr_ms",
                             valid_col: str = "valid",
                             min_beats: int = 10) -> pd.DataFrame:
    """
    Flag ectopic, missed, extra and long/short beats with the Kubios algorithm
    (neurokit2.signal_fixpeaks, Lipponen & Tarvainen 2019) for RR series that come
    without a raw ECG (e.g. Polar RRI). Flagged rows get valid=False and
    rr_artifact_reason="kubios_<type>"; rows are kept so other columns stay aligned.
    """
    import neurokit2 as nk

    out = df.copy()
    rr = pd.to_numeric(out[rr_col], errors="coerce").astype(float)
    if rr.notna().sum() < min_beats:
        return out

    # beat positions in ms (sampling_rate 1000); gaps from invalid RR are filled with the median
    peaks = np.round(np.cumsum(rr.fillna(rr.median()).to_numpy())).astype(int)

    # not iterative: the returned info then lists the artifacts found in the original series
    info, _ = nk.signal_fixpeaks(peaks, sampling_rate=1000, method="Kubios", iterative=False, show=False)

    if "rr_artifact_reason" not in out.columns:
        out["rr_artifact_reason"] = pd.Series(index=out.index, dtype="object")
    flagged = np.zeros(len(out), dtype=bool)
    for kind in ("ectopic", "missed", "extra", "longshort"):
        idx = np.asarray(info.get(kind, []), dtype=int)
        idx = idx[(idx >= 0) & (idx < len(out))]
        new = idx[out["rr_artifact_reason"].iloc[idx].isna().to_numpy()]
        out.iloc[new, out.columns.get_loc("rr_artifact_reason")] = f"kubios_{kind}"
        flagged[idx] = True

    out[valid_col] = out[valid_col].astype(bool) & ~flagged if valid_col in out.columns else ~flagged
    return out



def summarize_rr_validity(clean_df: pd.DataFrame) -> dict:
    """
    Summarize how many RR values are valid/invalid.

    Expects a 'valid' boolean column in clean_df.

    Returns a dict like:
      {
        "n_rr_total": int,
        "n_rr_valid": int,
        "n_rr_invalid": int,
        "frac_rr_valid": float,
        "frac_rr_invalid": float,
      }
    """
    if "valid" not in clean_df.columns:
        raise KeyError("summarize_rr_validity expects a 'valid' column.")

    n_total = int(len(clean_df))
    n_valid = int(clean_df["valid"].sum())
    n_invalid = n_total - n_valid

    frac_valid = float(n_valid / n_total) if n_total > 0 else 0.0
    frac_invalid = float(n_invalid / n_total) if n_total > 0 else 0.0

    return {
        "n_rr_total": n_total,
        "n_rr_valid": n_valid,
        "n_rr_invalid": n_invalid,
        "frac_rr_valid": frac_valid,
        "frac_rr_invalid": frac_invalid,
    }






def flag_rr_artifacts(df: pd.DataFrame,
                      rr_col: str = "rr_ms",
                      valid_col: str = "valid",
                      window: int = 15,
                      ratio_hi: float = 1.8,
                      ratio_lo: float = 0.3,
                      min_rr: float = 250.0,
                      max_rr: float = 2000.0) -> pd.DataFrame:
    """
    Flags obvious RR artifacts:
      - rr <= 0
      - rr outside [min_rr, max_rr]
      - local doubled-beat pattern (missed peak): rr[i] very large vs local median,
        and previous rr[i-1] very small (or zero) vs same local median.

    Adds columns:
      - rr_median_local
      - rr_artifact_reason
    Updates `valid` by AND-ing with detected validity.
    """
    out = df.copy()
    rr = pd.to_numeric(out[rr_col], errors="coerce").astype(float)

    # local robust baseline
    local_med = rr.rolling(window=window, center=True, min_periods=max(5, window//3)).median()

    reason = pd.Series(index=out.index, dtype="object")

    # basic invalids
    bad_zero = rr <= 0
    bad_range = (rr < min_rr) | (rr > max_rr)

    # doubled-beat heuristic: current high, previous low
    prev_rr = rr.shift(1)
    prev_med = local_med.shift(1)

    high_now = rr > (local_med * ratio_hi)
    low_prev = prev_rr < (prev_med * ratio_lo)

    doubled_pattern = high_now & low_prev

    # combine
    bad = bad_zero | bad_range | doubled_pattern

    reason.loc[bad_zero] = "rr_leq_0"
    reason.loc[bad_range & ~bad_zero] = "rr_out_of_range"
    reason.loc[doubled_pattern & ~bad_zero & ~bad_range] = "missed_peak_doubled_rr"

    out["rr_median_local"] = local_med
    out["rr_artifact_reason"] = reason

    # update valid flag
    if valid_col in out.columns:
        out[valid_col] = out[valid_col].astype(bool) & (~bad)
    else:
        out[valid_col] = ~bad

    return out
