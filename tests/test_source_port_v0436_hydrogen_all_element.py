from __future__ import annotations

import csv
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from xstar_atomic.source_port import (
    ElementBasisRow,
    ElementCompactBasis,
    ElementIonBlock,
    ElementMatrixAssembly,
    MatrixTerm,
    MSolveLucyFinalSnapshotParityResult,
    MSolveLucyInitialPopulationParityResult,
    SameCallMatrixParityResult,
    SourceFaithfulUCalc,
    ThermalFamilyParityResult,
    UCalcContext,
    UCalcLevel,
    UCalcLevelTable,
    UCalcRecord,
    compare_msolvelucy_initial_populations,
    compare_same_call_matrix_terms,
)
from xstar_atomic.source_port.calc_hmc_all_parity import (
    _all_element_acceptance_summary,
)
from xstar_atomic.source_port.element_equilibrium import _matrix_terms_for_result


def _levels() -> UCalcLevelTable:
    return UCalcLevelTable(
        levels={
            1: UCalcLevel(
                1, energy_ev=0.0, statistical_weight=2.0,
                principal_n=1, orbital_l=0, label="1s 2S",
            ),
            4: UCalcLevel(
                4, energy_ev=10.2, statistical_weight=6.0,
                principal_n=2, orbital_l=1, label="2p 2P",
            ),
            7: UCalcLevel(
                7, energy_ev=12.09, statistical_weight=6.0,
                principal_n=3, orbital_l=1, label="3p 2P",
            ),
            8: UCalcLevel(
                8, energy_ev=12.75, statistical_weight=10.0,
                principal_n=3, orbital_l=2, label="3d 2D",
            ),
            9: UCalcLevel(
                9, energy_ev=12.75, statistical_weight=2.0,
                principal_n=3, orbital_l=0, label="3s 2S",
            ),
        },
        nlev=9,
    )


def _type62(record: int, upper: int) -> UCalcRecord:
    # nrdt=8: two unused real slots, three polynomial coefficients, and the
    # Callaway log/exp tail A*log(B*tt)*exp(-C*tt).
    return UCalcRecord(
        record=record,
        data_type=62,
        rate_type=3,
        continuation=0,
        parent_record=0,
        reals=(0.0, 0.0, 0.8, 0.2, 0.03, 0.15, 2.0, 0.4),
        integers=(1, upper),
    )


def test_type62_is_translated_and_matches_calt6062_source_formula():
    temperature = 76655.18557758832
    context = UCalcContext(
        temperature_k=temperature,
        hydrogen_density_cm3=1.0e8,
        electron_fraction_xee=1.2046560563936872,
        nlev=9,
        levels=_levels(),
    )
    result = SourceFaithfulUCalc().evaluate(_type62(488, 4), context)
    assert result.ready is True
    assert result.status.value == "evaluated"
    assert (result.idest1, result.idest2) == (1, 4)

    de = 10.2
    t = temperature / 1.0e4
    temp_for_fit = max(temperature, 0.02 * de * 1.0e4 / 0.861707)
    t1 = temp_for_fit * 6.33652e-6
    tt = min(t1, 1.0)
    upsilon = 0.8 + 0.2 * tt + 0.03 * tt**2
    upsilon += 0.15 * math.log(2.0 * tt) * math.exp(-0.4 * tt)
    if t1 > tt:
        upsilon *= 1.0 + math.log(t1 / 1.0) / (math.log(t1 / 1.0) + 1.0)
    cji = 8.626e-8 * upsilon / math.sqrt(t) / (1.0e-16 + 6.0)
    cij = cji * 6.0 * math.exp(-de / (0.861707 * t)) / (1.0e-16 + 2.0)
    ne = 1.0e8 * 1.2046560563936872
    assert result.ans1 == pytest.approx(cij * ne)
    assert result.ans2 == pytest.approx(cji * ne)
    assert result.ans6 == pytest.approx(result.ans1 * de * 1.602176634e-12)
    assert result.ans5 == pytest.approx(result.ans2 * de * 1.602176634e-12)
    assert result.diagnostics["fit_form"] == "callaway_type62_polynomial_plus_log_exp_tail"
    assert result.diagnostics["lower_principal_n"] == 1
    assert result.diagnostics["upper_principal_n"] == 2
    assert result.diagnostics["upper_orbital_l"] == 1


def test_hydrogen_records_488_491_emit_exactly_sixteen_terms():
    levels = _levels()
    context = UCalcContext(
        temperature_k=76655.18557758832,
        hydrogen_density_cm3=1.0e8,
        electron_fraction_xee=1.2046560563936872,
        nlev=9,
        levels=levels,
    )
    block = ElementIonBlock(
        ion_index=1, ion_record=1, element_z=1, ion_stage=1,
        nlev=9, compact_start=1, compact_stop=9, first_level_record=1,
        ion_counter=1,
    )
    basis = ElementCompactBasis(
        element_z=1, min_ion_stage=1, max_ion_stage=1,
        blocks=[block],
        rows=[ElementBasisRow(i, superlevel=i, ion_counter=1) for i in range(1, 10)],
        n_rows=9, n_superlevels=9, n_ions=1, normalization_row=9,
    )
    dispatcher = SourceFaithfulUCalc()
    all_terms = []
    for offset, (record, upper) in enumerate(zip(range(488, 492), (4, 7, 8, 9))):
        evaluated = dispatcher.evaluate(_type62(record, upper), context)
        terms = _matrix_terms_for_result(
            result=evaluated, basis=basis, block=block, levels=levels,
            term_start=1 + 4 * offset, xpx=context.hydrogen_density_cm3,
        )
        assert len(terms) == 4
        assert {term.role for term in terms} == {
            "forward_offdiag", "reverse_offdiag",
            "forward_diag_loss", "reverse_diag_loss",
        }
        assert all(term.record == record for term in terms)
        all_terms.extend(terms)
    assert len(all_terms) == 16
    assert [term.record for term in all_terms[::4]] == [488, 489, 490, 491]


def _assembly_two_records() -> ElementMatrixAssembly:
    block = ElementIonBlock(1, 1, 1, 1, 2, 1, 2, 1, ion_counter=1)
    basis = ElementCompactBasis(
        element_z=1, min_ion_stage=1, max_ion_stage=1,
        blocks=[block],
        rows=[ElementBasisRow(1, 1, 1), ElementBasisRow(2, 2, 1)],
        n_rows=2, n_superlevels=2, n_ions=1, normalization_row=2,
    )
    terms = []
    roles = ("forward_offdiag", "reverse_offdiag", "forward_diag_loss", "reverse_diag_loss")
    rc = ((2, 1), (1, 2), (1, 1), (2, 2))
    for rindex, record in enumerate((488, 492)):
        for off, (role, (row, col)) in enumerate(zip(roles, rc)):
            value = float(10 * rindex + off + 1)
            terms.append(MatrixTerm(
                1 + 4 * rindex + off, record, 62 if record == 488 else 63, 3,
                1, 1, role, row, col, value, value + 0.1,
                value + 0.2, value + 0.3, 1, 2, 1, 2, "evaluated", row, col,
            ))
    matrix = np.zeros((2, 2))
    for term in terms:
        matrix[term.row - 1, term.column - 1] += term.aj1
    return ElementMatrixAssembly(
        basis=basis, initial_populations=np.array([0.0, 0.5, 0.5]),
        terms=terms, dense_matrix=matrix, normalized_matrix=matrix.copy(),
        rhs=np.zeros(2), heating_matrix=np.zeros((2, 2)),
        heating_matrix2=np.zeros((2, 2)), ion_summaries=[], blocked_records=[],
        record_results=[
            {"record": 488, "data_type": 62, "rate_type": 3, "idest1": 1, "idest2": 2},
            {"record": 492, "data_type": 63, "rate_type": 3, "idest1": 1, "idest2": 2},
        ],
        n_records_seen=2, n_records_evaluated=2, n_records_source_noop=0,
        n_records_skipped=0, n_records_blocked=0, n_unmapped_endpoints=0,
        strict_assembly_ready=True,
    )


def _matrix_probe(assembly: ElementMatrixAssembly, *, drop_record: int | None = None):
    rows = []
    for term in assembly.terms:
        if term.record == drop_record:
            continue
        rows.append({
            "calc_hmc_all_call_id": 73, "element_z": 1,
            # Deliberately offset the source execution index.  Record-keyed
            # matching must remain exact despite this shift.
            "term_index": term.term_index + 100,
            "source_record": term.record,
            "row_raw": term.source_row_unclamped,
            "column_raw": term.source_column_unclamped,
            "row_compact": term.row, "column_compact": term.column,
            "aj1": term.aj1, "aj2": term.aj2,
            "cj": term.cj, "cj2": term.cj2,
        })
    return rows


def test_matrix_parity_is_record_role_keyed_not_term_index_keyed():
    assembly = _assembly_two_records()
    fixed = SimpleNamespace(element_results=[SimpleNamespace(
        request=SimpleNamespace(element_z=1),
        equilibrium=SimpleNamespace(assembly=assembly),
    )])
    compared = compare_same_call_matrix_terms(
        fixed, matrix_probe_rows=_matrix_probe(assembly), closure=None,
    )
    assert compared.topology_ready is True
    assert compared.coefficient_ready is True
    assert compared.n_matched_terms == 8
    assert compared.n_topology_mismatches == 0
    assert compared.diagnostics["join_key"] == "(element_z,source_record,role)"
    assert all(row["python_term_index"] != row["xstar_term_index"] for row in compared.term_rows)


def test_one_missing_record_reports_four_misses_without_cascade():
    assembly = _assembly_two_records()
    fixed = SimpleNamespace(element_results=[SimpleNamespace(
        request=SimpleNamespace(element_z=1),
        equilibrium=SimpleNamespace(assembly=assembly),
    )])
    compared = compare_same_call_matrix_terms(
        fixed, matrix_probe_rows=_matrix_probe(assembly, drop_record=488), closure=None,
    )
    assert compared.n_matched_terms == 4
    assert compared.n_topology_mismatches == 4
    missing = [row for row in compared.term_rows if row["match_status"] == "missing_xstar"]
    assert len(missing) == 4
    assert {row["record"] for row in missing} == {488}
    assert all(row["topology_match"] for row in compared.term_rows if row["record"] == 492)


def _write_initial_probe(path: Path) -> None:
    fields = [
        "calc_hmc_all_call_id", "element_index", "element_z",
        "compact_dimension", "compact_index", "population",
    ]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for element_index, (z, n) in enumerate(((1, 33), (2, 78), (8, 607)), start=1):
            for i in range(1, n + 1):
                writer.writerow({
                    "calc_hmc_all_call_id": 73, "element_index": element_index,
                    "element_z": z, "compact_dimension": n,
                    "compact_index": i, "population": 1.0 / n,
                })


def test_initial_population_parity_covers_all_718_h_he_o_rows(tmp_path: Path):
    _write_initial_probe(tmp_path / "xstar_calc_hmc_all_msolvelucy_initial_population_probe.csv")
    populations = {
        z: np.full(n, 1.0 / n) for z, n in ((1, 33), (2, 78), (8, 607))
    }
    compared = compare_msolvelucy_initial_populations(
        populations, tmp_path, element_zs=(1, 2, 8), call_id=73,
        rtol=5e-3, atol=1e-12,
    )
    assert compared.ready is True
    assert compared.n_rows == 718
    assert compared.compact_dimension == 718
    assert [row["element_z"] for row in compared.element_results] == [1, 2, 8]
    assert all(row["ready"] for row in compared.element_results)


def test_all_element_acceptance_requires_each_element_and_zero_blockers():
    result = SimpleNamespace(
        diagnostics={
            "element_scope": "all_positive_abundance_elements_from_xstar_probe",
            "oxygen_call73_regression_ready": True,
        },
        element_results=[SimpleNamespace(request=SimpleNamespace(element_z=z)) for z in (1, 2, 8)],
    )
    initial = MSolveLucyInitialPopulationParityResult(
        ready=True, status="ready", call_id=73, element_z=0,
        compact_dimension=718, n_rows=718, n_outside_tolerance=0,
        max_absolute_difference=0.0, max_relative_difference=0.0, rows=[],
        element_results=[
            {"element_z": z, "ready": True, "status": "ready", "n_rows": n}
            for z, n in ((1, 33), (2, 78), (8, 607))
        ],
    )
    matrix = SameCallMatrixParityResult(
        status="ready", ready=True, topology_ready=True,
        coefficient_ready=False, active_closure_ready=True,
        n_python_terms=3, n_xstar_terms=3, n_matched_terms=3,
        n_topology_mismatches=0, n_coefficient_rows_outside_tolerance=0,
        n_active_rows_outside_tolerance=0, max_abs_aj1_difference=0,
        max_abs_aj2_difference=0, max_abs_cj_difference=0,
        max_abs_cj2_difference=0,
        term_rows=[{"element_z": z, "topology_match": True} for z in (1, 2, 8)],
        active_row_rows=[], diagnostics={"closure_elements_evaluated": [1, 2, 8]},
    )
    thermal = ThermalFamilyParityResult(
        status="ready", ready=True, n_rows=3, n_outside_tolerance=0,
        rows=[{"element_z": z, "within_tolerance": True} for z in (1, 2, 8)],
    )
    final = MSolveLucyFinalSnapshotParityResult(
        status="ready", ready=True, probe_pair_present=True,
        same_iteration_ready=True, iteration_tuple_ready=True,
        matrix_dimension_ready=True, matrix_population_columns_ready=True,
        topology_ready=True, coefficient_ready=False,
        active_final_population_ready=True, active_outer_start_population_ready=True,
        source_xtot_ready=True, final_vector_xtot_ready=True,
        n_matrix_rows=3, n_population_rows=3, n_topology_mismatches=0,
        n_coefficient_rows_outside_tolerance=0,
        n_active_final_population_rows_outside_tolerance=0,
        n_active_outer_start_rows_outside_tolerance=0,
        n_source_xtot_rows_outside_tolerance=0,
        population_rows=[{
            "element_z": z, "active_population": True,
            "final_population_within_tolerance": True,
            "outer_start_population_within_tolerance": True,
        } for z in (1, 2, 8)],
        ion_total_rows=[{
            "element_z": z, "source_xtot_within_tolerance": True,
        } for z in (1, 2, 8)],
    )
    ready, solver_ready, thermal_ready, elements = _all_element_acceptance_summary(
        result, rows=[], blocking_outside=0, initial=initial,
        matrix=matrix, thermal=thermal, final=final,
    )
    assert ready is True
    assert solver_ready is True
    assert thermal_ready is True
    assert [row["element_z"] for row in elements] == [1, 2, 8]
    assert all(row["detailed_parity_ready"] for row in elements)


def test_type62_preserves_source_nlev_endpoint_rejection():
    levels = _levels()
    # The mutable leveltemp workspace may contain higher zero columns, but
    # ucalc label 60/62 rejects endpoints outside the current source nlev.
    levels.levels[10] = UCalcLevel(10, energy_ev=13.0, statistical_weight=2.0)
    context = UCalcContext(
        temperature_k=1.0e5, hydrogen_density_cm3=1.0,
        electron_fraction_xee=1.0, nlev=9, levels=levels,
    )
    rejected = SourceFaithfulUCalc().evaluate(_type62(999, 10), context)
    assert rejected.status.value == "source_branch_rejected_record"
    assert rejected.reason == "type6062_endpoint_outside_level_table"


def test_all_element_acceptance_fails_when_hydrogen_thermal_row_fails():
    result = SimpleNamespace(
        diagnostics={
            "element_scope": "all_positive_abundance_elements_from_xstar_probe",
            "oxygen_call73_regression_ready": True,
        },
        element_results=[SimpleNamespace(request=SimpleNamespace(element_z=z)) for z in (1, 2, 8)],
    )
    initial = MSolveLucyInitialPopulationParityResult(
        True, "ready", 73, 0, 718, 718, 0, 0.0, 0.0, [],
        [{"element_z": z, "ready": True, "n_rows": n} for z, n in ((1, 33), (2, 78), (8, 607))],
    )
    matrix = SameCallMatrixParityResult(
        "ready", True, True, False, True, 3, 3, 3, 0, 0, 0,
        0.0, 0.0, 0.0, 0.0,
        term_rows=[{"element_z": z, "topology_match": True} for z in (1, 2, 8)],
        diagnostics={"closure_elements_evaluated": [1, 2, 8]},
    )
    thermal = ThermalFamilyParityResult(
        "failed", False, 3, 1,
        rows=[
            {"element_z": 1, "within_tolerance": False},
            {"element_z": 2, "within_tolerance": True},
            {"element_z": 8, "within_tolerance": True},
        ],
    )
    final = MSolveLucyFinalSnapshotParityResult(
        status="ready", ready=True, probe_pair_present=True,
        same_iteration_ready=True, iteration_tuple_ready=True,
        matrix_dimension_ready=True, matrix_population_columns_ready=True,
        topology_ready=True, coefficient_ready=False,
        active_final_population_ready=True, active_outer_start_population_ready=True,
        source_xtot_ready=True, final_vector_xtot_ready=True,
        n_matrix_rows=3, n_population_rows=3, n_topology_mismatches=0,
        n_coefficient_rows_outside_tolerance=0,
        n_active_final_population_rows_outside_tolerance=0,
        n_active_outer_start_rows_outside_tolerance=0,
        n_source_xtot_rows_outside_tolerance=0,
        population_rows=[{
            "element_z": z, "active_population": True,
            "final_population_within_tolerance": True,
            "outer_start_population_within_tolerance": True,
        } for z in (1, 2, 8)],
        ion_total_rows=[{"element_z": z, "source_xtot_within_tolerance": True} for z in (1, 2, 8)],
    )

    ready, _solver, all_thermal, elements = _all_element_acceptance_summary(
        result, rows=[], blocking_outside=0, initial=initial,
        matrix=matrix, thermal=thermal, final=final,
    )
    assert ready is False
    assert all_thermal is False
    hydrogen = next(row for row in elements if row["element_z"] == 1)
    assert hydrogen["thermal_family_ready"] is False
    assert hydrogen["detailed_parity_ready"] is False
