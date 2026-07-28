"""Native final zero-thickness fixed-state bridge for accelerated Python.

v0.6.48.10.1 keeps the radial/zone controller in Python and replaces only the
post-loop ``bremsmap -> calc_hmc_all -> calc_emisab_all -> calc_emis_all``
recompute with the accepted native fixed-state engine.  HEATT/STPCUT remain in
the normal Python driver order (and can themselves use their existing C++
backend).
"""
from __future__ import annotations

import ctypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

ABI = 6048101
_MSG = 512
_LIB: ctypes.CDLL | None = None

_DBLP = ctypes.POINTER(ctypes.c_double)


class _Input(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32), ("abi_version", ctypes.c_uint32),
        ("atdb_path", ctypes.c_char_p),
        ("temperature_k", ctypes.c_double), ("electron_density_cm3", ctypes.c_double),
        ("hydrogen_density_cm3", ctypes.c_double), ("neutral_h_density_cm3", ctypes.c_double),
        ("ionized_h_density_cm3", ctypes.c_double), ("electron_fraction_xee", ctypes.c_double),
        ("emission_covering_fraction", ctypes.c_double), ("dsec_covering_fraction", ctypes.c_double),
        ("turbulent_velocity_km_s", ctypes.c_double),
        ("abundances_by_z", _DBLP), ("abundance_count", ctypes.c_size_t),
        ("radiation_energy_ev", _DBLP), ("incident_flux", _DBLP), ("dsec_bremsa", _DBLP),
        ("radiation_bin_count", ctypes.c_size_t),
        ("continuum_tau_in", _DBLP), ("continuum_tau_out", _DBLP), ("continuum_tau_count", ctypes.c_size_t),
        ("line_tau_in", _DBLP), ("line_tau_out", _DBLP), ("line_tau_count", ctypes.c_size_t),
        ("global_xilevg", _DBLP), ("global_bilevg", _DBLP), ("global_rnisg", _DBLP),
        ("global_level_count", ctypes.c_size_t),
    ]


class _Output(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32), ("abi_version", ctypes.c_uint32),
        ("element_heating", ctypes.c_double), ("element_cooling", ctypes.c_double),
        ("continuum_heating", ctypes.c_double), ("continuum_cooling", ctypes.c_double),
        ("total_heating", ctypes.c_double), ("total_cooling", ctypes.c_double),
        ("hmctot", ctypes.c_double), ("computed_electron_fraction", ctypes.c_double),
        ("charge_residual", ctypes.c_double),
        ("hydrogen_heating", ctypes.c_double), ("hydrogen_cooling", ctypes.c_double),
        ("helium_heating", ctypes.c_double), ("helium_cooling", ctypes.c_double),
        ("magnesium_heating", ctypes.c_double), ("magnesium_cooling", ctypes.c_double),
        ("compton_heating", ctypes.c_double), ("compton_cooling", ctypes.c_double),
        ("free_free_heating", ctypes.c_double), ("bremsstrahlung_cooling", ctypes.c_double),
        ("populations", _DBLP), ("populations_capacity", ctypes.c_size_t), ("populations_count", ctypes.c_size_t),
        ("lte_populations", _DBLP), ("lte_populations_capacity", ctypes.c_size_t), ("lte_populations_count", ctypes.c_size_t),
        ("rcem", _DBLP), ("rcem_capacity", ctypes.c_size_t), ("rcem_count", ctypes.c_size_t),
        ("oplin", _DBLP), ("oplin_capacity", ctypes.c_size_t), ("oplin_count", ctypes.c_size_t),
        ("cemab", _DBLP), ("cemab_capacity", ctypes.c_size_t), ("cemab_count", ctypes.c_size_t),
        ("cabab", _DBLP), ("cabab_capacity", ctypes.c_size_t), ("cabab_count", ctypes.c_size_t),
        ("opakab", _DBLP), ("opakab_capacity", ctypes.c_size_t), ("opakab_count", ctypes.c_size_t),
        ("rccemis", _DBLP), ("rccemis_capacity", ctypes.c_size_t), ("rccemis_count", ctypes.c_size_t),
        ("opakc", _DBLP), ("opakc_capacity", ctypes.c_size_t), ("opakc_count", ctypes.c_size_t),
        ("opakcont", _DBLP), ("opakcont_capacity", ctypes.c_size_t), ("opakcont_count", ctypes.c_size_t),
        ("fline", _DBLP), ("fline_capacity", ctypes.c_size_t), ("fline_count", ctypes.c_size_t),
        ("flinel", _DBLP), ("flinel_capacity", ctypes.c_size_t), ("flinel_count", ctypes.c_size_t),
        ("brcems", _DBLP), ("brcems_capacity", ctypes.c_size_t), ("brcems_count", ctypes.c_size_t),
        ("traversal_seconds", ctypes.c_double), ("rate_seconds", ctypes.c_double),
        ("element_seconds", ctypes.c_double), ("continuum_seconds", ctypes.c_double),
        ("spectral_seconds", ctypes.c_double), ("total_seconds", ctypes.c_double),
        ("message", ctypes.c_char * _MSG),
    ]


def _p(a: np.ndarray) -> _DBLP:
    return a.ctypes.data_as(_DBLP)


def _arr(value: Any, *, n: int | None = None) -> np.ndarray:
    a = np.ascontiguousarray(np.asarray(value, dtype=np.float64).reshape(-1))
    if n is not None:
        if a.size < n:
            raise RuntimeError(f"native final recompute input shorter than required: {a.size} < {n}")
        a = np.ascontiguousarray(a[:n])
    return a


def _load() -> ctypes.CDLL:
    global _LIB
    if _LIB is not None:
        return _LIB
    path = Path(__file__).resolve().parent / "cpp" / "libxstar_final_recompute.so"
    if not path.exists():
        raise RuntimeError(f"native final recompute library is missing: {path}")
    lib = ctypes.CDLL(str(path))
    lib.xstar_final_recompute_bridge_abi_version.argtypes = []
    lib.xstar_final_recompute_bridge_abi_version.restype = ctypes.c_uint32
    if int(lib.xstar_final_recompute_bridge_abi_version()) != ABI:
        raise RuntimeError("native final recompute ABI mismatch")
    lib.xstar_final_recompute_input_init_v1.argtypes = [ctypes.POINTER(_Input)]
    lib.xstar_final_recompute_input_init_v1.restype = ctypes.c_int
    lib.xstar_final_recompute_output_init_v1.argtypes = [ctypes.POINTER(_Output)]
    lib.xstar_final_recompute_output_init_v1.restype = ctypes.c_int
    lib.xstar_final_recompute_run_v1.argtypes = [
        ctypes.POINTER(_Input), ctypes.POINTER(_Output), ctypes.c_char_p, ctypes.c_size_t
    ]
    lib.xstar_final_recompute_run_v1.restype = ctypes.c_int
    _LIB = lib
    return lib


@dataclass(frozen=True)
class NativeFinalRecomputeResult:
    total_heating: float
    total_cooling: float
    hmctot: float
    computed_electron_fraction: float
    charge_residual: float
    cpp_seconds: float
    bridge_seconds: float
    message: str
    thermal_components: dict[str, float]
    native_counts: dict[str, int]


def apply_native_final_recompute(state: Any) -> NativeFinalRecomputeResult:
    """Replace only the final local xstarcalc fixed-state/emissivity work."""
    from .radial_transfer import RadialTransferWorkspace

    workspace = state.control.get("radial_transfer_workspace")
    if not isinstance(workspace, RadialTransferWorkspace):
        raise RuntimeError("native final recompute requires RadialTransferWorkspace")
    fixed = state.local_zone.calc_hmc_all
    if fixed is None:
        raise RuntimeError("native final recompute requires the terminal calc_hmc_all state")
    n = int(state.control.get("ncn2", 0))
    if n <= 1:
        raise RuntimeError("invalid final recompute continuum size")

    energy = _arr(state.radiation.epi, n=n)
    incident = _arr(workspace.zremsz, n=n)
    bremsa = _arr(state.radiation.bremsa, n=n)
    gx = _arr(getattr(fixed, "global_xilevg_by_index"))
    gb = _arr(getattr(fixed, "global_bilevg_by_index"))
    gr = _arr(getattr(fixed, "global_rnisg_by_index"))
    if not (gx.size == gb.size == gr.size and gx.size > 0):
        raise RuntimeError("terminal global level workspaces are incomplete")

    tauc = np.asarray(workspace.tauc, dtype=np.float64)
    tau0 = np.asarray(workspace.tau0, dtype=np.float64)
    cont_tau_in = _arr(tauc[0])
    cont_tau_out = _arr(tauc[1])
    line_tau_in = _arr(tau0[0])
    line_tau_out = _arr(tau0[1])

    abund = np.zeros(30, dtype=np.float64)
    if state.plasma.abundances is not None:
        a = _arr(state.plasma.abundances)
        abund[: min(30, a.size)] = a[: min(30, a.size)]
    else:
        ctx = state.control.get("calc_emis_context")
        for z, value in getattr(ctx, "abundances_by_z", {}).items():
            if 1 <= int(z) <= 30:
                abund[int(z) - 1] = float(value)

    nlines_guard = int(workspace.emissivity.base.rcem.shape[1])
    ncont_guard = int(workspace.emissivity.base.cemab.shape[1])
    populations = np.zeros(max(gx.size, 4096), dtype=np.float64)
    lte = np.zeros_like(populations)
    rcem = np.zeros(2 * nlines_guard, dtype=np.float64)
    oplin = np.zeros(nlines_guard, dtype=np.float64)
    cemab = np.zeros(2 * ncont_guard, dtype=np.float64)
    cabab = np.zeros(ncont_guard, dtype=np.float64)
    opakab = np.zeros(ncont_guard, dtype=np.float64)
    rccemis = np.zeros(2 * n, dtype=np.float64)
    opakc = np.zeros(n, dtype=np.float64)
    opakcont = np.zeros(n, dtype=np.float64)
    fline = np.zeros(2 * nlines_guard, dtype=np.float64)
    flinel = np.zeros(n, dtype=np.float64)
    brcems = np.zeros(n, dtype=np.float64)

    inp = _Input(); out = _Output(); lib = _load()
    if lib.xstar_final_recompute_input_init_v1(ctypes.byref(inp)) != 0:
        raise RuntimeError("native final recompute input initialization failed")
    if lib.xstar_final_recompute_output_init_v1(ctypes.byref(out)) != 0:
        raise RuntimeError("native final recompute output initialization failed")

    atdb = str(state.atomic.atdb_path or state.control.get("atdb_path") or "")
    if not atdb:
        raise RuntimeError("native final recompute cannot resolve atdb path")
    atdb_bytes = atdb.encode()
    inp.atdb_path = atdb_bytes
    inp.temperature_k = float(state.plasma.temperature)
    inp.electron_density_cm3 = float(state.plasma.electron_density)
    inp.hydrogen_density_cm3 = float(state.plasma.xpx)
    inp.neutral_h_density_cm3 = float(getattr(fixed, "neutral_h_density_cm3", 0.0))
    inp.ionized_h_density_cm3 = float(getattr(fixed, "ionized_h_density_cm3", max(0.0, state.plasma.xpx - inp.neutral_h_density_cm3)))
    inp.electron_fraction_xee = float(state.plasma.xee)
    inp.emission_covering_fraction = float(state.control.get("emult", 0.5))
    inp.dsec_covering_fraction = float(state.control.get("cfrac", 1.0))
    inp.turbulent_velocity_km_s = float(state.control.get("vturbi", 0.0))
    inp.abundances_by_z = _p(abund); inp.abundance_count = abund.size
    inp.radiation_energy_ev = _p(energy); inp.incident_flux = _p(incident); inp.dsec_bremsa = _p(bremsa); inp.radiation_bin_count = n
    inp.continuum_tau_in = _p(cont_tau_in); inp.continuum_tau_out = _p(cont_tau_out); inp.continuum_tau_count = cont_tau_in.size
    inp.line_tau_in = _p(line_tau_in); inp.line_tau_out = _p(line_tau_out); inp.line_tau_count = line_tau_in.size
    inp.global_xilevg = _p(gx); inp.global_bilevg = _p(gb); inp.global_rnisg = _p(gr); inp.global_level_count = gx.size

    def bind(name: str, array: np.ndarray) -> None:
        setattr(out, name, _p(array)); setattr(out, name + "_capacity", array.size)
    bind("populations", populations); bind("lte_populations", lte); bind("rcem", rcem); bind("oplin", oplin)
    bind("cemab", cemab); bind("cabab", cabab); bind("opakab", opakab); bind("rccemis", rccemis)
    bind("opakc", opakc); bind("opakcont", opakcont); bind("fline", fline); bind("flinel", flinel); bind("brcems", brcems)

    msg = ctypes.create_string_buffer(_MSG)
    import time
    t0 = time.perf_counter()
    rc = int(lib.xstar_final_recompute_run_v1(ctypes.byref(inp), ctypes.byref(out), msg, len(msg)))
    bridge_seconds = float(time.perf_counter() - t0)
    text = msg.value.decode(errors="replace")
    if rc != 0:
        raise RuntimeError(f"native final recompute failed: {text or bytes(out.message).split(bytes([0]),1)[0].decode(errors='replace')}")

    # Project exact native source workspaces into the already-owned Python arrays.
    workspace.emissivity.base.rcem[:, :] = rcem.reshape(2, nlines_guard)
    workspace.emissivity.base.oplin[:] = oplin
    workspace.emissivity.base.cemab[:, :] = cemab.reshape(2, ncont_guard)
    workspace.emissivity.base.cabab[:] = cabab
    workspace.emissivity.base.opakab[:] = opakab
    workspace.emissivity.base.rccemis[:, :n] = rccemis.reshape(2, n)
    workspace.emissivity.base.opakc[:n] = opakc
    workspace.emissivity.base.opakcont[:n] = opakcont
    workspace.emissivity.base.brcems[:n] = brcems
    workspace.emissivity.fline[:, :] = fline.reshape(2, nlines_guard)
    workspace.emissivity.flinel[:n] = flinel

    # The fixed-state bridge owns the same final local thermal solve as the
    # historical Python calc_hmc_all.  The trial xee/temperature remain the
    # caller state; computed electron fraction is retained only as a diagnostic.
    state.thermal.heating = float(out.total_heating)
    state.thermal.cooling = float(out.total_cooling)
    state.thermal.residual = float(out.hmctot)
    state.thermal.electron_fraction = float(state.plasma.xee)
    state.control["httot"] = float(out.total_heating)
    state.control["cltot"] = float(out.total_cooling)
    state.control["hmctot"] = float(out.hmctot)
    state.control["htcomp"] = float(out.compton_heating)
    state.control["clcomp"] = float(out.compton_cooling)
    state.control["htfreef"] = float(out.free_free_heating)
    state.control["clbrems"] = float(out.bremsstrahlung_cooling)

    ctx = state.control.get("calc_emis_context")
    if ctx is not None:
        ctx.temperature_1e4K = float(state.plasma.temperature) / 1.0e4
        ctx.electron_fraction_xee = float(state.plasma.xee)
        ctx.hydrogen_density_cm3 = float(state.plasma.xpx)
        ctx.zone_thickness_cm = float(np.float32(1.0e-15))
        ctx.workspace = workspace.emissivity

    counts = {name: int(getattr(out, name + "_count")) for name in (
        "populations", "lte_populations", "rcem", "oplin", "cemab", "cabab", "opakab",
        "rccemis", "opakc", "opakcont", "fline", "flinel", "brcems")}
    components = {
        "hydrogen_heating": float(out.hydrogen_heating), "hydrogen_cooling": float(out.hydrogen_cooling),
        "helium_heating": float(out.helium_heating), "helium_cooling": float(out.helium_cooling),
        "magnesium_heating": float(out.magnesium_heating), "magnesium_cooling": float(out.magnesium_cooling),
        "compton_heating": float(out.compton_heating), "compton_cooling": float(out.compton_cooling),
        "free_free_heating": float(out.free_free_heating), "bremsstrahlung_cooling": float(out.bremsstrahlung_cooling),
    }
    result = NativeFinalRecomputeResult(
        total_heating=float(out.total_heating), total_cooling=float(out.total_cooling), hmctot=float(out.hmctot),
        computed_electron_fraction=float(out.computed_electron_fraction), charge_residual=float(out.charge_residual),
        cpp_seconds=float(out.total_seconds), bridge_seconds=bridge_seconds, message=text,
        thermal_components=components, native_counts=counts,
    )
    state.local_zone.source_arrays["v0648101_native_final_recompute"] = result
    state.outputs["v0648101_native_final_recompute"] = {
        "backend": "cpp-fixed-state-bridge", "cpp_seconds": result.cpp_seconds,
        "bridge_seconds": result.bridge_seconds, "message": result.message,
        "computed_electron_fraction": result.computed_electron_fraction,
        "charge_residual": result.charge_residual, "counts": dict(counts),
        "thermal_components": dict(components),
    }
    return result
