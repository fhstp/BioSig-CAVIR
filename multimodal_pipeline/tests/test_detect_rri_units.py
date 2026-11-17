import numpy as np
import pandas as pd
import pytest

from modules.ecg.rr_unit_detection import detect_rri_units


def test_detect_rri_units_ms():
    df = pd.DataFrame(
        {
            "Timestamp": [0.0, 1.0, 2.0],
            "RRI": [np.nan, 1000.0, 1000.0],
        }
    )
    result = detect_rri_units(df, tolerance=0.01)
    assert result["unit"] == "ms"
    assert np.isfinite(result["rel_diff_ms"])


def test_detect_rri_units_ticks():
    df = pd.DataFrame(
        {
            "Timestamp": [0.0, 1.0, 2.0],
            "RRI": [np.nan, 100.0, 100.0],
        }
    )
    result = detect_rri_units(df, tolerance=0.01)
    assert result["unit"] == "ticks"
    assert result["rel_diff_ms"] > 0.5


def test_detect_rri_units_missing_columns():
    df = pd.DataFrame({"Timestamp": [0.0, 1.0]})
    with pytest.raises(KeyError):
        detect_rri_units(df)


def test_detect_rri_units_unknown_for_short_series():
    df = pd.DataFrame({"Timestamp": [0.0], "RRI": [1000.0]})
    result = detect_rri_units(df)
    assert result["unit"] == "unknown"
    assert np.isnan(result["rel_diff_ms"])
