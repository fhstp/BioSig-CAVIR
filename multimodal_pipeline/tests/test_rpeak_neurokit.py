import numpy as np
import pandas as pd
import pytest

nk = pytest.importorskip("neurokit2")

from modules.ecg.rpeak_detection_neurokit import detect_rpeaks_neurokit, estimate_fs_from_timestamps
from modules.ecg.ecg_pipeline import detect_rpeaks


FS = 130
T0 = 1724069872.0


def _chunked_timestamps(n, fs=FS, chunk=73):
    """LSL-style timestamps: ~10 us spacing inside a chunk, one jump per chunk."""
    chunk_start = T0 + (np.arange(n) // chunk) * chunk / fs
    return chunk_start + (np.arange(n) % chunk) * 1e-5


def _ecg_df(timestamps, heart_rate=80, duration=120):
    ecg = nk.ecg_simulate(duration=duration, sampling_rate=FS, heart_rate=heart_rate,
                          heart_rate_std=1, noise=0.01, random_state=42)
    return pd.DataFrame({"Timestamp": timestamps(len(ecg)), "HR": ecg * 500})


def test_fs_estimate_ignores_chunking():
    t = _chunked_timestamps(FS * 120)
    assert estimate_fs_from_timestamps(t, FS) == pytest.approx(FS, rel=0.02)


def test_neurokit_rr_not_quantized_by_chunked_timestamps():
    df = _ecg_df(_chunked_timestamps)
    _, peak_ms, fs, _, source, idx = detect_rpeaks_neurokit(df, fallback_fs_hz=FS)

    rr = np.diff(peak_ms)
    assert source.startswith("neurokit2")
    assert np.median(rr) == pytest.approx(60000 / 80, rel=0.05)
    # chunk-quantized RR (old bug) gives RMSSD of several hundred ms
    assert np.sqrt(np.mean(np.diff(rr) ** 2)) < 60


def test_fallback_to_heartpy_when_neurokit_fails():
    df = _ecg_df(lambda n: T0 + np.arange(n) / FS).iloc[:200]    # too short for neurokit path
    _, reason = detect_rpeaks(df, "neurokit", "heartpy", {}, FS, (5.0, 25.0), (40, 200))
    assert reason is not None and "fell back to heartpy" in reason


def test_no_fallback_raises():
    df = _ecg_df(lambda n: T0 + np.arange(n) / FS).iloc[:200]
    with pytest.raises(ValueError):
        detect_rpeaks(df, "neurokit", None, {}, FS, (5.0, 25.0), (40, 200))
