

import pandas as pd

from pathlib import Path

from ..io.load_modality import load_data_file


'''
def load_pupillabs_folder(folder: str) -> dict:
    """
    Loads a Pupillabs folder and returns a dictionary of the data.
    """
    folder = Path(folder)
    out = {}

    def read(name: str) -> pd.DataFrame:
        path = folder / name
        return pd.read_csv(path) if path.exists() else None
    
    out["gaze_positions"] = read("gaze_positions.csv")
    out["eye_states_3d"] = read("eye_states_3d.csv")
    out["worn"] = read("worn.csv")

    # events
    out["blinks"] = read("blinks.csv")
    out["fixations"] = read("fixations.csv")
    out["saccades"] = read("saccades.csv")
    #out["pupil_size"] = read("pupil_size.csv")
    #out["pupil_size_3d"] = read("pupil_size_3d.csv")
    #out["pupil_size_3d"] = read("pupil_size_3d.csv")

    return out
'''

def load_pupillabs_folder(data_root, pid, task):
    
    # TODO #FIXME IMPORTANT check which modality will be used for Pupillabs -> currently using Eyetracking but might be different 
    # check the entire file structure in which the data will be saved - for now only placeholder
    gaze = load_data_file(data_root, pid, task, "gaze", pattern="*{task}*{modality}*", sep=",")
    # TODO solve that issue here or in the pre-processor?  
    return 




def merge_pupillabs_samples(data_dict, tollerance_eye_s = 0.01, tollerance_worn_s = 0.05) -> pd.DataFrame:


    gaze = data_dict["gaze"]
    eye = data_dict["eye"]
    worn = data_dict["worn"]

    # Backbone: gaze timestamps
    merged = gaze

    # Merge eye states onto gaze time axis
    merged = pd.merge_asof(
        merged,
        eye,
        on="ts",
        direction="nearest",
        tolerance=tollerance_eye_s,
        suffixes=("", "_eye")  # should not be needed now, but harmless
    )

    # Merge worn onto gaze time axis
    merged = pd.merge_asof(
        merged,
        worn,
        on="ts",
        direction="nearest",
        tolerance=tollerance_worn_s,
        suffixes=("", "_worn")
    )

    # Add “alignment discrepancy” columns (super helpful for debugging)
    for src in ("gaze", "eye", "worn"):
        col = f"timestamp_ns_{src}"
        if col in merged.columns:
            merged[f"dt_{src}_s"] = merged["ts"] - (merged[col] * 1e-9)

    return merged

