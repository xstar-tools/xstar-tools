"""Capability and provenance API for stable xstar-tools execution modes."""
from __future__ import annotations

from typing import Any
from dataclasses import asdict, is_dataclass

from .execution import (
    C_API_ABI_VERSION, SCIENCE_REVISION, ZONE_ABI_VERSION, cpu_features,
    native_executable_info, package_version, resolve_mode, cpp_identity_for_mode,
)

_PUBLIC_MODES = ("pure-python", "zone-python", "zone-cpp", "zone-all", "xstar-cpp")


def _modular_cpp_status() -> dict[str, Any]:
    from .xstar.solver_backend import resolve_active_backend
    from .xstar.cpp_backend_rates import rates_backend_status
    from .xstar.cpp_backend_matrix import matrix_backend_status
    from .xstar.cpp_backend_emissivity import emissivity_backend_status
    from .xstar.cpp_backend_extra import opacity_backend_status, thermal_backend_status, engine_backend_status

    solver_status = resolve_active_backend("cpp")
    statuses = {
        "solver": asdict(solver_status) if is_dataclass(solver_status) else dict(solver_status),
        "rates": rates_backend_status("cpp").as_dict(),
        "matrix": matrix_backend_status("cpp").as_dict(),
        "emissivity": emissivity_backend_status("cpp").as_dict(),
        "opacity": opacity_backend_status("cpp").as_dict(),
        "thermal": thermal_backend_status("cpp").as_dict(),
        "engine": engine_backend_status("cpp").as_dict(),
    }
    statuses["available"] = all(str(v.get("active")) == "cpp" for v in statuses.values() if isinstance(v, dict) and "active" in v)
    return statuses


def _shared_zone_status(which: str) -> dict[str, Any]:
    from .xstar.cpp_backend_production_zone import backend_status
    return backend_status(which)


def describe() -> dict[str, Any]:
    modular = _modular_cpp_status()
    zone_cpp = _shared_zone_status("cpp-zone")
    zone_all = _shared_zone_status("cpp-all")
    native = native_executable_info()
    modes = {
        "pure-python": {"available": True, "description": "Python controller/radial flow and Python science backends; no C++ runtime required."},
        "zone-python": {"available": bool(modular.get("available")), "description": "Python controller/radial flow with qualified modular C++ kernels.", "components": modular},
        "zone-cpp": {"available": bool(zone_cpp.get("cpp_available")), "description": "Python invocation with persistent shared C++ production-zone evaluator.", "zone_backend": zone_cpp},
        "zone-all": {"available": bool(zone_all.get("cpp_available")), "description": "Python invocation with one-call shared C++ production trajectory.", "zone_backend": zone_all},
        "xstar-cpp": {"available": bool(native.get("available")), "description": "Native standalone executable; no Python runtime dependency for normal direct runs.", "standalone": native},
    }
    for name in _PUBLIC_MODES:
        modes[name]["mapping"] = resolve_mode(name).as_dict()
    return {
        "package_version": package_version(),
        "science_revision": SCIENCE_REVISION,
        "c_api_abi": C_API_ABI_VERSION,
        "zone_abi": ZONE_ABI_VERSION,
        "cpu": cpu_features(),
        "cpp_runtime": cpp_identity_for_mode("pure-python"),
        "modes": modes,
    }


def available() -> dict[str, bool]:
    data = describe()["modes"]
    return {name: bool(data[name]["available"]) for name in _PUBLIC_MODES}


__all__ = ["available", "describe"]
