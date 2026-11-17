import numpy as np
import pandas as pd


def sanity_check_eyetracking(
    df: pd.DataFrame,
    ts_col: str = "ts",
    min_rows: int = 10,
    gap_threshold_s: float = 0.1,
    fs_bounds_hz: tuple[float, float] = (30.0, 500.0),
    max_nonpositive_dt_pct: float = 0.05,
    pupil_bounds_mm: tuple[float, float] = (0.5, 12.0),
) -> dict:
    """
    Early sanity checks on a unified eyetracking dataframe (canonical `ts` in seconds).

    Errors (ok=False, segment is not analysed):
      - too few rows, missing/NaN timestamps, no positive time steps
      - sampling rate estimate outside `fs_bounds_hz`
      - more than `max_nonpositive_dt_pct` non-increasing time steps
        (chunked or duplicated LSL samples; event durations would be wrong)

    Missingness counts device placeholders (0 / negative) as missing, not only NaN:
    the VR headsets write 0 for pupil and gaze vector when an eye is not detected.
    """
    report = {
        "ok": True,
        "n_rows": int(len(df)),
        "errors": [],
        "warnings": [],
        "timebase": {},
        "missingness": {},
        "ranges": {},
    }

    # basic
    if df is None or df.empty or len(df) < min_rows:
        report["ok"] = False
        report["errors"].append(f"Too few rows: {0 if df is None else len(df)} (min {min_rows})")
        return report

    if ts_col not in df.columns:
        report["ok"] = False
        report["errors"].append(f"Missing timestamp column '{ts_col}'")
        return report

    ts = pd.to_numeric(df[ts_col], errors="coerce")
    n_nan_ts = int(ts.isna().sum())
    if n_nan_ts > 0:
        report["ok"] = False
        report["errors"].append(f"{n_nan_ts} NaN timestamps")

    dt = ts.diff().iloc[1:]
    dt_pos = dt[dt > 0]

    nonpos = int((dt <= 0).sum())
    nonpos_pct = float(nonpos / len(dt)) if len(dt) else 0.0
    report["timebase"]["nonpositive_dt_count"] = nonpos
    report["timebase"]["nonpositive_dt_pct"] = nonpos_pct

    duration_s = float(ts.max() - ts.min())
    report["timebase"]["duration_s"] = duration_s
    if duration_s <= 0:
        report["ok"] = False
        report["errors"].append("Non-positive duration (timestamps broken)")

    if dt_pos.empty:
        report["ok"] = False
        report["errors"].append("No positive dt values (timestamps not increasing)")
        return report

    dt_med = float(dt_pos.median())
    fs_est = float(1.0 / dt_med)
    report["timebase"]["dt_median_s"] = dt_med
    report["timebase"]["fs_est_hz"] = fs_est
    # samples per second over the whole segment; differs from fs_est when samples are duplicated
    report["timebase"]["fs_span_hz"] = float((len(ts) - 1) / duration_s) if duration_s > 0 else None

    if not fs_bounds_hz[0] <= fs_est <= fs_bounds_hz[1]:
        report["ok"] = False
        report["errors"].append(f"Implausible sampling rate estimate: {fs_est:.1f} Hz")

    if nonpos_pct > max_nonpositive_dt_pct:
        report["ok"] = False
        report["errors"].append(f"{nonpos_pct:.1%} non-increasing timestamps (chunked or duplicated samples)")
    elif nonpos > 0:
        report["warnings"].append(f"{nonpos} non-increasing timestamps")

    gaps = dt_pos[dt_pos > gap_threshold_s]
    report["timebase"]["n_gaps"] = int(len(gaps))
    report["timebase"]["max_gap_s"] = float(gaps.max()) if not gaps.empty else 0.0
    report["timebase"]["gap_time_s"] = float(gaps.sum()) if not gaps.empty else 0.0
    if not gaps.empty:
        report["warnings"].append(f"{len(gaps)} gaps > {gap_threshold_s:.3f}s")

    # missingness: NaN or device placeholder (<= 0) per signal group
    groups = {
        "pupil": [c for c in ("pupil_l_mm", "pupil_r_mm") if c in df.columns],
        "gaze_dir": [c for c in df.columns if c.startswith("gaze_dir_") and c[-2:] in ("_x", "_y", "_z")],
        "vel_raw": [c for c in ("vel_raw_l", "vel_raw_r") if c in df.columns],
    }
    for name, cols in groups.items():
        if not cols:
            continue
        vals = df[cols].apply(pd.to_numeric, errors="coerce")
        report["missingness"][f"{name}_nan_pct"] = float(vals.isna().mean().mean())
        if name == "pupil":
            report["missingness"]["pupil_missing_pct"] = float((vals.isna() | (vals <= 0)).mean().mean())

    if groups["pupil"]:
        p = df[groups["pupil"]].apply(pd.to_numeric, errors="coerce")
        present = p > 0
        out_of_range = present & ((p < pupil_bounds_mm[0]) | (p > pupil_bounds_mm[1]))
        report["ranges"]["pupil_out_of_range_pct"] = float(out_of_range.sum().sum() / max(int(present.sum().sum()), 1))

    for eye in ("l", "r"):
        cols = [f"gaze_dir_{eye}_{a}" for a in "xyz"]
        if all(c in df.columns for c in cols):
            g = df[cols].apply(pd.to_numeric, errors="coerce").to_numpy()
            norm = np.sqrt(np.sum(g**2, axis=1))
            norm = norm[np.isfinite(norm) & (norm > 1e-6)]
            if norm.size:
                med = float(np.median(norm))
                report["ranges"][f"gaze_dir_norm_median_{eye}"] = med
                if not 0.8 <= med <= 1.2:
                    report["warnings"].append(f"Gaze direction norm suspicious ({eye}: median {med:.2f})")

    return report
