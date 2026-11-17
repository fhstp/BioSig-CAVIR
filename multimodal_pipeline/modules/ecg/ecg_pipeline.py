import os, glob, json
import numpy as np
import pandas as pd
import logging
import warnings
from importlib.metadata import version as pkg_version
from pathlib import Path

from .rpeak_detection import detect_rpeaks_from_ecg
from .rpeak_detection_neurokit import detect_rpeaks_neurokit
from .rr_from_rpeaks import rpeaks_to_rr
from .detect_ecg_input import detect_ecg_input_mode
#from .ecg_metrics.calculate_rmssd import rmssd_from_rr
from .ecg_metrics.hrv_rr_time import pnn50_from_rr, rmssd_from_rr, sdnn_from_rr
from .ecg_metrics.hrv_neurokit import hrv_time_neurokit
from .polar_ticks import convert_polar_ticks_df
from .rr_unit_detection import detect_rri_units
from .rr_cleaning import finalize_clean_table_from_rr, summarize_rr_validity, flag_rr_artifacts_kubios, rr_qc_stats
# from .finalize_clean_table import finalize_clean_table_from_rr
from .ecg_sanity import sanity_check_ecg_raw

from ..io.load_modality import load_data_file
from ..io.file_saving import save_csv, save_json, make_output_path
from ..io.directory_tree_setup import validate_order
from ..qc.coverage import coverage_qc
from ..viz.ecg_plots import plot_rr_timeseries

from ..viz.time_series import plot_time_series


RPEAK_METHODS = ("heartpy", "neurokit")


def _library_versions() -> dict:
    out = {}
    for lib in ("heartpy", "neurokit2"):
        try:
            out[lib] = pkg_version(lib)
        except Exception:
            out[lib] = None
    return out


def detect_rpeaks(df_clean, method, fallback_method, ecg_params, fallback_fs_hz, bandpass, bpm_range,
                  artifact_info=None):
    """
    Run R-peak detection with the requested backend and fall back to
    `fallback_method` if it fails. Returns (detector output tuple, fallback reason or None).
    `artifact_info` (dict) receives the uncorrected NeuroKit peaks, see detect_rpeaks_neurokit.
    """
    def _run(m):
        if m == "neurokit":
            nk_params = ecg_params.get("neurokit", {}) or {}
            return detect_rpeaks_neurokit(
                df_clean,
                time_col="Timestamp",
                value_col="HR",
                fallback_fs_hz=fallback_fs_hz,
                clean_method=nk_params.get("clean_method", "neurokit"),
                peak_method=nk_params.get("peak_method", "neurokit"),
                correct_artifacts=bool(nk_params.get("correct_artifacts", True)),
                artifact_info=artifact_info,
            )
        return detect_rpeaks_from_ecg(
            df_clean,
            time_col="Timestamp",
            #time_col=None,     # BUG #FIXME heartpy breaks with actual Timestamps
            value_col="HR",
            fallback_fs_hz=fallback_fs_hz,
            bandpass=bandpass,
            bpm_range=bpm_range,
        )

    try:
        return _run(method), None
    except Exception as e:
        if not fallback_method or fallback_method == method:
            raise ValueError(str(e)) from e
        reason = f"{method} failed ({e}), fell back to {fallback_method}"
        print("[WARN] [rpeak]", reason)
        return _run(fallback_method), reason



def run_ecg_pipeline(cfg, run_root, file_structure, data_root):
    
    ecg_params = cfg["params"]["ecg"]
    requested_metrics = cfg["metrics"].get("ecg", [])            
    participants = cfg["participants"]
    tasks = cfg["tasks"]


    bpm_range = cfg["params"]["ecg"]["hr_outlier_range_bpm"]
    fallback_hz = cfg["params"]["ecg"]["sampling_rate_hz"]
    bpm_range   = tuple(ecg_params["hr_outlier_range_bpm"])
    fallback_hz = ecg_params.get("sampling_rate_hz")
    bandpass    = tuple(ecg_params.get("bandpass_hz", (0.5, 35.0)))
    polar_hz    = float(ecg_params.get("polar_ticks_hz", 1024.0))
    trim_start_sec = float(ecg_params.get("trim_start_sec", 0) or 0)
    # gaps between ECG rows longer than this count as missing data (Polar via iMotions: ~1 row/s)
    coverage_max_gap_s = float(ecg_params.get("coverage_max_gap_s", 3.0))
    # RRI unit of Polar files: "ticks" (1/polar_ticks_hz s, Polar H10 via iMotions BLE), "ms",
    # or "auto" (guess from sum(RRI) vs. segment duration - unreliable, both differ by only 2.4%)
    rri_unit = str(ecg_params.get("rri_unit", "ticks")).lower()
    if rri_unit not in {"ticks", "ms", "auto"}:
        raise ValueError(f"params.ecg.rri_unit must be 'ticks', 'ms' or 'auto', got {rri_unit!r}")
    # Artifact correction for RRI files (raw ECG is corrected during NeuroKit peak detection)
    rri_artifact_correction = str(ecg_params.get("rri_artifact_correction", "kubios")).lower()
    if rri_artifact_correction not in {"kubios", "none"}:
        raise ValueError(f"params.ecg.rri_artifact_correction must be 'kubios' or 'none', got {rri_artifact_correction!r}")
    # R-peak backend for raw ECG: "heartpy" (legacy) or "neurokit".
    # If the primary backend fails, rpeak_fallback ("heartpy" or None) is tried instead.
    rpeak_method = str(ecg_params.get("rpeak_method", "heartpy")).lower()
    rpeak_fallback = ecg_params.get("rpeak_fallback", "heartpy")
    if rpeak_method not in RPEAK_METHODS:
        raise ValueError(f"params.ecg.rpeak_method must be one of {RPEAK_METHODS}, got {rpeak_method!r}")


    summary_rows = []   # collects summary dictionaries per participant and task

    for pid in participants:
        for task in tasks:
            # Input files from the pre-processor use "ECG" in the filename
            # (e.g. "..._ECG_preparsed.csv"), so we search with that token.
            df = load_data_file(data_root, pid, task, "ECG")
            
            if df is None:
                print(f"No ECG data found for participant {pid} and task {task}")
                print("Skipping task")

                summary_rows.append({"participant": pid, "task": task, "error_ECG": "No ECG data found"})

                continue  




            # time covered by ECG samples; gaps > coverage_max_gap_s count as dropouts
            coverage = coverage_qc(df["Timestamp"], coverage_max_gap_s) if "Timestamp" in df.columns else {}

            mode = detect_ecg_input_mode(df, bpm_range)

            clean_df = None
            unit = None     # RRI unit, only set for mode == "rri"
            rpeak_fallback_reason = None    # only set if raw-ECG peak detection had to fall back
            nk_artifacts = {}   # uncorrected NeuroKit peaks, for counting corrected beats


            if mode == "raw_ecg":

                df_clean, raw_stats = sanity_check_ecg_raw(df, time_col="Timestamp", value_col="HR")

                x_col = "Timestamp" if "Timestamp" in df_clean.columns else df_clean.columns[0]
                y_col = "HR" if "HR" in df_clean.columns else df_clean.columns[1]

                try:
                    (peak_times_unix, peak_times_ms, fs, x_filt, meta_rri_source, peak_idx), rpeak_fallback_reason = detect_rpeaks(
                        df_clean,
                        method=rpeak_method,
                        fallback_method=rpeak_fallback,
                        ecg_params=ecg_params,
                        fallback_fs_hz=fallback_hz,
                        bandpass=bandpass,
                        bpm_range=bpm_range,
                        artifact_info=nk_artifacts,
                    )
                except ValueError as e:
                    msg = f"R-peak detection failed for participant {pid}, task {task}: {e}"
                    print("[WARN]", msg)
                    raw_plot_path = Path(
                        make_output_path(run_root, pid, task, "ecg", file_structure, "ecg_raw.png")
                    )
                    plot_time_series(
                        df=df_clean,
                        x_col=x_col,
                        y_col=y_col,
                        out_path=raw_plot_path,
                        title=f"ECG Raw Data - Participant: {pid}, Task: {task}",
                        xlabel="Time",
                        ylabel="ECG Signal",
                        dpi=150,
                    )
                    summary_rows.append(
                        {
                            "participant": pid,
                            "task": task,
                            "error_ECG": f"rpeak_detection_failed: {e}",
                        }
                    )
                    continue  # skip to next task/participant

                raw_plot_path = Path(
                    make_output_path(run_root, pid, task, "ecg", file_structure, "ecg_raw.png")
                )
                plot_time_series(
                    df=df_clean,
                    x_col=x_col,
                    y_col=y_col,
                    out_path=raw_plot_path,
                    title=f"ECG Raw Data - Participant: {pid}, Task: {task}",
                    xlabel="Time",
                    ylabel="ECG Signal",
                    highlight_idx=peak_idx,
                    highlight_color="red",
                    highlight_size=14,
                    dpi=150,
                )

                # returns beat_time_ms, timestamp_s, rr_ms, timestamp_unix (optional)
                rr_df = rpeaks_to_rr(peak_times_ms, peak_times_unix)
                ts_raw = pd.to_numeric(df_clean[x_col], errors="coerce")
                duration_s = float(ts_raw.max() - ts_raw.min())

                clean_df, qc_stats = finalize_clean_table_from_rr(
                    rr_df,
                    source="RAW_ECG",       # TODO better source detection
                    bpm_range=bpm_range,
                )

                # XXX won't need that anymore 
                # # qc_stats = summarize_rr_validity(clean_df)

                rr_plot_path = Path(
                    make_output_path(run_root, pid, task, "ecg", file_structure, "rr_timeseries.png")
                )
                plot_rr_timeseries(
                    clean_df,
                    rr_plot_path,
                    participant_id=f"Participant: {pid}, Task: {task}",
                    dpi=150,
                )


            
            elif mode == "rri":


                meta_rri_source = "iMotions"    # FIXME outomatic detection? from pre-processor?

                # A single row means the Polar stream had already stopped: the preparser
                # then puts its last sample into every later task
                if len(df) < 2 or df["Timestamp"].nunique() < 2:
                    msg = f"ecg_ends_before_task: only {len(df)} RR row(s) in segment"
                    print(f"[ECG] {msg} for participant {pid} and task {task}")
                    summary_rows.append({"participant": pid, "task": task, "error_ECG": msg})
                    continue

                unit = detect_rri_units(df)["unit"] if rri_unit == "auto" else rri_unit

                if unit == "ms":
                    df_ms = df.copy()
                    # make sure we have a canonical rr_ms column
                    if "rr_ms" not in df_ms.columns:
                        df_ms["rr_ms"] = df_ms["RRI"].astype(float)

                # convert ticks to milliseconds (overwrite RRI)
                elif unit == "ticks": 
                    df_ms = convert_polar_ticks_df(df, ticks_col="RRI",new_col="rr_ms", hz=polar_hz)
                
                else:
                    print(f"Unknown RRI units for participant {pid} and task {task}")
                    summary_rows.append({"participant": pid, "task": task, "error_ECG": "Unknown RRI units"})
                    continue


                # build relative timeline of beats
                df_ms["beat_time_ms"] = np.cumsum(df_ms["rr_ms"].astype(float).values)
                df_ms["timestamp_s"]  = df_ms["beat_time_ms"] / 1000.0
                duration_s = float(df_ms["rr_ms"].astype(float).clip(lower=0).sum() / 1000.0)

                #print ("****one line above finalize clean table****")
                clean_df, qc_stats = finalize_clean_table_from_rr(
                        df_ms,
                        source="RRI_POLAR",         # TODO better source detection
                        bpm_range=tuple(ecg_params["hr_outlier_range_bpm"]),
                    )
                if rri_artifact_correction == "kubios":
                    clean_df = flag_rr_artifacts_kubios(clean_df, rr_col="rr_ms", valid_col="valid")
                # print(clean_df.head())
                #print("[ecg_pipeline] RRI clean_df type:", type(clean_df))
                #print("[ecg_pipeline] RRI clean_df shape:", clean_df.shape)
                #print("[ecg_pipeline] RRI clean_df head:\n", clean_df.head())

                rr_plot_path = Path(
                    make_output_path(run_root, pid, task, "ecg", file_structure, "rr_timeseries.png")
                )
                plot_rr_timeseries(
                    clean_df,
                    rr_plot_path,
                    participant_id=f"Participant: {pid}, Task: {task}",
                    dpi=150,
                )
        
        
            elif mode == "bpm":

                meta_rri_source = "no RR Intervals from BPM values"
                print(f"BPM input mode for participant {pid} and task {task}")
                print("Skipping task")
                summary_rows.append({"participant": pid, "task": task, "error_ECG": "BPM input mode"})

                # FIXME #BUG #XXX still return df ? if not make case for clean_table .... or would it be better to keep clean_tabel inside the if clause? 

        
            else:
                print(f"Unknown ECG input format for participant {pid} and task {task}")
                print("Skipping task")

                summary_rows.append({"participant": pid, "task": task, "error_ECG": "Unknown ECG input format"})




            # //HACK From here we have "true" RR intervals but no peak hight. For some metrics that might be important. SO maybe here another loop to distinguish source (rri or raw_ecg) for future metrics //TODO


            # TODO add QC flags for meta data or raising errors for artifacts etc //FIXME
            # then not rr_df anymore but clean_df etc 
            # TODO make cleaning it's own module clean_table.py


            # for now
            # clean_df = rr_df

            print("[ecg_pipeline] before metrics, clean_df is None?", clean_df is None)
            if clean_df is None:
                print("---- clean_df is None -----")
                continue    # jumps to next task

            n_rr_before_trim = len(clean_df)
            if trim_start_sec > 0:
                if "timestamp_s" in clean_df.columns:
                    clean_df = clean_df[clean_df["timestamp_s"] >= trim_start_sec].copy()
                elif "beat_time_ms" in clean_df.columns:
                    clean_df = clean_df[clean_df["beat_time_ms"] >= (trim_start_sec * 1000.0)].copy()

                if clean_df.empty:
                    summary_rows.append(
                        {
                            "participant": pid,
                            "task": task,
                            "error_ECG": f"trim_start_sec_removed_all_data_{trim_start_sec:g}s",
                        }
                    )
                    continue
            
            

            # RR quality counts after trimming, so all counts refer to the same beats
            qc_stats = {
                **rr_qc_stats(clean_df),
                **summarize_rr_validity(clean_df),
                "n_rr_trimmed": int(n_rr_before_trim - len(clean_df)),
            }
            if mode == "rri" and rri_artifact_correction == "kubios":
                n_kubios = int(clean_df["rr_artifact_reason"].astype(str).str.startswith("kubios_").sum())
                artifact_handling = "excluded"
            elif mode == "raw_ecg":
                n_kubios = count_kubios_artifacts_raw(clean_df, nk_artifacts, trim_start_sec)
                artifact_handling = "corrected" if nk_artifacts else "none"
            else:
                n_kubios, artifact_handling = None, "none"
            qc_stats["n_rr_kubios_artifacts"] = n_kubios
            qc_stats["frac_rr_kubios_artifacts"] = (n_kubios / len(clean_df)) if n_kubios is not None and len(clean_df) else None
            qc_stats["kubios_artifact_handling"] = artifact_handling

            # save (cleaned?) rr_intervals as csv //TODO check if that's even wanted/requested? Maybe later
            # Use a consistent, lower-case modality folder name for all ECG outputs.
            save_csv(clean_df, run_root, pid, task, "ecg", file_structure, "ecg_clean.csv", overwrite=True)


            # BUG if NOT mode=="BPM" then we calculate features, otherwise add note to metadata 


            print("[ecg_pipeline] requested_metrics:", requested_metrics)
            #calculate requested metrics
            feats_dict = compute_requested_ecg_features(clean_df, requested_metrics)  
            print("[ecg_pipeline] feats_dict:", feats_dict)
            feats_row  = {"participant": pid, "task": task, **feats_dict}

            summary_rows.append(feats_row)

            feat_particiapnt_task = pd.DataFrame([feats_row])

            save_csv(feat_particiapnt_task, run_root, pid, task, "ecg", file_structure, "features.csv", overwrite=True)

            # IDEA //XXX //TODO create dedicated build_meta module? 
            #save_json(build_meta(..., input_mode=clean_df["source"].iloc[0]), run_root, pid, task, "ECG", file_structure, "meta.json", overwrite=True)

            meta = {
                        "participant": pid,
                        "task": task,
                        "source_file_mode": mode,
                        "rri_unit": unit,
                        "params": {
                            "sampling_rate_hz": ecg_params.get("sampling_rate_hz"),
                            "hr_outlier_range_bpm": ecg_params.get("hr_outlier_range_bpm"),
                            "bandpass_hz": ecg_params.get("bandpass_hz", (5.0, 25.0)),
                            "trim_start_sec": trim_start_sec,
                            "rpeak_method": rpeak_method,
                            "rpeak_fallback": rpeak_fallback,
                            "neurokit": ecg_params.get("neurokit"),
                        },
                        "rri_source" : meta_rri_source,    # how and where the RR Intervals were calculated
                        "rpeak_fallback_reason": rpeak_fallback_reason,
                        "library_versions": _library_versions(),
                        "qc": {
                            "valid_frac": float(clean_df["valid"].mean()) if "valid" in clean_df else None,
                            "duration_s": duration_s,
                            "covered_s": coverage.get("covered_s"),
                            "coverage_max_gap_s": coverage_max_gap_s,
                            "frac_rr_kubios_artifacts": qc_stats["frac_rr_kubios_artifacts"],
                            "kubios_artifact_handling": qc_stats["kubios_artifact_handling"],
                        },
                        "rr_cleaning_qc": qc_stats,
                    }
            
            if mode == "raw_ecg":
                meta["raw_stats"] = raw_stats            # from sanity_check_ecg_raw
            if mode == "rri":
                meta["params"]["rri_artifact_correction"] = rri_artifact_correction

            # error message
            #if error is not None:
            #    meta["error_ECG"] = error

                        # Save ECG metadata into the same lower-case modality folder as the
            # cleaned data and features to avoid mixed "ecg"/"ECG" directories.
            save_json(meta, run_root, pid, task, "ecg", file_structure, filename="meta.json", overwrite=True)

    # Build a DataFrame for the collected summary rows (may be empty).
    summary_df = pd.DataFrame(summary_rows)

    print("[ecg_pipeline] summary_rows length:", len(summary_rows))
    print("[ecg_pipeline] summary_df shape:", summary_df.shape)
    print("[ecg_pipeline] summary_df head:\n", summary_df.head())
    # Put summaries in a stable place for the run (only write when non-empty):
    if not summary_df.empty:
        # Store ECG summaries under a consistent, lower-case folder name.
        summary_dir = os.path.join(run_root, "_summaries", "ecg")
        os.makedirs(summary_dir, exist_ok=True)
        summary_df.to_csv(os.path.join(summary_dir, "features_by_task.csv"), index=False)


    # TODO //FIXME either keep logging and warnings or append to metadata file 

    else:
        # Warn the user explicitly when no metrics were produced so it's easy
        # to spot a silent no-op in notebook runs.
        logger = logging.getLogger(__name__)
        msg = (
            "[ECG pipeline] No ECG metrics were produced for this run. "
            "Check that the input data files exist and that your config "
            "('participants', 'tasks', 'metrics', and params) are correct."
        )
        logger.warning(msg)
        warnings.warn(msg)

    return summary_df



def count_kubios_artifacts_raw(clean_df: pd.DataFrame, nk_artifacts: dict, trim_start_sec: float) -> int:
    """
    Number of beats the Kubios algorithm flags in a raw-ECG segment, after trimming.

    NeuroKit corrects artifacts during peak detection, so the corrected series is
    (almost) clean; the count is taken from the uncorrected peaks instead. Without
    them (HeartPy, no correction) the cleaned RR series itself is counted.
    This makes the figure comparable with the Kubios flags of Polar RRI files.
    """
    if nk_artifacts.get("peak_idx_uncorrected") is not None:
        peaks_ms = nk_artifacts["peak_idx_uncorrected"] / nk_artifacts["fs"] * 1000.0
        rr = rpeaks_to_rr(np.asarray(peaks_ms, dtype=float))
        if trim_start_sec > 0:
            rr = rr[rr["timestamp_s"] >= trim_start_sec]
        rr = rr.reset_index(drop=True)
    else:
        rr = clean_df[["rr_ms"]].reset_index(drop=True)
    if rr.empty:
        return 0
    flagged = flag_rr_artifacts_kubios(rr.assign(valid=True), rr_col="rr_ms", valid_col="valid")
    return int((~flagged["valid"]).sum())


def compute_requested_ecg_features(df: pd.DataFrame,
                                   requested_metrics: list[str]) -> dict:
    # HACK replace by function that reads desired metric and automatically finds corresponding module (or function inside HRV) 

    #FIXME no HRV from BPM ??? 
    """
    Compute ECG metrics from cleaned Dataframe.
    HRV metrics are only computed when we have true RR (not BPM). 
    """

    output_dict = {}
    nk_time = None      # neurokit2 time-domain results, computed once on first NK_ metric

    if "valid" in df.columns:
        df_valid = df[df["valid"] == True].copy()
    else:
        df_valid = df.copy()

    for name in requested_metrics:
        #key = name.upper()
        key = name
        
        
        if key == "RMSSD":
            rmssd = rmssd_from_rr(df_valid)
            output_dict[name] = rmssd

            """
            out["RMSSD"] = rmssd_from_rr(clean_df) if has_true_rr else float("nan")
            # TODO: add SDNN etc. here later
            """
        
        if key == "SDNN":
            sdnn = sdnn_from_rr(df_valid)
            output_dict[name] = sdnn

        if key == "pNN50":
            pnn50 = pnn50_from_rr(df_valid)
            output_dict[name] = pnn50

        # "NK_<metric>" -> neurokit2.hrv_time, e.g. NK_RMSSD, NK_SDNN, NK_pNN50, NK_MeanNN
        if key.startswith("NK_"):
            if nk_time is None:
                nk_time = hrv_time_neurokit(df_valid)
            output_dict[name] = nk_time.get(key.removeprefix("NK_"), float("nan"))


    return output_dict




# --------- new Version here that checks for mode and calls corresponding functions 
# test with new mwetric that'S not calculatable from RRI ???  --------------


def compute_requested_ecg_features_mode(df: pd.DataFrame,
                                        mode: str,
                                   requested_metrics: list[str]) -> dict:
    # HACK replace by function that reads desired metric and automatically finds corresponding module (or function inside HRV) 

    #FIXME no HRV from BPM ??? 
    """
    Compute ECG metrics from cleaned Dataframe.
    HRV metrics are only computed when we have true RR (not BPM). 
    """

    output_dict = {}

    # TODO error handling if only BPM 

    for name in requested_metrics:
        key = name.upper()
        
        # //TODO //FIXME somewhere here check if only RRI or raw_ecg

        if key == "RMSSD":
            rmssd = rmssd_from_rr(df)
            output_dict[name] = rmssd

            """
            out["RMSSD"] = rmssd_from_rr(clean_df) if has_true_rr else float("nan")
            # TODO: add SDNN etc. here later
            """

        if key == "SDNN":
            sdnn = sdnn_from_rr(df)
            output_dict[name] = sdnn

        if key == "pNN50":
            pnn50 = pnn50_from_rr(df)
            output_dict[name] = pnn50
        
    return output_dict
