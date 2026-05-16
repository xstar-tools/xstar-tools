from pathlib import Path
import csv, json

from xstar_atomic.xstar_full_element_basis import (
    build_full_element_basis_scaffold,
    write_full_element_basis_scaffold,
)


def _write_csv(path: Path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader(); w.writerows(rows)


def test_full_element_basis_scaffold(tmp_path: Path):
    root = tmp_path / "remap"
    root.mkdir()
    _write_csv(root / "xstar_element_basis_remap_audit_xstar_basis_rows.csv",
               ["xstar_ipmat2_index","xstar_after_population","row_kinds","sharing_class","role_count","primary_nionp_current","primary_ml_ion","primary_klion","primary_jkk_ion","primary_local_level_index","population_role_nionp","population_role_local_level_index","parent_role_nionp","parent_role_local_level_index","final_slot"], [
        {"xstar_ipmat2_index":1,"xstar_after_population":0.7,"row_kinds":"ion_population_row","sharing_class":"single_role","role_count":1,"primary_nionp_current":8,"primary_ml_ion":80,"primary_klion":8,"primary_jkk_ion":8,"primary_local_level_index":1,"population_role_nionp":8,"population_role_local_level_index":1,"parent_role_nionp":"","parent_role_local_level_index":"","final_slot":False},
        {"xstar_ipmat2_index":2,"xstar_after_population":0.2,"row_kinds":"ion_population_row","sharing_class":"single_role","role_count":1,"primary_nionp_current":7,"primary_ml_ion":70,"primary_klion":7,"primary_jkk_ion":7,"primary_local_level_index":1,"population_role_nionp":7,"population_role_local_level_index":1,"parent_role_nionp":"","parent_role_local_level_index":"","final_slot":False},
        {"xstar_ipmat2_index":3,"xstar_after_population":0.1,"row_kinds":"ion_parent_continuum_link;final_parent_continuum_slot","sharing_class":"parent_continuum_shared_with_final_closure_slot","role_count":2,"primary_nionp_current":8,"primary_ml_ion":-1,"primary_klion":-1,"primary_jkk_ion":-1,"primary_local_level_index":-1,"population_role_nionp":"","population_role_local_level_index":"","parent_role_nionp":8,"parent_role_local_level_index":2,"final_slot":True},
    ])
    _write_csv(root / "xstar_element_basis_remap_audit_python_remap.csv",
               ["global_index","ion_stage","level_index","level_label","corrected_xstar_ipmat2_index"], [
        {"global_index":0,"ion_stage":8,"level_index":1,"level_label":"g","corrected_xstar_ipmat2_index":1},
    ])
    _write_csv(root / "xstar_element_basis_remap_audit_xstar_ion_blocks.csv",
               ["nionp_current","ml_ion","klion","jkk_ion","nlev","compact_first_population_row","parent_continuum_ipmat2_index"], [
        {"nionp_current":7,"ml_ion":70,"klion":7,"jkk_ion":7,"nlev":2,"compact_first_population_row":2,"parent_continuum_ipmat2_index":3},
        {"nionp_current":8,"ml_ion":80,"klion":8,"jkk_ion":8,"nlev":2,"compact_first_population_row":1,"parent_continuum_ipmat2_index":1},
    ])
    _write_csv(root / "xstar_element_basis_remap_audit_xstar_alias_roles.csv",
               ["xstar_ipmat2_index","sharing_class"], [
        {"xstar_ipmat2_index":3,"sharing_class":"parent_continuum_shared_with_final_closure_slot"},
        {"xstar_ipmat2_index":3,"sharing_class":"parent_continuum_shared_with_final_closure_slot"},
    ])
    (root / "xstar_element_basis_remap_audit.json").write_text(json.dumps({"summary":{"ion":"O VII","selected_basis_solve_call_id":5}}), encoding="utf-8")

    audit = build_full_element_basis_scaffold(element_basis_remap_audit=root)
    s = audit["summary"]
    assert s["n_full_xstar_basis_rows"] == 3
    assert s["n_missing_python_basis_rows"] == 2
    assert abs(s["current_population_coverage"] - 0.7) < 1e-12
    assert abs(s["missing_population_fraction"] - 0.3) < 1e-12
    assert s["full_element_basis_scaffold_ready"] is True
    assert audit["missing_priority_rows"][0]["xstar_ipmat2_index"] == 2
    assert len(audit["coverage_tier_rows"]) == 6
    paths = write_full_element_basis_scaffold(tmp_path / "out", audit)
    assert Path(paths["full_basis_scaffold_csv"]).exists()
    assert Path(paths["coverage_tiers_csv"]).exists()
