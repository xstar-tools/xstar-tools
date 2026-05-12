from pathlib import Path

from xstar_atomic.xstar_matrix_parity import (
    audit_type68_collision_rates,
    write_type68_collision_rate_audit,
)


def test_type68_collision_rate_audit_matches_q_ne_and_partner(tmp_path):
    matrix_csv = tmp_path / "matrix.csv"
    solve_csv = tmp_path / "solve.csv"
    ne = 1.0e8
    q = 2.5e-10
    rate = ne * q
    matrix_csv.write_text(
        "matrix_row_global_index,matrix_col_global_index,full_global_signed_rate_s^-1,full_global_rate_s^-1,"
        "rate_s^-1,data_type,source_method,source_format,record,matrix_role,transition_kind,from_global_index,to_global_index,"
        "from_level_label,to_level_label,electron_density_cm^-3,q_excitation_cm3_s,q_deexcitation_cm3_s,directional_q_cm3_s,"
        "collision_rate_scale_applied,upsilon,temperature_K,xstar_calt67_68_effective_temperature_K,xstar_calt67_68_temperature_floor_applied,eval_method\n"
        f"39,34,{rate},{rate},{rate},68,helike_calt68_zhang_sampson,helike_zhang_sampson_type68,22483,"
        f"bound_bound_gain_to_destination,collisional_excitation,34,39,1s1.2s1.3S_1,1s1.2p1.1P_1,{ne},{q},,{q},1.0,0.1,76655.2,76655.2,False,helike_calt68_zhang_sampson\n"
        f"34,34,{-rate},{rate},{rate},68,helike_calt68_zhang_sampson,helike_zhang_sampson_type68,22483,"
        f"bound_bound_loss_from_source,collisional_excitation,34,39,1s1.2s1.3S_1,1s1.2p1.1P_1,{ne},{q},,{q},1.0,0.1,76655.2,76655.2,False,helike_calt68_zhang_sampson\n",
        encoding="utf-8",
    )
    solve_csv.write_text(
        "row_kind,global_index,triplet_component,is_triplet_upper,level_label,population_fraction\n"
        "population,39,r,True,1s1.2p1.1P_1,0.1\n",
        encoding="utf-8",
    )
    result = audit_type68_collision_rates(matrix_terms_csv=matrix_csv, normalized_solve_csv=solve_csv, ion="O VII")
    assert result["overall"]["n_type68_matrix_terms"] == 2
    assert result["overall"]["n_type68_matrix_matches_q_ne_rate"] == 2
    assert result["overall"]["n_type68_gain_loss_record_pairs_matching"] == 1
    assert result["term_rows"][0]["rate_classification"] == "matrix_matches_q_ne_rate"
    assert result["term_rows"][0]["partner_status"] == "matrix_gain_loss_partner_matches"
    paths = write_type68_collision_rate_audit(result, tmp_path / "out")
    assert Path(paths["terms_csv"]).exists()
    assert Path(paths["markdown"]).read_text(encoding="utf-8").startswith("# XSTAR type-68")
