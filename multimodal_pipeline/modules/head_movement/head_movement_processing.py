"""
Head movement data processing functions.

Handles low-level processing of head position, rotation, velocity, and angular velocity data.
"""
import numpy as np
import pandas as pd
from scipy import signal
import logging


def process_head_movement_data(df, sampling_rate=120.0, smoothing_window=5):
    """
    Process raw head movement data.
    
    Parameters
    ----------
    df : pd.DataFrame
        Raw head movement data with columns: Timestamp, PosX, PosY, PosZ,
        RotX, RotY, RotZ, RotW, VelX, VelY, VelZ, AngVelX, AngVelY, AngVelZ
    sampling_rate : float
        Sampling rate in Hz
    smoothing_window : int
        Window size for smoothing (in samples)
    
    Returns
    -------
    pd.DataFrame
        Processed head movement data with smoothed values and computed metrics
    """
    df = df.copy()
    
    # Ensure required columns exist
    required_cols = [
        'Timestamp', 'PosX', 'PosY', 'PosZ',
        'RotX', 'RotY', 'RotZ', 'RotW',
        'VelX', 'VelY', 'VelZ',
        'AngVelX', 'AngVelY', 'AngVelZ'
    ]
    
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")
    
    # Smooth position data to reduce noise
    pos_cols = ['PosX', 'PosY', 'PosZ']
    for col in pos_cols:
        df[f'{col}_smooth'] = _smooth_signal(df[col].values, smoothing_window)
    
    # Smooth rotation data
    rot_cols = ['RotX', 'RotY', 'RotZ', 'RotW']
    for col in rot_cols:
        df[f'{col}_smooth'] = _smooth_signal(df[col].values, smoothing_window)
    
    # Smooth velocity data
    vel_cols = ['VelX', 'VelY', 'VelZ']
    for col in vel_cols:
        df[f'{col}_smooth'] = _smooth_signal(df[col].values, smoothing_window)
    
    # Smooth angular velocity data
    ang_vel_cols = ['AngVelX', 'AngVelY', 'AngVelZ']
    for col in ang_vel_cols:
        df[f'{col}_smooth'] = _smooth_signal(df[col].values, smoothing_window)
    
    # Compute velocity magnitudes
    vel_magnitude = np.sqrt(
        df['VelX'].values**2 + 
        df['VelY'].values**2 + 
        df['VelZ'].values**2
    )
    df['velocity_magnitude'] = vel_magnitude
    df['velocity_magnitude_smooth'] = _smooth_signal(vel_magnitude, smoothing_window)
    
    # Compute angular velocity magnitudes
    ang_vel_magnitude = np.sqrt(
        df['AngVelX'].values**2 + 
        df['AngVelY'].values**2 + 
        df['AngVelZ'].values**2
    )
    df['angular_velocity_magnitude'] = ang_vel_magnitude
    df['angular_velocity_magnitude_smooth'] = _smooth_signal(ang_vel_magnitude, smoothing_window)
    
    # Mark data quality flags
    df['is_valid'] = True  # Start with all valid, can be modified by sanity checks
    
    return df


def compute_movement_features(df, velocity_threshold=0.03, angular_velocity_threshold=0.1):
    """
    Compute derived features from head movement data.
    
    Parameters
    ----------
    df : pd.DataFrame
        Processed head movement data
    velocity_threshold : float
        Threshold for detecting movement events (velocity magnitude in m/s)
        Default: 0.03 m/s (3 cm/s) - distinguishes intentional movement from noise
    angular_velocity_threshold : float
        Threshold for detecting rotation events (angular velocity magnitude in rad/s)
        Default: 0.1 rad/s (~5.7 degrees/s) - detects clear rotational movement
    
    Returns
    -------
    pd.DataFrame
        Dataframe with computed features
    """
    df = df.copy()
    
    # Detect movement events (when velocity exceeds threshold)
    df['is_moving'] = df['velocity_magnitude_smooth'] > velocity_threshold
    
    # Detect rotation events (when angular velocity exceeds threshold)
    df['is_rotating'] = df['angular_velocity_magnitude_smooth'] > angular_velocity_threshold
    
    # Position-based features
    pos_x = df['PosX_smooth'].values
    pos_y = df['PosY_smooth'].values
    pos_z = df['PosZ_smooth'].values
    
    # Distance from origin
    df['distance_from_origin'] = np.sqrt(pos_x**2 + pos_y**2 + pos_z**2)
    
    # Position variance in windows (e.g., 1-second windows)
    window_size = 120  # 1 second at 120 Hz
    df['position_variance_window'] = _compute_windowed_variance(
        df['distance_from_origin'].values,
        window_size
    )
    
    # Movement acceleration (rate of change of velocity)
    vel_magnitude = df['velocity_magnitude_smooth'].values
    df['velocity_acceleration'] = np.gradient(vel_magnitude)
    
    return df


def _smooth_signal(signal_data, window_size):
    """
    Apply Savitzky-Golay smoothing to signal data.
    
    Parameters
    ----------
    signal_data : np.ndarray
        Input signal
    window_size : int
        Smoothing window size (must be odd)
    
    Returns
    -------
    np.ndarray
        Smoothed signal
    """
    # Ensure window size is odd
    if window_size % 2 == 0:
        window_size += 1
    
    # Ensure window size is not larger than signal
    if window_size > len(signal_data):
        window_size = len(signal_data) if len(signal_data) % 2 == 1 else len(signal_data) - 1
    
    # Handle edge cases
    if window_size < 3:
        return signal_data
    
    try:
        return signal.savgol_filter(signal_data, window_size, polyorder=2)
    except Exception as e:
        logging.warning(f"Savgol smoothing failed: {e}. Using moving average instead.")
        return pd.Series(signal_data).rolling(window=window_size, center=True).mean().values


def _compute_windowed_variance(data, window_size):
    """
    Compute variance in sliding windows.
    
    Parameters
    ----------
    data : np.ndarray
        Input data
    window_size : int
        Window size
    
    Returns
    -------
    np.ndarray
        Windowed variance for each point
    """
    variance = np.zeros_like(data, dtype=float)
    
    for i in range(len(data)):
        start = max(0, i - window_size // 2)
        end = min(len(data), i + window_size // 2 + 1)
        variance[i] = np.var(data[start:end])
    
    return variance
