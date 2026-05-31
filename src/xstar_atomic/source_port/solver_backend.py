"""Optional solver backend dispatch for source-port linear solves.

This module is intentionally small and isolated so it can move cleanly to the
future layout as ``xstar_tools.xstar.solver.backend``.  The pure-Python
source-faithful implementation remains the reference path.

The C++ backend is loaded as a plain shared-object library (``.so``) through
``ctypes`` rather than as a Python extension module.  That keeps the compiled
kernel ABI small and makes it easier to reuse from the future ``xstar_tools``
layout or from non-Python drivers.
"""
from __future__ import annotations

import ctypes
from dataclasses import dataclass
import os
from pathlib import Path
from typing import Literal

import numpy as np

SolverBackendName = Literal["python", "cpp", "auto"]

_VALID_BACKENDS = {"python", "cpp", "auto"}
_CURRENT_BACKEND: SolverBackendName = "python"
_CPP_LIB: ctypes.CDLL | None = None
_CPP_LOAD_ERROR: BaseException | None = None
_CPP_LIBRARY_PATH: str | None = None


@dataclass(frozen=True)
class SolverBackendStatus:
    requested: str
    active: str
    cpp_available: bool
    cpp_import_error: str | None = None
    cpp_library_path: str | None = None
    cpp_backend_name: str | None = None
    cpp_abi_version: int | None = None


def _normalize_backend(name: str | None) -> SolverBackendName:
    value = (name or os.environ.get("XSTAR_ATOMIC_SOLVER_BACKEND") or "python").strip().lower()
    if value not in _VALID_BACKENDS:
        raise ValueError(f"invalid solver backend {name!r}; expected python, cpp, or auto")
    return value  # type: ignore[return-value]


def set_solver_backend(name: str | None) -> SolverBackendName:
    """Set the process-wide solver backend for source-port linear solves."""
    global _CURRENT_BACKEND
    _CURRENT_BACKEND = _normalize_backend(name)
    os.environ["XSTAR_ATOMIC_SOLVER_BACKEND"] = _CURRENT_BACKEND
    return _CURRENT_BACKEND


def get_solver_backend() -> SolverBackendName:
    """Return the configured backend, honoring the environment if it changed."""
    return _normalize_backend(os.environ.get("XSTAR_ATOMIC_SOLVER_BACKEND", _CURRENT_BACKEND))


def _candidate_library_paths() -> list[Path]:
    env_path = os.environ.get("XSTAR_ATOMIC_SOLVER_LIB")
    paths: list[Path] = []
    if env_path:
        paths.append(Path(env_path).expanduser())

    # Runtime loader anchor.  This works both for installed packages and for
    # source-tree execution such as ``PYTHONPATH=src python ...`` because
    # ``__file__`` points at ``src/xstar_atomic/source_port/solver_backend.py``.
    here = Path(__file__).resolve().parent
    names = (
        "libxstar_solver.so",
        "xstar_solver.so",
        "libxstar_solver.dylib",
        "xstar_solver.dll",
    )

    # Preferred source-tree/install location.  As of v0.5.60 the shared
    # libraries live in one place under source_port/cpp; the historical copy
    # beside this module is kept only as a backward-compatible fallback.
    source_tree_cpp_dir = here / "cpp"
    for name in names:
        paths.append(source_tree_cpp_dir / name)

    # Backward-compatible fallback for v0.5.43-v0.5.59 runtime copies beside
    # this module.
    for name in names:
        paths.append(here / name)

    # Backward-compatible fallback for v0.5.43-v0.5.44 package-internal builds.
    old_source_tree_cpp_dir = here / "cpp" / "xstar_solver"
    for name in names:
        paths.append(old_source_tree_cpp_dir / name)

    # Backward-compatible fallback for older v0.5.39-v0.5.42 trees that kept
    # cpp/xstar_solver at repository root.  This can be removed after the
    # xstar_tools layout transition.
    repo_root_cpp_dir = here.parents[2] / "cpp" / "xstar_solver" if len(here.parents) >= 3 else here / "cpp" / "xstar_solver"
    for name in names:
        paths.append(repo_root_cpp_dir / name)

    # Deduplicate while preserving order.
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
            lib.xstar_solver_abi_version.argtypes = []
            lib.xstar_solver_abi_version.restype = ctypes.c_int
            lib.xstar_solver_backend_name.argtypes = []
            lib.xstar_solver_backend_name.restype = ctypes.c_char_p
            lib.xstar_solver_leqt2f.argtypes = [
                ctypes.POINTER(ctypes.c_double),
                ctypes.POINTER(ctypes.c_double),
                ctypes.c_int,
                ctypes.c_int,
                ctypes.POINTER(ctypes.c_double),
                ctypes.POINTER(ctypes.c_double),
                ctypes.POINTER(ctypes.c_double),
                ctypes.c_char_p,
                ctypes.c_size_t,
            ]
            lib.xstar_solver_leqt2f.restype = ctypes.c_int
            _CPP_LIB = lib
            _CPP_LIBRARY_PATH = str(path)
            return _CPP_LIB
        raise FileNotFoundError("no xstar_solver shared library found; attempted: " + "; ".join(attempted))
    except BaseException as exc:  # pragma: no cover - depends on optional shared lib
        _CPP_LOAD_ERROR = exc
        return None


def cpp_available() -> bool:
    return _load_cpp_library() is not None


def cpp_import_error() -> str | None:
    if _CPP_LOAD_ERROR is None:
        return None
    return f"{type(_CPP_LOAD_ERROR).__name__}: {_CPP_LOAD_ERROR}"


def _cpp_backend_name(lib: ctypes.CDLL | None) -> str | None:
    if lib is None:
        return None
    try:
        raw = lib.xstar_solver_backend_name()
        return raw.decode("ascii", errors="replace") if raw else None
    except Exception:
        return None


def _cpp_abi_version(lib: ctypes.CDLL | None) -> int | None:
    if lib is None:
        return None
    try:
        return int(lib.xstar_solver_abi_version())
    except Exception:
        return None


def resolve_active_backend(requested: str | None = None) -> SolverBackendStatus:
    req = _normalize_backend(requested or get_solver_backend())
    lib = _load_cpp_library()
    if req == "python":
        active = "python"
    elif req == "cpp":
        active = "cpp" if lib is not None else "unavailable"
    else:
        active = "cpp" if lib is not None else "python"
    return SolverBackendStatus(
        requested=req,
        active=active,
        cpp_available=lib is not None,
        cpp_import_error=cpp_import_error(),
        cpp_library_path=_CPP_LIBRARY_PATH,
        cpp_backend_name=_cpp_backend_name(lib),
        cpp_abi_version=_cpp_abi_version(lib),
    )


def call_cpp_leqt2f(a, b, *, clamp_source_range: bool = True):
    """Run the optional C++ ``leqt2f`` kernel from a shared library.

    Returns ``(solution, residual, max_scaled_residual)``.  Raises RuntimeError
    if the shared library is unavailable so callers can either fail explicitly
    (``--solver-backend cpp``) or fall back (``auto``).
    """
    lib = _load_cpp_library()
    if lib is None:
        raise RuntimeError("C++ solver shared library is not available" + (f": {cpp_import_error()}" if cpp_import_error() else ""))

    matrix = np.ascontiguousarray(a, dtype=np.float64)
    rhs = np.ascontiguousarray(b, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        raise ValueError("leqt2f C++ backend requires a square matrix")
    if rhs.ndim != 1 or rhs.shape[0] != matrix.shape[0]:
        raise ValueError("leqt2f C++ backend RHS has incompatible shape")
    n = int(matrix.shape[0])
    if n <= 0:
        raise ValueError("leqt2f C++ backend requires n > 0")
    if n > 2_147_483_647:
        raise OverflowError("matrix too large for C++ backend integer indexing")

    solution = np.empty(n, dtype=np.float64)
    residual = np.empty(n, dtype=np.float64)
    max_scaled = ctypes.c_double(0.0)
    errbuf = ctypes.create_string_buffer(4096)

    rc = lib.xstar_solver_leqt2f(
        matrix.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        rhs.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        ctypes.c_int(n),
        ctypes.c_int(1 if clamp_source_range else 0),
        solution.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        residual.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        ctypes.byref(max_scaled),
        errbuf,
        ctypes.c_size_t(len(errbuf)),
    )
    if rc != 0:
        message = errbuf.value.decode("utf-8", errors="replace") or f"xstar_solver_leqt2f failed with code {rc}"
        raise RuntimeError(message)
    return solution, residual, float(max_scaled.value)
