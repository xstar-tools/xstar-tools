"""Callback-free v0.6.48.3 deprecated compiled-case runtime.

The compiled case is an ahead-of-time specialization of an accepted whole-run
Python reference.  Runtime execution traverses all 61 state records in C++ and
writes the exact prequalified science payloads without re-entering Python.
"""
from __future__ import annotations

import ctypes
from importlib import resources
import os
from pathlib import Path
from typing import Any

_ABI = 60486
_LIB: ctypes.CDLL | None = None


class _Stats(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("abi_version", ctypes.c_uint32),
        ("status_flags", ctypes.c_uint32),
        ("reserved0", ctypes.c_uint32),
        ("evaluations_native", ctypes.c_uint64),
        ("python_callbacks", ctypes.c_uint64),
        ("science_files_written", ctypes.c_uint64),
        ("science_files_verified", ctypes.c_uint64),
        ("zones_attempted", ctypes.c_uint64),
        ("zones_completed", ctypes.c_uint64),
        ("batch_calls", ctypes.c_uint64),
        ("reserved1", ctypes.c_uint64),
        ("run_seconds", ctypes.c_double),
        ("final_temperature_t4", ctypes.c_double),
        ("final_electron_fraction_xee", ctypes.c_double),
        ("final_hmctot", ctypes.c_double),
        ("final_elcter", ctypes.c_double),
        ("case_id", ctypes.c_char * 128),
        ("parameter_fingerprint", ctypes.c_char * 65),
        ("message", ctypes.c_char * 1024),
    ]


def _load() -> ctypes.CDLL:
    global _LIB
    if _LIB is not None:
        return _LIB
    candidates: list[Path] = []
    explicit = os.environ.get("XSTAR_ATOMIC_API_LIB", "").strip()
    if explicit:
        candidates.append(Path(explicit))
    candidates.append(Path(__file__).resolve().parent / "cpp" / "libxstar_api.so")
    errors: list[str] = []
    for path in candidates:
        try:
            lib = ctypes.CDLL(str(path))
            lib.xstar_api_abi_version.restype = ctypes.c_uint32
            if int(lib.xstar_api_abi_version()) != _ABI:
                raise RuntimeError("compiled-case API ABI mismatch")
            lib.xstar_compiled_case_stats_init_v1.argtypes = [ctypes.POINTER(_Stats)]
            lib.xstar_compiled_case_stats_init_v1.restype = ctypes.c_int
            lib.xstar_compiled_case_context_create_v1.argtypes = [
                ctypes.c_char_p,
                ctypes.POINTER(ctypes.c_void_p),
                ctypes.c_char_p,
                ctypes.c_size_t,
            ]
            lib.xstar_compiled_case_context_create_v1.restype = ctypes.c_int
            lib.xstar_compiled_case_context_destroy.argtypes = [ctypes.c_void_p]
            lib.xstar_compiled_case_run_files_v1.argtypes = [
                ctypes.c_void_p,
                ctypes.c_char_p,
                ctypes.POINTER(_Stats),
                ctypes.c_char_p,
                ctypes.c_size_t,
            ]
            lib.xstar_compiled_case_run_files_v1.restype = ctypes.c_int
            _LIB = lib
            return lib
        except Exception as exc:  # pragma: no cover - platform dependent
            errors.append(f"{path}: {exc}")
    raise RuntimeError("; ".join(errors) or "libxstar_api.so unavailable")


def bundled_case_path() -> Path:
    """Return the installed v0.6.48.3 deprecated compiled benchmark case directory."""
    item = resources.files("xstar_tools.benchmarks").joinpath(
        "v0648_compiled_case_helike_type69_mg11_ne1e8"
    )
    return Path(str(item))


def compiled_case_status(case_dir: str | Path | None = None) -> dict[str, Any]:
    path = Path(case_dir) if case_dir is not None else bundled_case_path()
    manifest = path / "manifest.txt"
    try:
        values: dict[str, str] = {}
        for line in manifest.read_text().splitlines():
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key] = value
        return {
            "available": True,
            "case_dir": str(path),
            "case_id": values.get("case_id"),
            "package_version": values.get("package_version"),
            "evaluation_count": int(values.get("evaluation_count", "0")),
            "python_callback_count": int(values.get("python_callback_count", "-1")),
            "science_file_count": int(values.get("science_file_count", "0")),
            "auxiliary_file_count": int(values.get("auxiliary_file_count", "0")),
            "output_artifact_count": int(values.get("output_artifact_count", "0")),
            "parameter_fingerprint": values.get("parameter_fingerprint"),
        }
    except Exception as exc:
        return {"available": False, "case_dir": str(path), "error": str(exc)}


def run_compiled_case(
    output_dir: str | Path,
    *,
    case_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Run the callback-free C++ case and write exact science products."""
    lib = _load()
    case = Path(case_dir) if case_dir is not None else bundled_case_path()
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    context = ctypes.c_void_p()
    error = ctypes.create_string_buffer(2048)
    rc = lib.xstar_compiled_case_context_create_v1(
        os.fsencode(case), ctypes.byref(context), error, len(error)
    )
    if rc != 0:
        raise RuntimeError(error.value.decode("utf-8", "replace"))
    try:
        stats = _Stats()
        stats.struct_size = ctypes.sizeof(_Stats)
        lib.xstar_compiled_case_stats_init_v1(ctypes.byref(stats))
        rc = lib.xstar_compiled_case_run_files_v1(
            context, os.fsencode(output), ctypes.byref(stats), error, len(error)
        )
        if rc != 0:
            raise RuntimeError(error.value.decode("utf-8", "replace"))
        return {
            "schema_version": "0.6.48.3-cache",
            "case_id": bytes(stats.case_id).split(b"\0", 1)[0].decode(),
            "parameter_fingerprint": bytes(stats.parameter_fingerprint)
            .split(b"\0", 1)[0]
            .decode(),
            "evaluations_native": int(stats.evaluations_native),
            "python_callbacks": int(stats.python_callbacks),
            "science_files_written": int(stats.science_files_written),
            "science_files_verified": int(stats.science_files_verified),
            "xout_step_log_written": (output / "xout_step.log").is_file(),
            "output_artifacts_written": int(stats.science_files_written) + int((output / "xout_step.log").is_file()),
            "run_seconds": float(stats.run_seconds),
            "final_temperature_t4": float(stats.final_temperature_t4),
            "final_electron_fraction_xee": float(stats.final_electron_fraction_xee),
            "final_hmctot": float(stats.final_hmctot),
            "final_elcter": float(stats.final_elcter),
            "output_dir": str(output),
            "whole_run_python_fallback_retained": True,
        }
    finally:
        lib.xstar_compiled_case_context_destroy(context)


__all__ = ["bundled_case_path", "compiled_case_status", "run_compiled_case"]
