from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pytest

from xstar_atomic.source_port import (
    ElementBasisRow,
    ElementCompactBasis,
    ElementEquilibriumContext,
    ElementMatrixAssembly,
    MatrixTerm,
    compare_element_population_parity,
    load_xstar_population_reference,
    msolvelucy,
    write_element_population_parity_products,
)


def _two_level_assembly(initial=(0.5, 0.5)) -> ElementMatrixAssembly:
    basis = ElementCompactBasis(
        element_z=8,
        min_ion_stage=7,
        max_ion_stage=7,
        blocks=[],
        rows=[
            ElementBasisRow(1, superlevel=1, ion_counter=1),
            ElementBasisRow(2, superlevel=2, ion_counter=1),
        ],
        n_rows=2,
        n_superlevels=2,
        n_ions=1,
        normalization_row=2,
    )
    up, down = 2.0, 8.0
    terms = [
        MatrixTerm(1, 10, 50, 4, 1, 7, "forward_offdiag", 2, 1, up, down, 0, 0, 1, 2, 1, 2, "evaluated"),
        MatrixTerm(2, 10, 50, 4, 1, 7, "reverse_offdiag", 1, 2, down, up, 0, 0, 1, 2, 1, 2, "evaluated"),
        MatrixTerm(3, 10, 50, 4, 1, 7, "forward_diag_loss", 1, 1, -up, -up, 0, 0, 1, 2, 1, 2, "evaluated"),
        MatrixTerm(4, 10, 50, 4, 1, 7, "reverse_diag_loss", 2, 2, -down, -down, 0, 0, 1, 2, 1, 2, "evaluated"),
    ]
    matrix = np.asarray([[-up, down], [up, -down]], dtype=float)
    return ElementMatrixAssembly(
        basis=basis,
        initial_populations=np.asarray([0.0, *initial], dtype=float),
        terms=terms,
        dense_matrix=matrix,
        normalized_matrix=np.asarray([[-up, down], [1.0, 1.0]], dtype=float),
        rhs=np.asarray([0.0, 1.0]),
        heating_matrix=np.zeros((2, 2)),
        heating_matrix2=np.zeros((2, 2)),
        ion_summaries=[],
        blocked_records=[],
        record_results=[],
        n_records_seen=1,
        n_records_evaluated=1,
        n_records_source_noop=0,
        n_records_skipped=0,
        n_records_blocked=0,
        n_unmapped_endpoints=0,
        strict_assembly_ready=True,
    )


def _write_probe(path: Path, before=(0.5, 0.5), after=(0.8, 0.2), solve_call_id=219):
    fields = [
        "capture_index", "solve_call_id", "stage_capture_index", "stage",
        "ml_element", "element_z", "ipmat2", "nsp", "nionp", "nindbe",
        "nit", "nit2", "nit3", "level_index", "x_population", "nsup", "nion",
        "t_xstar_1e4K", "xee", "xpx", "cfrac",
    ]
    rows = []
    for capture, stage, values in [(1, "before_msolvelucy", before), (2, "after_msolvelucy", after)]:
        for index, value in enumerate(values, start=1):
            rows.append({
                "capture_index": capture, "solve_call_id": solve_call_id,
                "stage_capture_index": capture, "stage": stage, "ml_element": 8,
                "element_z": 8, "ipmat2": 2, "nsp": 2, "nionp": 1, "nindbe": 4,
                "nit": 0 if stage.startswith("before") else 2, "nit2": 0, "nit3": 0,
                "level_index": index, "x_population": value, "nsup": index, "nion": 7,
                "t_xstar_1e4K": 100.0, "xee": 1.0, "xpx": 1.0e8, "cfrac": 1.0,
            })
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)


def test_population_reference_loader_and_native_seed_parity(tmp_path: Path):
    probe = tmp_path / "probe.csv"
    _write_probe(probe)
    ref = load_xstar_population_reference(probe, element_z=8, n_rows=2, solve_call_id="219")
    assembly = _two_level_assembly()
    context = ElementEquilibriumContext(
        temperature_k=1e6, hydrogen_density_cm3=1e8, electron_fraction_xee=1.0,
        min_ion_stage=7, max_ion_stage=7, capture_lucy_trace=True,
    )
    native = msolvelucy(assembly, context)
    result = compare_element_population_parity(assembly, native, context, ref)
    assert result.xstar_population_parity_ready is True
    assert result.diagnosis == "population_parity_reproduced_from_python_native_seed"
    assert result.native_final_metrics.l1_difference < 1e-12
    assert result.seeded_final_metrics is not None
    assert native.trace is not None
    assert native.trace.outer_level_rows
    assert native.trace.fixed_point_rows
    outputs = write_element_population_parity_products(result, tmp_path / "out")
    assert outputs["population_parity_json"].is_file()
    assert outputs["seeded_lucy_outer_trace_csv"].is_file()


def test_population_parity_classifies_operator_or_context_mismatch(tmp_path: Path):
    probe = tmp_path / "probe.csv"
    _write_probe(probe, after=(0.2, 0.8))
    ref = load_xstar_population_reference(probe, element_z=8, n_rows=2)
    assembly = _two_level_assembly()
    context = ElementEquilibriumContext(
        temperature_k=1e6, hydrogen_density_cm3=1e8, electron_fraction_xee=1.0,
        min_ion_stage=7, max_ion_stage=7,
    )
    native = msolvelucy(assembly, context)
    result = compare_element_population_parity(assembly, native, context, ref)
    assert result.xstar_population_parity_ready is False
    assert result.diagnosis == "assembled_operator_or_runtime_context_mismatch"
    assert result.native_final_metrics.l1_difference == pytest.approx(1.2)


def test_population_probe_rejects_wrong_dimension(tmp_path: Path):
    probe = tmp_path / "probe.csv"
    _write_probe(probe)
    with pytest.raises(Exception):
        load_xstar_population_reference(probe, element_z=8, n_rows=607)


def test_iteration_state_probe_comparator_round_trip(tmp_path: Path):
    from xstar_atomic.source_port import (
        compare_msolvelucy_state_probe,
        write_msolvelucy_state_parity_products,
    )

    assembly = _two_level_assembly(initial=(0.8, 0.2))
    context = ElementEquilibriumContext(
        temperature_k=1e6, hydrogen_density_cm3=1e8, electron_fraction_xee=1.0,
        min_ion_stage=7, max_ion_stage=7, capture_lucy_trace=True,
    )
    solved = msolvelucy(assembly, context)
    trace = solved.trace
    assert trace is not None
    root = tmp_path / "probe"
    root.mkdir()

    def write(name, fields, rows):
        with (root / name).open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader(); writer.writerows(rows)

    level_rows = []
    for row in trace.outer_level_rows:
        base = {
            "solve_call_id": 219,
            "outer_iteration": row["outer_iteration"],
            "fixed_iteration": 0,
            "global_fixed_iteration": 0,
            "compact_index": row["compact_index"],
            "superlevel": row["superlevel"],
            "ion_counter": row["ion_counter"],
            "diff": 0.0,
            "diff2": row["fixed_difference"],
        }
        for phase, field in [
            ("outer_start", "population_outer_start"),
            ("after_condensed_solve", "population_after_condensed"),
            ("outer_end", "population_after_fixed_point"),
        ]:
            level_rows.append({**base, "phase": phase, "population": row[field]})
    write(
        "xstar_msolvelucy_levels_probe.csv",
        list(level_rows[0]),
        level_rows,
    )

    rr_rows = [
        {
            "solve_call_id": 219,
            "outer_iteration": row["outer_iteration"],
            "compact_index": row["compact_index"],
            "population": row["population_outer_start"],
            "rr": row["rr"],
            "superlevel": row["superlevel"],
            "ion_counter": row["ion_counter"],
        }
        for row in trace.outer_level_rows
    ]
    write("xstar_msolvelucy_rr_probe.csv", list(rr_rows[0]), rr_rows)

    super_rows = []
    for row in trace.superlevel_rows:
        for phase, field in [
            ("before_condensed_solve", "population_before_condensed_solve"),
            ("after_condensed_solve", "population_after_condensed_solve"),
        ]:
            super_rows.append({
                "solve_call_id": 219,
                "phase": phase,
                "outer_iteration": row["outer_iteration"],
                "superlevel": row["superlevel"],
                "population": row[field],
            })
    write("xstar_msolvelucy_superlevels_probe.csv", list(super_rows[0]), super_rows)

    matrix_rows = [
        {
            "solve_call_id": 219,
            "outer_iteration": row["outer_iteration"],
            "row_superlevel": row["row_superlevel"],
            "column_superlevel": row["column_superlevel"],
            "matrix_value": row["raw_matrix_value"],
        }
        for row in trace.condensed_matrix_rows
    ]
    write("xstar_msolvelucy_condensed_matrix_probe.csv", list(matrix_rows[0]), matrix_rows)

    fixed_rows = [
        {
            "solve_call_id": 219,
            "outer_iteration": row["outer_iteration"],
            "fixed_iteration": row["fixed_iteration"],
            "global_fixed_iteration": row["global_fixed_iteration"],
            "compact_index": row["compact_index"],
            "population_before": row["population_before"],
            "riu": row["riu"],
            "rui": row["rui"],
            "ril": row["ril"],
            "rli": row["rli"],
            "population_after": row["population_after"],
            "superlevel": row["superlevel"],
            "ion_counter": row["ion_counter"],
            "diff2": row["fixed_difference"],
        }
        for row in trace.fixed_point_rows
    ]
    write("xstar_msolvelucy_fixed_probe.csv", list(fixed_rows[0]), fixed_rows)

    parity = compare_msolvelucy_state_probe(
        trace,
        root,
        solve_call_id="219",
        comparison_trace_source="unit_test",
    )
    assert parity.msolvelucy_state_parity_ready is True
    assert parity.first_failing_component == ""
    outputs = write_msolvelucy_state_parity_products(parity, tmp_path / "out_state")
    assert outputs["msolvelucy_state_parity_json"].is_file()


def test_msolvelucy_probe_generator_writes_free_form_helper(tmp_path: Path):
    from xstar_atomic.xstar_msolvelucy_state_probe import write_msolvelucy_state_probe_products

    outputs = write_msolvelucy_state_probe_products(tmp_path)
    helper = outputs["helper_fortran"].read_text()
    assert "subroutine xap_msl_fixed" in helper
    assert "xstar_msolvelucy_fixed_probe.csv" in outputs["patch_notes"].read_text()
