"""
Head movement sanity checks.

Validates the integrity and quality of head movement data.
"""
import numpy as np
import pandas as pd
import logging


def sanity_check_head_movement_raw(df):
    """
    Perform sanity checks on raw head movement data.
    
    Parameters
    ----------
    df : pd.DataFrame
        Raw head movement data
    
    Returns
    -------
    dict
        Dictionary with sanity check results
    """
    results = {
        "num_samples": len(df),
        "has_missing_values": bool(df.isnull().any().any()),
        "num_missing_values": int(df.isnull().sum().sum()),
        "timestamp_monotonic": _check_timestamp_monotonic(df),
        "velocity_plausible": _check_velocity_plausibility(df),
        "position_plausible": _check_position_plausibility(df),
        "rotation_valid": _check_rotation_validity(df),
    }
    
    return results


def _check_timestamp_monotonic(df):
    """Check if timestamps are monotonically increasing."""
    if 'Timestamp' not in df.columns:
        return None
    
    timestamps = df['Timestamp'].values
    return bool(np.all(np.diff(timestamps) > 0))


def _check_velocity_plausibility(df):
    """
    Check if velocity values are within plausible ranges.
    
    Head movement velocities should typically be < 5000 units/second
    (depends on your coordinate system and units)
    """
    vel_cols = ['VelX', 'VelY', 'VelZ']
    
    for col in vel_cols:
        if col not in df.columns:
            return None
        
        vel_magnitude = np.sqrt(
            df['VelX'].values**2 + 
            df['VelY'].values**2 + 
            df['VelZ'].values**2
        )
        
        # Check for unreasonable velocities (> 100,000 units/sec)
        if np.any(vel_magnitude > 100000):
            logging.warning(f"Implausible velocity detected in {col}")
            return False
    
    return True


def _check_position_plausibility(df):
    """
    Check if position values are within plausible ranges.
    
    Position should vary but not too drastically between samples.
    """
    pos_cols = ['PosX', 'PosY', 'PosZ']
    
    for col in pos_cols:
        if col not in df.columns:
            return None
        
        # Check for extreme jumps between consecutive samples
        diffs = np.abs(np.diff(df[col].values))
        
        # Flag if any single jump exceeds 10000 units
        if np.any(diffs > 10000):
            logging.warning(f"Large position jump detected in {col}")
            return False
    
    return True


def _check_rotation_validity(df):
    """
    Check if quaternion (RotX, RotY, RotZ, RotW) values are valid.
    
    A valid quaternion should have a magnitude close to 1.
    """
    rot_cols = ['RotX', 'RotY', 'RotZ', 'RotW']
    
    if not all(col in df.columns for col in rot_cols):
        return None
    
    # Compute quaternion magnitudes
    quat_magnitude = np.sqrt(
        df['RotX'].values**2 +
        df['RotY'].values**2 +
        df['RotZ'].values**2 +
        df['RotW'].values**2
    )
    
    # Valid quaternions should have magnitude close to 1 or close to 10000
    # (depends on your encoding, e.g., 16-bit fixed point would give ~10000)
    valid_magnitudes = (
        (np.abs(quat_magnitude - 1.0) < 0.1) |
        (np.abs(quat_magnitude - 10000) < 100)
    )
    
    if not np.all(valid_magnitudes):
        logging.warning("Invalid quaternion magnitudes detected")
        return False
    
    return True
