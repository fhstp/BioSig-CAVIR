import pandas as pd

def sanity_check_ecg_raw(df, time_col="Timestamp", value_col="HR"):
    """
    - ensure columns exist
    - convert to numeric
    - drop rows with NaN in time or value
    - compute basic stats (nan_ratio, std, abs_max)
    - raise only on completely broken data (all NaN / flatline)
    Returns: df_clean, stats
    """
    if time_col not in df.columns or value_col not in df.columns:
        raise KeyError(f"Missing '{time_col}' or '{value_col}' in ECG dataframe.")

    t = pd.to_numeric(df[time_col], errors="coerce")
    x = pd.to_numeric(df[value_col], errors="coerce")

    mask_valid = t.notna() & x.notna()
    df_clean = df.loc[mask_valid].copy()

    stats = {
        "nan_ratio_raw": float(1.0 - mask_valid.mean()),
        "std_raw": float(x[mask_valid].std()) if mask_valid.any() else 0.0,
        "abs_max_raw": float(x[mask_valid].abs().max()) if mask_valid.any() else 0.0,
    }

    if not mask_valid.any():
        raise ValueError("Raw ECG is entirely NaN / invalid.")
    if stats["std_raw"] < 1e-6:
        raise ValueError("Raw ECG seems flatlined (very low variance).")

    return df_clean, stats
