import numpy as np
import pandas as pd
import pytest

from modules.ecg.ecg_metrics.hrv_rr_time import pnn50_from_rr, rmssd_from_rr
from modules.ecg.ecg_pipeline import run_ecg_pipeline
from modules.ecg.rr_cleaning import flag_rr_artifacts_kubios


def _rr_series(n=150, seed=0, base=800.0):
    rng = np.random.default_rng(seed)
    return base + rng.normal(0, 15, n)


def test_kubios_flags_missed_and_extra_beat():
    rr = _rr_series()
    rr[40] = 1600.0                     # missed beat
    rr[90], rr[91] = 400.0, 400.0       # extra beat
    df = pd.DataFrame({"rr_ms": rr, "valid": True})
    out = flag_rr_artifacts_kubios(df)
    assert not out.loc[40, "valid"]
    assert out.loc[40, "rr_artifact_reason"] == "kubios_missed"
    assert not out.loc[90, "valid"]
    assert out["valid"].mean() > 0.9    # clean beats stay valid


def test_kubios_keeps_existing_reason_and_invalid_rows():
    rr = _rr_series()
    rr[40] = 1600.0
    df = pd.DataFrame({"rr_ms": rr, "valid": True, "rr_artifact_reason": None})
    df.loc[5, ["valid", "rr_artifact_reason"]] = [False, "rr_out_of_range"]
    out = flag_rr_artifacts_kubios(df)
    assert out.loc[5, "rr_artifact_reason"] == "rr_out_of_range"
    assert not out.loc[5, "valid"]


def test_successive_diffs_do_not_bridge_removed_beats():
    # row 2 was removed; 800 -> 900 across the gap must not count
    valid_rows = pd.DataFrame({"rr_ms": [800.0, 810.0, 900.0, 910.0]}, index=[0, 1, 3, 4])
    assert rmssd_from_rr(valid_rows) == pytest.approx(10.0)
    assert pnn50_from_rr(valid_rows) == pytest.approx(0.0)


def _run_pipeline(tmp_path, rr_ticks, **ecg_extra):
    pdir = tmp_path / "data" / "p1"
    pdir.mkdir(parents=True)
    ts = 1_700_000_000 + np.cumsum(rr_ticks / 1024.0)
    pd.DataFrame({"Timestamp": ts, "BpM": 75, "RRI": rr_ticks}).to_csv(
        pdir / "CAVIR_Start1_start1700000000000_ECGPolarImotionsNative_preparsed.csv", index=False)
    cfg = {"participants": ["p1"], "tasks": ["CAVIR_Start1"], "metrics": {"ecg": ["RMSSD", "pNN50"]},
           "params": {"ecg": {"hr_outlier_range_bpm": [40, 200], "sampling_rate_hz": 130,
                              "polar_ticks_hz": 1024, **ecg_extra}}}
    return run_ecg_pipeline(cfg, str(tmp_path / "run"), "PTM", data_root=str(tmp_path / "data"))


def test_pipeline_rmssd_with_missed_and_ectopic_beat(tmp_path):
    # 100 bpm, so a missed beat (1200 ms) stays inside the 40-200 bpm range check
    clean = _rr_series(seed=1, base=600.0) * 1.024  # ticks
    rr = clean.copy()
    rr[60] = clean[60] * 2                          # missed beat
    rr[100], rr[101] = clean[100] * 0.7, clean[101] * 1.3   # premature beat + compensatory pause
    ref = _run_pipeline(tmp_path / "clean", clean, rri_artifact_correction="none").loc[0, "RMSSD"]
    raw = _run_pipeline(tmp_path / "raw", rr, rri_artifact_correction="none").loc[0, "RMSSD"]
    fixed = _run_pipeline(tmp_path / "fixed", rr).loc[0, "RMSSD"]   # default: kubios
    assert raw > 2 * ref                            # a single missed beat inflates RMSSD
    assert fixed == pytest.approx(ref, rel=0.15)


def test_invalid_artifact_option_raises(tmp_path):
    with pytest.raises(ValueError, match="rri_artifact_correction"):
        _run_pipeline(tmp_path, _rr_series() * 1.024, rri_artifact_correction="median")
