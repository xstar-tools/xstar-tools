from pathlib import Path

from xstar_atomic.xstar_population_basis_mapping import diagnose_population_basis_mapping, write_population_basis_mapping_diagnosis


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_population_basis_mapping_diagnosis(tmp_path: Path) -> None:
    audit_dir = tmp_path / "parity"
    _write(
        audit_dir / "xstar_population_closure_parity_audit_overlap_rows.csv",
        "xstar_ipmat2_index,xstar_after_population,xstar_before_population,xstar_nsup,xstar_nion,python_population_fraction,python_xstar_superlevel_population_p\n"
        "1,1e-10,1e-10,1,3,0.9,0.9\n",
    )
    _write(
        audit_dir / "xstar_population_closure_parity_audit_unmapped_xstar_rows.csv",
        "xstar_ipmat2_index,xstar_after_population,xstar_before_population,xstar_nsup,xstar_nion,reason\n"
        "10,0.5,0.5,5,8,no_python_row_with_this_xstar_ipmat2_index\n"
        "11,0.1,0.1,6,8,no_python_row_with_this_xstar_ipmat2_index\n",
    )
    _write(
        audit_dir / "xstar_population_closure_parity_audit_capture_scan.csv",
        "element_occurrence_rank,solve_call_id,ipmat2,nsp,nionp,after_n_nonzero_population_rows,xstar_after_population_sum_on_python_mapped_rows,xstar_after_population_sum_on_unmapped_rows,unmapped_population_fraction_of_total\n"
        "1,3,11,5,8,3,1e-10,0.6,0.9999999998\n",
    )
    _write(
        audit_dir / "xstar_population_closure_parity_audit.json",
        '{"summary":{"ion":"O VII","selected_solve_call_id":"3","occurrence_rank":1,"selected_xstar_ipmat2":11}}',
    )

    audit = diagnose_population_basis_mapping(population_closure_parity_audit=audit_dir)
    s = audit["summary"]
    assert s["status"] == "population_basis_mapping_diagnosis_completed"
    assert s["mapping_diagnosis"] == "python_ipmat2_mapping_is_not_source_equivalent_to_xstar_element_basis"
    assert s["max_unmapped_row_ipmat2"] == 10
    assert audit["xstar_basis_block_summary"][0]["basis_gap_priority"] == "high"

    paths = write_population_basis_mapping_diagnosis(audit, tmp_path / "out")
    assert Path(paths["basis_block_summary_csv"]).exists()
    assert Path(paths["implementation_plan_csv"]).exists()
