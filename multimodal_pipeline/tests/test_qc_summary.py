import json
from pathlib import Path

import pandas as pd
import pytest

from modules.qc.qc_summary import build_qc_summary

TASKS = ["CAVIR_Start1", "CAVIR_Start2"]


def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


def _et_meta(track_loss, duration=100.0):
    return {"qc": {"timebase": {"duration_s": duration, "fs_est_hz": 72.0, "n_gaps": 0},
                   "validity": {"track_loss_excl_blink_frac": track_loss, "blink_time_prop": 0.02,
                                "pupil_both_eyes_valid_frac": 0.95}}}


def _ecg_meta(artifacts, duration=100.0, valid=0.99, covered=None):
    return {"source_file_mode": "rri",
            "qc": {"valid_frac": valid, "duration_s": duration, "covered_s": covered, "coverage_max_gap_s": 3.0,
                   "frac_rr_kubios_artifacts": artifacts, "kubios_artifact_handling": "excluded"},
            "rr_cleaning_qc": {"frac_rr_invalid": 1 - valid, "frac_rr_valid": valid}}


def _eeg_meta(covered, duration=100.0):
    return {"features_disabled_reason": "shifted labels",
            "qc": {"duration_s": duration, "covered_s": covered, "coverage_max_gap_s": 0.5, "fs_est_hz": 8.0}}


def _gsr_meta(out_of_range=0.0, slope=0.0, duration=100.0, rng=1.0):
    return {"raw_stats": {"min_raw": 1.0, "max_raw": 1.0 + rng},
            "qc": {"duration_s": duration, "fs_est_hz": 128.0, "gap_time_s": 0.0, "range_raw": rng,
                   "frac_out_of_range": out_of_range, "frac_steep_slope": slope}}


@pytest.fixture
def run_root(tmp_path: Path) -> Path:
    """Cohort A: p1 (all good, p1/T2 ECG has artifacts), p2 (GSR missing, ECG failed).
    Cohort B: p3, eye tracking only (ECG, GSR, PAAS not recorded)."""
    root = tmp_path / "run"
    _write_json(root / "run_metadata.json", {
        "config": {"tasks": TASKS, "file_structure": "PTM",
                   "metrics": {"eye_tracking": ["x"], "eeg": ["n_samples"], "ecg": ["RMSSD"], "gsr": ["x"],
                               "paas": ["score"]}},
        "cohorts": {"p1": "A", "p2": "A", "p3": "B"},
    })
    for pid in ("p1", "p2", "p3"):
        for task in TASKS:
            tl = 0.5 if (pid, task) == ("p3", "CAVIR_Start2") else 0.05
            _write_json(root / pid / task / "eye_tracking" / "meta.json", _et_meta(tl))
    _write_json(root / "p1" / "CAVIR_Start1" / "ecg" / "meta.json", _ecg_meta(0.01))
    _write_json(root / "p1" / "CAVIR_Start2" / "ecg" / "meta.json", _ecg_meta(0.10, covered=60.0))
    _write_json(root / "p2" / "CAVIR_Start1" / "ecg" / "meta.json", _ecg_meta(0.0, duration=50.0))
    _write_json(root / "p1" / "CAVIR_Start1" / "eeg" / "meta.json", _eeg_meta(99.0))
    _write_json(root / "p1" / "CAVIR_Start2" / "eeg" / "meta.json", _eeg_meta(40.0))
    _write_json(root / "p1" / "CAVIR_Start1" / "gsr" / "meta.json", _gsr_meta())
    _write_json(root / "p1" / "CAVIR_Start2" / "gsr" / "meta.json", _gsr_meta(slope=0.2, rng=0.01))

    def summary(mod, rows):
        path = root / "_summaries" / mod / "features_by_task.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_csv(path, index=False)

    summary("eye_tracking", [{"participant": p, "task": t, "x": 1} for p in ("p1", "p2", "p3") for t in TASKS])
    summary("eeg", [
        {"participant": "p1", "task": "CAVIR_Start1", "n_samples": 800},
        {"participant": "p1", "task": "CAVIR_Start2", "n_samples": 320},
        {"participant": "p2", "task": "CAVIR_Start1", "error_EEG": "No EEG samples in segment: only 1 row(s)"},
        {"participant": "p2", "task": "CAVIR_Start2", "error_EEG": "No EEG data found"},
        *[{"participant": "p3", "task": t, "error_EEG": "No EEG data found"} for t in TASKS],
    ])
    summary("ecg", [
        {"participant": "p1", "task": "CAVIR_Start1", "RMSSD": 30},
        {"participant": "p1", "task": "CAVIR_Start2", "RMSSD": 30},
        {"participant": "p2", "task": "CAVIR_Start1", "RMSSD": 30},
        {"participant": "p2", "task": "CAVIR_Start2", "error_ECG": "ecg_ends_before_task: only 1 RR row(s)"},
        *[{"participant": "p3", "task": t, "error_ECG": "No ECG data found"} for t in TASKS],
    ])
    summary("gsr", [
        {"participant": "p1", "task": "CAVIR_Start1", "x": 1},
        {"participant": "p1", "task": "CAVIR_Start2", "x": 1},
        *[{"participant": p, "task": t, "error_GSR": "No GSR data found"} for p in ("p2", "p3") for t in TASKS],
    ])
    summary("paas", [
        *[{"participant": p, "task": t, "score": 5} for p in ("p1", "p2") for t in TASKS],
        *[{"participant": "p3", "task": t, "error": "No PAAS entry for participant"} for t in TASKS],
    ])
    return root


def _seg(result, pid, task, mod):
    s = result["segments"]
    return s[(s.participant == pid) & (s.task == task) & (s.modality == mod)].iloc[0]


def test_segment_status_and_usable(run_root):
    r = build_qc_summary(str(run_root))

    assert _seg(r, "p1", "CAVIR_Start1", "ecg").usable
    p1_t2 = _seg(r, "p1", "CAVIR_Start2", "ecg")
    assert p1_t2.status == "ok" and not p1_t2.usable and "artifact" in p1_t2.reason

    p2_t2 = _seg(r, "p2", "CAVIR_Start2", "ecg")
    assert p2_t2.status == "failed" and p2_t2.reason.startswith("ecg_ends_before_task")
    assert _seg(r, "p2", "CAVIR_Start1", "ecg").coverage == pytest.approx(0.5)   # 50 s of a 100 s task
    assert not _seg(r, "p2", "CAVIR_Start1", "ecg").usable

    gsr = _seg(r, "p1", "CAVIR_Start2", "gsr")
    assert not gsr.usable and "low variability" in gsr["flags"]
    assert _seg(r, "p2", "CAVIR_Start1", "gsr").status == "missing"

    assert not _seg(r, "p3", "CAVIR_Start2", "eye_tracking").usable
    assert _seg(r, "p1", "CAVIR_Start1", "eye_tracking").quality == pytest.approx(0.95)


def test_not_recorded_by_design(run_root):
    r = build_qc_summary(str(run_root))
    s = r["segments"]
    b = s[s.cohort == "B"]
    assert (b[b.modality.isin(["ecg", "gsr", "paas"])].status == "not_recorded").all()
    # cohort A has GSR for p1, so p2's missing GSR stays "missing"
    assert (s[(s.cohort == "A") & (s.participant == "p2") & (s.modality == "gsr")].status == "missing").all()

    # explicit study design overrides the heuristic
    r2 = build_qc_summary(str(run_root), write=False, expected_modalities={"A": ["eye_tracking", "ecg", "paas"]})
    s2 = r2["segments"]
    assert (s2[(s2.cohort == "A") & (s2.modality == "gsr")].status != "missing").all()


def test_aggregates_and_files(run_root):
    r = build_qc_summary(str(run_root))
    agg = r["by_cohort"].set_index(["cohort", "modality"])

    ecg = agg.loc[("A", "ecg")]
    assert ecg.n_segments_expected == 4
    assert ecg.n_segments_usable == 1
    assert ecg.n_segments_failed == 1
    assert ("B", "ecg") not in agg.index

    et_b = agg.loc[("B", "eye_tracking")]
    assert et_b.n_segments_usable == 1 and et_b.n_participants_all_tasks_usable == 0

    combos = r["combinations"].set_index(["cohort", "combination"])
    assert combos.loc[("A", "eye_tracking+ecg"), "n_segments_usable"] == 1
    assert ("B", "eye_tracking+ecg") not in combos.index

    out = run_root / "_summaries" / "qc"
    for name in ("qc_by_segment.csv", "qc_by_cohort_modality.csv", "qc_modality_combinations.csv",
                 "qc_thresholds.json", "qc_report.md"):
        assert (out / name).exists()
    assert "PAAS harmonisation" in (out / "qc_report.md").read_text(encoding="utf-8")


def test_csv_values_rounded(run_root):
    build_qc_summary(str(run_root))
    seg = pd.read_csv(run_root / "_summaries" / "qc" / "qc_by_segment.csv", dtype=str)
    for col in seg.columns:
        decimals = seg[col].dropna().str.extract(r"^-?\d+\.(\d+)$")[0].dropna().str.len()
        assert (decimals <= 4).all(), col


def test_threshold_override(run_root):
    r = build_qc_summary(str(run_root), write=False, thresholds={"ecg": {"max_artifact_frac": 0.2, "min_coverage": 0.5}})
    assert _seg(r, "p1", "CAVIR_Start2", "ecg").usable


def test_eeg_coverage(run_root):
    r = build_qc_summary(str(run_root))
    ok = _seg(r, "p1", "CAVIR_Start1", "eeg")
    assert ok.usable and ok.coverage == pytest.approx(0.99) and "features disabled" in ok["flags"]
    short = _seg(r, "p1", "CAVIR_Start2", "eeg")
    assert short.status == "ok" and not short.usable and "covers 40%" in short.reason
    assert _seg(r, "p2", "CAVIR_Start1", "eeg").status == "missing"
    assert "EEG features were not computed" in r["report"]


def test_ecg_coverage_uses_covered_time(run_root):
    r = build_qc_summary(str(run_root))
    # 100 s of RR data, but only 60 s without dropouts
    assert _seg(r, "p1", "CAVIR_Start2", "ecg").coverage == pytest.approx(0.6)
    # older runs without covered_s fall back to the RR duration
    assert _seg(r, "p2", "CAVIR_Start1", "ecg").coverage == pytest.approx(0.5)
