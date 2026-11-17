from __future__ import annotations
import numpy as np
import pandas as pd


# The VR headsets (Mindleap / iMotions LSL export) do not report blinks.
# When an eye is not detected the device writes 0 for pupil diameter and
# for the gaze direction vector of that eye. A blink is a short run where
# BOTH eyes are lost at the same time; longer runs are track loss.

DEFAULT_MIN_DURATION_MS = 50.0
DEFAULT_MAX_DURATION_MS = 500.0


def resolve_blink_params(et_params: dict) -> dict:
    blk = (et_params or {}).get("blinks", {}) or {}
    p = {
        "enabled": blk.get("enabled", True),
        "min_duration_ms": blk.get("min_duration_ms", DEFAULT_MIN_DURATION_MS),
        "max_duration_ms": blk.get("max_duration_ms", DEFAULT_MAX_DURATION_MS),
    }
    if p["min_duration_ms"] < 0 or p["max_duration_ms"] <= p["min_duration_ms"]:
        raise ValueError("blinks: need 0 <= min_duration_ms < max_duration_ms")
    return p


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """Return [(start, end_exclusive)] of consecutive True values."""
    m = np.concatenate(([False], mask, [False])).astype(int)
    d = np.diff(m)
    return list(zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)))


def _eye_lost(df: pd.DataFrame, eye: str) -> np.ndarray | None:
    """Signal loss for one eye: pupil <= 0/NaN and gaze vector ~0/NaN (if present)."""
    pupil_col = f"pupil_{eye}_mm"
    gaze_cols = [f"gaze_dir_{eye}_{a}" for a in "xyz"]
    has_pupil = pupil_col in df.columns
    has_gaze = all(c in df.columns for c in gaze_cols)
    if not has_pupil and not has_gaze:
        return None

    lost = np.ones(len(df), dtype=bool)
    if has_pupil:
        p = pd.to_numeric(df[pupil_col], errors="coerce").to_numpy()
        lost &= ~(p > 0)  # also True for NaN
    if has_gaze:
        g = np.column_stack([pd.to_numeric(df[c], errors="coerce").to_numpy() for c in gaze_cols])
        norm = np.sqrt(np.sum(g**2, axis=1))
        lost &= ~(norm > 1e-6)  # also True for NaN
    return lost


def detect_blinks(
    df: pd.DataFrame,
    *,
    ts_col: str = "ts",
    sampling_rate_hz: float | None = None,
    min_duration_ms: float = DEFAULT_MIN_DURATION_MS,
    max_duration_ms: float = DEFAULT_MAX_DURATION_MS,
    out_col: str = "blink",
) -> pd.DataFrame:
    """
    Derive a boolean blink column from bilateral signal loss.

    - Runs shorter than min_duration_ms are treated as noise.
    - Runs longer than max_duration_ms are track loss, not blinks.
    - Runs touching the start or end of the recording are skipped
      (their true duration is unknown).

    Returns a copy of df. If no pupil/gaze columns exist, df is returned
    unchanged (no blink column -> blink metrics stay "not available").
    """
    lost_l = _eye_lost(df, "l")
    lost_r = _eye_lost(df, "r")
    if lost_l is None and lost_r is None:
        return df.copy()
    if lost_l is None:
        both_lost = lost_r
    elif lost_r is None:
        both_lost = lost_l
    else:
        both_lost = lost_l & lost_r

    n = len(df)
    ts = pd.to_numeric(df[ts_col], errors="coerce").to_numpy() if ts_col in df.columns else None
    if ts is not None and np.isfinite(ts).sum() > 1:
        dt = np.diff(ts[np.isfinite(ts)])
        dt_s = float(np.median(dt[dt > 0])) if (dt > 0).any() else None
    else:
        ts, dt_s = None, None
    if dt_s is None:
        if not sampling_rate_hz:
            raise ValueError("detect_blinks needs a valid ts column or sampling_rate_hz")
        dt_s = 1.0 / sampling_rate_hz

    blink = np.zeros(n, dtype=bool)
    for start, end in _runs(both_lost):
        if start == 0 or end == n:
            continue
        if ts is not None and np.isfinite(ts[start]) and np.isfinite(ts[end - 1]):
            dur_ms = (ts[end - 1] - ts[start] + dt_s) * 1000.0
        else:
            dur_ms = (end - start) * dt_s * 1000.0
        if min_duration_ms <= dur_ms <= max_duration_ms:
            blink[start:end] = True

    out = df.copy()
    out[out_col] = blink
    return out
