from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pytest

from xstar_atomic.source_port import (
    ElementBasisRow,
    ElementCompactBasis,
    ElementEquilibriumContext,
    ElementIonBlock,
    ElementMatrixAssembly,
    LucyIterationTrace,
    MatrixTerm,
    SourceFaithfulUCalc,
    UCalcContext,
    UCalcLevel,
    UCalcLevelTable,
    UCalcRecord,
    UCalcStatus,
    compare_full_element_matrix_probe,
    compare_msolvelucy_state_probe,
)


def test_type76_is_unescaped_two_photon_decay_after_source_swap():
    levels = UCalcLevelTable(
        levels={
            1: UCalcLevel(index=1, energy_ev=10.0, statistical_weight=1.0),
            2: UCalcLevel(index=2, energy_ev=0.0, statistical_weight=1.0),
        },
        nlev=2,
    )
    record = UCalcRecord(
        record=100,
        data_type=76,
        rate_type=9,
        continuation=0,
        reals=(25.0,),
        integers=(1, 2),
    )
    result = SourceFaithfulUCalc().evaluate(
        record,
        UCalcContext(
            temperature_k=1.0e6,
            levels=levels,
            ptmp1=0.01,
            ptmp2=0.02,
        ),
    )
    assert result.status is UCalcStatus.EVALUATED
    assert result.ans1 == 0.0
    assert result.ans2 == pytest.approx(25.0)
    assert result.ans3 < 0.0
    assert result.ans4 == 0.0


def _write(path: Path, rows):
    fields = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_state_parity_reports_first_failure_in_execution_order(tmp_path: Path):
    trace = LucyIterationTrace(
        outer_level_rows=[
            {
                "outer_iteration": outer,
                "compact_index": 1,
                "superlevel": 1,
                "ion_counter": 1,
                "population_outer_start": 1.0 if outer == 1 else 0.5,
                "rr": 1.0,
                "population_after_condensed": 1.0,
                "population_after_fixed_point": 0.5,
                "fixed_iterations_this_outer": 1,
                "fixed_difference": 0.0,
            }
            for outer in (1, 2)
        ],
        superlevel_rows=[
            {
                "outer_iteration": outer,
                "superlevel": 1,
                "population_before_condensed_solve": 1.0 if outer == 1 else 0.5,
                "population_after_condensed_solve": 1.0,
            }
            for outer in (1, 2)
        ],
        condensed_matrix_rows=[
            {
                "outer_iteration": outer,
                "row_superlevel": 1,
                "column_superlevel": 1,
                "raw_matrix_value": 2.0 if outer == 1 else 3.0,
                "normalized_matrix_value": 1.0,
            }
            for outer in (1, 2)
        ],
        fixed_point_rows=[
            {
                "outer_iteration": outer,
                "fixed_iteration": 1,
                "global_fixed_iteration": outer,
                "compact_index": 1,
                "superlevel": 1,
                "ion_counter": 1,
                "population_before": 1.0,
                "riu": 0.0,
                "rui": 0.0,
                "ril": 0.0,
                "rli": 0.0,
                "population_after": 0.5,
                "fixed_difference": 0.0,
            }
            for outer in (1, 2)
        ],
    )
    root = tmp_path / "probe"
    root.mkdir()
    levels = []
    rr = []
    supers = []
    matrices = []
    fixed = []
    for outer in (1, 2):
        # Outer 2 deliberately disagrees, but it is downstream of the outer-1
        # condensed matrix mismatch and must not become the reported first failure.
        start = 1.0 if outer == 1 else 0.8
        levels.extend(
            [
                {"solve_call_id": 219, "outer_iteration": outer, "compact_index": 1, "phase": "outer_start", "population": start},
                {"solve_call_id": 219, "outer_iteration": outer, "compact_index": 1, "phase": "after_condensed_solve", "population": 1.0},
                {"solve_call_id": 219, "outer_iteration": outer, "compact_index": 1, "phase": "outer_end", "population": 0.5},
            ]
        )
        rr.append({"solve_call_id": 219, "outer_iteration": outer, "compact_index": 1, "population": start, "rr": 1.0})
        supers.extend(
            [
                {"solve_call_id": 219, "outer_iteration": outer, "superlevel": 1, "phase": "before_condensed_solve", "population": start},
                {"solve_call_id": 219, "outer_iteration": outer, "superlevel": 1, "phase": "after_condensed_solve", "population": 1.0},
            ]
        )
        matrices.append(
            {
                "solve_call_id": 219,
                "outer_iteration": outer,
                "row_superlevel": 1,
                "column_superlevel": 1,
                "matrix_value": 2.5 if outer == 1 else 3.0,
            }
        )
        fixed.append(
            {
                "solve_call_id": 219,
                "outer_iteration": outer,
                "fixed_iteration": 1,
                "compact_index": 1,
                "population_before": 1.0,
                "riu": 0.0,
                "rui": 0.0,
                "ril": 0.0,
                "rli": 0.0,
                "population_after": 0.5,
            }
        )
    _write(root / "xstar_msolvelucy_levels_probe.csv", levels)
    _write(root / "xstar_msolvelucy_rr_probe.csv", rr)
    _write(root / "xstar_msolvelucy_superlevels_probe.csv", supers)
    _write(root / "xstar_msolvelucy_condensed_matrix_probe.csv", matrices)
    _write(root / "xstar_msolvelucy_fixed_probe.csv", fixed)

    result = compare_msolvelucy_state_probe(
        trace,
        root,
        solve_call_id="219",
        comparison_trace_source="unit_test",
    )
    assert result.first_failing_component == "condensed_matrix_raw"
    assert result.first_failing_outer_iteration == 1
    assert result.first_failing_comparison_key == "outer=1,row=1,column=1"
    assert result.diagnosis == "condensed_matrix_or_rate_assembly_mismatch"


def _assembly() -> ElementMatrixAssembly:
    block = ElementIonBlock(
        ion_index=31,
        ion_record=1000,
        element_z=8,
        ion_stage=3,
        nlev=2,
        compact_start=1,
        compact_stop=2,
        first_level_record=1001,
    )
    basis = ElementCompactBasis(
        element_z=8,
        min_ion_stage=3,
        max_ion_stage=3,
        blocks=[block],
        rows=[
            ElementBasisRow(1, superlevel=1, ion_counter=1),
            ElementBasisRow(2, superlevel=2, ion_counter=1),
        ],
        n_rows=2,
        n_superlevels=2,
        n_ions=1,
        normalization_row=2,
    )
    terms = [
        MatrixTerm(1, 10, 50, 4, 31, 3, "forward_offdiag", 2, 1, 2.0, 8.0, 0, 0, 1, 2, 1, 2, "evaluated", 2, 1, False),
        MatrixTerm(2, 10, 50, 4, 31, 3, "reverse_offdiag", 1, 2, 8.0, 2.0, 0, 0, 1, 2, 1, 2, "evaluated", 1, 2, False),
        MatrixTerm(3, 10, 50, 4, 31, 3, "forward_diag_loss", 1, 1, -2.0, -2.0, 0, 0, 1, 2, 1, 2, "evaluated", 1, 1, False),
        MatrixTerm(4, 10, 50, 4, 31, 3, "reverse_diag_loss", 2, 2, -8.0, -8.0, 0, 0, 1, 2, 1, 2, "evaluated", 2, 2, False),
    ]
    matrix = np.asarray([[-2.0, 8.0], [2.0, -8.0]])
    return ElementMatrixAssembly(
        basis=basis,
        initial_populations=np.asarray([0.0, 0.5, 0.5]),
        terms=terms,
        dense_matrix=matrix,
        normalized_matrix=matrix.copy(),
        rhs=np.zeros(2),
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


def test_full_element_matrix_probe_comparator(tmp_path: Path):
    ucalc = tmp_path / "ucalc.csv"
    matrix = tmp_path / "matrix.csv"
    _write(
        ucalc,
        [
            {
                "capture_index": 7,
                "ml_data": 10,
                "ltyp": 50,
                "lrtyp": 4,
                "jkk_ion": 31,
                "idest1": 1,
                "idest2": 2,
            }
        ],
    )
    rows = [
        ("forward_offdiag", 2, 1, 2.0, 8.0),
        ("reverse_offdiag", 1, 2, 8.0, 2.0),
        ("forward_diag_loss", 1, 1, -2.0, -2.0),
        ("reverse_diag_loss", 2, 2, -8.0, -8.0),
    ]
    _write(
        matrix,
        [
            {
                "capture_index": 7,
                "ml_data": 10,
                "ltyp": 50,
                "lrtyp": 4,
                "insertion_kind": role,
                "indbi_1": row,
                "indbi_2": col,
                "ajisi_1": aj1,
                "ajisi_2": aj2,
                "idest1": 1,
                "idest2": 2,
            }
            for role, row, col, aj1, aj2 in rows
        ],
    )
    exact = compare_full_element_matrix_probe(_assembly(), ucalc, matrix)
    assert exact.full_element_matrix_parity_ready is True
    assert exact.n_matched_terms == 4

    bad_rows = list(csv.DictReader(matrix.open()))
    bad_rows[0]["ajisi_1"] = "3.0"
    _write(matrix, bad_rows)
    bad = compare_full_element_matrix_probe(_assembly(), ucalc, matrix)
    assert bad.full_element_matrix_parity_ready is False
    assert bad.first_failing_data_type == 50
    assert bad.first_failing_rate_type == 4
    assert bad.diagnosis == "resolve_native_type50_rate4_matrix_parity"
