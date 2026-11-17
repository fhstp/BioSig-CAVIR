from __future__ import annotations
import glob
import os
import pandas as pd
from modules.eyetracking.eye_tracking_pipeline import run_eye_tracking_pipeline
import numpy as np

from .io.directory_tree_setup import make_run_root, ensure_result_dirs
from .io.file_saving import save_csv, save_json, update_run_metadata
from .io.global_summary import update_global_summary, add_cohort_column

from .ecg.ecg_pipeline import run_ecg_pipeline
from .eeg.eeg_pipeline import run_eeg_pipeline
from .gsr.gsr_pipeline import run_gsr_pipeline
from .head_movement.head_movement_pipeline import run_head_movement_pipeline
from .paas.paas_pipeline import run_paas_pipeline
from .qc.qc_summary import build_qc_summary


# HACK maybe find a way to make that more modular/flexible ? 
ALLOWED_MODALITIES = {"ecg", "eeg", "gsr", "eye_tracking", "head_movement", "paas"}



'''
run_cfg = {
    "participants": participants,		# list of participants  ["001", "002", "003"]
                                        # or dict cohort -> list  {"data_acquisition_2024": ["001", "002"], "data_acquisition_2025": ["003"]}
                                        # (dict keys end up in the 'cohort' column of the global summary)
    "tasks": tasks_to_analyze,               # list of tasks   ["RedCross", "CAVIR1", "CAVIR2", "CAVIR3", "CAVIR4", "CAVIR5"]      
    "metrics": metrics,			# directory    { "ecg" : ["RMSSD", "SDNN"], "gsr" : ["FC", "AFD"], "eye_tracking" : ["FC", "AFD"], "eeg": ["idx_mean"], "paas": ["score"] }                 
    "params": {
        "ecg": ecg_params,				# dict
        "gsr": gsr_params,				# dict
        "et":  et_params,				# dict
        "eeg": eeg_params				# dict
    },
    "export_mode": export_mode,     		# string  "combined"             
    "file_structure" : "PTM"				# String participant, task, metric
    "label" : label                     # string or None. Optional label: 'results/1731062458' or 'results/20251108_112530_label'.
    "output_path": output_folder          # String or None - if None, default is "results"
    }


// TODO no paths, that should always be in a fixed file format from the preprocessor

'''

def run_pipeline(cfg):

    _validate_cfg(cfg)

    # flatten cohort dict -> plain participant list, modality pipelines only see the list
    original_cfg = cfg
    flat_participants, cohort_map = _normalize_participants(cfg["participants"])
    cfg = cfg.copy()
    cfg["participants"] = flat_participants

    input_check = _check_files_exist(cfg)

    missing_participants = {
        m["participant"] for m in input_check.get("missing", []) if m.get("task") is None
    }
    if missing_participants:
        print(
            "[WARN] Skipping missing participants: "
            f"{sorted(missing_participants)}"
        )
        cfg = cfg.copy()
        cfg["participants"] = [
            p for p in cfg["participants"] if p not in missing_participants
        ]

    participants = cfg["participants"]
    tasks = cfg["tasks"]
    metrics = cfg["metrics"]
    label = cfg["label"]
    output_path = cfg["output_path"]
    data_root = cfg.get("input_path", "data")


    # build file structure (use singular `file_structure` as used in examples)
    file_structure = cfg["file_structure"]
    run_root = make_run_root(base_results=output_path or "results", label=label or None)
    ensure_result_dirs(run_root, participants, tasks, metrics, file_structure)

    update_run_metadata(
        run_root,
        {
            "config": original_cfg,
            "input_check": input_check,
            "missing_participants": sorted(missing_participants),
            "participants_used": participants,
            "cohorts": cohort_map,
        },
    )

    modalities = [
    m                   # the modality name ("ecg", "gsr", "eye_tracking")
    for m, metrics in metrics.items() 
    if metrics          # keep only if the list of metrics is NOT empty
    ]

    # all modalities the user requestes minus all valid ones, what remains is unknown
    unknown = set(metrics.keys()) - ALLOWED_MODALITIES
    if unknown:
        raise ValueError(
            f"Unknown modalities in export metrics: {unknown}. "
            f"Allowed modalities are: {ALLOWED_MODALITIES}"
        )


    # TODO find a more modular approach (like for modality i modalities : summary_df = pipeline_modality)
    if "ecg" in modalities:
        ecg_summary = run_ecg_pipeline(cfg, run_root, file_structure, data_root=data_root)
        update_global_summary(run_root, "ECG", ecg_summary)
  
    if "gsr" in modalities:
        gsr_summary = run_gsr_pipeline(cfg, run_root, file_structure, data_root=data_root)
        update_global_summary(run_root, "GSR", gsr_summary)
    
    if "eeg" in modalities:
        eeg_summary = run_eeg_pipeline(cfg, run_root, file_structure, data_root=data_root)
        update_global_summary(run_root, "EEG", eeg_summary)

    if "head_movement" in modalities:
        hm_summary = run_head_movement_pipeline(cfg, run_root, file_structure, data_root=data_root)
        update_global_summary(run_root, "HEAD_MOVEMENT", hm_summary)
    
    if "eye_tracking" in modalities:
        et_summary = run_eye_tracking_pipeline(cfg, run_root, file_structure, data_root=data_root)
        update_global_summary(run_root, "EYE_TRACKING", et_summary)

    if "paas" in modalities:
        paas_summary = run_paas_pipeline(cfg, run_root, file_structure, data_root=data_root)
        update_global_summary(run_root, "PAAS", paas_summary)

    if any(c is not None for c in cohort_map.values()):
        add_cohort_column(run_root, cohort_map)

    # dataset-level data-quality tables and report in _summaries/qc/
    qc_params = cfg["params"].get("qc", {}) or {}
    if qc_params.get("enabled", True):
        try:
            build_qc_summary(
                run_root,
                thresholds=qc_params.get("thresholds"),
                expected_modalities=qc_params.get("expected_modalities"),
            )
        except Exception as e:
            print(f"[WARN] QC summary failed: {e}")

    return run_root


def _normalize_participants(participants):
    """
    Accept a plain list of participant IDs or a dict {cohort: [ids]}.
    Returns (flat list of ids, {id: cohort or None}).
    """
    if not isinstance(participants, dict):
        return list(participants), {pid: None for pid in participants}

    flat, cohort_map = [], {}
    for cohort, pids in participants.items():
        for pid in pids:
            if pid in cohort_map:
                raise ValueError(
                    f"Participant {pid} appears in multiple cohorts: "
                    f"'{cohort_map[pid]}' and '{cohort}'"
                )
            cohort_map[pid] = cohort
            flat.append(pid)
    return flat, cohort_map


def _validate_cfg(cfg):
    required = ["participants", "tasks", "metrics", "params"]
    missing = [k for k in required if k not in cfg]
    if missing:
        raise ValueError(f"Missing required cfg keys: {missing}")  #TODO write better error messages



def _check_files_exist(cfg):
    participants = cfg["participants"]
    tasks = cfg["tasks"]
    data_root = cfg.get("input_path", "data")

    result = {
        "data_root": data_root,
        "missing": [],  # list of {participant, task, reason}
    }

    if not os.path.isdir(data_root):
        # Hard error: nothing will work anyway
        raise FileNotFoundError(f"Input data_root not found: {data_root}")

    for pid in participants:
        participant_path = os.path.join(data_root, pid)

        if not os.path.isdir(participant_path):
            result["missing"].append({
                "participant": pid,
                "task": None,
                "reason": "participant_folder_not_found",
            })
            continue

        for task in tasks:
            pattern_any = os.path.join(participant_path, f"*{task}*_preparsed.csv")
            matches_any = glob.glob(pattern_any)
            if not matches_any:
                result["missing"].append({
                    "participant": pid,
                    "task": task,
                    "reason": "no_preparsed_files_for_task",
                })

    # Logging (optional, for console)
    if result["missing"]:
        print("[WARN] Missing data detected for some participants/tasks:")
        for m in result["missing"]:
            if m["task"] is None:
                print(f"  - participant {m['participant']}: folder not found")
            else:
                print(f"  - participant {m['participant']}, task {m['task']}: no *_preparsed.csv for this task")
        print("The pipeline will continue; missing entries will be handled by modality-specific pipelines.")
    else:
        print("All required files available.")

    return result








# def run_ecg_pipeline(cfg, run_root, order="PTM", data_root="data"):

#     participants = cfg["participants"]
#     tasks        = cfg["tasks"]
#     requested    = cfg["metrics"].get("ecg", [])  # e.g., ["RMSSD", "SDNN"]
#     ecg_params   = cfg["params"]["ecg"]



#     ####    path: data/1c9042c3-319b-40f9-af21-3e8b979f688e/Cavir_Start5_start1755694627206_ECG_preparsed.csv


#     for pid in participants:
#         pdir = os.path.join(data_root, str(pid))
#         if not os.path.isdir(pdir):
#             raise FileNotFoundError(f"Participant folder not found: {pdir}")

#         for task in tasks:
#             pattern = os.path.join(pdir, file_pattern.format(task=task))
#             matches = sorted(glob.glob(pattern))
#             if not matches:
#                 # If you prefer failing fast, raise instead of continue:
#                 # raise FileNotFoundError(f"No ECG file for {pid} {task} with pattern {pattern}")
#                 continue

#             raw_path = matches[0]  # take the first match for now
#             df_raw = pd.read_csv(raw_path)
#             clean_df = normalize_rri_from_df(df_raw, ecg_params)

#             # metadata sidecar
#             meta = {
#                 "source_file": raw_path,
#                 "n_rows": int(len(clean_df)),
#                 "params": {
#                     "hr_outlier_range_bpm": ecg_params.get("hr_outlier_range_bpm", [40, 180]),
#                     "window_sec": ecg_params.get("window_sec", 0),
#                     "window_overlap": ecg_params.get("window_overlap", 0.0),
#                     "polar_ticks_hz": ecg_params.get("polar_ticks_hz", POLAR_TICKS_HZ_DEFAULT),
#                 },
#                 "input_mode": "BPM_REPORTED" if (len(clean_df.columns) == 3 and "HR" in clean_df.columns and "rr_ms" in clean_df and clean_df["source"].iloc[0]=="BPM_REPORTED") else "RR_OR_RRI",
#                 "qc": {
#                     "valid_frac": float(clean_df["valid"].mean()) if "valid" in clean_df else None
#                 }
#             }

#             # save clean + meta
#             ecg_dir = save_clean_and_meta(run_root, pid, task, order, clean_df, meta)

#             # features (skip HRV if BPM-only)
#             has_true_rr = "rr_ms" in clean_df.columns and clean_df["source"].iloc[0] != "BPM_REPORTED"
#             feats_df = compute_ecg_features(clean_df, ecg_params, requested) if has_true_rr else pd.DataFrame([{}])
#             if not feats_df.empty:
#                 save_features(ecg_dir, feats_df)

#             summary.append({"pid": pid, "task": task, "rows": len(clean_df)})

#     return pd.DataFrame(summary)










# def run_pipeline_old(guid: str, file_pattern: str = "RC_RedCross_start*_ECG_preparsed") -> dict:
#     """
#     Loads ET velocity for guid, classifies fix/sac, computes stats,
#     computes RMSSD from ECG (raw or RRI) and returns metrics dict.
#     Mirrors your run_pipeline flow, but with modular calls.
#     """
#     root = f"./data/{guid}/"

#     # --- Eye tracking velocity (deg/s) ---
#     et_path = glob.glob(root + file_pattern + "_Eyetracking_preparsed.csv")[0]
#     et_df = pd.read_csv(et_path)
#     vel = load_gaze_velocity_from_csv(et_df)

#     fix, sac = create_fixation_saccade_arrays(
#         vel,
#         sampling_rate_hz=90,     # keep your defaults from the notebook
#         three_state=True,
#         fixation_off_threshold=15,
#         fixation_on_threshold=20,
#         saccade_off_threshold=25,
#         saccade_on_threshold=30,
#         min_fixation_duration_ms=80,
#         min_saccade_duration_ms=25,
#         min_mid_duration_ms=80,
#         smooth_win_ms=15,
#         merge_fix_gap_ms=30,
#     )
#     et_stats = compute_statistics(fix, sac, sampling_rate_hz=90)

#     # --- ECG (either RRI or raw ECG) ---
#     ecg_path = glob.glob(root + file_pattern + "_ECG_preparsed.csv")[0]
#     ecg_df = pd.read_csv(ecg_path)
#     rr = ecg_to_rr(ecg_df, time_col="Timestamp", value_col="HR", has_header=True)
#     rmssd = rmssd_from_rr(rr)

#     return {
#         "FC": et_stats["fixation_count"],
#         "AFD": et_stats["avg_fixation_duration_ms"],
#         "SC": et_stats["saccade_count"],
#         "ASD": et_stats["avg_saccade_duration_ms"],
#         "RMSSD": rmssd,
#     }

# def batch_pipeline(guids, file_pattern: str = "RC_RedCross_start*_ECG_preparsed", dropna_for_corr=True):
#     rows, failures = [], {}
#     for guid in guids:
#         try:
#             res = run_pipeline(guid, file_pattern)
#             rows.append({"GUID": guid, **res})
#         except Exception as e:
#             failures[guid] = str(e)
#     df = pd.DataFrame(rows, columns=["GUID","FC","AFD","SC","ASD","RMSSD"])
#     metrics = df[["FC","AFD","SC","ASD","RMSSD"]]
#     corr = (metrics.dropna() if dropna_for_corr else metrics).corr(method="pearson", min_periods=2)
#     return df, corr, failures

# def do_correlation_analysis(guids, filepatterns):
#     out = []
#     for pattern in filepatterns:
#         df, corr, failures = batch_pipeline(guids, file_pattern=pattern)
#         correlation_heatmap(corr, title=f"Correlation Matrix • {pattern}")
#         out.append({"pattern": pattern, "df_results": df, "corr": corr, "failures": failures})
#     return out
























































# # pipeline.py
# from pathlib import Path
# from typing import Dict, List, Any
# import pandas as pd

# # ---- Public API -------------------------------------------------------------

# def run(cfg: Dict[str, Any]) -> pd.DataFrame:
#     """
#     Orchestrates the run:
#       - iterates participants × tasks × enabled modalities
#       - loads per-modality data (stub)
#       - computes requested metrics (stub)
#       - returns a tidy DataFrame and optionally writes CSVs
#     """
#     _validate_cfg(cfg)
#     participants = cfg["participants"]
#     tasks        = cfg["tasks"]
#     mods_enabled = cfg["modalities_enabled"]  # dict: {"ecg": bool, ...}
#     metrics      = cfg["metrics"]             # dict: {"ecg": [...], ...}
#     paths        = cfg["paths"]               # dict: {"ecg": "...", ...}
#     params       = cfg["params"]              # dict: {"ecg": {...}, ...}
#     export_mode  = cfg.get("export_mode", "combined")
#     out_dir      = Path(cfg.get("output_path", "results"))
#     out_dir.mkdir(parents=True, exist_ok=True)

#     rows = []

#     for pid in participants:
#         for task in tasks:
#             for mod in ["ecg", "gsr", "et"]:
#                 if not mods_enabled.get(mod, False):
#                     continue
#                 mod_metrics = metrics.get(mod, [])
#                 if not mod_metrics:
#                     continue

#                 df_raw = _load_data(mod, paths.get(mod, ""), pid, task)
#                 metric_vals = _compute_metrics(mod, df_raw, mod_metrics, params.get(mod, {}))

#                 rows.append({
#                     "participant_id": pid,
#                     "task": task,
#                     "modality": mod,
#                     **metric_vals
#                 })

#         # export per participant if requested
#         if export_mode == "combined":
#             df_pp = pd.DataFrame([r for r in rows if r["participant_id"] == pid])
#             if not df_pp.empty:
#                 (out_dir / f"{pid}_combined.csv").write_text(df_pp.to_csv(index=False))

#     # export separate files if requested
#     if export_mode == "separate":
#         df_all = pd.DataFrame(rows)
#         if not df_all.empty:
#             for mod in df_all["modality"].unique():
#                 df_mod = df_all[df_all["modality"] == mod]
#                 (out_dir / f"{mod}_metrics.csv").write_text(df_mod.to_csv(index=False))

#     return pd.DataFrame(rows)

# # ---- Internals (simple, safe stubs you can flesh out later) ----------------

# def _validate_cfg(cfg: Dict[str, Any]) -> None:
#     required = ["participants", "tasks", "modalities_enabled", "metrics", "paths", "params"]
#     missing = [k for k in required if k not in cfg]
#     if missing:
#         raise ValueError(f"Missing required cfg keys: {missing}")

# def _load_data(modality: str, base_path: str, participant_id: str, task: str) -> pd.DataFrame:
#     """
#     Looks for CSV like: {base_path}/{participant_id}_{task}.csv
#     If not found, returns empty DataFrame (pipeline still runs).
#     """
#     p = Path(base_path) / f"{participant_id}_{task}.csv"
#     if p.exists():
#         try:
#             return pd.read_csv(p)
#         except Exception:
#             return pd.DataFrame()
#     return pd.DataFrame()

# def _compute_metrics(modality: str, df: pd.DataFrame, metrics: List[str], params: Dict[str, Any]) -> Dict[str, Any]:
#     """
#     Minimal placeholder implementations so you have something to show.
#     Replace with real functions later (e.g., ecg.compute_rmssd(rr), etc.)
#     If required columns are missing, returns NaN for that metric.
#     """
#     import numpy as np
#     out = {}
#     for m in metrics:
#         try:
#             if modality == "ecg":
#                 if m == "MeanHR":
#                     # use 'hr_bpm' if available, else NaN
#                     out[m] = float(np.nanmean(df["hr_bpm"])) if "hr_bpm" in df else np.nan
#                 elif m == "RMSSD":
#                     # expects 'rr_ms' column; simple demo calc
#                     if "rr_ms" in df and len(df["rr_ms"]) > 2:
#                         rr = df["rr_ms"].values.astype(float)
#                         diff = np.diff(rr)
#                         out[m] = float(np.sqrt(np.nanmean(diff**2)))
#                     else:
#                         out[m] = np.nan
#                 elif m == "SDNN":
#                     out[m] = float(np.nanstd(df["rr_ms"])) if "rr_ms" in df else np.nan
#                 else:
#                     out[m] = np.nan

#             elif modality == "gsr":
#                 if m == "SCL_mean":
#                     out[m] = float(np.nanmean(df["scl_uS"])) if "scl_uS" in df else np.nan
#                 elif m == "SCR_amplitude":
#                     # toy example: max phasic if column exists
#                     out[m] = float(np.nanmax(df["scr_uS"])) if "scr_uS" in df else np.nan
#                 elif m == "SCR_frequency":
#                     out[m] = float(np.nansum(df["scr_count"])) if "scr_count" in df else np.nan
#                 elif m == "SCL_std":
#                     out[m] = float(np.nanstd(df["scl_uS"])) if "scl_uS" in df else np.nan
#                 else:
#                     out[m] = np.nan

#             elif modality == "et":
#                 if m == "fixation_count":
#                     out[m] = int(np.nansum(df["fixation_flag"])) if "fixation_flag" in df else np.nan
#                 elif m == "fixation_duration_mean":
#                     out[m] = float(np.nanmean(df["fixation_dur_ms"])) if "fixation_dur_ms" in df else np.nan
#                 elif m == "saccade_amplitude":
#                     out[m] = float(np.nanmean(df["sacc_amp_deg"])) if "sacc_amp_deg" in df else np.nan
#                 elif m == "blink_count":
#                     out[m] = int(np.nansum(df["blink_flag"])) if "blink_flag" in df else np.nan
#                 elif m == "pupil_diameter_mean":
#                     out[m] = float(np.nanmean(df["pupil_mm"])) if "pupil_mm" in df else np.nan
#                 else:
#                     out[m] = np.nan

#             else:
#                 out[m] = np.nan

#         except Exception:
#             out[m] = np.nan
#     return out




















































# # pipeline.py
# from __future__ import annotations
# from pathlib import Path
# from typing import Dict, Any, List, Tuple
# import json, hashlib, datetime

# # ---------- Public API -------------------------------------------------------

# def init_run_dirs(cfg: Dict[str, Any], *, make_latest_symlink: bool = True) -> Dict[str, Any]:
#     """
#     Create the participant → task → modality folder structure and sidecars.

#     Expected cfg keys (from your notebook):
#       - participants: List[str]
#       - tasks: List[str]
#       - modalities_enabled: {"ecg": bool, "gsr": bool, "et": bool}
#       - metrics: {"ecg": [...], "gsr": [...], "et": [...]}
#       - paths: {...}     # input paths (not used here, but recorded in manifest)
#       - params: {"ecg": {...}, "gsr": {...}, "et": {...}}
#       - output_path: str
#       - export_mode: str

#     Returns:
#       dict with:
#         - run_id
#         - run_dir (Path)
#         - paths_registry: List[dict] rows describing where to write things later
#     """
#     _require(cfg, ["participants", "tasks", "modalities_enabled", "metrics", "params", "output_path"])

#     run_id = _make_run_id(cfg)
#     base_out = Path(cfg["output_path"]).resolve()
#     run_dir = base_out / run_id
#     run_dir.mkdir(parents=True, exist_ok=True)

#     # Root sidecars
#     _write_json(run_dir / "_manifest.json", _manifest_from_cfg(cfg, run_id))
#     (run_dir / "exports").mkdir(parents=True, exist_ok=True)  # optional convenience views later

#     # Build dirs and per-level sidecars
#     paths_registry: List[Dict[str, Any]] = []
#     mods = [m for m, on in cfg["modalities_enabled"].items() if on]

#     for pid in cfg["participants"]:
#         p_dir = run_dir / pid
#         p_dir.mkdir(parents=True, exist_ok=True)
#         _touch_gitkeep(p_dir)
#         _write_json(p_dir / "_participant.json", {"participant_id": pid})

#         for task in cfg["tasks"]:
#             t_dir = p_dir / task
#             t_dir.mkdir(parents=True, exist_ok=True)
#             _touch_gitkeep(t_dir)
#             # Optional task sidecar; extend as needed
#             _write_json(t_dir / "_task.json", {"task": task})

#             for mod in mods:
#                 m_dir = t_dir / mod.upper()
#                 m_dir.mkdir(parents=True, exist_ok=True)
#                 _touch_gitkeep(m_dir)
#                 # Record params snapshot per modality at first occurrence
#                 params = cfg["params"].get(mod, {})
#                 _write_json(m_dir / f"_{mod.lower()}_params.json", params, overwrite=False)

#                 # Register common output targets you’ll fill later
#                 paths_registry.append({
#                     "participant_id": pid,
#                     "task": task,
#                     "modality": mod,
#                     "dir": str(m_dir),
#                     "files": {
#                         "metrics_global": str(m_dir / "metrics_global.csv"),
#                         "index_windows": str(m_dir / f"windows_{_win_label(cfg, mod)}.csv"),
#                         # ET event tables (only relevant for ET)
#                         "et_fixations": str(m_dir / "fixations.csv") if mod == "et" else None,
#                         "et_saccades": str(m_dir / "saccades.csv") if mod == "et" else None,
#                     }
#                 })

#     # Save a simple registry for humans (optional)
#     _write_json(run_dir / "_paths_registry.json", {"entries": paths_registry})

#     # Optional "latest" symlink for convenience
#     if make_latest_symlink:
#         latest = base_out / "latest"
#         try:
#             if latest.exists() or latest.is_symlink():
#                 latest.unlink()
#             latest.symlink_to(run_dir, target_is_directory=True)
#         except Exception:
#             pass  # symlink may fail on Windows; ignore gracefully

#     return {"run_id": run_id, "run_dir": run_dir, "paths_registry": paths_registry}


# # ---------- Helpers ----------------------------------------------------------

# def _require(cfg: Dict[str, Any], keys: List[str]) -> None:
#     missing = [k for k in keys if k not in cfg]
#     if missing:
#         raise ValueError(f"Missing required cfg keys: {missing}")

# def _write_json(path: Path, obj: Any, *, overwrite: bool = True) -> None:
#     if path.exists() and not overwrite:
#         return
#     with path.open("w", encoding="utf-8") as f:
#         json.dump(obj, f, indent=2, ensure_ascii=False)

# def _touch_gitkeep(dirpath: Path) -> None:
#     (dirpath / ".gitkeep").touch(exist_ok=True)

# def _now_iso() -> str:
#     # naive timestamp is fine for a local manifest
#     return datetime.datetime.now().strftime("%Y-%m-%dT%H-%M-%S")

# def _make_run_id(cfg: Dict[str, Any]) -> str:
#     # stable-ish short hash over high-level config + timestamp
#     base = {
#         "participants": cfg.get("participants", []),
#         "tasks": cfg.get("tasks", []),
#         "modalities_enabled": cfg.get("modalities_enabled", {}),
#         "metrics": cfg.get("metrics", {}),
#         "params": cfg.get("params", {}),
#         "export_mode": cfg.get("export_mode", ""),
#     }
#     digest = hashlib.sha1(json.dumps(base, sort_keys=True).encode("utf-8")).hexdigest()[:8]
#     return f"run_{_now_iso()}_{digest}"

# def _win_label(cfg: Dict[str, Any], mod: str) -> str:
#     # build a short, consistent window label from params if present
#     p = cfg.get("params", {}).get(mod, {})
#     w = p.get("window_sec", None)
#     ov = p.get("window_overlap", None)
#     if w is None:
#         return "na"
#     if ov is None:
#         return f"{int(w)}s"
#     return f"{int(w)}s_overlap{int(round(ov*100))}"

# def _manifest_from_cfg(cfg: Dict[str, Any], run_id: str) -> Dict[str, Any]:
#     return {
#         "run_id": run_id,
#         "created_at": _now_iso(),
#         "participants": cfg.get("participants", []),
#         "tasks": cfg.get("tasks", []),
#         "modalities_enabled": cfg.get("modalities_enabled", {}),
#         "metrics": cfg.get("metrics", {}),
#         "paths": cfg.get("paths", {}),
#         "params": cfg.get("params", {}),
#         "export_mode": cfg.get("export_mode", ""),
#         "output_path": str(cfg.get("output_path", "")),
#         "notebook": cfg.get("_notebook_name", None),  # optional
#         "code_version": cfg.get("_git_commit", None)  # optional
#     }


