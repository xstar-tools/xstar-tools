from __future__ import annotations

import csv
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from xstar_atomic.source_port import (
    DsecCalcHMCAllInputSnapshot,
    DsecLevelTempSnapshot,
    DsecMatchingInputState,
    EscapeProbabilityContext,
    UCalcLevel,
    UCalcLevelTable,
    compare_dsec_transition_state,
    load_dsec_matching_input_state,
)
from xstar_atomic.xstar_live_rate_grid_probe import LiveRateGridState


def _radiation() -> LiveRateGridState:
    return LiveRateGridState(
        zone_index=-1,
        pass_index=-1,
        ldir=0,
        ncn2m=2,
        epim_eV=(10.0, 20.0),
        bremsam=(3.0, 4.0),
        bremsint=(7.0, 4.0),
        metadata={},
    )


def _escape() -> EscapeProbabilityContext:
    return EscapeProbabilityContext(
        line_tau_in=np.array([0.1, 0.2]),
        line_tau_out=np.array([0.3, 0.4]),
        continuum_tau_in=np.array([0.5]),
        continuum_tau_out=np.array([0.6]),
        allow_missing_as_zero=False,
    )


def _snapshot(xilev: float = 0.25) -> DsecCalcHMCAllInputSnapshot:
    level = UCalcLevel(
        index=1,
        energy_ev=12.0,
        statistical_weight=3.0,
        ionization_potential_ev=99.0,
        principal_n=2,
        orbital_l=1,
    )
    return DsecCalcHMCAllInputSnapshot(
        evaluation_index=2,
        temperature_t4=100.0,
        temperature_k=1.0e6,
        electron_fraction_xee=1.2,
        hydrogen_density_cm3=1.0e8,
        pressure=0.0,
        lcdd=1,
        covering_fraction=1.0,
        turbulent_velocity_km_s=0.0,
        critf=1.0e-6,
        global_level_populations={(8, 8, 1): xilev},
        global_bilev_values={(8, 8, 1): 2.5},
        global_rnist_values={(8, 8, 1): 0.1},
        global_level_index_by_key={(8, 8, 1): 1},
        leveltemp_workspace=UCalcLevelTable(levels={1: level}, nlev=1),
        leveltemp_owner_by_column={1: {"phase": "second_pass", "ion_index": 8}},
        radiation=_radiation(),
        escape=_escape(),
        calc_kwargs={
            "heatf_context": SimpleNamespace(radius_cm=1.0e16, zone_thickness_cm=2.0e12),
            "free_free_context": SimpleNamespace(opakc_before_cm_inv=np.array([0.01, 0.02])),
            "bremem_context": SimpleNamespace(brcems_before=np.array([0.03, 0.04])),
        },
    )


def _xstar(xilev: float = 0.25) -> DsecMatchingInputState:
    rlev = np.zeros((10, 1), dtype=float)
    ilev = np.zeros((10, 1), dtype=int)
    rlev[0, 0] = 12.0
    rlev[1, 0] = 3.0
    rlev[3, 0] = 99.0
    ilev[0, 0] = 2
    ilev[2, 0] = 1
    return DsecMatchingInputState(
        calc_hmc_all_call_id=2,
        dsec_call_id=1,
        dsec_evaluation_index=2,
        phase="dsec_internal",
        temperature_t4=100.0,
        trad=0.0,
        radius_cm=1.0e16,
        zone_thickness_cm=2.0e12,
        electron_fraction_xee=1.2,
        hydrogen_density_cm3=1.0e8,
        covering_fraction=1.0,
        pressure=0.0,
        lcdd=1,
        zeta=0.0,
        turbulent_velocity_km_s=0.0,
        critf=1.0e-6,
        ncn2=2,
        radiation=_radiation(),
        escape=_escape(),
        global_level_values_by_index=np.array([xilev]),
        global_bilev_values_by_index=np.array([2.5]),
        global_rnist_values_by_index=np.array([0.1]),
        leveltemp_workspace=UCalcLevelTable(),
        leveltemp_snapshot=DsecLevelTempSnapshot(
            rlev=rlev,
            ilev=ilev,
            nlpt=np.array([17]),
            iltp=np.array([13]),
        ),
        source_dir="synthetic-eval2",
    )


def test_eval2_transition_state_parity_passes_for_exact_state() -> None:
    result = compare_dsec_transition_state(
        _snapshot(),
        _xstar(),
        xstar_opakc_before_cm_inv=[0.01, 0.02],
        xstar_brcems_before=[0.03, 0.04],
    )
    assert result.ready
    assert result.runtime_state_ready
    assert result.global_xilevg_ready
    assert result.global_bilevg_ready
    assert result.global_rnisg_ready
    assert result.leveltemp_source_used_slots_ready


def test_eval2_transition_state_identifies_global_population_mismatch() -> None:
    result = compare_dsec_transition_state(_snapshot(xilev=0.2), _xstar(xilev=0.25))
    assert not result.ready
    assert not result.global_xilevg_ready
    mismatches = [
        row for row in result.rows
        if row.category == "global_levels" and row.quantity == "xilevg" and not row.within_tolerance
    ]
    assert len(mismatches) == 1
    assert mismatches[0].index == 1



def test_eval2_transition_state_identifies_continuum_workspace_mismatch() -> None:
    result = compare_dsec_transition_state(
        _snapshot(),
        _xstar(),
        xstar_opakc_before_cm_inv=[0.01, 9.0],
        xstar_brcems_before=[0.03, 0.04],
    )
    assert not result.ready
    assert not result.continuum_workspace_ready
    mismatches = [
        row for row in result.rows
        if row.category == "continuum_workspace" and not row.within_tolerance
    ]
    assert len(mismatches) == 1
    assert mismatches[0].quantity == "opakc_before_cm_inv"
    assert mismatches[0].index == 2

def _write(path: Path, header: list[str], rows: list[list[object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def test_matching_loader_preserves_all_leveltemp_slots_and_ilev3(tmp_path: Path) -> None:
    _write(
        tmp_path / "xstar_calc_hmc_all_input_summary_probe.csv",
        [
            "calc_hmc_all_call_id", "dsec_call_id", "dsec_evaluation_index",
            "phase", "temperature_t4", "temperature_k", "trad", "radius_cm",
            "zone_thickness_cm", "electron_fraction_xee", "hydrogen_density_cm3",
            "covering_fraction", "pressure", "lcdd", "zeta",
            "turbulent_velocity_km_s", "critf", "ncn2",
        ],
        [[2, 1, 2, "dsec_internal", 100.0, 1.0e6, 0.0, 1.0e16, 1.0e12,
          1.2, 1.0e8, 1.0, 0.0, 1, 0.0, 0.0, 1.0e-6, 2]],
    )
    _write(
        tmp_path / "xstar_calc_hmc_all_input_continuum_probe.csv",
        ["calc_hmc_all_call_id", "grid_index", "ncn2", "epi_eV", "bremsa", "bremsint"],
        [[2, 1, 2, 10.0, 3.0, 7.0], [2, 2, 2, 20.0, 4.0, 4.0]],
    )
    _write(tmp_path / "xstar_calc_hmc_all_input_tau0_probe.csv",
           ["calc_hmc_all_call_id", "line_index", "tau_in", "tau_out"], [[2, 1, 0.1, 0.2]])
    _write(tmp_path / "xstar_calc_hmc_all_input_tauc_probe.csv",
           ["calc_hmc_all_call_id", "continuum_index", "tau_in", "tau_out"], [[2, 1, 0.3, 0.4]])
    _write(tmp_path / "xstar_calc_hmc_all_input_global_levels_probe.csv",
           ["calc_hmc_all_call_id", "global_level_index", "xilevg", "bilevg", "rnisg"], [[2, 1, 0.2, 2.0, 0.1]])
    level_rows = []
    for slot in range(1, 11):
        level_rows.append([2, 1, slot, float(slot), slot * 10, 123, 13])
    _write(
        tmp_path / "xstar_calc_hmc_all_input_leveltemp_probe.csv",
        ["calc_hmc_all_call_id", "column_index", "slot", "rlev", "ilev", "nlpt", "iltp"],
        level_rows,
    )
    state = load_dsec_matching_input_state(tmp_path, call_id=2)
    assert state.leveltemp_snapshot is not None
    assert state.leveltemp_snapshot.rlev[9, 0] == 10.0
    assert state.leveltemp_snapshot.ilev[9, 0] == 100
    assert state.leveltemp_snapshot.nlpt[0] == 123
    assert state.leveltemp_snapshot.iltp[0] == 13
    assert state.leveltemp_workspace is not None
    # UCalc source uses ilev(3), not ilev(2), for orbital l.
    assert state.leveltemp_workspace.require(1).orbital_l == 30


def test_physical_evaluator_captures_only_requested_transition_snapshot(monkeypatch) -> None:
    from xstar_atomic.source_port import CalcHMCAllDsecEvaluator
    import importlib
    dsec_module = importlib.import_module("xstar_atomic.source_port.dsec")

    request = SimpleNamespace(
        radiation=_radiation(),
        escape=_escape(),
        covering_fraction=1.0,
        turbulent_velocity_km_s=0.0,
        critf=1.0e-6,
    )

    class FakeState:
        temperature_t4 = 100.0
        temperature_k = 1.0e6
        electron_fraction_xee = 1.0
        hydrogen_density_cm3 = 1.0e8
        pressure = 0.0
        lcdd = 1
        required_element_z = (1, 2, 8)
        leveltemp_workspace = None
        leveltemp_owner_by_column = {}
        global_level_populations = {}
        source_arrays = {"bilevg": {}, "rnisg": {}}
        last_calc_hmc_all = None
        calc_hmc_all_call_count = 0

        def requests_for_next_call(self):
            return (request,)

        def commit_calc_hmc_all(self, result):
            self.last_calc_hmc_all = result
            self.calc_hmc_all_call_count += 1

    fake_result = SimpleNamespace(
        hmctot=-1.0,
        elcter=-0.5,
        complete_fixed_state_ready=True,
        global_level_index_by_key={},
    )
    monkeypatch.setattr(dsec_module, "calc_hmc_all", lambda *args, **kwargs: fake_result)

    state = FakeState()
    evaluator = CalcHMCAllDsecEvaluator(
        master=object(),
        derived=object(),
        capture_input_snapshot_indices=(2,),
    )
    evaluator(state)
    assert evaluator.input_snapshots == []
    evaluator(state)
    assert [item.evaluation_index for item in evaluator.input_snapshots] == [2]
