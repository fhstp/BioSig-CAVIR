"""
Head Movement pipeline - main orchestrator for head movement data processing.
Follows the same structure as the ECG and GSR pipelines.

Processes head position, rotation, velocity, and angular velocity data.
"""
import os
import glob
import numpy as np
import pandas as pd
import logging
import warnings
from pathlib import Path

from .head_movement_processing import process_head_movement_data, compute_movement_features
from .head_movement_sanity import sanity_check_head_movement_raw
from .head_movement_metrics import compute_head_movement_metrics

from ..io.load_modality import load_data_file
from ..io.file_saving import save_csv, save_json, make_output_path
from ..viz.time_series import plot_time_series


def run_head_movement_pipeline(cfg, run_root, file_structure, data_root):
    """
    Main head movement pipeline orchestrator.
    
    Parameters
    ----------
    cfg : dict
        Configuration dictionary with participants, tasks, metrics, and params
    run_root : str
        Root directory for output files
    file_structure : str
        Directory structure format (e.g., "PTM")
    data_root : str
        Root directory for input data files
    
    Returns
    -------
    pd.DataFrame
        Summary dataframe with metrics per participant and task
    """
    hm_params = cfg["params"].get("head_movement", {})
    requested_metrics = cfg["metrics"].get("head_movement", [])
    participants = cfg["participants"]
    tasks = cfg["tasks"]
    
    # Extract head movement-specific parameters
    sampling_rate_hz = hm_params.get("sampling_rate_hz", 120.0)
    velocity_threshold = hm_params.get("velocity_threshold", 0.03)  # m/s (3 cm/s)
    angular_velocity_threshold = hm_params.get("angular_velocity_threshold", 0.1)  # rad/s (~5.7 deg/s)
    position_smoothing_window = hm_params.get("position_smoothing_window", 5)
    
    summary_rows = []  # collects summary dictionaries per participant and task
    
    for pid in participants:
        for task in tasks:
            try:
                # Search for head movement data files
                # Assuming naming convention: "*_HEAD_MOVEMENT_*.csv" or similar
                
                # FIXME no need for that since that should be handled by load_data_file
                #data_file = _find_head_movement_file(pid, task, data_root)
                #if data_file is None:
                #    logging.warning(f"No head movement data found for {pid}/{task}")
                #    continue
                
                # Load raw data
                raw_df = load_data_file(data_root, pid, task, "HEAD_MOVEMENT", pattern="*HEAD*MOVEMENT*.csv")  # FIXME placeholder until I know how the files will be saved
                
                if raw_df is None or len(raw_df) == 0:
                    logging.warning(f"Empty head movement data for {pid}/{task}")
                    continue
                
                # Sanity check on raw data
                sanity_results = sanity_check_head_movement_raw(raw_df)
                
                # Process head movement data
                processed_df = process_head_movement_data(
                    raw_df,
                    sampling_rate=sampling_rate_hz,
                    smoothing_window=position_smoothing_window
                )
                
                # Compute movement features
                features_df = compute_movement_features(
                    processed_df,
                    velocity_threshold=velocity_threshold,
                    angular_velocity_threshold=angular_velocity_threshold
                )
                
                # Compute requested metrics
                metrics_dict = {}
                if requested_metrics:
                    metrics_dict = compute_head_movement_metrics(
                        features_df,
                        requested_metrics
                    )
                
                # Save outputs
                save_csv(
                    features_df,
                    run_root, pid, task, "HEAD_MOVEMENT", file_structure,
                    "head_movement_features.csv"
                )
                
                if metrics_dict:
                    save_json(
                        metrics_dict,
                        run_root, pid, task, "HEAD_MOVEMENT", file_structure,
                        "head_movement_metrics.json"
                    )
                
                # Create summary row
                summary_row = {
                    "participant": pid,
                    "task": task,
                    "num_samples": len(features_df),
                    "duration_sec": len(features_df) / sampling_rate_hz,
                    **sanity_results,
                    **metrics_dict
                }
                summary_rows.append(summary_row)
                
                logging.info(f"Completed head movement processing for {pid}/{task}")
                
            except Exception as e:
                logging.error(f"Error processing head movement for {pid}/{task}: {str(e)}")
                summary_row = {
                    "participant": pid,
                    "task": task,
                    "error": str(e)
                }
                summary_rows.append(summary_row)
    
    # Create and return summary dataframe
    summary_df = pd.DataFrame(summary_rows)
    return summary_df


def _find_head_movement_file(participant, task, data_root):
    """
    Find the head movement data file for a given participant and task.
    
    Parameters
    ----------
    participant : str
        Participant ID
    task : str
        Task name
    data_root : str
        Root directory for data files
    
    Returns
    -------
    str or None
        Path to the data file, or None if not found
    """
    # Adjust search pattern as needed based on your file naming convention
    patterns = [
        os.path.join(data_root, f"*{participant}*{task}*HEAD*MOVEMENT*.csv"),
        os.path.join(data_root, f"*{participant}*{task}*head*movement*.csv"),
        os.path.join(data_root, f"P{participant}*{task}*HM*.csv"),
    ]
    
    for pattern in patterns:
        files = glob.glob(pattern)
        if files:
            return files[0]
    
    return None
