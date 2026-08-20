from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_06823083_is_diagnostic_only_and_scoped_to_first_fe_eval():
    text = (ROOT / "src/xstar_tools/xstar/cpp/xstar_standalone.cpp").read_text()
    assert 'XSTAR_FE_CALL1_MATRIX_DIAG_DIR' in text
    assert 'snapshot.call_index == 1u' in text
    assert 'snapshot.evaluation_index == 1u' in text
    assert 'XSTAR_QUALIFICATION_ITERATION_RESOLVED_TRACE' in text
    assert 'XSTAR_QUALIFICATION_ITERATION_TRACE_TARGETS' in text
    assert 'XSTAR_QUALIFICATION_ITERATION_TRACE_DIR' in text
    assert 'restore_env_v06823083' in text


def test_06823083_fortran_patch_captures_matrix_and_first_lucy_iteration():
    patch = (ROOT / "tools/qualification/diagnostics/fe_call1_06823083_v2/fortran_fe_call1_matrix_diag_06823083_v2.patch").read_text()
    for marker in (
        "FE2_SOLVER", "FE2_INPUT", "FE2_MATRIX", "FE2_RR",
        "FE2_CONDENSED", "FE2_SUPSOL", "FE2_AFTER_COND", "FE2_FIXED1",
    ):
        assert marker in patch
    assert "if (lpri.eq.-98) lprim=-98" in patch


def test_06823083_comparator_separates_order_from_numerical_divergence():
    text = (ROOT / "tools/qualification/diagnostics/fe_call1_06823083_v2/compare_fe_call1_matrix_diag_06823083_v2.py").read_text()
    assert "FE2_RECORD_ORDER" in text
    assert "FE2_MATRIX_TERM_IDENT_MISMATCHES" in text
    assert "FE2_MATRIX_TERM_VALUE_MISMATCHES_GT1E-10" in text
    assert "FE2_FIRST_LITERAL_DIVERGENCE" in text
    assert "FE2_FIRST_NUMERICAL_DIVERGENCE" in text
