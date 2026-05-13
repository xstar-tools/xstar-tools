
from pathlib import Path

from xstar_atomic.xstar_matrix_parity import (
    audit_type53_source_sink_rates,
    write_type53_source_sink_rate_audit,
)


def test_type53_source_sink_audit_closes_photo_and_milne_pairs(tmp_path):
    matrix_csv = tmp_path / "matrix.csv"
    solve_csv = tmp_path / "solve.csv"
    photo = 1.2e-3
    milne = 4.5e-9
    alpha_ne = 3.0e-9
    matrix_csv.write_text(
        "matrix_row_global_index,matrix_col_global_index,full_global_signed_rate_s^-1,full_global_rate_s^-1,rate_s^-1,"
        "data_type,record,matrix_term_kind,matrix_role,bound_global_index,continuum_or_parent_global_index,"
        "radiation_field_mode,phint53_status,inverse_recombination_mode,phint53_milne_ans2_status,"
        "source_code_phint53_milne_ans2_rrrt_s^-1,source_code_milne_f90_rate_alpha_ne_s^-1,bound_level,target_ion_stage,parent_ion_stage,triplet_component\n"
        f"113,39,{photo},{photo},{photo},53,21536,offdiag_bound_to_continuum_phint53_gain,photo_gain,39,113,"
        "xstar-powerlaw,evaluated_phint53_photoionization_kernel_with_placeholder_radiation,,,,,6,7,8,r\n"
        f"39,39,{-photo},{photo},{photo},53,21536,diagonal_bound_phint53_photoionization_loss,photo_loss,39,113,"
        "xstar-powerlaw,evaluated_phint53_photoionization_kernel_with_placeholder_radiation,,,,,6,7,8,r\n"
        f"39,113,{milne},{milne},{milne},53,21536,offdiag_parent_continuum_to_bound_xstar_ucalc_phint53_milne_gain,milne_gain,39,113,"
        f",,xstar-ucalc,evaluated_source_code_phint53_rrrt_integral_with_reconstructed_rnist,{milne},{alpha_ne},6,7,8,r\n"
        f"113,113,{-milne},{milne},{milne},53,21536,diagonal_parent_continuum_xstar_ucalc_phint53_milne_loss,milne_loss,39,113,"
        f",,xstar-ucalc,evaluated_source_code_phint53_rrrt_integral_with_reconstructed_rnist,{milne},{alpha_ne},6,7,8,r\n",
        encoding="utf-8",
    )
    solve_csv.write_text(
        "row_kind,global_index,triplet_component,is_triplet_upper,level_label,population_fraction\n"
        "population,39,r,True,1s1.2p1.1P_1,0.1\n",
        encoding="utf-8",
    )
    result = audit_type53_source_sink_rates(matrix_terms_csv=matrix_csv, normalized_solve_csv=solve_csv, ion="O VII")
    assert result["overall"]["n_type53_matrix_terms"] == 4
    assert result["overall"]["n_type53_photoionization_terms"] == 2
    assert result["overall"]["n_type53_milne_terms"] == 2
    assert result["overall"]["n_type53_partner_matches"] == 4
    assert result["overall"]["n_type53_gain_loss_record_pairs_matching"] == 2
    assert result["overall"]["n_type53_milne_matrix_matches_phint53_ans2"] == 2
    assert any(r["rate_classification"] == "matrix_matches_phint53_milne_ans2" for r in result["term_rows"])
    paths = write_type53_source_sink_rate_audit(result, tmp_path / "out")
    assert Path(paths["terms_csv"]).exists()
    assert Path(paths["markdown"]).read_text(encoding="utf-8").startswith("# XSTAR type-53")
