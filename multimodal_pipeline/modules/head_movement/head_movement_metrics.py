"""
Head movement metrics calculation.

Computes derived metrics from processed head movement data.
"""
import numpy as np
import pandas as pd
from scipy import signal
import logging


def compute_head_movement_metrics(df, requested_metrics):
    """
    Compute head movement metrics based on requested types.
    
    Parameters
    ----------
    df : pd.DataFrame
        Processed head movement data with features
    requested_metrics : list
        List of metric names to compute. Supported metrics:
        - "movement_intensity": Average velocity magnitude
        - "movement_frequency": Number of movement events per minute
        - "positional_stability": Inverse of position variance
        - "rotation_smoothness": Smoothness of rotational movement
        - "movement_range": Total range of head positions
        - "activity_level": Percentage of time spent moving
        - "mean_velocity": Mean velocity magnitude
        - "max_velocity": Maximum velocity magnitude
        - "mean_angular_velocity": Mean angular velocity
        - "max_angular_velocity": Maximum angular velocity
    
    Returns
    -------
    dict
        Dictionary with computed metrics
    """
    metrics = {}
    
    for metric in requested_metrics:
        try:
            if metric.lower() == "movement_intensity":
                metrics["movement_intensity"] = _compute_movement_intensity(df)
            
            elif metric.lower() == "movement_frequency":
                metrics["movement_frequency"] = _compute_movement_frequency(df)
            
            elif metric.lower() == "positional_stability":
                metrics["positional_stability"] = _compute_positional_stability(df)
            
            elif metric.lower() == "rotation_smoothness":
                metrics["rotation_smoothness"] = _compute_rotation_smoothness(df)
            
            elif metric.lower() == "movement_range":
                metrics["movement_range"] = _compute_movement_range(df)
            
            elif metric.lower() == "activity_level":
                metrics["activity_level"] = _compute_activity_level(df)
            
            elif metric.lower() == "mean_velocity":
                metrics["mean_velocity"] = float(df['velocity_magnitude_smooth'].mean())
            
            elif metric.lower() == "max_velocity":
                metrics["max_velocity"] = float(df['velocity_magnitude_smooth'].max())
            
            elif metric.lower() == "mean_angular_velocity":
                metrics["mean_angular_velocity"] = float(df['angular_velocity_magnitude_smooth'].mean())
            
            elif metric.lower() == "max_angular_velocity":
                metrics["max_angular_velocity"] = float(df['angular_velocity_magnitude_smooth'].max())
            
            else:
                logging.warning(f"Unknown head movement metric: {metric}")
        
        except Exception as e:
            logging.error(f"Error computing metric {metric}: {str(e)}")
    
    return metrics


def _compute_movement_intensity(df):
    """
    Compute average velocity magnitude (movement intensity).
    
    Returns
    -------
    float
        Mean velocity magnitude
    """
    if 'velocity_magnitude_smooth' not in df.columns:
        return None
    
    return float(df['velocity_magnitude_smooth'].mean())


def _compute_movement_frequency(df):
    """
    Compute frequency of movement events per minute.
    
    Returns
    -------
    float
        Number of movement events per minute
    """
    if 'is_moving' not in df.columns:
        return None
    
    # Count transitions from not moving to moving
    is_moving = df['is_moving'].values
    transitions = np.diff(is_moving.astype(int))
    movement_starts = np.sum(transitions == 1)
    
    # Get duration in minutes
    if 'Timestamp' in df.columns:
        duration_sec = (df['Timestamp'].iloc[-1] - df['Timestamp'].iloc[0]) / 1e6
        if duration_sec > 0:
            duration_min = duration_sec / 60
            return float(movement_starts / duration_min)
    
    return float(movement_starts)


def _compute_positional_stability(df):
    """
    Compute positional stability (inverse of position variance).
    
    Lower position variance = higher stability.
    
    Returns
    -------
    float
        Stability metric (1 / variance). Higher is more stable.
    """
    if 'distance_from_origin' not in df.columns:
        return None
    
    pos_variance = df['distance_from_origin'].var()
    
    if pos_variance == 0:
        return float('inf')
    
    return float(1.0 / pos_variance)


def _compute_rotation_smoothness(df):
    """
    Compute smoothness of rotational movement.
    
    Uses spectral analysis - smoother motion has more power at low frequencies.
    
    Returns
    -------
    float
        Smoothness metric (0-1, higher is smoother)
    """
    if 'angular_velocity_magnitude_smooth' not in df.columns:
        return None
    
    ang_vel = df['angular_velocity_magnitude_smooth'].values
    
    # Compute FFT
    fft = np.fft.fft(ang_vel - np.mean(ang_vel))
    freqs = np.fft.fftfreq(len(ang_vel))
    power = np.abs(fft)**2
    
    # Find power in low frequencies (first 20% of spectrum)
    low_freq_power = np.sum(power[:len(power)//5])
    total_power = np.sum(power)
    
    if total_power == 0:
        return 0.0
    
    return float(low_freq_power / total_power)


def _compute_movement_range(df):
    """
    Compute total range of head position.
    
    Returns
    -------
    float
        Distance from min to max position
    """
    if 'distance_from_origin' not in df.columns:
        return None
    
    dist = df['distance_from_origin'].values
    return float(np.max(dist) - np.min(dist))


def _compute_activity_level(df):
    """
    Compute percentage of time spent moving.
    
    Returns
    -------
    float
        Percentage (0-100) of samples where head is moving
    """
    if 'is_moving' not in df.columns:
        return None
    
    activity = np.sum(df['is_moving']) / len(df) * 100
    return float(activity)
