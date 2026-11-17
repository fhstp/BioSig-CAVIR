from __future__ import annotations
import numpy as np
import pandas as pd

def rpeaks_to_rr(peak_times_ms: np.ndarray,
                 peak_times_unix: np.ndarray | None = None,
                 ) -> pd.DataFrame:
    """
    Build an RR table from peak times.

    Parameters
    ----------
    peak_times_ms : np.ndarray
        Peak times in ms, relative to the first sample used for detection.
    peak_times_unix : np.ndarray or None
        Original timestamps at each peak (same units as input to detection),
        or None if not available.

    Returns
    -------
    DataFrame with columns:
      - beat_time_ms : relative time (ms) of the *end* of each RR interval
      - timestamp_s  : same as beat_time_ms, but in seconds (for compatibility)
      - rr_ms        : RR interval in ms
      - timestamp_unix (optional): original timestamp at end of interval
    """
    
    
    if peak_times_ms is None or peak_times_ms.size < 2:
        cols = ["beat_time_ms", "timestamp_s", "rr_ms", "valid"]
        if peak_times_unix is not None:
            cols.insert(-1, "timestamp_unix")
        return pd.DataFrame(columns=cols)

    # RR intervals between successive peaks (ms)
    rr_ms = np.diff(peak_times_ms).astype(float)

    # Relative time of each RR, referenced to the first peak
    beat_time_ms = (peak_times_ms[1:] - peak_times_ms[0]).astype(float)

    data = {
        "beat_time_ms": beat_time_ms,
        "timestamp_s": beat_time_ms / 1000.0, 
        "rr_ms": rr_ms
    }

    if peak_times_unix is not None:
        # one Unix timestamp per RR, aligned to the *end* of each interval
        data["timestamp_unix"] = peak_times_unix[1:]

    return pd.DataFrame(data)