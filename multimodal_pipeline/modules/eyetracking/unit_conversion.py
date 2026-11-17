from __future__ import annotations
import re
import numpy as np
import pandas as pd
from typing import Optional


# Canonical units (what we convert TO)
CANONICAL_UNITS = {
    "time": "s",           # seconds
    "velocity": "deg/s",   # degrees per second
    "pupil": "mm",         # millimeters
    "gaze_dir": "unitless",  # normalized direction vectors (no conversion needed)
}


def detect_time_unit(col_name: str, values: np.ndarray) -> str:
    """
    Detect time unit from column name and/or data values.
    
    Returns: "s", "ms", "us", "ns", or "unknown"
    """
    col_lower = col_name.lower()
    
    # Check column name for unit hints
    if "[ms]" in col_lower or "millisecond" in col_lower:
        return "ms"
    if "[us]" in col_lower or "[µs]" in col_lower or "microsecond" in col_lower:
        return "us"
    if "[ns]" in col_lower or "nanosecond" in col_lower:
        return "ns"
    if "[s]" in col_lower or "second" in col_lower:
        return "s"
    
    # Heuristic: check data range
    if len(values) == 0:
        return "unknown"
    
    valid_values = values[np.isfinite(values)]
    if len(valid_values) == 0:
        return "unknown"
    
    median_val = np.median(valid_values)
    
    # Nanoseconds: typically > 1e12 (Unix epoch in ns)
    if median_val > 1e12:
        return "ns"
    # Milliseconds: typically 1e9 - 1e12 (Unix epoch in ms)
    elif median_val > 1e9:
        return "ms"
    # Microseconds: typically 1e6 - 1e9
    elif median_val > 1e6:
        return "us"
    # Seconds: typically < 1e6 (or Unix epoch in s: ~1e9)
    elif median_val > 1e3:
        # Could be seconds (Unix epoch) or milliseconds (relative time)
        # If it's Unix epoch-like, it's seconds; if it's relative, check range
        if median_val > 1e8:  # Likely Unix epoch in seconds
            return "s"
        else:
            # Ambiguous: could be ms or s. Default to seconds for relative time
            return "s"
    else:
        # Small values: likely seconds (relative time)
        return "s"


def detect_velocity_unit(col_name: str, values: np.ndarray) -> str:
    """
    Detect velocity unit from column name and/or data values.
    
    Returns: "deg/s", "px/s", "m/s", "rad/s", or "unknown"
    """
    col_lower = col_name.lower()
    
    # Check column name for unit hints
    if "[deg/s]" in col_lower or "[deg/sec]" in col_lower or "degree" in col_lower:
        return "deg/s"
    if "[px/s]" in col_lower or "[pixel/s]" in col_lower or "pixel" in col_lower:
        return "px/s"
    if "[m/s]" in col_lower or "meter" in col_lower:
        return "m/s"
    if "[rad/s]" in col_lower or "radian" in col_lower:
        return "rad/s"
    
    # Heuristic: check data range
    # Typical gaze velocities:
    #   - deg/s: 0-1000 (fixations < 30, saccades 30-900)
    #   - px/s: 0-5000+ (depends on screen resolution)
    #   - m/s: 0-10 (very rare, unlikely)
    
    if len(values) == 0:
        return "unknown"
    
    valid_values = values[np.isfinite(values)]
    if len(valid_values) == 0:
        return "unknown"
    
    p95 = np.percentile(valid_values, 95)
    
    # If most values are > 1000, likely px/s
    if p95 > 1000:
        return "px/s"
    # If most values are < 1000, likely deg/s (most common)
    elif p95 < 1000:
        return "deg/s"
    else:
        # Ambiguous: default to deg/s (most common in eye tracking)
        return "deg/s"


def detect_pupil_unit(col_name: str, values: np.ndarray) -> str:
    """
    Detect pupil diameter unit from column name and/or data values.
    
    Returns: "mm", "cm", "px", or "unknown"
    """
    col_lower = col_name.lower()
    
    # Check column name for unit hints
    if "[mm]" in col_lower or "millimeter" in col_lower:
        return "mm"
    if "[cm]" in col_lower or "centimeter" in col_lower:
        return "cm"
    if "[px]" in col_lower or "pixel" in col_lower:
        return "px"
    
    # Heuristic: check data range
    # Typical pupil diameters:
    #   - mm: 2-8 mm
    #   - cm: 0.2-0.8 cm
    #   - px: 20-200+ pixels (depends on camera resolution)
    
    if len(values) == 0:
        return "unknown"
    
    valid_values = values[np.isfinite(values)]
    if len(valid_values) == 0:
        return "unknown"
    
    median_val = np.median(valid_values)
    
    # If median < 1, likely cm
    if median_val < 1:
        return "cm"
    # If median > 20, likely pixels
    elif median_val > 20:
        return "px"
    # Otherwise, likely mm (most common)
    else:
        return "mm"


def convert_time_to_seconds(values: np.ndarray, from_unit: str) -> np.ndarray:
    """Convert time values to seconds."""
    if from_unit == "s":
        return values
    elif from_unit == "ms":
        return values * 1e-3
    elif from_unit == "us":
        return values * 1e-6
    elif from_unit == "ns":
        return values * 1e-9
    else:
        # Unknown unit: assume seconds (no conversion)
        return values


def convert_velocity_to_deg_per_sec(values: np.ndarray, from_unit: str, 
                                     screen_width_px: Optional[float] = None,
                                     screen_width_deg: Optional[float] = None) -> np.ndarray:
    """
    Convert velocity values to deg/s.
    
    Parameters
    ----------
    values : np.ndarray
        Velocity values in source unit
    from_unit : str
        Source unit ("deg/s", "px/s", "m/s", "rad/s")
    screen_width_px : float, optional
        Screen width in pixels (needed for px/s -> deg/s conversion)
    screen_width_deg : float, optional
        Screen width in degrees (needed for px/s -> deg/s conversion)
    """
    if from_unit == "deg/s":
        return values
    elif from_unit == "px/s":
        if screen_width_px is None or screen_width_deg is None:
            raise ValueError(
                "px/s -> deg/s conversion requires screen_width_px and screen_width_deg. "
                "Cannot convert automatically."
            )
        px_per_deg = screen_width_px / screen_width_deg
        return values / px_per_deg
    elif from_unit == "rad/s":
        return np.rad2deg(values)  # rad/s -> deg/s
    elif from_unit == "m/s":
        # This is very rare and requires viewing distance to convert properly
        # For now, warn and don't convert
        raise ValueError(
            "m/s -> deg/s conversion requires viewing distance. "
            "Cannot convert automatically."
        )
    else:
        # Unknown unit: assume deg/s (no conversion)
        return values


def convert_pupil_to_mm(values: np.ndarray, from_unit: str,
                        px_per_mm: Optional[float] = None) -> np.ndarray:
    """
    Convert pupil diameter values to mm.
    
    Parameters
    ----------
    values : np.ndarray
        Pupil diameter values in source unit
    from_unit : str
        Source unit ("mm", "cm", "px")
    px_per_mm : float, optional
        Pixels per millimeter (needed for px -> mm conversion)
    """
    if from_unit == "mm":
        return values
    elif from_unit == "cm":
        return values * 10.0
    elif from_unit == "px":
        if px_per_mm is None:
            raise ValueError(
                "px -> mm conversion requires px_per_mm. "
                "Cannot convert automatically."
            )
        return values / px_per_mm
    else:
        # Unknown unit: assume mm (no conversion)
        return values


def detect_and_convert_units(
    df: pd.DataFrame,
    time_col: str = "ts",
    velocity_cols: Optional[list[str]] = None,
    pupil_cols: Optional[list[str]] = None,
    screen_width_px: Optional[float] = None,
    screen_width_deg: Optional[float] = None,
    px_per_mm: Optional[float] = None,
) -> tuple[pd.DataFrame, dict]:
    """
    Detect units and convert to canonical units for eye-tracking data.
    
    Parameters
    ----------
    df : pd.DataFrame
        Input dataframe with potentially mixed units
    time_col : str
        Name of timestamp column
    velocity_cols : list[str], optional
        List of velocity column names. If None, auto-detect from common names.
    pupil_cols : list[str], optional
        List of pupil diameter column names. If None, auto-detect from common names.
    screen_width_px : float, optional
        Screen width in pixels (for px/s -> deg/s conversion)
    screen_width_deg : float, optional
        Screen width in degrees (for px/s -> deg/s conversion)
    px_per_mm : float, optional
        Pixels per millimeter (for px -> mm conversion)
    
    Returns
    -------
    df_converted : pd.DataFrame
        Dataframe with converted values
    conversion_metadata : dict
        Metadata about detected units and conversions performed
    """
    df_out = df.copy()
    metadata = {
        "time": {},
        "velocity": {},
        "pupil": {},
        "warnings": [],
    }
    
    # --- Time conversion ---
    if time_col in df_out.columns:
        ts_values = pd.to_numeric(df_out[time_col], errors="coerce").to_numpy()
        detected_unit = detect_time_unit(time_col, ts_values)
        
        if detected_unit != "unknown" and detected_unit != CANONICAL_UNITS["time"]:
            df_out[time_col] = convert_time_to_seconds(ts_values, detected_unit)
            metadata["time"] = {
                "detected_unit": detected_unit,
                "converted_to": CANONICAL_UNITS["time"],
                "converted": True,
            }
        else:
            metadata["time"] = {
                "detected_unit": detected_unit,
                "converted_to": CANONICAL_UNITS["time"],
                "converted": False,
            }
    
    # --- Velocity conversion ---
    if velocity_cols is None:
        # Auto-detect velocity columns
        velocity_cols = [c for c in df_out.columns 
                        if any(x in c.lower() for x in ["vel", "velocity"])]
    
    for vel_col in velocity_cols:
        if vel_col not in df_out.columns:
            continue
        
        vel_values = pd.to_numeric(df_out[vel_col], errors="coerce").to_numpy()
        detected_unit = detect_velocity_unit(vel_col, vel_values)
        
        if detected_unit != "unknown" and detected_unit != CANONICAL_UNITS["velocity"]:
            try:
                df_out[vel_col] = convert_velocity_to_deg_per_sec(
                    vel_values, detected_unit, screen_width_px, screen_width_deg
                )
                metadata["velocity"][vel_col] = {
                    "detected_unit": detected_unit,
                    "converted_to": CANONICAL_UNITS["velocity"],
                    "converted": True,
                }
            except ValueError as e:
                metadata["warnings"].append(
                    f"Could not convert {vel_col} from {detected_unit}: {e}"
                )
                metadata["velocity"][vel_col] = {
                    "detected_unit": detected_unit,
                    "converted_to": CANONICAL_UNITS["velocity"],
                    "converted": False,
                    "error": str(e),
                }
        else:
            metadata["velocity"][vel_col] = {
                "detected_unit": detected_unit,
                "converted_to": CANONICAL_UNITS["velocity"],
                "converted": False,
            }
    
    # --- Pupil conversion ---
    if pupil_cols is None:
        # Auto-detect pupil columns
        pupil_cols = [c for c in df_out.columns 
                     if any(x in c.lower() for x in ["pupil", "diameter"])]
    
    for pupil_col in pupil_cols:
        if pupil_col not in df_out.columns:
            continue
        
        pupil_values = pd.to_numeric(df_out[pupil_col], errors="coerce").to_numpy()
        detected_unit = detect_pupil_unit(pupil_col, pupil_values)
        
        if detected_unit != "unknown" and detected_unit != CANONICAL_UNITS["pupil"]:
            try:
                df_out[pupil_col] = convert_pupil_to_mm(pupil_values, detected_unit, px_per_mm)
                metadata["pupil"][pupil_col] = {
                    "detected_unit": detected_unit,
                    "converted_to": CANONICAL_UNITS["pupil"],
                    "converted": True,
                }
            except ValueError as e:
                metadata["warnings"].append(
                    f"Could not convert {pupil_col} from {detected_unit}: {e}"
                )
                metadata["pupil"][pupil_col] = {
                    "detected_unit": detected_unit,
                    "converted_to": CANONICAL_UNITS["pupil"],
                    "converted": False,
                    "error": str(e),
                }
        else:
            metadata["pupil"][pupil_col] = {
                "detected_unit": detected_unit,
                "converted_to": CANONICAL_UNITS["pupil"],
                "converted": False,
            }
    
    return df_out, metadata

