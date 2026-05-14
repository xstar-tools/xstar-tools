from pathlib import Path

from xstar_atomic.xstar_record_level_parity import audit_record_level_matrix_parity


def test_v03181_record_level_parity_synthetic(tmp_path: Path):
    bench = tmp_path / "bench" / "solver_products" / "o_vii"
    bench.mkdir(parents=True)
    matrix_terms = bench / "xstar_like_element_solver_full_global_matrix_terms.csv"
    matrix_terms.write_text(
        "record,data_type,rate_type,full_global_signed_rate_s^-1,source_method,rate_source\n"
        "100,50,4,3.0,xstar-ucalc,source-code\n"
        "100,50,4,2.0,xstar-ucalc,source-code\n"
        "100,50,4,-3.0,xstar-ucalc,source-code\n"
        "100,50,4,-2.0,xstar-ucalc,source-code\n",
        encoding="utf-8",
    )
    u = tmp_path / "u.csv"
    u.write_text(
        "capture_index,ml_data,ltyp,lrtyp,jkk_ion,idest1,idest2,idest3,idest4,ans1,ans2,ans3,ans4,ans5,ans6\n"
        "1,100,50,4,7,1,2,0,0,1.0,1.0,0,0,0,0\n"
        "2,100,50,4,7,1,2,0,0,3.0,2.0,0,0,0,0\n",
        encoding="utf-8",
    )
    m = tmp_path / "m.csv"
    m.write_text(
        "capture_index,matrix_capture_index,ml_data,ltyp,lrtyp,insertion_index,insertion_kind,indbi_1,indbi_2,ajisi_1,ajisi_2\n"
        "2,1,100,50,4,1,forward_offdiag,2,1,3.0,2.0\n"
        "2,2,100,50,4,2,reverse_offdiag,1,2,2.0,3.0\n"
        "2,3,100,50,4,3,forward_diag_loss,1,1,-3.0,-3.0\n"
        "2,4,100,50,4,4,reverse_diag_loss,2,2,-2.0,-2.0\n",
        encoding="utf-8",
    )
    audit = audit_record_level_matrix_parity(
        benchmark_dir=tmp_path / "bench",
        ion="O VII",
        ucalc_probe_csv=u,
        matrix_probe_csv=m,
    )
    s = audit["summary"]
    assert s["audit_version"] == "v0.3.182"
    assert s["n_python_records"] == 1
    assert s["n_python_records_with_selected_four_fortran_rows"] == 1
    assert s["n_fortran_self_check_pass_records"] == 1
    assert s["record_level_source_equivalent_ready"] is True


def test_v03181_detects_proxy_mismatch(tmp_path: Path):
    bench = tmp_path / "bench" / "solver_products" / "o_vii"
    bench.mkdir(parents=True)
    (bench / "xstar_like_element_solver_full_global_matrix_terms.csv").write_text(
        "record,data_type,rate_type,full_global_signed_rate_s^-1,source_method,rate_source\n"
        "200,53,7,44.0,xstar-powerlaw,proxy\n"
        "200,53,7,44.0,xstar-powerlaw,proxy\n"
        "200,53,7,-44.0,xstar-powerlaw,proxy\n"
        "200,53,7,-44.0,xstar-powerlaw,proxy\n",
        encoding="utf-8",
    )
    u = tmp_path / "u.csv"
    u.write_text(
        "capture_index,ml_data,ltyp,lrtyp,jkk_ion,idest1,idest2,idest3,idest4,ans1,ans2,ans3,ans4,ans5,ans6\n"
        "9,200,53,7,7,1,2,0,0,1.0,1.0,0,0,0,0\n",
        encoding="utf-8",
    )
    m = tmp_path / "m.csv"
    m.write_text(
        "capture_index,matrix_capture_index,ml_data,ltyp,lrtyp,insertion_index,insertion_kind,indbi_1,indbi_2,ajisi_1,ajisi_2\n"
        "9,1,200,53,7,1,forward_offdiag,2,1,1.0,1.0\n"
        "9,2,200,53,7,2,reverse_offdiag,1,2,1.0,1.0\n"
        "9,3,200,53,7,3,forward_diag_loss,1,1,-1.0,-1.0\n"
        "9,4,200,53,7,4,reverse_diag_loss,2,2,-1.0,-1.0\n",
        encoding="utf-8",
    )
    audit = audit_record_level_matrix_parity(
        benchmark_dir=tmp_path / "bench",
        ion="O VII",
        ucalc_probe_csv=u,
        matrix_probe_csv=m,
    )
    row = audit["record_rows"][0]
    assert row["record_parity_status"] == "python_fortran_abs_sum_differs"
    assert row["python_proxy_or_scaffold"] is True
    assert audit["summary"]["record_level_source_equivalent_ready"] is False


def test_v03182_occurrence_rank_selection_and_scan(tmp_path: Path):
    bench = tmp_path / "bench" / "solver_products" / "o_vii"
    bench.mkdir(parents=True)
    (bench / "xstar_like_element_solver_full_global_matrix_terms.csv").write_text(
        "record,data_type,rate_type,full_global_signed_rate_s^-1,source_method,rate_source\n"
        "300,50,4,5.0,xstar-ucalc,source-code\n"
        "300,50,4,4.0,xstar-ucalc,source-code\n"
        "300,50,4,-5.0,xstar-ucalc,source-code\n"
        "300,50,4,-4.0,xstar-ucalc,source-code\n",
        encoding="utf-8",
    )
    u = tmp_path / "u.csv"
    u.write_text(
        "capture_index,ml_data,ltyp,lrtyp,jkk_ion,idest1,idest2,idest3,idest4,ans1,ans2,ans3,ans4,ans5,ans6\n"
        "10,300,50,4,7,1,2,0,0,1.0,1.0,0,0,0,0\n"
        "20,300,50,4,7,1,2,0,0,5.0,4.0,0,0,0,0\n",
        encoding="utf-8",
    )
    m = tmp_path / "m.csv"
    m.write_text(
        "capture_index,matrix_capture_index,ml_data,ltyp,lrtyp,insertion_index,insertion_kind,indbi_1,indbi_2,ajisi_1,ajisi_2\n"
        "10,1,300,50,4,1,forward_offdiag,2,1,1.0,1.0\n"
        "10,2,300,50,4,2,reverse_offdiag,1,2,1.0,1.0\n"
        "10,3,300,50,4,3,forward_diag_loss,1,1,-1.0,-1.0\n"
        "10,4,300,50,4,4,reverse_diag_loss,2,2,-1.0,-1.0\n"
        "20,5,300,50,4,1,forward_offdiag,2,1,5.0,4.0\n"
        "20,6,300,50,4,2,reverse_offdiag,1,2,4.0,5.0\n"
        "20,7,300,50,4,3,forward_diag_loss,1,1,-5.0,-5.0\n"
        "20,8,300,50,4,4,reverse_diag_loss,2,2,-4.0,-4.0\n",
        encoding="utf-8",
    )
    audit = audit_record_level_matrix_parity(
        benchmark_dir=tmp_path / "bench",
        ion="O VII",
        ucalc_probe_csv=u,
        matrix_probe_csv=m,
        selection="occurrence-rank",
        occurrence_rank=2,
        scan_occurrence_ranks=True,
    )
    assert audit["summary"]["occurrence_rank"] == 2
    assert audit["summary"]["best_occurrence_rank_by_scan"] == 2
    assert audit["summary"]["record_level_source_equivalent_ready"] is True
    scan = audit["occurrence_scan_rows"]
    assert len(scan) == 2
    assert min(scan, key=lambda r: r["scan_rank_by_median_abs_log10_ratio"])["occurrence_rank"] == 2
