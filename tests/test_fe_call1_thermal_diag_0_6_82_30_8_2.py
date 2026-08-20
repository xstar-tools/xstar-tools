from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def test_version_and_cpp_hook_are_diagnostic_only():
    assert 'version = "0.6.82.30.8.2"' in (ROOT/'pyproject.toml').read_text()
    src=(ROOT/'src/xstar_tools/xstar/cpp/xstar_standalone.cpp').read_text()
    assert 'XSTAR_FE_CALL1_THERMAL_DIAG_DIR' in src
    assert 'snapshot.kind == "dsec" && snapshot.call_index == 1u && snapshot.evaluation_index == 1u' in src
    assert 'xstar_fixed_state_write_last_thermal_budget_v1' in src
    assert 'xstar_fixed_state_write_last_element_attribution_v06481235' in src
    assert 'FE_CALL1_THERMAL_DIAG_06823082_CPP_CAPTURE=COMPLETE' in src

def test_rejected_3081_science_fix_is_preserved_not_changed_here():
    src=(ROOT/'src/xstar_tools/xstar/cpp/local_zone_engine.cpp').read_text()
    assert '0.6.82.30.8.1: literal ucalc.f90 Type-57 semantics' in src
    assert 'const int n=i57;' in src

def test_paired_diagnostic_bundle_present():
    d=ROOT/'tools/qualification/diagnostics/fe_call1_06823082_v1'
    for name in (
        'fortran_fe_call1_thermal_diag_06823082_v1.patch',
        'cpp_fe_call1_thermal_diag_06823082_v1.patch',
        'run_fortran_fe_call1_thermal_diag_06823082_v1.sh',
        'run_cpp_fe_call1_thermal_diag_06823082_v1.sh',
        'check_fortran_fe_call1_diag_health_06823082_v1.py',
        'compare_fe_call1_thermal_diag_06823082_v1.py',
    ):
        assert (d/name).is_file(), name
