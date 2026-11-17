import os
from pathlib import Path

import pytest

from modules import pipeline


def test_validate_cfg_missing_keys():
    with pytest.raises(ValueError) as excinfo:
        pipeline._validate_cfg({"participants": [], "tasks": []})
    assert "Missing required cfg keys" in str(excinfo.value)


def test_validate_cfg_ok():
    cfg = {"participants": [], "tasks": [], "metrics": {}, "params": {}}
    pipeline._validate_cfg(cfg)


def test_check_files_exist_missing_root(tmp_path: Path):
    cfg = {"participants": ["001"], "tasks": ["TaskA"], "input_path": str(tmp_path / "nope")}
    with pytest.raises(FileNotFoundError):
        pipeline._check_files_exist(cfg)


def test_check_files_exist_missing_participant(tmp_path: Path):
    data_root = tmp_path / "data"
    data_root.mkdir()

    cfg = {"participants": ["001", "002"], "tasks": ["TaskA"], "input_path": str(data_root)}

    participant_dir = data_root / "001"
    participant_dir.mkdir()
    (participant_dir / "fooTaskA_preparsed.csv").write_text("a,b\n1,2\n", encoding="utf-8")

    result = pipeline._check_files_exist(cfg)
    missing_participants = {m["participant"] for m in result["missing"] if m["task"] is None}
    assert missing_participants == {"002"}


def test_check_files_exist_missing_task_file(tmp_path: Path):
    data_root = tmp_path / "data"
    data_root.mkdir()

    participant_dir = data_root / "001"
    participant_dir.mkdir()

    cfg = {"participants": ["001"], "tasks": ["TaskA"], "input_path": str(data_root)}
    result = pipeline._check_files_exist(cfg)

    assert any(m["task"] == "TaskA" for m in result["missing"])


def test_normalize_participants_list():
    flat, cohort_map = pipeline._normalize_participants(["001", "002"])
    assert flat == ["001", "002"]
    assert cohort_map == {"001": None, "002": None}


def test_normalize_participants_dict():
    flat, cohort_map = pipeline._normalize_participants(
        {"acq_2024": ["001", "002"], "acq_2025": ["003"]}
    )
    assert flat == ["001", "002", "003"]
    assert cohort_map == {"001": "acq_2024", "002": "acq_2024", "003": "acq_2025"}


def test_normalize_participants_duplicate_raises():
    with pytest.raises(ValueError, match="multiple cohorts"):
        pipeline._normalize_participants({"a": ["001"], "b": ["001"]})


def test_add_cohort_column(tmp_path: Path):
    import pandas as pd
    from modules.io.global_summary import add_cohort_column

    summary_dir = tmp_path / "_summaries"
    summary_dir.mkdir()
    path = summary_dir / "summary_all_modalities.csv"
    pd.DataFrame(
        {"participant": ["001", "002", "003"], "task": ["T", "T", "T"], "x_ECG": [1, 2, 3]}
    ).to_csv(path, index=False)

    add_cohort_column(str(tmp_path), {"001": "acq_2024", "002": "acq_2024", "003": "acq_2025"})

    df = pd.read_csv(path, dtype={"participant": str})
    assert list(df.columns) == ["participant", "cohort", "task", "x_ECG"]
    assert df["cohort"].tolist() == ["acq_2024", "acq_2024", "acq_2025"]
