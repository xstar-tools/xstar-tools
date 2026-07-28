"""Shared standalone-production controller backend for accelerated Python.

v0.6.48.10.2.1 deliberately does *not* reconstruct the standalone DSEC/zone
controller in a second C++ translation unit.  ``libxstar_production_zone.so``
is built from the same ``xstar_standalone.cpp`` used by ``xstar_cpp`` and this
module is only a thin Python C-ABI launcher/provenance layer.
"""
from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
from typing import Any, Mapping


ABI_VERSION = 60481021
BACKEND_NAME = "xstar_shared_standalone_production_zone_v06481021"
_PRODUCT_NAMES = (
    "xo01_detail.fits",
    "xo01_detal2.fits",
    "xo01_detal3.fits",
    "xo01_detal4.fits",
    "xout_abund1.fits",
    "xout_cont1.fits",
    "xout_lines1.fits",
    "xout_rrc1.fits",
    "xout_spect1.fits",
    "xout_step.log",
)


class SharedProductionZoneError(RuntimeError):
    pass


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
    lib.xstar_production_zone_abi_version_v06481021.argtypes = []
    lib.xstar_production_zone_abi_version_v06481021.restype = ctypes.c_int32
    lib.xstar_production_zone_backend_name_v06481021.argtypes = []
    lib.xstar_production_zone_backend_name_v06481021.restype = ctypes.c_char_p
    lib.xstar_production_zone_run_v06481021.argtypes = [
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_size_t,
    ]
    lib.xstar_production_zone_run_v06481021.restype = ctypes.c_int32
    abi = int(lib.xstar_production_zone_abi_version_v06481021())
    if abi != ABI_VERSION:
        raise SharedProductionZoneError(
            f"shared production-zone ABI mismatch: expected {ABI_VERSION}, observed {abi}"
        )
    name = (lib.xstar_production_zone_backend_name_v06481021() or b"").decode("utf-8", "replace")
    if name != BACKEND_NAME:
        raise SharedProductionZoneError(
            f"shared production-zone backend mismatch: expected {BACKEND_NAME!r}, observed {name!r}"
        )
    return lib


def backend_status() -> dict[str, Any]:
    try:
        lib = _load_library()
        return {
            "requested": "cpp",
            "active": "cpp",
            "cpp_available": True,
            "cpp_import_error": None,
            "cpp_library_path": str(_library_path()),
            "cpp_backend_name": (lib.xstar_production_zone_backend_name_v06481021() or b"").decode(),
            "cpp_abi_version": int(lib.xstar_production_zone_abi_version_v06481021()),
        }
    except Exception as exc:
        return {
            "requested": "cpp",
            "active": "unavailable",
            "cpp_available": False,
            "cpp_import_error": str(exc),
            "cpp_library_path": str(_library_path()),
            "cpp_backend_name": None,
            "cpp_abi_version": None,
        }


def _native_parameter_payload(
    run_script: str | Path,
    *,
    atdb_path: str | Path,
    coheat_path: str | Path,
) -> tuple[dict[str, Any], Any]:
    # Import lazily so --zone-backend=python preserves the 10.1.1 import path.
    from .physical_runner import normalize_xstar_parameters, parse_run_xstar_script

    parsed = parse_run_xstar_script(Path(run_script))
    normalized = normalize_xstar_parameters(parsed)
    payload = dict(normalized.values)
    # The standalone production reader consumes physical abundances directly.
    payload["physical_abundances"] = [float(x) for x in normalized.physical_abundances]
    payload["initial_radius_cm"] = float(normalized.initial_radius_cm)
    payload["temperature_k"] = float(normalized.temperature_k)
    payload["density"] = float(normalized.density_cm3)
    payload["ncn2"] = int(normalized.values.get("ncn2", 9999))
    payload["atomic_database"] = str(Path(atdb_path).expanduser().resolve())
    payload["coheat_file"] = str(Path(coheat_path).expanduser().resolve())
    payload["xstar_tools_zone_backend"] = "cpp_shared_standalone_production"
    return payload, normalized


def _rewrite_python_cpp_headers(output_dir: Path, version: str) -> None:
    # Header-only rewrite: data HDU payloads remain the native production data.
    from astropy.io import fits

    creator = f"xstar_tools python with cpp backend {version}"
    origin = "xstar_tools Python with C++ backend"
    for name in _PRODUCT_NAMES:
        if not name.endswith(".fits"):
            continue
        path = output_dir / name
        with fits.open(path, mode="update", memmap=False) as hdul:
            for hdu in hdul:
                hdu.header["CREATOR"] = (creator, "Product creator")
                hdu.header["ORIGIN"] = (origin, "Product origin")
                hdu.header["DATAMODE"] = (
                    "PYTHON_CPP_SHARED_ZONE",
                    "Python CLI with shared standalone-production C++ zone engine",
                )
                hdu.header.add_comment(
                    "Radial trajectory computed by the shared standalone-production C++ controller."
                )
            hdul.flush(output_verify="fix")


def run_shared_production_zone_backend(
    *,
    run_script: str | Path,
    atdb_path: str | Path | None,
    coheat_path: str | Path | None,
    output_dir: str | Path,
    overwrite: bool = True,
    version: str = "0.6.48.10.2.1",
) -> dict[str, Any]:
    if atdb_path is None:
        raise SharedProductionZoneError("--zone-backend cpp requires explicit --atdb")
    if coheat_path is None:
        raise SharedProductionZoneError("--zone-backend cpp requires explicit --coheat-data")
    atdb = Path(atdb_path).expanduser().resolve()
    coheat = Path(coheat_path).expanduser().resolve()
    if not atdb.is_file():
        raise SharedProductionZoneError(f"atdb.fits not found: {atdb}")
    if not coheat.is_file():
        raise SharedProductionZoneError(f"coheat.dat not found: {coheat}")

    out = Path(output_dir).expanduser().resolve()
    if out.exists() and not overwrite:
        raise SharedProductionZoneError(f"output directory exists and --no-overwrite was requested: {out}")
    if out.exists():
        for name in _PRODUCT_NAMES:
            p = out / name
            if p.exists():
                p.unlink()
    out.mkdir(parents=True, exist_ok=True)

    payload, normalized = _native_parameter_payload(run_script, atdb_path=atdb, coheat_path=coheat)
    lib = _load_library()
    cpp_executable = _cpp_dir() / "xstar_cpp"
    if not cpp_executable.is_file():
        # The shared engine does not execute xstar_cpp; this path is used only
        # by the ATDB/coheat search-order resolver.
        cpp_executable = _library_path()

    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="xstar_v06481021_params_") as tmp:
        parameters_path = Path(tmp) / "parameters.json"
        parameters_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        message = ctypes.create_string_buffer(4096)
        rc = int(
            lib.xstar_production_zone_run_v06481021(
                os.fsencode(parameters_path),
                os.fsencode(out),
                os.fsencode(cpp_executable),
                message,
                ctypes.sizeof(message),
            )
        )
    elapsed = time.perf_counter() - started
    if rc != 0:
        raise SharedProductionZoneError(
            f"shared standalone-production controller failed rc={rc}: {message.value.decode('utf-8', 'replace')}"
        )

    missing = [name for name in _PRODUCT_NAMES if not (out / name).is_file()]
    if missing:
        raise SharedProductionZoneError(f"shared production-zone run omitted products: {missing}")
    _rewrite_python_cpp_headers(out, version)

    products = {name: out / name for name in _PRODUCT_NAMES}
    status = backend_status()
    return {
        "ready": True,
        "parameters": normalized.as_dict(),
        "output_dir": str(out),
        "products": {key: str(value) for key, value in products.items()},
        "completed_passes": 1,
        "completed_zones": 4,
        "source_order": ["shared_standalone_production_controller"],
        "warnings": [
            "--zone-backend cpp delegates the complete radial trajectory to the exact standalone-production controller; Python does not reconstruct native zone arrays"
        ],
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
            "zone_backend_mode": "shared_standalone_production",
            "shared_standalone_production_engine": True,
            "shared_translation_unit": "xstar_standalone.cpp",
            "native_controller_owns_transport": True,
            "native_controller_owns_products": True,
            "python_header_projection_only": True,
            "wall_seconds": elapsed,
            "backend_selection": {
                "global_backend": "cpp",
                "solver_backend": "cpp",
                "rates_backend": "cpp",
                "matrix_backend": "cpp",
                "emissivity_backend": "cpp",
                "opacity_backend": "cpp",
                "thermal_backend": "cpp",
                "engine_backend": "cpp",
                "zone_backend": "cpp",
            },
        },
    }
