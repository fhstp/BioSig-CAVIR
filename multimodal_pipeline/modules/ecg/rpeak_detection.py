from __future__ import annotations
import numpy as np
import pandas as pd
import heartpy as hp

def detect_rpeaks_from_ecg(
        df: pd.DataFrame,
        #time_col: str | None = "Timestamp",  #BUG FIXME heartpy breaks with actual Timestamps so this code generates new unniform time based on sampling rate
        time_col=None,      
        value_col: str | None = "HR",
        has_header: bool = True,
        fallback_fs_hz: float | None = None,
        bandpass: tuple[float, float] = (5.0, 25.0),
        bpm_range: tuple[int, int] = (40, 200),
) -> tuple[np.ndarray | None, np.ndarray, float, np.ndarray, str, np.ndarray]:
    """
    Detect R-peaks from a raw ECG-like signal using HeartPy.

        Returns:
            peak_times_unix: np.ndarray or None
                The original timestamp values (same units as input) at each detected peak
                or None if no original timestamps were provided.
            peak_times_ms: np.ndarray
                Peak times in milliseconds relative to the first sample used for detection.
            fs_hz: float
                Inferred sample rate (Hz).
            signal_used: np.ndarray
                The filtered/normalized signal that detection ran on.
            meta_rri_source: str
                Name of algorithm used (for metadata purposes).
            peak_idx: np.ndarray
                Indices into the (possibly masked) signal where peaks were detected.
    """
    # --- read CSV headers vs no-headers  ---
    if has_header:
        # Normalize names
        cols = [str(c).strip() for c in df.columns]
        df.columns = cols
        t_series = df[time_col] if (time_col and time_col in df.columns) else df.iloc[:, 0]
        x_series = df[value_col] if (value_col and value_col in df.columns) else df.iloc[:, -1]
    else:
        t_series = df.iloc[:, 1]
        x_series = df.iloc[:, -1]

    x_raw = pd.to_numeric(x_series, errors="coerce").to_numpy()
    # Your notebook synthesized time at ~130 Hz; here we prefer real timestamps if present.
    # If timestamps are unreliable or absent, allow a fallback fs.
    peak_times_unix = None
    if time_col and has_header and time_col in df.columns:
        # preserve the original timestamp vector (numeric)
        t = pd.to_numeric(t_series, errors="coerce").to_numpy()
        mask = np.isfinite(t) & np.isfinite(x_raw)
        t, x = t[mask], x_raw[mask]
        # infer units (assume milliseconds if median diff > 1)
        dt = np.diff(t)
        dt = dt[dt > 0]
        if dt.size == 0:
            raise ValueError("Time column not increasing or invalid.")
        dt_med = float(np.median(dt))
        unit_per_sec = 1000.0 if dt_med > 1.0 else 1.0
        fs = unit_per_sec / dt_med


# --------------- test -------------------

        if (fs > 300 or fs < 10) and fallback_fs_hz is not None:
            # Timestamps are unusable per sample (e.g. LSL chunks: ~10 us steps inside a
            # chunk, ~0.5 s jumps between chunks). Rebuild a uniform time grid from the
            # sample index, otherwise RR intervals get quantized to the chunk boundaries.
            print(f"[rpeak_det] fs={fs:.1f} Hz looks suspicious, falling back to {fallback_fs_hz} Hz")
            fs = float(fallback_fs_hz)
            t_ms = np.arange(x.size) / fs * 1000.0
            t = t[0] + t_ms / (1000.0 if unit_per_sec == 1.0 else 1.0)
        else:
            # t contains original timestamps (seconds or milliseconds depending on data).
            # t_ms is the times in milliseconds relative to the first kept sample.
            t_ms = (t - t[0]) * (1000.0 if unit_per_sec == 1.0 else 1.0)
        # Also keep absolute/original timestamps so callers can map peaks back to unix time
        peak_times_unix = t
    else:
        if fallback_fs_hz is None:
            # fallback to your notebook’s ~130 Hz synthesis (step=0.007692… s)
            fallback_fs_hz = 130.0
        n = x_raw.size
        t_ms = (np.arange(n) / float(fallback_fs_hz)) * 1000.0
        x = x_raw
        fs = fallback_fs_hz

    # --- filter (5–25 Hz band) ---
    # Validate sampling rate vs requested bandpass to avoid filter design errors
    bp_lo, bp_hi = float(bandpass[0]), float(bandpass[1])
    if fs <= 0 or not np.isfinite(fs):
        raise ValueError(f"Invalid inferred sampling rate: {fs}")
    nyq = float(fs) / 2.0
    if bp_hi >= nyq:
        raise ValueError(
            f"Bandpass upper cutoff ({bp_hi} Hz) must be < Nyquist ({nyq:.2f} Hz). "
            f"Use a lower upper-frequency or increase the sampling rate."
        )

    # Require a minimum number of samples to run filtering/detection
    if x.size < 10:
        raise ValueError(f"Input signal too short for R-peak detection (n={x.size}).")


    try:
        x_filt = hp.filter_signal(x, cutoff=list(bandpass), sample_rate=fs, order=3, filtertype='bandpass')
    except Exception as e:
        raise ValueError(
            f"filtering failed: {e} (n_samples={x.size}, fs={fs}, bandpass={bandpass})"
        ) from e




# --------- test -------------------

    min_window_sec = 0.75  # HeartPy default windowsize
    min_len = int(min_window_sec * fs) + 1
    if x_filt.size < min_len:
        raise ValueError(
            f"ECG segment too short for HeartPy: n={x_filt.size}, "
            f"fs={fs:.2f} Hz, need >= {min_len} samples"
        )



    # --- heartpy process with high precision & wider bpm range ---
    try:
        wd, measures = hp.process(x_filt, sample_rate=fs, bpmmin=bpm_range[0], bpmmax=bpm_range[1], high_precision=True)
    except Exception as e:
        raise ValueError(
            f"heartpy processing failed: {e} (n_samples={x_filt.size}, fs={fs}, bpm_range={bpm_range})"
        ) from e
    peak_idx_hp = np.asarray(wd['peaklist'], dtype=int)
    peak_idx_hp.sort()


    peak_idx = peak_idx_hp

    # ── Post-processing (ported from Analysis.ipynb) ─────────────────────
    #
    # HeartPy alone can leave duplicate / spurious detections that inflate
    # RR-interval variability.  The original notebook applied two clean-up
    # steps *before* computing RR intervals; the pipeline was missing both,
    # which caused RMSSD values ~6-7x too high.

    # 1) Non-Maximum Suppression (NMS) with refractory period
    #    Keep only the tallest peak inside each window whose width equals
    #    the minimum RR gap (derived from bpm_max, e.g. 200 bpm → 300 ms).
    #    This removes duplicate detections within the same heartbeat.
    min_gap_ms = 60000.0 / bpm_range[1]                       # e.g. 300 ms
    min_gap_samples = max(1, int((min_gap_ms / 1000.0) * fs))

    if peak_idx.size > 1:
        order_desc = np.argsort(x_filt[peak_idx])[::-1]       # tallest first
        selected: list[int] = []
        for p in peak_idx[order_desc]:
            if not selected or np.min(np.abs(np.array(selected) - p)) >= min_gap_samples:
                selected.append(int(p))
        peak_idx = np.sort(np.asarray(selected, dtype=int))

    # 2) RR-interval sanity filter
    #    Drop peaks whose resulting RR interval falls outside the plausible
    #    physiological range [rr_lo, rr_hi] derived from bpm_range.
    if peak_idx.size >= 2:
        peak_t = t_ms[peak_idx]
        rr_ms_raw = np.diff(peak_t)
        rr_lo_ms = 60000.0 / bpm_range[1]                     # fastest  (e.g. 300 ms)
        rr_hi_ms = 60000.0 / bpm_range[0]                     # slowest  (e.g. 1500 ms)
        valid_rr = (rr_ms_raw >= rr_lo_ms) & (rr_ms_raw <= rr_hi_ms)
        # Keep the first peak unconditionally; then keep the second peak
        # of each *valid* RR pair.
        keep = np.hstack([True, valid_rr])
        peak_idx = peak_idx[keep]

    # ── end post-processing ──────────────────────────────────────────────

    meta_rri_source = "heartpy"

    # If we have original timestamps (peak_times_unix), map peaks to those absolute times
    if peak_times_unix is not None:
        peak_times_unix_out = peak_times_unix[peak_idx]
    else:
        peak_times_unix_out = None

    # peak times in ms relative to first used sample
    peak_times_ms = t_ms[peak_idx]

    return peak_times_unix_out, peak_times_ms, float(fs), x_filt, meta_rri_source, peak_idx
