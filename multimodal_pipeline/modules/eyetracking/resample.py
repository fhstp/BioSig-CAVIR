from __future__ import annotations
import numpy as np
import pandas as pd


# The VR headsets (Pico via iMotions/LSL) track the eyes at 60 Hz but deliver one row
# per rendered frame (72 or 90 Hz). Missing frames are filled with a copy of the
# previous sample: every 6th row at 72 Hz, every 3rd row at 90 Hz. Row timestamps are
# frame times, so the time between two real samples jitters by one frame.

DEFAULT_TRACKER_HZ = 60.0
EYES = ("l", "r")


def _signal_cols(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns
            if (c.startswith("gaze_dir_") and c[-2:] in ("_x", "_y", "_z"))
            or c in ("pupil_l_mm", "pupil_r_mm")]


def _any_eye_valid(df: pd.DataFrame) -> np.ndarray:
    """At least one eye detected: pupil > 0 or a non-zero gaze vector."""
    valid = np.zeros(len(df), dtype=bool)
    for eye in EYES:
        if f"pupil_{eye}_mm" in df.columns:
            valid |= pd.to_numeric(df[f"pupil_{eye}_mm"], errors="coerce").to_numpy() > 0
        cols = [f"gaze_dir_{eye}_{a}" for a in "xyz"]
        if all(c in df.columns for c in cols):
            g = df[cols].apply(pd.to_numeric, errors="coerce").to_numpy()
            valid |= np.sqrt(np.sum(g**2, axis=1)) > 1e-6
    return valid


def regularize_to_tracker_rate(
    df: pd.DataFrame,
    tracker_hz: float = DEFAULT_TRACKER_HZ,
    ts_col: str = "ts",
) -> tuple[pd.DataFrame, dict]:
    """
    Put an eye-tracking stream onto a regular grid at the tracker rate.

    - Repeated rows (all gaze/pupil values equal to the previous row, at least one eye
      valid) are dropped.
    - Each remaining valid sample goes to the next free grid slot near its time
      (target = round((t - t0) * tracker_hz)):
        - after a gap of two or more samples (blink, track loss) the sample goes back on
          schedule, so losses keep their length and shifts do not accumulate;
        - otherwise slot = max(previous slot + 1, target - 1). The one slot of tolerated
          lag absorbs the frame jitter (a sample delivered one frame late is not missing).
    - A single empty slot between two samples (dropped tracker sample) is interpolated.
    - Slots without a sample (blinks, track loss) get 0 for gaze and pupil, the device's
      placeholder for "eye not detected", so blink detection and validity masks treat
      them as signal loss. Other columns (device velocity, events) are NaN there.

    Returns the regular dataframe (`ts` = grid time, `ts_orig` = row time of the sample)
    and a dict with resampling figures for meta.json.
    """
    sig = _signal_cols(df)
    if not sig:
        raise ValueError("regularize_to_tracker_rate needs gaze_dir_* or pupil_*_mm columns")

    df = df.reset_index(drop=True)
    ts = pd.to_numeric(df[ts_col], errors="coerce").to_numpy(dtype=float)
    duration = float(np.nanmax(ts) - np.nanmin(ts))
    valid = _any_eye_valid(df)

    vals = df[sig].apply(pd.to_numeric, errors="coerce").to_numpy()
    same_prev = np.r_[False, np.all(vals[1:] == vals[:-1], axis=1)]
    repeat = same_prev & valid & np.r_[False, valid[:-1]]

    keep = valid & ~repeat
    t0 = float(np.nanmin(ts))
    samples = df.loc[keep]
    target = np.round((ts[keep] - t0) * tracker_hz).astype(int)
    slots = np.empty(target.size, dtype=int)
    prev, prev_target = -1, None
    for i, s in enumerate(target):
        if prev_target is not None and s - prev_target >= 3:
            # at least two samples missing (blink, track loss): back on schedule, keeping a
            # lag of one slot if there was one, so the loss keeps its length
            slot = max(prev + 1, s + min(prev - prev_target, 0))
        else:
            # frame jitter or a single dropped sample: up to one slot of lag
            slot = max(s - 1, prev + 1)
        slots[i] = prev = slot
        prev_target = s
    lag = (slots - target) / tracker_hz     # how far samples were shifted from their row time

    # the grid ends at the last sample (no artificial loss at the end)
    n_slots = int(slots[-1] + 1) if slots.size else int(np.floor(duration * tracker_hz)) + 1
    out = samples.assign(ts_orig=ts[keep]).set_axis(slots).reindex(pd.RangeIndex(n_slots))
    # a single empty slot between two samples is a dropped tracker sample (17 ms; too
    # short for a blink): interpolate it. Longer empty runs = eye not detected (0)
    empty = out[sig[0]].isna().to_numpy()
    single = empty & ~np.r_[True, empty[:-1]] & ~np.r_[empty[1:], True]
    out.loc[single, sig] = out[sig].interpolate(limit=1, limit_area="inside").loc[single]
    out["interpolated"] = single
    out[sig] = out[sig].fillna(0.0)
    out[ts_col] = t0 + np.arange(n_slots) / tracker_hz
    if "t_rel" in out.columns:
        out["t_rel"] = out[ts_col] - t0

    n_valid_rows = int(valid.sum())
    info = {
        "tracker_hz": float(tracker_hz),
        "render_rate_hz": float((len(df) - 1) / duration) if duration > 0 else None,
        "n_rows_in": int(len(df)),
        "repeat_frac": float(repeat.sum() / n_valid_rows) if n_valid_rows else None,
        "n_samples_unique": int(keep.sum()),
        "n_slots": int(n_slots),
        "n_interpolated": int(single.sum()),
        "shift_median_ms": float(np.median(lag) * 1000) if lag.size else None,
        "shift_max_ms": float(lag.max() * 1000) if lag.size else None,
        "unique_sample_rate_hz": float(keep.sum() / duration) if duration > 0 else None,
    }
    return out, info


def gaze_angular_velocity(df: pd.DataFrame, tracker_hz: float = DEFAULT_TRACKER_HZ) -> pd.Series:
    """
    Angular gaze velocity (deg/s) between neighbouring samples of a regular grid.

    Per eye: angle between the normalised gaze direction vectors of slot i-1 and i,
    times tracker_hz; NaN if the eye is not detected in either slot. Both eyes valid ->
    mean of both, otherwise the valid eye.
    """
    per_eye = []
    for eye in EYES:
        cols = [f"gaze_dir_{eye}_{a}" for a in "xyz"]
        if not all(c in df.columns for c in cols):
            continue
        g = df[cols].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
        norm = np.sqrt(np.sum(g**2, axis=1))
        ok = np.isfinite(norm) & (norm > 1e-6)
        u = np.where(ok[:, None], g / np.where(ok, norm, 1.0)[:, None], np.nan)
        cos = np.clip(np.sum(u[1:] * u[:-1], axis=1), -1.0, 1.0)
        vel = np.r_[np.nan, np.degrees(np.arccos(cos)) * tracker_hz]
        vel[~(ok & np.r_[False, ok[:-1]])] = np.nan
        per_eye.append(vel)

    if not per_eye:
        return pd.Series(np.nan, index=df.index, name="vel_calc")
    stacked = np.vstack(per_eye)
    n = np.sum(~np.isnan(stacked), axis=0)
    vel = np.where(n > 0, np.nansum(stacked, axis=0) / np.maximum(n, 1), np.nan)
    return pd.Series(vel, index=df.index, name="vel_calc")
