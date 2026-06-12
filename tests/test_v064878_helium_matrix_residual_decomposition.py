from pathlib import Path

from xstar_tools.xstar.helium_matrix_residual_decomposition import (
    REFINED_ROW_RANGES,
    REGULAR_FAMILIES,
    ROW_RANGES,
    RELEASE,
    SCHEMA,
    scenario_delta,
)


def test_release_and_scope_constants():
    assert RELEASE == "0.6.48.7.10"
    assert SCHEMA == "xstar-tools-v064878-helium-matrix-residual-decomposition-v1"
    assert 53 not in REGULAR_FAMILIES
    assert 71 not in REGULAR_FAMILIES
    assert 99 not in REGULAR_FAMILIES
    assert ("he2_rows_46_54", 46, 54) in ROW_RANGES
    assert ("rows_47_54", 47, 54) in REFINED_ROW_RANGES


def test_scenario_delta_reports_reference_error_reduction():
    baseline = {
        "he1_final_fraction": 0.0,
        "he2_final_fraction": 0.1,
        "he3_final_fraction": 0.9,
        "native_electron_fraction": 1.19,
        "native_charge_residual": 0.01,
        "native_hmctot": -1e-5,
    }
    observed = dict(baseline)
    observed["native_electron_fraction"] = 1.195
    observed["native_charge_residual"] = 0.005
    constraints = {
        "type53": {"records": 31},
        "type71": {"records": 31},
        "type99": {"exact_answers": 6},
    }
    row = scenario_delta(
        "probe", "family", 1, baseline, observed,
        {"electron_fraction": 1.2, "charge_residual": 0.0, "hmctot": -2e-5}, constraints,
    )
    assert row["charge_residual_error_reduction"] == 0.005
    assert abs(row["electron_fraction_error_reduction"] - 0.005) < 1e-15
    assert row["type53_records_exact"] == 31
    assert row["type71_records_exact"] == 31
    assert row["type99_answers_exact"] == 6


def test_cpp_contains_fail_closed_qualification_row_controls():
    cpp = Path(__file__).parents[1] / "src/xstar_tools/xstar/cpp/fixed_state_engine.cpp"
    text = cpp.read_text(encoding="utf-8")
    assert "XSTAR_HELIUM_ABLATE_MATRIX_ROW_MIN" in text
    assert "XSTAR_HELIUM_ABLATE_MATRIX_ROW_MAX" in text
    assert "XSTAR_HELIUM_ABLATE_UNQUALIFIED_TYPE53" in text
    assert "XSTAR_HELIUM_ABLATE_UNQUALIFIED_TYPE71" in text
    assert "XSTAR_HELIUM_ABLATE_UNQUALIFIED_TYPE99" in text
    assert "helium ablation requires XSTAR_QUALIFICATION_ABLATION=1" in text
