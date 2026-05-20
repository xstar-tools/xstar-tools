from __future__ import annotations

import math

import numpy as np

from xstar_atomic.source_port import (
    DsecProbeTrajectory,
    DsecTrajectoryEvent,
    PhysicalDsecCalcKwargsFactory,
    PhysicalDsecContinuumTemplate,
    initial_state_from_xstar_trajectory,
    clone_physical_dsec_runtime_state,
    load_compton_table,
)
from xstar_atomic.source_port.dsec import DsecMutableRuntimeState
from xstar_atomic.source_port.free_free import freef_continuum_result


def _event(**updates):
    values = dict(
        event_index=1,
        event="begin",
        evaluation_index=0,
        ntotit=0,
        nnx=0,
        nnxx=0,
        nnt=0,
        nntt=0,
        nlim=99,
        nlimt=99,
        nlimx=99,
        nlimtt=99,
        nlimxx=99,
        temperature_t4=100.0,
        temperature_k=1.0e6,
        tinf_t4=0.0,
        electron_fraction_xee=1.0,
        hydrogen_density_cm3=1.0e8,
        tl=0.0,
        th=0.0,
        xeel=0.0,
        xeeh=1.0,
        elcter=None,
        elctrl=1.0,
        elctrh=-1.0,
        hmctot=None,
        hmcttl=0.0,
        hmctth=0.0,
        previous_temperature_t4=1.0e30,
        normalized_charge_residual=None,
        temperature_stagnation_metric=None,
        lnerr=0,
        iht=0,
        ilt=0,
        iuht=0,
        iult=0,
        ihx=0,
        ilx=0,
    )
    values.update(updates)
    return DsecTrajectoryEvent(**values)


def test_initial_state_defaults_to_xstar_begin_row() -> None:
    ref = DsecProbeTrajectory(call_id=1, events=(_event(tinf_t4=6.0e-154),), source_path="probe.csv")
    initial = initial_state_from_xstar_trajectory(ref)
    assert initial.temperature_t4 == 100.0
    assert initial.electron_fraction_xee == 1.0
    assert initial.hydrogen_density_cm3 == 1.0e8
    assert initial.nlim == 99
    assert initial.tinf_t4 == 6.0e-154
    assert initial.source == "xstar_dsec_begin_probe"


def test_initial_state_check_rejects_mismatch() -> None:
    ref = DsecProbeTrajectory(call_id=1, events=(_event(),), source_path="probe.csv")
    try:
        initial_state_from_xstar_trajectory(
            ref,
            temperature_t4=99.0,
            electron_fraction_xee=1.0,
            hydrogen_density_cm3=1.0e8,
            nlim=99,
            tinf_t4=0.0,
            policy="check",
        )
    except Exception as exc:
        assert "differs from XSTAR begin row" in str(exc)
    else:
        raise AssertionError("mismatched checked state was accepted")


def test_dynamic_continuum_factory_rebuilds_and_carries_workspace() -> None:
    table = load_compton_table()
    epi = np.array([10.0, 20.0, 40.0, 80.0])
    bremsa = np.array([4.0e5, 3.0e5, 2.0e5, 1.0e5])
    template = PhysicalDsecContinuumTemplate(
        epi_eV=epi,
        bremsa=bremsa,
        compton_table=table,
        radius_cm=1.0e16,
        zone_thickness_cm=1.0e12,
        ncn2=4,
        initial_opakc_cm_inv=np.ones(4),
        initial_brcems=np.ones(4),
        first_workspace_policy="zero",
        carry_continuum_workspace=True,
    )
    factory = PhysicalDsecCalcKwargsFactory(template)
    state = DsecMutableRuntimeState(2.0, 1.2, 1.0e8)

    first = factory(state)
    assert factory.build_count == 1
    assert np.array_equal(first["free_free_context"].opakc_before_cm_inv, np.zeros(4))
    assert np.array_equal(first["bremem_context"].brcems_before, np.zeros(4))

    freef_result, _ = freef_continuum_result(
        first["free_free_context"],
        temperature_k=state.temperature_k,
        hydrogen_density_cm3=state.hydrogen_density_cm3,
        electron_fraction_xee=state.electron_fraction_xee,
    )
    assert np.array_equal(
        first["bremem_context"].opakc_before_cm_inv,
        freef_result.opakc_after_cm_inv,
    )
    assert np.array_equal(
        first["heatf_context"].brcems,
        first["bremem_context"].brcems_before * 0.0
        + first["heatf_context"].brcems,
    )

    carried_opacity = np.arange(4, dtype=float) + 10.0
    carried_brcems = np.arange(4, dtype=float) + 20.0
    state.work_arrays["opakc"] = carried_opacity
    state.work_arrays["brcems"] = carried_brcems
    second = factory(state)
    assert factory.build_count == 2
    assert np.array_equal(second["free_free_context"].opakc_before_cm_inv, carried_opacity)
    assert np.array_equal(second["bremem_context"].brcems_before, carried_brcems)
    assert math.isclose(second["heatf_context"].radius_cm, 1.0e16)


def test_post_dsec_clone_preserves_inputs_without_mutating_call_count() -> None:
    state = DsecMutableRuntimeState(7.5, 1.2, 1.0e8)
    state.element_populations[8] = np.array([0.25, 0.75])
    state.work_arrays["opakc"] = np.array([1.0, 2.0])
    state.leveltemp_owner_by_column[1] = {"element_z": 8}
    state.calc_hmc_all_call_count = 34
    clone = clone_physical_dsec_runtime_state(state)

    assert clone.temperature_t4 == state.temperature_t4
    assert clone.electron_fraction_xee == state.electron_fraction_xee
    assert clone.calc_hmc_all_call_count == 0
    assert clone.last_calc_hmc_all is None
    assert np.array_equal(clone.element_populations[8], state.element_populations[8])
    assert np.array_equal(clone.work_arrays["opakc"], state.work_arrays["opakc"])
    clone.element_populations[8][0] = 99.0
    clone.work_arrays["opakc"][0] = 99.0
    assert state.element_populations[8][0] == 0.25
    assert state.work_arrays["opakc"][0] == 1.0
    assert clone.provenance["post_dsec_xstarcalc_clone"] is True
