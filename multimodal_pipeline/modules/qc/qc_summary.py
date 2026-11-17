"""
Dataset-level data-quality summary of one pipeline run.

Reads the per-segment QC values that the modality pipelines write into
``<run_root>/<pid>/<task>/<modality>/meta.json`` plus the error columns of
``_summaries/<modality>/features_by_task.csv`` and writes to ``_summaries/qc/``:

  qc_by_segment.csv            one row per cohort x participant x task x modality
  qc_by_cohort_modality.csv    aggregates per cohort and modality
  qc_modality_combinations.csv usable segments / participants per modality combination
  qc_thresholds.json           the thresholds used
  qc_report.md                 text and tables for the data-quality section of a paper

Segment status:
  ok                     processed, QC values available
  failed                 data present but rejected (sanity check, peak detection, ...)
  missing                expected but no data
  not_recorded           the whole cohort has no data for this modality (by study design),
                         or the cohort is not listed in `expected_modalities`

A segment is `usable` if it is ok and passes the thresholds of its modality.
Can be run on any existing run folder: build_qc_summary("results/<run>").
"""
from __future__ import annotations

import copy
import json
import os

import numpy as np
import pandas as pd

from ..io.directory_tree_setup import build_result_dir


MODALITIES = ("eye_tracking", "eeg", "ecg", "gsr", "paas")

DEFAULT_THRESHOLDS = {
    # share of samples without a detected eye, blinks excluded
    "eye_tracking": {"max_track_loss": 0.25},
    # time covered by EEG rows (gaps > params.eeg.coverage_max_gap_s count as missing)
    "eeg": {"min_coverage": 0.8},
    # Kubios-flagged beats (excluded for Polar RRI, corrected for raw ECG);
    # RMSSD needs at least ~30 s of clean RR data (ultra-short HRV)
    "ecg": {"max_artifact_frac": 0.05, "min_valid_duration_s": 30.0, "min_coverage": 0.8},
    # Kleckner et al. (2018): conductance outside 0.05-60 µS, slopes > 10 µS/s
    "gsr": {"max_out_of_range_frac": 0.05, "max_steep_slope_frac": 0.05, "min_coverage": 0.8,
            "low_variability_range_us": 0.05},
    "paas": {},
}

# error texts that mean "no data" rather than "data rejected"
_MISSING_ERRORS = ("no ecg data found", "no gsr data found", "no eye tracking data found",
                   "no eeg data found", "no eeg samples in segment",
                   "no paas entry for participant", "no paas score for this task")


def build_qc_summary(run_root: str,
                     thresholds: dict | None = None,
                     expected_modalities: dict | None = None,
                     cohorts: dict | None = None,
                     write: bool = True) -> dict:
    """
    Build the QC tables for one run.

    thresholds          overrides of DEFAULT_THRESHOLDS, e.g. {"ecg": {"max_artifact_frac": 0.1}}
    expected_modalities {cohort: [modalities]} recorded per cohort; without it, a cohort
                        with no data at all for a modality counts as not_recorded
    cohorts             {pid: cohort}; default from run_metadata.json

    Returns a dict of DataFrames (segments, by_cohort, combinations) and the report text.
    """
    thr = _merge_thresholds(thresholds)
    run_meta = _read_json(os.path.join(run_root, "run_metadata.json")) or {}
    cfg = run_meta.get("config", {}) or {}
    file_structure = cfg.get("file_structure", "PTM")
    tasks = list(cfg.get("tasks") or [])
    modalities = [m for m in MODALITIES if (cfg.get("metrics") or {}).get(m)]
    cohort_map = cohorts or run_meta.get("cohorts") or {}
    if not cohort_map:
        cohort_map = {p: None for p in run_meta.get("participants_used", [])}

    errors = {m: _read_errors(run_root, m) for m in modalities}

    rows = []
    for pid, cohort in cohort_map.items():
        for task in tasks:
            ref_duration = _et_duration(_read_meta(run_root, pid, task, "eye_tracking", file_structure))
            for mod in modalities:
                meta = None if mod == "paas" else _read_meta(run_root, pid, task, mod, file_structure)
                err = errors[mod].get((str(pid), task))
                row = _segment_row(mod, meta, err, errors[mod], pid, task, ref_duration, thr[mod])
                rows.append({"cohort": cohort, "participant": pid, "task": task, "modality": mod, **row})

    seg = pd.DataFrame(rows)
    if seg.empty:
        raise ValueError(f"No segments found for run {run_root}")
    seg = _mark_not_recorded(seg, expected_modalities)

    by_cohort = _aggregate(seg, thr)
    combos = _combinations(seg)
    report = _report(seg, by_cohort, combos, thr, run_root)

    if write:
        out_dir = os.path.join(run_root, "_summaries", "qc")
        os.makedirs(out_dir, exist_ok=True)
        _rounded(seg).to_csv(os.path.join(out_dir, "qc_by_segment.csv"), index=False)
        _rounded(by_cohort).to_csv(os.path.join(out_dir, "qc_by_cohort_modality.csv"), index=False)
        _rounded(combos).to_csv(os.path.join(out_dir, "qc_modality_combinations.csv"), index=False)
        with open(os.path.join(out_dir, "qc_thresholds.json"), "w", encoding="utf-8") as f:
            json.dump({"thresholds": thr, "expected_modalities": expected_modalities}, f, indent=2)
        with open(os.path.join(out_dir, "qc_report.md"), "w", encoding="utf-8") as f:
            f.write(report)
        print(f"[QC] Data-quality summary written to {out_dir}")

    return {"segments": seg, "by_cohort": by_cohort, "combinations": combos, "report": report}


def _rounded(df: pd.DataFrame, decimals: int = 4) -> pd.DataFrame:
    """Round float columns for the CSV output (values in memory stay unrounded)."""
    return df.round({c: decimals for c in df.select_dtypes("float").columns})


# ---------------------------------------------------------------- per segment

def _segment_row(mod, meta, err, mod_errors, pid, task, ref_duration, thr) -> dict:
    row = {"status": None, "reason": None, "quality": np.nan, "duration_s": np.nan,
           "coverage": np.nan, "usable": False, "flags": None}

    if err is not None:
        missing = any(err.lower().startswith(e) for e in _MISSING_ERRORS)
        row["status"] = "missing" if missing else "failed"
        row["reason"] = err
        return row

    if mod == "paas":
        if (str(pid), task) not in mod_errors["_present"]:
            return {**row, "status": "missing", "reason": "not in PAAS summary"}
        return {**row, "status": "ok", "quality": 1.0, "usable": True}

    if meta is None:
        return {**row, "status": "missing", "reason": "no meta.json"}

    qc = meta.get("qc", {}) or {}
    problems, flags = [], []

    if mod == "eye_tracking":
        val = qc.get("validity") or {}
        tb = qc.get("timebase") or {}
        row["duration_s"] = tb.get("duration_s", np.nan)
        rs = qc.get("resampling") or {}
        row["fs_hz"] = rs.get("tracker_hz", tb.get("fs_est_hz", np.nan))
        row["render_rate_hz"] = rs.get("render_rate_hz", tb.get("fs_est_hz", np.nan))
        row["repeat_frac"] = rs.get("repeat_frac", np.nan)
        row["track_loss_excl_blink"] = val.get("track_loss_excl_blink_frac", np.nan)
        row["blink_time_prop"] = val.get("blink_time_prop", np.nan)
        row["pupil_both_eyes_valid"] = val.get("pupil_both_eyes_valid_frac", np.nan)
        row["n_gaps"] = tb.get("n_gaps", np.nan)
        if pd.isna(row["track_loss_excl_blink"]):
            problems.append("no validity figures (run before QC update)")
        else:
            row["quality"] = 1.0 - row["track_loss_excl_blink"]
            if row["track_loss_excl_blink"] > thr["max_track_loss"]:
                problems.append(f"track loss {row['track_loss_excl_blink']:.0%} > {thr['max_track_loss']:.0%}")
        row["coverage"] = 1.0

    elif mod == "ecg":
        rq = meta.get("rr_cleaning_qc", {}) or {}
        row["duration_s"] = qc.get("duration_s", np.nan)
        row["input_mode"] = meta.get("source_file_mode")
        row["frac_rr_invalid"] = rq.get("frac_rr_invalid", np.nan)
        row["frac_rr_artifacts"] = _first(qc.get("frac_rr_kubios_artifacts"), rq.get("frac_rr_artifacts"))
        row["artifact_handling"] = qc.get("kubios_artifact_handling")
        valid_frac = _first(qc.get("valid_frac"), rq.get("frac_rr_valid"))
        if not pd.isna(row["frac_rr_artifacts"]):
            row["quality"] = 1.0 - row["frac_rr_artifacts"]
            if row["frac_rr_artifacts"] > thr["max_artifact_frac"]:
                problems.append(f"{row['frac_rr_artifacts']:.1%} artifact beats > {thr['max_artifact_frac']:.0%}")
        if not pd.isna(row["duration_s"]) and not pd.isna(valid_frac):
            valid_s = row["duration_s"] * valid_frac
            row["valid_duration_s"] = valid_s
            if valid_s < thr["min_valid_duration_s"]:
                problems.append(f"{valid_s:.0f} s clean RR < {thr['min_valid_duration_s']:.0f} s")
        # time with ECG rows (dropouts excluded); older runs only have the RR duration
        row["coverage_max_gap_s"] = qc.get("coverage_max_gap_s", np.nan)
        row["coverage"] = _coverage(_first(qc.get("covered_s"), row["duration_s"]), ref_duration)
        if not pd.isna(row["coverage"]) and row["coverage"] < thr["min_coverage"]:
            problems.append(f"covers {row['coverage']:.0%} of task")

    elif mod == "eeg":
        row["duration_s"] = qc.get("duration_s", np.nan)
        row["fs_hz"] = qc.get("fs_est_hz", np.nan)
        row["coverage_max_gap_s"] = qc.get("coverage_max_gap_s", np.nan)
        row["coverage"] = _coverage(qc.get("covered_s", np.nan), ref_duration)
        if pd.isna(row["coverage"]):
            problems.append("no coverage figures (run before QC update)")
        else:
            row["quality"] = row["coverage"]
            if row["coverage"] < thr["min_coverage"]:
                problems.append(f"covers {row['coverage']:.0%} of task")
        if meta.get("features_disabled_reason"):
            flags.append("features disabled (preparsed column labels)")

    elif mod == "gsr":
        rs = meta.get("raw_stats", {}) or {}
        q = {**rs, **qc}
        row["duration_s"] = q.get("duration_s", np.nan)
        row["fs_hz"] = q.get("fs_est_hz", np.nan)
        row["frac_out_of_range"] = q.get("frac_out_of_range", np.nan)
        row["frac_steep_slope"] = q.get("frac_steep_slope", np.nan)
        row["range_us"] = _first(q.get("range_raw"),
                                 (q.get("max_raw", np.nan) - q.get("min_raw", np.nan)))
        if pd.isna(row["frac_out_of_range"]):
            problems.append("no artifact figures (run before QC update)")
        else:
            row["quality"] = 1.0 - max(row["frac_out_of_range"], row["frac_steep_slope"])
            if row["frac_out_of_range"] > thr["max_out_of_range_frac"]:
                problems.append(f"{row['frac_out_of_range']:.1%} samples outside 0.05-60 µS")
            if row["frac_steep_slope"] > thr["max_steep_slope_frac"]:
                problems.append(f"{row['frac_steep_slope']:.1%} steep slopes")
        if not pd.isna(row["range_us"]) and row["range_us"] < thr["low_variability_range_us"]:
            flags.append("low variability (low responder or poor contact)")
        active = row["duration_s"] - q.get("gap_time_s", 0.0) if not pd.isna(row["duration_s"]) else np.nan
        row["coverage"] = _coverage(active, ref_duration)
        if not pd.isna(row["coverage"]) and row["coverage"] < thr["min_coverage"]:
            problems.append(f"covers {row['coverage']:.0%} of task")

    row["status"] = "ok"
    row["usable"] = not problems
    row["reason"] = "; ".join(problems) or None
    row["flags"] = "; ".join(flags) or None
    return row


def _mark_not_recorded(seg: pd.DataFrame, expected: dict | None) -> pd.DataFrame:
    seg = seg.copy()
    for (cohort, mod), grp in seg.groupby(["cohort", "modality"], dropna=False):
        if expected is not None and cohort in expected:
            by_design = mod not in expected[cohort]
        else:
            by_design = not grp["status"].isin(["ok", "failed"]).any()
        if by_design:
            idx = grp.index[grp["status"] == "missing"]
            seg.loc[idx, "status"] = "not_recorded"
    return seg


# ---------------------------------------------------------------- aggregation

def _aggregate(seg: pd.DataFrame, thr: dict) -> pd.DataFrame:
    rows = []
    for (cohort, mod), g in seg.groupby(["cohort", "modality"], dropna=False, sort=True):
        if (g["status"] == "not_recorded").all():
            continue
        expected = g[g["status"] != "not_recorded"]
        recorded = expected[expected["status"].isin(["ok", "failed"])]
        ok = expected[expected["status"] == "ok"]
        usable = expected[expected["usable"]]
        n_tasks = expected["task"].nunique()
        per_pid_usable = usable.groupby("participant")["task"].nunique()
        q = ok["quality"].dropna()
        row = {
            "cohort": cohort,
            "modality": mod,
            "n_participants": expected["participant"].nunique(),
            "n_participants_with_data": recorded["participant"].nunique(),
            "n_participants_usable": per_pid_usable.size,
            "n_participants_all_tasks_usable": int((per_pid_usable == n_tasks).sum()),
            "n_segments_expected": len(expected),
            "n_segments_ok": len(ok),
            "n_segments_failed": int((expected["status"] == "failed").sum()),
            "n_segments_missing": int((expected["status"] == "missing").sum()),
            "n_segments_usable": len(usable),
            "pct_usable_of_expected": _pct(len(usable), len(expected)),
            "pct_usable_of_recorded": _pct(len(usable), len(recorded)),
            "quality_median": q.median() if len(q) else np.nan,
            "quality_q25": q.quantile(0.25) if len(q) else np.nan,
            "quality_q75": q.quantile(0.75) if len(q) else np.nan,
            "quality_min": q.min() if len(q) else np.nan,
            "duration_median_s": ok["duration_s"].median(),
            "coverage_median": ok["coverage"].median(),
            "top_reasons": _top_reasons(expected),
        }
        if "fs_hz" in ok and ok["fs_hz"].notna().any():
            fs = ok["fs_hz"].dropna()
            row["fs_median_hz"] = fs.median()
            row["fs_range_hz"] = f"{fs.min():.0f}-{fs.max():.0f}"
        if mod == "eye_tracking":
            rr = ok["render_rate_hz"].dropna() if "render_rate_hz" in ok else pd.Series(dtype=float)
            if len(rr):
                row["render_rate_hz"] = ", ".join(f"{v:.0f}" for v in sorted(rr.round(-1).unique()))
            row["repeat_frac_median"] = ok.get("repeat_frac", pd.Series(dtype=float)).median()
            row["blink_time_prop_median"] = ok.get("blink_time_prop", pd.Series(dtype=float)).median()
        if mod == "ecg" and "input_mode" in ok:
            row["input_modes"] = ", ".join(f"{k}: {v}" for k, v in ok["input_mode"].value_counts().items())
        if mod == "gsr" and "flags" in ok:
            row["n_low_variability"] = int(ok["flags"].fillna("").str.contains("low variability").sum())
        rows.append(row)
    return pd.DataFrame(rows)


def _combinations(seg: pd.DataFrame) -> pd.DataFrame:
    present = set(seg["modality"])
    combos = [c for c in (
        ("eye_tracking",),
        ("eye_tracking", "ecg"),
        ("eye_tracking", "gsr"),
        ("eye_tracking", "ecg", "gsr"),
        ("eye_tracking", "paas"),
        ("eye_tracking", "ecg", "paas"),
        ("eye_tracking", "ecg", "gsr", "paas"),
        ("eye_tracking", "eeg"),
        ("eye_tracking", "eeg", "ecg"),
        ("eye_tracking", "eeg", "paas"),
        ("eye_tracking", "eeg", "ecg", "paas"),
    ) if set(c) <= present]
    usable = seg.pivot_table(index=["cohort", "participant", "task"], columns="modality",
                             values="usable", aggfunc="any", fill_value=False, dropna=False)
    not_recorded = (seg.assign(nr=seg["status"] == "not_recorded")
                    .groupby(["cohort", "modality"], dropna=False)["nr"].all())
    rows = []
    for cohort, g in usable.groupby(level="cohort", dropna=False):
        for c in combos:
            if any(not_recorded.get((cohort, m), False) for m in c):
                continue
            ok = g[list(c)].all(axis=1)
            rows.append({
                "cohort": cohort,
                "combination": "+".join(c),
                "n_segments_usable": int(ok.sum()),
                "n_participants_any_task": int(ok.groupby(level="participant").any().sum()),
                "n_participants_all_tasks": int(ok.groupby(level="participant").all().sum()),
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- report

_LABEL = {"eye_tracking": "Eye tracking", "eeg": "EEG", "ecg": "ECG / HRV", "gsr": "GSR / EDA", "paas": "PAAS"}


def _report(seg, by_cohort, combos, thr, run_root) -> str:
    t_et, t_eeg, t_ecg, t_gsr = thr["eye_tracking"], thr["eeg"], thr["ecg"], thr["gsr"]
    lines = [
        "# Data quality summary",
        "",
        f"Run: `{os.path.basename(os.path.normpath(run_root))}`. "
        "Generated by `modules/qc/qc_summary.py`; all numbers refer to task segments "
        "(participant x task).",
        "",
        "## Quality criteria",
        "",
        "- **Eye tracking**: the headsets track at 60 Hz and deliver one row per rendered frame "
        "(72 or 90 Hz), repeating the previous sample; repeats were removed and samples placed on a "
        "regular 60 Hz grid. Angular gaze velocity was computed from the gaze direction vectors "
        "(binocular mean) and used for I-VT classification. "
        f"Quality: share of samples without a detected eye, blinks excluded "
        f"(bilateral signal loss of 50-500 ms). Segments with more than {t_et['max_track_loss']:.0%} "
        "track loss, implausible sampling rates (outside 30-500 Hz) or more than 5% non-increasing "
        "timestamps were excluded.",
        f"- **EEG**: coverage = time covered by EEG rows relative to the task duration (eye-tracking "
        f"segment); intervals between rows longer than {_gap(seg, 'eeg')} s count as missing data. "
        f"Segments covering less than {t_eeg['min_coverage']:.0%} of the task were excluded.",
        f"- **ECG / HRV**: beats flagged by the Kubios algorithm (Lipponen & Tarvainen, 2019). "
        "For Polar RR intervals flagged beats were excluded; for raw ECG they were corrected during "
        f"R-peak detection (NeuroKit2). Segments with more than {t_ecg['max_artifact_frac']:.0%} flagged "
        f"beats, less than {t_ecg['min_valid_duration_s']:.0f} s of clean RR data, or covering less than "
        f"{t_ecg['min_coverage']:.0%} of the task were excluded. Coverage = time covered by ECG rows "
        f"relative to the task duration; intervals longer than {_gap(seg, 'ecg')} s count as missing data.",
        f"- **GSR / EDA**: following Kleckner et al. (2018), samples outside 0.05-60 µS and slopes "
        f"above 10 µS/s (0.25 s bins). Segments with more than {t_gsr['max_out_of_range_frac']:.0%} "
        f"out-of-range samples or {t_gsr['max_steep_slope_frac']:.0%} steep slopes, flat signals, or "
        f"covering less than {t_gsr['min_coverage']:.0%} of the task were excluded. Segments with a total "
        f"range below {t_gsr['low_variability_range_us']} µS are reported as low variability but kept.",
        "- **PAAS**: missing or out-of-range (outside 1-9) ratings.",
        "",
        "Quality per segment: eye tracking 1 - track loss; EEG coverage; ECG 1 - share of flagged beats; "
        "GSR 1 - max(share out of range, share of steep slopes); values are median [IQR].",
        "",
        "## Results",
        "",
    ]

    for mod in [m for m in MODALITIES if m in set(by_cohort["modality"])]:
        lines.append(f"### {_LABEL[mod]}")
        lines.append("")
        for _, r in by_cohort[by_cohort["modality"] == mod].iterrows():
            s = (f"- **{r['cohort']}**: data for {r['n_participants_with_data']}/{r['n_participants']} "
                 f"participants; {r['n_segments_usable']}/{r['n_segments_expected']} segments usable "
                 f"({r['pct_usable_of_expected']:.0f}%; {r['pct_usable_of_recorded']:.0f}% of recorded), "
                 f"{r['n_segments_failed']} rejected, {r['n_segments_missing']} missing.")
            if not pd.isna(r["quality_median"]) and mod != "paas":
                s += f" Quality {_fmt_q(r)}."
            if mod == "eye_tracking" and not pd.isna(r.get("fs_median_hz", np.nan)):
                s += f" Sampling rate {r['fs_median_hz']:.0f} Hz"
                if isinstance(r.get("render_rate_hz"), str):
                    s += (f" (delivered at {r['render_rate_hz']} Hz frame rate; repeated samples, "
                          f"median {r['repeat_frac_median']:.0%} of rows, removed)")
                s += "."
            if mod == "ecg" and isinstance(r.get("input_modes"), str):
                s += f" Input: {r['input_modes']}."
            if mod == "eeg":
                g = seg[(seg["cohort"] == r["cohort"]) & (seg["modality"] == "eeg")]
                if g["flags"].fillna("").str.contains("features disabled").any():
                    s += (" EEG features were not computed: the column labels of the preparsed EEG "
                          "files are shifted, only timestamps were used.")
            if mod == "gsr" and r.get("n_low_variability", 0):
                s += f" {int(r['n_low_variability'])} segments with low variability."
            if isinstance(r["top_reasons"], str) and r["top_reasons"]:
                s += f" Main reasons: {r['top_reasons']}."
            lines.append(s)
        lines.append("")

    not_rec = seg[seg["status"] == "not_recorded"].groupby("cohort")["modality"].unique()
    if len(not_rec):
        lines.append("Not recorded by design: " + "; ".join(
            f"{c}: {', '.join(_LABEL.get(m, m) for m in sorted(ms))}" for c, ms in not_rec.items()) + ".")
        lines.append("")

    lines += ["## Usable segments per modality combination", "", _md_table(combos), ""]
    lines += ["## Table: quality per cohort and modality", "", _md_table(by_cohort[[
        "cohort", "modality", "n_participants", "n_participants_with_data", "n_segments_expected",
        "n_segments_usable", "pct_usable_of_expected", "quality_median", "quality_q25", "quality_q75",
    ]].round(3)), ""]

    if "paas" in set(seg["modality"]):
        lines += [
            "## PAAS harmonisation",
            "",
            "Mental effort was rated on the 9-point Paas scale (1 = very, very low; 9 = very, very high "
            "mental effort). Cohorts 2024/2025 used a questionnaire with whole points; cohort 2026 rated "
            "in-app and could also select half points (17 steps). Because both versions share the same "
            "anchors and range, raw ratings were analysed on the common 1-9 scale. For interpretability we "
            "additionally report POMP scores (percent of maximum possible, (x - 1) / 8 x 100). In a "
            "sensitivity analysis, half-point ratings were rounded half up to whole points (`score_int`).",
            "",
        ]

    lines += [
        "## References",
        "",
        "- Lipponen, J. A., & Tarvainen, M. P. (2019). A robust algorithm for heart rate variability time "
        "series artefact correction using novel beat classification. *Journal of Medical Engineering & "
        "Technology*, 43(3), 173-181.",
        "- Kleckner, I. R., et al. (2018). Simple, transparent, and flexible automated quality assessment "
        "procedures for ambulatory electrodermal activity data. *IEEE Transactions on Biomedical "
        "Engineering*, 65(7), 1460-1467.",
        "- Paas, F. G. W. C. (1992). Training strategies for attaining transfer of problem-solving skill in "
        "statistics: A cognitive-load approach. *Journal of Educational Psychology*, 84(4), 429-434.",
        "- Cohen, P., Cohen, J., Aiken, L. S., & West, S. G. (1999). The problem of units and the "
        "circumstance for POMP. *Multivariate Behavioral Research*, 34(3), 315-346.",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------- helpers

def _merge_thresholds(overrides):
    thr = copy.deepcopy(DEFAULT_THRESHOLDS)
    for mod, vals in (overrides or {}).items():
        thr.setdefault(mod, {}).update(vals or {})
    return thr


def _read_json(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _read_meta(run_root, pid, task, mod, file_structure):
    return _read_json(os.path.join(build_result_dir(run_root, pid, task, mod, file_structure), "meta.json"))


def _read_errors(run_root, mod) -> dict:
    """{(pid, task): error text} from the modality summary; key "_present" holds all rows."""
    path = os.path.join(run_root, "_summaries", mod, "features_by_task.csv")
    if not os.path.exists(path):
        return {"_present": set()}
    df = pd.read_csv(path, dtype={"participant": str})
    err_cols = [c for c in df.columns if c.startswith("error")]
    out = {"_present": set(zip(df["participant"].astype(str), df["task"]))}
    for _, r in df.iterrows():
        msgs = [str(r[c]) for c in err_cols if pd.notna(r[c]) and str(r[c]).strip()]
        if msgs:
            out[(str(r["participant"]), r["task"])] = "; ".join(msgs)
    return out


def _et_duration(meta):
    if not meta:
        return np.nan
    return ((meta.get("qc") or {}).get("timebase") or {}).get("duration_s", np.nan)


def _coverage(duration, ref):
    if pd.isna(duration) or pd.isna(ref) or not ref:
        return np.nan
    return float(min(duration / ref, 1.0))


def _first(*vals):
    for v in vals:
        if v is not None and not (isinstance(v, float) and np.isnan(v)):
            return v
    return np.nan


def _pct(a, b):
    return 100.0 * a / b if b else np.nan


def _top_reasons(g, n=3):
    reasons = g.loc[g["status"].isin(["failed", "missing"]) | (~g["usable"] & (g["status"] == "ok")), "reason"]
    reasons = reasons.dropna().str.replace(r"\[.*\]", "", regex=True).str.split(";").explode().str.strip()
    reasons = reasons.str.replace(r"\d+(\.\d+)?%?", "#", regex=True)    # group by rule, not value
    counts = reasons[reasons != ""].value_counts().head(n)
    return ", ".join(f"{k} ({v})" for k, v in counts.items())


def _gap(seg, mod):
    vals = seg.loc[seg["modality"] == mod, "coverage_max_gap_s"].dropna().unique()         if "coverage_max_gap_s" in seg else []
    return "/".join(f"{v:g}" for v in sorted(vals)) or "n/a"


def _fmt_q(r):
    return f"{r['quality_median']:.3f} [{r['quality_q25']:.3f}-{r['quality_q75']:.3f}]"


def _md_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_none_"
    cols = list(df.columns)
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, r in df.iterrows():
        out.append("| " + " | ".join("" if pd.isna(v) else (f"{v:.3g}" if isinstance(v, float) else str(v))
                                     for v in r) + " |")
    return "\n".join(out)
