
from __future__ import annotations

from pathlib import Path
import pandas as pd

from .time_series import plot_time_series


def plot_rr_timeseries(
    df_rr: pd.DataFrame,
    out_path: Path,
    *,
    participant_id: str | None = None,
    dpi: int = 150,
) -> None:
    """
    Expect df_rr to have RR columns and a usable time column.
    - Time columns: 'time_s' preferred, else 'timestamp_s', else 'beat_time_ms'
    - RR columns: 'rr_ms' preferred, else 'RRI'
    - Validity columns: 'is_valid' or 'valid'
    """
    title = "RR intervals"
    if participant_id is not None:
        title = f"{participant_id} – RR intervals"

    time_col = None
    if "time_s" in df_rr.columns:
        time_col = "time_s"
    elif "timestamp_s" in df_rr.columns:
        time_col = "timestamp_s"
    elif "beat_time_ms" in df_rr.columns:
        df_rr = df_rr.copy()
        df_rr["time_s"] = df_rr["beat_time_ms"].astype(float) / 1000.0
        time_col = "time_s"

    if time_col is None:
        raise KeyError(
            "plot_rr_timeseries needs 'time_s', 'timestamp_s', or 'beat_time_ms'."
        )

    rr_col = "rr_ms" if "rr_ms" in df_rr.columns else "RRI" if "RRI" in df_rr.columns else None
    if rr_col is None:
        raise KeyError("plot_rr_timeseries needs 'rr_ms' (or 'RRI') column.")

    outlier_mask = None
    if "is_valid" in df_rr.columns:
        outlier_mask = ~df_rr["is_valid"]
    elif "valid" in df_rr.columns:
        outlier_mask = ~df_rr["valid"]

    plot_time_series(
        df=df_rr,
        x_col=time_col,
        y_col=rr_col,
        out_path=out_path,
        title=title,
        xlabel="Time [s]",
        ylabel="RR [ms]",
        thresholds={"lower": 300, "upper": 2000},  # just example defaults
        outlier_mask=outlier_mask,
        dpi=dpi,
        #max_points=5000,
    )
