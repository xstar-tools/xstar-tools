"""Load optional flat-layout C++ backend skeleton libraries.

v0.6.1 adds ABI skeletons for opacity, thermal, and engine libraries while
keeping every C++ source and shared object directly in ``src/xstar_tools/xstar/cpp``.
The new Mg-ion accumulator is present as an opt-in engine ABI skeleton and is
not product-active by default.
"""
from __future__ import annotations

import ctypes
from dataclasses import dataclass, asdict
import os
from pathlib import Path
from typing import Any

import numpy as np


@dataclass(frozen=True)
class ExtraBackendStatus:
    requested: str
    active: str
    cpp_available: bool
    cpp_import_error: str | None = None
    cpp_library_path: str | None = None
    cpp_backend_name: str | None = None
    cpp_abi_version: int | None = None
    cpp_feature_flags: int | None = None

    def as_dict(self) -> dict[str, object]:
        return dict(asdict(self))


@dataclass(frozen=True)
class MgIonAccumulatorProbe:
    enabled: bool
    library_available: bool
    records_seen: int
    cpp_supported: int
    python_fallback: int
    matrix_terms_emitted: int
    rate_terms_emitted: int
    heat_terms_emitted: int
    cool_terms_emitted: int
    message: str
    error: str | None = None

    def as_dict(self) -> dict[str, object]:
        return dict(asdict(self))


_LIBS: dict[str, ctypes.CDLL | None] = {}
_ERRORS: dict[str, BaseException | None] = {}
_PATHS: dict[str, str | None] = {}

_LIBRARY_INFO = {
    "opacity": {
        "env": "XSTAR_ATOMIC_OPACITY_LIB",
        "backend_env": "XSTAR_ATOMIC_OPACITY_BACKEND",
        "names": ("libxstar_opacity.so", "xstar_opacity.so", "libxstar_opacity.dylib", "xstar_opacity.dll"),
        "prefix": "xstar_opacity",
    },
    "thermal": {
        "env": "XSTAR_ATOMIC_THERMAL_LIB",
        "backend_env": "XSTAR_ATOMIC_THERMAL_BACKEND",
        "names": ("libxstar_thermal.so", "xstar_thermal.so", "libxstar_thermal.dylib", "xstar_thermal.dll"),
        "prefix": "xstar_thermal",
    },
    "engine": {
        "env": "XSTAR_ATOMIC_ENGINE_LIB",
        "backend_env": "XSTAR_ATOMIC_ENGINE_BACKEND",
        "names": ("libxstar_engine.so", "xstar_engine.so", "libxstar_engine.dylib", "xstar_engine.dll"),
        "prefix": "xstar_engine",
    },
}


def _candidate_library_paths(kind: str) -> list[Path]:
    info = _LIBRARY_INFO[kind]
    paths: list[Path] = []
    env_path = os.environ.get(str(info["env"]))
    if env_path:
        paths.append(Path(env_path).expanduser())
    here = Path(__file__).resolve().parent
    for name in info["names"]:
        paths.append(here / "cpp" / str(name))
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        key = str(path)
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def _load_library(kind: str) -> ctypes.CDLL | None:
    if kind in _LIBS:
        return _LIBS[kind]
    info = _LIBRARY_INFO[kind]
    prefix = str(info["prefix"])
    attempted: list[str] = []
    try:
        for path in _candidate_library_paths(kind):
            attempted.append(str(path))
            if not path.exists():
                continue
            lib = ctypes.CDLL(str(path))
            getattr(lib, f"{prefix}_abi_version").argtypes = []
            getattr(lib, f"{prefix}_abi_version").restype = ctypes.c_int
            getattr(lib, f"{prefix}_backend_name").argtypes = []
            getattr(lib, f"{prefix}_backend_name").restype = ctypes.c_char_p
            getattr(lib, f"{prefix}_feature_flags").argtypes = []
            getattr(lib, f"{prefix}_feature_flags").restype = ctypes.c_int
            if kind == "opacity":
                lib.xstar_opacity_probe.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_size_t]
                lib.xstar_opacity_probe.restype = ctypes.c_int
            elif kind == "thermal":
                lib.xstar_thermal_probe.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_size_t]
                lib.xstar_thermal_probe.restype = ctypes.c_int
            elif kind == "engine":
                lib.xstar_engine_probe.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_size_t]
                lib.xstar_engine_probe.restype = ctypes.c_int
                i64p = np.ctypeslib.ndpointer(dtype=np.int64, ndim=1, flags="C_CONTIGUOUS")
                lib.xstar_engine_eval_mg_ion_accumulator_v1.argtypes = [
                    ctypes.c_int, ctypes.c_int, ctypes.c_int,
                    i64p, i64p, i64p, ctypes.c_int,
                    ctypes.c_char_p, ctypes.c_size_t,
                ]
                lib.xstar_engine_eval_mg_ion_accumulator_v1.restype = ctypes.c_int
            _LIBS[kind] = lib
            _PATHS[kind] = str(path)
            _ERRORS[kind] = None
            return lib
        raise FileNotFoundError(f"could not find {kind} C++ library; attempted " + ", ".join(attempted))
    except BaseException as exc:
        _LIBS[kind] = None
        _ERRORS[kind] = exc
        _PATHS[kind] = None
        return None


def cpp_import_error(kind: str) -> str | None:
    err = _ERRORS.get(kind)
    return None if err is None else repr(err)


def backend_status(kind: str, requested: str | None = None) -> ExtraBackendStatus:
    info = _LIBRARY_INFO[kind]
    req = (requested or os.environ.get(str(info["backend_env"])) or os.environ.get("XSTAR_ATOMIC_BACKEND") or "python").strip().lower()
    if req not in {"python", "cpp", "auto"}:
        req = "python"
    lib = _load_library(kind)
    if req == "python":
        active = "python"
    elif req == "cpp":
        active = "cpp" if lib is not None else "unavailable"
    else:
        active = "cpp" if lib is not None else "python"
    name: str | None = None
    abi: int | None = None
    flags: int | None = None
    if lib is not None:
        prefix = str(info["prefix"])
        try:
            raw = getattr(lib, f"{prefix}_backend_name")()
            name = raw.decode("utf-8", "replace") if raw else None
            abi = int(getattr(lib, f"{prefix}_abi_version")())
            flags = int(getattr(lib, f"{prefix}_feature_flags")())
        except Exception as exc:
            if req == "cpp":
                active = "unavailable"
            name = None
            abi = None
            flags = None
            _ERRORS[kind] = exc
    return ExtraBackendStatus(
        requested=req,
        active=active,
        cpp_available=lib is not None,
        cpp_import_error=cpp_import_error(kind),
        cpp_library_path=_PATHS.get(kind),
        cpp_backend_name=name,
        cpp_abi_version=abi,
        cpp_feature_flags=flags,
    )


def opacity_backend_status(requested: str | None = None) -> ExtraBackendStatus:
    return backend_status("opacity", requested)


def thermal_backend_status(requested: str | None = None) -> ExtraBackendStatus:
    return backend_status("thermal", requested)


def engine_backend_status(requested: str | None = None) -> ExtraBackendStatus:
    return backend_status("engine", requested)


def probe_mg_ion_accumulator_skeleton(
    *,
    element_z: int = 12,
    ion_index: int = 0,
    record_rate_type: np.ndarray | None = None,
    record_data_type: np.ndarray | None = None,
    enabled: bool | None = None,
) -> MgIonAccumulatorProbe:
    """Exercise the opt-in Mg-ion accumulator ABI skeleton.

    The skeleton deliberately supports no records yet.  It is useful to prove
    the coarse C++ boundary and fallback counters without changing products.
    """
    enabled_value = bool(enabled) if enabled is not None else str(os.environ.get("XSTAR_ATOMIC_ENGINE_MG_ION_ACCUMULATOR_CPP", "0")).strip().lower() in {"1", "true", "yes", "on"}
    lib = _load_library("engine")
    if not enabled_value:
        return MgIonAccumulatorProbe(False, lib is not None, 0, 0, 0, 0, 0, 0, 0, "Mg-ion accumulator skeleton disabled by default")
    if lib is None:
        return MgIonAccumulatorProbe(True, False, 0, 0, 0, 0, 0, 0, 0, "engine library unavailable", cpp_import_error("engine"))
    rt = np.ascontiguousarray(np.asarray(record_rate_type if record_rate_type is not None else np.zeros(0, dtype=np.int64), dtype=np.int64))
    dt = np.ascontiguousarray(np.asarray(record_data_type if record_data_type is not None else np.zeros(rt.shape[0], dtype=np.int64), dtype=np.int64))
    if dt.shape[0] != rt.shape[0]:
        raise ValueError("record_rate_type and record_data_type must have the same length")
    counters = np.zeros(7, dtype=np.int64)
    buf = ctypes.create_string_buffer(512)
    rc = lib.xstar_engine_eval_mg_ion_accumulator_v1(
        int(element_z), int(ion_index), int(rt.shape[0]), rt, dt, counters, int(counters.shape[0]), buf, ctypes.sizeof(buf)
    )
    msg = buf.value.decode("utf-8", "replace")
    if rc != 0:
        return MgIonAccumulatorProbe(True, True, 0, 0, 0, 0, 0, 0, 0, msg or f"accumulator returned {rc}", f"return_code={rc}")
    return MgIonAccumulatorProbe(
        True, True,
        int(counters[0]), int(counters[1]), int(counters[2]),
        int(counters[3]), int(counters[4]), int(counters[5]), int(counters[6]),
        msg,
    )
