from pathlib import Path

from xstar_atomic.xstar_full_parity_closure import (
    audit_source_code_equivalent_local_closure,
    matrix_family_closure_summary,
    write_source_code_equivalent_local_closure_audit,
    ucalc_probe_schema_rows,
)


def test_matrix_family_closure_summary_flags_type99_proxy():
    rows = [
        {"data_type": "99", "type99_rate_source": "legacy_proxy", "record": "101", "feeds_any_triplet_component": "True"},
        {"source_method": "data_type_50_rate_type_4", "type50_bound_bound_treatment": "xstar-line-escape", "record": "102"},
        {"data_type": "53", "radiation_field_mode": "xstar-powerlaw", "phint53_status": "proxy", "record": "103"},
    ]
    out = matrix_family_closure_summary(rows)
    by_dt = {r["data_type"]: r for r in out}
    assert by_dt["99"]["closure_class"] == "parent_superlevel_closure_incomplete"
    assert by_dt["99"]["n_triplet_touching_terms"] == 1
    assert by_dt["53"]["closure_class"] == "mixed_proxy_and_source_code_branches"
    assert by_dt["50"]["n_matrix_terms"] == 1


def test_probe_schema_contains_ans_columns():
    cols = {r["column"] for r in ucalc_probe_schema_rows()}
    for name in ["ml_data", "ltyp", "lrtyp", "idest1", "idest2", "ans1", "ans6", "scale"]:
        assert name in cols


def test_write_closure_audit_outputs(tmp_path: Path):
    matrix_csv = tmp_path / "matrix.csv"
    matrix_csv.write_text(
        "data_type,record,type99_rate_source,feeds_any_triplet_component\n"
        "99,201,legacy_proxy,True\n"
        "74,202,xstar-ucalc,False\n",
        encoding="utf-8",
    )
    audit = audit_source_code_equivalent_local_closure(matrix_terms_csv=matrix_csv, ion="O VII")
    assert audit["summary"]["audit_version"] == "v0.3.175"
    assert audit["summary"]["n_matrix_terms"] == 2
    paths = write_source_code_equivalent_local_closure_audit(audit, tmp_path / "out")
    assert Path(paths["family_summary_csv"]).exists()
    assert Path(paths["ucalc_probe_schema_csv"]).exists()
    assert Path(paths["fortran_probe_template"]).read_text(encoding="utf-8").startswith("! xstar-atomic v0.3.175")
