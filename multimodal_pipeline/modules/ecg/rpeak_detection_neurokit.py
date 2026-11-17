from __future__ import annotations
import numpy as np
import pandas as pd


def estimate_fs_from_timestamps(t: np.ndarray, fallback_fs_hz: float, tolerance: float = 0.1) -> float:
    """
    Estimate the sampling rate from the whole recording (n samples / duration).

    The median sample-to-sample step is useless for LSL streams: samples arrive in
    chunks with ~10 us spacing inside a chunk and ~0.5 s jumps between chunks.
    Over the whole recording the chunking averages out (e.g. 130.2 Hz for a Polar H10).
    Falls back to `fallback_fs_hz` if the estimate deviates more than `tolerance`
    (e.g. stream dropouts or wrong units).
    """
    span = float(t[-1] - t[0])
    if span > 1e5:     # timestamps in ms instead of s
        span /= 1000.0
    if not np.isfinite(span) or span <= 0 or t.size < 2:
        return float(fallback_fs_hz)

    fs_est = (t.size - 1) / span
    if abs(fs_est - fallback_fs_hz) / fallback_fs_hz > tolerance:
        print(f"[rpeak_nk] fs from timestamps ({fs_est:.1f} Hz) deviates from configured "
              f"{fallback_fs_hz} Hz, using configured value")
        return float(fallback_fs_hz)
    return float(fs_est)


def detect_rpeaks_neurokit(
        df: pd.DataFrame,
        time_col: str | None = "Timestamp",
        value_col: str = "HR",
        fallback_fs_hz: float = 130.0,
        clean_method: str = "neurokit",
        peak_method: str = "neurokit",
        correct_artifacts: bool = True,
        artifact_info: dict | None = None,
) -> tuple[np.ndarray | None, np.ndarray, float, np.ndarray, str, np.ndarray]:
    """
    Detect R-peaks from a raw ECG signal using NeuroKit2.

    Same return signature as `detect_rpeaks_from_ecg` (HeartPy) so both are
    interchangeable in the pipeline.

    Unlike the HeartPy path, peak times are derived from the sample index
    (idx / fs) on a uniform grid and NOT read from the per-sample timestamps,
    which are chunked for LSL recordings and would quantize the RR intervals.

        Returns:
            peak_times_unix: original start timestamp + idx / fs (seconds), or None
            peak_times_ms:   peak times in ms relative to the first sample
            fs_hz:           sampling rate used
            signal_used:     cleaned ECG signal
            meta_rri_source: e.g. "neurokit2:neurokit"
            peak_idx:        sample indices of the R-peaks

    If `artifact_info` is a dict, it receives the peaks before artifact correction
    ("peak_idx_uncorrected") and "fs", so the number of corrected beats can be reported.
    """
    import neurokit2 as nk

    x_series = df[value_col] if value_col in df.columns else df.iloc[:, -1]
    x = pd.to_numeric(x_series, errors="coerce").to_numpy(dtype=float)

    t = None
    if time_col and time_col in df.columns:
        t = pd.to_numeric(df[time_col], errors="coerce").to_numpy(dtype=float)
        mask = np.isfinite(t) & np.isfinite(x)
        t, x = t[mask], x[mask]
        fs = estimate_fs_from_timestamps(t, fallback_fs_hz)
    else:
        x = x[np.isfinite(x)]
        fs = float(fallback_fs_hz)

    if x.size < int(2 * fs):
        raise ValueError(f"ECG segment too short for NeuroKit2: n={x.size}, fs={fs:.2f} Hz")

    try:
        x_clean = nk.ecg_clean(x, sampling_rate=fs, method=clean_method)
        _, info = nk.ecg_peaks(x_clean, sampling_rate=fs, method=peak_method,
                               correct_artifacts=correct_artifacts)
    except Exception as e:
        raise ValueError(f"neurokit2 peak detection failed: {e} (n_samples={x.size}, fs={fs:.2f})") from e

    if artifact_info is not None:
        artifact_info["peak_idx_uncorrected"] = np.asarray(info.get("ECG_R_Peaks_Uncorrected", info["ECG_R_Peaks"]), dtype=int)
        artifact_info["fs"] = float(fs)

    peak_idx = np.asarray(info["ECG_R_Peaks"], dtype=int)
    peak_idx = np.unique(peak_idx[(peak_idx >= 0) & (peak_idx < x.size)])

    if peak_idx.size < 2:
        raise ValueError(f"neurokit2 found only {peak_idx.size} R-peak(s)")

    peak_times_ms = peak_idx / fs * 1000.0
    peak_times_unix = (t[0] + peak_idx / fs) if t is not None else None

    meta_rri_source = f"neurokit2:{peak_method}" + ("+fixpeaks" if correct_artifacts else "")

    return peak_times_unix, peak_times_ms, float(fs), np.asarray(x_clean), meta_rri_source, peak_idx
