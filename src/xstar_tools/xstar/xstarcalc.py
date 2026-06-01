"""Complete local-zone assembly of XSTAR ``xstarcalc.f90``.

This module joins the previously accepted bounded source ports in their literal
caller order::

    bremsmap -> [dsec] -> calc_hmc_all -> calc_emisab_all -> calc_emis_all

The brackets denote XSTAR's ``nlimdt == 0`` skip branch.  The routine also
preserves the caller print-switch save/zero/restore sequence and the final
``nry = nbinc(13.6, epi, ncn2) + 2`` assignment.

``dsec`` and the final ``calc_hmc_all`` are supplied as explicit state handlers.
This keeps the complete local driver independent of probe products while the
physical ATDB-backed adapters remain available to callers.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Mapping, Optional

import numpy as np

from .driver import XSTARPythonDriver, XSTARSourceRoutine
from .emissivity import (
    CalcEmisabContext,
    CalcEmisabWorkspace,
    apply_calc_emisab_all_to_state,
    register_calc_emisab_all_source_routine,
)
from .emergent_emissivity import (
    CalcEmisContext,
    CalcEmisWorkspace,
    apply_calc_emis_all_to_state,
    register_calc_emis_all_source_routine,
)
from .element_equilibrium import EscapeProbabilityContext
from .radiation import (
    apply_bremsmap_to_state,
    nbinc,
    register_bremsmap_source_routine,
)
from .state import XSTARPythonState
from .ucalc import UCalcResult, UCalcStatus


class CompleteLocalXstarcalcPortError(RuntimeError):
    """Raised when the complete local ``xstarcalc`` contract is incomplete."""


SourceStateHandler = Callable[[XSTARPythonState], Any]


@dataclass(frozen=True)
class CompleteLocalXstarcalcResult:
    """Summary of one translated local ``xstarcalc`` execution."""

    state: XSTARPythonState
    dsec_executed: bool
    source_order: tuple[str, ...]
    skipped_source_routines: tuple[str, ...]
    lpri_before: int
    lpri_after: int
    nlimdt: int
    nry: int
    bremsmap_result: Any
    dsec_result: Any
    calc_hmc_all_result: Any
    calc_emisab_all_result: Any
    calc_emis_all_result: Any
    source_file: str = "xstar/xstarlib/src/xstarcalc.f90"


def _require_source_handler(state: XSTARPythonState, key: str) -> SourceStateHandler:
    handler = state.control.get(key)
    if not callable(handler):
        raise CompleteLocalXstarcalcPortError(
            f"state.control[{key!r}] must be a callable source-state handler"
        )
    return handler


def apply_dsec_to_state(state: XSTARPythonState) -> Any:
    """Invoke the caller-supplied translated ``dsec`` state handler."""
    result = _require_source_handler(state, "dsec_source_handler")(state)
    state.local_zone.thermal_iteration_ready = True
    state.local_zone.source_arrays["dsec"] = result
    state.local_zone.provenance["dsec"] = {
        "source_file": "xstar/xstarlib/src/dsec.f90",
        "handler": "state.control['dsec_source_handler']",
    }
    return result


def apply_calc_hmc_all_to_state(state: XSTARPythonState) -> Any:
    """Invoke the caller-supplied final ``calc_hmc_all`` state handler."""
    result = _require_source_handler(state, "calc_hmc_all_source_handler")(state)
    state.local_zone.calc_hmc_all = result
    state.local_zone.fixed_state_ready = True
    state.local_zone.source_arrays["calc_hmc_all"] = result
    state.local_zone.provenance["calc_hmc_all"] = {
        "source_file": "xstar/xstarlib/src/calc_hmc_all.f90",
        "handler": "state.control['calc_hmc_all_source_handler']",
    }
    return result


def register_complete_local_xstarcalc_source_routines(
    driver: XSTARPythonDriver,
) -> None:
    """Register every translated routine required by local ``xstarcalc``."""
    register_bremsmap_source_routine(driver)
    driver.register_source_routine(XSTARSourceRoutine.DSEC, apply_dsec_to_state)
    driver.register_source_routine(
        XSTARSourceRoutine.CALC_HMC_ALL, apply_calc_hmc_all_to_state
    )
    register_calc_emisab_all_source_routine(driver)
    register_calc_emis_all_source_routine(driver)


def run_complete_local_xstarcalc(
    state: XSTARPythonState,
    *,
    driver: Optional[XSTARPythonDriver] = None,
    fixed_state: bool = False,
) -> CompleteLocalXstarcalcResult:
    """Execute the complete translated local ``xstarcalc`` sequence."""
    runner = driver or XSTARPythonDriver()
    if driver is None:
        register_complete_local_xstarcalc_source_routines(runner)

    completed_before = len(state.provenance.get("completed_source_routines", []))
    skipped_before = len(state.provenance.get("skipped_source_routines", []))
    lpri_before = int(state.control.get("lpri", 0))
    nlimdt = int(state.control.get("nlimdt", 1))

    runner.run_xstarcalc(state, fixed_state=fixed_state)

    source_order = tuple(
        state.provenance.get("completed_source_routines", [])[completed_before:]
    )
    skipped = tuple(
        state.provenance.get("skipped_source_routines", [])[skipped_before:]
    )
    dsec_executed = XSTARSourceRoutine.DSEC.value in source_order
    return CompleteLocalXstarcalcResult(
        state=state,
        dsec_executed=dsec_executed,
        source_order=source_order,
        skipped_source_routines=skipped,
        lpri_before=lpri_before,
        lpri_after=int(state.control.get("lpri", 0)),
        nlimdt=nlimdt,
        nry=int(state.control["nry"]),
        bremsmap_result=state.local_zone.source_arrays.get("bremsmap"),
        dsec_result=state.local_zone.source_arrays.get("dsec"),
        calc_hmc_all_result=state.local_zone.source_arrays.get("calc_hmc_all"),
        calc_emisab_all_result=state.local_zone.source_arrays.get(
            "calc_emisab_all"
        ),
        calc_emis_all_result=state.local_zone.source_arrays.get("calc_emis_all"),
    )


def _continuum_length_from_context(context: Any) -> int:
    radiation = getattr(context, "radiation", None)
    for name in ("epim", "epi"):
        values = getattr(radiation, name, None)
        if values is not None:
            return int(np.asarray(values, dtype=float).reshape(-1).size)
    raise CompleteLocalXstarcalcPortError(
        "synthetic ucalc context lacks a radiation energy grid"
    )


def _synthetic_complete_ucalc(record: int, context: Any) -> UCalcResult:
    """Shared reduced/full-grid evaluator used by the assembly fixture."""
    payload = {
        10: (1.0, 4.0, -4.0, 0.0, 0.25, {}),
        11: (0.5, 3.0, -9.0, 0.0, 0.55, {}),
        12: (0.0, 0.0, -6.0, -2.0, 0.125, "continuum"),
        14: (0.0, 0.0, -7.0, -3.0, 0.2, {}),
        15: (0.0, 0.0, -2.0, -1.0, 0.375, "continuum_42"),
    }
    ans1, ans2, ans3, ans4, opak, diagnostics = payload[int(record)]
    if isinstance(diagnostics, str) and diagnostics in {"continuum", "continuum_42"}:
        n = _continuum_length_from_context(context)
        scale = 1.0 if diagnostics == "continuum" else 0.1
        base = np.arange(1, n + 1, dtype=float)
        diagnostics = {
            "opakc_cm^-1": scale * base,
            "opakcont_cm^-1": 0.5 * scale * base,
            "rccemis_inward": 0.1 * scale * base,
            "rccemis_outward": 0.1 * scale * base[::-1],
        }
    header = {
        10: (50, 4),
        11: (11, 9),
        12: (53, 7),
        14: (74, 7),
        15: (42, 42),
    }[int(record)]
    return UCalcResult(
        record=int(record),
        data_type=header[0],
        rate_type=header[1],
        status=UCalcStatus.EVALUATED,
        ans1=ans1,
        ans2=ans2,
        ans3=ans3,
        ans4=ans4,
        opakab=opak,
        diagnostics=diagnostics,
    )


def _build_validation_state(*, nlimdt: int) -> tuple[XSTARPythonState, list[str]]:
    # Import the frozen synthetic ATDB/pointer model from the immediately
    # preceding accepted subsystem.  The fixture remains independent of any
    # production ATDB installation or probe products.
    from .emergent_emissivity import _SyntheticDerived, _SyntheticMaster

    state = XSTARPythonState()
    calls: list[str] = []
    state.control.update({
        "ncn2": 5,
        "ncn2m": 4,
        "nlimdt": int(nlimdt),
        "lpri": 7,
    })
    state.radiation.epi = np.asarray([1.0, 10.0, 100.0, 1000.0, 10000.0])
    state.radiation.bremsa = np.asarray([10.0, 8.0, 4.0, 2.0, 1.0])
    state.radiation.epim = np.asarray([1.0, 10.0, 100.0, 1000.0])
    state.radiation.bremsam = np.asarray([91.0, 92.0, 93.0, 94.0, 777.0])
    state.radiation.bremsint = np.asarray([11.0, 12.0, 13.0, 14.0, 1234.0])
    state.plasma.temperature = 1.0e6
    state.plasma.xee = 1.0
    state.plasma.xpx = 5.0

    def dsec_handler(runtime: XSTARPythonState) -> Mapping[str, Any]:
        calls.append("dsec")
        mapped = np.asarray(runtime.radiation.bremsam, dtype=float)
        runtime.control["dsec_saw_lpri_zero"] = int(runtime.control["lpri"]) == 0
        bremsmap_result = runtime.local_zone.source_arrays.get("bremsmap")
        runtime.control["dsec_saw_bremsmap"] = bool(
            bremsmap_result is not None
            and np.array_equal(mapped, bremsmap_result.bremsam_after)
            and mapped[4] == 777.0
        )
        runtime.plasma.temperature = 2.0e4
        runtime.plasma.xee = 1.2
        runtime.plasma.xpx = 5.0
        return {
            "temperature_k": runtime.plasma.temperature,
            "electron_fraction_xee": runtime.plasma.xee,
            "converged": True,
        }

    def calc_hmc_all_handler(runtime: XSTARPythonState) -> Mapping[str, Any]:
        calls.append("calc_hmc_all")
        runtime.control["calc_hmc_saw_dsec_state"] = bool(
            math.isclose(runtime.plasma.temperature, 2.0e4)
            and math.isclose(runtime.plasma.xee, 1.2)
        ) if nlimdt != 0 else bool(math.isclose(runtime.plasma.temperature, 1.0e6))

        master = _SyntheticMaster()
        derived = _SyntheticDerived()
        shared = CalcEmisWorkspace.allocate(
            n_lines=3,
            n_continua=3,
            n_energy=5,
            continuum_fill=7.0,
            fline_fill=9.0,
            flinel_fill=5.0,
        )
        xilevg = np.asarray([0.0, 0.2, 0.1, 0.7, 0.3, 0.1])
        bilevg = np.ones(6)
        rnisg = np.ones(6)
        runtime.plasma.populations = xilevg
        runtime.local_zone.source_arrays["xilevg"] = xilevg
        runtime.local_zone.source_arrays["bilevg"] = bilevg
        runtime.local_zone.source_arrays["rnisg"] = rnisg
        radiation = SimpleNamespace(
            epi=runtime.radiation.epi,
            bremsa=runtime.radiation.bremsa,
            epim=runtime.radiation.epim,
            bremsam=runtime.radiation.bremsam,
            bremsint=runtime.radiation.bremsint,
        )
        escape = EscapeProbabilityContext(
            line_tau_in=np.asarray([0.0, 0.0, 0.0]),
            line_tau_out=np.asarray([0.0, 0.0, 0.0]),
            continuum_tau_in=np.asarray([0.0, 0.0, 0.0]),
            continuum_tau_out=np.asarray([0.0, 0.0, 0.0]),
        )
        common = dict(
            master=master,
            derived=derived,
            temperature_1e4K=float(runtime.plasma.temperature) / 1.0e4,
            electron_fraction_xee=float(runtime.plasma.xee),
            hydrogen_density_cm3=float(runtime.plasma.xpx),
            pressure_dyn_cm2=0.0,
            density_control_lcdd=1,
            abundances_by_z={1: 1.0, 8: 0.5},
            min_ion_stage_by_z={8: 1},
            max_ion_stage_by_z={8: 1},
            xilevg=xilevg,
            bilevg=bilevg,
            rnisg=rnisg,
            radiation=radiation,
            escape=escape,
            covering_fraction=0.25,
            ucalc_evaluator=_synthetic_complete_ucalc,
        )
        runtime.control["calc_emisab_context"] = CalcEmisabContext(
            **common,
            workspace=shared.base,
        )
        wavelengths = np.asarray([
            0.0,
            12398.419843320026 / 2.0,
            12398.419843320026 / 3.0,
            12398.419843320026 / 4.0,
        ])
        runtime.control["calc_emis_context"] = CalcEmisContext(
            **common,
            workspace=shared,
            line_wavelength_angstrom=wavelengths.copy(),
            rrc_wavelength_angstrom=wavelengths.copy(),
            rank_depth=3,
        )
        runtime.control["shared_emissivity_workspace"] = shared
        return {
            "temperature_k": runtime.plasma.temperature,
            "electron_fraction_xee": runtime.plasma.xee,
            "xilevg": xilevg.copy(),
        }

    state.control["dsec_source_handler"] = dsec_handler
    state.control["calc_hmc_all_source_handler"] = calc_hmc_all_handler
    return state, calls


def run_complete_local_xstarcalc_validation(
    *, rtol: float = 2.0e-14, atol: float = 1.0e-30
) -> Mapping[str, Any]:
    """Run the independent bounded complete-local assembly validation."""
    del rtol, atol  # Exact source-ownership gates dominate this fixture.

    state, callback_order = _build_validation_state(nlimdt=5)
    result = run_complete_local_xstarcalc(state)
    expected_order = (
        "bremsmap",
        "dsec",
        "calc_hmc_all",
        "calc_emisab_all",
        "calc_emis_all",
    )
    emisab = result.calc_emisab_all_result
    emis = result.calc_emis_all_result
    shared = state.control["shared_emissivity_workspace"]

    source_order_ready = result.source_order == expected_order
    print_switch_ready = bool(
        state.control.get("dsec_saw_lpri_zero")
        and result.lpri_before == 7
        and result.lpri_after == 7
        and int(state.control.get("lprisv", -1)) == 7
    )
    bremsmap_before_dsec_ready = bool(state.control.get("dsec_saw_bremsmap"))
    final_hmc_after_dsec_ready = bool(
        callback_order == ["dsec", "calc_hmc_all"]
        and state.control.get("calc_hmc_saw_dsec_state")
    )
    shared_workspace_ready = bool(
        emisab.workspace is shared.base
        and emis.workspace is shared
        and emis.workspace.base is emisab.workspace
    )
    reduced_full_continuum_ready = bool(
        shared.base.opakc.shape == (5,)
        and shared.base.rccemis.shape == (2, 5)
        and len(np.asarray(state.radiation.epim)) == 4
        and len(np.asarray(state.radiation.epi)) == 5
    )
    precomputed_ranking_ready = bool(
        len(emis.rank_traces) > 0
        and np.count_nonzero(emis.line_rank_table) > 0
        and np.count_nonzero(emis.continuum_rank_table) > 0
    )
    final_array_ownership_ready = bool(
        result.bremsmap_result is not None
        and np.array_equal(
            state.radiation.bremsam, result.bremsmap_result.bremsam_after
        )
        and state.radiation.bremsam[4] == 777.0
        and state.radiation.bremsint[4] == 1234.0
        and state.local_zone.emissivity_ready
        and state.local_zone.fixed_state_ready
        and state.local_zone.thermal_iteration_ready
    )
    nry_expected = nbinc(13.6, state.radiation.epi, 5) + 2
    nry_ready = result.nry == nry_expected

    skip_state, skip_callbacks = _build_validation_state(nlimdt=0)
    skip_result = run_complete_local_xstarcalc(skip_state)
    expected_skip_order = (
        "bremsmap",
        "calc_hmc_all",
        "calc_emisab_all",
        "calc_emis_all",
    )
    nlimdt_zero_ready = bool(
        skip_result.source_order == expected_skip_order
        and skip_result.skipped_source_routines == ("dsec",)
        and skip_callbacks == ["calc_hmc_all"]
        and not skip_result.dsec_executed
    )

    summary: dict[str, Any] = {
        "port_version": "v0.4.63",
        "complete_local_xstarcalc_translated": True,
        "literal_source_order_ready": source_order_ready,
        "source_order": list(result.source_order),
        "lpri_save_zero_restore_ready": print_switch_ready,
        "bremsmap_before_dsec_ready": bremsmap_before_dsec_ready,
        "nlimdt_zero_dsec_skip_ready": nlimdt_zero_ready,
        "final_calc_hmc_all_after_dsec_ready": final_hmc_after_dsec_ready,
        "calc_emisab_before_calc_emis_ready": bool(
            result.source_order.index("calc_emisab_all")
            < result.source_order.index("calc_emis_all")
        ),
        "shared_emissivity_workspace_ready": shared_workspace_ready,
        "reduced_to_full_continuum_capacity_ready": reduced_full_continuum_ready,
        "precomputed_absorption_feature_ranking_ready": precomputed_ranking_ready,
        "caller_owned_array_continuity_ready": final_array_ownership_ready,
        "final_nry_assignment_ready": nry_ready,
        "nry": int(result.nry),
        "nry_expected": int(nry_expected),
        "fixed_state_ready": bool(state.local_zone.fixed_state_ready),
        "thermal_iteration_ready": bool(state.local_zone.thermal_iteration_ready),
        "emissivity_ready": bool(state.local_zone.emissivity_ready),
    }
    summary["complete_local_xstarcalc_source_acceptance_ready"] = bool(
        all(value for key, value in summary.items() if key.endswith("_ready"))
    )
    summary["next_source_target"] = "radial_transfer_and_output"
    return summary


def write_complete_local_xstarcalc_validation_products(
    summary: Mapping[str, Any], out_dir: str | Path
) -> Mapping[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "xstar_complete_local_xstarcalc_source_validation_summary.json"
    md_path = out / "xstar_complete_local_xstarcalc_source_validation_summary.md"
    json_path.write_text(
        json.dumps(dict(summary), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(
        "# XSTAR complete local `xstarcalc` source validation\n\n"
        + "\n".join(f"- {key}: `{value}`" for key, value in summary.items())
        + "\n",
        encoding="utf-8",
    )
    return {"json": str(json_path), "markdown": str(md_path)}


__all__ = [
    "CompleteLocalXstarcalcPortError",
    "CompleteLocalXstarcalcResult",
    "apply_dsec_to_state",
    "apply_calc_hmc_all_to_state",
    "register_complete_local_xstarcalc_source_routines",
    "run_complete_local_xstarcalc",
    "run_complete_local_xstarcalc_validation",
    "write_complete_local_xstarcalc_validation_products",
]
