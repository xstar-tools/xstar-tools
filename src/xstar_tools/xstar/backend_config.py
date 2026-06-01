"""Backend configuration helpers for modular Python+C++ source-port kernels.

The Python implementation remains the source-faithful reference path.  These
helpers centralize environment/CLI backend names so individual kernel modules
can be developed as plain shared libraries first and later linked into a
standalone ``xstar_tools`` C++ executable.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import os
from typing import Literal, Mapping

BackendName = Literal["python", "cpp", "auto"]

_VALID_BACKENDS = {"python", "cpp", "auto"}
_KERNEL_ENV = {
    "solver": "XSTAR_ATOMIC_SOLVER_BACKEND",
    "rates": "XSTAR_ATOMIC_RATES_BACKEND",
    "matrix": "XSTAR_ATOMIC_MATRIX_BACKEND",
    "emissivity": "XSTAR_ATOMIC_EMISSIVITY_BACKEND",
}
_GLOBAL_ENV = "XSTAR_ATOMIC_BACKEND"


@dataclass(frozen=True)
class BackendSelection:
    """Normalized backend selection for the modular source-port kernels."""

    global_backend: BackendName
    solver_backend: BackendName
    rates_backend: BackendName
    matrix_backend: BackendName
    emissivity_backend: BackendName

    def as_dict(self) -> dict[str, str]:
        return dict(asdict(self))


def normalize_backend_name(value: str | None, *, default: str = "python") -> BackendName:
    name = (value or default or "python").strip().lower()
    if name not in _VALID_BACKENDS:
        raise ValueError(f"invalid backend {value!r}; expected python, cpp, or auto")
    return name  # type: ignore[return-value]


def resolve_backend_selection(
    *,
    global_backend: str | None = None,
    solver_backend: str | None = None,
    rates_backend: str | None = None,
    matrix_backend: str | None = None,
    emissivity_backend: str | None = None,
) -> BackendSelection:
    """Resolve global and per-kernel backend selections.

    Per-kernel values override the global value.  Environment variables are
    honored before the built-in default so scripts can select C++ kernels
    without changing Python call sites.
    """
    global_value = normalize_backend_name(
        global_backend or os.environ.get(_GLOBAL_ENV) or "python",
        default="python",
    )

    def one(kernel: str, explicit: str | None) -> BackendName:
        return normalize_backend_name(
            explicit or os.environ.get(_KERNEL_ENV[kernel]) or global_value,
            default=global_value,
        )

    return BackendSelection(
        global_backend=global_value,
        solver_backend=one("solver", solver_backend),
        rates_backend=one("rates", rates_backend),
        matrix_backend=one("matrix", matrix_backend),
        emissivity_backend=one("emissivity", emissivity_backend),
    )


def install_backend_environment(selection: BackendSelection) -> None:
    """Publish a selection into process environment variables."""
    os.environ[_GLOBAL_ENV] = selection.global_backend
    os.environ[_KERNEL_ENV["solver"]] = selection.solver_backend
    os.environ[_KERNEL_ENV["rates"]] = selection.rates_backend
    os.environ[_KERNEL_ENV["matrix"]] = selection.matrix_backend
    os.environ[_KERNEL_ENV["emissivity"]] = selection.emissivity_backend


def backend_selection_from_mapping(mapping: Mapping[str, object] | None) -> BackendSelection:
    data = dict(mapping or {})
    return resolve_backend_selection(
        global_backend=str(data.get("global_backend", "python")),
        solver_backend=str(data.get("solver_backend", data.get("solver", "python"))),
        rates_backend=str(data.get("rates_backend", data.get("rates", "python"))),
        matrix_backend=str(data.get("matrix_backend", data.get("matrix", "python"))),
        emissivity_backend=str(data.get("emissivity_backend", data.get("emissivity", "python"))),
    )
