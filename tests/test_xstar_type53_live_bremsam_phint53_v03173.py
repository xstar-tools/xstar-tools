from pathlib import Path

from xstar_atomic.xstar_matrix_parity import audit_type53_live_bremsam_phint53


def test_type53_live_bremsam_phint53_audit_synthetic(tmp_path: Path):
    matrix = tmp_path / "matrix.csv"
    adjacent = tmp_path / "adjacent.csv"
    global_index = tmp_path / "global.csv"
    probe = tmp_path / "probe.csv"

    matrix.write_text(
        "data_type,full_global_component,matrix_role,matrix_term_kind,record,bound_global_index,continuum_or_parent_global_index,full_global_rate_s^-1,triplet_component\n"
        "53,photoionization,photoionization,phint53,10,1,2,1.0,f\n",
        encoding="utf-8",
    )
    adjacent.write_text(
        "data_type,record,type53_raw_reals_full\n"
        "53,10,0 1 1 1\n",
        encoding="utf-8",
    )
    global_index.write_text(
        "global_index,level_label,binding_from_continuum_eV,triplet_component,is_triplet_upper\n"
        "1,1s.2s,10,f,true\n"
        "2,cont,0,,false\n",
        encoding="utf-8",
    )
    probe.write_text(
        "zone_index,pass_index,ldir,grid_index,ncn2m,epim_eV,bremsam,bremsint\n"
        "-1,1,0,1,3,10,1e20,0\n"
        "-1,1,0,2,3,20,1e20,0\n"
        "-1,1,0,3,3,30,1e20,0\n",
        encoding="utf-8",
    )

    audit = audit_type53_live_bremsam_phint53(
        matrix_terms_csv=matrix,
        adjacent_coupling_csv=adjacent,
        global_index_csv=global_index,
        probe_csv=probe,
        ion="O VII",
        triplet_only=True,
    )
    summary = audit["summary"]
    assert summary["audit_version"] == "v0.3.173"
    assert summary["probe_status"] == "probe_csv_loaded"
    assert summary["n_type53_photoionization_records"] == 1
    assert summary["n_live_phint53_evaluated"] == 1
    assert audit["rows"][0]["live_phint53_photo_ans1_s^-1"] is not None
