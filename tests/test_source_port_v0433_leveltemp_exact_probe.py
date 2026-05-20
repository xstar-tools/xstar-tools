from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path
import shutil
import subprocess

import pytest
import numpy as np

from xstar_atomic.source_port import (
    ElementCompactBasis,
    compare_leveltemp_energy_probe,
    UCalcLevel,
    UCalcLevelTable,
    load_msolvelucy_initial_population_reference,
    compare_msolvelucy_initial_population,
)
from xstar_atomic.source_port.element_equilibrium import (
    ElementIonBlock,
    _initialize_leveltemp_workspace_from_levwkelement,
    _overwrite_leveltemp_workspace,
)
from xstar_atomic.xstar_calc_hmc_all_probe import (
    calc_hmc_all_insertion_snippets,
    calc_hmc_all_probe_helper,
    write_calc_hmc_all_probe_products,
)


def _table(nlev: int, base: float) -> UCalcLevelTable:
    return UCalcLevelTable(
        levels={
            i: UCalcLevel(i, energy_ev=base + float(i), statistical_weight=1.0)
            for i in range(1, nlev + 1)
        },
        nlev=nlev,
    )


def _basis() -> ElementCompactBasis:
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


def test_levwkelement_replay_builds_composite_retained_workspace():
    basis = _basis()
    tables = {
        block.ion_index: _table(block.nlev, 1000.0 * block.ion_stage)
        for block in basis.blocks
    }
    workspace, owners, trace = _initialize_leveltemp_workspace_from_levwkelement(
        basis, tables
    )
    # O VIII is last but has only 33 levels.  Higher columns must still hold
    # O VII values from the preceding 241-level write.
    assert workspace.nlev == 33
    assert workspace.energy(1) == pytest.approx(8001.0)
    assert workspace.energy(33) == pytest.approx(8033.0)
    assert workspace.energy(34) == pytest.approx(7034.0)
    assert workspace.energy(241) == pytest.approx(7241.0)
    assert owners[34]["ion_stage"] == 7
    assert owners[241]["ion_stage"] == 7
    assert len(trace) == 6

    # The first second-pass O III write replaces 1:79 but preserves 80:241.
    _overwrite_leveltemp_workspace(
        workspace,
        tables[1],
        owner_by_column=owners,
        owner_ion_index=1,
        owner_ion_stage=3,
        write_sequence=7,
        phase="calc_hmc_ion_second_pass",
    )
    assert workspace.nlev == 79
    assert workspace.energy(79) == pytest.approx(3079.0)
    assert workspace.energy(80) == pytest.approx(7080.0)
    assert owners[79]["ion_stage"] == 3
    assert owners[80]["ion_stage"] == 7


def _fixed_record_row():
    row = {
        "record": 17123,
        "data_type": 53,
        "rate_type": 7,
        "status": "evaluated",
        "ion_index": 12,
        "ion_stage": 4,
        "nlev": 163,
        "idest1": 1,
        "idest2": 180,
        "leveltemp_idest1_energy_ev": 0.0,
        "leveltemp_idest2_energy_ev": 7180.0,
        "leveltemp_idest2_owner_ion_index": 15,
        "leveltemp_idest2_owner_ion_stage": 7,
        "leveltemp_idest2_owner_nlev": 241,
        "leveltemp_idest2_owner_write_sequence": 5,
        "leveltemp_idest2_owner_phase": "levwkelement",
        "leveltemp_workspace_write_sequence": 8,
        "leveltemp_workspace_max_column": 241,
        "ans1": 1.0,
        "ans2": 2.0,
        "ans3": 3.0,
        "ans4": 4.0,
        "ans5": 5.0,
        "ans6": 6.0,
    }
    assembly = SimpleNamespace(record_results=[row])
    element = SimpleNamespace(
        request=SimpleNamespace(element_z=8),
        equilibrium=SimpleNamespace(assembly=assembly),
    )
    return SimpleNamespace(element_results=[element])


def test_exact_leveltemp_probe_compares_source_read_not_physical_reconstruction():
    probe = [{
        "calc_hmc_all_call_id": 73,
        "element_z": 8,
        "ion_stage": 4,
        "ion_index": 12,
        "record": 17123,
        "data_type": 53,
        "rate_type": 7,
        "nlev": 163,
        "idest1": 1,
        "idest2": 180,
        "leveltemp_e1_ev": "0.0000000000000000E+000",
        "leveltemp_e2_ev": "7.1800000000000000E+003",
        "ans1": 1.0,
        "ans2": 2.0,
        "ans3": 3.0,
        "ans4": 4.0,
        "ans5": 5.0,
        "ans6": 6.0,
    }]
    result = compare_leveltemp_energy_probe(_fixed_record_row(), probe_rows=probe)
    assert result.ready is True
    assert result.type53_ready is True
    assert result.rows[0]["python_leveltemp_e2_owner_ion_stage"] == 7

    bad = [dict(probe[0], leveltemp_e2_ev=999.0)]
    result = compare_leveltemp_energy_probe(_fixed_record_row(), probe_rows=bad)
    assert result.ready is False
    assert result.type53_ready is False
    assert result.n_type53_energy_outside_tolerance == 1
    assert result.type53_trace_rows[-1]["event_kind"] == "xstar_python_comparison"
    assert result.type53_trace_rows[-1]["target_record"] == 17123


def test_missing_exact_leveltemp_probe_is_not_accepted():
    result = compare_leveltemp_energy_probe(_fixed_record_row(), probe_rows=[])
    assert result.ready is None
    assert result.type53_ready is None
    assert result.status == "not_comparable_missing_leveltemp_energy_probe"


def test_v0433_probe_adds_calc_hmc_ion_exact_leveltemp_hook_and_compiles(tmp_path: Path):
    snippets = calc_hmc_all_insertion_snippets()
    assert len(snippets) == 9
    snippet = snippets["calc_hmc_ion_leveltemp_energy"]
    assert "after call ucalc" in snippet
    assert "leveltemp%rlev(1,idest2)" in snippet
    assert "ltyp.eq.49" in snippet and "ltyp.eq.53" in snippet and "ltyp.eq.99" in snippet
    helper = calc_hmc_all_probe_helper()
    assert "xstar_calc_hmc_all_leveltemp_energy_probe.csv" in helper
    assert "XSTAR_ATOMIC_HMC_TARGET_RECORD" in helper

    paths = write_calc_hmc_all_probe_products(tmp_path)
    assert paths["calc_hmc_ion_leveltemp_energy_insertion"].exists()
    compiler = shutil.which("gfortran")
    if compiler:
        subprocess.run(
            [compiler, "-c", str(paths["helper_fortran"]), "-o", str(tmp_path / "probe.o")],
            check=True,
        )


def test_same_call_initial_population_probe_loads_complete_vector_without_rescaling(tmp_path: Path):
    path = tmp_path / "xstar_calc_hmc_all_msolvelucy_initial_population_probe.csv"
    path.write_text(
        "calc_hmc_all_call_id,element_index,element_z,compact_dimension,compact_index,population\n"
        "73,5,8,3,1,2.0000000000000000E-001\n"
        "73,5,8,3,2,3.0000000000000000E-001\n"
        "73,5,8,3,3,4.0000000000000000E-001\n"
    )
    reference = load_msolvelucy_initial_population_reference(
        tmp_path, element_z=8, call_id=73
    )
    assert reference.compact_dimension == 3
    assert reference.population_sum == pytest.approx(0.9)
    assert np.allclose(reference.populations, [0.2, 0.3, 0.4])

    parity = compare_msolvelucy_initial_population(
        np.array([0.0, 0.2, 0.3, 0.4]), reference, rtol=0.0, atol=0.0
    )
    assert parity.ready is True
    assert parity.n_outside_tolerance == 0


def test_v0433_matrix_hook_writes_complete_initial_population_vector():
    helper = calc_hmc_all_probe_helper()
    assert "xstar_calc_hmc_all_msolvelucy_initial_population_probe.csv" in helper
    assert "do ll=1,ipmat" in helper
    assert "ipmat, ll, x(ll)" in helper
