import numpy as np
import pandas as pd
import pytest

from modules.eyetracking.resample import gaze_angular_velocity, regularize_to_tracker_rate


def _gaze_rows(angles_deg):
    """Gaze rotating horizontally; both eyes identical, pupil 4 mm."""
    a = np.radians(np.asarray(angles_deg, dtype=float))
    cols = {}
    for eye in ("l", "r"):
        cols[f"gaze_dir_{eye}_x"] = np.sin(a)
        cols[f"gaze_dir_{eye}_y"] = np.zeros_like(a)
        cols[f"gaze_dir_{eye}_z"] = np.cos(a)
        cols[f"pupil_{eye}_mm"] = np.full_like(a, 4.0)
    return cols


def _stream_72hz(seconds=2.0, deg_per_s=10.0):
    """60 Hz samples delivered at 72 Hz: every 6th row repeats the previous sample."""
    n_rows = int(seconds * 72)
    ts = np.arange(n_rows) / 72.0
    # sample index of each row: 5 new samples per 6 rows
    sample_idx = np.arange(n_rows) - np.arange(n_rows) // 6
    angles = sample_idx / 60.0 * deg_per_s
    return pd.DataFrame({"ts": ts, **_gaze_rows(angles)})


def test_repeats_removed_and_60hz():
    df = _stream_72hz()
    out, info = regularize_to_tracker_rate(df, tracker_hz=60)

    assert info["repeat_frac"] == pytest.approx(1 / 6, abs=0.01)
    assert info["unique_sample_rate_hz"] == pytest.approx(60, abs=1.5)
    assert np.allclose(np.diff(out["ts"]), 1 / 60)
    g = out[["gaze_dir_l_x", "gaze_dir_l_y", "gaze_dir_l_z"]].to_numpy()
    assert not np.any(np.all(g[1:] == g[:-1], axis=1))
    assert info["shift_max_ms"] <= 1000 / 60 + 1e-9


def test_track_loss_keeps_its_duration():
    df = _stream_72hz(seconds=3.0)
    lost = (df["ts"] >= 1.0) & (df["ts"] < 1.5)        # 0.5 s without an eye
    df.loc[lost, [c for c in df.columns if c != "ts"]] = 0.0
    out, _ = regularize_to_tracker_rate(df, tracker_hz=60)

    empty = (out["pupil_l_mm"] == 0) & (out["pupil_r_mm"] == 0)
    assert empty.sum() == pytest.approx(30, abs=2)      # 0.5 s at 60 Hz
    assert len(out) == pytest.approx(3.0 * 60, abs=2)


def test_angular_velocity_constant_rotation():
    df = _stream_72hz(deg_per_s=10.0)
    out, _ = regularize_to_tracker_rate(df, tracker_hz=60)
    vel = gaze_angular_velocity(out, tracker_hz=60)
    assert np.nanmedian(vel) == pytest.approx(10.0, rel=0.05)


def test_velocity_nan_next_to_invalid_samples():
    df = pd.DataFrame({"ts": np.arange(10) / 60, **_gaze_rows(np.arange(10.0))})
    df.loc[5, ["gaze_dir_l_x", "gaze_dir_l_y", "gaze_dir_l_z",
               "gaze_dir_r_x", "gaze_dir_r_y", "gaze_dir_r_z"]] = 0.0
    vel = gaze_angular_velocity(df, tracker_hz=60)
    assert np.isnan(vel[0])
    assert np.isnan(vel[5]) and np.isnan(vel[6])
    assert vel[4] == pytest.approx(60.0, rel=1e-6)     # 1 deg per sample at 60 Hz


def test_dropped_samples_are_not_signal_loss():
    # tracker dropped single samples; the first is absorbed by the one-slot lag
    # tolerance, later ones are interpolated - none may show up as "eye not detected"
    df = pd.DataFrame({"ts": np.arange(40) / 60, **_gaze_rows(np.arange(40.0))})
    df = df.drop(index=[10, 20, 30]).reset_index(drop=True)
    out, info = regularize_to_tracker_rate(df, tracker_hz=60)

    assert info["n_interpolated"] >= 1
    assert (out["pupil_l_mm"] > 0).all()
    vel = gaze_angular_velocity(out, tracker_hz=60)
    assert vel.iloc[1:].notna().all()
