import pandas as pd
import pytest

from modules.eyetracking.metrics import compute_pupil_metrics


def test_zero_and_placeholder_samples_are_invalid():
    # 0 and -0.1 are what the headset writes during blinks / track loss
    df = pd.DataFrame({"pupil_l_mm": [4.0, 0.0, -0.1, 4.0],
                       "pupil_r_mm": [5.0, 0.0, -0.1, 5.0]})
    m = compute_pupil_metrics(df)
    assert m["pupil_valid_fraction"] == pytest.approx(0.5)
    assert m["pupil_min_mm"] == pytest.approx(4.5)
    assert m["pupil_mean_mm"] == pytest.approx(4.5)


def test_one_valid_eye_is_used_alone():
    df = pd.DataFrame({"pupil_l_mm": [4.0, 0.0], "pupil_r_mm": [6.0, 3.0]})
    m = compute_pupil_metrics(df)
    assert m["pupil_valid_fraction"] == pytest.approx(1.0)
    assert m["pupil_min_mm"] == pytest.approx(3.0)   # left invalid -> right only
    assert m["pupil_max_mm"] == pytest.approx(5.0)   # (4 + 6) / 2


def test_existing_validity_masks_are_respected():
    df = pd.DataFrame({"pupil_l_mm": [4.0, 4.0], "pupil_r_mm": [4.0, 4.0],
                       "valid_pupil_l": [True, False], "valid_pupil_r": [True, False]})
    m = compute_pupil_metrics(df)
    assert m["pupil_valid_fraction"] == pytest.approx(0.5)


def test_all_invalid_returns_empty_metrics():
    df = pd.DataFrame({"pupil_l_mm": [0.0, -0.1], "pupil_r_mm": [0.0, -0.1]})
    m = compute_pupil_metrics(df)
    assert m["pupil_valid_fraction"] == 0.0
    assert m["pupil_mean_mm"] is None
