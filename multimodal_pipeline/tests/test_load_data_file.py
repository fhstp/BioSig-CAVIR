from pathlib import Path

import pandas as pd

from modules.io.load_modality import load_data_file


def test_load_data_file_returns_none_for_missing_participant(tmp_path: Path):
    df = load_data_file(str(tmp_path), "001", "TaskA", "ecg")
    assert df is None


def test_load_data_file_reads_matching_csv(tmp_path: Path):
    participant_dir = tmp_path / "001"
    participant_dir.mkdir()
    file_path = participant_dir / "foo_TaskA_ecg_preparsed.csv"
    file_path.write_text("col1,col2\n1,2\n3,4\n", encoding="utf-8")

    df = load_data_file(str(tmp_path), "001", "TaskA", "ecg")

    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == ["col1", "col2"]
    assert len(df) == 2
