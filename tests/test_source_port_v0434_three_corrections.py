from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import csv

import numpy as np
import pytest

from xstar_atomic.source_port import FixedStateElementRequest, calc_hmc_all
from xstar_atomic.source_port.element_equilibrium import (
    ElementCompactBasis,
    ElementIonBlock,
    XSTAR_LEVELTEMP_NDL,
    _initialize_leveltemp_workspace_from_levwkelement,
    _overwrite_leveltemp_workspace,
)
from xstar_atomic.source_port.ucalc import (
    UCalcContext,
    UCalcLevel,
    UCalcLevelTable,
    _phint53hunt_exact,
)
from xstar_atomic.source_port.v0434_regression import (
    V0434_BASELINE_TARGET_COUNTS,
    assess_v0434_oxygen_correction_gates,
)


def _table(nlev: int, base: float) -> UCalcLevelTable:
    return UCalcLevelTable(
        levels={
            i: UCalcLevel(i, energy_ev=base + i, statistical_weight=1.0)
            for i in range(1, nlev + 1)
        },
        nlev=nlev,
    )


def _basis() -> ElementCompactBasis:
    dims = [79, 163, 53, 43, 241, 33]
    blocks = []
    start = 1
    for ion_index, (stage, nlev) in enumerate(zip(range(3, 9), dims), start=1):
        blocks.append(
            ElementIonBlock(
                ion_index=ion_index,
                ion_record=100 + ion_index,
                element_z=8,
                ion_stage=stage,
                nlev=nlev,
                compact_start=start,
                compact_stop=start + nlev - 1,
                first_level_record=1000 + ion_index,
                ion_counter=stage,
            )
        )
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


def test_leveltemp_is_complete_zero_initialized_ndl_workspace():
    basis = _basis()
    tables = {
        block.ion_index: _table(block.nlev, 1000.0 * block.ion_stage)
        for block in basis.blocks
    }
    workspace, owners, _ = _initialize_leveltemp_workspace_from_levwkelement(
        basis, tables
    )
    assert len(workspace.levels) == XSTAR_LEVELTEMP_NDL == 5000
    assert workspace.energy(241) == pytest.approx(7241.0)
    assert workspace.energy(242) == 0.0
    assert workspace.energy(5000) == 0.0
    assert owners[242]["phase"] == "initial_unwritten_zero"
    assert owners[242]["write_sequence"] == 0

    _overwrite_leveltemp_workspace(
        workspace,
        tables[1],
        owner_by_column=owners,
        owner_ion_index=1,
        owner_ion_stage=3,
        write_sequence=7,
        phase="calc_hmc_ion_second_pass",
    )
    assert workspace.energy(242) == 0.0
    assert owners[242]["phase"] == "initial_unwritten_zero"


def _pre_matrix(master, derived, *, element_z, context, critf, dispatcher=None):
    return (
        {1: SimpleNamespace(ready=True, pirti=1.0, rrrti=2.0, contributions=[], ion_index=1)},
        SimpleNamespace(n_rates=1, fractions=np.array([0.0, 1.0, 0.0])),
        SimpleNamespace(mml=1, mmu=1),
    )


def _element_with_distinct_lte_and_seed(master, derived, *, element_z, context, dispatcher=None):
    rows = [
        SimpleNamespace(compact_index=1, roles=[{"ion_stage": 1, "local_level": 1}]),
        SimpleNamespace(compact_index=2, roles=[{"ion_stage": 1, "local_level": 2}]),
    ]
    block = SimpleNamespace(
        ion_index=1,
        ion_stage=1,
        nlev=2,
        compact_index=lambda level: int(level),
        second_pass_pirt=0.0,
        second_pass_rrrt=0.0,
    )
    assembly = SimpleNamespace(
        basis=SimpleNamespace(rows=rows, blocks=[block]),
        # Same-call xileve replay used by msolvelucy.
        initial_populations=np.array([0.0, 0.25, 0.75]),
        # Independent levwkelement rnise used by rnisg/bilevg.
        lte_populations=np.array([0.0, 0.8, 0.2]),
        ion_summaries=[block],
        record_results=[],
    )
    solve = SimpleNamespace(
        heating=0.0,
        cooling=0.0,
        heating2=0.0,
        cooling2=0.0,
        ion_population_totals=np.array([1.0]),
        ionization_totals=np.array([0.0]),
        recombination_totals=np.array([0.0]),
        ionization_components=np.zeros((5, 1)),
        recombination_components=np.zeros((5, 1)),
        populations=np.array([0.4, 0.6]),
        gamma=np.zeros(2),
        alpha=np.zeros(2),
        fgamma=np.zeros((5, 2)),
        falpha=np.zeros((5, 2)),
        igammamax_record=np.zeros(2, dtype=int),
        ialphamax_record=np.zeros(2, dtype=int),
    )
    return SimpleNamespace(
        assembly=assembly,
        solve=solve,
        full_element_direct_solve_ready=True,
    )


def test_rnise_lte_remains_distinct_from_same_call_solver_seed():
    derived = SimpleNamespace(
        n_ions=1,
        ion_records=np.array([0, 11]),
        ion_element_z=np.array([0, 1]),
        ion_stage=np.array([0, 1]),
        nlevs=np.array([0, 2]),
        npilev=np.array([[0, 0], [0, 10], [0, 11]]),
        element_records=np.array([0]),
    )
    result = calc_hmc_all(
        object(),
        derived,
        elements=[FixedStateElementRequest(1, 1, 1, abundance=1.0)],
        temperature_k=1.0e6,
        hydrogen_density_cm3=1.0e8,
        electron_fraction_xee=1.0,
        element_solver=_element_with_distinct_lte_and_seed,
        pre_matrix_solver=_pre_matrix,
    )
    assert result.rnisg[(1, 1, 1)] == pytest.approx(0.8)
    assert result.rnisg[(1, 1, 2)] == pytest.approx(0.2)
    assert result.bilevg[(1, 1, 1)] == pytest.approx(0.4 / (0.8 + 1.0e-37))
    assert result.bilevg[(1, 1, 2)] == pytest.approx(0.6 / (0.2 + 1.0e-48))


def test_phint53hunt_preserves_cached_branch_stale_atmp22():
    epi = np.geomspace(1.0, 1.0e4, 100)
    radiation = SimpleNamespace(
        epim_eV=epi,
        bremsam=np.geomspace(1.0e-3, 1.0e-6, 100),
        bremsint=np.zeros(100),
    )
    result = _phint53hunt_exact(
        energy_above_threshold_ryd=[0.01, 0.1, 1.0, 10.0, 100.0],
        cross_section_cm2=[1.0e-18, 8.0e-19, 5.0e-19, 2.0e-19, 1.0e-20],
        threshold_ev=20.0,
        context=UCalcContext(
            temperature_k=7.6655e4,
            hydrogen_density_cm3=1.0e8,
            electron_fraction_xee=1.2,
            radiation=radiation,
        ),
        swrat=2.0,
        crit=0.01,
    )
    assert result["status"] == "evaluated_phint53hunt_live_grid"
    assert result["type99_phint53hunt_cached_atmp22_policy"] == "preserve_stale_previous_loop_value"
    assert result["n_cached_atmp22_stale_reuses"] == 30
    assert result["rrcl2"] == pytest.approx(4.35300317986006e-17, rel=1.0e-13)


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_v0434_focused_regression_gate_counts(tmp_path: Path):
    parity_rows = [
        {
            "component": "global_level_rnisg",
            "within_tolerance": "False",
            "milestone_blocking": "True",
        }
        for _ in range(35)
    ] + [
        {
            "component": "global_level_bilevg",
            "within_tolerance": "False",
            "milestone_blocking": "False",
        }
        for _ in range(349)
    ]
    _write_csv(
        tmp_path / "xstar_calc_hmc_all_pre_continuum_parity_details.csv",
        ["component", "within_tolerance", "milestone_blocking"],
        parity_rows,
    )

    leveltemp_rows = [
        {
            "data_type": "53",
            "within_tolerance": "False",
            "python_ans5": "0",
            "xstar_ans5": "0",
        }
        for _ in range(205)
    ] + [
        {
            "data_type": "99",
            "within_tolerance": "True",
            "python_ans5": "1",
            "xstar_ans5": "2",
        }
        for _ in range(7)
    ]
    _write_csv(
        tmp_path / "xstar_calc_hmc_all_leveltemp_energy_parity.csv",
        ["data_type", "within_tolerance", "python_ans5", "xstar_ans5"],
        leveltemp_rows,
    )

    _write_csv(
        tmp_path / "xstar_calc_hmc_all_rate7_cj2_record_summary.csv",
        ["data_type", "within_tolerance"],
        [{"data_type": "53", "within_tolerance": "False"} for _ in range(196)],
    )
    _write_csv(
        tmp_path / "xstar_calc_hmc_all_xstar_thermal_family_parity.csv",
        ["within_tolerance"],
        [{"within_tolerance": "False"} for _ in range(2)],
    )

    result = assess_v0434_oxygen_correction_gates(tmp_path)
    assert result.counts == V0434_BASELINE_TARGET_COUNTS
    assert result.baseline_target_match is True
    assert result.closure_ready is False


def test_frozen_v0433_production_target_manifest_matches_requested_counts():
    import json

    root = Path(__file__).resolve().parents[1]
    payload = json.loads(
        (root / "benchmarks" / "oxygen_v0434_correction_targets" /
         "v0433_baseline_target_gate.json").read_text(encoding="utf-8")
    )
    assert payload["counts"] == V0434_BASELINE_TARGET_COUNTS
    assert payload["baseline_target_match"] is True
    assert payload["closure_ready"] is False
