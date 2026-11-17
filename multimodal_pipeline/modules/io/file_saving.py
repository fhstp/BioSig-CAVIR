import os
import json
from typing import Any
from .directory_tree_setup import build_result_dir

def make_output_path(run_root, pid, task, metric, order, filename):
    d = build_result_dir(run_root, pid, task, metric, order)
    os.makedirs(d, exist_ok=True)       # redundant but if somehow directory doesn'T already exist...
    return os.path.join(d, filename)


def unique_path(path):
    """If file exists, add _1,..."""
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    i = 1
    while True:
        new_path = f"{base}_{i}{ext}"
        if not os.path.exists(new_path):
            return new_path
        i += 1

def save_csv(df, run_root, pid, task, metric, order, filename, overwrite=False):
    """Saves the DataFrame into the correct directory."""
    path = make_output_path(run_root, pid, task, metric, order, filename)
    if not overwrite:
        path = unique_path(path)
    df.to_csv(path, index=False)
    return path


def save_json(obj: Any, run_root, pid, task, metric, order, filename, overwrite=False):
    """Save a JSON file (e.g., metadata or QC info)."""
    path = make_output_path(run_root, pid, task, metric, order, filename)
    if not overwrite:
        path = unique_path(path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)
    return path


def update_json(data: dict, run_root, pid, task, metric, order, filename):
    """
    Load existing JSON (if present), update with `data`, and save back.
    Does NOT create multiple _1,_2 files — always overwrites by design.
    """
    path = make_output_path(run_root, pid, task, metric, order, filename)

    # Load existing content if file exists
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            try:
                existing = json.load(f)
            except json.JSONDecodeError:
                existing = {}
    else:
        existing = {}

    # Update
    existing.update(data)

    # Save back
    with open(path, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2)

    return path


def update_run_metadata(run_root, data: dict):
    """
    Update run_metadata.json in the given run_root. This is a flat file
    at the top level (no participant/task/metric nesting).
    """
    meta_path = os.path.join(run_root, "run_metadata.json")

    # Load existing metadata if present (make_run_root should have created it)
    if os.path.exists(meta_path):
        with open(meta_path, "r", encoding="utf-8") as f:
            try:
                existing = json.load(f)
            except json.JSONDecodeError:
                existing = {}
    else:
        existing = {}

    # Merge in new data
    existing.update(data)

    # Save back
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2)

    return meta_path



"""

how to use:


# assume you have a dataframe with results and some metadata
df = processed_ecg_dataframe
meta = {"filter": "bandpass 0.5–40Hz", "sampling_rate": 250}

# Save both in the right place
save_csv(df, run_root, pid, task, metric, order="PTM", filename="cleaned.csv")
save_json(meta, run_root, pid, task, metric, order="PTM", filename="meta.json")


"""