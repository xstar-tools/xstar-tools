from pathlib import Path

from xstar_atomic.xstar_matrix_parity import (
    audit_triplet_rate_terms,
    write_triplet_rate_term_audit,
)


def test_triplet_rate_term_audit_ranks_terms_and_partner_checks(tmp_path):
    matrix_csv = tmp_path / "matrix.csv"
    solve_csv = tmp_path / "solve.csv"
    matrix_csv.write_text(
        "global_term_id,matrix_term_kind,matrix_role,matrix_row_global_index,matrix_col_global_index,"
        "signed_rate_s^-1,full_global_signed_rate_s^-1,rate_s^-1,full_global_rate_s^-1,data_type,"
        "source_method,record,from_global_index,to_global_index,from_level_label,to_level_label,row_kind\n"
        "1,offdiag_gain,bound_bound_gain_to_destination,34,39,5.0,5.0,5.0,5.0,50,data_type_50_rate_type_4,100,39,34,r_upper,f_upper,full_global_matrix_term\n"
        "2,diagonal_loss,bound_bound_loss_from_source,39,39,-5.0,-5.0,5.0,5.0,50,data_type_50_rate_type_4,100,39,34,r_upper,f_upper,full_global_matrix_term\n"
        "3,diagonal_loss,collisional_loss,34,34,-0.2,-0.2,0.2,0.2,63,bautista_nl_algorithm_type63,200,34,1,f_upper,ground,full_global_matrix_term\n",
        encoding="utf-8",
    )
    solve_csv.write_text(
        "row_kind,global_index,triplet_component,is_triplet_upper,level_label,population_fraction\n"
        "population,34,f,True,1s1.2s1.3S_1,0.1\n"
        "population,39,r,True,1s1.2p1.1P_1,0.2\n",
        encoding="utf-8",
    )
    result = audit_triplet_rate_terms(matrix_terms_csv=matrix_csv, normalized_solve_csv=solve_csv, ion="O VII")
    assert result["overall"]["n_triplet_upper_levels"] == 2
    assert result["overall"]["n_triplet_row_terms_total"] == 3
    assert result["term_rows"][0]["partner_status"] == "matrix_gain_loss_partner_matches"
    assert any(row["data_type"] == "63" for row in result["family_rows"])
    paths = write_triplet_rate_term_audit(result, tmp_path / "out")
    assert Path(paths["ranked_terms_csv"]).exists()
    assert Path(paths["markdown"]).read_text(encoding="utf-8").startswith("# XSTAR triplet row rate-term audit")
