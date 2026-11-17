

import numpy as np
import pandas as pd


def detect_rri_units(
    df: pd.DataFrame,
    tolerance: float = 0.024,           # TODO rename tolerance to expacted_gap or something? also add tolerance to expected_gap (noise_margin maybe?) Noise margin would generally tell how much noise is allowed - better to have that in a dedicated cleaning module ... //FIXME //TODO give inout option of how much noise is tolerated? 
) -> dict:
    """
    Detect whether df['RRI'] is in ms or Polar ticks based on
    sum(RRI) vs duration from timestamps.

    Idea:
      - duration_ms = (last_ts - first_ts) * 1000
      - sum_rri_ms = sum(RRI)  (interpret as ms)
      - if relative difference <= tolerance -> 'ms'
      - else -> 'ticks'

    Returns dict:
      - unit: 'ms', 'ticks', or 'unknown'
      - rel_diff_ms: relative mismatch if interpreted as ms
    """
    if "Timestamp" not in df.columns or "RRI" not in df.columns:
        raise KeyError("Expected 'Timestamp' and 'RRI' in df.")

    ts = df["Timestamp"].to_numpy(dtype=float)
    rri = df["RRI"].to_numpy(dtype=float)

    if ts.size < 2 or rri.size == 0:
        return {"unit": "unknown", "rel_diff_ms": np.nan}

    duration_ms = (ts[-1] - ts[0]) * 1000.0
    if duration_ms <= 0:
        return {"unit": "unknown", "rel_diff_ms": np.nan}

    sum_rri_ms = float(np.nansum(rri))
    rel_diff_ms = abs(sum_rri_ms - duration_ms) / duration_ms

    if rel_diff_ms <= tolerance:
        unit = "ms"
    else:
        unit = "ticks"

    return {"unit": unit, "rel_diff_ms": float(rel_diff_ms)}




    # TODO add confidence score 


"""
    # confidence assuming "ms"
    conf_ms = max(0.0, 1.0 - rel_diff / tolerance)
    conf_ms = min(1.0, conf_ms)

    # confidence that it is ticks
    conf_ticks = 1.0 - conf_ms

    if conf_ms >= conf_ticks:
        unit = "ms"
        confidence = conf_ms
    else:
        unit = "ticks"
        confidence = conf_ticks

    return {
        "unit": unit,
        "confidence": float(confidence),
        "rel_diff": float(rel_diff),
    }

"""