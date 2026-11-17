from modules.gsr.gsr_pipeline import detect_gsr_value_col

LSL_COLS = ["Timestamp", "GSR", "GSR_CONDUCTANCE"]
NATIVE_COLS = ["Timestamp", "GSR RAW", "GSR Resistance CAL", "GSR Conductance CAL"]


def test_lsl_uses_conductance():
    assert detect_gsr_value_col(LSL_COLS) == "GSR_CONDUCTANCE"


def test_native_uses_calibrated_conductance():
    assert detect_gsr_value_col(NATIVE_COLS) == "GSR Conductance CAL"


def test_choice_does_not_depend_on_order():
    # previously the column picked for a native file leaked into the next LSL file
    picked = [detect_gsr_value_col(cols) for cols in (NATIVE_COLS, LSL_COLS, NATIVE_COLS)]
    assert picked == ["GSR Conductance CAL", "GSR_CONDUCTANCE", "GSR Conductance CAL"]


def test_configured_column_wins():
    assert detect_gsr_value_col(NATIVE_COLS, preferred="GSR Resistance CAL") == "GSR Resistance CAL"


def test_fallback_without_conductance():
    assert detect_gsr_value_col(["Timestamp", "GSR RAW"]) == "GSR RAW"
