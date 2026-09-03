# XSTAR-PYTHON-SOURCE-CORRESPONDENCE-BEGIN
# Source correspondence:
#   Fortran: ucalc.f90 / calc_hmc_ion.f90; no direct Fortran backend-dispatch analogue
#   Role: Optional Python/native bridge for compact record classification and low-level native backend counters.
#   Relation: Backend/observability layer; scientific ownership remains in mapped source-equivalent kernels.
#   Concordance: BACKEND-001; MATRIX-001
#   Qualification: accepted science revision 0.6.48.12.3.45.3.3.8; frozen C++ baseline 0.6.48.12.3.44.
# Atomic-data note (XSTAR Manual Ch. 12; Mendoza et al. 2021, Appendix A):
#   Rule: data type selects the record formula/interpretation; rate type selects downstream use.
#   Native counters and payloads distinguish unsupported data type from unsupported rate type because those
#   fields mean formula selection versus downstream rate ownership.
# XSTAR-PYTHON-SOURCE-CORRESPONDENCE-END

"""Load optional flat-layout C++ backend libraries.

C++ sources and shared objects live directly in ``src/xstar_tools/xstar/cpp``.
This module exposes optional low-level backend status and retained generic
rate-payload verification helpers.  Obsolete Mg-only accumulator diagnostics
were retired after the production engine became element-general.
"""
from __future__ import annotations

import ctypes
from dataclasses import dataclass, asdict
import os
from pathlib import Path
from typing import Any

import numpy as np

from xstar_tools.native_runtime import native_library_candidates, prepare_native_library_search


@dataclass(frozen=True)
class ExtraBackendStatus:
    requested: str
    active: str
    cpp_available: bool
    cpp_import_error: str | None = None
    cpp_library_path: str | None = None
    cpp_backend_name: str | None = None
    cpp_abi_version: int | None = None
    cpp_feature_flags: int | None = None

    # XSTAR-FUNCTION-COMMENT-BEGIN
    # Purpose: Serialize the current state into a plain mapping for diagnostics, provenance, or machine-readable output.
    # Reference context: Backend adapter/provenance helper; the underlying scientific routine is documented in the corresponding XSTAR Manual section.
    # XSTAR-FUNCTION-COMMENT-END
    def as_dict(self) -> dict[str, object]:
        return dict(asdict(self))



_LIBS: dict[str, ctypes.CDLL | None] = {}
_ERRORS: dict[str, BaseException | None] = {}
_PATHS: dict[str, str | None] = {}

_LIBRARY_INFO = {
    "opacity": {
        "env": "XSTAR_ATOMIC_OPACITY_LIB",
        "backend_env": "XSTAR_ATOMIC_OPACITY_BACKEND",
        "stem": "xstar_opacity",
        "prefix": "xstar_opacity",
    },
    "thermal": {
        "env": "XSTAR_ATOMIC_THERMAL_LIB",
        "backend_env": "XSTAR_ATOMIC_THERMAL_BACKEND",
        "stem": "xstar_thermal",
        "prefix": "xstar_thermal",
    },
    "engine": {
        "env": "XSTAR_ATOMIC_ENGINE_LIB",
        "backend_env": "XSTAR_ATOMIC_ENGINE_BACKEND",
        "stem": "xstar_engine",
        "prefix": "xstar_engine",
    },
}


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the candidate library paths operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: Backend adapter/provenance helper; the underlying scientific routine is documented in the corresponding XSTAR Manual section.
# XSTAR-FUNCTION-COMMENT-END
def _candidate_library_paths(kind: str) -> list[Path]:
    info = _LIBRARY_INFO[kind]
    return native_library_candidates(
        str(info["stem"]),
        env_var=str(info["env"]),
        compatibility_names=(f"xstar_{kind}.so", f"xstar_{kind}.dll"),
    )

# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Load library for this module while preserving the surrounding source/runtime invariants.
# Reference context: Backend adapter/provenance helper; the underlying scientific routine is documented in the corresponding XSTAR Manual section.
# XSTAR-FUNCTION-COMMENT-END
def _load_library(kind: str) -> ctypes.CDLL | None:
    if kind in _LIBS:
        return _LIBS[kind]
    info = _LIBRARY_INFO[kind]
    prefix = str(info["prefix"])
    attempted: list[str] = []
    try:
        for path in _candidate_library_paths(kind):
            attempted.append(str(path))
            if not path.exists():
                continue
            prepare_native_library_search(path)
            lib = ctypes.CDLL(str(path))
            getattr(lib, f"{prefix}_abi_version").argtypes = []
            getattr(lib, f"{prefix}_abi_version").restype = ctypes.c_int
            getattr(lib, f"{prefix}_backend_name").argtypes = []
            getattr(lib, f"{prefix}_backend_name").restype = ctypes.c_char_p
            getattr(lib, f"{prefix}_feature_flags").argtypes = []
            getattr(lib, f"{prefix}_feature_flags").restype = ctypes.c_int
            if kind == "opacity":
                lib.xstar_opacity_probe.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_size_t]
                lib.xstar_opacity_probe.restype = ctypes.c_int
            elif kind == "thermal":
                lib.xstar_thermal_probe.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_size_t]
                lib.xstar_thermal_probe.restype = ctypes.c_int
            elif kind == "engine":
                lib.xstar_engine_probe.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_size_t]
                lib.xstar_engine_probe.restype = ctypes.c_int
                i64p = np.ctypeslib.ndpointer(dtype=np.int64, ndim=1, flags="C_CONTIGUOUS")
                try:
                    f64p = np.ctypeslib.ndpointer(dtype=np.float64, ndim=1, flags="C_CONTIGUOUS")
                    lib.xstar_engine_eval_rate_payload_shadow_v1.argtypes = [
                        ctypes.c_int, i64p, ctypes.c_int, f64p, ctypes.c_int,
                        ctypes.c_int, i64p, ctypes.c_int, f64p, ctypes.c_int,
                        f64p, ctypes.c_int, i64p, ctypes.c_int, ctypes.c_char_p, ctypes.c_size_t,
                    ]
                    lib.xstar_engine_eval_rate_payload_shadow_v1.restype = ctypes.c_int
                except AttributeError:
                    pass
                try:
                    f64p = np.ctypeslib.ndpointer(dtype=np.float64, ndim=1, flags="C_CONTIGUOUS")
                    lib.xstar_engine_eval_rate_payload_native_scalars_v1.argtypes = [
                        ctypes.c_int, i64p, ctypes.c_int, f64p, ctypes.c_int,
                        f64p, ctypes.c_int, f64p, f64p, ctypes.c_int,
                        f64p, ctypes.c_int, f64p, ctypes.c_int, i64p, ctypes.c_int,
                        ctypes.c_char_p, ctypes.c_size_t,
                    ]
                    lib.xstar_engine_eval_rate_payload_native_scalars_v1.restype = ctypes.c_int
                except AttributeError:
                    pass
            _LIBS[kind] = lib
            _PATHS[kind] = str(path)
            _ERRORS[kind] = None
            return lib
        raise FileNotFoundError(f"could not find {kind} C++ library; attempted " + ", ".join(attempted))
    except BaseException as exc:
        _LIBS[kind] = None
        _ERRORS[kind] = exc
        _PATHS[kind] = None
        return None


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the cpp import error operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: Backend adapter/provenance helper; the underlying scientific routine is documented in the corresponding XSTAR Manual section.
# XSTAR-FUNCTION-COMMENT-END
def cpp_import_error(kind: str) -> str | None:
    err = _ERRORS.get(kind)
    return None if err is None else repr(err)


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the backend status operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: Backend adapter/provenance helper; the underlying scientific routine is documented in the corresponding XSTAR Manual section.
# XSTAR-FUNCTION-COMMENT-END
def backend_status(kind: str, requested: str | None = None) -> ExtraBackendStatus:
    info = _LIBRARY_INFO[kind]
    req = (requested or os.environ.get(str(info["backend_env"])) or os.environ.get("XSTAR_ATOMIC_BACKEND") or "python").strip().lower()
    if req not in {"python", "cpp", "auto"}:
        req = "python"
    lib = _load_library(kind)
    if req == "python":
        active = "python"
    elif req == "cpp":
        active = "cpp" if lib is not None else "unavailable"
    else:
        active = "cpp" if lib is not None else "python"
    name: str | None = None
    abi: int | None = None
    flags: int | None = None
    if lib is not None:
        prefix = str(info["prefix"])
        try:
            raw = getattr(lib, f"{prefix}_backend_name")()
            name = raw.decode("utf-8", "replace") if raw else None
            abi = int(getattr(lib, f"{prefix}_abi_version")())
            flags = int(getattr(lib, f"{prefix}_feature_flags")())
        except Exception as exc:
            if req == "cpp":
                active = "unavailable"
            name = None
            abi = None
            flags = None
            _ERRORS[kind] = exc
    return ExtraBackendStatus(
        requested=req,
        active=active,
        cpp_available=lib is not None,
        cpp_import_error=cpp_import_error(kind),
        cpp_library_path=_PATHS.get(kind),
        cpp_backend_name=name,
        cpp_abi_version=abi,
        cpp_feature_flags=flags,
    )


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the opacity backend status operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: Backend adapter/provenance helper; the underlying scientific routine is documented in the corresponding XSTAR Manual section.
# XSTAR-FUNCTION-COMMENT-END
def opacity_backend_status(requested: str | None = None) -> ExtraBackendStatus:
    return backend_status("opacity", requested)


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the thermal backend status operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: Backend adapter/provenance helper; the underlying scientific routine is documented in the corresponding XSTAR Manual section.
# XSTAR-FUNCTION-COMMENT-END
def thermal_backend_status(requested: str | None = None) -> ExtraBackendStatus:
    return backend_status("thermal", requested)


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the engine backend status operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: Backend adapter/provenance helper; the underlying scientific routine is documented in the corresponding XSTAR Manual section.
# XSTAR-FUNCTION-COMMENT-END
def engine_backend_status(requested: str | None = None) -> ExtraBackendStatus:
    return backend_status("engine", requested)










_RATE_PAYLOAD_SHADOW_ROLE = {1: "forward_offdiag", 2: "reverse_offdiag", 3: "forward_diag_loss", 4: "reverse_diag_loss"}

# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the eval mg rate payload batched orchestration shadow cpp operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: Backend adapter/provenance helper; the underlying scientific routine is documented in the corresponding XSTAR Manual section.
# XSTAR-FUNCTION-COMMENT-END
def eval_rate_payload_batched_orchestration_shadow_cpp(
    records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str, dict[str, float]]:
    """Reconstruct supported Mg matrix rows in one diagnostic C++ call.

    The accepted path supplies exact scalar ans1..ans6 channels and endpoint
    metadata.  C++ validates the compact packet and performs the matrix-term
    orchestration.  Returned rows are shadow-only and never enter live matrices.
    """
    lib = _load_library("engine")
    if lib is None or not hasattr(lib, "xstar_engine_eval_rate_payload_shadow_v1"):
        raise RuntimeError("C++ rate-payload batched orchestration shadow is unavailable" + (f": {cpp_import_error('engine')}" if cpp_import_error('engine') else ""))
    _time = __import__('time')
    packing_t0 = _time.perf_counter()
    n = len(records)
    meta = np.zeros((n, 12), dtype=np.int64)
    rates = np.zeros((n, 7), dtype=np.float64)
    for k, row in enumerate(records):
        meta[k] = [
            int(row["record"]), int(row["rate_type"]), int(row["data_type"]),
            int(row["ion_index"]), int(row["ion_stage"]), int(row["compact_start"]),
            int(row["basis_n_rows"]), int(row["idest1"]), int(row["idest2"]),
            int(row["lower_endpoint"]), int(row["upper_endpoint"]), int(row["term_start"]),
        ]
        rates[k] = [float(row.get(f"ans{i}", 0.0)) for i in range(1, 7)] + [float(row["hydrogen_density_cm3"])]
    meta_flat = np.ascontiguousarray(meta.reshape(-1))
    rates_flat = np.ascontiguousarray(rates.reshape(-1))
    max_terms = max(4, n * 4)
    out_i64 = np.zeros(max_terms * 16, dtype=np.int64)
    out_f64 = np.zeros(max_terms * 4, dtype=np.float64)
    stats_i64 = np.zeros(16, dtype=np.int64)
    timing_f64 = np.zeros(3, dtype=np.float64)
    buf = ctypes.create_string_buffer(512)
    packing_seconds = _time.perf_counter() - packing_t0
    t0 = _time.perf_counter()
    rc = lib.xstar_engine_eval_rate_payload_shadow_v1(
        n, meta_flat, 12, rates_flat, 7, max_terms,
        out_i64, 16, out_f64, 4, timing_f64, int(timing_f64.size), stats_i64, int(stats_i64.size),
        buf, ctypes.sizeof(buf),
    )
    elapsed = _time.perf_counter() - t0
    message = buf.value.decode("utf-8", errors="replace")
    if rc != 0:
        raise RuntimeError(message or f"xstar_engine_eval_rate_payload_shadow_v1 failed with code {rc}")
    emitted = int(stats_i64[2])
    oi = out_i64[: emitted * 16].reshape((emitted, 16)) if emitted else np.zeros((0,16),dtype=np.int64)
    of = out_f64[: emitted * 4].reshape((emitted, 4)) if emitted else np.zeros((0,4),dtype=np.float64)
    decode_t0 = _time.perf_counter()
    rows: list[dict[str, Any]] = []
    for j in range(emitted):
        rows.append({
            "term_index": int(oi[j,0]), "record": int(oi[j,1]), "data_type": int(oi[j,2]), "rate_type": int(oi[j,3]),
            "ion_index": int(oi[j,4]), "ion_stage": int(oi[j,5]), "role": _RATE_PAYLOAD_SHADOW_ROLE.get(int(oi[j,6]), f"role_{int(oi[j,6])}"),
            "row": int(oi[j,7]), "column": int(oi[j,8]), "idest1": int(oi[j,9]), "idest2": int(oi[j,10]),
            "lower_endpoint": int(oi[j,11]), "upper_endpoint": int(oi[j,12]),
            "source_row_unclamped": int(oi[j,13]), "source_column_unclamped": int(oi[j,14]), "source_ipmat_clamped": bool(int(oi[j,15])),
            "ucalc_status": "evaluated", "aj1": float(of[j,0]), "aj2": float(of[j,1]), "cj": float(of[j,2]), "cj2": float(of[j,3]),
        })
    output_decoding_seconds = _time.perf_counter() - decode_t0
    names=("records_seen","records_supported","terms_emitted","records_emitted","unsupported_records","invalid_records","output_overflow","valid","family_4_50","family_3_51","family_3_63","family_42_88")
    stats={name: float(stats_i64[i]) for i,name in enumerate(names)}
    stats.update({
        "cpp_calls": 1.0 if n else 0.0, "cpp_wall_seconds": float(elapsed),
        "cpp_rate_evaluation_seconds": float(timing_f64[0]),
        "cpp_matrix_term_construction_seconds": float(timing_f64[1]),
        "cpp_internal_total_seconds": float(timing_f64[2]),
        "packing_seconds": float(packing_seconds),
        "python_to_cpp_call_seconds": max(0.0, float(elapsed) - float(timing_f64[2])),
        "output_decoding_seconds": float(output_decoding_seconds),
        "input_bytes": float(meta_flat.nbytes + rates_flat.nbytes),
        "output_bytes": float(emitted * (16*8 + 4*8)),
        "allocation_count": 5.0,
    })
    return rows, message, stats



# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the eval mg rate payload native scalar shadow cpp operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: Backend adapter/provenance helper; the underlying scientific routine is documented in the corresponding XSTAR Manual section.
# XSTAR-FUNCTION-COMMENT-END
def eval_rate_payload_native_scalar_shadow_cpp(
    records: list[dict[str, Any]],
    *,
    epi_eV: Any,
    bremsa: Any,
) -> tuple[list[dict[str, Any]], str, dict[str, float]]:
    """Evaluate native C++ scalar channels for Mg 4:50, 3:63, and 42:88 records.

    The call is diagnostic only.  For 3:63 C++ receives quantum numbers,
    endpoint level context, temperature, and electron density.  For 42:88 it
    receives raw alternating energy/cross-section pairs and one shared live
    radiation grid.  No returned scalar can enter a live matrix in v0.6.33. Type-88 callers must supply the full high-resolution radiation grid.
    """
    lib = _load_library("engine")
    symbol = "xstar_engine_eval_rate_payload_native_scalars_v1"
    if lib is None or not hasattr(lib, symbol):
        raise RuntimeError("C++ native scalar shadow is unavailable" + (f": {cpp_import_error('engine')}" if cpp_import_error('engine') else ""))
    _time = __import__("time")
    packing_t0 = _time.perf_counter()
    n = len(records)
    meta = np.zeros((n, 14), dtype=np.int64)
    context = np.zeros((n, 27), dtype=np.float64)
    payload: list[float] = []
    for k, row in enumerate(records):
        raw = [float(v) for v in row.get("raw_payload_f64", ())]
        offset = len(payload)
        payload.extend(raw)
        meta[k] = [
            int(row["record"]), int(row["rate_type"]), int(row["data_type"]),
            int(row.get("ion_index", 0)), int(row.get("ion_stage", 0)),
            int(row.get("idest1", 0)), int(row.get("idest2", 0)),
            int(row.get("ni", 0)), int(row.get("li", 0)),
            int(row.get("nf", 0)), int(row.get("lf", 0)), int(row.get("iq", 0)),
            int(offset), int(len(raw)),
        ]
        context[k] = [
            *[float(row.get(f"accepted_ans{i}", 0.0)) for i in range(1, 7)],
            float(row.get("temperature_k", 0.0)),
            float(row.get("electron_density_cm3", 0.0)),
            float(row.get("initial_energy_eV", 0.0)),
            float(row.get("final_energy_eV", 0.0)),
            float(row.get("initial_g", 0.0)),
            float(row.get("final_g", 0.0)),
            float(row.get("threshold_eV", 0.0)),
            float(row.get("type88_phextrap_grid_points", 0.0)),
            float(row.get("type50_wavelength_A", 0.0)),
            float(row.get("type50_aij_s_inv", 0.0)),
            float(row.get("type50_upper_g", 0.0)),
            float(row.get("type50_lower_g", 0.0)),
            float(row.get("type50_ptmp1", 0.0)),
            float(row.get("type50_ptmp2", 0.0)),
            float(row.get("type50_cfrac", 1.0)),
            float(row.get("type50_bremsa_nb1", 0.0)),
            float(row.get("type50_hydrogen_density_cm3", 0.0)),
            float(row.get("type50_endpoint_energy_eV", 0.0)),
            float(row.get("temperature_k", 0.0)),
            float(row.get("turbulent_velocity_km_s", 0.0)),
            float(row.get("type50_atomic_mass_amu", 0.0)),
        ]
    meta_flat = np.ascontiguousarray(meta.reshape(-1))
    context_flat = np.ascontiguousarray(context.reshape(-1))
    payload_flat = np.ascontiguousarray(np.asarray(payload, dtype=np.float64).reshape(-1))
    epi = np.ascontiguousarray(np.asarray(epi_eV, dtype=np.float64).reshape(-1))
    brem = np.ascontiguousarray(np.asarray(bremsa, dtype=np.float64).reshape(-1))
    if epi.size < 3 or brem.size < epi.size:
        raise ValueError("native scalar shadow requires a valid live radiation grid")
    brem = np.ascontiguousarray(brem[: epi.size])
    out = np.zeros(max(1, n * 7), dtype=np.float64)
    timing = np.zeros(3, dtype=np.float64)
    stats_i64 = np.zeros(16, dtype=np.int64)
    buf = ctypes.create_string_buffer(512)
    packing_seconds = _time.perf_counter() - packing_t0
    t0 = _time.perf_counter()
    rc = lib.xstar_engine_eval_rate_payload_native_scalars_v1(
        n, meta_flat, 14, context_flat, 27,
        payload_flat, int(payload_flat.size), epi, brem, int(epi.size),
        out, 7, timing, int(timing.size), stats_i64, int(stats_i64.size),
        buf, ctypes.sizeof(buf),
    )
    elapsed = _time.perf_counter() - t0
    message = buf.value.decode("utf-8", errors="replace")
    if rc != 0:
        raise RuntimeError(message or f"{symbol} failed with code {rc}")
    values = out[: n * 7].reshape((n, 7)) if n else np.zeros((0, 7), dtype=np.float64)
    decode_t0 = _time.perf_counter()
    rows: list[dict[str, Any]] = []
    for k, source in enumerate(records):
        rows.append({
            "record": int(source["record"]),
            "rate_type": int(source["rate_type"]),
            "data_type": int(source["data_type"]),
            "ion_index": int(source.get("ion_index", 0)),
            "ion_stage": int(source.get("ion_stage", 0)),
            **{f"ans{i}": float(values[k, i - 1]) for i in range(1, 7)},
            "opakab": float(values[k, 6]),
        })
    decode_seconds = _time.perf_counter() - decode_t0
    names = (
        "records_seen", "records_evaluated", "scalar_fields_emitted", "reserved3",
        "unsupported_records", "invalid_records", "reserved6", "valid",
        "family_3_63", "family_42_88", "family_4_50",
    )
    stats = {name: float(stats_i64[i]) for i, name in enumerate(names)}
    stats.update({
        "cpp_calls": 1.0 if n else 0.0,
        "cpp_wall_seconds": float(elapsed),
        "cpp_native_scalar_seconds": float(timing[0]),
        "cpp_internal_total_seconds": float(timing[2]),
        "packing_seconds": float(packing_seconds),
        "python_to_cpp_call_seconds": max(0.0, float(elapsed) - float(timing[2])),
        "output_decoding_seconds": float(decode_seconds),
        "input_bytes": float(meta_flat.nbytes + context_flat.nbytes + payload_flat.nbytes + epi.nbytes + brem.nbytes),
        "output_bytes": float(n * 7 * 8),
        "payload_values": float(payload_flat.size),
        "radiation_grid_points": float(epi.size),
        "allocation_count": 7.0,
    })
    return rows, message, stats
