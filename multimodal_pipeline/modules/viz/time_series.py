
from __future__ import annotations

from pathlib import Path
from typing import Mapping, Iterable

import matplotlib.pyplot as plt
import pandas as pd
import numpy as np


def plot_time_series(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    out_path: Path,
    *,
    title: str | None = None,
    xlabel: str | None = None,
    ylabel: str | None = None,
    thresholds: Mapping[str, float] | None = None,  # e.g. {"lower": 300, "upper": 2000}
    outlier_mask: Iterable[bool] | None = None,             # -> #TODO df_rr[valid]
    highlight_idx: Iterable[int] | None = None,
    highlight_color: str = "red",
    highlight_size: int = 12,
    dpi: int = 150, # resolution of the plot
    # TODO #FIXEM maybe later max_points: int | None = None,  # downsample to this many points if > max_points
) -> None:
    """
    Generic 'plot a column over x' helper.

    - df[x_col], df[y_col]: your time series
    - thresholds: optional dict with "lower"/"upper"
    - outlier_mask: True for outliers (will be highlighted)
    """

    # TODO later 
    '''
    if max_points is not None and len(df) > max_points:
        # simple downsampling: take every n-th sample
        step = int(np.ceil(len(df) / max_points))
        df = df.iloc[::step]

        if outlier_mask is not None:
            outlier_mask = np.asarray(list(outlier_mask))[::step]
    '''

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(10, 4))     # figure container and axes (width in inches)

    # ---- X-axis handling: avoid epoch-offset plots ---------------------------------
    # Matplotlib may display large epoch seconds with an offset (e.g., "+1.7e9"),
    # which is visually distracting for QC plots. If the x values look like epoch-like
    # timestamps, plot relative time starting at 0.
    x_raw = pd.to_numeric(df.get(x_col), errors="coerce")
    use_relative_time = False
    if x_raw is not None and x_raw.notna().any():
        x_med = float(np.nanmedian(x_raw.values))
        x_min = float(np.nanmin(x_raw.values))
        x_max = float(np.nanmax(x_raw.values))
        x_span = x_max - x_min

        # Heuristic: "timestamp-like" column name + very large magnitude values.
        name_hint = x_col.lower()
        looks_like_time = any(k in name_hint for k in ("time", "timestamp", "ts"))
        if looks_like_time and abs(x_med) >= 1e6 and x_span > 0:
            use_relative_time = True

    if use_relative_time:
        first_valid = x_raw.dropna().iloc[0]
        x_plot = x_raw - first_valid
        x_label_default = "Time [s]"
    else:
        x_plot = x_raw
        x_label_default = x_col

    # main signal
    ax.plot(x_plot, df[y_col], linewidth=1)

    # thresholds as horizontal lines / band
    if thresholds:
        lower = thresholds.get("lower")
        upper = thresholds.get("upper")

        if lower is not None:
            ax.axhline(lower, linestyle="--", linewidth=1)
        if upper is not None:
            ax.axhline(upper, linestyle="--", linewidth=1)
        if lower is not None and upper is not None:
            ax.axhspan(lower, upper, alpha=0.1)

    # outliers as scatter
    if outlier_mask is not None:
        mask = np.asarray(list(outlier_mask), dtype=bool)
        if mask.shape[0] == len(df):
            outliers = df[mask]
            ax.scatter(
                x_plot[mask],
                outliers[y_col],
                s=10,
            )

    # highlight specific indices (e.g., detected peaks)
    if highlight_idx is not None:
        idx = np.asarray(list(highlight_idx), dtype=int)
        idx = idx[(idx >= 0) & (idx < len(df))]
        if idx.size > 0:
            points = df.iloc[idx]
            ax.scatter(
                x_plot.iloc[idx],
                points[y_col],
                s=highlight_size,
                color=highlight_color,
                zorder=3,
            )

    ax.set_xlabel(xlabel or x_label_default)
    ax.set_ylabel(ylabel or y_col)
    if title:
        ax.set_title(title)

    ax.grid(True, linewidth=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=dpi)
    plt.close(fig)
