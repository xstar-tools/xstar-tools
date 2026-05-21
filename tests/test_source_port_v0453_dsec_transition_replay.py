from __future__ import annotations

from types import SimpleNamespace
import importlib

import numpy as np
import pytest

from xstar_atomic.source_port import (
    CalcHMCAllDsecEvaluator,
    DsecMatchingInputState,
    DsecMutableRuntimeState,
    EscapeProbabilityContext,
    FixedStateElementRequest,
    UCalcLevel,
    UCalcLevelTable,
    apply_dsec_matching_input_state,
)
from xstar_atomic.xstar_live_rate_grid_probe import LiveRateGridState


def _matching_state() -> DsecMatchingInputState:
    radiation = LiveRateGridState(
        zone_index=-1,
        pass_index=-1,
        ldir=0,
        ncn2m=2,
        epim_eV=(1.0, 2.0),
        bremsam=(3.0, 4.0),
        bremsint=(5.0, 6.0),
        metadata={},
    )
    escape = EscapeProbabilityContext(
        line_tau_in=np.array([0.1]),
        line_tau_out=np.array([0.2]),
        continuum_tau_in=np.array([0.3]),
        continuum_tau_out=np.array([0.4]),
        allow_missing_as_zero=False,
    )
    leveltemp = UCalcLevelTable(
        levels={1: UCalcLevel(index=1, energy_ev=12.0, statistical_weight=3.0)},
        nlev=1,
    )
    return DsecMatchingInputState(
        calc_hmc_all_call_id=2,
        dsec_call_id=1,
        dsec_evaluation_index=2,
        phase="dsec_internal",
        temperature_t4=100.0,
        trad=0.0,
        radius_cm=1.5e18,
        zone_thickness_cm=2.5e15,
        electron_fraction_xee=1.2,
        hydrogen_density_cm3=1.0e8,
        covering_fraction=0.7,
        pressure=0.03,
        lcdd=1,
        zeta=0.0,
        turbulent_velocity_km_s=100.0,
        critf=1.0e-7,
        ncn2=2,
        radiation=radiation,
        escape=escape,
        global_level_values_by_index=np.array([0.25, 0.75]),
        global_bilev_values_by_index=np.array([2.5, 7.5]),
        global_rnist_values_by_index=np.array([0.1, 0.2]),
        leveltemp_workspace=leveltemp,
        leveltemp_snapshot=None,
        source_dir="probe",
    )


def test_apply_exact_transition_state_replaces_all_replayed_inputs() -> None:
    state = DsecMutableRuntimeState(
        temperature_t4=90.0,
        electron_fraction_xee=1.0,
        hydrogen_density_cm3=2.0e8,
        element_requests=(FixedStateElementRequest(8, 1, 2),),
        global_level_populations={},
        global_xilevg_by_index=np.zeros(2),
        global_bilevg_by_index=np.zeros(2),
        global_rnisg_by_index=np.zeros(2),
        global_level_index_by_key={(8, 1, 1): 1, (8, 2, 1): 2},
    )
    info = apply_dsec_matching_input_state(
        state,
        _matching_state(),
        opakc_before_cm_inv=np.array([8.0, 9.0]),
        brcems_before=np.array([10.0, 11.0]),
    )

    assert state.temperature_t4 == pytest.approx(100.0)
    assert state.electron_fraction_xee == pytest.approx(1.2)
    assert state.hydrogen_density_cm3 == pytest.approx(1.0e8)
    assert state.global_xilevg_by_index.tolist() == pytest.approx([0.25, 0.75])
    assert state.global_bilevg_by_index.tolist() == pytest.approx([2.5, 7.5])
    assert state.global_rnisg_by_index.tolist() == pytest.approx([0.1, 0.2])
    assert state.global_level_populations[(8, 1, 1)] == pytest.approx(0.25)
    assert state.global_level_populations[(8, 2, 1)] == pytest.approx(0.75)
    assert state.leveltemp_workspace.require(1).energy_ev == pytest.approx(12.0)
    assert state.leveltemp_owner_by_column == {}
    assert state.work_arrays["opakc"].tolist() == pytest.approx([8.0, 9.0])
    assert state.work_arrays["brcems"].tolist() == pytest.approx([10.0, 11.0])
    request = state.element_requests[0]
    assert request.covering_fraction == pytest.approx(0.7)
    assert request.turbulent_velocity_km_s == pytest.approx(100.0)
    assert request.radiation.bremsint == pytest.approx((5.0, 6.0))
    assert info["evaluation_index"] == 2
    assert info["n_nonzero_xilevg"] == 2
    assert state.provenance["diagnostic_exact_xstar_transition_replay"]


def test_pre_evaluation_callback_runs_before_context_factory(monkeypatch) -> None:
    observed = []

    def pre(index, state):
        assert index == 1
        state.electron_fraction_xee = 1.2

    def factory(state):
        observed.append(state.electron_fraction_xee)
        return {}

    fake = SimpleNamespace(
        temperature_k=1.0e6,
        electron_fraction_xee=1.2,
        hydrogen_density_cm3=1.0e8,
        element_results=(),
        global_xilevg_by_index=np.zeros(0),
        global_bilevg_by_index=np.zeros(0),
        global_rnisg_by_index=np.zeros(0),
        global_level_index_by_key={},
        xilevg={},
        ion_fractions={},
        rrrt={},
        pirt={},
        htt={},
        cll={},
        htt2={},
        cll2={},
        rnisg={},
        bilevg={},
        gammag={},
        alphag={},
        stotg={},
        atotg={},
        xtotg={},
        leveltemp_workspace=None,
        leveltemp_owner_by_column={},
        continuum=SimpleNamespace(opakc=None, brcems=None),
        hmctot=-0.5,
        elcter=0.0,
        complete_fixed_state_ready=True,
    )

    def fake_calc(*args, **kwargs):
        return fake

    dsec_module = importlib.import_module("xstar_atomic.source_port.dsec")
    monkeypatch.setattr(dsec_module, "calc_hmc_all", fake_calc)
    evaluator = CalcHMCAllDsecEvaluator(
        master=object(),
        derived=object(),
        calc_kwargs_factory=factory,
        pre_evaluation_callback=pre,
    )
    state = DsecMutableRuntimeState(
        100.0,
        1.0,
        1.0e8,
        element_requests=(FixedStateElementRequest(8, 1, 1),),
        global_level_populations={},
    )
    result = evaluator(state)
    assert observed == [pytest.approx(1.2)]
    assert result.hmctot == pytest.approx(-0.5)


def test_exact_transition_replay_helper_is_public_at_top_level() -> None:
    import xstar_atomic as xa

    assert xa.apply_dsec_matching_input_state is apply_dsec_matching_input_state
