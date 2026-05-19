from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import shutil
import subprocess

import numpy as np
import pytest

from xstar_atomic.rates_type71 import evaluate_type71_ucalc_record
from xstar_atomic.source_port import (
    ElementBasisRow,
    ElementCompactBasis,
    ElementEquilibriumContext,
    MatrixTerm,
    SameCallMatrixParityResult,
    SourceFaithfulUCalc,
    UCalcContext,
    UCalcLevel,
    UCalcLevelTable,
    UCalcRecord,
    compare_msolvelucy_final_snapshot,
    diagnose_rate7_cj2_records,
    msolvelucy,
)
from xstar_atomic.source_port.element_equilibrium import ElementMatrixAssembly
from xstar_atomic.xstar_calc_hmc_all_probe import (
    calc_hmc_all_insertion_snippets,
    calc_hmc_all_probe_helper,
)


def _levels() -> UCalcLevelTable:
    return UCalcLevelTable(
        levels={
            1: UCalcLevel(1, energy_ev=0.0, statistical_weight=2.0),
            2: UCalcLevel(2, energy_ev=12.0, statistical_weight=4.0),
        },
        nlev=2,
    )


def test_type71_ports_post_swap_ans3_ans4_wavelength_energy_channel():
    # Single-point calt71: log10(A)=1, wavelength=10 Angstrom.  The last four
    # packed integers are the source endpoints 2 -> 1.
    record = UCalcRecord(
        71001, 71, 14, 0,
        (0.0, 0.0, 1.0, 10.0),
        (1, 1, 0, 0, 2, 1, 0, 0),
    )
    context = UCalcContext(
        temperature_k=1.0e6,
        hydrogen_density_cm3=1.0e8,
        ptmp1=0.4,
        ptmp2=0.6,
        nlev=2,
        levels=_levels(),
    )
    result = SourceFaithfulUCalc().evaluate(record, context)
    decay = 10.0
    expected = -decay * (12398.4016 / 10.0) * 1.602197e-12
    assert (result.idest1, result.idest2) == (2, 1)
    assert result.ans1 == 0.0
    assert result.ans2 == pytest.approx(decay)
    assert result.ans3 == pytest.approx(expected)
    assert result.ans4 == 0.0
    assert result.diagnostics["energy_channel_source"] == "stored_wavelength"


def test_type71_fake_wavelength_uses_endpoint_energy_difference():
    evaluated = evaluate_type71_ucalc_record(
        {"reals": [0.0, 0.0, 2.0, 0.01], "ints": [1, 1, 0, 0, 2, 1, 0, 0]},
        temperature_k=1.0e6,
        electron_density_cm3=1.0e8,
        ptmp1=0.5,
        ptmp2=0.5,
        endpoint1_energy_ev=12.0,
        endpoint2_energy_ev=2.0,
    )
    assert evaluated["ans2_downward_s^-1"] == pytest.approx(100.0)
    assert evaluated["ans3_cooling_signed_erg_s^-1"] == pytest.approx(
        -100.0 * 10.0 * 1.602176634e-12
    )
    assert evaluated["ans4_heating_signed_erg_s^-1"] == 0.0
    assert evaluated["energy_channel_source"] == "endpoint_energy_difference"


def test_type72_uses_fourth_and_third_integers_from_record_tail():
    record = UCalcRecord(
        72001, 72, 40, 0,
        (1.0e12, 3.0, 1.0),
        (7, 8, 9, 10, 2, 1, 99, 98),
    )
    result = SourceFaithfulUCalc().evaluate(
        record,
        UCalcContext(
            temperature_k=1.0e6,
            hydrogen_density_cm3=1.0e8,
            electron_fraction_xee=1.2,
            nlev=2,
            levels=_levels(),
        ),
    )
    assert (result.idest1, result.idest2) == (2, 1)


def _two_level_assembly(rate_type: int = 4, data_type: int = 50) -> tuple[ElementMatrixAssembly, ElementEquilibriumContext]:
    basis = ElementCompactBasis(
        element_z=8,
        min_ion_stage=3,
        max_ion_stage=3,
        blocks=[],
        rows=[
            ElementBasisRow(1, superlevel=1, ion_counter=1, roles=[{"ion_stage": 3, "local_level": 1, "role": "ground"}]),
            ElementBasisRow(2, superlevel=2, ion_counter=1, roles=[{"ion_stage": 3, "local_level": 2, "role": "continuum"}]),
        ],
        n_rows=2,
        n_superlevels=2,
        n_ions=1,
        normalization_row=2,
    )
    up, down = 2.0, 8.0
    terms = [
        MatrixTerm(1, 53001, data_type, rate_type, 1, 3, "forward_offdiag", 2, 1, up, down, 0, 0, 1, 2, 1, 2, "evaluated", 2, 1),
        MatrixTerm(2, 53001, data_type, rate_type, 1, 3, "reverse_offdiag", 1, 2, down, up, 0, 0, 1, 2, 1, 2, "evaluated", 1, 2),
        MatrixTerm(3, 53001, data_type, rate_type, 1, 3, "forward_diag_loss", 1, 1, -up, -up, 0, 6.0, 1, 2, 1, 2, "evaluated", 1, 1),
        MatrixTerm(4, 53001, data_type, rate_type, 1, 3, "reverse_diag_loss", 2, 2, -down, -down, 0, 5.0, 1, 2, 1, 2, "evaluated", 2, 2),
    ]
    matrix = np.asarray([[-up, down], [up, -down]], dtype=float)
    assembly = ElementMatrixAssembly(
        basis=basis,
        initial_populations=np.asarray([0.0, 0.5, 0.5]),
        terms=terms,
        dense_matrix=matrix,
        normalized_matrix=np.asarray([[-up, down], [1.0, 1.0]], dtype=float),
        rhs=np.asarray([0.0, 1.0]),
        heating_matrix=np.zeros((2, 2)),
        heating_matrix2=np.zeros((2, 2)),
        ion_summaries=[],
        blocked_records=[],
        record_results=[{
            "record": 53001, "data_type": data_type, "rate_type": rate_type,
            "status": "evaluated", "ion_stage": 3,
            "ans5": -5.0, "ans6": 6.0,
            "diag_threshold_eV": 10.0,
        }],
        n_records_seen=1, n_records_evaluated=1, n_records_source_noop=0,
        n_records_skipped=0, n_records_blocked=0, n_unmapped_endpoints=0,
        strict_assembly_ready=True,
    )
    context = ElementEquilibriumContext(
        temperature_k=1.0e6,
        hydrogen_density_cm3=1.0,
        electron_fraction_xee=1.0,
        min_ion_stage=3,
        max_ion_stage=3,
    )
    return assembly, context


def test_msolvelucy_source_xtot_uses_final_outer_start_and_excludes_last_row():
    assembly, context = _two_level_assembly()
    solved = msolvelucy(assembly, context)
    assert solved.ion_population_totals_source == "final_outer_iteration_start_vector"
    assert solved.ion_population_totals[0] == pytest.approx(
        solved.final_outer_start_populations[0]
    )
    assert solved.ion_population_totals_final_vector[0] == pytest.approx(
        solved.populations[0]
    )


def _final_probe_rows(assembly: ElementMatrixAssembly, solved) -> tuple[list[dict], list[dict]]:
    common = {
        "calc_hmc_all_call_id": 73,
        "element_index": 5,
        "element_z": 8,
        "outer_iteration": solved.outer_iterations,
        "fixed_iteration": 1,
        "global_fixed_iteration": solved.fixed_point_iterations,
        "final_outer_difference": solved.final_outer_difference,
        "final_fixed_difference": solved.final_fixed_point_difference,
        "compact_dimension": assembly.basis.n_rows,
    }
    populations = []
    for compact in range(1, assembly.basis.n_rows + 1):
        populations.append({
            **common,
            "compact_index": compact,
            "population": solved.populations[compact - 1],
            "final_outer_start_population": solved.final_outer_start_populations[compact - 1],
            "superlevel": assembly.basis.nsup[compact],
            "ion_counter": assembly.basis.nion[compact],
        })
    matrix = []
    for term in assembly.terms:
        matrix.append({
            **common,
            "n_matrix_terms": len(assembly.terms),
            "term_index": term.term_index,
            "source_record": term.record,
            "row_raw": term.source_row_unclamped,
            "column_raw": term.source_column_unclamped,
            "row_compact": term.row,
            "column_compact": term.column,
            "operator_coefficient": term.aj1,
            "aj1": term.aj1,
            "aj2": term.aj2,
            "cj": term.cj,
            "cj2": term.cj2,
            "row_population": solved.populations[term.row - 1],
            "column_population": solved.populations[term.column - 1],
            "row_outer_start_population": solved.final_outer_start_populations[term.row - 1],
            "column_outer_start_population": solved.final_outer_start_populations[term.column - 1],
        })
    return matrix, populations


def test_final_msolvelucy_snapshot_compares_operator_x_and_xo_same_iteration():
    assembly, context = _two_level_assembly()
    solved = msolvelucy(assembly, context)
    matrix, populations = _final_probe_rows(assembly, solved)
    fixed = SimpleNamespace(
        element_results=[SimpleNamespace(
            request=SimpleNamespace(element_z=8),
            equilibrium=SimpleNamespace(assembly=assembly, solve=solved),
        )]
    )
    compared = compare_msolvelucy_final_snapshot(
        fixed,
        final_matrix_rows=matrix,
        final_population_rows=populations,
    )
    assert compared.ready is True
    assert compared.same_iteration_ready is True
    assert compared.topology_ready is True
    assert compared.coefficient_ready is True
    assert compared.active_final_population_ready is True
    assert compared.active_outer_start_population_ready is True
    assert compared.source_xtot_ready is True
    assert compared.oxygen_reassessment_rows == []


def test_rate7_cj2_diagnosis_is_record_resolved_and_type53_gated():
    assembly, _ = _two_level_assembly(rate_type=7, data_type=53)
    term_rows = []
    for term in assembly.terms:
        term_rows.append({
            "element_z": 8, "term_index": term.term_index,
            "record": term.record, "data_type": term.data_type,
            "rate_type": term.rate_type, "role": term.role,
            "python_row_compact": term.row, "xstar_row_compact": term.row,
            "python_cj2": term.cj2, "xstar_cj2": term.cj2,
            "topology_match": True, "within_tolerance": True,
        })
    same = SameCallMatrixParityResult(
        status="ready", ready=True, topology_ready=True,
        coefficient_ready=True, active_closure_ready=True,
        n_python_terms=4, n_xstar_terms=4, n_matched_terms=4,
        n_topology_mismatches=0, n_coefficient_rows_outside_tolerance=0,
        n_active_rows_outside_tolerance=0,
        max_abs_aj1_difference=0.0, max_abs_aj2_difference=0.0,
        max_abs_cj_difference=0.0, max_abs_cj2_difference=0.0,
        term_rows=term_rows,
    )
    fixed = SimpleNamespace(
        hydrogen_density_cm3=1.0,
        element_results=[SimpleNamespace(
            request=SimpleNamespace(element_z=8),
            equilibrium=SimpleNamespace(assembly=assembly),
        )],
    )
    diagnosis = diagnose_rate7_cj2_records(fixed, same_call_matrix=same)
    assert diagnosis.ready is True
    assert diagnosis.type53_ready is True
    assert diagnosis.n_type53_records == 1
    assert diagnosis.n_type53_rows == 2
    assert {row["source_energy_channel"] for row in diagnosis.rows} == {
        "ans6_forward_electron_pov", "minus_ans5_reverse_electron_pov"
    }
    assert all(row["record_channel_reconstruction_matches_matrix"] for row in diagnosis.rows)


def test_v0431_probe_has_seven_hooks_and_compiles(tmp_path: Path):
    snippets = calc_hmc_all_insertion_snippets()
    # Later bounded releases may append source-local hooks while preserving
    # the original v0.4.31 seven-hook set.
    assert len(snippets) >= 7
    assert "msolvelucy_final_snapshot" in snippets
    helper = calc_hmc_all_probe_helper()
    assert "xstar_calc_hmc_all_msolvelucy_final_matrix_probe.csv" in helper
    assert "xstar_calc_hmc_all_msolvelucy_final_population_probe.csv" in helper
    assert "x(*), xo(*)" in helper
    assert "es26.16e3" in helper.lower()
    gfortran = shutil.which("gfortran")
    if gfortran is None:
        pytest.skip("gfortran not installed")
    source = tmp_path / "probe.f90"
    source.write_text(helper)
    subprocess.run(
        [gfortran, "-c", "-ffree-line-length-none", str(source)],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
