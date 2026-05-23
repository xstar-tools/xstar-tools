from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np

from xstar_atomic.source_port import physical_runner as runner
from xstar_atomic.source_port.bremsstrahlung import bremem_continuum_result
from xstar_atomic.source_port.compton import comp2_continuum_result, load_compton_table
from xstar_atomic.source_port.dsec import DsecMutableRuntimeState
from xstar_atomic.source_port.free_free import freef_continuum_result


_HELPER_PATH = Path(__file__).with_name("test_source_port_atomic_database_v041.py")
_HELPER_SPEC = importlib.util.spec_from_file_location(
    "xstar_atomic_test_source_port_atomic_database_v041_v0475", _HELPER_PATH
)
assert _HELPER_SPEC is not None and _HELPER_SPEC.loader is not None
_HELPER_MODULE = importlib.util.module_from_spec(_HELPER_SPEC)
_HELPER_SPEC.loader.exec_module(_HELPER_MODULE)
_write_mini_atdb = _HELPER_MODULE._write_mini_atdb


def _build_state(tmp_path: Path):
    atdb = tmp_path / "atdb.fits"
    _write_mini_atdb(atdb)
    parameters = runner.normalize_xstar_parameters(
        {
            "ncn2": 1200,
            "nsteps": 1,
            "npass": 1,
            "spectrum": "pow",
            "abundtbl": "xdef",
        }
    )
    return runner._build_initial_state(parameters, atdb_path=atdb, use_cache=False)


def test_v0475_physical_factory_replays_mutable_continuum_chain(tmp_path: Path):
    state, built = _build_state(tmp_path)
    try:
        n = int(state.control["ncn2m"])
        incoming_opacity = np.linspace(0.0, 1.0e-20, n)
        incoming_brcems = np.linspace(1.0e-30, 2.0e-30, n)
        runtime = DsecMutableRuntimeState(
            temperature_t4=100.0,
            electron_fraction_xee=1.2,
            hydrogen_density_cm3=3.0,
            work_arrays={
                "opakc": incoming_opacity,
                "brcems": incoming_brcems,
            },
        )

        contexts = runner._calc_kwargs_factory(state, load_compton_table())(runtime)
        comp = contexts["compton_context"]
        free = contexts["free_free_context"]
        bremem = contexts["bremem_context"]
        heat = contexts["heatf_context"]

        comp_result, _ = comp2_continuum_result(
            comp,
            temperature_k=runtime.temperature_k,
            hydrogen_density_cm3=runtime.hydrogen_density_cm3,
            electron_fraction_xee=runtime.electron_fraction_xee,
        )
        free_result, _ = freef_continuum_result(
            free,
            temperature_k=runtime.temperature_k,
            hydrogen_density_cm3=runtime.hydrogen_density_cm3,
            electron_fraction_xee=runtime.electron_fraction_xee,
        )
        bremem_result, _ = bremem_continuum_result(
            bremem,
            temperature_k=runtime.temperature_k,
            hydrogen_density_cm3=runtime.hydrogen_density_cm3,
            electron_fraction_xee=runtime.electron_fraction_xee,
        )

        assert np.array_equal(free.opakc_before_cm_inv, incoming_opacity)
        assert np.array_equal(
            bremem.opakc_before_cm_inv,
            free_result.opakc_after_cm_inv,
        )
        assert not np.array_equal(
            bremem.opakc_before_cm_inv,
            incoming_opacity,
        )
        assert np.array_equal(bremem.brcems_before, incoming_brcems)
        assert np.array_equal(heat.brcems, bremem_result.brcems_after)
        assert heat.htfreef_erg_cm3_s == free_result.htfreef_erg_cm3_s
        assert heat.cmp1 == comp_result.cmp1
        assert heat.cmp2 == comp_result.cmp2
    finally:
        built.atomic_state.close()


def test_v0475_zero_first_call_also_chains_freef_into_bremem(tmp_path: Path):
    state, built = _build_state(tmp_path)
    try:
        runtime = DsecMutableRuntimeState(
            temperature_t4=100.0,
            electron_fraction_xee=1.0,
            hydrogen_density_cm3=1.0,
        )
        contexts = runner._calc_kwargs_factory(state, load_compton_table())(runtime)
        free = contexts["free_free_context"]
        bremem = contexts["bremem_context"]
        free_result, _ = freef_continuum_result(
            free,
            temperature_k=runtime.temperature_k,
            hydrogen_density_cm3=runtime.hydrogen_density_cm3,
            electron_fraction_xee=runtime.electron_fraction_xee,
        )
        assert np.array_equal(
            bremem.opakc_before_cm_inv,
            free_result.opakc_after_cm_inv,
        )
        assert np.any(bremem.opakc_before_cm_inv > 0.0)
    finally:
        built.atomic_state.close()
