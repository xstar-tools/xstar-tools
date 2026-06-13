from pathlib import Path


def test_two_state_promotion_sources_present():
    root = Path(__file__).resolve().parents[1]
    fixed = (root / 'src/xstar_tools/xstar/cpp/fixed_state_engine.cpp').read_text()
    standalone = (root / 'src/xstar_tools/xstar/cpp/xstar_standalone.cpp').read_text()
    assert 'XSTAR_QUALIFICATION_TYPE53_TWO_STATE_PROMOTION' in fixed
    assert '--controller-smoke-evaluations' in standalone
    assert 'runtime_state_workspace_evaluations' in standalone


def test_embedded_evaluation60_workspace_present():
    root = Path(__file__).resolve().parents[1]
    bundle = root / 'src/xstar_tools/benchmarks/v0648719_type53_two_state_promotion/evaluation60'
    assert (bundle / 'type53_independent_state_runtime_records.csv').is_file()
    assert (bundle / 'type53_independent_state_runtime_matrix_terms.csv').is_file()
    assert (bundle / 'dsec_radiation_workspace.csv').is_file()
    assert (bundle / 'dsec_continuum_tau_workspace.csv').is_file()


def test_full_controller_nonzero_result_is_scientific_reject_not_not_run():
    from xstar_tools.xstar.type53_two_state_thermal_promotion_audit import _full_controller_assessment
    summary = {
        'total_evaluations': 14,
        'dsec_evaluations': 10,
        'python_callbacks': 0,
        'runtime_state_workspace_evaluations': 0,
        'reference_state_identity': False,
        'max_abs_hmctot_delta_to_reference': 1.335393908894136,
    }
    result = _full_controller_assessment(summary, 20)
    assert result['status'] == 'REJECT'
    assert result['completed'] is True
    assert result['returncode'] == 20
    assert result['runtime_state_workspace_evaluations'] == 0


def test_checker_supports_existing_output_recovery():
    root = Path(__file__).resolve().parents[1]
    checker = (root / 'check_v048719_type53_two_state_thermal_promotion_audit.py').read_text()
    audit = (root / 'src/xstar_tools/xstar/type53_two_state_thermal_promotion_audit.py').read_text()
    assert 'recover_existing_output' in checker
    assert '--recover-existing' in audit
    assert 'full_controller_assessment' in audit
