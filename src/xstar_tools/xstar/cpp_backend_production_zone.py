# XSTAR-PYTHON-SOURCE-CORRESPONDENCE-BEGIN
# Source correspondence:
#   Fortran: xstarcalc.f90 scientific boundary; no Fortran backend-dispatch analogue
#   Role: Python controller bridge to the qualified C++ production-zone ABI.
#   Relation: Backend dispatch only; native scientific ownership remains in source-mapped C++ kernels.
#   Concordance: BACKEND-001; ARCH-001
#   Qualification: accepted science revision 0.6.48.12.3.45.3.3.8; frozen C++ baseline 0.6.48.12.3.44.
# XSTAR-PYTHON-SOURCE-CORRESPONDENCE-END

"""Shared standalone-production controller backends for accelerated Python.

0.6.48.11.0 exposes the accepted production controller through two native
execution modes while retaining the source-faithful Python controller:

* ``cpp-all``: one C++ call owns the complete naturally terminated radial
  trajectory.
* ``cpp-zone``: a persistent native context pauses at every accepted physical
  radial-zone boundary. Python calls ``run_next_zone()`` until ``done`` while
  all controller/lifetime/workspace state remains resident in C++.
* ``python``: the accepted Python controller path (selected by the outer CLI;
  this module is not entered for that mode).

The native controller determines the number of zones from the source first-pass
predicate. No model-specific zone count is projected through Python.
"""
from __future__ import annotations

import ctypes
import json
import math
import os
from pathlib import Path
import tempfile
import time
from typing import Any

ABI_VERSION = 6048110
BACKEND_NAME = "xstar_shared_standalone_production_zone_v0648110"
_PRODUCT_NAMES = (
    "xo01_detail.fits", "xo01_detal2.fits", "xo01_detal3.fits", "xo01_detal4.fits",
    "xout_abund1.fits", "xout_cont1.fits", "xout_lines1.fits", "xout_rrc1.fits",
    "xout_spect1.fits", "xout_step.log",
)


class SharedProductionZoneError(RuntimeError):
    pass


class _ZoneResult(ctypes.Structure):
    _fields_ = [
        ("zone_index", ctypes.c_int32),
        ("dsec_evaluations", ctypes.c_int32),
        ("source_sequence", ctypes.c_int32),
        ("done_after_zone", ctypes.c_int32),
        ("seconds", ctypes.c_double),
        ("temperature_t4", ctypes.c_double),
        ("electron_fraction", ctypes.c_double),
        ("hmctot", ctypes.c_double),
        ("heating_minus_cooling_percent", ctypes.c_double),
    ]


def _cpp_dir() -> Path:
    return Path(__file__).resolve().parent / "cpp"


def _library_path() -> Path:
    override = os.environ.get("XSTAR_PRODUCTION_ZONE_LIBRARY")
    return Path(override).expanduser().resolve() if override else (_cpp_dir() / "libxstar_production_zone.so")


def _load_library() -> ctypes.CDLL:
    path = _library_path()
    if not path.is_file():
        raise SharedProductionZoneError(
            f"shared standalone-production zone library is missing: {path}; build the C++ backends first"
        )
    lib = ctypes.CDLL(str(path), mode=getattr(ctypes, "RTLD_GLOBAL", 0))
    lib.xstar_production_zone_abi_version_v0648110.argtypes = []
    lib.xstar_production_zone_abi_version_v0648110.restype = ctypes.c_int32
    lib.xstar_production_zone_backend_name_v0648110.argtypes = []
    lib.xstar_production_zone_backend_name_v0648110.restype = ctypes.c_char_p
    lib.xstar_production_zone_run_all_v0648110.argtypes = [
        ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_size_t,
    ]
    lib.xstar_production_zone_run_all_v0648110.restype = ctypes.c_int32
    lib.xstar_production_zone_context_create_v0648110.argtypes = [
        ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_void_p), ctypes.c_char_p, ctypes.c_size_t,
    ]
    lib.xstar_production_zone_context_create_v0648110.restype = ctypes.c_int32
    lib.xstar_production_zone_context_run_next_zone_v0648110.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(_ZoneResult), ctypes.c_char_p, ctypes.c_size_t,
    ]
    lib.xstar_production_zone_context_run_next_zone_v0648110.restype = ctypes.c_int32
    lib.xstar_production_zone_context_done_v0648110.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(ctypes.c_int32),
        ctypes.c_char_p, ctypes.c_size_t,
    ]
    lib.xstar_production_zone_context_done_v0648110.restype = ctypes.c_int32
    lib.xstar_production_zone_context_finalize_v0648110.argtypes = [
        ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t,
    ]
    lib.xstar_production_zone_context_finalize_v0648110.restype = ctypes.c_int32
    lib.xstar_production_zone_context_destroy_v0648110.argtypes = [ctypes.c_void_p]
    lib.xstar_production_zone_context_destroy_v0648110.restype = None
    abi = int(lib.xstar_production_zone_abi_version_v0648110())
    if abi != ABI_VERSION:
        raise SharedProductionZoneError(f"production-zone ABI mismatch: expected {ABI_VERSION}, observed {abi}")
    name = (lib.xstar_production_zone_backend_name_v0648110() or b"").decode("utf-8", "replace")
    if name != BACKEND_NAME:
        raise SharedProductionZoneError(f"production-zone backend mismatch: expected {BACKEND_NAME!r}, observed {name!r}")
    return lib


def backend_status(requested: str = "cpp-all") -> dict[str, Any]:
    try:
        lib = _load_library()
        return {
            "requested": requested, "active": requested, "cpp_available": True,
            "cpp_import_error": None, "cpp_library_path": str(_library_path()),
            "cpp_backend_name": (lib.xstar_production_zone_backend_name_v0648110() or b"").decode(),
            "cpp_abi_version": int(lib.xstar_production_zone_abi_version_v0648110()),
        }
    except Exception as exc:
        return {
            "requested": requested, "active": "unavailable", "cpp_available": False,
            "cpp_import_error": str(exc), "cpp_library_path": str(_library_path()),
            "cpp_backend_name": None, "cpp_abi_version": None,
        }


def _native_parameter_payload(run_script: str | Path, *, atdb_path: str | Path, coheat_path: str | Path):
    from .physical_runner import normalize_xstar_parameters, parse_run_xstar_script
    parsed = parse_run_xstar_script(Path(run_script))
    normalized = normalize_xstar_parameters(parsed)
    payload = dict(normalized.values)
    payload["physical_abundances"] = [float(x) for x in normalized.physical_abundances]
    payload["initial_radius_cm"] = float(normalized.initial_radius_cm)
    payload["temperature_k"] = float(normalized.temperature_k)
    payload["density"] = float(normalized.density_cm3)
    payload["ncn2"] = int(normalized.values.get("ncn2", 9999))
    payload["atomic_database"] = str(Path(atdb_path).expanduser().resolve())
    payload["coheat_file"] = str(Path(coheat_path).expanduser().resolve())
    return payload, normalized


def _prepare_inputs(run_script, atdb_path, coheat_path, output_dir, overwrite):
    if atdb_path is None:
        raise SharedProductionZoneError("native zone backend requires explicit --atdb")
    if coheat_path is None:
        raise SharedProductionZoneError("native zone backend requires explicit --coheat-data")
    atdb = Path(atdb_path).expanduser().resolve()
    coheat = Path(coheat_path).expanduser().resolve()
    if not atdb.is_file():
        raise SharedProductionZoneError(f"atdb.fits not found: {atdb}")
    if not coheat.is_file():
        raise SharedProductionZoneError(f"coheat.dat not found: {coheat}")
    out = Path(output_dir).expanduser().resolve()
    if out.exists() and not overwrite:
        raise SharedProductionZoneError(f"output directory exists and --no-overwrite was requested: {out}")
    out.mkdir(parents=True, exist_ok=True)
    for name in _PRODUCT_NAMES:
        p = out / name
        if p.exists():
            p.unlink()
    payload, normalized = _native_parameter_payload(run_script, atdb_path=atdb, coheat_path=coheat)
    return out, payload, normalized


def _rewrite_python_cpp_headers(output_dir: Path, version: str, mode: str) -> None:
    from astropy.io import fits
    creator = f"xstar_tools python with cpp backend {version}"
    origin = "xstar_tools Python with C++ backend"
    datamode = "PYTHON_CPP_ALL_ZONES" if mode == "cpp-all" else "PYTHON_CPP_ZONE_BY_ZONE"
    comment = (
        "Complete naturally terminated radial trajectory computed in one shared standalone-production C++ call."
        if mode == "cpp-all" else
        "Naturally terminated radial trajectory computed by persistent shared-production C++ zone calls."
    )
    for name in _PRODUCT_NAMES:
        if not name.endswith(".fits"):
            continue
        path = output_dir / name
        with fits.open(path, mode="update", memmap=False) as hdul:
            for hdu in hdul:
                hdu.header["CREATOR"] = (creator, "Product creator")
                hdu.header["ORIGIN"] = (origin, "Product origin")
                hdu.header["DATAMODE"] = (datamode, "Native radial-zone execution mode")
                hdu.header.add_comment(comment)
            hdul.flush(output_verify="fix")


def _validate_products(out: Path) -> dict[str, Path]:
    missing = [name for name in _PRODUCT_NAMES if not (out / name).is_file()]
    if missing:
        raise SharedProductionZoneError(f"native zone run omitted products: {missing}")
    return {name: out / name for name in _PRODUCT_NAMES}


class PersistentProductionZoneContext:
    """Persistent exact-production context used by ``--zone-backend cpp-zone``."""

    def __init__(self, *, run_script, atdb_path, coheat_path, output_dir, overwrite=True, version="0.6.48.11.0"):
        self.out, payload, self.normalized = _prepare_inputs(run_script, atdb_path, coheat_path, output_dir, overwrite)
        self.version = version
        self.lib = _load_library()
        self._tmp = tempfile.TemporaryDirectory(prefix="xstar_v0648110_params_")
        self.parameters_path = Path(self._tmp.name) / "parameters.json"
        payload["xstar_tools_zone_backend"] = "cpp-zone"
        self.parameters_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        exe = _cpp_dir() / "xstar_cpp"
        if not exe.is_file():
            exe = _library_path()
        self._context = ctypes.c_void_p()
        message = ctypes.create_string_buffer(4096)
        rc = int(self.lib.xstar_production_zone_context_create_v0648110(
            os.fsencode(self.parameters_path), os.fsencode(self.out), os.fsencode(exe),
            ctypes.byref(self._context), message, ctypes.sizeof(message)))
        if rc != 0:
            self._tmp.cleanup()
            raise SharedProductionZoneError(
                f"cpp-zone context creation failed rc={rc}: {message.value.decode(errors='replace')}"
            )
        self.zone_results: list[dict[str, Any]] = []
        self.finalized = False
        self.started = time.perf_counter()

    def done(self) -> bool:
        if self.finalized:
            return True
        done_value = ctypes.c_int32(0)
        completed = ctypes.c_int32(0)
        message = ctypes.create_string_buffer(4096)
        rc = int(self.lib.xstar_production_zone_context_done_v0648110(
            self._context, ctypes.byref(done_value), ctypes.byref(completed),
            message, ctypes.sizeof(message)))
        if rc != 0:
            raise SharedProductionZoneError(f"cpp-zone done query failed rc={rc}: {message.value.decode(errors='replace')}")
        return bool(done_value.value)

    @property
    def completed_zones(self) -> int:
        return len(self.zone_results)

    def run_next_zone(self) -> dict[str, Any]:
        if self.finalized:
            raise SharedProductionZoneError("cpp-zone context is already finalized")
        if self.done():
            raise SharedProductionZoneError("cpp-zone radial loop is already complete")
        result = _ZoneResult()
        message = ctypes.create_string_buffer(4096)
        rc = int(self.lib.xstar_production_zone_context_run_next_zone_v0648110(
            self._context, ctypes.byref(result), message, ctypes.sizeof(message)))
        if rc != 0:
            raise SharedProductionZoneError(f"cpp-zone run_next_zone failed rc={rc}: {message.value.decode(errors='replace')}")
        zone_index = int(result.zone_index)
        row = {
            "zone_index": zone_index,
            "dsec_evaluations": int(result.dsec_evaluations),
            "source_sequence": int(result.source_sequence),
            "done_after_zone": bool(result.done_after_zone),
            "seconds": float(result.seconds),
            "temperature_t4": float(result.temperature_t4),
            "log_temperature_k": 4.0 + math.log10(float(result.temperature_t4)),
            "electron_fraction": float(result.electron_fraction),
            "hmctot": float(result.hmctot),
            "heating_minus_cooling_percent": float(result.heating_minus_cooling_percent),
        }
        if zone_index != len(self.zone_results) + 1:
            raise SharedProductionZoneError(
                f"cpp-zone returned non-sequential zone {zone_index}; expected {len(self.zone_results) + 1}"
            )
        self.zone_results.append(row)
        print(
            f"V0648110_CPP_ZONE{zone_index}_SECONDS={row['seconds']:.9f}\n"
            f"V0648110_CPP_ZONE{zone_index}_DSEC_EVALUATIONS={row['dsec_evaluations']}\n"
            f"V0648110_CPP_ZONE{zone_index}_SOURCE_SEQUENCE={row['source_sequence']}\n"
            f"V0648110_CPP_ZONE{zone_index}_T4={row['temperature_t4']:.17g}\n"
            f"V0648110_CPP_ZONE{zone_index}_LOGT={row['log_temperature_k']:.9f}\n"
            f"V0648110_CPP_ZONE{zone_index}_XEE={row['electron_fraction']:.17g}\n"
            f"V0648110_CPP_ZONE{zone_index}_HC_PERCENT={row['heating_minus_cooling_percent']:.9f}\n"
            f"V0648110_CPP_ZONE{zone_index}_DONE_AFTER_ZONE={'YES' if row['done_after_zone'] else 'NO'}",
            flush=True,
        )
        return row

    # Compatibility with callers that still explicitly pass the next ordinal.
    def run_zone(self, zone_index: int) -> dict[str, Any]:
        expected = len(self.zone_results) + 1
        if int(zone_index) != expected:
            raise SharedProductionZoneError(f"cpp-zone calls must be sequential; expected zone {expected}")
        return self.run_next_zone()

    def finalize(self) -> dict[str, Any]:
        if self.finalized:
            raise SharedProductionZoneError("cpp-zone context is already finalized")
        if not self.done():
            raise SharedProductionZoneError("cpp-zone finalize requires the native radial loop to be complete")
        message = ctypes.create_string_buffer(4096)
        rc = int(self.lib.xstar_production_zone_context_finalize_v0648110(
            self._context, message, ctypes.sizeof(message)))
        if rc != 0:
            raise SharedProductionZoneError(f"cpp-zone finalize failed rc={rc}: {message.value.decode(errors='replace')}")
        self.finalized = True
        products = _validate_products(self.out)
        _rewrite_python_cpp_headers(self.out, self.version, "cpp-zone")
        elapsed = time.perf_counter() - self.started
        return _summary(self.out, self.normalized, products, "cpp-zone", self.zone_results, elapsed)

    def close(self) -> None:
        if getattr(self, "_context", None):
            self.lib.xstar_production_zone_context_destroy_v0648110(self._context)
            self._context = ctypes.c_void_p()
        if getattr(self, "_tmp", None):
            self._tmp.cleanup()
            self._tmp = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


def _summary(out, normalized, products, mode, zone_results, elapsed):
    status = backend_status(mode)
    return {
        "ready": True,
        "parameters": normalized.as_dict(),
        "output_dir": str(out),
        "products": {k: str(v) for k, v in products.items()},
        "completed_passes": 1,
        "completed_zones": len(zone_results) if mode == "cpp-zone" else _infer_zone_count_from_step_log(out / "xout_step.log"),
        "source_order": ["shared_standalone_production_controller"],
        "warnings": [],
        "zone_results": zone_results,
        "provenance": {
            "xstar_outputs_used_as_python_inputs": False,
            "zone_backend": status,
            "solver_backend": status,
            "rates_backend": status,
            "matrix_backend": status,
            "emissivity_backend": status,
            "opacity_backend": status,
            "thermal_backend": status,
            "engine_backend": status,
            "zone_backend_mode": mode,
            "shared_standalone_production_engine": True,
            "shared_translation_unit": "xstar_standalone.cpp",
            "persistent_cpp_context": mode == "cpp-zone",
            "native_controller_owns_transport": True,
            "native_controller_owns_products": True,
            "python_header_projection_only": True,
            "variable_zone_source_predicate": True,
            "wall_seconds": elapsed,
            "backend_selection": {k: "cpp" for k in (
                "global_backend", "solver_backend", "rates_backend", "matrix_backend",
                "emissivity_backend", "opacity_backend", "thermal_backend", "engine_backend")}
                | {"zone_backend": mode},
        },
    }


def _infer_zone_count_from_step_log(path: Path) -> int:
    """Count physical first-pass controller rows, excluding terminal pprint."""
    if not path.is_file():
        return 0
    rows = 0
    saw_header = False
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "log(r)" in line and "delr/r" in line:
            saw_header = True
            continue
        if not saw_header:
            continue
        if "final print:" in line:
            break
        fields = line.split()
        if len(fields) < 12:
            continue
        try:
            [float(x) for x in fields[:11]]
            int(fields[11])
        except ValueError:
            continue
        rows += 1
    return max(0, rows - 1)


def run_shared_production_zone_backend(
    *, mode, run_script, atdb_path, coheat_path, output_dir, overwrite=True, version="0.6.48.11.0"
):
    if mode not in {"cpp-all", "cpp-zone"}:
        raise SharedProductionZoneError(f"unsupported native zone mode: {mode}")
    if mode == "cpp-zone":
        with PersistentProductionZoneContext(
            run_script=run_script, atdb_path=atdb_path, coheat_path=coheat_path,
            output_dir=output_dir, overwrite=overwrite, version=version,
        ) as ctx:
            while not ctx.done():
                ctx.run_next_zone()
                if len(ctx.zone_results) > 3999:
                    raise SharedProductionZoneError("cpp-zone exceeded source 3999-zone safety bound")
            return ctx.finalize()

    out, payload, normalized = _prepare_inputs(run_script, atdb_path, coheat_path, output_dir, overwrite)
    payload["xstar_tools_zone_backend"] = "cpp-all"
    lib = _load_library()
    exe = _cpp_dir() / "xstar_cpp"
    if not exe.is_file():
        exe = _library_path()
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="xstar_v0648110_params_") as tmp:
        parameters_path = Path(tmp) / "parameters.json"
        parameters_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        message = ctypes.create_string_buffer(4096)
        rc = int(lib.xstar_production_zone_run_all_v0648110(
            os.fsencode(parameters_path), os.fsencode(out), os.fsencode(exe), message, ctypes.sizeof(message)))
    elapsed = time.perf_counter() - started
    if rc != 0:
        raise SharedProductionZoneError(f"cpp-all failed rc={rc}: {message.value.decode(errors='replace')}")
    products = _validate_products(out)
    _rewrite_python_cpp_headers(out, version, "cpp-all")
    return _summary(out, normalized, products, "cpp-all", [], elapsed)
