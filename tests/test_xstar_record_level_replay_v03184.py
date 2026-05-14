from xstar_atomic.xstar_record_level_replay import apply_record_level_ucalc_replay


def test_apply_record_level_ucalc_replay_type53_branches():
    matrix = [
        {"record": "10", "matrix_term_kind": "offdiag_bound_to_continuum_phint53_gain", "full_global_signed_rate_s^-1": "100", "full_global_rate_s^-1": "100"},
        {"record": "10", "matrix_term_kind": "diagonal_bound_phint53_photoionization_loss", "full_global_signed_rate_s^-1": "-100", "full_global_rate_s^-1": "100"},
        {"record": "10", "matrix_term_kind": "offdiag_parent_continuum_to_bound_xstar_ucalc_phint53_milne_gain", "full_global_signed_rate_s^-1": "3", "full_global_rate_s^-1": "3"},
        {"record": "10", "matrix_term_kind": "diagonal_parent_continuum_xstar_ucalc_phint53_milne_loss", "full_global_signed_rate_s^-1": "-3", "full_global_rate_s^-1": "3"},
    ]
    recs = [{"record": "10", "family_key": "type53_rate7:global_type53_phint53_matrix_term", "fortran_n_matrix_rows": "4", "fortran_matrix_self_check_status": "pass", "ans1": "2.5", "ans2": "0.25", "blocker_priority": "blocking", "blocker_hypothesis": "type53_python_proxy_radiation_not_source_equivalent_phint53"}]
    out, changed = apply_record_level_ucalc_replay(matrix, recs)
    vals = [float(r["full_global_signed_rate_s^-1"]) for r in out]
    assert vals == [2.5, -2.5, 0.25, -0.25]
    assert [r["branch"] for r in changed] == ["ans1", "ans1", "ans2", "ans2"]


def test_apply_record_level_ucalc_replay_type50_two_row_decay_maps_to_ans2():
    matrix = [
        {"record": "20", "matrix_term_kind": "offdiag_gain", "full_global_component": "bound_bound_blocks", "full_global_signed_rate_s^-1": "35", "full_global_rate_s^-1": "35"},
        {"record": "20", "matrix_term_kind": "diagonal_loss", "full_global_component": "bound_bound_blocks", "full_global_signed_rate_s^-1": "-35", "full_global_rate_s^-1": "35"},
    ]
    recs = [{"record": "20", "family_key": "unknown:data_type_50_rate_type_4", "fortran_n_matrix_rows": "4", "fortran_matrix_self_check_status": "pass", "ans1": "0", "ans2": "100", "blocker_priority": "high", "blocker_hypothesis": "type50_nontriplet_escape_factor_proxy_0p35"}]
    out, changed = apply_record_level_ucalc_replay(matrix, recs)
    vals = [float(r["full_global_signed_rate_s^-1"]) for r in out]
    assert vals == [100.0, -100.0]
    assert all(r["branch"] == "ans2" for r in changed)
