"""Persistent native single-zone DSEC backend for accelerated Python.

v0.6.48.10.2.0.1 corrects the zone-entry source lifetime and moves one complete DSEC convergence call (20/1/17/16
fixed-state evaluations for the qualified Mg XI trajectory) behind one C ABI
call while Python retains radial transport, the accepted post-DSEC boundary
calculation, and all product writers.
"""
from __future__ import annotations

import ctypes
from pathlib import Path
from typing import Any

import numpy as np

ABI = 604810201
_MSG = 512
_DBLP = ctypes.POINTER(ctypes.c_double)
_I32P = ctypes.POINTER(ctypes.c_int32)
_LIB: ctypes.CDLL | None = None


class _Config(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32), ("abi_version", ctypes.c_uint32),
        ("atdb_path", ctypes.c_char_p),
        ("abundances_by_z", _DBLP), ("abundance_count", ctypes.c_size_t),
        ("emission_covering_fraction", ctypes.c_double),
        ("dsec_covering_fraction", ctypes.c_double),
        ("turbulent_velocity_km_s", ctypes.c_double),
    ]


class _Input(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32), ("abi_version", ctypes.c_uint32),
        ("zone_index", ctypes.c_int32), ("nlim", ctypes.c_int32),
        ("tinf_t4", ctypes.c_double), ("temperature_k", ctypes.c_double),
        ("electron_fraction_xee", ctypes.c_double),
        ("hydrogen_density_cm3", ctypes.c_double),
        ("neutral_h_density_cm3", ctypes.c_double),
        ("ionized_h_density_cm3", ctypes.c_double),
        ("radiation_energy_ev", _DBLP), ("incident_flux", _DBLP),
        ("dsec_bremsa", _DBLP), ("radiation_bin_count", ctypes.c_size_t),
        ("continuum_tau_in", _DBLP), ("continuum_tau_out", _DBLP),
        ("continuum_tau_count", ctypes.c_size_t),
        ("line_tau_in", _DBLP), ("line_tau_out", _DBLP),
        ("line_tau_count", ctypes.c_size_t),
        ("global_xilevg", _DBLP), ("global_bilevg", _DBLP),
        ("global_rnisg", _DBLP), ("global_level_count", ctypes.c_size_t),
        ("active_stage_element_z", _I32P), ("active_stage_min", _I32P),
        ("active_stage_max", _I32P), ("active_stage_window_count", ctypes.c_size_t),
    ]


class _Output(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32), ("abi_version", ctypes.c_uint32),
        ("lnerr", ctypes.c_int32), ("ntotit", ctypes.c_int32),
        ("temperature_iterations", ctypes.c_int32),
        ("temperature_attempts", ctypes.c_int32),
        ("charge_converged", ctypes.c_uint32),
        ("thermal_converged", ctypes.c_uint32),
        ("prefix_terminated", ctypes.c_uint32), ("reserved0", ctypes.c_uint32),
        ("final_temperature_t4", ctypes.c_double),
        ("final_electron_fraction_xee", ctypes.c_double),
        ("final_hmctot", ctypes.c_double), ("final_elcter", ctypes.c_double),
        ("global_xilevg", _DBLP), ("global_xilevg_capacity", ctypes.c_size_t),
        ("global_xilevg_count", ctypes.c_size_t),
        ("global_bilevg", _DBLP), ("global_bilevg_capacity", ctypes.c_size_t),
        ("global_bilevg_count", ctypes.c_size_t),
        ("global_rnisg", _DBLP), ("global_rnisg_capacity", ctypes.c_size_t),
        ("global_rnisg_count", ctypes.c_size_t),
        ("fixed_state_seconds", ctypes.c_double),
        ("dsec_orchestration_seconds", ctypes.c_double),
        ("total_seconds", ctypes.c_double),
        ("seeded_active_stage_window_count", ctypes.c_uint32),
        ("seeded_mg_min_stage", ctypes.c_int32),
        ("seeded_mg_max_stage", ctypes.c_int32),
        ("entry_neutral_h_density_cm3", ctypes.c_double),
        ("entry_ionized_h_density_cm3", ctypes.c_double),
        ("message", ctypes.c_char * _MSG),
    ]


def _p(a: np.ndarray) -> _DBLP:
    return a.ctypes.data_as(_DBLP)


def _arr(value: Any, *, n: int | None = None) -> np.ndarray:
    a = np.ascontiguousarray(np.asarray(value, dtype=np.float64).reshape(-1))
    if n is not None:
        if a.size < n:
            raise RuntimeError(f"native zone input shorter than required: {a.size} < {n}")
        a = np.ascontiguousarray(a[:n])
    return a


def _pi32(a: np.ndarray) -> _I32P:
    return a.ctypes.data_as(_I32P)


def _source_entry_active_stage_windows(state: Any, runtime: Any) -> tuple[dict[int, tuple[int, int]], float]:
    """Evaluate only the accepted source pre-matrix ion-window selector.

    The 10.2.0 native context independently widened Mg at zone entry.  The
    Python/source path decides mml/mmu before the expensive matrix/level solve,
    so 10.2.0.1 reuses that exact small pre-matrix phase to seed the persistent
    native fixed-state lifetime before DSEC evaluation 1.
    """
    import time
    from .ion_balance import CalcIonRatesContext, calc_element_pre_matrix_balance
    from .ucalc import default_source_faithful_ucalc

    started = time.perf_counter()
    requests = tuple(getattr(runtime, "element_requests", ()) or ())
    if not requests:
        raise RuntimeError("native zone active-stage selector has no element requests")
    raw_dense_x = getattr(runtime, "global_xilevg_by_index", None)
    dense_x = (
        np.zeros(0, dtype=np.float64)
        if raw_dense_x is None
        else np.asarray(raw_dense_x, dtype=np.float64).reshape(-1)
    )
    hydrogen_ground = float(dense_x[0]) if dense_x.size else 0.0
    if not np.isfinite(hydrogen_ground) or hydrogen_ground < 0.0 or hydrogen_ground > 1.0:
        raise RuntimeError("native zone entry H I ground population is invalid")
    h_abundance = next((float(r.abundance) for r in requests if int(r.element_z) == 1), 0.0)
    xpx = float(runtime.hydrogen_density_cm3)
    live_xh0 = xpx * hydrogen_ground * h_abundance
    live_xh1 = xpx * (1.0 - hydrogen_ground) * h_abundance
    dispatcher = default_source_faithful_ucalc()
    windows: dict[int, tuple[int, int]] = {}
    master = state.atomic.master
    derived = state.atomic.derived
    for request in requests:
        z = int(request.element_z)
        context = CalcIonRatesContext(
            temperature_k=float(runtime.temperature_k),
            hydrogen_density_cm3=xpx,
            electron_fraction_xee=float(runtime.electron_fraction_xee),
            radiation=request.radiation,
            covering_fraction=float(request.covering_fraction),
            turbulent_velocity_km_s=float(request.turbulent_velocity_km_s),
            neutral_h_density_cm3=live_xh0,
            ionized_h_density_cm3=live_xh1,
            lfast=int(request.lfast),
            strict_context=bool(request.strict_context),
            retain_contributions=False,
        )
        _, _, limits = calc_element_pre_matrix_balance(
            master, derived, element_z=z, context=context,
            critf=float(request.critf), dispatcher=dispatcher,
        )
        windows[z] = (int(limits.mml), int(limits.mmu))
    return windows, float(time.perf_counter() - started)


def _load() -> ctypes.CDLL:
    global _LIB
    if _LIB is not None:
        return _LIB
    path = Path(__file__).resolve().parent / "cpp" / "libxstar_zone_backend.so"
    if not path.exists():
        raise RuntimeError(f"native single-zone backend library is missing: {path}")
    lib = ctypes.CDLL(str(path))
    lib.xstar_zone_backend_bridge_abi_version.argtypes = []
    lib.xstar_zone_backend_bridge_abi_version.restype = ctypes.c_uint32
    if int(lib.xstar_zone_backend_bridge_abi_version()) != ABI:
        raise RuntimeError("native single-zone backend ABI mismatch")
    lib.xstar_zone_backend_bridge_backend_name.argtypes = []
    lib.xstar_zone_backend_bridge_backend_name.restype = ctypes.c_char_p
    lib.xstar_zone_backend_context_config_init_v1.argtypes = [ctypes.POINTER(_Config)]
    lib.xstar_zone_backend_context_config_init_v1.restype = ctypes.c_int
    lib.xstar_zone_backend_input_init_v1.argtypes = [ctypes.POINTER(_Input)]
    lib.xstar_zone_backend_input_init_v1.restype = ctypes.c_int
    lib.xstar_zone_backend_output_init_v1.argtypes = [ctypes.POINTER(_Output)]
    lib.xstar_zone_backend_output_init_v1.restype = ctypes.c_int
    lib.xstar_zone_backend_context_create_v1.argtypes = [
        ctypes.POINTER(_Config), ctypes.POINTER(ctypes.c_void_p), ctypes.c_char_p, ctypes.c_size_t
    ]
    lib.xstar_zone_backend_context_create_v1.restype = ctypes.c_int
    lib.xstar_zone_backend_context_destroy_v1.argtypes = [ctypes.c_void_p]
    lib.xstar_zone_backend_context_destroy_v1.restype = None
    lib.xstar_zone_backend_run_v1.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(_Input), ctypes.POINTER(_Output), ctypes.c_char_p, ctypes.c_size_t
    ]
    lib.xstar_zone_backend_run_v1.restype = ctypes.c_int
    _LIB = lib
    return lib


class NativeZoneContext:
    def __init__(self, state: Any):
        self._lib = _load()
        self._ptr = ctypes.c_void_p()
        cfg = _Config()
        if self._lib.xstar_zone_backend_context_config_init_v1(ctypes.byref(cfg)) != 0:
            raise RuntimeError("native zone context config initialization failed")
        atdb = str(getattr(getattr(state, "atomic", None), "atdb_path", "") or state.control.get("atdb_path", ""))
        if not atdb:
            raise RuntimeError("native zone backend cannot resolve atdb path")
        self._atdb_bytes = atdb.encode()
        abund = getattr(getattr(state, "plasma", None), "abundances", None)
        if abund is None:
            abund = state.control.get("ababs", np.zeros(30))
        self._abund = _arr(abund)
        cfg.atdb_path = self._atdb_bytes
        cfg.abundances_by_z = _p(self._abund)
        cfg.abundance_count = self._abund.size
        cfg.emission_covering_fraction = float(state.control.get("emult", 0.5))
        cfg.dsec_covering_fraction = float(state.control.get("cfrac", 1.0))
        cfg.turbulent_velocity_km_s = float(state.control.get("vturbi", 0.0))
        msg = ctypes.create_string_buffer(_MSG)
        rc = self._lib.xstar_zone_backend_context_create_v1(
            ctypes.byref(cfg), ctypes.byref(self._ptr), msg, len(msg)
        )
        if rc != 0 or not self._ptr.value:
            raise RuntimeError(f"native zone context creation failed: {msg.value.decode(errors='replace')}")
        raw_name = self._lib.xstar_zone_backend_bridge_backend_name()
        self.backend_name = raw_name.decode(errors="replace") if raw_name else "xstar_native_single_zone"

    def close(self) -> None:
        if getattr(self, "_ptr", None) is not None and self._ptr.value:
            self._lib.xstar_zone_backend_context_destroy_v1(self._ptr)
            self._ptr = ctypes.c_void_p()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass


def _get_context(state: Any) -> NativeZoneContext:
    ctx = state.control.get("native_zone_backend_context")
    if isinstance(ctx, NativeZoneContext):
        return ctx
    ctx = NativeZoneContext(state)
    state.control["native_zone_backend_context"] = ctx
    state.control["native_zone_backend_name"] = ctx.backend_name
    state.control["native_zone_backend_abi"] = ABI
    return ctx


def _global_workspaces(state: Any, runtime: Any) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[tuple[int, int, int], int]]:
    mapping = dict(getattr(runtime, "global_level_index_by_key", {}) or {})
    subset = state.control.get("active_atdb_subset")
    if not mapping and subset is not None:
        mapping = {
            (int(k[0]), int(k[1]), int(k[2])): int(v)
            for k, v in dict(getattr(subset, "global_level_index_by_key", {}) or {}).items()
        }
    n = max(mapping.values(), default=0)
    if subset is not None:
        n = max(n, int(getattr(subset, "n_global_levels_active", 0)))
    for values in (
        getattr(runtime, "global_xilevg_by_index", None),
        getattr(runtime, "global_bilevg_by_index", None),
        getattr(runtime, "global_rnisg_by_index", None),
    ):
        if values is not None:
            n = max(n, int(np.asarray(values).size))
    if n <= 0:
        raise RuntimeError("native zone backend has no global-level workspace mapping")

    def dense(values: Any) -> np.ndarray:
        if values is None:
            return np.zeros(n, dtype=np.float64)
        a = _arr(values)
        if a.size < n:
            out = np.zeros(n, dtype=np.float64)
            out[:a.size] = a
            return out
        return np.ascontiguousarray(a[:n])

    return dense(getattr(runtime, "global_xilevg_by_index", None)), dense(getattr(runtime, "global_bilevg_by_index", None)), dense(getattr(runtime, "global_rnisg_by_index", None)), mapping


def run_native_zone_dsec(state: Any, runtime: Any, *, nlim: int, tinf_t4: float):
    """Execute one complete source DSEC call in the persistent native context."""
    from .dsec import DsecResult
    from .radial_transfer import RadialTransferWorkspace

    zone = int(state.transfer.zone_index)
    if zone < 1 or zone > 4:
        raise RuntimeError(f"v0.6.48.10.2.0.1 native zone backend currently qualifies zones 1..4, got {zone}")
    workspace = state.control.get("radial_transfer_workspace")
    if not isinstance(workspace, RadialTransferWorkspace):
        raise RuntimeError("native zone backend requires RadialTransferWorkspace")

    n = int(state.control.get("ncn2", 0))
    if n <= 1:
        raise RuntimeError("native zone backend has invalid continuum size")
    energy = _arr(state.radiation.epi, n=n)
    incident = _arr(workspace.zremsz, n=n)
    bremsa = _arr(state.radiation.bremsa, n=n)
    tauc = np.asarray(workspace.tauc, dtype=np.float64)
    tau0 = np.asarray(workspace.tau0, dtype=np.float64)
    cont_in = _arr(tauc[0]); cont_out = _arr(tauc[1])
    line_in = _arr(tau0[0]); line_out = _arr(tau0[1])
    gx, gb, gr, mapping = _global_workspaces(state, runtime)
    out_x = np.zeros_like(gx); out_b = np.zeros_like(gb); out_r = np.zeros_like(gr)

    # Literal calc_hmc_all entry lifetime: xh0/xh1 come from the incoming
    # global H I ground population.  A legitimate xh0=0 must remain zero.
    h_abundance = next((float(r.abundance) for r in runtime.element_requests if int(r.element_z) == 1), 0.0)
    h_ground = float(gx[0]) if gx.size else 0.0
    if not np.isfinite(h_ground) or h_ground < 0.0 or h_ground > 1.0:
        raise RuntimeError("native zone entry H I ground population is invalid")
    neutral_h = float(runtime.hydrogen_density_cm3) * h_ground * h_abundance
    ionized_h = float(runtime.hydrogen_density_cm3) * (1.0 - h_ground) * h_abundance

    active_windows, selector_seconds = _source_entry_active_stage_windows(state, runtime)
    active_z = np.ascontiguousarray(sorted(active_windows), dtype=np.int32)
    active_min = np.ascontiguousarray([active_windows[int(z)][0] for z in active_z], dtype=np.int32)
    active_max = np.ascontiguousarray([active_windows[int(z)][1] for z in active_z], dtype=np.int32)

    inp = _Input(); out = _Output(); ctx = _get_context(state); lib = ctx._lib
    if lib.xstar_zone_backend_input_init_v1(ctypes.byref(inp)) != 0:
        raise RuntimeError("native zone input initialization failed")
    if lib.xstar_zone_backend_output_init_v1(ctypes.byref(out)) != 0:
        raise RuntimeError("native zone output initialization failed")
    inp.zone_index = zone
    inp.nlim = int(nlim)
    inp.tinf_t4 = float(tinf_t4)
    inp.temperature_k = float(runtime.temperature_k)
    inp.electron_fraction_xee = float(runtime.electron_fraction_xee)
    inp.hydrogen_density_cm3 = float(runtime.hydrogen_density_cm3)
    inp.neutral_h_density_cm3 = neutral_h
    inp.ionized_h_density_cm3 = ionized_h
    inp.radiation_energy_ev = _p(energy); inp.incident_flux = _p(incident); inp.dsec_bremsa = _p(bremsa); inp.radiation_bin_count = n
    inp.continuum_tau_in = _p(cont_in); inp.continuum_tau_out = _p(cont_out); inp.continuum_tau_count = cont_in.size
    inp.line_tau_in = _p(line_in); inp.line_tau_out = _p(line_out); inp.line_tau_count = line_in.size
    inp.global_xilevg = _p(gx); inp.global_bilevg = _p(gb); inp.global_rnisg = _p(gr); inp.global_level_count = gx.size
    inp.active_stage_element_z = _pi32(active_z); inp.active_stage_min = _pi32(active_min); inp.active_stage_max = _pi32(active_max); inp.active_stage_window_count = active_z.size
    out.global_xilevg = _p(out_x); out.global_xilevg_capacity = out_x.size
    out.global_bilevg = _p(out_b); out.global_bilevg_capacity = out_b.size
    out.global_rnisg = _p(out_r); out.global_rnisg_capacity = out_r.size

    msg = ctypes.create_string_buffer(_MSG)
    rc = lib.xstar_zone_backend_run_v1(ctx._ptr, ctypes.byref(inp), ctypes.byref(out), msg, len(msg))
    if rc != 0:
        detail = msg.value.decode(errors="replace") or bytes(out.message).split(b"\0", 1)[0].decode(errors="replace")
        raise RuntimeError(f"native single-zone DSEC solve failed: {detail}")
    nx, nb, nr = int(out.global_xilevg_count), int(out.global_bilevg_count), int(out.global_rnisg_count)
    if not (nx == nb == nr == gx.size):
        raise RuntimeError(f"native zone global workspace size mismatch: {nx}/{nb}/{nr} vs {gx.size}")
    if int(out.seeded_active_stage_window_count) != int(active_z.size):
        raise RuntimeError("native zone did not install every source active-stage seed")
    if 12 in active_windows:
        expected_mg = active_windows[12]
        if (int(out.seeded_mg_min_stage), int(out.seeded_mg_max_stage)) != expected_mg:
            raise RuntimeError(
                "native zone Mg active-stage seed mismatch: "
                f"native={int(out.seeded_mg_min_stage)}..{int(out.seeded_mg_max_stage)} "
                f"source={expected_mg[0]}..{expected_mg[1]}"
            )

    runtime.temperature_t4 = float(out.final_temperature_t4)
    runtime.electron_fraction_xee = float(out.final_electron_fraction_xee)
    runtime.global_xilevg_by_index = out_x.copy()
    runtime.global_bilevg_by_index = out_b.copy()
    runtime.global_rnisg_by_index = out_r.copy()
    runtime.global_level_index_by_key = mapping
    runtime.global_level_populations = {
        key: float(out_x[index - 1])
        for key, index in mapping.items()
        if 1 <= int(index) <= out_x.size
    }
    runtime.last_hmctot = float(out.final_hmctot)
    runtime.last_elcter = float(out.final_elcter)
    runtime.calc_hmc_all_call_count += int(out.ntotit)
    # Compact qualification markers: four lines per run, no per-evaluation I/O.
    mg_window = active_windows.get(12, (0, 0))
    print(
        f"V064810201_ZONE{zone}_ENTRY_SOURCE_MG_STAGE_WINDOW="
        f"{int(mg_window[0])}..{int(mg_window[1])}"
    )
    print(
        f"V064810201_ZONE{zone}_ENTRY_H_DENSITIES="
        f"{float(out.entry_neutral_h_density_cm3):.17g};"
        f"{float(out.entry_ionized_h_density_cm3):.17g}"
    )
    print(
        f"V064810201_ZONE{zone}_NATIVE_DSEC_TERMINAL="
        f"T4={float(out.final_temperature_t4):.17g};"
        f"XEE={float(out.final_electron_fraction_xee):.17g};"
        f"HMCTOT={float(out.final_hmctot):.17g};"
        f"ELCTER={float(out.final_elcter):.17g};"
        f"NTOTIT={int(out.ntotit)}"
    )
    print(
        f"V064810201_ZONE{zone}_NATIVE_DSEC_SECONDS="
        f"{float(out.total_seconds):.9f};SELECTOR={float(selector_seconds):.9f}"
    )
    runtime.provenance.update({
        "dsec_native_orchestration": True,
        "dsec_native_single_zone_backend": True,
        "dsec_native_zone_backend_name": ctx.backend_name,
        "dsec_native_zone_backend_abi": ABI,
        "dsec_orchestration_seconds": float(out.dsec_orchestration_seconds),
        "dsec_fixed_state_seconds": float(out.fixed_state_seconds),
        "dsec_zone_backend_total_seconds": float(out.total_seconds),
        "dsec_entry_active_stage_selector_seconds": float(selector_seconds),
        "dsec_entry_active_stage_windows": {int(z): [int(v[0]), int(v[1])] for z, v in active_windows.items()},
        "dsec_entry_mg_min_stage": int(active_windows.get(12, (0, 0))[0]),
        "dsec_entry_mg_max_stage": int(active_windows.get(12, (0, 0))[1]),
        "dsec_entry_neutral_h_density_cm3": float(out.entry_neutral_h_density_cm3),
        "dsec_entry_ionized_h_density_cm3": float(out.entry_ionized_h_density_cm3),
        "dsec_callback_seconds": 0.0,
        "dsec_callback_state_propagation": False,
        "dsec_trace_count": 0,
        "dsec_trace_truncated": False,
        "dsec_ntotit": int(out.ntotit),
        "dsec_lnerr": int(out.lnerr),
        "dsec_prefix_terminated": bool(out.prefix_terminated),
    })
    maximum = (20, 1, 17, 16)[zone - 1]
    return DsecResult(
        state=runtime,
        trajectory=(),
        nlim=int(nlim),
        tinf_t4=float(tinf_t4),
        lnerr=int(out.lnerr),
        ntotit=int(out.ntotit),
        temperature_iterations=int(out.temperature_iterations),
        temperature_attempts=int(out.temperature_attempts),
        charge_converged=bool(out.charge_converged),
        thermal_converged=bool(out.thermal_converged),
        requested_thermal_iteration=int(nlim) > 0,
        source_returned=not bool(out.prefix_terminated),
        prefix_terminated=bool(out.prefix_terminated),
        maximum_evaluations=maximum,
    )


__all__ = ["ABI", "NativeZoneContext", "run_native_zone_dsec"]
