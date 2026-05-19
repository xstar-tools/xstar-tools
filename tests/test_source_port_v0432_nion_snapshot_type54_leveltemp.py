from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from xstar_atomic.rates_type53 import Type53LiveRadiationState
from xstar_atomic.source_port import (
    ElementBasisRow,
    ElementCompactBasis,
    ElementEquilibriumContext,
    MatrixTerm,
    SourceFaithfulUCalc,
    UCalcContext,
    UCalcLevel,
    UCalcLevelTable,
    UCalcRecord,
    build_element_compact_basis,
    compare_msolvelucy_final_snapshot,
    msolvelucy,
)
from xstar_atomic.source_port.element_equilibrium import (
    ElementMatrixAssembly,
    _copy_level_table,
    _overwrite_leveltemp_workspace,
)
from xstar_atomic.source_port.ucalc import (
    XSTAR_SOURCE_ERG_PER_EV,
    XSTAR_SOURCE_KT_EV_PER_1E4K,
)


def _assembly() -> tuple[ElementMatrixAssembly, ElementEquilibriumContext]:
    basis = ElementCompactBasis(
        element_z=8,
        min_ion_stage=3,
        max_ion_stage=3,
        blocks=[],
        rows=[
            ElementBasisRow(1, superlevel=1, ion_counter=3,
                            roles=[{"ion_stage": 3, "local_level": 1, "role": "ground"}]),
            ElementBasisRow(2, superlevel=2, ion_counter=8,
                            roles=[{"ion_stage": 9, "local_level": 1, "role": "continuum"}]),
        ],
        n_rows=2,
        n_superlevels=2,
        n_ions=8,
        normalization_row=2,
        ion_stage_by_counter={i: i for i in range(1, 9)},
    )
    up, down = 2.0, 8.0
    terms = [
        MatrixTerm(1, 53001, 50, 4, 1, 3, "forward_offdiag", 2, 1,
                   up, down, 0, 0, 1, 2, 1, 2, "evaluated", 2, 1),
        MatrixTerm(2, 53001, 50, 4, 1, 3, "reverse_offdiag", 1, 2,
                   down, up, 0, 0, 1, 2, 1, 2, "evaluated", 1, 2),
        MatrixTerm(3, 53001, 50, 4, 1, 3, "forward_diag_loss", 1, 1,
                   -up, -up, 0, 0, 1, 2, 1, 2, "evaluated", 1, 1),
        MatrixTerm(4, 53001, 50, 4, 1, 3, "reverse_diag_loss", 2, 2,
                   -down, -down, 0, 0, 1, 2, 1, 2, "evaluated", 2, 2),
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
        ion_summaries=[], blocked_records=[], record_results=[],
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


def _snapshot_rows(assembly: ElementMatrixAssembly, solved, *, xstar_outer: int = 99):
    common = {
        "calc_hmc_all_call_id": 73,
        "element_index": 5,
        "element_z": 8,
        # Deliberately not equal to Python's iteration counts.  Snapshot
        # synchronization is an internal XSTAR property.
        "outer_iteration": xstar_outer,
        "fixed_iteration": 7,
        "global_fixed_iteration": 123,
        "final_outer_difference": 1.25e-7,
        "final_fixed_difference": 2.5e-8,
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


def _fixed_result(assembly, solved):
    return SimpleNamespace(
        element_results=[SimpleNamespace(
            request=SimpleNamespace(element_z=8),
            equilibrium=SimpleNamespace(assembly=assembly, solve=solved),
        )]
    )


def test_source_nionp_counters_include_inactive_lower_ions():
    derived = SimpleNamespace(
        n_ions=8,
        ion_element_z=np.asarray([0] + [8] * 8),
        ion_stage=np.asarray([0] + list(range(1, 9))),
        ion_records=np.asarray([0] + list(range(101, 109))),
        nlevs=np.asarray([0] + [2] * 8),
        npfi=np.zeros((14, 9), dtype=int),
    )
    basis = build_element_compact_basis(
        SimpleNamespace(record_chars=lambda record: b""),
        derived,
        element_z=8,
        min_ion_stage=3,
        max_ion_stage=8,
    )
    assert [block.ion_counter for block in basis.blocks] == [3, 4, 5, 6, 7, 8]
    assert basis.n_ions == 8
    assert basis.nion[basis.normalization_row] == 8
    assert basis.ion_stage_by_counter == {i: i for i in range(1, 9)}


def test_source_xtot_uses_global_nionp_slot_and_excludes_final_row():
    assembly, context = _assembly()
    solved = msolvelucy(assembly, context)
    assert solved.ion_population_totals.shape == (8,)
    assert solved.ion_population_totals[2] == pytest.approx(
        solved.final_outer_start_populations[0]
    )
    assert np.count_nonzero(solved.ion_population_totals) == 1


def test_snapshot_gate_uses_internal_xstar_tuple_dimensions_and_population_columns():
    assembly, context = _assembly()
    solved = msolvelucy(assembly, context)
    matrix, populations = _snapshot_rows(assembly, solved, xstar_outer=99)
    compared = compare_msolvelucy_final_snapshot(
        _fixed_result(assembly, solved),
        final_matrix_rows=matrix,
        final_population_rows=populations,
    )
    assert solved.outer_iterations != 99
    assert compared.ready is True
    assert compared.iteration_tuple_ready is True
    assert compared.matrix_dimension_ready is True
    assert compared.matrix_population_columns_ready is True
    assert compared.same_iteration_ready is True

    bad_dimensions = [dict(row, compact_dimension=3) for row in matrix]
    bad = compare_msolvelucy_final_snapshot(
        _fixed_result(assembly, solved),
        final_matrix_rows=bad_dimensions,
        final_population_rows=populations,
    )
    assert bad.ready is False
    assert bad.iteration_tuple_ready is True
    assert bad.matrix_dimension_ready is False

    bad_columns = [dict(row) for row in matrix]
    bad_columns[0]["row_population"] += 1.0e-3
    bad = compare_msolvelucy_final_snapshot(
        _fixed_result(assembly, solved),
        final_matrix_rows=bad_columns,
        final_population_rows=populations,
    )
    assert bad.ready is False
    assert bad.matrix_population_columns_ready is False


def test_type54_uses_dimensionless_delta_e_over_kt_energy_channel():
    levels = UCalcLevelTable(
        levels={
            1: UCalcLevel(1, energy_ev=0.0, statistical_weight=2.0,
                          principal_n=1, orbital_l=0),
            2: UCalcLevel(2, energy_ev=10.0, statistical_weight=4.0,
                          principal_n=2, orbital_l=1),
        },
        nlev=2,
    )
    result = SourceFaithfulUCalc().evaluate(
        UCalcRecord(54001, 54, 4, 0, (), (1, 2, 1, 0)),
        UCalcContext(temperature_k=1.0e6, nlev=2, levels=levels),
    )
    expected_delt = 10.0 / (XSTAR_SOURCE_KT_EV_PER_1E4K * 100.0)
    assert result.diagnostics["delt_dimensionless"] == pytest.approx(expected_delt)
    assert result.ans3 == pytest.approx(
        -result.ans2 * expected_delt * XSTAR_SOURCE_ERG_PER_EV
    )


def _persistent_levels() -> UCalcLevelTable:
    return UCalcLevelTable(
        levels={
            1: UCalcLevel(1, energy_ev=0.0, statistical_weight=2.0,
                          ionization_potential_ev=20.0),
            2: UCalcLevel(2, energy_ev=20.0, statistical_weight=1.0,
                          ionization_potential_ev=20.0),
            # Retained column from a previously processed ion.
            3: UCalcLevel(3, energy_ev=77.0, statistical_weight=9.0),
        },
        nlev=2,
    )


def _radiation() -> Type53LiveRadiationState:
    return Type53LiveRadiationState.from_sequences(
        [1.0, 10.0, 20.0, 40.0, 80.0],
        [1.0] * 5,
        [0.0] * 5,
    )


def test_leveltemp_overwrite_retains_higher_columns():
    prior = UCalcLevelTable(
        levels={i: UCalcLevel(i, energy_ev=float(10 * i)) for i in range(1, 5)},
        nlev=4,
    )
    current = UCalcLevelTable(
        levels={1: UCalcLevel(1, energy_ev=1.0), 2: UCalcLevel(2, energy_ev=2.0)},
        nlev=2,
    )
    workspace = _overwrite_leveltemp_workspace(_copy_level_table(prior), current)
    assert workspace.nlev == 2
    assert workspace.energy(1) == 1.0
    assert workspace.energy(2) == 2.0
    assert workspace.energy(3) == 30.0
    assert workspace.energy(4) == 40.0


@pytest.mark.parametrize("data_type", [49, 53])
def test_type49_and_type53_use_persistent_leveltemp_destination_energy(monkeypatch, data_type):
    captured = {}

    def fake_type53(decoded, *args, **kwargs):
        captured.update(decoded)
        return {
            "status": "evaluated",
            "ans1_photoionization_s^-1": 1.0,
            "ans2_milne_recombination_s^-1": 1.0,
            "ans3_cooling_signed_erg_s^-1": -1.0,
            "ans4_heating_signed_erg_s^-1": -1.0,
            "ans5_electron_pov_cooling_signed_erg_s^-1": -1.0,
            "ans6_electron_pov_heating_signed_erg_s^-1": -1.0,
            "opakab_cm^-1": 0.0,
        }

    monkeypatch.setattr(
        "xstar_atomic.rates_type53.evaluate_type53_ucalc_record", fake_type53
    )
    record = UCalcRecord(
        50000 + data_type,
        data_type,
        7,
        0,
        (0.0, 1.0, 1.0, 1.0),
        (2, 99, 1, 88),  # off=2 at [-4], bound level=1 at [-2]
    )
    context = UCalcContext(
        temperature_k=1.0e6,
        hydrogen_density_cm3=1.0,
        electron_fraction_xee=1.0,
        nlev=2,
        levels=_persistent_levels(),
        radiation=_radiation(),
        extras={
            "parent_level_energy_ev_by_destination": {3: 5.0},
            "parent_level_stat_weight_by_destination": {3: 6.0},
        },
    )
    result = SourceFaithfulUCalc().evaluate(record, context)
    assert result.status.value == "evaluated"
    assert captured["destination_energy_eV"] == 77.0
    assert captured["leveltemp_destination_energy_eV"] == 77.0
    assert captured["physical_parent_destination_energy_eV"] != 77.0


def test_type99_uses_persistent_leveltemp_destination_energy(monkeypatch):
    def fake_calt99(**kwargs):
        return {
            "type99_calt99_rec_cm3_s": 1.0,
            "type99_cross_section_energy_ryd": [0.0, 1.0],
            "type99_cross_section_scaled_cm2": [1.0, 1.0],
            "type99_calt99_status": "evaluated",
        }

    monkeypatch.setattr(
        "xstar_atomic.xstar_element_solver._xstar_calt99_superlevel_bound_free",
        fake_calt99,
    )
    energy = XSTAR_SOURCE_ERG_PER_EV
    monkeypatch.setattr(
        "xstar_atomic.source_port.ucalc._phint53hunt_exact",
        lambda **kwargs: {
            "pirt": 1.0,
            "rrrt": 1.0,
            "piht": 100.0 * energy,
            "rrcl": 100.0 * energy,
            "piht2": 1.0,
            "rrcl2": 1.0,
        },
    )
    result = SourceFaithfulUCalc().evaluate(
        UCalcRecord(99001, 99, 7, 0, (1.0,), (2, 99, 1, 88)),
        UCalcContext(
            temperature_k=1.0e6,
            hydrogen_density_cm3=1.0,
            electron_fraction_xee=1.0,
            nlev=2,
            levels=_persistent_levels(),
            radiation=_radiation(),
            extras={
                "parent_level_energy_ev_by_destination": {3: 5.0},
                "parent_level_stat_weight_by_destination": {3: 6.0},
            },
        ),
    )
    # threshold=5 eV, source leveltemp energy difference=77 eV.
    assert result.ans6 == pytest.approx(-(100.0 - 77.0) / (100.0 - 5.0))
    assert result.diagnostics["type99_leveltemp_destination_energy_eV"] == 77.0
