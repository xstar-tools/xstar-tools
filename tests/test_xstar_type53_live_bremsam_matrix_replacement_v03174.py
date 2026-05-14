from xstar_atomic.xstar_matrix_parity import apply_live_bremsam_type53_photoionization_replacement


def test_apply_live_bremsam_type53_replacement_preserves_sign_and_topology():
    terms = [
        {
            "data_type": "53",
            "full_global_component": "type53_phint53_photoionization_kernel",
            "matrix_role": "M[continuum_or_parent_global_index,bound_global_index]+=phint53_photoionization_rate",
            "matrix_term_kind": "offdiag_bound_to_continuum_phint53_gain",
            "record": "21635",
            "bound_global_index": "39",
            "continuum_or_parent_global_index": "113",
            "matrix_row_global_index": "113",
            "matrix_col_global_index": "39",
            "full_global_signed_rate_s^-1": "44.0",
            "full_global_rate_s^-1": "44.0",
            "signed_rate_s^-1": "44.0",
            "rate_s^-1": "44.0",
        },
        {
            "data_type": "53",
            "full_global_component": "type53_phint53_photoionization_kernel",
            "matrix_role": "M[bound_global_index,bound_global_index]-=phint53_photoionization_rate",
            "matrix_term_kind": "diagonal_bound_phint53_photoionization_loss",
            "record": "21635",
            "bound_global_index": "39",
            "continuum_or_parent_global_index": "113",
            "matrix_row_global_index": "39",
            "matrix_col_global_index": "39",
            "full_global_signed_rate_s^-1": "-44.0",
            "full_global_rate_s^-1": "44.0",
            "signed_rate_s^-1": "-44.0",
            "rate_s^-1": "44.0",
        },
        {"data_type": "68", "full_global_rate_s^-1": "3.0"},
    ]
    live_rows = [
        {
            "record": "21635",
            "bound_global_index": "39",
            "continuum_or_parent_global_index": "113",
            "live_phint53_photo_ans1_s^-1": "1.0",
            "classification": "matrix_differs_from_live_bremsam_phint53_ans1",
        }
    ]
    replaced, changed = apply_live_bremsam_type53_photoionization_replacement(terms, live_rows)
    assert len(replaced) == 3
    assert len(changed) == 2
    assert replaced[0]["matrix_row_global_index"] == "113"
    assert replaced[0]["matrix_col_global_index"] == "39"
    assert float(replaced[0]["full_global_signed_rate_s^-1"]) == 1.0
    assert float(replaced[1]["full_global_signed_rate_s^-1"]) == -1.0
    assert float(replaced[0]["type53_original_over_live_bremsam"]) == 44.0
    assert replaced[2]["data_type"] == "68"
