from __future__ import annotations

from importlib import resources
from types import SimpleNamespace
import csv
import json

import numpy as np
import pytest

from xstar_atomic.source_port.calc_hmc_all_matrix_parity import (
    SameCallMatrixParityResult,
    compare_thermal_families,
    diagnose_rate7_cj2_records,
)
from xstar_atomic.source_port.element_equilibrium import (
    ElementCompactBasis,
    ElementIonBlock,
    XSTAR_LEVELTEMP_NDL,
    _initialize_leveltemp_workspace_from_levwkelement,
)
from xstar_atomic.source_port.leveltemp_energy_parity import (
    compare_leveltemp_energy_probe,
)
from xstar_atomic.source_port.local_zone import _assembly_lte_population_vector
from xstar_atomic.source_port.ucalc import (
    UCalcContext,
    UCalcLevel,
    UCalcLevelTable,
    _phint53hunt_exact,
    _phint53hunt_reuse_cached_point,
)


def _benchmark_root():
    return resources.files("xstar_atomic.benchmarks").joinpath("oxygen_v0434")


def _read_csv(name: str):
    with _benchmark_root().joinpath(name).open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_v0434_frozen_regression_gate_counts():
    manifest = json.loads(
        _benchmark_root().joinpath("benchmark_manifest.json").read_text(encoding="utf-8")
    )
    expected = {
        "rnisg_rows": 35,
        "bilevg_rows": 349,
        "type53_leveltemp_rows": 205,
        "type53_cj2_records": 196,
        "type99_ans5_records": 7,
        "thermal_family_rows": 2,
    }
    assert manifest["expected_counts"] == expected

    global_rows = _read_csv("v0433_global_level_remaining_rows.csv")
    assert sum(row["component"] == "global_level_rnisg" for row in global_rows) == 35
    assert sum(row["component"] == "global_level_bilevg" for row in global_rows) == 349
    assert len(_read_csv("v0433_type53_leveltemp_remaining_rows.csv")) == 205
    assert len(_read_csv("v0433_type53_cj2_remaining_records.csv")) == 196
    assert len(_read_csv("v0433_type99_ans5_rows.csv")) == 7
    assert len(_read_csv("v0433_thermal_family_remaining_rows.csv")) == 2


def test_rnise_lte_remains_distinct_from_same_call_solver_seed():
    rnise_lte = np.array([0.0, 0.6, 0.3, 0.1])
    solver_seed = np.array([0.0, 0.2, 0.5, 0.3])
    assembly = SimpleNamespace(
        lte_populations=rnise_lte,
        initial_populations=solver_seed,
    )
    selected = _assembly_lte_population_vector(assembly)
    assert np.array_equal(selected, rnise_lte)
    assert not np.shares_memory(selected, solver_seed)
    # The 35 rnisg and 349 bilevg rows are both controlled by rnise_lte.
    population = np.array([0.0, 0.12, 0.21, 0.07])
    bilevg = population[1:] / (selected[1:] + 1.0e-37)
    assert np.allclose(bilevg, [0.2, 0.7, 0.7])


def _table(nlev: int, base: float) -> UCalcLevelTable:
    return UCalcLevelTable(
        levels={
            i: UCalcLevel(index=i, energy_ev=base + i, statistical_weight=1.0)
            for i in range(1, nlev + 1)
        },
        nlev=nlev,
    )


def _oxygen_basis() -> ElementCompactBasis:
    dims = [79, 163, 53, 43, 241, 33]
    blocks = []
    start = 1
    for ion_index, (stage, nlev) in enumerate(zip(range(3, 9), dims), start=1):
        blocks.append(ElementIonBlock(
            ion_index=ion_index,
            ion_record=100 + ion_index,
            element_z=8,
            ion_stage=stage,
            nlev=nlev,
            compact_start=start,
            compact_stop=start + nlev - 1,
            first_level_record=1000 + ion_index,
            ion_counter=stage,
        ))
        start += nlev - 1
    return ElementCompactBasis(
        element_z=8,
        min_ion_stage=3,
        max_ion_stage=8,
        blocks=blocks,
        rows=[],
        n_rows=start - 1,
        n_superlevels=1,
        n_ions=8,
        normalization_row=start - 1,
    )


def test_complete_leveltemp_workspace_is_zero_initialized_through_ndl_5000():
    basis = _oxygen_basis()
    tables = {
        block.ion_index: _table(block.nlev, 1000.0 * block.ion_stage)
        for block in basis.blocks
    }
    workspace, owners, trace = _initialize_leveltemp_workspace_from_levwkelement(
        basis, tables
    )
    assert len(workspace.levels) == XSTAR_LEVELTEMP_NDL == 5000
    assert max(workspace.levels) == 5000
    # O VII writes 1:241 and O VIII then overwrites 1:33.  Columns 242:246
    # were never written and must remain valid zero-valued source columns.
    for index in range(242, 247):
        assert workspace.require(index).energy_ev == 0.0
        assert owners[index]["phase"] == "initial_unwritten_zero"
        assert owners[index]["write_sequence"] == 0
    assert trace[-1]["workspace_capacity"] == 5000


def test_205_type53_exact_leveltemp_rows_close_with_unwritten_zero_columns():
    benchmark = _read_csv("v0433_type53_leveltemp_remaining_rows.csv")
    assert len(benchmark) == 205
    record_rows = []
    probe_rows = []
    for source in benchmark:
        record = int(source["record"])
        idest1 = int(source["python_idest1"])
        idest2 = int(source["python_idest2"])
        ion_stage = int(source["ion_stage"])
        record_rows.append({
            "record": record,
            "data_type": 53,
            "rate_type": 7,
            "status": "evaluated",
            "ion_index": 1,
            "ion_stage": ion_stage,
            "nlev": int(source["python_nlev"]),
            "idest1": idest1,
            "idest2": idest2,
            "leveltemp_idest1_energy_ev": float(source["xstar_leveltemp_e1_ev"]),
            "leveltemp_idest2_energy_ev": 0.0,
            "leveltemp_idest2_owner_ion_index": 0,
            "leveltemp_idest2_owner_ion_stage": 0,
            "leveltemp_idest2_owner_nlev": 0,
            "leveltemp_idest2_owner_write_sequence": 0,
            "leveltemp_idest2_owner_phase": "initial_unwritten_zero",
            "leveltemp_workspace_write_sequence": 11,
            "leveltemp_workspace_max_column": 5000,
            "ans1": 0.0,
            "ans2": 0.0,
            "ans3": 0.0,
            "ans4": 0.0,
            "ans5": 0.0,
            "ans6": 0.0,
        })
        probe_rows.append({
            "element_z": 8,
            "record": record,
            "data_type": 53,
            "rate_type": 7,
            "ion_stage": ion_stage,
            "ion_index": 1,
            "nlev": int(source["xstar_nlev"]),
            "idest1": int(source["xstar_idest1"]),
            "idest2": int(source["xstar_idest2"]),
            "leveltemp_e1_ev": source["xstar_leveltemp_e1_ev"],
            "leveltemp_e2_ev": source["xstar_leveltemp_e2_ev"],
            "ans1": 0.0,
            "ans2": 0.0,
            "ans3": 0.0,
            "ans4": 0.0,
            "ans5": 0.0,
            "ans6": 0.0,
        })
    assembly = SimpleNamespace(record_results=record_rows, leveltemp_workspace_trace=[])
    fixed = SimpleNamespace(element_results=[SimpleNamespace(
        request=SimpleNamespace(element_z=8),
        equilibrium=SimpleNamespace(assembly=assembly),
    )])
    parity = compare_leveltemp_energy_probe(fixed, probe_rows=probe_rows)
    assert parity.ready is True
    assert parity.type53_ready is True
    assert parity.n_xstar_rows == 205
    assert parity.n_type53_energy_outside_tolerance == 0


def test_196_type53_cj2_record_gate_closes_when_ans5_ans6_match():
    benchmark = _read_csv("v0433_type53_cj2_remaining_records.csv")
    assert len(benchmark) == 196
    record_results = []
    term_rows = []
    xpx = 1.0e8
    for term_index, source in enumerate(benchmark, start=1):
        record = int(source["record"])
        ans5 = 2.0e-20 * term_index
        ans6 = 3.0e-20 * term_index
        record_results.append({
            "record": record,
            "data_type": 53,
            "rate_type": 7,
            "status": "evaluated",
            "ion_stage": 7,
            "ans1": 0.0,
            "ans2": 0.0,
            "ans5": ans5,
            "ans6": ans6,
        })
        term_rows.extend([
            {
                "element_z": 8,
                "record": record,
                "data_type": 53,
                "rate_type": 7,
                "term_index": 2 * term_index - 1,
                "role": "forward_diag_loss",
                "python_cj2": ans6 * xpx,
                "xstar_cj2": ans6 * xpx,
                "topology_match": True,
            },
            {
                "element_z": 8,
                "record": record,
                "data_type": 53,
                "rate_type": 7,
                "term_index": 2 * term_index,
                "role": "reverse_diag_loss",
                "python_cj2": -ans5 * xpx,
                "xstar_cj2": -ans5 * xpx,
                "topology_match": True,
            },
        ])
    fixed = SimpleNamespace(
        hydrogen_density_cm3=xpx,
        element_results=[SimpleNamespace(
            request=SimpleNamespace(element_z=8),
            equilibrium=SimpleNamespace(
                assembly=SimpleNamespace(record_results=record_results)
            ),
        )],
    )
    same_call = SameCallMatrixParityResult(
        status="ready",
        ready=True,
        topology_ready=True,
        coefficient_ready=True,
        active_closure_ready=True,
        n_python_terms=len(term_rows),
        n_xstar_terms=len(term_rows),
        n_matched_terms=len(term_rows),
        n_topology_mismatches=0,
        n_coefficient_rows_outside_tolerance=0,
        n_active_rows_outside_tolerance=0,
        max_abs_aj1_difference=0.0,
        max_abs_aj2_difference=0.0,
        max_abs_cj_difference=0.0,
        max_abs_cj2_difference=0.0,
        term_rows=term_rows,
    )
    diagnosis = diagnose_rate7_cj2_records(fixed, same_call_matrix=same_call)
    assert diagnosis.type53_ready is True
    assert diagnosis.n_type53_records == 196
    assert diagnosis.n_type53_records_outside_tolerance == 0


def test_seven_type99_cached_points_preserve_stale_atmp22():
    rows = _read_csv("v0433_type99_ans5_rows.csv")
    assert len(rows) == 7
    for i, row in enumerate(rows, start=1):
        stale = float(i) * 1.25
        sgtmp, tempi, atmp2, atmp22 = _phint53hunt_reuse_cached_point(
            sgtmp=0.01 * i,
            atmp2=2.0 * i,
            epii=4.0 * i,
            stale_atmp22=stale,
        )
        assert sgtmp == pytest.approx(0.01 * i)
        assert tempi == pytest.approx(0.5)
        assert atmp2 == pytest.approx(2.0 * i)
        assert atmp22 == pytest.approx(stale)
        python_ans5 = float(row["python_ans5"])
        xstar_ans5 = float(row["xstar_ans5"])
        assert abs(python_ans5 - xstar_ans5) / abs(xstar_ans5) > 5.0e-3


def test_phint53hunt_full_quadrature_uses_cached_stale_atmp22():
    radiation = SimpleNamespace(
        epi_eV=np.geomspace(1.0, 2.0e4, 100),
        bremsa=np.geomspace(1.0e10, 1.0e5, 100),
        bremsint=np.zeros(100),
    )
    context = UCalcContext(
        temperature_k=76655.18557758832,
        hydrogen_density_cm3=1.0e8,
        electron_fraction_xee=1.2046560563936872,
        radiation=radiation,
    )
    result = _phint53hunt_exact(
        energy_above_threshold_ryd=np.geomspace(1.0e-4, 50.0, 50),
        cross_section_cm2=np.geomspace(1.0e-18, 1.0e-22, 50),
        threshold_ev=100.0,
        context=context,
        swrat=1.0,
    )
    assert result["type99_cached_atmp22_policy"] == "preserve_preceding_loop_value"
    assert result["type99_n_cached_atmp22_reuses"] == 14
    assert result["rrcl2"] == pytest.approx(9.460670173862706e-19, rel=1.0e-14)


def test_two_thermal_family_rows_close_with_corrected_type99_cooling2():
    remaining = _read_csv("v0433_thermal_family_remaining_rows.csv")
    assert {(row["family_dimension"], row["family_index"], row["thermal_channel"]) for row in remaining} == {
        ("data_type", "99", "cooling2"),
        ("rate_type", "7", "cooling2"),
    }
    corrected = 1.2345e-7
    closure = SimpleNamespace(elements=[SimpleNamespace(thermal_rows=[{
        "element_z": 8,
        "data_type": 99,
        "rate_type": 7,
        "thermal_channel": "cooling2",
        "python_contribution_per_abundance": corrected,
    }])])
    data_rows = [{
        "element_z": 8,
        "data_type": 99,
        "heating": 0.0,
        "cooling": 0.0,
        "heating2": 0.0,
        "cooling2": corrected,
    }]
    rate_rows = [{
        "element_z": 8,
        "rate_type": 7,
        "heating": 0.0,
        "cooling": 0.0,
        "heating2": 0.0,
        "cooling2": corrected,
    }]
    parity = compare_thermal_families(
        closure=closure,
        data_type_probe_rows=data_rows,
        rate_type_probe_rows=rate_rows,
        rtol=0.0,
        atol=0.0,
    )
    assert parity.ready is True
    targeted = [
        row for row in parity.rows
        if row["thermal_channel"] == "cooling2"
        and ((row["family_dimension"], row["family_index"]) in {("data_type", 99), ("rate_type", 7)})
    ]
    assert len(targeted) == 2
    assert all(row["within_tolerance"] for row in targeted)
