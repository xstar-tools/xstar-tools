from pathlib import Path

from xstar_atomic.xstar_full_parity_probes import (
    prepare_full_parity_probe_products,
    read_ucalc_record_probe_csv,
    read_calc_hmc_ion_matrix_probe_csv,
    summarize_full_parity_probe_csvs,
)


def test_prepare_full_parity_probe_products_without_csvs(tmp_path: Path):
    result = prepare_full_parity_probe_products(out_dir=tmp_path)
    s = result["summary"]
    assert s["audit_version"] == "v0.3.180"
    assert s["status"] == "probe_csvs_not_loaded"
    assert s["probe_ready_for_record_level_matrix_parity"] is False
    for key in ["helper_fortran", "after_ucalc_insertion", "matrix_insertion_notes", "ucalc_schema_csv", "matrix_schema_csv"]:
        assert Path(result["paths"][key]).exists()


def test_full_parity_probe_validation_ready(tmp_path: Path):
    u = tmp_path / "xstar_ucalc_record_probe.csv"
    m = tmp_path / "xstar_calc_hmc_ion_matrix_probe.csv"
    u.write_text(
        "capture_index,ml_data,ltyp,lrtyp,jkk_ion,idest1,idest2,idest3,idest4,ans1,ans2,ans3,ans4,ans5,ans6\n"
        "1,21635,53,7,7,1,10,0,0,1.0,2.0,0.0,0.0,0.0,0.0\n",
        encoding="utf-8",
    )
    rows = []
    kinds = ["forward_offdiag", "reverse_offdiag", "forward_diag_loss", "reverse_diag_loss"]
    for i, kind in enumerate(kinds, 1):
        rows.append(f"{1},{i},{21635},{53},{7},{i},{kind},{i},{i+1},{1.0},{2.0}\n")
    m.write_text(
        "capture_index,matrix_capture_index,ml_data,ltyp,lrtyp,insertion_index,insertion_kind,indbi_1,indbi_2,ajisi_1,ajisi_2\n" + "".join(rows),
        encoding="utf-8",
    )
    s = summarize_full_parity_probe_csvs(ucalc_probe_csv=u, matrix_probe_csv=m)
    assert s["status"] == "probe_csvs_loaded"
    assert s["n_ucalc_rows"] == 1
    assert s["n_matrix_rows"] == 4
    assert s["n_matrix_record_keys_with_four_rows"] == 1
    assert s["probe_ready_for_record_level_matrix_parity"] is True
    assert len(read_ucalc_record_probe_csv(u)) == 1
    assert len(read_calc_hmc_ion_matrix_probe_csv(m)) == 4


def test_full_parity_probe_validation_detects_bad_matrix_count(tmp_path: Path):
    u = tmp_path / "u.csv"
    m = tmp_path / "m.csv"
    u.write_text(
        "capture_index,ml_data,ltyp,lrtyp,jkk_ion,idest1,idest2,idest3,idest4,ans1,ans2,ans3,ans4,ans5,ans6\n"
        "1,1,50,4,7,1,2,0,0,1,2,3,4,5,6\n",
        encoding="utf-8",
    )
    m.write_text(
        "capture_index,matrix_capture_index,ml_data,ltyp,lrtyp,insertion_index,insertion_kind,indbi_1,indbi_2,ajisi_1,ajisi_2\n"
        "1,1,1,50,4,1,forward_offdiag,2,1,1,2\n",
        encoding="utf-8",
    )
    s = summarize_full_parity_probe_csvs(ucalc_probe_csv=u, matrix_probe_csv=m)
    assert s["probe_ready_for_record_level_matrix_parity"] is False
    assert s["n_matrix_record_keys_not_four_rows"] == 1
