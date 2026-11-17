import os
import logging
import warnings
import pandas as pd
from pathlib import Path
import numpy as np

from modules.eyetracking.pupillabs import load_pupillabs_folder, merge_pupillabs_samples
from modules.eyetracking.segmentation import apply_ivt_segmentation, create_fixation_saccade_arrays, resolve_ivt_params
from modules.eyetracking.validity_mask import add_validity_masks, validity_summary
from modules.eyetracking.blinks import detect_blinks, resolve_blink_params
from modules.eyetracking.resample import regularize_to_tracker_rate, gaze_angular_velocity, DEFAULT_TRACKER_HZ
from modules.eyetracking.unifier import unify_columns_by_alias
from modules.eyetracking.eye_tracking_sanity import sanity_check_eyetracking
from modules.eyetracking.metrics import compute_all_metrics
from ..io.load_modality import load_data_file
from ..io.file_saving import make_output_path, save_csv, save_json
from ..viz.eyetracking_plots import (
    plot_gaze_velocity_timeseries,
    plot_pupil_diameter_timeseries,
    plot_gaze_2d,
    plot_event_timeline,
)



def run_eye_tracking_pipeline(cfg, run_root, file_structure, data_root):

    eye_tracking_params = cfg["params"]["et"]
    requested_metrics = cfg["metrics"].get("eye_t" \
    "racking", [])            
    participants = cfg["participants"]
    tasks = cfg["tasks"]


    sample_rate = eye_tracking_params.get("sampling_rate_hz", 120)  # fallback only, see tracker_rate_hz
    # eye-tracker sampling rate; rows are regularised to it. None keeps the delivered rows
    tracker_hz = eye_tracking_params.get("tracker_rate_hz", DEFAULT_TRACKER_HZ)
    # FIXME check paratmeters for different metrics/Devices 
    #velocity_threshold = eye_tracking_params.get("velocity_threshold_deg_s", 30)  #

    
    fixation_min_duration_ms = eye_tracking_params.get("fixation_min_duration_ms", 60)  #
    saccade_min_velocity_deg_s = eye_tracking_params.get("saccade_min_velocity_deg_s", 30)  #

    summary_rows = [] # list to hold summary data for all participants and tasks

    for pid in participants:
        for task in tasks:
            print(f"[INFO] Processing Eye Tracking data for Participant: {pid}, Task: {task}")


            # PICO TESTXASE #XXX 
            df_raw = load_data_file(data_root, pid, task, modality="Eyetracking", pattern="*{task}*{modality}*", sep=",")
            #  pattern="**/*{task}*Eyetracking_preparsed.csv", ??? #FIXME check if right file path

            if df_raw is None:
                print(f"[WARN] No Eye Tracking data found for participant {pid} and task {task}")
                summary_rows.append({
                    "participant": pid,
                    "task": task,
                    "error_EYE_TRACKING": "No eye tracking data found",
                })
                continue

            # here I can call unifier.py or however it will be called alter on but before I can do that I ahve to check if all the devices use the same units for the metrics (are all velocities in deg/s or some in px/s ?)   

            # HACK for now as a placeholder
            df = df_raw.copy()

            #df["ts"] = pd.to_numeric(df["Time"], errors="coerce")
            #df["t_rel"] = df["ts"] - df["ts"].iloc[0]  

            # Unify column names and convert units to canonical units (s, deg/s, mm)
            # This handles: Time -> ts, Velocity_Left -> vel_raw_l, unit conversion, etc.
            df, conversion_metadata = unify_columns_by_alias(
                df_raw,
                convert_units=True,  # Enable unit detection and conversion
            )
            
            # Debug: Check timestamps after conversion
            if "ts" in df.columns:
                ts_vals = pd.to_numeric(df["ts"], errors="coerce")
                print(f"[DEBUG] Timestamp after conversion: min={ts_vals.min():.6f}, max={ts_vals.max():.6f}, median={ts_vals.median():.6f}")
                if len(ts_vals) > 1:
                    dt = ts_vals.diff()
                    dt_pos = dt[dt > 0]
                    if not dt_pos.empty:
                        print(f"[DEBUG] Time diff (dt): median={dt_pos.median():.9f}s, expected_fs={1/dt_pos.median():.2f} Hz")
            
            # Log unit conversion info if any conversions were performed
            if conversion_metadata.get("time", {}).get("converted", False):
                print(f"[INFO] Time unit converted: {conversion_metadata['time']['detected_unit']} -> {conversion_metadata['time']['converted_to']}")
            if conversion_metadata.get("velocity"):
                for vel_col, info in conversion_metadata["velocity"].items():
                    if info.get("converted", False):
                        print(f"[INFO] Velocity unit converted ({vel_col}): {info['detected_unit']} -> {info['converted_to']}")
            if conversion_metadata.get("warnings"):
                for warning in conversion_metadata["warnings"]:
                    print(f"[WARN] Unit conversion: {warning}")

            # Sanity check on unified data
            qc = sanity_check_eyetracking(df, ts_col="ts")   

            if not qc["ok"]:
                print(f"[WARN] Eye Tracking data for Participant: {pid}, Task: {task} failed sanity check: {qc['errors']}")
                summary_rows.append({
                    "participant": pid,
                    "task": task,
                    "error_EYE_TRACKING": f"Sanity check failed: {qc['errors']}",
                })
                # keep the QC report for the data-quality summary
                if run_root is not None:
                    save_json({"participant": pid, "task": task, "qc": qc},
                              run_root, pid, task, "eye_tracking", file_structure, "meta.json", overwrite=True)
                continue

            # The headsets track at 60 Hz but deliver one row per rendered frame (72/90 Hz),
            # repeating the previous sample. Drop the repeats and put the samples on a
            # regular grid at the tracker rate; everything below counts samples at that rate.
            if tracker_hz:
                df, qc["resampling"] = regularize_to_tracker_rate(df, tracker_hz=tracker_hz)
                sampling_rate_hz = float(tracker_hz)
            else:
                fs_est = qc.get("timebase", {}).get("fs_est_hz", None)
                sampling_rate_hz = fs_est if fs_est is not None else sample_rate

            # Derive blinks from bilateral signal loss (device does not report them).
            # Keep a blink column if the device already provides one (e.g. Pupil Labs).
            blink_params = resolve_blink_params(eye_tracking_params)
            if blink_params["enabled"] and "blink" not in df.columns:
                df = detect_blinks(
                    df,
                    sampling_rate_hz=sampling_rate_hz,
                    min_duration_ms=blink_params["min_duration_ms"],
                    max_duration_ms=blink_params["max_duration_ms"],
                )
                if "blink" in df.columns:
                    n_blinks = int((np.diff(np.concatenate(([0], df["blink"].astype(int)))) == 1).sum())
                    print(f"[INFO] Blinks detected: {n_blinks} ({100*df['blink'].mean():.1f}% of samples)")

            df = add_validity_masks(df)
            qc["validity"] = validity_summary(df)

            # Debug: Check available columns and validity
            print(f"[DEBUG] Available columns: {list(df.columns)}")
            if "valid_gaze_l" in df.columns:
                print(f"[DEBUG] valid_gaze_l: {df['valid_gaze_l'].sum()} / {len(df)} ({100*df['valid_gaze_l'].mean():.1f}%)")
            if "valid_gaze_r" in df.columns:
                print(f"[DEBUG] valid_gaze_r: {df['valid_gaze_r'].sum()} / {len(df)} ({100*df['valid_gaze_r'].mean():.1f}%)")
            if "valid_gaze_2d" in df.columns:
                print(f"[DEBUG] valid_gaze_2d: {df['valid_gaze_2d'].sum()} / {len(df)} ({100*df['valid_gaze_2d'].mean():.1f}%)")
            if "valid_gaze" in df.columns:
                print(f"[DEBUG] valid_gaze (combined): {df['valid_gaze'].sum()} / {len(df)} ({100*df['valid_gaze'].mean():.1f}%)")
            if "valid_sample" in df.columns:
                print(f"[DEBUG] valid_sample (final): {df['valid_sample'].sum()} / {len(df)} ({100*df['valid_sample'].mean():.1f}%)")
            

            # TODO here call segementation or eye_classify whatever and get in return two arrays (one fixation one saccade and add them to the original dataframe (probaly merked, that that's hand calculated so call it fixation_calc for example). 

            # Angular velocity from the gaze direction (deg/s). The device velocity column
            # updates at about half the row rate and does not line up with the gaze samples,
            # so it is kept for comparison only.
            df["vel_calc"] = gaze_angular_velocity(df, tracker_hz=sampling_rate_hz)
            qc["velocity_check"] = velocity_check(df)
            vel_col = "vel_calc"
            if df[vel_col].notna().sum() == 0:
                print(f"[WARN] No gaze velocity for Participant: {pid}, Task: {task}")
                summary_rows.append({
                    "participant": pid,
                    "task": task,
                    "error_EYE_TRACKING": "No valid gaze direction samples",
                })
                continue

            # Debug: Check velocity data
            vel_data = pd.to_numeric(df[vel_col], errors="coerce")
            print(f"[DEBUG] Velocity column: {vel_col}")
            print(f"[DEBUG] Velocity stats: min={vel_data.min():.2f}, max={vel_data.max():.2f}, mean={vel_data.mean():.2f}, median={vel_data.median():.2f}")
            print(f"[DEBUG] NaN count: {vel_data.isna().sum()} / {len(vel_data)}")
            if "valid_sample" in df.columns:
                valid_count = df["valid_sample"].sum()
                print(f"[DEBUG] Valid samples: {valid_count} / {len(df)} ({100*valid_count/len(df):.1f}%)")

            '''
            fixation_mask_l, saccade_mask_l = create_fixation_saccade_arrays(gaze_velocity_l, 
                sampling_rate_hz=sample_rate,
                velocity_threshold=saccade_min_velocity_deg_s,
                min_fixation_duration_ms=fixation_min_duration_ms,
            )
            '''

            # Debug: Check segmentation parameters
            vel_threshold = eye_tracking_params.get("velocity_threshold_deg_s", 30)
            min_fix_dur = eye_tracking_params.get("fixation_min_duration_ms", 60)
            min_sac_dur = eye_tracking_params.get("min_saccade_duration_ms", 22)
            print(f"[DEBUG] Sampling rate: {sampling_rate_hz} Hz")
            print(f"[DEBUG] Segmentation params: vel_threshold={vel_threshold} deg/s, min_fix={min_fix_dur}ms, min_sac={min_sac_dur}ms")
            print(f"[DEBUG] Velocity below threshold: {(vel_data < vel_threshold).sum()} samples ({100*(vel_data < vel_threshold).mean():.1f}%)")
            print(f"[DEBUG] Velocity above threshold: {(vel_data >= vel_threshold).sum()} samples ({100*(vel_data >= vel_threshold).mean():.1f}%)")

            ivt = resolve_ivt_params(eye_tracking_params)

            # Apply I-VT segmentation to classify fixations and saccades
            # Note: valid_col=None to avoid breaking up runs with scattered invalid samples
            """
            df = apply_ivt_segmentation(
                df,
                vel_col=vel_col,
                valid_col=None,  # Don't use validity mask to avoid breaking up runs
                sampling_rate_hz=sampling_rate_hz,  # Uses estimate if available, else config default
                velocity_threshold=vel_threshold,
                min_fixation_duration_ms=min_fix_dur,
                min_saccade_duration_ms=min_sac_dur,
                smooth_win_ms=eye_tracking_params.get("smooth_win_ms", 10),
                merge_fix_gap_ms=eye_tracking_params.get("merge_fix_gap_ms", 20),
            )
            """
            df["vel_used"] = df["vel_calc"]

            df = apply_ivt_segmentation(
                df,
                vel_col="vel_used",
                sampling_rate_hz=sampling_rate_hz,
                **ivt,
            )
            
            # Debug: Check segmentation results
            fix_count = df["fix"].sum() if "fix" in df.columns else 0
            sac_count = df["sac"].sum() if "sac" in df.columns else 0
            print(f"[DEBUG] Segmentation results: {fix_count} fixation samples, {sac_count} saccade samples")
            print(f"[DEBUG] Fixation proportion: {100*fix_count/len(df):.1f}%, Saccade proportion: {100*sac_count/len(df):.1f}%")

            # Save cleaned eye-tracking data (unified columns, segmented, but no metrics yet)
            if run_root is not None:
                save_csv(
                    df,
                    run_root,
                    pid,
                    task,
                    "eye_tracking",
                    file_structure,
                    "eyetracking_clean.csv",
                    overwrite=True
                )

            # Compute all available metrics (fixation, saccade, blink, pupil, etc.)
            metrics_result = compute_all_metrics(
                df,
                sampling_rate_hz=sampling_rate_hz,
                requested_metrics=requested_metrics,
            )
            
            # Build summary row with metrics and notes about missing data
            # Use filtered metrics for the returned summary (respects requested_metrics)
            # Use full metrics for features.csv so the saved file always contains everything
            filtered_payload = metrics_result["metrics"]
            full_payload = metrics_result.get("metrics_full", filtered_payload)

            feats_row = {
                "participant": pid,
                "task": task,
                **filtered_payload,
            }
            feats_row_full = {
                "participant": pid,
                "task": task,
                **full_payload,
            }

            # Add notes as string columns only (dicts break CSV summary merges)
            if metrics_result["notes"]:
                for key, note in metrics_result["notes"].items():
                    if key in ["blink", "pupil", "fixation_saccade", "device"]:
                        feats_row[f"_{key}_note"] = note
                        feats_row_full[f"_{key}_note"] = note

            summary_rows.append(feats_row)

            # Log notes about missing data
            if metrics_result["notes"]:
                print(f"[INFO] Metrics notes for {pid}/{task}:")
                for key, note in metrics_result["notes"].items():
                    print(f"  - {key}: {note}")

            # Save per-task metrics and metadata if run_root is provided
            if run_root is not None:
                # Save full feature set to CSV (regardless of requested_metrics filter)
                feat_df = pd.DataFrame([feats_row_full])
                save_csv(feat_df, run_root, pid, task, "eye_tracking", file_structure, "features.csv", overwrite=True)
                
                # Save metadata including QC and parameters
                meta = {
                    "participant": pid,
                    "task": task,
                    "params": {
                        "sampling_rate_hz": sampling_rate_hz,
                        "sampling_rate_hz_config": sample_rate,
                        "velocity_threshold_deg_s": eye_tracking_params.get("velocity_threshold_deg_s", 30),
                        "fixation_min_duration_ms": eye_tracking_params.get("fixation_min_duration_ms", 60),
                        "min_saccade_duration_ms": eye_tracking_params.get("min_saccade_duration_ms", 22),
                        "smooth_win_ms": eye_tracking_params.get("smooth_win_ms", 10),
                        "merge_fix_gap_ms": eye_tracking_params.get("merge_fix_gap_ms", 20),
                    },
                    "segmentation": {
                        "method": "ivt",
                        "resolved_params": ivt,
                        "sampling_rate_hz": sampling_rate_hz,
                    },
                    "blinks": blink_params,
                    "unit_conversion": conversion_metadata,
                    "qc": qc,
                    "notes": metrics_result.get("notes", {}),
                }
                save_json(
                    meta,
                    run_root,
                    pid,
                    task,
                    "eye_tracking",
                    file_structure,
                    "meta.json",
                    overwrite=True
                )
            
            # Generate visualizations if run_root is provided
            if run_root is not None:
                try:
                    vel_plot_path = Path(make_output_path(
                        run_root, pid, task, "eye_tracking", file_structure, "gaze_velocity_timeseries.png"
                    ))
                    plot_gaze_velocity_timeseries(
                        df,
                        vel_plot_path,
                        vel_col=vel_col,
                        participant_id=pid,
                        task=task,
                    )

                    event_plot_path = Path(make_output_path(
                        run_root, pid, task, "eye_tracking", file_structure, "event_timeline.png"
                    ))
                    plot_event_timeline(
                        df,
                        event_plot_path,
                        participant_id=pid,
                        task=task,
                    )

                    if any(c.startswith("pupil") and c.endswith("_mm") for c in df.columns):
                        pupil_plot_path = Path(make_output_path(
                            run_root, pid, task, "eye_tracking", file_structure, "pupil_diameter_timeseries.png"
                        ))
                        plot_pupil_diameter_timeseries(
                            df,
                            pupil_plot_path,
                            participant_id=pid,
                            task=task,
                        )

                    if "gaze_2d_x" in df.columns and "gaze_2d_y" in df.columns:
                        gaze2d_plot_path = Path(make_output_path(
                            run_root, pid, task, "eye_tracking", file_structure, "gaze_2d_scanpath.png"
                        ))
                        plot_gaze_2d(
                            df,
                            gaze2d_plot_path,
                            participant_id=pid,
                            task=task,
                        )
                except Exception as e:
                    print(f"[WARN] Could not create eye-tracking plots for {pid}/{task}: {e}")

    summary_df = pd.DataFrame(summary_rows)
    dict_cols = [
        c for c in summary_df.columns
        if summary_df[c].map(lambda x: isinstance(x, dict)).any()
    ]
    if dict_cols:
        summary_df = summary_df.drop(columns=dict_cols)

    print("[eye_tracking_pipeline] summary_rows length:", len(summary_rows))
    print("[eye_tracking_pipeline] summary_df shape:", summary_df.shape)
    print("[eye_tracking_pipeline] summary_df head:\n", summary_df.head())

    if run_root is not None and not summary_df.empty:
        summary_dir = os.path.join(run_root, "_summaries", "eye_tracking")
        os.makedirs(summary_dir, exist_ok=True)
        summary_df.to_csv(
            os.path.join(summary_dir, "features_by_task.csv"),
            index=False,
        )
    elif summary_df.empty:
        msg = (
            "[eye_tracking pipeline] No eye-tracking metrics were produced for this run. "
            "Check that the input data files exist and that your config "
            "('participants', 'tasks', 'metrics', and params) are correct."
        )
        logging.getLogger(__name__).warning(msg)
        warnings.warn(msg)

    return summary_df





            # TODO somehow distinguish if it's pupillabs, viewpoint or pico #XXX 

            # 

    device = "pico3"     # Placeholder for which dwevice is used

    '''
            if device == "pupillabs":
                pupillabs_dict = load_pupillabs_folder(data_root, pid, task)
                merged_df = merge_pupillabs_samples


            et_data = load_data_file(cfg["data_root"], pid, task, modality="eye", pattern="*{task}*{modality}*")
            '''

            # after device detection one unifierd dataframe

            # TODO find a schema for unified column names
            # eye_tracking_sanity_check(df) 

'''
            # XXX rename columns here? 
            df = df.rename(columns={
    "Velocity_Left": "vel_raw_l",
    "Velocity_Right": "vel_raw_r",
    "Pupil_Diameter_Left": "pupil_l_mm",
    "Pupil_Diameter_Right": "pupil_r_mm",
    "Gaze_Left_x": "gaze_dir_l_x",
    "Gaze_Left_y": "gaze_dir_l_y",
    "Gaze_Left_z": "gaze_dir_l_z",
    "Gaze_Right_x": "gaze_dir_r_x",
    "Gaze_Right_y": "gaze_dir_r_y",
    "Gaze_Right_z": "gaze_dir_r_z",
})
'''




'''

# TODO here I have a function checking which kind of poarameters are present in the dataframe
# TODO first I need to unify the column names from different devices into one common schema or at least similar names so I could work with regex


def describe_eyetracking_schema(df):
    return {
        "has_gaze_dir": all(c in df for c in ["gaze_dir_l_x", "gaze_dir_l_y", "gaze_dir_l_z"]),
        "has_gaze_2d": all(c in df for c in ["gaze_2d_x", "gaze_2d_y"]),
        "has_pupil": any(c in df for c in ["pupil_l_mm", "pupil_r_mm"]),
        "has_vel_raw": any(c in df for c in ["vel_raw_l", "vel_raw_r"]),
    }



'''


# TODO Then for unified dataframe : sanity check






"""
            if et_data is None:
                print(f"[WARN] Skipping Participant: {pid}, Task: {task} due to missing data.")
                continue

            # Process eye-tracking data
            from modules.eyetracking.eye_tracking_analysis import analyze_eye_tracking_data
            metrics = analyze_eye_tracking_data(
                et_data,
                sample_rate=sample_rate,
                fixation_min_duration_ms=fixation_min_duration_ms,
                saccade_min_velocity_deg_s=saccade_min_velocity_deg_s,
                requested_metrics=requested_metrics
            )

            # Add participant and task info to metrics
            metrics["participant_id"] = pid
            metrics["task"] = task

            # Append to summary rows
            summary_rows.append(metrics)
"""



'''

            # Compute metrics from segmented data
            stats = compute_statistics(fix_mask, sac_mask, sampling_rate_hz=sample_rate)
            
            # Filter to requested metrics (or return all if none specified)
            feats_dict = {}
            if requested_metrics:
                for metric_name in requested_metrics:
                    if metric_name in stats:
                        feats_dict[metric_name] = stats[metric_name]
                    else:
                        print(f"[WARN] Requested metric '{metric_name}' not found in computed statistics")
            else:
                # If no metrics specified, return all computed stats
                feats_dict = stats.copy()
            
            # Add participant and task info
            feats_row = {"participant": pid, "task": task, **feats_dict}
            summary_rows.append(feats_row)
            
            # Save segmented dataframe (with fixation/saccade labels)
            save_csv(df, run_root, pid, task, "eyetracking", file_structure, "gaze_segmented.csv", overwrite=True)
            
            # Save per-task features
            feat_df = pd.DataFrame([feats_row])
            save_csv(feat_df, run_root, pid, task, "eyetracking", file_structure, "features.csv", overwrite=True)
            
            # Save metadata
            meta = {
                "participant": pid,
                "task": task,
                "params": {
                    "sampling_rate_hz": sampling_rate_hz,  # Uses estimate if available, else config
                    "sampling_rate_hz_config": sample_rate,  # Original config value
                    "sampling_rate_hz_estimated": fs_est,  # Estimated from timestamps (if available)
                    "velocity_threshold_deg_s": saccade_min_velocity_deg_s,
                    "fixation_min_duration_ms": fixation_min_duration_ms,
                },
                "unit_conversion": conversion_metadata,  # Store unit conversion metadata for traceability
                "qc": {
                    "valid_sample_frac": float(df["valid_sample"].mean()) if "valid_sample" in df.columns else None,
                    "fixation_time_prop": float(fix_mask.mean()),
                    "saccade_time_prop": float(sac_mask.mean()),
                },
                "statistics": stats,  # Include all computed stats in metadata
            }
            save_json(meta, run_root, pid, task, "eyetracking", file_structure, "meta.json", overwrite=True)

'''

def velocity_check(df: pd.DataFrame) -> dict:
    """Median own vs. device velocity (deg/s) on valid samples, for the methods section."""
    out = {"vel_calc_median": float(df["vel_calc"].median()) if df["vel_calc"].notna().any() else None}
    for eye in ("l", "r"):
        col = f"vel_raw_{eye}"
        if col in df.columns:
            dev = pd.to_numeric(df[col], errors="coerce")
            dev = dev[dev >= 0]   # -0.1 = not detected
            out[f"vel_device_{eye}_median"] = float(dev.median()) if len(dev) else None
    return out
