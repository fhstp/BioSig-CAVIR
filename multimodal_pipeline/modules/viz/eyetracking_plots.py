from __future__ import annotations

from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from .time_series import plot_time_series


def plot_gaze_velocity_timeseries(
    df: pd.DataFrame,
    out_path: Path,
    *,
    vel_col: str = "vel_raw_l",
    time_col: str = "t_rel",
    fix_col: str = "fix",
    sac_col: str = "sac",
    participant_id: str | None = None,
    task: str | None = None,
    dpi: int = 150,
) -> None:
    """
    Plot gaze velocity over time with fixations and saccades highlighted.
    
    Parameters
    ----------
    df : pd.DataFrame
        Segmented dataframe with velocity, fix, sac columns
    out_path : Path
        Output path for PNG file
    vel_col : str
        Velocity column name
    time_col : str
        Time column name (relative time in seconds)
    fix_col : str
        Fixation mask column name
    sac_col : str
        Saccade mask column name
    participant_id : str, optional
        Participant ID for title
    task : str, optional
        Task name for title
    dpi : int
        Resolution of output plot
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    fig, ax = plt.subplots(figsize=(12, 5))
    
    # Get data
    time = pd.to_numeric(df[time_col], errors="coerce")
    velocity = pd.to_numeric(df[vel_col], errors="coerce")
    
    # Plot velocity
    ax.plot(time, velocity, linewidth=0.5, color="gray", alpha=0.7, label="Velocity")
    
    # Highlight fixations (low velocity regions)
    if fix_col in df.columns:
        fix_mask = df[fix_col].astype(bool)
        fix_times = time[fix_mask]
        fix_vels = velocity[fix_mask]
        if len(fix_times) > 0:
            ax.scatter(fix_times, fix_vels, s=1, color="green", alpha=0.3, label="Fixation")
    
    # Highlight saccades (high velocity regions)
    if sac_col in df.columns:
        sac_mask = df[sac_col].astype(bool)
        sac_times = time[sac_mask]
        sac_vels = velocity[sac_mask]
        if len(sac_times) > 0:
            ax.scatter(sac_times, sac_vels, s=1, color="red", alpha=0.3, label="Saccade")
    
    # Add velocity threshold line (typical saccade threshold ~30 deg/s)
    ax.axhline(30, linestyle="--", linewidth=1, color="orange", alpha=0.5, label="Threshold (30 deg/s)")
    
    title = "Gaze Velocity with Fixations and Saccades"
    if participant_id and task:
        title = f"{participant_id} / {task} – {title}"
    elif participant_id:
        title = f"{participant_id} – {title}"
    
    ax.set_xlabel("Time [s]")
    ax.set_ylabel("Velocity [deg/s]")
    ax.set_title(title)
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(True, linewidth=0.3, alpha=0.5)
    
    fig.tight_layout()
    fig.savefig(out_path, dpi=dpi)
    plt.close(fig)


def plot_pupil_diameter_timeseries(
    df: pd.DataFrame,
    out_path: Path,
    *,
    time_col: str = "t_rel",
    pupil_col: str | None = None,
    participant_id: str | None = None,
    task: str | None = None,
    dpi: int = 150,
) -> None:
    """
    Plot pupil diameter over time.
    
    Parameters
    ----------
    df : pd.DataFrame
        Dataframe with pupil diameter columns
    out_path : Path
        Output path for PNG file
    time_col : str
        Time column name
    pupil_col : str, optional
        Pupil column to plot. If None, uses mean of pupil_l_mm and pupil_r_mm if available.
    participant_id : str, optional
        Participant ID for title
    task : str, optional
        Task name for title
    dpi : int
        Resolution of output plot
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Determine which pupil column to use
    if pupil_col is None:
        if "pupil_l_mm" in df.columns and "pupil_r_mm" in df.columns:
            pupil = (df["pupil_l_mm"] + df["pupil_r_mm"]) / 2.0
            pupil_label = "Pupil diameter (mean both eyes)"
        elif "pupil_l_mm" in df.columns:
            pupil = df["pupil_l_mm"]
            pupil_label = "Pupil diameter (left eye)"
        elif "pupil_r_mm" in df.columns:
            pupil = df["pupil_r_mm"]
            pupil_label = "Pupil diameter (right eye)"
        else:
            raise ValueError("No pupil diameter columns found in dataframe")
    else:
        pupil = df[pupil_col]
        pupil_label = f"Pupil diameter ({pupil_col})"
    
    plot_time_series(
        df=df.assign(**{pupil_label: pupil}),
        x_col=time_col,
        y_col=pupil_label,
        out_path=out_path,
        title=f"{participant_id} / {task} – Pupil Diameter" if (participant_id and task) else "Pupil Diameter",
        xlabel="Time [s]",
        ylabel="Pupil Diameter [mm]",
        thresholds={"lower": 2.0, "upper": 8.0},  # Typical pupil range
        dpi=dpi,
    )


def plot_gaze_2d(
    df: pd.DataFrame,
    out_path: Path,
    *,
    x_col: str = "gaze_2d_x",
    y_col: str = "gaze_2d_y",
    time_col: str = "t_rel",
    fix_col: str | None = "fix",
    participant_id: str | None = None,
    task: str | None = None,
    dpi: int = 150,
) -> None:
    """
    Plot 2D gaze position (scanpath) with fixations highlighted.
    
    Parameters
    ----------
    df : pd.DataFrame
        Dataframe with 2D gaze coordinates
    out_path : Path
        Output path for PNG file
    x_col : str
        X coordinate column (e.g., screen X in pixels or normalized)
    y_col : str
        Y coordinate column
    time_col : str
        Time column for coloring by time
    fix_col : str, optional
        Fixation mask column. If provided, fixations are highlighted.
    participant_id : str, optional
        Participant ID for title
    task : str, optional
        Task name for title
    dpi : int
        Resolution of output plot
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    if x_col not in df.columns or y_col not in df.columns:
        raise ValueError(f"Required columns {x_col} and/or {y_col} not found in dataframe")
    
    fig, ax = plt.subplots(figsize=(10, 8))
    
    x = pd.to_numeric(df[x_col], errors="coerce")
    y = pd.to_numeric(df[y_col], errors="coerce")
    time = pd.to_numeric(df[time_col], errors="coerce")
    
    # Plot scanpath (line connecting gaze points)
    valid = x.notna() & y.notna()
    if valid.sum() > 0:
        ax.plot(x[valid], y[valid], linewidth=0.5, color="lightblue", alpha=0.3, label="Gaze path")
        
        # Color by time (if time data available)
        if time_col in df.columns and time.notna().any():
            scatter = ax.scatter(x[valid], y[valid], c=time[valid], cmap="viridis", 
                               s=1, alpha=0.5, label="Gaze points")
            plt.colorbar(scatter, ax=ax, label="Time [s]")
        
        # Highlight fixations if available
        if fix_col and fix_col in df.columns:
            fix_mask = df[fix_col].astype(bool) & valid
            if fix_mask.sum() > 0:
                ax.scatter(x[fix_mask], y[fix_mask], s=10, color="red", 
                          alpha=0.6, marker="o", label="Fixations", zorder=5)
    
    title = "Gaze Position (2D Scanpath)"
    if participant_id and task:
        title = f"{participant_id} / {task} – {title}"
    elif participant_id:
        title = f"{participant_id} – {title}"
    
    ax.set_xlabel(f"{x_col} [px or normalized]")
    ax.set_ylabel(f"{y_col} [px or normalized]")
    ax.set_title(title)
    ax.legend(loc="best", fontsize=8)
    ax.grid(True, linewidth=0.3, alpha=0.5)
    ax.set_aspect("equal", adjustable="box")
    
    fig.tight_layout()
    fig.savefig(out_path, dpi=dpi)
    plt.close(fig)


def plot_event_timeline(
    df: pd.DataFrame,
    out_path: Path,
    *,
    time_col: str = "t_rel",
    fix_col: str = "fix",
    sac_col: str = "sac",
    blink_col: str | None = "blink",
    participant_id: str | None = None,
    task: str | None = None,
    dpi: int = 150,
) -> None:
    """
    Plot event timeline showing when fixations, saccades, and blinks occurred.
    
    Parameters
    ----------
    df : pd.DataFrame
        Segmented dataframe with event columns
    out_path : Path
        Output path for PNG file
    time_col : str
        Time column name
    fix_col : str
        Fixation mask column
    sac_col : str
        Saccade mask column
    blink_col : str, optional
        Blink mask column
    participant_id : str, optional
        Participant ID for title
    task : str, optional
        Task name for title
    dpi : int
        Resolution of output plot
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    fig, ax = plt.subplots(figsize=(12, 4))
    
    time = pd.to_numeric(df[time_col], errors="coerce")
    
    y_pos = 0
    events = []
    
    # Fixations
    if fix_col in df.columns:
        fix_mask = df[fix_col].astype(bool)
        fix_runs = _find_runs(fix_mask)
        for start, end in fix_runs:
            if end < len(time):
                ax.barh(y_pos, time.iloc[end] - time.iloc[start], left=time.iloc[start],
                       height=0.6, color="green", alpha=0.6, label="Fixation" if start == fix_runs[0][0] else "")
        y_pos += 1
        events.append("Fixation")
    
    # Saccades
    if sac_col in df.columns:
        sac_mask = df[sac_col].astype(bool)
        sac_runs = _find_runs(sac_mask)
        for start, end in sac_runs:
            if end < len(time):
                ax.barh(y_pos, time.iloc[end] - time.iloc[start], left=time.iloc[start],
                       height=0.6, color="red", alpha=0.6, label="Saccade" if start == sac_runs[0][0] else "")
        y_pos += 1
        events.append("Saccade")
    
    # Blinks
    if blink_col and blink_col in df.columns:
        blink_mask = df[blink_col].astype(bool)
        blink_runs = _find_runs(blink_mask)
        for start, end in blink_runs:
            if end < len(time):
                ax.barh(y_pos, time.iloc[end] - time.iloc[start], left=time.iloc[start],
                       height=0.6, color="orange", alpha=0.6, label="Blink" if start == blink_runs[0][0] else "")
        y_pos += 1
        events.append("Blink")
    
    title = "Eye Movement Events Timeline"
    if participant_id and task:
        title = f"{participant_id} / {task} – {title}"
    elif participant_id:
        title = f"{participant_id} – {title}"
    
    ax.set_xlabel("Time [s]")
    ax.set_ylabel("Event Type")
    ax.set_yticks(range(len(events)))
    ax.set_yticklabels(events)
    ax.set_title(title)
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(True, linewidth=0.3, alpha=0.5, axis="x")
    
    fig.tight_layout()
    fig.savefig(out_path, dpi=dpi)
    plt.close(fig)


def _find_runs(mask: pd.Series) -> list[tuple[int, int]]:
    """Find contiguous runs of True values in a boolean series. Returns (start_idx, end_idx) tuples."""
    runs = []
    in_run = False
    start = 0
    
    for i, val in enumerate(mask):
        if val and not in_run:
            in_run = True
            start = i
        elif not val and in_run:
            in_run = False
            runs.append((start, i - 1))
    
    if in_run:
        runs.append((start, len(mask) - 1))
    
    return runs

