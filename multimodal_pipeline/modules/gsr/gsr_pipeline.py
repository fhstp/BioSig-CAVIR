"""
GSR pipeline - main orchestrator for GSR data processing.
Follows the same structure as the ECG pipeline.
"""
import os
import numpy as np
import pandas as pd
import logging
import warnings
from pathlib import Path

from .gsr_processing import calculate_baseline_and_deviations, categorize_deviations
from .gsr_sanity import sanity_check_gsr_raw
from .gsr_metrics import compute_gsr_metrics

from ..io.load_modality import load_data_file
from ..io.file_saving import save_csv, save_json, make_output_path
from ..viz.time_series import plot_time_series
from ..viz.gsr_plots import plot_gsr_with_phasic_responses, plot_gsr_deviations


def run_gsr_pipeline(cfg, run_root, file_structure, data_root):
    """
    Main GSR pipeline orchestrator.
    
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
    gsr_params = cfg["params"].get("gsr", {})
    requested_metrics = cfg["metrics"].get("gsr", [])
    participants = cfg["participants"]
    tasks = cfg["tasks"]
    
    # Extract GSR-specific parameters
    baseline_col = gsr_params.get("baseline_col", "GSR_CONDUCTANCE")
    min_deviation = gsr_params.get("min_deviation", 0.1)
    max_deviation = gsr_params.get("max_deviation", 3.0)
    deviation_bins = gsr_params.get("deviation_bins", [0, 0.5, 1.0, 2.0, 3.0, 10])
    deviation_categories = gsr_params.get(
        "deviation_categories", 
        ['Very Low', 'Low', 'High', 'Very High', 'Extremely High']
    )
    
    summary_rows = []  # collects summary dictionaries per participant and task
    
    for pid in participants:
        for task in tasks:
            # Input files from the pre-processor use "GSR" in the filename
            df = load_data_file(data_root, pid, task, "GSR")
            
            if df is None:
                print(f"No GSR data found for participant {pid} and task {task}")
                print("Skipping task")
                summary_rows.append({
                    "participant": pid, 
                    "task": task, 
                    "error_GSR": "No GSR data found"
                })
                continue
            
            # Detect column names (similar to ECG pipeline)
            # Normalize column names
            df.columns = [str(c).strip() for c in df.columns]
            
            # Detect time column
            time_col = "Timestamp" if "Timestamp" in df.columns else df.columns[0]
            
            # Detect GSR value column per file (devices name it differently)
            value_col = detect_gsr_value_col(df.columns, preferred=baseline_col)

            # Sanity check raw data
            try:
                df_clean, raw_stats = sanity_check_gsr_raw(
                    df,
                    time_col=time_col,
                    value_col=value_col
                )
            except (KeyError, ValueError) as e:
                msg = f"GSR sanity check failed for participant {pid}, task {task}: {e}"
                print("[WARN]", msg)
                summary_rows.append({
                    "participant": pid,
                    "task": task,
                    "error_GSR": f"sanity_check_failed: {e}",
                })
                continue
            
            # Plot raw data
            plot_path_raw = Path(make_output_path(
                run_root, pid, task, "gsr", file_structure, "gsr_timeseries_raw.png"
            ))
            
            plot_time_series(
                df=df_clean,
                x_col=time_col,
                y_col=value_col,
                out_path=plot_path_raw,
                title=f"GSR Raw Data - Participant: {pid}, Task: {task}",
                xlabel="Time",
                ylabel="GSR Conductance (µS)",
                dpi=150,
            )
            
            # Calculate baseline and deviations
            try:
                baseline, data_with_deviations, phasic_data = calculate_baseline_and_deviations(
                    df_clean,
                    baseline_col=value_col,
                    min_deviation=min_deviation,
                    max_deviation=max_deviation
                )
            except Exception as e:
                msg = f"Baseline calculation failed for participant {pid}, task {task}: {e}"
                print("[WARN]", msg)
                summary_rows.append({
                    "participant": pid,
                    "task": task,
                    "error_GSR": f"baseline_calculation_failed: {e}",
                })
                continue
            
            # Categorize deviations
            try:
                categorized_data = categorize_deviations(
                    phasic_data,
                    bins=deviation_bins,
                    categories=deviation_categories
                )
            except Exception as e:
                msg = f"Deviation categorization failed for participant {pid}, task {task}: {e}"
                print("[WARN]", msg)
                # Continue with uncategorized data
                categorized_data = phasic_data.copy()
            
            # Save cleaned data with deviations
            save_csv(
                data_with_deviations, 
                run_root, pid, task, "gsr", file_structure, 
                "gsr_clean.csv", 
                overwrite=True
            )
            
            # Save phasic responses
            if len(categorized_data) > 0:
                save_csv(
                    categorized_data,
                    run_root, pid, task, "gsr", file_structure,
                    "gsr_phasic_responses.csv",
                    overwrite=True
                )
            
            # Plot processed data with phasic responses and baseline
            plot_path_processed = Path(make_output_path(
                run_root, pid, task, "gsr", file_structure, "gsr_processed.png"
            ))
            
            plot_gsr_with_phasic_responses(
                data=data_with_deviations,
                phasic_data=categorized_data,
                baseline=baseline,
                out_path=plot_path_processed,
                time_col=time_col,
                baseline_col=value_col,
                participant_id=pid,
                task=task,
                dpi=150,
            )
            
            # Plot deviations over time
            plot_path_deviations = Path(make_output_path(
                run_root, pid, task, "gsr", file_structure, "gsr_deviations.png"
            ))
            
            plot_gsr_deviations(
                data=data_with_deviations,
                out_path=plot_path_deviations,
                time_col=time_col,
                deviation_col='deviation',
                participant_id=pid,
                task=task,
                dpi=150,
            )
            
            # Calculate requested metrics
            print("[gsr_pipeline] requested_metrics:", requested_metrics)
            feats_dict = compute_gsr_metrics(
                data_with_deviations,
                categorized_data,
                requested_metrics,
                baseline_col=value_col,
                deviation_col='deviation'
            )
            print("[gsr_pipeline] feats_dict:", feats_dict)
            
            feats_row = {"participant": pid, "task": task, **feats_dict}
            summary_rows.append(feats_row)
            
            feat_participant_task = pd.DataFrame([feats_row])
            save_csv(
                feat_participant_task, 
                run_root, pid, task, "gsr", file_structure, 
                "features.csv", 
                overwrite=True
            )
            
            # Build metadata
            meta = {
                "participant": pid,
                "task": task,
                "params": {
                    "baseline_col": value_col,
                    "min_deviation": min_deviation,
                    "max_deviation": max_deviation,
                    "deviation_bins": deviation_bins,
                    "deviation_categories": deviation_categories,
                },
                "baseline": float(baseline),
                "raw_stats": raw_stats,
                "qc": {k: raw_stats.get(k) for k in (
                    "duration_s", "fs_est_hz", "n_gaps", "gap_time_s",
                    "frac_out_of_range", "frac_steep_slope", "range_raw", "nan_ratio_raw",
                )},
                "phasic_response_count": len(categorized_data),
            }
            
            save_json(
                meta, 
                run_root, pid, task, "gsr", file_structure, 
                filename="meta.json", 
                overwrite=True
            )
    
    # Build a DataFrame for the collected summary rows
    summary_df = pd.DataFrame(summary_rows)
    
    print("[gsr_pipeline] summary_rows length:", len(summary_rows))
    print("[gsr_pipeline] summary_df shape:", summary_df.shape)
    print("[gsr_pipeline] summary_df head:\n", summary_df.head())
    
    # Put summaries in a stable place for the run
    if not summary_df.empty:
        summary_dir = os.path.join(run_root, "_summaries", "gsr")
        os.makedirs(summary_dir, exist_ok=True)
        summary_df.to_csv(
            os.path.join(summary_dir, "features_by_task.csv"), 
            index=False
        )
    else:
        # Warn the user explicitly when no metrics were produced
        logger = logging.getLogger(__name__)
        msg = (
            "[GSR pipeline] No GSR metrics were produced for this run. "
            "Check that the input data files exist and that your config "
            "('participants', 'tasks', 'metrics', and params) are correct."
        )
        logger.warning(msg)
        warnings.warn(msg)
    
    return summary_df


def detect_gsr_value_col(columns, preferred="GSR_CONDUCTANCE"):
    """
    Pick the GSR column to analyse for one file.
    Order: configured column -> any conductance column (µS) -> legacy heuristic.
    Shimmer via LSL exports 'GSR_CONDUCTANCE', Shimmer native exports
    'GSR Conductance CAL'; 'GSR' / 'GSR RAW' are resistance / raw counts.
    """
    columns = list(columns)
    if preferred in columns:
        return preferred

    conductance = [c for c in columns if "CONDUCTANCE" in c.upper()]
    if conductance:
        return conductance[0]

    gsr_candidates = [c for c in columns if any(
        keyword in c.upper() for keyword in ['GSR', 'SCL', 'SCR']
    )]
    fallback = gsr_candidates[0] if gsr_candidates else columns[-1]
    print(f"[WARN] No GSR conductance column found, using '{fallback}' (check units)")
    return fallback

