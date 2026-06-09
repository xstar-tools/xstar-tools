"""Persistent native emissivity/opacity contribution engine for v0.6.46.1.

Python retains atomic-data traversal and scalar UCalc evaluation in this
candidate.  Source-ordered line/RRC/continuum contribution construction,
line-profile opacity, and workspace commit are performed by
``libxstar_emissivity.so`` linked to ``libxstar_opacity.so``.
"""
from __future__ import annotations

import ctypes
import os
from pathlib import Path
import threading
import time
from typing import Any, Iterable, Mapping

import numpy as np

_ABI = 60460
_LIB: ctypes.CDLL | None = None
_LOAD_ERROR: str | None = None
_TLS = threading.local()

KIND_EMISAB_BOUND_FREE = 1
KIND_EMISAB_LINE = 2
KIND_EMIS_OPACITY_ONLY = 3
KIND_EMIS_LINE = 4


class _Contribution(ctypes.Structure):
    _fields_ = [
        ("source_position", ctypes.c_uint64),
        ("record", ctypes.c_int64),
        ("kind", ctypes.c_uint32),
        ("rate_type", ctypes.c_int32),
        ("data_type", ctypes.c_int32),
        ("output_index", ctypes.c_int32),
        ("bin_one_based", ctypes.c_int32),
        ("reserved0", ctypes.c_int32),
        ("reserved1", ctypes.c_int32),
        ("ptmp1", ctypes.c_double),
        ("ptmp2", ctypes.c_double),
        ("abundance_lower", ctypes.c_double),
        ("abundance_upper", ctypes.c_double),
        ("hydrogen_density", ctypes.c_double),
        ("ans1", ctypes.c_double),
        ("ans2", ctypes.c_double),
        ("ans3", ctypes.c_double),
        ("ans4", ctypes.c_double),
        ("opakab", ctypes.c_double),
        ("line_energy_eV", ctypes.c_double),
        ("bin_width_eV", ctypes.c_double),
        ("atomic_mass_amu", ctypes.c_double),
        ("natural_width_eV", ctypes.c_double),
        ("turbulent_velocity_km_s", ctypes.c_double),
        ("temperature_1e4K", ctypes.c_double),
    ]


class _Workspace(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("abi_version", ctypes.c_uint32),
        ("flags", ctypes.c_uint32),
        ("reserved0", ctypes.c_uint32),
        ("rcem", ctypes.POINTER(ctypes.c_double)), ("rcem_count", ctypes.c_size_t),
        ("oplin", ctypes.POINTER(ctypes.c_double)), ("oplin_count", ctypes.c_size_t),
        ("cemab", ctypes.POINTER(ctypes.c_double)), ("cemab_count", ctypes.c_size_t),
        ("cabab", ctypes.POINTER(ctypes.c_double)), ("cabab_count", ctypes.c_size_t),
        ("opakab", ctypes.POINTER(ctypes.c_double)), ("opakab_count", ctypes.c_size_t),
        ("rccemis", ctypes.POINTER(ctypes.c_double)), ("rccemis_count", ctypes.c_size_t),
        ("opakc", ctypes.POINTER(ctypes.c_double)), ("opakc_count", ctypes.c_size_t),
        ("opakcont", ctypes.POINTER(ctypes.c_double)), ("opakcont_count", ctypes.c_size_t),
        ("fline", ctypes.POINTER(ctypes.c_double)), ("fline_count", ctypes.c_size_t),
        ("flinel", ctypes.POINTER(ctypes.c_double)), ("flinel_count", ctypes.c_size_t),
        ("epi_eV", ctypes.POINTER(ctypes.c_double)), ("energy_count", ctypes.c_size_t),
    ]


class _Stats(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("abi_version", ctypes.c_uint32),
        ("status_flags", ctypes.c_uint32),
        ("reserved0", ctypes.c_uint32),
        ("calls", ctypes.c_uint64),
        ("contributions_attempted", ctypes.c_uint64),
        ("contributions_committed", ctypes.c_uint64),
        ("emissivity_contributions", ctypes.c_uint64),
        ("opacity_contributions", ctypes.c_uint64),
        ("line_profiles", ctypes.c_uint64),
        ("source_order_violations", ctypes.c_uint64),
        ("construction_seconds", ctypes.c_double),
        ("opacity_seconds", ctypes.c_double),
        ("commit_seconds", ctypes.c_double),
    ]


def _p(array: np.ndarray) -> ctypes.POINTER(ctypes.c_double):
    return array.ctypes.data_as(ctypes.POINTER(ctypes.c_double))


def _load() -> ctypes.CDLL:
    global _LIB, _LOAD_ERROR
    if _LIB is not None:
        return _LIB
    candidates: list[Path] = []
    explicit = os.environ.get("XSTAR_ATOMIC_EMISSIVITY_LIB", "").strip()
    if explicit:
        candidates.append(Path(explicit))
    candidates.append(Path(__file__).resolve().parent / "cpp" / "libxstar_emissivity.so")
    errors: list[str] = []
    for path in candidates:
        try:
            lib = ctypes.CDLL(str(path))
            lib.xstar_spectral_engine_abi_version.restype = ctypes.c_uint32
            if int(lib.xstar_spectral_engine_abi_version()) != _ABI:
                raise RuntimeError(
                    f"spectral-engine ABI mismatch: {lib.xstar_spectral_engine_abi_version()} != {_ABI}"
                )
            lib.xstar_spectral_engine_backend_name.restype = ctypes.c_char_p
            lib.xstar_spectral_engine_feature_flags.restype = ctypes.c_uint32
            lib.xstar_spectral_context_create_v1.argtypes = [
                ctypes.POINTER(ctypes.c_void_p), ctypes.c_char_p, ctypes.c_size_t
            ]
            lib.xstar_spectral_context_create_v1.restype = ctypes.c_int
            lib.xstar_spectral_context_destroy.argtypes = [ctypes.c_void_p]
            lib.xstar_spectral_context_destroy.restype = None
            lib.xstar_spectral_apply_contributions_v1.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(_Contribution), ctypes.c_size_t,
                ctypes.POINTER(ctypes.c_double), ctypes.c_size_t,
                ctypes.POINTER(_Workspace), ctypes.POINTER(_Stats),
                ctypes.c_char_p, ctypes.c_size_t,
            ]
            lib.xstar_spectral_apply_contributions_v1.restype = ctypes.c_int
            _LIB = lib
            _LOAD_ERROR = None
            return lib
        except Exception as exc:  # pragma: no cover - environment dependent
            errors.append(f"{path}: {exc}")
    _LOAD_ERROR = "; ".join(errors)
    raise RuntimeError(_LOAD_ERROR or "libxstar_emissivity.so unavailable")


def _context() -> ctypes.c_void_p:
    value = getattr(_TLS, "context", None)
    if value:
        return value
    lib = _load()
    out = ctypes.c_void_p()
    error = ctypes.create_string_buffer(1024)
    rc = lib.xstar_spectral_context_create_v1(ctypes.byref(out), error, len(error))
    if rc != 0 or not out.value:
        raise RuntimeError(error.value.decode("utf-8", "replace") or f"spectral context create failed: {rc}")
    _TLS.context = out
    return out


def spectral_engine_status() -> dict[str, Any]:
    try:
        lib = _load()
        raw = lib.xstar_spectral_engine_backend_name()
        return {
            "available": True,
            "abi_version": int(lib.xstar_spectral_engine_abi_version()),
            "implementation": raw.decode("utf-8", "replace") if raw else "unknown",
            "feature_flags": int(lib.xstar_spectral_engine_feature_flags()),
            "load_error": None,
        }
    except Exception as exc:
        return {
            "available": False,
            "abi_version": None,
            "implementation": None,
            "feature_flags": 0,
            "load_error": str(exc),
        }


def _as_f64(value: Any) -> np.ndarray:
    return np.ascontiguousarray(np.asarray(value, dtype=np.float64).reshape(-1))


def _pack_contributions(values: Iterable[Mapping[str, Any]]) -> tuple[Any, np.ndarray, list[Mapping[str, Any]]]:
    rows = list(values)
    packed = (_Contribution * len(rows))()
    seeds = np.zeros((len(rows), 21), dtype=np.float64)
    for i, item in enumerate(rows):
        packed[i] = _Contribution(
            int(item.get("source_position", i + 1)),
            int(item.get("record", 0)),
            int(item.get("kind", 0)),
            int(item.get("rate_type", 0)),
            int(item.get("data_type", 0)),
            int(item.get("output_index", 0)),
            int(item.get("bin_one_based", 0)),
            0, 0,
            float(item.get("ptmp1", 0.0)),
            float(item.get("ptmp2", 0.0)),
            float(item.get("abundance_lower", 0.0)),
            float(item.get("abundance_upper", 0.0)),
            float(item.get("hydrogen_density", 0.0)),
            float(item.get("ans1", 0.0)),
            float(item.get("ans2", 0.0)),
            float(item.get("ans3", 0.0)),
            float(item.get("ans4", 0.0)),
            float(item.get("opakab", 0.0)),
            float(item.get("line_energy_eV", 0.0)),
            float(item.get("bin_width_eV", 0.0)),
            float(item.get("atomic_mass_amu", 0.0)),
            float(item.get("natural_width_eV", 0.0)),
            float(item.get("turbulent_velocity_km_s", 0.0)),
            float(item.get("temperature_1e4K", 0.0)),
        )
        seed = item.get("seed_profiles")
        if seed is not None:
            arr = np.asarray(seed, dtype=np.float64).reshape(-1)
            if arr.size != 21:
                raise ValueError(f"line seed profile must contain 21 values, got {arr.size}")
            seeds[i, :] = arr
    return packed, np.ascontiguousarray(seeds.reshape(-1)), rows


def apply_spectral_contributions_cpp(
    contributions: Iterable[Mapping[str, Any]],
    *,
    rcem: np.ndarray,
    oplin: np.ndarray,
    cemab: np.ndarray,
    cabab: np.ndarray,
    opakab: np.ndarray,
    rccemis: np.ndarray,
    opakc: np.ndarray,
    opakcont: np.ndarray,
    fline: np.ndarray,
    flinel: np.ndarray,
    epi_eV: np.ndarray,
) -> dict[str, Any]:
    """Apply source-ordered compact spectral contributions in-place."""
    lib = _load()
    packing_started = time.perf_counter()
    packed, seeds, rows = _pack_contributions(contributions)
    arrays = {
        "rcem": np.ascontiguousarray(np.asarray(rcem, dtype=np.float64)),
        "oplin": np.ascontiguousarray(np.asarray(oplin, dtype=np.float64)),
        "cemab": np.ascontiguousarray(np.asarray(cemab, dtype=np.float64)),
        "cabab": np.ascontiguousarray(np.asarray(cabab, dtype=np.float64)),
        "opakab": np.ascontiguousarray(np.asarray(opakab, dtype=np.float64)),
        "rccemis": np.ascontiguousarray(np.asarray(rccemis, dtype=np.float64)),
        "opakc": np.ascontiguousarray(np.asarray(opakc, dtype=np.float64)),
        "opakcont": np.ascontiguousarray(np.asarray(opakcont, dtype=np.float64)),
        "fline": np.ascontiguousarray(np.asarray(fline, dtype=np.float64)),
        "flinel": np.ascontiguousarray(np.asarray(flinel, dtype=np.float64)),
        "epi": _as_f64(epi_eV),
    }
    original_refs = {
        "rcem": rcem, "oplin": oplin, "cemab": cemab, "cabab": cabab,
        "opakab": opakab, "rccemis": rccemis, "opakc": opakc,
        "opakcont": opakcont, "fline": fline, "flinel": flinel,
    }
    workspace = _Workspace(
        ctypes.sizeof(_Workspace), _ABI, 0, 0,
        _p(arrays["rcem"]), arrays["rcem"].size,
        _p(arrays["oplin"]), arrays["oplin"].size,
        _p(arrays["cemab"]), arrays["cemab"].size,
        _p(arrays["cabab"]), arrays["cabab"].size,
        _p(arrays["opakab"]), arrays["opakab"].size,
        _p(arrays["rccemis"]), arrays["rccemis"].size,
        _p(arrays["opakc"]), arrays["opakc"].size,
        _p(arrays["opakcont"]), arrays["opakcont"].size,
        _p(arrays["fline"]), arrays["fline"].size,
        _p(arrays["flinel"]), arrays["flinel"].size,
        _p(arrays["epi"]), arrays["epi"].size,
    )
    stats = _Stats()
    stats.struct_size = ctypes.sizeof(_Stats)
    stats.abi_version = _ABI
    error = ctypes.create_string_buffer(1024)
    packing_seconds = time.perf_counter() - packing_started
    ffi_started = time.perf_counter()
    seed_ptr = _p(seeds) if seeds.size else ctypes.POINTER(ctypes.c_double)()
    rc = lib.xstar_spectral_apply_contributions_v1(
        _context(), packed, len(rows), seed_ptr, 21,
        ctypes.byref(workspace), ctypes.byref(stats), error, len(error),
    )
    ffi_seconds = time.perf_counter() - ffi_started
    if rc != 0:
        raise RuntimeError(error.value.decode("utf-8", "replace") or f"native spectral engine failed: {rc}")
    # Copy back only when ctypes had to materialize a contiguous temporary.
    for name, target in original_refs.items():
        target_array = np.asarray(target)
        native_array = arrays[name]
        if target_array.ctypes.data != native_array.ctypes.data:
            np.copyto(target_array, native_array.reshape(target_array.shape))
    return {
        "schema_version": "0.6.46.1",
        "contributions": len(rows),
        "calls": int(stats.calls),
        "contributions_attempted": int(stats.contributions_attempted),
        "contributions_committed": int(stats.contributions_committed),
        "emissivity_contributions": int(stats.emissivity_contributions),
        "opacity_contributions": int(stats.opacity_contributions),
        "line_profiles": int(stats.line_profiles),
        "source_order_violations": int(stats.source_order_violations),
        "packing_seconds": float(packing_seconds),
        "ffi_seconds": float(ffi_seconds),
        "construction_seconds": float(stats.construction_seconds),
        "opacity_seconds": float(stats.opacity_seconds),
        "commit_seconds": float(stats.commit_seconds),
        "message": error.value.decode("utf-8", "replace"),
    }


__all__ = [
    "KIND_EMISAB_BOUND_FREE", "KIND_EMISAB_LINE", "KIND_EMIS_OPACITY_ONLY", "KIND_EMIS_LINE",
    "spectral_engine_status", "apply_spectral_contributions_cpp",
]
