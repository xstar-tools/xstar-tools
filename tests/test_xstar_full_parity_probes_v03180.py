from pathlib import Path

from xstar_atomic.xstar_full_parity_probes import summarize_full_parity_probe_csvs


def test_v03180_detects_legacy_independent_matrix_counter(tmp_path: Path):
    u = tmp_path / "u.csv"
    m = tmp_path / "m.csv"
    u.write_text(
        "capture_index,ml_data,ltyp,lrtyp,jkk_ion,idest1,idest2,idest3,idest4,ans1,ans2,ans3,ans4,ans5,ans6\n"
        "1,21635,53,7,7,1,10,0,0,1,2,0,0,0,0\n",
        encoding="utf-8",
    )
    # Legacy v0.3.179 matrix probe: capture_index is an independent matrix-row counter,
    # and no matrix_capture_index column exists.
    m.write_text(
        "capture_index,ml_data,ltyp,lrtyp,insertion_index,insertion_kind,indbi_1,indbi_2,ajisi_1,ajisi_2\n"
        "1,21635,53,7,1,forward_offdiag,2,1,1,2\n"
        "2,21635,53,7,2,reverse_offdiag,1,2,2,1\n",
        encoding="utf-8",
    )
    s = summarize_full_parity_probe_csvs(ucalc_probe_csv=u, matrix_probe_csv=m)
    assert s["status"] == "probe_csvs_loaded_with_independent_matrix_capture_index"
    assert s["matrix_capture_index_status"] == "independent_matrix_capture_index_needs_v03180_rerun"
    assert s["probe_ready_for_record_level_matrix_parity"] is False


def test_v03180_shared_ucalc_capture_index_ready(tmp_path: Path):
    u = tmp_path / "u.csv"
    m = tmp_path / "m.csv"
    u.write_text(
        "capture_index,ml_data,ltyp,lrtyp,jkk_ion,idest1,idest2,idest3,idest4,ans1,ans2,ans3,ans4,ans5,ans6\n"
        "1,21635,53,7,7,1,10,0,0,1,2,0,0,0,0\n",
        encoding="utf-8",
    )
    rows = []
    for i, kind in enumerate(["forward_offdiag", "reverse_offdiag", "forward_diag_loss", "reverse_diag_loss"], 1):
        rows.append(f"1,{i},21635,53,7,{i},{kind},{i},{i+1},1.0,2.0\n")
    m.write_text(
        "capture_index,matrix_capture_index,ml_data,ltyp,lrtyp,insertion_index,insertion_kind,indbi_1,indbi_2,ajisi_1,ajisi_2\n" + "".join(rows),
        encoding="utf-8",
    )
    s = summarize_full_parity_probe_csvs(ucalc_probe_csv=u, matrix_probe_csv=m)
    assert s["status"] == "probe_csvs_loaded"
    assert s["matrix_capture_index_status"] == "shared_ucalc_capture_index_v03180"
    assert s["n_matrix_record_keys_with_four_rows"] == 1
    assert s["probe_ready_for_record_level_matrix_parity"] is True
