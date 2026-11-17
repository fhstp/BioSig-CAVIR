import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from modules.ecg.ecg_pipeline import run_ecg_pipeline

PID, TASK = "p1", "CAVIR_Start1"


def _write_rri(data_root: Path, rri_ticks: list[float]) -> None:
    pdir = data_root / PID
    pdir.mkdir(parents=True)
    ts = 1_700_000_000 + np.cumsum(np.array(rri_ticks) / 1024.0)
    pd.DataFrame({"Timestamp": ts, "BpM": 75, "RRI": rri_ticks}).to_csv(
        pdir / f"{TASK}_start1700000000000_ECGPolarImotionsNative_preparsed.csv", index=False)


def _run(tmp_path: Path, **ecg_extra):
    cfg = {"participants": [PID], "tasks": [TASK], "metrics": {"ecg": ["RMSSD", "SDNN"]},
           "params": {"ecg": {"hr_outlier_range_bpm": [40, 200], "sampling_rate_hz": 130,
                              "polar_ticks_hz": 1024, **ecg_extra}}}
    run_root = tmp_path / "run"
    summary = run_ecg_pipeline(cfg, str(run_root), "PTM", data_root=str(tmp_path / "data"))
    return summary, run_root


def _alternating(n=200):
    return [800.0 if i % 2 else 840.0 for i in range(n)]    # ticks, successive diff 40 ticks


def test_default_unit_is_ticks(tmp_path):
    _write_rri(tmp_path / "data", _alternating())
    summary, run_root = _run(tmp_path)
    # 40 ticks = 39.0625 ms; the default must convert ticks -> ms
    assert summary.loc[0, "RMSSD"] == pytest.approx(40 * 1000 / 1024, rel=1e-3)
    meta = json.loads(next(run_root.rglob("meta.json")).read_text())
    assert meta["rri_unit"] == "ticks"


def test_ms_unit_keeps_values(tmp_path):
    _write_rri(tmp_path / "data", _alternating())
    summary, _ = _run(tmp_path, rri_unit="ms")
    assert summary.loc[0, "RMSSD"] == pytest.approx(40.0, rel=1e-3)


def test_single_row_segment_reports_ecg_end(tmp_path):
    _write_rri(tmp_path / "data", [800.0])
    summary, _ = _run(tmp_path)
    assert summary.loc[0, "error_ECG"].startswith("ecg_ends_before_task")


def test_invalid_unit_raises(tmp_path):
    _write_rri(tmp_path / "data", _alternating())
    with pytest.raises(ValueError, match="rri_unit"):
        _run(tmp_path, rri_unit="seconds")
