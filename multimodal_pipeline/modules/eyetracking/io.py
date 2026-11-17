from __future__ import annotations
import pandas as pd
import numpy as np

def load_gaze_velocity_from_csv(df: pd.DataFrame, left_col="Velocity_Left", right_col="Velocity_Right") -> np.ndarray:
    """
    Returns a 1-D numpy array of gaze velocity (deg/s), computed as the row-wise
    mean of Velocity_Left and Velocity_Right (like your original loader).
    """
    return df[[left_col, right_col]].mean(axis=1).to_numpy(dtype=float)
