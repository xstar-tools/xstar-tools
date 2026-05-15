from xstar_atomic.xstar_record_level_replay import apply_record_level_ucalc_replay, family_selector_matches


def test_family_selector_type50_matches_legacy_unknown_key():
    text = "unknown:data_type_50_rate_type_4 type50_nontriplet_escape_factor_proxy_0p35"
    assert family_selector_matches("type50", text)
    assert family_selector_matches("bound-bound", text)


def test_apply_record_level_ucalc_replay_families_type50_alias():
    matrix = [
        {"record": "20", "matrix_term_kind": "offdiag_gain", "full_global_component": "bound_bound_blocks", "full_global_signed_rate_s^-1": "35", "full_global_rate_s^-1": "35"},
        {"record": "20", "matrix_term_kind": "diagonal_loss", "full_global_component": "bound_bound_blocks", "full_global_signed_rate_s^-1": "-35", "full_global_rate_s^-1": "35"},
    ]
    recs = [{
        "record": "20",
        "family_key": "unknown:data_type_50_rate_type_4",
        "fortran_n_matrix_rows": "4",
        "fortran_matrix_self_check_status": "pass",
        "ans1": "0",
        "ans2": "100",
        "blocker_priority": "high",
        "blocker_hypothesis": "type50_nontriplet_escape_factor_proxy_0p35",
    }]
    out, changed = apply_record_level_ucalc_replay(matrix, recs, replacement_mode="families", families=["type50"])
    assert len(changed) == 2
    assert [float(r["full_global_signed_rate_s^-1"]) for r in out] == [100.0, -100.0]
