import numpy as np
import pandas as pd
import pytest

from modules.eyetracking.blinks import detect_blinks, resolve_blink_params

FS = 72.0


def _make_df(n=400, lost_runs_both=(), lost_runs_left=()):
    """Valid binocular signal with zeroed samples at the given (start, length) runs."""
    df = pd.DataFrame({"ts": np.arange(n) / FS})
    for eye in "lr":
        df[f"pupil_{eye}_mm"] = 4.0
        df[f"gaze_dir_{eye}_x"] = 0.1
        df[f"gaze_dir_{eye}_y"] = 0.2
        df[f"gaze_dir_{eye}_z"] = 0.97
    eye_cols = {eye: [c for c in df.columns if f"_{eye}_" in c] for eye in "lr"}
    for start, length in lost_runs_both:
        df.loc[start:start + length - 1, eye_cols["l"] + eye_cols["r"]] = 0.0
    for start, length in lost_runs_left:
        df.loc[start:start + length - 1, eye_cols["l"]] = 0.0
    return df


def _count_onsets(mask):
    return int((np.diff(np.concatenate(([0], np.asarray(mask, dtype=int)))) == 1).sum())


def test_noise_blink_and_track_loss_are_separated():
    # 2 samples ~28 ms (noise), 6 samples ~83 ms (blink), 60 samples ~833 ms (track loss)
    df = _make_df(lost_runs_both=[(50, 2), (100, 6), (200, 60)])
    out = detect_blinks(df)

    assert _count_onsets(out["blink"]) == 1
    assert out["blink"].sum() == 6
    assert out.loc[100:105, "blink"].all()


def test_single_eye_loss_is_not_a_blink():
    df = _make_df(lost_runs_left=[(100, 6)])
    out = detect_blinks(df)
    assert out["blink"].sum() == 0


def test_runs_at_recording_edges_are_ignored():
    df = _make_df(lost_runs_both=[(0, 6), (394, 6)])
    out = detect_blinks(df)
    assert out["blink"].sum() == 0


def test_nan_counts_as_signal_loss():
    df = _make_df()
    cols = [c for c in df.columns if c != "ts"]
    df.loc[100:105, cols] = np.nan
    out = detect_blinks(df)
    assert out["blink"].sum() == 6


def test_without_eye_columns_df_is_unchanged():
    df = pd.DataFrame({"ts": np.arange(10) / FS})
    out = detect_blinks(df)
    assert "blink" not in out.columns


def test_resolve_blink_params_defaults_and_validation():
    assert resolve_blink_params({}) == {"enabled": True, "min_duration_ms": 50.0, "max_duration_ms": 500.0}
    assert resolve_blink_params({"blinks": {"max_duration_ms": 400}})["max_duration_ms"] == 400
    with pytest.raises(ValueError):
        resolve_blink_params({"blinks": {"min_duration_ms": 300, "max_duration_ms": 100}})
