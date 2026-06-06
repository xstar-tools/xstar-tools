"""Optional C++ emissivity/output backend loader.

v0.6.0a19 adds ``libxstar_emissivity.so`` for the binemis final-product
profile loop.  The library remains a flat C ABI shared object in
``src/xstar_tools/xstar/cpp/`` and Python keeps a source-faithful fallback.
"""
from __future__ import annotations

import ctypes
from dataclasses import dataclass, asdict
import os
from pathlib import Path
from typing import Any

import numpy as np


@dataclass(frozen=True)
class EmissivityBackendStatus:
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


_CPP_LIB: ctypes.CDLL | None = None
_CPP_LOAD_ERROR: BaseException | None = None
_CPP_LIBRARY_PATH: str | None = None


def _candidate_library_paths() -> list[Path]:
    env_path = os.environ.get("XSTAR_ATOMIC_EMISSIVITY_LIB")
    paths: list[Path] = []
    if env_path:
        paths.append(Path(env_path).expanduser())
    here = Path(__file__).resolve().parent
    for name in ("libxstar_emissivity.so", "xstar_emissivity.so", "libxstar_emissivity.dylib", "xstar_emissivity.dll"):
        paths.append(here / "cpp" / name)
    seen: set[str] = set(); out: list[Path] = []
    for p in paths:
        k = str(p)
        if k not in seen:
            seen.add(k); out.append(p)
    return out


def _load_cpp_library() -> ctypes.CDLL | None:
    global _CPP_LIB, _CPP_LOAD_ERROR, _CPP_LIBRARY_PATH
    if _CPP_LIB is not None:
        return _CPP_LIB
    if _CPP_LOAD_ERROR is not None:
        return None
    attempted: list[str] = []
    try:
        for path in _candidate_library_paths():
            attempted.append(str(path))
            if not path.exists():
                continue
            lib = ctypes.CDLL(str(path))
            lib.xstar_emissivity_abi_version.argtypes = []
            lib.xstar_emissivity_abi_version.restype = ctypes.c_int
            lib.xstar_emissivity_backend_name.argtypes = []
            lib.xstar_emissivity_backend_name.restype = ctypes.c_char_p
            lib.xstar_emissivity_feature_flags.argtypes = []
            lib.xstar_emissivity_feature_flags.restype = ctypes.c_int
            i64p = np.ctypeslib.ndpointer(dtype=np.int64, ndim=1, flags="C_CONTIGUOUS")
            f64p = np.ctypeslib.ndpointer(dtype=np.float64, ndim=1, flags="C_CONTIGUOUS")
            lib.xstar_emissivity_build_binemis_profile.argtypes = [
                ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                ctypes.c_double, ctypes.c_double, ctypes.c_double,
                f64p, f64p, f64p, f64p, f64p,
                i64p, f64p, i64p, f64p, f64p, f64p, f64p,
                f64p, f64p, ctypes.c_char_p, ctypes.c_size_t,
            ]
            lib.xstar_emissivity_build_binemis_profile.restype = ctypes.c_int
            _CPP_LIB = lib
            _CPP_LIBRARY_PATH = str(path)
            return lib
        raise FileNotFoundError("could not find libxstar_emissivity.so; attempted " + ", ".join(attempted))
    except BaseException as exc:
        _CPP_LOAD_ERROR = exc
        return None


def cpp_import_error() -> str | None:
    return None if _CPP_LOAD_ERROR is None else repr(_CPP_LOAD_ERROR)


def emissivity_backend_status(requested: str = "auto") -> EmissivityBackendStatus:
    req = (requested or os.environ.get("XSTAR_ATOMIC_EMISSIVITY_BACKEND") or "python").strip().lower()
    if req not in {"python", "cpp", "auto"}:
        req = "python"
    lib = _load_cpp_library()
    if lib is None:
        active = "unavailable" if req == "cpp" else "python"
        return EmissivityBackendStatus(requested=req, active=active, cpp_available=False, cpp_import_error=cpp_import_error())
    try:
        name = lib.xstar_emissivity_backend_name().decode("utf-8", "replace")
        abi = int(lib.xstar_emissivity_abi_version())
        flags = int(lib.xstar_emissivity_feature_flags())
    except Exception as exc:
        active = "unavailable" if req == "cpp" else "python"
        return EmissivityBackendStatus(requested=req, active=active, cpp_available=False, cpp_import_error=repr(exc), cpp_library_path=_CPP_LIBRARY_PATH)
    if req == "python":
        active = "python"
    elif req == "cpp":
        active = "cpp"
    else:
        active = "cpp"
    return EmissivityBackendStatus(requested=req, active=active, cpp_available=True, cpp_library_path=_CPP_LIBRARY_PATH, cpp_backend_name=name, cpp_abi_version=abi, cpp_feature_flags=flags)


def build_binemis_profile_cpp(
    *,
    epi_eV: np.ndarray,
    dpthc: np.ndarray,
    elum: np.ndarray,
    zrems: np.ndarray,
    zremsz: np.ndarray,
    slot_line_indices: np.ndarray,
    line_wavelength: np.ndarray,
    line_data_type: np.ndarray,
    line_atomic_mass: np.ndarray,
    line_natural_rate_s: np.ndarray,
    line_auger_width_eV: np.ndarray,
    line_auger_rate_s: np.ndarray,
    xlum: float,
    temperature_1e4K: float,
    turbulent_velocity_km_s: float,
    ncn2: int,
) -> tuple[np.ndarray, dict[str, float], str]:
    lib = _load_cpp_library()
    if lib is None:
        raise RuntimeError("C++ binemis backend unavailable" + (f": {cpp_import_error()}" if cpp_import_error() else ""))
    epi = np.ascontiguousarray(np.asarray(epi_eV, dtype=np.float64).reshape(-1))
    dp2 = np.ascontiguousarray(np.asarray(dpthc, dtype=np.float64))
    lum2 = np.ascontiguousarray(np.asarray(elum, dtype=np.float64))
    original2 = np.ascontiguousarray(np.asarray(zrems, dtype=np.float64))
    incident = np.ascontiguousarray(np.asarray(zremsz, dtype=np.float64).reshape(-1))
    slots = np.ascontiguousarray(np.asarray(slot_line_indices, dtype=np.int64).reshape(-1))
    wavelength = np.ascontiguousarray(np.asarray(line_wavelength, dtype=np.float64).reshape(-1))
    data_type = np.ascontiguousarray(np.asarray(line_data_type, dtype=np.int64).reshape(-1))
    atomic_mass = np.ascontiguousarray(np.asarray(line_atomic_mass, dtype=np.float64).reshape(-1))
    natural = np.ascontiguousarray(np.asarray(line_natural_rate_s, dtype=np.float64).reshape(-1))
    auger_width = np.ascontiguousarray(np.asarray(line_auger_width_eV, dtype=np.float64).reshape(-1))
    auger_rate = np.ascontiguousarray(np.asarray(line_auger_rate_s, dtype=np.float64).reshape(-1))
    if dp2.ndim != 2 or lum2.ndim != 2 or original2.ndim != 2:
        raise ValueError("binemis C++ arrays must be two-dimensional where expected")
    # v0.6.9: ctypes ABI expects flat one-dimensional contiguous buffers for
    # all matrix-like arrays.  Keep the Python-facing shape for comparison and
    # reshape after the C++ call, but pass only 1-D buffers to ndpointer(ndim=1).
    dp = np.ascontiguousarray(dp2.reshape(-1))
    lum = np.ascontiguousarray(lum2.reshape(-1))
    original = np.ascontiguousarray(original2.reshape(-1))
    out = np.ascontiguousarray(original.copy())
    stats = np.zeros(16, dtype=np.float64)
    buf = ctypes.create_string_buffer(512)
    rc = lib.xstar_emissivity_build_binemis_profile(
        int(ncn2), int(epi.size), int(original2.shape[1]), int(slots.size), int(lum2.shape[1]),
        float(xlum), float(temperature_1e4K), float(turbulent_velocity_km_s),
        epi, np.ascontiguousarray(dp), lum, original, incident,
        slots, wavelength, data_type, atomic_mass, natural, auger_width, auger_rate,
        out, stats, buf, ctypes.sizeof(buf),
    )
    msg = buf.value.decode("utf-8", "replace")
    if rc != 0:
        raise RuntimeError(msg or f"xstar_emissivity_build_binemis_profile failed with code {rc}")
    return out.reshape(original2.shape), {"cpp_profile_lines_attempted": float(stats[0]), "cpp_profile_lines_applied": float(stats[1]), "cpp_profile_slots": float(stats[2]), "cpp_source_real_literal_parity": float(stats[3])}, msg
