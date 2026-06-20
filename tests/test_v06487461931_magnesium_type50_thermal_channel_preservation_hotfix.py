from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_cpp_preserves_preclosure_thermal_channels():
    text = (ROOT / "src/xstar_tools/xstar/cpp/fixed_state_engine.cpp").read_text()
    assert "XSTAR_QUALIFICATION_MAGNESIUM_TYPE50_THERMAL_CHANNEL_PRESERVATION" in text
    assert "const double pre_closure_ans3 = contribution.ans3" in text
    assert "const double pre_closure_ans4 = contribution.ans4" in text
    assert "contribution.ans3 = pre_closure_ans3" in text
    assert "contribution.ans4 = pre_closure_ans4" in text
    assert "Thermal-channel preservation requires primary cooling reduction and source endpoint-energy transport" in text


def test_causal_gate_classifies_v46193_only():
    text = (
        ROOT / "src/xstar_tools/xstar/"
        "v46193_thermal_channel_gate_v0487461931.py"
    ).read_text()
    for gate in (
        "V46193_CJ_MISMATCH_ROWS_8044",
        "V46193_COOLING_MISMATCH_ROWS_8037",
        "V46193_MISMATCH_RECORDS_222",
        "V46193_MISMATCH_SEQUENCES_37",
        "V46193_MISMATCH_CALLS_3_4",
        "V46193_INITIAL_ANSWERS_EXACT_877716",
    ):
        assert gate in text
    assert "MAGNESIUM_TYPE50_MATRIX_CLOSURE_THERMAL_CHANNEL_RECOMPUTATION" in text


def test_audit_closes_type50_without_claiming_mg_cooling():
    text = (
        ROOT / "src/xstar_tools/xstar/"
        "magnesium_type50_thermal_channel_preservation_v0487461931.py"
    ).read_text()
    for gate in (
        "MAGNESIUM_TYPE50_COMMITTED_REVERSE_CJ_EXACT_146286",
        "MAGNESIUM_TYPE50_COMMITTED_REVERSE_COOLING_EXACT_146286",
        "MAGNESIUM_TYPE50_PRE_CLOSURE_THERMAL_CHANNELS_PRESERVED_292572",
        "MAGNESIUM_TYPE50_MATRIX_RATE_CHANNELS_SEPARATED_FROM_THERMAL",
        "MAGNESIUM_COOLING_REMAINS_NONEXACT_0_OF_61",
        "NATIVE_COMPUTED_THERMAL_VALUES_EXACT_1066",
        "NEXT_CAUSAL_FAMILY_REQUIRES_SEPARATE_ATTRIBUTION",
    ):
        assert gate in text
    assert "NATIVE_COMPUTED_THERMAL_VALUES_EXACT_1127" not in text


def test_runner_reuses_endpoint_capture_and_sets_preservation():
    text = (
        ROOT / "run_v0487461931_magnesium_type50_thermal_channel_preservation_hotfix.sh"
    ).read_text()
    assert "v46193_thermal_channel_gate_v0487461931" in text
    assert 'SOURCE_CAPTURE="$BASE193/v0472_all61_magnesium_type50_endpoint_capture"' in text
    assert "XSTAR_QUALIFICATION_MAGNESIUM_TYPE50_THERMAL_CHANNEL_PRESERVATION=1" in text
    assert "V0487461931_SOURCE_CAPTURE_REUSE=ACCEPT" in text
    assert "SOURCE_ARCHIVE" not in text


def test_checker_keeps_downstream_promotion_blocked():
    text = (
        ROOT / "check_v0487461931_magnesium_type50_thermal_channel_preservation.py"
    ).read_text()
    assert "NATIVE_COMPUTED_THERMAL_VALUES_EXACT_1066" in text
    assert "MAGNESIUM_COOLING_REMAINS_NONEXACT_0_OF_61" in text
    assert '"TYPE50_CLOSED_NEXT_FAMILY_REQUIRED"' in text
    assert "PRODUCTION_PROMOTION_BLOCKED" in text
