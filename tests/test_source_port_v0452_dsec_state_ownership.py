from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from xstar_atomic.source_port import (
    CalcIonRatesResult,
    DsecMutableRuntimeState,
    FixedStateElementRequest,
    IonStageLimitResult,
    IoneqmResult,
    IstrucResult,
    UCalcLevel,
    UCalcLevelTable,
    calc_hmc_all,
)


class _Block:
    ion_stage = 2
    nlev = 2
    ion_counter = 2
    ion_index = 2

    @staticmethod
    def compact_index(local_level: int) -> int:
        return int(local_level)


def _element_solver(master, derived, *, element_z, context, dispatcher=None):
    block = _Block()
    rows = [
        SimpleNamespace(
            compact_index=1,
            roles=[{"ion_index": 2, "ion_stage": 2, "local_level": 1}],
        ),
        SimpleNamespace(
            compact_index=2,
            roles=[{"ion_index": 2, "ion_stage": 2, "local_level": 2}],
        ),
    ]
    basis = SimpleNamespace(blocks=[block], rows=rows, n_rows=2)
    assembly = SimpleNamespace(
        basis=basis,
        initial_populations=np.array([0.0, 0.8, 0.2]),
        lte_populations=np.array([0.0, 0.8, 0.2]),
        leveltemp_workspace_final=None,
        leveltemp_owner_by_column={},
    )
    solve = SimpleNamespace(
        heating=0.0,
        cooling=0.0,
        heating2=0.0,
        cooling2=0.0,
        ion_population_totals=np.array([0.0, 0.7]),
        ion_population_totals_final_vector=np.array([0.0, 0.7]),
        recombination_totals=np.array([0.0, 2.0]),
        ionization_totals=np.array([0.0, 3.0]),
        ionization_components=np.zeros((3, 2)),
        recombination_components=np.zeros((3, 2)),
        populations=np.array([0.7, 0.3]),
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


def _pre_matrix_solver(master, derived, *, element_z, context, critf, dispatcher=None):
    rates = {
        1: CalcIonRatesResult(1, 11, element_z, 1, 1, 3.0, 2.0, ready=True),
        2: CalcIonRatesResult(2, 12, element_z, 2, 2, 3.0, 2.0, ready=True),
    }
    solved = IoneqmResult(
        fractions=np.array([0.0, 0.0, 0.7, 0.3]),
        q_ratio=np.array([1.0, 1.0]),
        jmax=2,
        mmn=2,
        mmx=2,
    )
    preliminary = IstrucResult(
        ionization_rates=np.array([0.0, 3.0, 3.0]),
        recombination_rates=np.array([0.0, 2.0, 2.0]),
        fractions=np.array([0.0, 0.0, 0.7, 0.3]),
        ioneqm=solved,
    )
    limits = IonStageLimitResult(2, 2, critf, 2, 2, 2)
    return rates, preliminary, limits


def _derived_two_ion_alias():
    npilev = np.zeros((3, 3), dtype=int)
    npilev[1, 1] = 1
    npilev[2, 1] = 2
    npilev[1, 2] = 3
    npilev[2, 2] = 4
    return SimpleNamespace(
        n_ions=2,
        ion_records=np.array([0, 11, 12]),
        ion_stage=np.array([0, 1, 2]),
        ion_element_z=np.array([0, 8, 8]),
        nlevs=np.array([0, 2, 2]),
        npilev=npilev,
        element_records=np.zeros(1, dtype=int),
    )


def test_dense_source_writeback_duplicates_lower_continuum_and_next_ground() -> None:
    result = calc_hmc_all(
        object(),
        _derived_two_ion_alias(),
        elements=[FixedStateElementRequest(8, 2, 2, abundance=1.0)],
        temperature_k=1.0e6,
        hydrogen_density_cm3=1.0e8,
        electron_fraction_xee=1.4,
        element_solver=_element_solver,
        pre_matrix_solver=_pre_matrix_solver,
        source_global_alias_writeback=True,
    )

    assert result.global_xilevg_by_index.tolist() == pytest.approx([0.0, 0.7, 0.7, 0.3])
    assert result.global_rnisg_by_index.tolist() == pytest.approx([0.0, 0.8, 0.8, 0.2])
    assert result.global_bilevg_by_index[1] == pytest.approx(0.7 / (0.8 + 1.0e-48))
    assert result.global_bilevg_by_index[2] == pytest.approx(0.7 / (0.8 + 1.0e-37))
    assert result.xilevg[(8, 1, 2)] == pytest.approx(0.7)
    assert result.xilevg[(8, 2, 1)] == pytest.approx(0.7)


def test_dense_global_state_is_mapped_back_to_next_compact_request() -> None:
    request = FixedStateElementRequest(8, 2, 2)
    state = DsecMutableRuntimeState(
        temperature_t4=100.0,
        electron_fraction_xee=1.0,
        hydrogen_density_cm3=1.0e8,
        element_requests=(request,),
        global_xilevg_by_index=np.array([0.0, 0.7, 0.7, 0.3]),
        global_bilevg_by_index=np.zeros(4),
        global_rnisg_by_index=np.zeros(4),
        global_level_index_by_key={(8, 1, 2): 2, (8, 2, 1): 3, (8, 2, 2): 4},
    )
    next_request = state.requests_for_next_call()[0]
    assert next_request.initial_populations is None
    assert next_request.initial_global_populations[(8, 1, 2)] == pytest.approx(0.7)
    assert next_request.initial_global_populations[(8, 2, 1)] == pytest.approx(0.7)
    assert next_request.initial_population_source == "xstar_init_zero_dense_global_xilevg"


def test_leveltemp_reset_policy_preserves_entry_state_and_records_last_workspace() -> None:
    entry = UCalcLevelTable(levels={1: UCalcLevel(index=1)}, nlev=0)
    final = UCalcLevelTable(
        levels={1: UCalcLevel(index=1, energy_ev=12.0, statistical_weight=3.0)},
        nlev=1,
    )
    state = DsecMutableRuntimeState(
        100.0,
        1.0,
        1.0e8,
        global_level_populations={},
        leveltemp_workspace=entry,
        reset_leveltemp_each_calc_hmc_all=True,
    )
    result = SimpleNamespace(
        temperature_k=1.0e6,
        electron_fraction_xee=1.2,
        hydrogen_density_cm3=1.0e8,
        element_results=(),
        xilevg={}, ion_fractions={}, rrrt={}, pirt={}, htt={}, cll={}, htt2={}, cll2={},
        rnisg={}, bilevg={}, gammag={}, alphag={}, stotg={}, atotg={}, xtotg={},
        leveltemp_workspace=final,
        leveltemp_owner_by_column={1: {"phase": "second_pass"}},
        continuum=SimpleNamespace(opakc=None, brcems=None),
        global_level_index_by_key={},
    )
    state.commit_calc_hmc_all(result)
    assert state.leveltemp_workspace.require(1).energy_ev == 0.0
    assert state.last_leveltemp_workspace.require(1).energy_ev == pytest.approx(12.0)
    assert state.last_leveltemp_owner_by_column[1]["phase"] == "second_pass"
