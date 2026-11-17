"""Load PAAS mental-effort ratings into the run summary.

All scores live in one table (default ``<data_root>/paas/all_paas_values.csv``)
with one row per participant and the columns ``paas_task1`` .. ``paas_task5``.
Pipeline tasks are matched to these columns by their trailing number
(``CAVIR_Start3`` -> ``paas_task3``) unless ``params.paas.task_map`` says otherwise.

Harmonisation: all cohorts rated on the same 1-9 scale; the in-app version (2026)
also allowed half points. ``score`` stays the raw rating (primary value). Added:
  - ``score_pomp``: (score - 1) / 8 * 100, percent of maximum possible (0-100)
  - ``score_int``:  score rounded half up to the 9-point grid (sensitivity analysis only)
  - ``resolution``: 0.5 for ``source == "in_app"``, else 1
"""
from __future__ import annotations

import math
import os
import re

import pandas as pd

_LAST_INT = re.compile(r"(\d+)(?!.*\d)")

PAAS_MIN, PAAS_MAX = 1.0, 9.0
HALF_POINT_SOURCES = {"in_app"}


def run_paas_pipeline(cfg, run_root, file_structure, data_root):
    """Collect PAAS scores per participant and task. Returns a summary DataFrame."""
    paas_params = cfg.get("params", {}).get("paas", {}) or {}
    participants = cfg["participants"]
    tasks = cfg["tasks"]
    task_map = paas_params.get("task_map") or {}
    csv_path = paas_params.get("csv_path") or os.path.join(data_root, "paas", "all_paas_values.csv")

    summary_rows = []

    try:
        paas_df = load_paas_table(csv_path)
    except Exception as e:
        print(f"[ERROR] Could not load PAAS table {csv_path}: {e}")
        for pid in participants:
            for task in tasks:
                summary_rows.append({
                    "participant": pid,
                    "task": task,
                    "score": None,
                    "error": f"Could not load PAAS table: {e}",
                })
        return _finish(summary_rows, run_root)

    print(f"[INFO] Loaded PAAS table: {csv_path}")

    for pid in participants:
        if str(pid) not in paas_df.index:
            print(f"[WARN] No PAAS entry for {pid}")
            for task in tasks:
                summary_rows.append({
                    "participant": pid,
                    "task": task,
                    "score": None,
                    "error": "No PAAS entry for participant",
                })
            continue

        row = paas_df.loc[str(pid)]
        source = row.get("source", "") or None
        note = row.get("notes", "")
        if note:
            print(f"[WARN] PAAS note for {pid}: {note}")

        for task in tasks:
            col = task_column(task, task_map)
            raw = row.get(col, "") if col else ""
            score, issue = parse_score(raw)
            if score is not None:
                range_issue = check_score(score, source)
                if range_issue and not (PAAS_MIN <= score <= PAAS_MAX):
                    score, issue = None, range_issue
                elif range_issue:
                    issue = " | ".join(i for i in (issue, range_issue) if i)
            entry = {"participant": pid, "task": task, "score": score,
                     **harmonise_score(score), "resolution": resolution(source), "source": source}
            if issue:
                print(f"[WARN] PAAS {pid} – {task}: {issue}")
            if score is None:
                print(f"[WARN] No PAAS score for {pid} – {task}")
                entry["error"] = issue or "No PAAS score for this task"
            row_note = " | ".join(n for n in (note, issue if score is not None else "") if n)
            if row_note:
                entry["note"] = row_note
            summary_rows.append(entry)

    return _finish(summary_rows, run_root)


def load_paas_table(path: str) -> pd.DataFrame:
    """Read the PAAS table indexed by participant ID. Separator (``,`` or ``;``) is auto-detected."""
    df = pd.read_csv(path, sep=None, engine="python", dtype=str, keep_default_na=False)
    df.columns = [c.strip() for c in df.columns]
    if "participant_id" not in df.columns:
        raise ValueError(f"missing 'participant_id' column (found {list(df.columns)})")
    df["participant_id"] = df["participant_id"].str.strip()
    df = df[df["participant_id"] != ""]
    dupes = df["participant_id"][df["participant_id"].duplicated()].unique()
    if len(dupes):
        print(f"[WARN] Duplicate PAAS rows for {list(dupes)}; using the last one")
        df = df.drop_duplicates("participant_id", keep="last")
    return df.set_index("participant_id")


def task_column(task: str, task_map: dict | None = None) -> str | None:
    """Map a pipeline task name to its PAAS column (``task_map`` first, then trailing number)."""
    if task_map and task in task_map:
        return task_map[task]
    n = _last_int(task)
    return f"paas_task{n}" if n is not None else None


def parse_score(raw) -> tuple[float | None, str]:
    """Convert a cell to a float. Returns ``(score, issue)``; multiple answers keep the first."""
    value = str(raw).strip().replace(",", ".")
    if not value:
        return None, ""
    issue = ""
    parts = [p.strip() for p in re.split(r"[;/]", value) if p.strip()]
    if len(parts) > 1:
        issue = f"multiple answers ({value}); kept first"
    try:
        return float(parts[0]), issue
    except ValueError:
        return None, f"non-numeric PAAS score {value!r}"


def resolution(source) -> float:
    """Step size of the rating scale: half points for the in-app version, else whole points."""
    return 0.5 if source in HALF_POINT_SOURCES else 1.0


def check_score(score: float, source) -> str:
    """Return an issue text if the score is outside 1-9 or off the scale grid of its source."""
    if not PAAS_MIN <= score <= PAAS_MAX:
        return f"PAAS score {score:g} outside {PAAS_MIN:g}-{PAAS_MAX:g}"
    step = resolution(source)
    if abs(score / step - round(score / step)) > 1e-9:
        return f"PAAS score {score:g} not on the {step:g}-point grid of source {source!r}"
    return ""


def harmonise_score(score: float | None) -> dict:
    """POMP score (0-100) and the score rounded half up to whole points."""
    if score is None:
        return {"score_pomp": None, "score_int": None}
    return {
        "score_pomp": (score - PAAS_MIN) / (PAAS_MAX - PAAS_MIN) * 100.0,
        "score_int": float(math.floor(score + 0.5)),   # not round(): Python rounds 4.5 to 4
    }


def _finish(summary_rows, run_root):
    summary_df = pd.DataFrame(summary_rows)
    if run_root is not None and not summary_df.empty:
        summary_dir = os.path.join(run_root, "_summaries", "paas")
        os.makedirs(summary_dir, exist_ok=True)
        summary_df.to_csv(os.path.join(summary_dir, "features_by_task.csv"), index=False)
    return summary_df


def _last_int(text) -> int | None:
    match = _LAST_INT.search(str(text))
    return int(match.group(1)) if match else None
