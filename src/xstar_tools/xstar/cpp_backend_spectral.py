"""Persistent native emissivity/opacity contribution engine for v0.6.48.2.

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


def _pack_contributions(
    values: Iterable[Mapping[str, Any]],
    *,
    seed_profile_stride: int = 21,
    seed_overrides: Mapping[int, np.ndarray] | None = None,
) -> tuple[Any, np.ndarray, list[Mapping[str, Any]]]:
    rows = list(values)
    stride = int(seed_profile_stride)
    from .spectral_profile_oracle import EXACT_GRID_STRIDE
    if stride != EXACT_GRID_STRIDE and (stride < 21 or stride % 2 != 1):
        raise ValueError(
            f"seed profile stride must be odd and at least 21, or exact-grid stride {EXACT_GRID_STRIDE}; got {stride}"
        )
    packed = (_Contribution * len(rows))()
    seeds = np.zeros((len(rows), stride), dtype=np.float64)
    overrides = dict(seed_overrides or {})
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
        if i in overrides:
            arr = np.asarray(overrides[i], dtype=np.float64).reshape(-1)
        else:
            seed = item.get("seed_profiles")
            arr = np.asarray(seed, dtype=np.float64).reshape(-1) if seed is not None else np.zeros(21, dtype=np.float64)
        if arr.size not in (21, stride):
            raise ValueError(f"line seed/oracle payload must contain 21 or {stride} values, got {arr.size}")
        seeds[i, :arr.size] = arr
    return packed, np.ascontiguousarray(seeds.reshape(-1)), rows


def _apply_spectral_batch(
    rows: list[Mapping[str, Any]],
    *,
    seed_profile_stride: int,
    seed_overrides: Mapping[int, np.ndarray] | None,
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
    lib = _load()
    packing_started = time.perf_counter()
    packed, seeds, rows = _pack_contributions(
        rows, seed_profile_stride=seed_profile_stride, seed_overrides=seed_overrides
    )
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
        _context(), packed, len(rows), seed_ptr, int(seed_profile_stride),
        ctypes.byref(workspace), ctypes.byref(stats), error, len(error),
    )
    ffi_seconds = time.perf_counter() - ffi_started
    if rc != 0:
        raise RuntimeError(error.value.decode("utf-8", "replace") or f"native spectral engine failed: {rc}")
    for name, target in original_refs.items():
        target_array = np.asarray(target)
        native_array = arrays[name]
        if target_array.ctypes.data != native_array.ctypes.data:
            np.copyto(target_array, native_array.reshape(target_array.shape))
    return {
        "schema_version": "0.6.48.2",
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
        "exact_profile_oracle_calls": 0,
        "exact_profile_oracle_values": 0,
        "exact_profile_oracle_line_profiles": 0,
        "exact_grid_oracle_calls": 0,
        "exact_grid_oracle_energy_values": 0,
        "exact_grid_oracle_opacity_values": 0,
        "strict_source_rounding": True,
        "source_hunt_floor": float(np.float32(1.0e-34)),
        "message": error.value.decode("utf-8", "replace"),
    }


def _merge_metrics(total: dict[str, Any], item: Mapping[str, Any]) -> None:
    for key in (
        "contributions", "calls", "contributions_attempted", "contributions_committed",
        "emissivity_contributions", "opacity_contributions", "line_profiles",
        "source_order_violations", "exact_profile_oracle_calls",
        "exact_profile_oracle_values", "exact_profile_oracle_line_profiles",
        "exact_grid_oracle_calls", "exact_grid_oracle_energy_values",
        "exact_grid_oracle_opacity_values",
    ):
        total[key] = int(total.get(key, 0) or 0) + int(item.get(key, 0) or 0)
    for key in ("packing_seconds", "ffi_seconds", "construction_seconds", "opacity_seconds", "commit_seconds"):
        total[key] = float(total.get(key, 0.0) or 0.0) + float(item.get(key, 0.0) or 0.0)
    if item.get("message"):
        total["message"] = str(item["message"])
    if "strict_source_rounding" in item:
        total["strict_source_rounding"] = bool(item.get("strict_source_rounding"))
    if "source_hunt_floor" in item:
        total["source_hunt_floor"] = float(item.get("source_hunt_floor", 0.0) or 0.0)


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
    exact_profile_oracle: bool = False,
    exact_profile_radius: int = 10000,
) -> dict[str, Any]:
    """Apply source-ordered compact spectral contributions in-place.

    Product execution uses 21 source seeds and native C++ Gaussian/Voigt
    evaluation. Qualification may set ``exact_profile_oracle``; v0.6.48.2 then
    supplies the complete Python temporary energy grid and exact ``optpp2``
    samples. C++ still performs trapezoid integration, continuum rebinning, and
    source-ordered array commit.
    """
    rows = list(contributions)
    previous = 0
    for row in rows:
        position = int(row.get("source_position", 0))
        if position <= previous:
            raise ValueError("spectral contribution source order violation before FFI")
        previous = position
    if not exact_profile_oracle or not any(int(row.get("kind", 0)) == KIND_EMIS_LINE for row in rows):
        return _apply_spectral_batch(
            rows, seed_profile_stride=21, seed_overrides=None,
            rcem=rcem, oplin=oplin, cemab=cemab, cabab=cabab, opakab=opakab,
            rccemis=rccemis, opakc=opakc, opakcont=opakcont,
            fline=fline, flinel=flinel, epi_eV=epi_eV,
        )

    from .spectral_profile_oracle import (
        EXACT_GRID_POINTS, EXACT_GRID_STRIDE, source_linopac_exact_grid,
    )

    total: dict[str, Any] = {
        "schema_version": "0.6.48.2", "message": "exact source-profile oracle applied",
        "contributions": 0, "calls": 0, "contributions_attempted": 0,
        "contributions_committed": 0, "emissivity_contributions": 0,
        "opacity_contributions": 0, "line_profiles": 0,
        "source_order_violations": 0, "packing_seconds": 0.0,
        "ffi_seconds": 0.0, "construction_seconds": 0.0,
        "opacity_seconds": 0.0, "commit_seconds": 0.0,
        "exact_profile_oracle_calls": 0, "exact_profile_oracle_values": 0,
        "exact_profile_oracle_line_profiles": 0,
        "exact_grid_oracle_calls": 0, "exact_grid_oracle_energy_values": 0,
        "exact_grid_oracle_opacity_values": 0,
        "strict_source_rounding": True,
        "source_hunt_floor": float(np.float32(1.0e-34)),
    }
    pending: list[Mapping[str, Any]] = []

    def flush_pending() -> None:
        nonlocal pending
        if not pending:
            return
        item = _apply_spectral_batch(
            pending, seed_profile_stride=21, seed_overrides=None,
            rcem=rcem, oplin=oplin, cemab=cemab, cabab=cabab, opakab=opakab,
            rccemis=rccemis, opakc=opakc, opakcont=opakcont,
            fline=fline, flinel=flinel, epi_eV=epi_eV,
        )
        _merge_metrics(total, item)
        pending = []

    radius = int(exact_profile_radius)
    if radius != 10000:
        raise ValueError("exact source-grid qualification requires radius=10000")
    for row in rows:
        if int(row.get("kind", 0)) != KIND_EMIS_LINE:
            pending.append(row)
            continue
        flush_pending()
        exact = source_linopac_exact_grid(
            optpp=float(row.get("opakab", 0.0)) * float(row.get("abundance_lower", 0.0)),
            line_energy_eV=float(row.get("line_energy_eV", 0.0)),
            vturb_km_s=float(row.get("turbulent_velocity_km_s", 0.0)),
            temperature_1e4K=float(row.get("temperature_1e4K", 0.0)),
            atomic_mass_amu=float(row.get("atomic_mass_amu", 0.0)),
            natural_width_eV=float(row.get("natural_width_eV", 0.0)),
            epi=epi_eV, ncn2=np.asarray(epi_eV).size,
        )
        item = _apply_spectral_batch(
            [row], seed_profile_stride=EXACT_GRID_STRIDE, seed_overrides={0: exact.packed},
            rcem=rcem, oplin=oplin, cemab=cemab, cabab=cabab, opakab=opakab,
            rccemis=rccemis, opakc=opakc, opakcont=opakcont,
            fline=fline, flinel=flinel, epi_eV=epi_eV,
        )
        item["exact_profile_oracle_calls"] = 1
        item["exact_profile_oracle_values"] = EXACT_GRID_POINTS
        item["exact_profile_oracle_line_profiles"] = int(item.get("line_profiles", 0) or 0)
        item["exact_grid_oracle_calls"] = 1
        item["exact_grid_oracle_energy_values"] = EXACT_GRID_POINTS
        item["exact_grid_oracle_opacity_values"] = EXACT_GRID_POINTS
        _merge_metrics(total, item)
    flush_pending()
    return total


__all__ = [
    "KIND_EMISAB_BOUND_FREE", "KIND_EMISAB_LINE", "KIND_EMIS_OPACITY_ONLY", "KIND_EMIS_LINE",
    "spectral_engine_status", "apply_spectral_contributions_cpp",
]
