from pathlib import Path

from xstar_atomic.xstar_matrix_parity import (
    audit_type71_cascade_rates,
    write_type71_cascade_rate_audit,
)


def test_type71_cascade_rate_audit_matches_calt71_and_partner(tmp_path):
    matrix_csv = tmp_path / "matrix.csv"
    solve_csv = tmp_path / "solve.csv"
    matrix_csv.write_text(
        "matrix_row_global_index,matrix_col_global_index,full_global_signed_rate_s^-1,full_global_rate_s^-1,"
        "rate_s^-1,data_type,rate_source,type71_rate_source,type71_calt71_status,type71_calt71_log10_aij,"
        "type71_calt71_wavelength_A,record,matrix_role,spectroscopic_global_index,superlevel_global_index,"
        "spectroscopic_level_label,superlevel_level_label,destination_triplet_component\n"
        "35,76,1000.0,1000.0,1000.0,71,calt71.f90,calt71.f90,evaluated_grid_calt71_logne_logT_interpolation,3.0,25.2,22260,"
        "type71_superlevel_cascade_gain_to_spectroscopic_destination,35,76,1s1.2p1.3P_0,sprlevlt,i\n"
        "76,76,-1000.0,1000.0,1000.0,71,calt71.f90,calt71.f90,evaluated_grid_calt71_logne_logT_interpolation,3.0,25.2,22260,"
        "type71_superlevel_cascade_loss_from_superlevel_source,35,76,1s1.2p1.3P_0,sprlevlt,i\n",
        encoding="utf-8",
    )
    solve_csv.write_text(
        "row_kind,global_index,triplet_component,is_triplet_upper,level_label,population_fraction\n"
        "population,35,i,True,1s1.2p1.3P_0,0.1\n",
        encoding="utf-8",
    )
    result = audit_type71_cascade_rates(matrix_terms_csv=matrix_csv, normalized_solve_csv=solve_csv, ion="O VII")
    assert result["overall"]["n_type71_matrix_terms"] == 2
    assert result["overall"]["n_type71_matrix_matches_calt71_aij"] == 2
    assert result["overall"]["n_type71_gain_loss_record_pairs_matching"] == 1
    assert result["term_rows"][0]["rate_classification"] == "matrix_matches_calt71_aij"
    assert result["term_rows"][0]["partner_status"] == "matrix_gain_loss_partner_matches"
    paths = write_type71_cascade_rate_audit(result, tmp_path / "out")
    assert Path(paths["terms_csv"]).exists()
    assert Path(paths["markdown"]).read_text(encoding="utf-8").startswith("# XSTAR type-71")
