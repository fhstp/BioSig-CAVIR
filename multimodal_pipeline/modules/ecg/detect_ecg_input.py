import pandas as pd


def detect_ecg_input_mode(df, bpm_range):
    cols = {c.lower(): c for c in df.columns}
    if {"rr_ms", "rri", "rr"} & set(cols):
        return "rri"

    hr_col = cols.get("hr")
    if hr_col:
        series = pd.to_numeric(df[hr_col], errors="coerce")
        valid = series.dropna()
        if valid.empty:
            return "unknown"
        # FIXME better to use bpm_range or fixed values for BPM detection?
        # `Series.between` expects two positional arguments: (left, right).
        try:
            left, right = bpm_range[0], bpm_range[1]
        except Exception:
            # Fallback to a sensible default if bpm_range is malformed
            left, right = 40, 200
        frac_bpm_like = valid.between(left, right).mean()
        if frac_bpm_like > 0.99:   # if 99% of the values are between 40 and 200 (99% beacuse of possible outliers) 
            return "bpm"
        return "raw_ecg"

    return "unknown"