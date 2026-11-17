from pathlib import Path

import pandas as pd

from modules.paas.paas_pipeline import (
    check_score,
    harmonise_score,
    parse_score,
    run_paas_pipeline,
    task_column,
)

HEADER = "participant_id,source,timestamp,paas_before,paas_task1,paas_task2,paas_task3,paas_task4,paas_task5,comment,notes\n"
TASKS = ["CAVIR_Start1", "CAVIR_Start2", "CAVIR_Start3"]


def _write_table(data_root: Path, body: str, sep: str = ",") -> None:
    paas_dir = data_root / "paas"
    paas_dir.mkdir(parents=True)
    (paas_dir / "all_paas_values.csv").write_text(
        (HEADER + body).replace(",", sep), encoding="utf-8"
    )


def _run(tmp_path: Path, participants, params=None):
    run_root = tmp_path / "results" / "run"
    run_root.mkdir(parents=True)
    cfg = {
        "participants": participants,
        "tasks": TASKS,
        "metrics": {"paas": ["score"]},
        "params": {"paas": params or {}},
    }
    summary = run_paas_pipeline(cfg, str(run_root), "PTM", str(tmp_path / "data"))
    return summary, run_root


def _score(summary, pid, task):
    sel = summary[(summary["participant"] == pid) & (summary["task"] == task)]
    return sel["score"].iloc[0]


def test_task_column():
    assert task_column("CAVIR_Start3") == "paas_task3"
    assert task_column("RedCross", {"RedCross": "paas_task1"}) == "paas_task1"
    assert task_column("Baseline") is None


def test_parse_score():
    assert parse_score("5.5") == (5.5, "")
    assert parse_score("") == (None, "")
    score, issue = parse_score("3;4")
    assert score == 3.0 and "kept first" in issue


def test_run_paas_pipeline(tmp_path: Path):
    _write_table(tmp_path / "data", "p1,in_app,,,9,5.5,,,,,\n")
    summary, run_root = _run(tmp_path, ["p1"])

    assert list(summary["task"]) == TASKS
    assert _score(summary, "p1", "CAVIR_Start1") == 9.0
    assert _score(summary, "p1", "CAVIR_Start2") == 5.5
    assert pd.isna(_score(summary, "p1", "CAVIR_Start3"))
    assert summary["error"].iloc[2] == "No PAAS score for this task"
    assert (run_root / "_summaries" / "paas" / "features_by_task.csv").exists()


def test_missing_participant(tmp_path: Path):
    _write_table(tmp_path / "data", "p1,in_app,,,9,5,4,,,,\n")
    summary, _ = _run(tmp_path, ["p1", "p2"])

    p2 = summary[summary["participant"] == "p2"]
    assert len(p2) == len(TASKS)
    assert p2["score"].isna().all()
    assert (p2["error"] == "No PAAS entry for participant").all()


def test_semicolon_separated_table_and_notes(tmp_path: Path):
    _write_table(
        tmp_path / "data",
        "p1,questionnaire,,4,3,2,7,8,5,,paas_task1 had two answers (3/4) - kept first\n",
        sep=";",
    )
    summary, _ = _run(tmp_path, ["p1"])

    assert _score(summary, "p1", "CAVIR_Start1") == 3.0
    assert _score(summary, "p1", "CAVIR_Start3") == 7.0
    assert (summary["note"] == "paas_task1 had two answers (3/4) - kept first").all()


def test_missing_table(tmp_path: Path):
    summary, _ = _run(tmp_path, ["p1"])
    assert summary["score"].isna().all()
    assert summary["error"].str.startswith("Could not load PAAS table").all()


def test_harmonise_score():
    assert harmonise_score(1.0)["score_pomp"] == 0.0
    assert harmonise_score(9.0)["score_pomp"] == 100.0
    assert harmonise_score(5.0)["score_pomp"] == 50.0
    assert harmonise_score(4.5)["score_int"] == 5.0     # half up, not banker's rounding
    assert harmonise_score(2.5)["score_int"] == 3.0
    assert harmonise_score(None) == {"score_pomp": None, "score_int": None}


def test_check_score():
    assert check_score(5.5, "in_app") == ""
    assert "grid" in check_score(5.5, "questionnaire")
    assert "outside" in check_score(10.0, "in_app")


def test_harmonised_columns_and_range_check(tmp_path: Path):
    _write_table(tmp_path / "data", "p1,in_app,,,4.5,12,,,,,\np2,questionnaire,,,7,,,,,,\n")
    summary, _ = _run(tmp_path, ["p1", "p2"])

    p1 = summary[summary["participant"] == "p1"].set_index("task")
    assert p1.loc["CAVIR_Start1", "score_pomp"] == 43.75
    assert p1.loc["CAVIR_Start1", "score_int"] == 5.0
    assert p1.loc["CAVIR_Start1", "resolution"] == 0.5
    assert pd.isna(p1.loc["CAVIR_Start2", "score"])          # 12 is out of range
    assert "outside" in p1.loc["CAVIR_Start2", "error"]

    p2 = summary[summary["participant"] == "p2"].set_index("task")
    assert p2.loc["CAVIR_Start1", "resolution"] == 1.0
    assert p2.loc["CAVIR_Start1", "source"] == "questionnaire"
