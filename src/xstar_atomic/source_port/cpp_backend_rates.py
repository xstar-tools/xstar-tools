"""Optional C++ rates backend loader.

This module intentionally exposes only a small status/probe interface in
v0.5.53.  Real rate evaluation will be added after compact active-ATDB arrays
are parity-checked.  Keeping the ABI as a plain C interface makes the same C++
source usable from Python, hydrodynamic post-processing workflows, and a future
standalone xstar_tools executable.
"""
from __future__ import annotations

import ctypes
from dataclasses import dataclass, asdict
import os
from pathlib import Path


@dataclass(frozen=True)
class RatesBackendStatus:
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
    env_path = os.environ.get("XSTAR_ATOMIC_RATES_LIB")
    paths: list[Path] = []
    if env_path:
        paths.append(Path(env_path).expanduser())
    here = Path(__file__).resolve().parent
    names = (
        "libxstar_rates.so",
        "xstar_rates.so",
        "libxstar_rates.dylib",
        "xstar_rates.dll",
    )
    for name in names:
        paths.append(here / name)
    for name in names:
        paths.append(here / "cpp" / name)
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        key = str(path)
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


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
            lib.xstar_rates_abi_version.argtypes = []
            lib.xstar_rates_abi_version.restype = ctypes.c_int
            lib.xstar_rates_backend_name.argtypes = []
            lib.xstar_rates_backend_name.restype = ctypes.c_char_p
            lib.xstar_rates_feature_flags.argtypes = []
            lib.xstar_rates_feature_flags.restype = ctypes.c_int
            lib.xstar_rates_eval_mg.argtypes = [
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_void_p,
                ctypes.c_size_t,
                ctypes.c_char_p,
                ctypes.c_size_t,
            ]
            lib.xstar_rates_eval_mg.restype = ctypes.c_int
            _CPP_LIB = lib
            _CPP_LIBRARY_PATH = str(path)
            return _CPP_LIB
        raise FileNotFoundError("no xstar_rates shared library found; attempted: " + "; ".join(attempted))
    except BaseException as exc:  # pragma: no cover - optional shared library
        _CPP_LOAD_ERROR = exc
        return None


def cpp_import_error() -> str | None:
    if _CPP_LOAD_ERROR is None:
        return None
    return f"{type(_CPP_LOAD_ERROR).__name__}: {_CPP_LOAD_ERROR}"


def _backend_name(lib: ctypes.CDLL | None) -> str | None:
    if lib is None:
        return None
    try:
        raw = lib.xstar_rates_backend_name()
        return raw.decode("ascii", errors="replace") if raw else None
    except Exception:
        return None


def _abi_version(lib: ctypes.CDLL | None) -> int | None:
    if lib is None:
        return None
    try:
        return int(lib.xstar_rates_abi_version())
    except Exception:
        return None


def _feature_flags(lib: ctypes.CDLL | None) -> int | None:
    if lib is None:
        return None
    try:
        return int(lib.xstar_rates_feature_flags())
    except Exception:
        return None


def rates_backend_status(requested: str | None = None) -> RatesBackendStatus:
    req = (requested or os.environ.get("XSTAR_ATOMIC_RATES_BACKEND") or "python").strip().lower()
    if req not in {"python", "cpp", "auto"}:
        req = "python"
    lib = _load_cpp_library()
    if req == "python":
        active = "python"
    elif req == "cpp":
        active = "cpp" if lib is not None else "unavailable"
    else:
        active = "cpp" if lib is not None else "python"
    return RatesBackendStatus(
        requested=req,
        active=active,
        cpp_available=lib is not None,
        cpp_import_error=cpp_import_error(),
        cpp_library_path=_CPP_LIBRARY_PATH,
        cpp_backend_name=_backend_name(lib),
        cpp_abi_version=_abi_version(lib),
        cpp_feature_flags=_feature_flags(lib),
    )


def probe_cpp_mg_rates(*, n_ions: int = 0, n_records: int = 0) -> str:
    """Call the v0.5.53 skeleton Mg rates entry point.

    This is a build/ABI smoke probe only.  It does not compute physics yet.
    """
    lib = _load_cpp_library()
    if lib is None:
        raise RuntimeError("C++ rates shared library is not available" + (f": {cpp_import_error()}" if cpp_import_error() else ""))
    errbuf = ctypes.create_string_buffer(512)
    rc = lib.xstar_rates_eval_mg(
        ctypes.c_int(int(n_ions)),
        ctypes.c_int(int(n_records)),
        None,
        ctypes.c_size_t(0),
        errbuf,
        ctypes.c_size_t(len(errbuf)),
    )
    message = errbuf.value.decode("utf-8", errors="replace")
    if rc != 0:
        raise RuntimeError(message or f"xstar_rates_eval_mg failed with code {rc}")
    return message
