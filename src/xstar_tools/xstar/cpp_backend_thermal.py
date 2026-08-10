# XSTAR-PYTHON-SOURCE-CORRESPONDENCE-BEGIN
# Source correspondence:
#   Fortran: calc_hmc_all.f90 / heatf.f90 / dsec.f90
#   Role: Python/native bridge for fixed-state thermal/controller calculations.
#   Relation: Backend bridge only; source arithmetic/order is owned by native thermal/fixed-state engines.
#   Concordance: THERM-001; DSEC-001
#   Qualification: accepted science revision 0.6.48.12.3.45.3.3.8; frozen C++ baseline 0.6.48.12.3.44.
# XSTAR-PYTHON-SOURCE-CORRESPONDENCE-END

"""Persistent native thermal-transfer and convergence engine for v0.6.48.3.

The native library owns the translated ``heatt`` arithmetic and the complete
``dsec`` temperature/electron iteration state machine.  The fixed-state
``calc_hmc_all`` evaluation remains an explicit callback in this candidate so
existing atomic-data and state-commit semantics are preserved while Python no
longer owns the convergence loop.
"""
from __future__ import annotations

import ctypes
import os
from pathlib import Path
import threading
import time
from typing import Any, Callable, Iterable, Mapping

import numpy as np

_ABI = 60471
_LIB: ctypes.CDLL | None = None
_TLS = threading.local()


class _HeattWorkspace(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32), ("abi_version", ctypes.c_uint32),
        ("flags", ctypes.c_uint32), ("reserved0", ctypes.c_uint32),
        ("temperature_t4", ctypes.c_double), ("radius_cm", ctypes.c_double),
        ("covering_fraction", ctypes.c_double), ("zone_thickness_cm", ctypes.c_double),
        ("electron_fraction_xee", ctypes.c_double), ("hydrogen_density_cm3", ctypes.c_double),
        ("epi_eV", ctypes.POINTER(ctypes.c_double)), ("bremsa", ctypes.POINTER(ctypes.c_double)),
        ("opakc", ctypes.POINTER(ctypes.c_double)), ("opakcont", ctypes.POINTER(ctypes.c_double)),
        ("flinel", ctypes.POINTER(ctypes.c_double)), ("brcems", ctypes.POINTER(ctypes.c_double)),
        ("ncn2", ctypes.c_size_t),
        ("zrems", ctypes.POINTER(ctypes.c_double)), ("zremso", ctypes.POINTER(ctypes.c_double)),
        ("zrems_count", ctypes.c_size_t),
        ("elum", ctypes.POINTER(ctypes.c_double)), ("elumo", ctypes.POINTER(ctypes.c_double)),
        ("rcem", ctypes.POINTER(ctypes.c_double)), ("n_lines", ctypes.c_size_t),
        ("elumab", ctypes.POINTER(ctypes.c_double)), ("elumabo", ctypes.POINTER(ctypes.c_double)),
        ("cemab", ctypes.POINTER(ctypes.c_double)), ("n_continua", ctypes.c_size_t),
        ("rccemis", ctypes.POINTER(ctypes.c_double)), ("rccemis_count", ctypes.c_size_t),
    ]


class _HeattLine(ctypes.Structure):
    _fields_ = [
        ("record", ctypes.c_int64), ("rate_type", ctypes.c_int32),
        ("reserved0", ctypes.c_int32), ("wavelength_angstrom", ctypes.c_double),
    ]


class _HeattRRC(ctypes.Structure):
    _fields_ = [
        ("record", ctypes.c_int64), ("continuum_index_one_based", ctypes.c_int32),
        ("destination_level", ctypes.c_int32), ("active", ctypes.c_uint32),
        ("reserved0", ctypes.c_uint32),
    ]


class _HeattStats(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32), ("abi_version", ctypes.c_uint32),
        ("status_flags", ctypes.c_uint32), ("reserved0", ctypes.c_uint32),
        ("calls", ctypes.c_uint64), ("continuum_bins", ctypes.c_uint64),
        ("line_records", ctypes.c_uint64), ("rrc_records", ctypes.c_uint64),
        ("state_commits", ctypes.c_uint64),
        ("continuum_seconds", ctypes.c_double), ("line_seconds", ctypes.c_double),
        ("rrc_seconds", ctypes.c_double), ("commit_seconds", ctypes.c_double),
        ("fpr2", ctypes.c_double), ("continuum_net_integral", ctypes.c_double),
        ("continuum_positive_integral", ctypes.c_double),
        ("pre_compton_heating", ctypes.c_double), ("pre_compton_cooling", ctypes.c_double),
        ("bremsstrahlung_integral", ctypes.c_double),
    ]


class _DsecConfig(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32), ("abi_version", ctypes.c_uint32),
        ("nlim", ctypes.c_int32), ("maximum_evaluations", ctypes.c_int32),
        ("tinf_t4", ctypes.c_double), ("charge_tolerance", ctypes.c_double),
        ("thermal_tolerance", ctypes.c_double),
        ("temperature_stagnation_tolerance", ctypes.c_double),
    ]


class _ThermalState(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32), ("abi_version", ctypes.c_uint32),
        ("flags", ctypes.c_uint32), ("reserved0", ctypes.c_uint32),
        ("temperature_t4", ctypes.c_double), ("electron_fraction_xee", ctypes.c_double),
        ("hydrogen_density_cm3", ctypes.c_double), ("state_generation", ctypes.c_uint64),
    ]


class _Evaluation(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32), ("abi_version", ctypes.c_uint32),
        ("flags", ctypes.c_uint32), ("reserved0", ctypes.c_uint32),
        ("hmctot", ctypes.c_double), ("elcter", ctypes.c_double),
        ("temperature_t4", ctypes.c_double), ("electron_fraction_xee", ctypes.c_double),
        ("hydrogen_density_cm3", ctypes.c_double), ("state_generation", ctypes.c_uint64),
    ]


class _Trace(ctypes.Structure):
    _fields_ = [
        ("event_code", ctypes.c_uint32), ("evaluation_index", ctypes.c_uint32),
        ("ntotit", ctypes.c_int32), ("nnt", ctypes.c_int32), ("nntt", ctypes.c_int32),
        ("nnx", ctypes.c_int32), ("nnxx", ctypes.c_int32), ("lnerr", ctypes.c_int32),
        ("temperature_t4", ctypes.c_double), ("electron_fraction_xee", ctypes.c_double),
        ("hmctot", ctypes.c_double), ("elcter", ctypes.c_double),
        ("normalized_charge_residual", ctypes.c_double),
        ("temperature_stagnation_metric", ctypes.c_double),
    ]


class _DsecStats(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32), ("abi_version", ctypes.c_uint32),
        ("status_flags", ctypes.c_uint32), ("reserved0", ctypes.c_uint32),
        ("lnerr", ctypes.c_int32), ("ntotit", ctypes.c_int32),
        ("temperature_iterations", ctypes.c_int32), ("temperature_attempts", ctypes.c_int32),
        ("charge_converged", ctypes.c_uint32), ("thermal_converged", ctypes.c_uint32),
        ("prefix_terminated", ctypes.c_uint32), ("reserved1", ctypes.c_uint32),
        ("evaluations_requested", ctypes.c_uint64), ("evaluations_completed", ctypes.c_uint64),
        ("state_commits", ctypes.c_uint64),
        ("orchestration_seconds", ctypes.c_double), ("callback_seconds", ctypes.c_double),
        ("final_hmctot", ctypes.c_double), ("final_elcter", ctypes.c_double),
        ("final_charge_residual", ctypes.c_double),
        ("final_temperature_t4", ctypes.c_double),
        ("final_electron_fraction_xee", ctypes.c_double),
        ("final_temperature_stagnation_metric", ctypes.c_double),
    ]

_EVALUATOR = ctypes.CFUNCTYPE(
    ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(_ThermalState),
    ctypes.POINTER(_Evaluation), ctypes.c_char_p, ctypes.c_size_t,
)


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the p operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: Backend adapter/provenance helper; the underlying scientific routine is documented in the corresponding XSTAR Manual section.
# XSTAR-FUNCTION-COMMENT-END
def _p(a: np.ndarray) -> ctypes.POINTER(ctypes.c_double):
    return a.ctypes.data_as(ctypes.POINTER(ctypes.c_double))


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Load operation for this module while preserving the surrounding source/runtime invariants.
# Reference context: Backend adapter/provenance helper; the underlying scientific routine is documented in the corresponding XSTAR Manual section.
# XSTAR-FUNCTION-COMMENT-END
def _load() -> ctypes.CDLL:
    global _LIB
    if _LIB is not None:
        return _LIB
    paths = []
    explicit = os.environ.get("XSTAR_ATOMIC_THERMAL_LIB", "").strip()
    if explicit:
        paths.append(Path(explicit))
    paths.append(Path(__file__).resolve().parent / "cpp" / "libxstar_thermal.so")
    errors: list[str] = []
    for path in paths:
        try:
            lib = ctypes.CDLL(str(path))
            lib.xstar_thermal_engine_abi_version.restype = ctypes.c_uint32
            if int(lib.xstar_thermal_engine_abi_version()) != _ABI:
                raise RuntimeError("thermal ABI mismatch")
            lib.xstar_thermal_engine_backend_name.restype = ctypes.c_char_p
            lib.xstar_thermal_engine_feature_flags.restype = ctypes.c_uint32
            lib.xstar_thermal_context_create_v1.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_char_p, ctypes.c_size_t]
            lib.xstar_thermal_context_create_v1.restype = ctypes.c_int
            lib.xstar_thermal_context_destroy.argtypes = [ctypes.c_void_p]
            lib.xstar_thermal_apply_heatt_v1.argtypes = [
                ctypes.c_void_p, ctypes.POINTER(_HeattWorkspace),
                ctypes.POINTER(_HeattLine), ctypes.c_size_t,
                ctypes.POINTER(_HeattRRC), ctypes.c_size_t,
                ctypes.POINTER(_HeattStats), ctypes.c_char_p, ctypes.c_size_t,
            ]
            lib.xstar_thermal_apply_heatt_v1.restype = ctypes.c_int
            lib.xstar_thermal_run_evaluation_loop_v1.argtypes = [
                ctypes.c_void_p, ctypes.POINTER(_DsecConfig), ctypes.POINTER(_ThermalState),
                _EVALUATOR, ctypes.c_void_p, ctypes.POINTER(_Trace), ctypes.c_size_t,
                ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(_DsecStats),
                ctypes.c_char_p, ctypes.c_size_t,
            ]
            lib.xstar_thermal_run_evaluation_loop_v1.restype = ctypes.c_int
            _LIB = lib
            return lib
        except Exception as exc:
            errors.append(f"{path}: {exc}")
    raise RuntimeError("; ".join(errors))


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the context operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: Backend adapter/provenance helper; the underlying scientific routine is documented in the corresponding XSTAR Manual section.
# XSTAR-FUNCTION-COMMENT-END
def _context() -> ctypes.c_void_p:
    value = getattr(_TLS, "context", None)
    if value:
        return value
    lib = _load()
    out = ctypes.c_void_p()
    error = ctypes.create_string_buffer(1024)
    rc = lib.xstar_thermal_context_create_v1(ctypes.byref(out), error, len(error))
    if rc != 0:
        raise RuntimeError(error.value.decode("utf-8", "replace"))
    _TLS.context = out
    return out


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the thermal engine status operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: Backend adapter/provenance helper; the underlying scientific routine is documented in the corresponding XSTAR Manual section.
# XSTAR-FUNCTION-COMMENT-END
def thermal_engine_status() -> dict[str, Any]:
    try:
        lib = _load()
        raw = lib.xstar_thermal_engine_backend_name()
        return {
            "available": True,
            "abi_version": int(lib.xstar_thermal_engine_abi_version()),
            "implementation": raw.decode() if raw else "unknown",
            "feature_flags": int(lib.xstar_thermal_engine_feature_flags()),
        }
    except Exception as exc:
        return {"available": False, "abi_version": None, "implementation": None, "feature_flags": 0, "load_error": str(exc)}


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the f64 operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: Backend adapter/provenance helper; the underlying scientific routine is documented in the corresponding XSTAR Manual section.
# XSTAR-FUNCTION-COMMENT-END
def _f64(value: Any) -> np.ndarray:
    return np.ascontiguousarray(np.asarray(value, dtype=np.float64))


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Apply heatt cpp for this module while preserving the surrounding source/runtime invariants.
# Reference context: Backend adapter/provenance helper; the underlying scientific routine is documented in the corresponding XSTAR Manual section.
# XSTAR-FUNCTION-COMMENT-END
def apply_heatt_cpp(*, lines: Iterable[Mapping[str, Any]], rrcs: Iterable[Mapping[str, Any]], **values: Any) -> dict[str, Any]:
    lib = _load()
    started = time.perf_counter()
    arrays = {name: _f64(values[name]) for name in (
        "epi_eV", "bremsa", "opakc", "opakcont", "flinel", "brcems",
        "zrems", "zremso", "elum", "elumo", "rcem", "elumab", "elumabo",
        "cemab", "rccemis",
    )}
    line_rows = list(lines)
    rrc_rows = list(rrcs)
    packed_lines = (_HeattLine * len(line_rows))(*[
        _HeattLine(int(row.get("record", 0)), int(row.get("rate_type", 0)), 0, float(row.get("wavelength_angstrom", 0.0)))
        for row in line_rows
    ]) if line_rows else None
    packed_rrcs = (_HeattRRC * len(rrc_rows))(*[
        _HeattRRC(int(row.get("record", 0)), int(row.get("continuum_index_one_based", 0)),
                  int(row.get("destination_level", 0)), int(bool(row.get("active", False))), 0)
        for row in rrc_rows
    ]) if rrc_rows else None
    n = int(values["ncn2"]); nl = int(values["n_lines"]); nc = int(values["n_continua"])
    workspace = _HeattWorkspace(
        ctypes.sizeof(_HeattWorkspace), _ABI, 0, 0,
        float(values["temperature_1e4K"]), float(values["radius_cm"]),
        float(values["covering_fraction"]), float(values["zone_thickness_cm"]),
        float(values["electron_fraction_xee"]), float(values["hydrogen_density_cm3"]),
        _p(arrays["epi_eV"]), _p(arrays["bremsa"]), _p(arrays["opakc"]),
        _p(arrays["opakcont"]), _p(arrays["flinel"]), _p(arrays["brcems"]), n,
        _p(arrays["zrems"]), _p(arrays["zremso"]), arrays["zrems"].size,
        _p(arrays["elum"]), _p(arrays["elumo"]), _p(arrays["rcem"]), nl,
        _p(arrays["elumab"]), _p(arrays["elumabo"]), _p(arrays["cemab"]), nc,
        _p(arrays["rccemis"]), arrays["rccemis"].size,
    )
    stats = _HeattStats(ctypes.sizeof(_HeattStats), _ABI)
    error = ctypes.create_string_buffer(1024)
    rc = lib.xstar_thermal_apply_heatt_v1(
        _context(), ctypes.byref(workspace), packed_lines, len(line_rows), packed_rrcs,
        len(rrc_rows), ctypes.byref(stats), error, len(error),
    )
    if rc != 0:
        raise RuntimeError(error.value.decode("utf-8", "replace") or f"native heatt failed: {rc}")
    for name in ("zrems", "elum", "elumab"):
        np.copyto(np.asarray(values[name]), arrays[name].reshape(np.asarray(values[name]).shape))
    return {
        "schema_version": "0.6.48.3", "calls": int(stats.calls),
        "continuum_bins": int(stats.continuum_bins), "line_records": int(stats.line_records),
        "rrc_records": int(stats.rrc_records), "state_commits": int(stats.state_commits),
        "continuum_seconds": float(stats.continuum_seconds), "line_seconds": float(stats.line_seconds),
        "rrc_seconds": float(stats.rrc_seconds), "commit_seconds": float(stats.commit_seconds),
        "ffi_seconds": time.perf_counter() - started,
        "fpr2": float(stats.fpr2), "continuum_net_integral": float(stats.continuum_net_integral),
        "continuum_positive_integral": float(stats.continuum_positive_integral),
        "pre_compton_heating": float(stats.pre_compton_heating),
        "pre_compton_cooling": float(stats.pre_compton_cooling),
        "bremsstrahlung_integral": float(stats.bremsstrahlung_integral),
        "native_heatt": True,
    }


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Execute dsec cpp for this module while preserving the surrounding source/runtime invariants.
# Reference context: Backend adapter/provenance helper; the underlying scientific routine is documented in the corresponding XSTAR Manual section.
# XSTAR-FUNCTION-COMMENT-END
def run_dsec_cpp(state: Any, evaluator: Callable[[Any], Any], *, nlim: int, tinf_t4: float,
                  charge_tolerance: float, thermal_tolerance: float,
                  temperature_stagnation_tolerance: float,
                  maximum_evaluations: int | None = None, trace_capacity: int = 4096) -> dict[str, Any]:
    lib = _load()
    config = _DsecConfig(
        ctypes.sizeof(_DsecConfig), _ABI, int(nlim), int(maximum_evaluations or 0),
        float(tinf_t4), float(charge_tolerance), float(thermal_tolerance),
        float(temperature_stagnation_tolerance),
    )
    native_state = _ThermalState(
        ctypes.sizeof(_ThermalState), _ABI, 0, 0,
        float(state.temperature_t4), float(state.electron_fraction_xee),
        float(state.hydrogen_density_cm3), int(getattr(state, "calc_hmc_all_call_count", 0)),
    )
    callback_error: list[BaseException] = []

    # XSTAR-FUNCTION-COMMENT-BEGIN
    # Purpose: Implement the callback operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
    # Reference context: Backend adapter/provenance helper; the underlying scientific routine is documented in the corresponding XSTAR Manual section.
    # XSTAR-FUNCTION-COMMENT-END
    @_EVALUATOR
    def callback(_user: int, trial: ctypes.POINTER(_ThermalState), output: ctypes.POINTER(_Evaluation),
                 _error: bytes, _error_size: int) -> int:
        try:
            item = trial.contents
            state.temperature_t4 = float(item.temperature_t4)
            state.electron_fraction_xee = float(item.electron_fraction_xee)
            state.hydrogen_density_cm3 = float(item.hydrogen_density_cm3)
            result = evaluator(state)
            out = output.contents
            out.struct_size = ctypes.sizeof(_Evaluation)
            out.abi_version = _ABI
            out.hmctot = float(result.hmctot)
            out.elcter = float(result.elcter)
            # calc_hmc_all commits temperature/electron state before returning.
            # Preserve that source state across the native callback boundary.
            out.temperature_t4 = float(state.temperature_t4)
            out.electron_fraction_xee = float(state.electron_fraction_xee)
            out.hydrogen_density_cm3 = float(state.hydrogen_density_cm3)
            out.state_generation = int(getattr(state, "calc_hmc_all_call_count", 0))
            return 0
        except BaseException as exc:  # callback boundary
            callback_error.append(exc)
            return 1

    trace = (_Trace * int(trace_capacity))()
    trace_count = ctypes.c_size_t()
    stats = _DsecStats(ctypes.sizeof(_DsecStats), _ABI)
    error = ctypes.create_string_buffer(2048)
    rc = lib.xstar_thermal_run_evaluation_loop_v1(
        _context(), ctypes.byref(config), ctypes.byref(native_state), callback, None,
        trace, len(trace), ctypes.byref(trace_count), ctypes.byref(stats), error, len(error),
    )
    if rc != 0:
        if callback_error:
            raise RuntimeError("native dsec evaluator callback failed") from callback_error[0]
        raise RuntimeError(error.value.decode("utf-8", "replace") or f"native dsec failed: {rc}")
    state.temperature_t4 = float(native_state.temperature_t4)
    state.electron_fraction_xee = float(native_state.electron_fraction_xee)
    state.hydrogen_density_cm3 = float(native_state.hydrogen_density_cm3)
    rows = []
    for i in range(min(int(trace_count.value), len(trace))):
        row = trace[i]
        rows.append({name: getattr(row, name) for name, _ctype in _Trace._fields_})
    return {
        "schema_version": "0.6.48.3", "lnerr": int(stats.lnerr), "ntotit": int(stats.ntotit),
        "temperature_iterations": int(stats.temperature_iterations),
        "temperature_attempts": int(stats.temperature_attempts),
        "charge_converged": bool(stats.charge_converged),
        "thermal_converged": bool(stats.thermal_converged),
        "prefix_terminated": bool(stats.prefix_terminated),
        "evaluations_requested": int(stats.evaluations_requested),
        "evaluations_completed": int(stats.evaluations_completed),
        "state_commits": int(stats.state_commits),
        "orchestration_seconds": float(stats.orchestration_seconds),
        "callback_seconds": float(stats.callback_seconds),
        "final_hmctot": float(stats.final_hmctot), "final_elcter": float(stats.final_elcter),
        "final_charge_residual": float(stats.final_charge_residual),
        "final_temperature_t4": float(stats.final_temperature_t4),
        "final_electron_fraction_xee": float(stats.final_electron_fraction_xee),
        "final_temperature_stagnation_metric": float(stats.final_temperature_stagnation_metric),
        "trace_count": int(trace_count.value),
        "trace_truncated": bool(int(trace_count.value) > len(trace)),
        "trace": rows, "native_dsec": True, "callback_evaluation": True,
        "callback_state_propagation": True,
    }
