
import os
import pandas as pd


def update_global_summary(run_root: str,
                          modality: str,
                          summary_df: pd.DataFrame):
    """
    Merge a modality-specific summary_df into a global run summary.

    - Creates global summary file if it does not exist.
    - Renames metric columns to <metric>_<MODALITY>.
    - Merges on ['participant', 'task'].
    - Writes updated global summary back to disk.

    Parameters
    ----------
    run_root : str
        Root directory of the run (from make_run_root).

    modality : str
        Example: "ECG", "GSR", "ET"

    summary_df : pd.DataFrame
        A dataframe with columns:
            participant, task, <metric1>, <metric2>, ...
        produced by the modality pipeline.
    """

    summary_dir = os.path.join(run_root, "_summaries")
    os.makedirs(summary_dir, exist_ok=True)

    global_path = os.path.join(summary_dir, "summary_all_modalities.csv")

    # Identify metric columns (all except keys)
    key_cols = ["participant", "task"]
    if summary_df is None or summary_df.empty:
        return
    missing_keys = [k for k in key_cols if k not in summary_df.columns]
    if missing_keys:
        print(
            f"[WARN] Skipping global summary update for {modality}: "
            f"missing columns {missing_keys}"
        )
        return

    metric_cols = [c for c in summary_df.columns if c not in key_cols]

    # Rename metric columns -> <metric>_<MODALITY> (error_ECG stays error_ECG, not error_ECG_ECG)
    suffix = f"_{modality.upper()}"
    renamed = {
        col: col if col.endswith(suffix) else f"{col}{suffix}"
        for col in metric_cols
    }
    df_mod = summary_df.rename(columns=renamed)

    # If global summary doesn't exist -> create it
    if not os.path.exists(global_path):
        df_mod.to_csv(global_path, index=False)
        return

    # Else merge with existing
    df_global = pd.read_csv(global_path)

    df_merged = df_global.merge(
        df_mod,
        on=["participant", "task"],
        how="outer"
    )

    df_merged.to_csv(global_path, index=False)


def add_cohort_column(run_root: str, cohort_map: dict):
    """
    Insert a 'cohort' column (right after 'participant') into the global summary.

    Called once after all modalities are merged, so the column is not
    duplicated (cohort_x / cohort_y) by the per-modality merges.
    """
    global_path = os.path.join(run_root, "_summaries", "summary_all_modalities.csv")
    if not os.path.exists(global_path):
        return

    df = pd.read_csv(global_path, dtype={"participant": str})
    if "participant" not in df.columns:
        return

    if "cohort" in df.columns:
        df = df.drop(columns="cohort")
    pos = df.columns.get_loc("participant") + 1
    df.insert(pos, "cohort", df["participant"].map(cohort_map))

    df.to_csv(global_path, index=False)
