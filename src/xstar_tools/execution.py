"""Stable public execution modes for xstar-tools.

This module is intentionally a thin productization layer over the qualified
execution paths.  It does not implement scientific calculations itself.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, replace
from enum import Enum
from hashlib import sha256
import json
import ctypes
import os
from pathlib import Path
import platform
import subprocess
import tempfile
import time
import shutil
from typing import Any, Mapping
from contextlib import contextmanager

SCIENCE_REVISION = "0.6.48.12.3.45.3.3.8"
ZONE_ABI_VERSION = 6048110
C_API_ABI_VERSION = 60487


class ExecutionMode(str, Enum):
    PURE_PYTHON = "pure-python"
    ZONE_PYTHON = "zone-python"
    ZONE_CPP = "zone-cpp"
    ZONE_ALL = "zone-all"
    XSTAR_CPP = "xstar-cpp"


# Backward-compatible public spelling used by the productization roadmap.
BackendMode = ExecutionMode


@dataclass(frozen=True)
class ModeMapping:
    public_mode: str
    controller: str
    zone_backend: str
    global_backend: str
    solver_backend: str
    rates_backend: str
    matrix_backend: str
    emissivity_backend: str
    opacity_backend: str
    thermal_backend: str
    engine_backend: str
    standalone: bool = False
    legacy_alias: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return dict(asdict(self))


_MODE_MAPPINGS: dict[str, ModeMapping] = {
    "pure-python": ModeMapping(
        "pure-python", "python", "python", "python", "python", "python", "python",
        "python", "python", "python", "python", False, "--zone-backend python --backend python --solver-backend python",
    ),
    "zone-python": ModeMapping(
        "zone-python", "python", "python", "cpp", "cpp", "cpp", "cpp", "cpp", "cpp", "cpp", "cpp", False,
        "--zone-backend python --backend cpp --solver-backend cpp",
    ),
    "zone-cpp": ModeMapping(
        "zone-cpp", "cpp-shared-zone", "cpp-zone", "cpp", "cpp", "cpp", "cpp", "cpp", "cpp", "cpp", "cpp", False,
        "--zone-backend cpp-zone --backend cpp --solver-backend cpp",
    ),
    "zone-all": ModeMapping(
        "zone-all", "cpp-shared-all", "cpp-all", "cpp", "cpp", "cpp", "cpp", "cpp", "cpp", "cpp", "cpp", False,
        "--zone-backend cpp-all --backend cpp --solver-backend cpp",
    ),
    "xstar-cpp": ModeMapping(
        "xstar-cpp", "native-standalone", "native", "cpp", "cpp", "cpp", "cpp", "cpp", "cpp", "cpp", "cpp", True,
        "xstar_cpp run-production",
    ),
}


def normalize_mode(mode: str | ExecutionMode | None) -> str:
    value = ExecutionMode.PURE_PYTHON.value if mode is None else str(getattr(mode, "value", mode)).strip().lower()
    aliases = {
        "python": "pure-python",
        "cpp-zone": "zone-cpp",
        "cpp-all": "zone-all",
        "accelerated-python": "zone-python",
        "xstar_cpp": "xstar-cpp",
    }
    value = aliases.get(value, value)
    if value not in _MODE_MAPPINGS:
        raise ValueError(f"invalid execution mode {mode!r}; expected {', '.join(_MODE_MAPPINGS)}")
    return value


def resolve_mode(mode: str | ExecutionMode | None) -> ModeMapping:
    return _MODE_MAPPINGS[normalize_mode(mode)]


def infer_public_mode(*, zone_backend: str = "python", backend: str = "python", solver_backend: str = "python",
                      rates_backend: str | None = None, matrix_backend: str | None = None,
                      emissivity_backend: str | None = None) -> str:
    """Map legacy backend flags to a stable public name when the mapping is exact."""
    zone = str(zone_backend or "python").strip().lower()
    glob = str(backend or "python").strip().lower()
    solver = str(solver_backend or "python").strip().lower()
    rates = str(rates_backend or glob).strip().lower()
    matrix = str(matrix_backend or glob).strip().lower()
    emis = str(emissivity_backend or glob).strip().lower()
    if zone == "python" and all(x == "python" for x in (glob, solver, rates, matrix, emis)):
        return "pure-python"
    if zone == "python" and all(x == "cpp" for x in (glob, solver, rates, matrix, emis)):
        return "zone-python"
    if zone == "cpp-zone" and all(x == "cpp" for x in (glob, solver, rates, matrix, emis)):
        return "zone-cpp"
    if zone == "cpp-all" and all(x == "cpp" for x in (glob, solver, rates, matrix, emis)):
        return "zone-all"
    return "advanced"


def package_version() -> str:
    # Prefer the active source checkout so an older installed distribution does
    # not mask the version being developed/tested.  Installed wheels fall back
    # to importlib.metadata because pyproject.toml is not shipped beside modules.
    try:
        root = Path(__file__).resolve().parents[2]
        for line in (root / "pyproject.toml").read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("version ="):
                return line.split("=", 1)[1].strip().strip('"\'')
    except Exception:
        pass
    try:
        from importlib.metadata import version
        return str(version("xstar-tools")).strip()
    except Exception:
        return "unknown"


def _sha256_file(path: str | Path | None) -> str | None:
    if path is None:
        return None
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        return None
    h = sha256()
    with p.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def cpu_features() -> dict[str, Any]:
    flags: set[str] = set()
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.lower().startswith(("flags", "features")) and ":" in line:
                flags.update(line.split(":", 1)[1].strip().lower().split())
                break
    except OSError:
        pass
    return {
        "machine": platform.machine(),
        "avx2": "avx2" in flags,
        "avx": "avx" in flags,
        "sse2": "sse2" in flags,
        "type50_dispatch": "runtime-avx2-or-scalar" if platform.machine().lower() in {"x86_64", "amd64", "i386", "i686"} else "scalar/non-x86",
    }


def atomic_data_identity(atdb_path: str | Path | None, coheat_path: str | Path | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {}
    resolved_atdb: Path | None = None
    if atdb_path is not None:
        resolved_atdb = Path(atdb_path).expanduser().resolve()
        result["atdb_path"] = str(resolved_atdb)
        result["atdb_sha256"] = _sha256_file(resolved_atdb)
    resolved_coheat: Path | None = None
    if coheat_path is not None:
        resolved_coheat = Path(coheat_path).expanduser().resolve()
    elif resolved_atdb is not None:
        try:
            from .xstar.compton import resolve_coheat_path
            resolved_coheat = resolve_coheat_path(None, atdb_path=resolved_atdb)
        except Exception:
            resolved_coheat = None
    if resolved_coheat is not None:
        result["coheat_path"] = str(resolved_coheat)
        result["coheat_sha256"] = _sha256_file(resolved_coheat)
    return result


def _api_library_identity() -> dict[str, Any]:
    path = _cpp_dir() / "libxstar_api.so"
    if not path.is_file():
        return {"available": False, "path": str(path), "version": None, "abi": None}
    try:
        lib = ctypes.CDLL(str(path))
        lib.xstar_api_version_string.argtypes = []
        lib.xstar_api_version_string.restype = ctypes.c_char_p
        lib.xstar_api_abi_version.argtypes = []
        lib.xstar_api_abi_version.restype = ctypes.c_uint32
        raw = lib.xstar_api_version_string()
        return {"available": True, "path": str(path), "version": raw.decode("utf-8", "replace") if raw else None,
                "abi": int(lib.xstar_api_abi_version())}
    except Exception as exc:
        return {"available": False, "path": str(path), "version": None, "abi": None, "error": str(exc)}


def cpp_identity_for_mode(mode: str) -> dict[str, Any]:
    name = normalize_mode(mode)
    if name == "pure-python":
        return {"used": False, "api": _api_library_identity(), "standalone": native_executable_info()}
    if name == "xstar-cpp":
        return {"used": True, "api": _api_library_identity(), "standalone": native_executable_info()}
    if name in {"zone-cpp", "zone-all"}:
        try:
            from .xstar.cpp_backend_production_zone import backend_status
            internal = "cpp-zone" if name == "zone-cpp" else "cpp-all"
            zone = backend_status(internal)
        except Exception as exc:
            zone = {"requested": name, "active": "unavailable", "cpp_import_error": str(exc)}
        return {"used": True, "api": _api_library_identity(), "production_zone": zone, "standalone": native_executable_info()}
    # zone-python: report the modular libraries independently.
    try:
        from dataclasses import asdict, is_dataclass
        from .xstar.solver_backend import resolve_active_backend
        from .xstar.cpp_backend_rates import rates_backend_status
        from .xstar.cpp_backend_matrix import matrix_backend_status
        from .xstar.cpp_backend_emissivity import emissivity_backend_status
        from .xstar.cpp_backend_extra import opacity_backend_status, thermal_backend_status, engine_backend_status
        def d(value):
            return asdict(value) if is_dataclass(value) else dict(value)
        components = {
            "solver": d(resolve_active_backend("cpp")), "rates": d(rates_backend_status("cpp")),
            "matrix": d(matrix_backend_status("cpp")), "emissivity": d(emissivity_backend_status("cpp")),
            "opacity": d(opacity_backend_status("cpp")), "thermal": d(thermal_backend_status("cpp")),
            "engine": d(engine_backend_status("cpp")),
        }
    except Exception as exc:
        components = {"error": str(exc)}
    return {"used": True, "api": _api_library_identity(), "components": components, "standalone": native_executable_info()}


def collect_fallback_events(provenance: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    prov = dict(provenance or {})
    for key in ("solver_backend", "rates_backend", "matrix_backend", "emissivity_backend", "opacity_backend", "thermal_backend", "engine_backend", "zone_backend"):
        value = prov.get(key)
        if not isinstance(value, Mapping):
            continue
        requested = str(value.get("requested", ""))
        active = str(value.get("active", ""))
        if requested in {"cpp", "cpp-zone", "cpp-all"} and active and active not in {"cpp", "cpp-zone", "cpp-all"}:
            events.append({"component": key, "requested": requested, "active": active, "reason": value.get("cpp_import_error")})
    return events


def actual_mode_from_provenance(requested_mode: str, provenance: Mapping[str, Any] | None) -> str:
    requested = normalize_mode(requested_mode)
    if requested in {"pure-python", "zone-cpp", "zone-all", "xstar-cpp"}:
        return requested
    fallbacks = collect_fallback_events(provenance)
    return "zone-python" if not fallbacks else "zone-python-with-fallbacks"


def advanced_execution_provenance(*, provenance: Mapping[str, Any] | None = None,
                                  atdb_path: str | Path | None = None, coheat_path: str | Path | None = None,
                                  mapping: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Provenance envelope for legacy/custom backend combinations.

    Stable public modes use :func:`execution_provenance`.  This companion keeps
    advanced compatibility aliases observable without pretending that a mixed
    custom selection is one of the five stable modes.
    """
    prov = dict(provenance or {})
    selected = dict(mapping or {})
    cpp_requested = any(str(value).lower() in {"cpp", "cpp-zone", "cpp-all"} for value in selected.values())
    return {
        "requested_mode": "advanced",
        "actual_mode": "advanced",
        "mapping": selected,
        "package_version": package_version(),
        "science_revision": SCIENCE_REVISION,
        "c_api_abi": C_API_ABI_VERSION,
        "zone_abi": ZONE_ABI_VERSION,
        "cpp": {"used": cpp_requested, "api": _api_library_identity(), "standalone": native_executable_info()},
        "cpu": cpu_features(),
        "fallback_events": collect_fallback_events(prov),
        "atomic_data": atomic_data_identity(atdb_path, coheat_path),
    }


def execution_provenance(*, requested_mode: str, provenance: Mapping[str, Any] | None = None,
                         atdb_path: str | Path | None = None, coheat_path: str | Path | None = None,
                         cpp: Mapping[str, Any] | None = None) -> dict[str, Any]:
    mode = normalize_mode(requested_mode)
    mapping = resolve_mode(mode)
    prov = dict(provenance or {})
    return {
        "requested_mode": mode,
        "actual_mode": actual_mode_from_provenance(mode, prov),
        "mapping": mapping.as_dict(),
        "package_version": package_version(),
        "science_revision": SCIENCE_REVISION,
        "c_api_abi": C_API_ABI_VERSION,
        "zone_abi": ZONE_ABI_VERSION,
        "cpp": dict(cpp) if cpp is not None else cpp_identity_for_mode(mode),
        "cpu": cpu_features(),
        "fallback_events": collect_fallback_events(prov),
        "atomic_data": atomic_data_identity(atdb_path, coheat_path),
    }


def _cpp_dir() -> Path:
    return Path(__file__).resolve().parent / "xstar" / "cpp"


def native_executable_candidates() -> list[Path]:
    paths: list[Path] = []
    if os.environ.get("XSTAR_CPP_EXECUTABLE"):
        paths.append(Path(os.environ["XSTAR_CPP_EXECUTABLE"]).expanduser())
    paths.extend((_cpp_dir() / "xstar-cpp", _cpp_dir() / "xstar_cpp"))
    return paths


def native_executable_path() -> Path | None:
    for p in native_executable_candidates():
        if p.is_file() and os.access(p, os.X_OK):
            return p.resolve()
    return None


def native_build_info() -> dict[str, Any]:
    path = _cpp_dir() / "native_build.json"
    if not path.is_file():
        return {"metadata_available": False, "path": str(path)}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return {"metadata_available": True, "path": str(path), **dict(payload)}
    except Exception as exc:
        return {"metadata_available": False, "path": str(path), "error": str(exc)}


def native_executable_info() -> dict[str, Any]:
    path = native_executable_path()
    build = native_build_info()
    if path is None:
        return {"available": False, "path": None, "version": None, "build": build,
                "error": "xstar-cpp executable not found"}
    try:
        proc = subprocess.run([str(path), "--version"], text=True, capture_output=True, timeout=5, check=False)
        version = proc.stdout.strip() if proc.returncode == 0 else None
        return {"available": proc.returncode == 0, "path": str(path), "version": version, "returncode": proc.returncode,
                "build": build, "error": proc.stderr.strip() or None}
    except Exception as exc:
        return {"available": False, "path": str(path), "version": None, "build": build, "error": str(exc)}


@contextmanager
def _backend_environment(mapping: ModeMapping):
    names = {
        "XSTAR_ATOMIC_BACKEND": mapping.global_backend,
        "XSTAR_ATOMIC_SOLVER_BACKEND": mapping.solver_backend,
        "XSTAR_ATOMIC_RATES_BACKEND": mapping.rates_backend,
        "XSTAR_ATOMIC_MATRIX_BACKEND": mapping.matrix_backend,
        "XSTAR_ATOMIC_EMISSIVITY_BACKEND": mapping.emissivity_backend,
        "XSTAR_ATOMIC_OPACITY_BACKEND": mapping.opacity_backend,
        "XSTAR_ATOMIC_THERMAL_BACKEND": mapping.thermal_backend,
        "XSTAR_ATOMIC_ENGINE_BACKEND": mapping.engine_backend,
    }
    old = {key: os.environ.get(key) for key in names}
    try:
        os.environ.update(names)
        yield
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@dataclass(frozen=True)
class PublicRunResult:
    ready: bool
    mode: str
    summary: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {"ready": self.ready, "mode": self.mode, **dict(self.summary)}


def _native_payload_from_command(command: str, *, atdb_path: str | Path, coheat_path: str | Path) -> dict[str, Any]:
    from .xstar_run import parse_xstar_command
    from .xstar.physical_runner import normalize_xstar_parameters
    parsed = parse_xstar_command(command)
    normalized = normalize_xstar_parameters(parsed)
    payload = dict(normalized.values)
    payload["physical_abundances"] = [float(x) for x in normalized.physical_abundances]
    payload["initial_radius_cm"] = float(normalized.initial_radius_cm)
    payload["temperature_k"] = float(normalized.temperature_k)
    payload["density"] = float(normalized.density_cm3)
    payload["ncn2"] = int(normalized.values.get("ncn2", 9999))
    payload["atomic_database"] = str(Path(atdb_path).expanduser().resolve())
    payload["coheat_file"] = str(Path(coheat_path).expanduser().resolve())
    return payload


def _run_xstar_legacy(*, mode: str | ExecutionMode = ExecutionMode.PURE_PYTHON, run_script: str | Path | None = None,
              command: str | None = None, atdb_path: str | Path | None = None,
              coheat_path: str | Path | None = None, output_dir: str | Path = ".",
              _mapping_override: ModeMapping | None = None, **kwargs: Any) -> PublicRunResult:
    """Run XSTAR through one of the five stable public execution modes.

    Advanced/internal backend flags remain available through the legacy runner;
    this function deliberately accepts only the stable public mode boundary.
    """
    mode_name = normalize_mode(mode)
    mapping = _mapping_override or resolve_mode(mode_name)
    if (run_script is None) == (command is None):
        raise ValueError("exactly one of run_script or command is required")
    if mapping.standalone:
        if atdb_path is None or coheat_path is None:
            raise ValueError("xstar-cpp requires explicit atdb_path and coheat_path")
        exe = native_executable_path()
        if exe is None:
            raise RuntimeError("xstar-cpp executable is not available; build the C++ standalone target")
        if run_script is not None:
            from .xstar.cpp_backend_production_zone import _native_parameter_payload
            payload, _ = _native_parameter_payload(run_script, atdb_path=atdb_path, coheat_path=coheat_path)
        else:
            payload = _native_payload_from_command(str(command), atdb_path=atdb_path, coheat_path=coheat_path)
        out = Path(output_dir).expanduser().resolve()
        out.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="xstar_tools_public_mode_") as td:
            params = Path(td) / "parameters.json"
            params.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            proc = subprocess.run([str(exe), "run-production", "--parameters", str(params), "--output-dir", str(out)],
                                  text=True, capture_output=True, check=False)
        summary = {
            "output_dir": str(out), "returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr,
            "provenance": {"execution": execution_provenance(requested_mode=mode_name, atdb_path=atdb_path,
                coheat_path=coheat_path, cpp={"standalone": native_executable_info()})},
        }
        return PublicRunResult(proc.returncode == 0, mode_name, summary)

    if mapping.zone_backend in {"cpp-zone", "cpp-all"}:
        if run_script is None:
            raise ValueError(f"{mode_name} currently requires run_script so the existing qualified shared-production path is selected exactly")
        from .xstar.cpp_backend_production_zone import run_shared_production_zone_backend
        summary = run_shared_production_zone_backend(
            mode=mapping.zone_backend, run_script=run_script, atdb_path=atdb_path, coheat_path=coheat_path,
            output_dir=output_dir, overwrite=bool(kwargs.pop("overwrite", True)), version=package_version(),
        )
        prov = dict(summary.get("provenance", {}))
        prov["execution"] = execution_provenance(requested_mode=mode_name, provenance=prov, atdb_path=atdb_path,
            coheat_path=coheat_path)
        summary["provenance"] = prov
        return PublicRunResult(bool(summary.get("ready")), mode_name, summary)

    from .xstar.physical_runner import run_xstar_python_script, run_xstar_python_command
    call = run_xstar_python_script if run_script is not None else run_xstar_python_command
    source = run_script if run_script is not None else command
    with _backend_environment(mapping):
        result = call(
            source, atdb_path=atdb_path, coheat_path=coheat_path, output_dir=output_dir,
            backend=mapping.global_backend, rates_backend=mapping.rates_backend,
            matrix_backend=mapping.matrix_backend, emissivity_backend=mapping.emissivity_backend,
            **kwargs,
        )
    summary = result.as_dict()
    prov = dict(summary.get("provenance", {}))
    prov["execution"] = execution_provenance(requested_mode=mode_name, provenance=prov,
        atdb_path=prov.get("atdb_path", atdb_path), coheat_path=coheat_path)
    summary["provenance"] = prov
    return PublicRunResult(bool(summary.get("ready")), mode_name, summary)


def _config_progress_callback(event: str, details: Mapping[str, Any]) -> None:
    detail = " ".join(f"{key}={value}" for key, value in sorted(details.items()))
    print(f"xstar: {event}" + (f" {detail}" if detail else ""), flush=True)


@contextmanager
def _public_run_environment(*, threads: int, reproducible: bool):
    updates = {"OMP_NUM_THREADS": str(int(threads)), "XSTAR_TOOLS_REPRODUCIBLE": "1" if reproducible else "0"}
    old = {key: os.environ.get(key) for key in updates}
    try:
        os.environ.update(updates)
        yield
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _mapping_with_advanced_overrides(mapping: ModeMapping, overrides: Mapping[str, str]) -> ModeMapping:
    if not overrides:
        return mapping
    fields: dict[str, str] = {}
    rename = {"backend": "global_backend"}
    for key, value in overrides.items():
        fields[rename.get(key, key)] = value
    return replace(mapping, **fields)


def _prepare_public_output_directory(path: Path, *, overwrite: bool) -> Path:
    out = Path(path).expanduser().resolve()
    if out.exists() and any(out.iterdir()):
        if not overwrite:
            raise FileExistsError(
                f"output directory is not empty: {out}; pass overwrite=True to replace it deterministically"
            )
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    return out


def _run_xstar_config(config: Any):
    from .config import XStarConfig
    from .data import XStarData
    from .result import XStarProducts, XStarResult

    if not isinstance(config, XStarConfig):
        raise TypeError("run_xstar(config) requires an XStarConfig instance")
    config.validate()
    data = config.data_dir if isinstance(config.data_dir, XStarData) else XStarData.from_directory(config.data_dir)
    data.validate()
    output_dir = _prepare_public_output_directory(Path(config.output_dir), overwrite=bool(config.overwrite))
    mapping = _mapping_with_advanced_overrides(resolve_mode(config.mode_name), config.advanced_backend_overrides)

    legacy_kwargs: dict[str, Any] = {
        "mode": config.mode_name,
        "atdb_path": data.atdb,
        "coheat_path": data.coheat,
        "output_dir": output_dir,
        "overwrite": True,
        "_mapping_override": mapping,
    }
    if config.cache_dir is not None:
        legacy_kwargs["cache_dir"] = config.cache_dir
    legacy_kwargs["use_cache"] = bool(config.use_cache)
    legacy_kwargs["rebuild_cache"] = bool(config.rebuild_cache)
    if config.progress and config.mode_name in {"pure-python", "zone-python"}:
        legacy_kwargs["progress_callback"] = _config_progress_callback

    source_script = config.source_run_script()
    temp_dir = None
    if source_script is not None:
        legacy_kwargs["run_script"] = source_script
    else:
        command = config.to_xstar_command()
        if config.mode_name in {"zone-cpp", "zone-all"}:
            temp_dir = tempfile.TemporaryDirectory(prefix="xstar_tools_public_config_")
            script = Path(temp_dir.name) / "run_xstar.sh"
            script.write_text("#!/bin/sh\n" + command + "\n", encoding="utf-8")
            legacy_kwargs["run_script"] = script
        else:
            legacy_kwargs["command"] = command

    started = time.perf_counter()
    try:
        with _public_run_environment(threads=config.threads, reproducible=config.reproducible):
            legacy = _run_xstar_legacy(**legacy_kwargs)
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()
    elapsed = time.perf_counter() - started

    summary = dict(legacy.summary)
    provenance = dict(summary.get("provenance", {}))
    underlying_execution = dict(provenance.get("execution", {}))
    execution = execution_provenance(
        requested_mode=config.mode_name, provenance=provenance, atdb_path=data.atdb, coheat_path=data.coheat,
        cpp=underlying_execution.get("cpp") if isinstance(underlying_execution.get("cpp"), Mapping) else None,
    )
    execution.update(underlying_execution)
    execution.update({
        "public_api": "XStarConfig",
        "input_source_kind": config.source_kind,
        "threads": int(config.threads),
        "reproducible": bool(config.reproducible),
        "advanced_backend_overrides": dict(config.advanced_backend_overrides),
    })
    if config.advanced_backend_overrides:
        execution["actual_mode"] = "advanced"
    provenance["execution"] = execution
    provenance["data"] = data.identity()

    return_code = int(summary.get("returncode", 0 if legacy.ready else 1))
    success = bool(legacy.ready) and return_code == 0
    products = XStarProducts(output_dir)
    diagnostics_raw = summary.get("diagnostics", ())
    warnings_raw = summary.get("warnings", ())
    diagnostics = tuple(str(x) for x in diagnostics_raw) if isinstance(diagnostics_raw, (list, tuple)) else (() if not diagnostics_raw else (str(diagnostics_raw),))
    warnings = tuple(str(x) for x in warnings_raw) if isinstance(warnings_raw, (list, tuple)) else (() if not warnings_raw else (str(warnings_raw),))
    fallback_events = execution.get("fallback_events", provenance.get("fallback_events", ()))
    if isinstance(fallback_events, (list, tuple)):
        warnings = warnings + tuple(f"backend fallback: {item}" for item in fallback_events)
    timings = summary.get("timings", summary.get("runtime_profile", {}))
    if not isinstance(timings, Mapping):
        timings = {}
    return XStarResult(
        success=success, status="success" if success else "failed", return_code=return_code,
        output_dir=output_dir, products=products, step_log=products.step_log, runtime_seconds=float(elapsed),
        timings=dict(timings), provenance=provenance, diagnostics=diagnostics, warnings=warnings, raw_summary=summary,
    )


def run_xstar(config: Any = None, *, mode: str | ExecutionMode = ExecutionMode.PURE_PYTHON,
              run_script: str | Path | None = None, command: str | None = None,
              atdb_path: str | Path | None = None, coheat_path: str | Path | None = None,
              output_dir: str | Path = ".", **kwargs: Any):
    """Run XSTAR through the stable public API.

    Recommended usage is ``run_xstar(XStarConfig(...))``.  The Milestone-3
    keyword-style call remains a compatibility alias and returns
    :class:`PublicRunResult`.
    """
    if config is not None:
        if any(x is not None for x in (run_script, command, atdb_path, coheat_path)) or output_dir != "." or mode != ExecutionMode.PURE_PYTHON or kwargs:
            raise TypeError("run_xstar(XStarConfig) cannot be combined with legacy execution keyword arguments")
        return _run_xstar_config(config)
    return _run_xstar_legacy(
        mode=mode, run_script=run_script, command=command, atdb_path=atdb_path,
        coheat_path=coheat_path, output_dir=output_dir, **kwargs,
    )


__all__ = [
    "BackendMode", "ExecutionMode", "ModeMapping", "PublicRunResult", "SCIENCE_REVISION",
    "ZONE_ABI_VERSION", "C_API_ABI_VERSION", "normalize_mode", "resolve_mode", "infer_public_mode",
    "package_version", "execution_provenance", "advanced_execution_provenance", "native_executable_info", "run_xstar",
]
