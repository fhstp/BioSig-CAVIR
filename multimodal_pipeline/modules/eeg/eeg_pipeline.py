"""
EEG pipeline - main orchestrator for EEG data processing.

Assumes EEG data is already preprocessed and split per task with
uniform UNIX timestamps.
"""
from __future__ import annotations

import os
import logging
import warnings
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from ..io.load_modality import load_data_file
from ..io.file_saving import save_csv, save_json, make_output_path
from ..qc.coverage import coverage_qc


DEFAULT_FRONTAL_CHANNELS = ["AF3", "F7", "F3", "F4", "F8", "AF4"]
DEFAULT_PARIETAL_CHANNELS = ["P7", "P8"]



def run_eeg_pipeline(cfg, run_root, file_structure, data_root):
    """
    Main EEG pipeline orchestrator.

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
    eeg_params = cfg["params"].get("eeg", {})
    requested_metrics = cfg["metrics"].get("eeg", [])
    participants = cfg["participants"]
    tasks = cfg["tasks"]

    frontal_channels = eeg_params.get("frontal_channels", DEFAULT_FRONTAL_CHANNELS)
    parietal_channels = eeg_params.get("parietal_channels", DEFAULT_PARIETAL_CHANNELS)
    pow_prefix = eeg_params.get("pow_prefix", "POW.")

    apply_quality_filter = eeg_params.get("apply_quality_filter", True)
    cq_prefix = eeg_params.get("cq_prefix", "CQ.")
    eq_overall_col = eeg_params.get("eq_overall_col", "EQ.OVERALL")
    use_eq = eeg_params.get("use_eq", False)
    min_eq_fraction = eeg_params.get("min_eq_fraction", 0.5)
    min_cq = eeg_params.get("min_cq", 2.0)
    min_good_frontal = eeg_params.get("min_good_frontal", 3)
    min_good_parietal = eeg_params.get("min_good_parietal", 1)
    

    lower_q = eeg_params.get("outlier_lower_q", 0.01)
    upper_q = eeg_params.get("outlier_upper_q", 0.99)
    baseline_tasks = set(eeg_params.get("baseline_tasks", []))
    file_pattern = eeg_params.get("file_pattern", "*{task}*{modality}*")

    # "preparsed": *_EEGEmotiv_preparsed.csv from the DataPreParser (comma separated)
    # "emotiv_raw": Emotiv export split per task (";" separated, title line, decimal comma)
    input_format = eeg_params.get("input_format", "preparsed")
    if input_format not in {"preparsed", "emotiv_raw"}:
        raise ValueError(f"params.eeg.input_format must be 'preparsed' or 'emotiv_raw', got {input_format!r}")
    # The preparser writes a fixed 13-channel header over rows that start with an extra timestamp
    # (and 14 channels for 2025), so CQ/POW column names do not match their values. Only the first
    # column (Timestamp) is reliable -> features stay off for preparsed files until that is fixed.
    compute_features = bool(eeg_params.get("compute_features", input_format != "preparsed"))
    features_disabled_reason = None if compute_features else (
        "EEG features disabled: column labels of preparsed EEG files are shifted (preparser header)")
    # gaps between EEG rows longer than this count as missing data (POW rows: 8 Hz)
    coverage_max_gap_s = float(eeg_params.get("coverage_max_gap_s", 0.5))

    summary_rows = []
    baseline_samples_by_participant: dict[str, list[np.ndarray]] = {}

    for pid in participants:
        for task in tasks:
            if input_format == "preparsed":
                # rows have more fields than the header: index_col=False keeps the first
                # field (preparser timestamp) in "Timestamp" and drops the surplus at the end
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", pd.errors.ParserWarning)
                    df = load_data_file(data_root, pid, task, "EEG", pattern=file_pattern,
                                        read_csv_kwargs={"index_col": False})
            else:
                df = load_data_file(
                    data_root,
                    pid,
                    task,
                    "EEG",
                    pattern=file_pattern,
                    sep=";",
                    skip_title_line=True,
                    read_csv_kwargs={
                        "decimal": ",",
                        "engine": "python",
                        "on_bad_lines": "skip",
                    },
                )

            if df is None:
                print(f"No EEG data found for participant {pid} and task {task}")
                summary_rows.append({"participant": pid, "task": task, "error_EEG": "No EEG data found"})
                continue

            df.columns = [str(c).strip() for c in df.columns]
            if "Timestamp" in df.columns:
                df["Timestamp"] = pd.to_numeric(df["Timestamp"], errors="coerce")

            raw_rows = len(df)

            # a single row means the EEG stream had already stopped (preparser repeats the last sample)
            if "Timestamp" not in df.columns or df["Timestamp"].nunique() < 2:
                msg = f"No EEG samples in segment: only {raw_rows} row(s)"
                print(f"[EEG] {msg} for participant {pid} and task {task}")
                summary_rows.append({"participant": pid, "task": task, "error_EEG": msg})
                continue

            coverage = coverage_qc(df["Timestamp"], coverage_max_gap_s)

            if not compute_features:
                summary_rows.append({"participant": pid, "task": task, "n_samples": int(raw_rows)})
                save_json(
                    {
                        "participant": pid,
                        "task": task,
                        "params": {"input_format": input_format, "compute_features": False,
                                   "coverage_max_gap_s": coverage_max_gap_s, "file_pattern": file_pattern},
                        "raw_rows": int(raw_rows),
                        "features_disabled_reason": features_disabled_reason,
                        "qc": coverage,
                    },
                    run_root, pid, task, "eeg", file_structure, filename="meta.json", overwrite=True,
                )
                continue

            if apply_quality_filter:
                df_filtered, quality_stats = mark_and_filter_quality(
                    df,
                    frontal_channels=frontal_channels,
                    parietal_channels=parietal_channels,
                    cq_prefix=cq_prefix,
                    eq_overall_col=eq_overall_col,
                    use_eq=use_eq,
                    min_cq=min_cq,
                    min_good_frontal=min_good_frontal,
                    min_good_parietal=min_good_parietal,
                    min_eq_fraction=min_eq_fraction,
                )
            else:
                df_filtered = df.copy()
                quality_stats = {"quality_filter_applied": False}

            if df_filtered.empty:
                summary_rows.append({
                    "participant": pid,
                    "task": task,
                    "error_EEG": "No samples after quality filtering",
                })
                continue

            df_idx = compute_theta_alpha_index(
                df_filtered,
                frontal_channels=frontal_channels,
                parietal_channels=parietal_channels,
                pow_prefix=pow_prefix,
            )

            df_idx_no_outliers = remove_theta_alpha_outliers(
                df_idx,
                lower_q=lower_q,
                upper_q=upper_q,
            )

            if df_idx_no_outliers.empty:
                summary_rows.append({
                    "participant": pid,
                    "task": task,
                    "error_EEG": "No samples after outlier trimming",
                })
                continue

            if task in baseline_tasks:
                baseline_samples_by_participant.setdefault(str(pid), []).append(
                    df_idx_no_outliers["idx_theta_alpha"].dropna().to_numpy()
                )

            save_csv(
                df_idx_no_outliers,
                run_root,
                pid,
                task,
                "eeg",
                file_structure,
                "eeg_clean.csv",
                overwrite=True,
            )

            feats_dict = compute_requested_eeg_features(
                df_idx_no_outliers,
                requested_metrics=requested_metrics,
            )
            feats_row = {"participant": pid, "task": task, **feats_dict}
            summary_rows.append(feats_row)

            feat_participant_task = pd.DataFrame([feats_row])
            save_csv(
                feat_participant_task,
                run_root,
                pid,
                task,
                "eeg",
                file_structure,
                "features.csv",
                overwrite=True,
            )

            meta = {
                "participant": pid,
                "task": task,
                "params": {
                    "frontal_channels": frontal_channels,
                    "parietal_channels": parietal_channels,
                    "pow_prefix": pow_prefix,
                    "apply_quality_filter": apply_quality_filter,
                    "min_cq": min_cq,
                    "min_good_frontal": min_good_frontal,
                    "min_good_parietal": min_good_parietal,
                    "use_eq": use_eq,
                    "min_eq_fraction": min_eq_fraction,
                    "outlier_lower_q": lower_q,
                    "outlier_upper_q": upper_q,
                    "baseline_tasks": sorted(baseline_tasks),
                    "file_pattern": file_pattern,
                    "input_format": input_format,
                    "coverage_max_gap_s": coverage_max_gap_s,
                },
                "raw_rows": int(raw_rows),
                "rows_after_quality_filter": int(len(df_filtered)),
                "rows_after_outlier_trim": int(len(df_idx_no_outliers)),
                "quality_stats": quality_stats,
                "qc": coverage,
            }

            save_json(
                meta,
                run_root,
                pid,
                task,
                "eeg",
                file_structure,
                filename="meta.json",
                overwrite=True,
            )

    summary_df = pd.DataFrame(summary_rows)

    if baseline_tasks and not summary_df.empty:
        summary_df = add_baseline_z_scores(
            summary_df,
            baseline_samples_by_participant=baseline_samples_by_participant,
            baseline_tasks=baseline_tasks,
        )

    if not summary_df.empty:
        summary_dir = os.path.join(run_root, "_summaries", "eeg")
        os.makedirs(summary_dir, exist_ok=True)
        summary_df.to_csv(os.path.join(summary_dir, "features_by_task.csv"), index=False)
    else:
        logger = logging.getLogger(__name__)
        msg = (
            "[EEG pipeline] No EEG metrics were produced for this run. "
            "Check that the input data files exist and that your config "
            "('participants', 'tasks', 'metrics', and params) are correct."
        )
        logger.warning(msg)
        warnings.warn(msg)

    return summary_df


def mark_and_filter_quality(
    df: pd.DataFrame,
    *,
    frontal_channels: Iterable[str] | None,
    parietal_channels: Iterable[str] | None,
    cq_prefix: str = "CQ.",
    eq_overall_col: str = "EQ.OVERALL",
    use_eq: bool = False,
    min_cq: float = 2.0,
    min_good_frontal: int = 3,
    min_good_parietal: int = 1,
    min_eq_fraction: float = 0.5,
) -> tuple[pd.DataFrame, dict]:
    """
    Apply CQ-based quality filtering to EEG samples.

    A sample is 'quality_ok' if:
      - (optionally) EQ.OVERALL >= min_eq_fraction * max(EQ.OVERALL)
      - AND at least min_good_frontal frontal channels have CQ >= min_cq
      - AND at least min_good_parietal parietal channels have CQ >= min_cq
    """
    df = df.copy()

    if use_eq and eq_overall_col in df.columns:
        eq = pd.to_numeric(df[eq_overall_col], errors="coerce")
        max_eq = eq.max()
        if pd.isna(max_eq) or max_eq <= 0:
            eq_ok = pd.Series(True, index=df.index)
        else:
            eq_threshold = min_eq_fraction * max_eq
            eq_ok = eq >= eq_threshold
    else:
        eq_ok = pd.Series(True, index=df.index)

    if frontal_channels is None:
        frontal_channels = DEFAULT_FRONTAL_CHANNELS
    if parietal_channels is None:
        parietal_channels = DEFAULT_PARIETAL_CHANNELS

    def get_cq_cols(ch_list: Iterable[str]) -> list[str]:
        return [f"{cq_prefix}{ch}" for ch in ch_list if f"{cq_prefix}{ch}" in df.columns]

    frontal_cq_cols = get_cq_cols(frontal_channels)
    parietal_cq_cols = get_cq_cols(parietal_channels)

    if frontal_cq_cols:
        frontal_cq = df[frontal_cq_cols].apply(pd.to_numeric, errors="coerce")
        n_good_frontal = frontal_cq.ge(min_cq).sum(axis=1)
    else:
        n_good_frontal = pd.Series(len(list(frontal_channels)), index=df.index)

    if parietal_cq_cols:
        parietal_cq = df[parietal_cq_cols].apply(pd.to_numeric, errors="coerce")
        n_good_parietal = parietal_cq.ge(min_cq).sum(axis=1)
    else:
        n_good_parietal = pd.Series(len(list(parietal_channels)), index=df.index)

    frontal_ok = n_good_frontal >= min_good_frontal
    parietal_ok = n_good_parietal >= min_good_parietal

    quality_ok = eq_ok & frontal_ok & parietal_ok
    df["quality_ok"] = quality_ok

    before_n = len(df)
    df_filtered = df[df["quality_ok"]].copy()

    quality_stats = {
        "quality_filter_applied": True,
        "rows_before": int(before_n),
        "rows_after": int(len(df_filtered)),
        "retained_frac": float(len(df_filtered) / before_n) if before_n else np.nan,
        "frontal_cq_cols": frontal_cq_cols,
        "parietal_cq_cols": parietal_cq_cols,
    }

    return df_filtered, quality_stats


def compute_theta_alpha_index(
    df: pd.DataFrame,
    frontal_channels: Iterable[str] | None = None,
    parietal_channels: Iterable[str] | None = None,
    pow_prefix: str = "POW.",
    eps: float = 1e-12,
) -> pd.DataFrame:
    """
    Compute theta/alpha index per sample:
      - theta_frontal: mean theta over frontal channels
      - alpha_parietal: mean alpha over parietal channels
      - idx_theta_alpha: log10(theta_frontal / alpha_parietal)
    """
    df = df.copy()

    frontal_channels = list(frontal_channels) if frontal_channels is not None else DEFAULT_FRONTAL_CHANNELS
    parietal_channels = list(parietal_channels) if parietal_channels is not None else DEFAULT_PARIETAL_CHANNELS

    theta_cols_frontal = [f"{pow_prefix}{ch}.Theta" for ch in frontal_channels]
    alpha_cols_parietal = [f"{pow_prefix}{ch}.Alpha" for ch in parietal_channels]

    theta_cols_frontal = [c for c in theta_cols_frontal if c in df.columns]
    alpha_cols_parietal = [c for c in alpha_cols_parietal if c in df.columns]

    df[theta_cols_frontal] = df[theta_cols_frontal].apply(pd.to_numeric, errors="coerce")
    df[alpha_cols_parietal] = df[alpha_cols_parietal].apply(pd.to_numeric, errors="coerce")

    df["theta_frontal"] = df[theta_cols_frontal].mean(axis=1)
    df["alpha_parietal"] = df[alpha_cols_parietal].mean(axis=1)

    ratio = df["theta_frontal"] / (df["alpha_parietal"] + eps)
    df["idx_theta_alpha"] = np.log10(ratio)

    return df


def remove_theta_alpha_outliers(
    df: pd.DataFrame,
    lower_q: float = 0.01,
    upper_q: float = 0.99,
) -> pd.DataFrame:
    """
    Remove samples with extreme idx_theta_alpha values based on quantiles.
    """
    df = df.copy()

    for col in ["theta_frontal", "alpha_parietal", "idx_theta_alpha"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df_nonan = df.dropna(subset=["theta_frontal", "alpha_parietal", "idx_theta_alpha"]).copy()
    if df_nonan.empty:
        return df_nonan

    q = df_nonan["idx_theta_alpha"].quantile([lower_q, upper_q])
    lower = q.loc[lower_q]
    upper = q.loc[upper_q]

    mask = df_nonan["idx_theta_alpha"].between(lower, upper)
    return df_nonan[mask].copy()


def compute_requested_eeg_features(
    df: pd.DataFrame,
    requested_metrics: list[str],
) -> dict:
    """
    Compute requested EEG metrics from a cleaned DataFrame.
    """
    metrics = {
        "n_samples": int(len(df)),
        "theta_frontal_mean": float(df["theta_frontal"].mean()) if "theta_frontal" in df else np.nan,
        "theta_frontal_std": float(df["theta_frontal"].std()) if "theta_frontal" in df else np.nan,
        "alpha_parietal_mean": float(df["alpha_parietal"].mean()) if "alpha_parietal" in df else np.nan,
        "alpha_parietal_std": float(df["alpha_parietal"].std()) if "alpha_parietal" in df else np.nan,
        "idx_mean": float(df["idx_theta_alpha"].mean()) if "idx_theta_alpha" in df else np.nan,
        "idx_std": float(df["idx_theta_alpha"].std()) if "idx_theta_alpha" in df else np.nan,
    }

    if not requested_metrics:
        return metrics

    return {k: v for k, v in metrics.items() if k in requested_metrics}


def add_baseline_z_scores(
    summary_df: pd.DataFrame,
    *,
    baseline_samples_by_participant: dict[str, list[np.ndarray]],
    baseline_tasks: set[str],
    idx_col: str = "idx_mean",
    z_col: str = "z_idx_vs_baseline",
) -> pd.DataFrame:
    """
    Add z-scored idx_mean values relative to participant baseline samples.
    """
    summary_df = summary_df.copy()
    if idx_col not in summary_df.columns:
        summary_df[z_col] = np.nan
        return summary_df

    baseline_stats: dict[str, tuple[float, float]] = {}
    for pid, arrays in baseline_samples_by_participant.items():
        if not arrays:
            baseline_stats[str(pid)] = (np.nan, np.nan)
            continue
        vals = np.concatenate([a for a in arrays if a.size])
        if vals.size == 0:
            baseline_stats[str(pid)] = (np.nan, np.nan)
            continue
        baseline_stats[str(pid)] = (float(np.nanmean(vals)), float(np.nanstd(vals)))

    z_vals = []
    for _, row in summary_df.iterrows():
        pid = str(row.get("participant"))
        base_mean, base_std = baseline_stats.get(pid, (np.nan, np.nan))
        idx_val = row.get(idx_col, np.nan)
        if np.isnan(base_mean) or np.isnan(base_std) or base_std == 0 or pd.isna(idx_val):
            z_vals.append(np.nan)
        else:
            z_vals.append((idx_val - base_mean) / base_std)

    summary_df[z_col] = z_vals

    if baseline_tasks:
        summary_df["baseline_tasks"] = ",".join(sorted(baseline_tasks))

    return summary_df
