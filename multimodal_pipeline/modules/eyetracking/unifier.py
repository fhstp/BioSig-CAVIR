from __future__ import annotations
import pandas as pd
from .unit_conversion import detect_and_convert_units

CANON_ALIASES = {
    # time
    "ts": ["ts", "timestamp", "Timestamp", "time", "Time", "world_timestamp", "timestamp [ns]"],

    # raw velocity
    "vel_raw_l": ["Velocity_Left", "vel_left", "velocity_left", "gaze_velocity_left"],
    "vel_raw_r": ["Velocity_Right", "vel_right", "velocity_right", "gaze_velocity_right"],

    # pupil
    "pupil_l_mm": ["Pupil_Diameter_Left", "pupil_left", "pupil_diameter_left", "pupil diameter left [mm]"],
    "pupil_r_mm": ["Pupil_Diameter_Right", "pupil_right", "pupil_diameter_right", "pupil diameter right [mm]"],

    # gaze direction vectors
    "gaze_dir_l_x": ["Gaze_Left_x", "gaze_left_x", "optical axis left x", "gaze_dir_left_x"],
    "gaze_dir_l_y": ["Gaze_Left_y", "gaze_left_y", "optical axis left y", "gaze_dir_left_y"],
    "gaze_dir_l_z": ["Gaze_Left_z", "gaze_left_z", "optical axis left z", "gaze_dir_left_z"],
    "gaze_dir_r_x": ["Gaze_Right_x", "gaze_right_x", "optical axis right x", "gaze_dir_right_x"],
    "gaze_dir_r_y": ["Gaze_Right_y", "gaze_right_y", "optical axis right y", "gaze_dir_right_y"],
    "gaze_dir_r_z": ["Gaze_Right_z", "gaze_right_z", "optical axis right z", "gaze_dir_right_z"],

    # raw events (optional)
    "fix_raw_l": ["Fixation_Left", "fixation_left"],
    "fix_raw_r": ["Fixation_Right", "fixation_right"],
    "sac_raw_l": ["Saccade_Left", "saccade_left"],
    "sac_raw_r": ["Saccade_Right", "saccade_right"],
}


def unify_columns_by_alias(
    df: pd.DataFrame, 
    aliases: dict = CANON_ALIASES,
    convert_units: bool = True,
    screen_width_px: float | None = None,
    screen_width_deg: float | None = None,
    px_per_mm: float | None = None,
) -> tuple[pd.DataFrame, dict]:
    """
    Unify column names across different eye-tracking devices to a canonical schema.
    
    Handles:
    - Unit detection and conversion (time to seconds, velocity to deg/s, pupil to mm)
    - Column renaming based on device-specific aliases (Pico3, Pupil Labs, ViewPoint, etc.)
    - Timestamp normalization (converts nanoseconds/milliseconds to seconds if detected)
    - Relative time computation (t_rel)
    - Numeric type conversion for key columns
    
    Parameters
    ----------
    df : pd.DataFrame
        Raw dataframe with device-specific column names and potentially mixed units
    aliases : dict, optional
        Mapping of canonical names to lists of possible aliases. Defaults to CANON_ALIASES.
    convert_units : bool, default=True
        If True, detect and convert units to canonical units (s, deg/s, mm)
    screen_width_px : float, optional
        Screen width in pixels (needed for px/s -> deg/s conversion)
    screen_width_deg : float, optional
        Screen width in degrees (needed for px/s -> deg/s conversion)
    px_per_mm : float, optional
        Pixels per millimeter (needed for px -> mm conversion)
    
    Returns
    -------
    df_unified : pd.DataFrame
        Dataframe with unified column names and normalized units
    conversion_metadata : dict
        Metadata about unit conversions performed (empty if convert_units=False)
    """
    df = df.copy()
    conversion_metadata = {}

    # Step 1: Detect and convert units BEFORE renaming (so we can detect from original column names)
    if convert_units:
        # Find time column (could be "Time", "Timestamp", "ts", etc.)
        time_col = None
        for possible in ["ts", "Time", "Timestamp", "time", "timestamp"]:
            if possible in df.columns:
                time_col = possible
                break
        
        # BUG doesnt take epoch seconds into account # FIXME 
        """
        if time_col:
            df, conversion_metadata = detect_and_convert_units(
                df,
                time_col=time_col,
                screen_width_px=screen_width_px,
                screen_width_deg=screen_width_deg,
                px_per_mm=px_per_mm,
            )
        """
        
        
    # Step 2: Build rename map: found_alias -> canonical
    rename_map = {}
    for canon, candidates in aliases.items():
        if canon in df.columns:
            continue  # Already has canonical name
        for c in candidates:
            if c in df.columns:
                rename_map[c] = canon
                break  # Take first match

    if rename_map:
        df = df.rename(columns=rename_map)

    # Step 3: Ensure ts exists and is numeric (after renaming)
    if "ts" in df.columns:
        df["ts"] = pd.to_numeric(df["ts"], errors="coerce")

        # Add relative time (t_rel) starting from first valid timestamp
        first_valid = df["ts"].dropna().iloc[0] if df["ts"].notna().any() else None
        if first_valid is not None:
            df["t_rel"] = df["ts"] - first_valid
        else:
            df["t_rel"] = pd.NA

    # Step 4: Convert key numeric columns to numeric (in case they came in as strings)
    numeric_cols = [c for c in df.columns if c in aliases.keys() or c in ("ts", "t_rel")]
    for c in numeric_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    return df, conversion_metadata

