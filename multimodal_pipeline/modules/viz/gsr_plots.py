"""
GSR-specific plotting functions.
"""
from __future__ import annotations

from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from .time_series import plot_time_series


def plot_gsr_with_phasic_responses(
    data: pd.DataFrame,
    phasic_data: pd.DataFrame,
    baseline: float,
    out_path: Path,
    *,
    time_col: str = "Timestamp",
    baseline_col: str = "GSR_CONDUCTANCE",
    participant_id: str | None = None,
    task: str | None = None,
    dpi: int = 150,
) -> None:
    """
    Plot GSR signal with phasic responses highlighted and baseline shown.
    
    Parameters
    ----------
    data : pd.DataFrame
        Full GSR data with conductance values
    phasic_data : pd.DataFrame
        Phasic response data (subset of data)
    baseline : float
        Baseline conductance value (µS)
    out_path : Path
        Output path for PNG file
    time_col : str, default "Timestamp"
        Time column name
    baseline_col : str, default "GSR_CONDUCTANCE"
        GSR conductance column name
    participant_id : str, optional
        Participant ID for title
    task : str, optional
        Task name for title
    dpi : int, default 150
        Resolution of output plot
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    fig, ax = plt.subplots(figsize=(12, 6))
    
    # Get time and conductance values
    time = pd.to_numeric(data[time_col], errors="coerce")
    conductance = pd.to_numeric(data[baseline_col], errors="coerce")
    
    # Plot the full GSR signal
    ax.plot(time, conductance, label='GSR Conductance', color='blue', alpha=0.6, linewidth=1)
    
    # Highlight phasic responses if available
    if len(phasic_data) > 0 and time_col in phasic_data.columns and baseline_col in phasic_data.columns:
        phasic_time = pd.to_numeric(phasic_data[time_col], errors="coerce")
        phasic_conductance = pd.to_numeric(phasic_data[baseline_col], errors="coerce")
        ax.scatter(
            phasic_time, 
            phasic_conductance, 
            color='red', 
            label='Phasic Response', 
            alpha=0.7, 
            s=10,
            zorder=5  # Make sure phasic responses are on top
        )
    
    # Plot the baseline as a horizontal line
    ax.axhline(
        y=baseline, 
        color='green', 
        linestyle='--', 
        linewidth=2, 
        label=f'Baseline ({baseline:.2f} µS)',
        zorder=3
    )
    
    # Labels and title
    ax.set_xlabel('Time')
    ax.set_ylabel('GSR Conductance (µS)')
    
    title = 'GSR Conductance over Time with Phasic Responses'
    if participant_id and task:
        title = f'{participant_id} / {task} – {title}'
    elif participant_id:
        title = f'{participant_id} – {title}'
    elif task:
        title = f'{task} – {title}'
    
    ax.set_title(title)
    ax.legend(loc='upper right')
    ax.grid(True, linewidth=0.3, alpha=0.5)
    
    fig.tight_layout()
    fig.savefig(out_path, dpi=dpi)
    plt.close(fig)


def plot_gsr_deviations(
    data: pd.DataFrame,
    out_path: Path,
    *,
    time_col: str = "Timestamp",
    
    deviation_col: str = "deviation",
    participant_id: str | None = None,
    task: str | None = None,
    dpi: int = 150,
) -> None:
    """
    Plot GSR deviations from baseline over time.
    
    Parameters
    ----------
    data : pd.DataFrame
        GSR data with deviation column
    out_path : Path
        Output path for PNG file
    time_col : str, default "Timestamp"
        Time column name
    deviation_col : str, default "deviation"
        Deviation column name
    participant_id : str, optional
        Participant ID for title
    task : str, optional
        Task name for title
    dpi : int, default 150
        Resolution of output plot
    """
    title = "GSR Deviations from Baseline"
    if participant_id and task:
        title = f"{participant_id} / {task} – {title}"
    
    plot_time_series(
        df=data,
        x_col=time_col,
        y_col=deviation_col,
        out_path=out_path,
        title=title,
        xlabel="Time",
        ylabel="Deviation from Baseline (µS)",
        thresholds={"lower": 0.1, "upper": 3.0},  # Typical phasic response range
        dpi=dpi,
    )

