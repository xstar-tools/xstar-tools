"""Optional solver backend dispatch for source-port linear solves.

This module is intentionally small and isolated so it can move cleanly to the
future layout as ``xstar_tools.xstar.solver.backend``.  The pure-Python
source-faithful implementation remains the reference path; the C++ backend is
an optional acceleration path for the dense ``leqt2f`` population solve.
"""
from __future__ import annotations

from dataclasses import dataclass
import importlib
import os
from typing import Literal, Optional

SolverBackendName = Literal["python", "cpp", "auto"]

_VALID_BACKENDS = {"python", "cpp", "auto"}
_CURRENT_BACKEND: SolverBackendName = "python"
_CPP_MODULE = None
_CPP_IMPORT_ERROR: BaseException | None = None


@dataclass(frozen=True)
class SolverBackendStatus:
    requested: str
    active: str
    cpp_available: bool
    cpp_import_error: str | None = None


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


def _load_cpp_module():
    global _CPP_MODULE, _CPP_IMPORT_ERROR
    if _CPP_MODULE is not None:
        return _CPP_MODULE
    if _CPP_IMPORT_ERROR is not None:
        return None
    try:
        _CPP_MODULE = importlib.import_module("xstar_atomic.source_port._xstar_solver_cpp")
    except BaseException as exc:  # pragma: no cover - depends on optional extension
        _CPP_IMPORT_ERROR = exc
        return None
    return _CPP_MODULE


def cpp_available() -> bool:
    return _load_cpp_module() is not None


def cpp_import_error() -> str | None:
    if _CPP_IMPORT_ERROR is None:
        return None
    return f"{type(_CPP_IMPORT_ERROR).__name__}: {_CPP_IMPORT_ERROR}"


def resolve_active_backend(requested: str | None = None) -> SolverBackendStatus:
    req = _normalize_backend(requested or get_solver_backend())
    module = _load_cpp_module()
    if req == "python":
        active = "python"
    elif req == "cpp":
        active = "cpp" if module is not None else "unavailable"
    else:
        active = "cpp" if module is not None else "python"
    return SolverBackendStatus(
        requested=req,
        active=active,
        cpp_available=module is not None,
        cpp_import_error=cpp_import_error(),
    )


def call_cpp_leqt2f(a, b, *, clamp_source_range: bool = True):
    """Run the optional C++ ``leqt2f`` kernel.

    Returns ``(solution, residual, max_scaled_residual)``.  Raises RuntimeError
    if the extension is unavailable so callers can either fail explicitly
    (``--solver-backend cpp``) or fall back (``auto``).
    """
    module = _load_cpp_module()
    if module is None:
        raise RuntimeError("C++ solver backend is not available" + (f": {cpp_import_error()}" if cpp_import_error() else ""))
    return module.leqt2f(a, b, bool(clamp_source_range))
