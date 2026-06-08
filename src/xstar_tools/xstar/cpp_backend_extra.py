"""Load optional flat-layout C++ backend libraries.

v0.6.3 keeps every C++ source and shared object directly in
``src/xstar_tools/xstar/cpp``.  The engine library now exposes a coarse
Mg-ion accumulator ABI that can traverse/classify compact per-ion record
packets and report fallback counters.  Product-active matrix/rate row
generation remains disabled until a later parity-gated release.
"""
from __future__ import annotations

import ctypes
from dataclasses import dataclass, asdict
import os
from pathlib import Path
from typing import Any

import numpy as np


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

    def as_dict(self) -> dict[str, object]:
        return dict(asdict(self))


_COUNTER_NAMES = (
    "records_seen",
    "cpp_supported",
    "python_fallback",
    "matrix_terms_emitted",
    "rate_terms_emitted",
    "heat_terms_emitted",
    "cool_terms_emitted",
    "rate_type7_records",
    "type49_records",
    "type53_records",
    "type50_records",
    "type51_records",
    "type49_supported",
    "type53_supported",
    "type50_topology_supported",
    "type51_topology_supported",
    "unsupported_rate_type_records",
    "unsupported_data_type_records",
    "source_order_records",
    "product_active",
)


@dataclass(frozen=True)
class MgIonAccumulatorProbe:
    enabled: bool
    library_available: bool
    records_seen: int
    cpp_supported: int
    python_fallback: int
    matrix_terms_emitted: int
    rate_terms_emitted: int
    heat_terms_emitted: int
    cool_terms_emitted: int
    message: str
    error: str | None = None
    rate_type7_records: int = 0
    type49_records: int = 0
    type53_records: int = 0
    type50_records: int = 0
    type51_records: int = 0
    type49_supported: int = 0
    type53_supported: int = 0
    type50_topology_supported: int = 0
    type51_topology_supported: int = 0
    unsupported_rate_type_records: int = 0
    unsupported_data_type_records: int = 0
    source_order_records: int = 0
    product_active: int = 0

    def as_dict(self) -> dict[str, object]:
        return dict(asdict(self))


_LIBS: dict[str, ctypes.CDLL | None] = {}
_ERRORS: dict[str, BaseException | None] = {}
_PATHS: dict[str, str | None] = {}

_LIBRARY_INFO = {
    "opacity": {
        "env": "XSTAR_ATOMIC_OPACITY_LIB",
        "backend_env": "XSTAR_ATOMIC_OPACITY_BACKEND",
        "names": ("libxstar_opacity.so", "xstar_opacity.so", "libxstar_opacity.dylib", "xstar_opacity.dll"),
        "prefix": "xstar_opacity",
    },
    "thermal": {
        "env": "XSTAR_ATOMIC_THERMAL_LIB",
        "backend_env": "XSTAR_ATOMIC_THERMAL_BACKEND",
        "names": ("libxstar_thermal.so", "xstar_thermal.so", "libxstar_thermal.dylib", "xstar_thermal.dll"),
        "prefix": "xstar_thermal",
    },
    "engine": {
        "env": "XSTAR_ATOMIC_ENGINE_LIB",
        "backend_env": "XSTAR_ATOMIC_ENGINE_BACKEND",
        "names": ("libxstar_engine.so", "xstar_engine.so", "libxstar_engine.dylib", "xstar_engine.dll"),
        "prefix": "xstar_engine",
    },
}


def _candidate_library_paths(kind: str) -> list[Path]:
    info = _LIBRARY_INFO[kind]
    paths: list[Path] = []
    env_path = os.environ.get(str(info["env"]))
    if env_path:
        paths.append(Path(env_path).expanduser())
    here = Path(__file__).resolve().parent
    for name in info["names"]:
        paths.append(here / "cpp" / str(name))
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        key = str(path)
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


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
                    lib.xstar_matrix_eval_mg_ion_accumulator_v1.argtypes = [
                        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                        i64p, i64p, i64p, i64p,
                        i64p, ctypes.c_int,
                        ctypes.c_char_p, ctypes.c_size_t,
                    ]
                    lib.xstar_matrix_eval_mg_ion_accumulator_v1.restype = ctypes.c_int
                except AttributeError:
                    pass
                lib.xstar_engine_eval_mg_ion_accumulator_v1.argtypes = [
                    ctypes.c_int, ctypes.c_int, ctypes.c_int,
                    i64p, i64p, i64p, ctypes.c_int,
                    ctypes.c_char_p, ctypes.c_size_t,
                ]
                lib.xstar_engine_eval_mg_ion_accumulator_v1.restype = ctypes.c_int
                try:
                    f64p = np.ctypeslib.ndpointer(dtype=np.float64, ndim=1, flags="C_CONTIGUOUS")
                    lib.xstar_engine_eval_mg_rate_payload_shadow_v1.argtypes = [
                        ctypes.c_int, i64p, ctypes.c_int, f64p, ctypes.c_int,
                        ctypes.c_int, i64p, ctypes.c_int, f64p, ctypes.c_int,
                        f64p, ctypes.c_int, i64p, ctypes.c_int, ctypes.c_char_p, ctypes.c_size_t,
                    ]
                    lib.xstar_engine_eval_mg_rate_payload_shadow_v1.restype = ctypes.c_int
                except AttributeError:
                    pass
                try:
                    f64p = np.ctypeslib.ndpointer(dtype=np.float64, ndim=1, flags="C_CONTIGUOUS")
                    lib.xstar_engine_eval_mg_rate_payload_native_scalars_v1.argtypes = [
                        ctypes.c_int, i64p, ctypes.c_int, f64p, ctypes.c_int,
                        f64p, ctypes.c_int, f64p, f64p, ctypes.c_int,
                        f64p, ctypes.c_int, f64p, ctypes.c_int, i64p, ctypes.c_int,
                        ctypes.c_char_p, ctypes.c_size_t,
                    ]
                    lib.xstar_engine_eval_mg_rate_payload_native_scalars_v1.restype = ctypes.c_int
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


def cpp_import_error(kind: str) -> str | None:
    err = _ERRORS.get(kind)
    return None if err is None else repr(err)


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


def opacity_backend_status(requested: str | None = None) -> ExtraBackendStatus:
    return backend_status("opacity", requested)


def thermal_backend_status(requested: str | None = None) -> ExtraBackendStatus:
    return backend_status("thermal", requested)


def engine_backend_status(requested: str | None = None) -> ExtraBackendStatus:
    return backend_status("engine", requested)


def _enabled_from_env(name: str, default: str = "0") -> bool:
    return str(os.environ.get(name, default)).strip().lower() in {"1", "true", "yes", "on"}


def _make_probe(enabled: bool, lib_available: bool, counters: np.ndarray | None, message: str, error: str | None = None) -> MgIonAccumulatorProbe:
    vals = {name: 0 for name in _COUNTER_NAMES}
    if counters is not None:
        for i, name in enumerate(_COUNTER_NAMES):
            if i < int(counters.shape[0]):
                vals[name] = int(counters[i])
    return MgIonAccumulatorProbe(
        enabled=enabled,
        library_available=lib_available,
        message=message,
        error=error,
        **vals,
    )


def eval_mg_ion_accumulator_cpp(
    *,
    element_z: int = 12,
    ion_index: int = 0,
    ion_stage: int = 0,
    n_levels: int = 0,
    n_parent_levels: int = 0,
    record_number: np.ndarray | None = None,
    record_rate_type: np.ndarray | None = None,
    record_data_type: np.ndarray | None = None,
    record_source_index: np.ndarray | None = None,
    enabled: bool | None = None,
) -> MgIonAccumulatorProbe:
    """Call the v0.6.3 coarse Mg-ion accumulator ABI.

    This is a coarse per-ion packet call: C++ receives source-order record
    arrays, traverses/classifies supported groups, and returns fallback
    counters.  Product-active matrix/rate emission remains disabled.
    """
    enabled_value = bool(enabled) if enabled is not None else _enabled_from_env("XSTAR_ATOMIC_ENGINE_MG_ION_ACCUMULATOR_CPP", "0")
    lib = _load_library("engine")
    if not enabled_value:
        return _make_probe(False, lib is not None, None, "Mg-ion accumulator disabled by default")
    if lib is None:
        return _make_probe(True, False, None, "engine library unavailable", cpp_import_error("engine"))

    rn = np.ascontiguousarray(np.asarray(record_number if record_number is not None else np.zeros(0, dtype=np.int64), dtype=np.int64))
    rt = np.ascontiguousarray(np.asarray(record_rate_type if record_rate_type is not None else np.zeros(rn.shape[0], dtype=np.int64), dtype=np.int64))
    dt = np.ascontiguousarray(np.asarray(record_data_type if record_data_type is not None else np.zeros(rn.shape[0], dtype=np.int64), dtype=np.int64))
    si = np.ascontiguousarray(np.asarray(record_source_index if record_source_index is not None else rn, dtype=np.int64))
    if not (rn.shape[0] == rt.shape[0] == dt.shape[0] == si.shape[0]):
        raise ValueError("record_number, record_rate_type, record_data_type, and record_source_index must have the same length")
    counters = np.zeros(len(_COUNTER_NAMES), dtype=np.int64)
    buf = ctypes.create_string_buffer(768)
    try:
        fn = lib.xstar_matrix_eval_mg_ion_accumulator_v1
        rc = fn(
            int(element_z), int(ion_index), int(ion_stage), int(n_levels), int(n_parent_levels), int(rn.shape[0]),
            rn, rt, dt, si,
            counters, int(counters.shape[0]), buf, ctypes.sizeof(buf),
        )
    except AttributeError:
        rc = lib.xstar_engine_eval_mg_ion_accumulator_v1(
            int(element_z), int(ion_index), int(rn.shape[0]), rt, dt, counters, int(counters.shape[0]), buf, ctypes.sizeof(buf)
        )
    msg = buf.value.decode("utf-8", "replace")
    if rc != 0:
        return _make_probe(True, True, counters, msg or f"accumulator returned {rc}", f"return_code={rc}")
    return _make_probe(True, True, counters, msg)


def probe_mg_ion_accumulator_skeleton(
    *,
    element_z: int = 12,
    ion_index: int = 0,
    record_rate_type: np.ndarray | None = None,
    record_data_type: np.ndarray | None = None,
    enabled: bool | None = None,
) -> MgIonAccumulatorProbe:
    """Backward-compatible probe wrapper for older checkers."""
    n = 0 if record_rate_type is None else int(np.asarray(record_rate_type).shape[0])
    record_number = np.arange(1, n + 1, dtype=np.int64)
    return eval_mg_ion_accumulator_cpp(
        element_z=element_z,
        ion_index=ion_index,
        record_number=record_number,
        record_rate_type=record_rate_type,
        record_data_type=record_data_type,
        enabled=enabled,
    )


_RATE_PAYLOAD_SHADOW_ROLE = {1: "forward_offdiag", 2: "reverse_offdiag", 3: "forward_diag_loss", 4: "reverse_diag_loss"}

def eval_mg_rate_payload_batched_orchestration_shadow_cpp(
    records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str, dict[str, float]]:
    """Reconstruct supported Mg matrix rows in one diagnostic C++ call.

    The accepted path supplies exact scalar ans1..ans6 channels and endpoint
    metadata.  C++ validates the compact packet and performs the matrix-term
    orchestration.  Returned rows are shadow-only and never enter live matrices.
    """
    lib = _load_library("engine")
    if lib is None or not hasattr(lib, "xstar_engine_eval_mg_rate_payload_shadow_v1"):
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
    rc = lib.xstar_engine_eval_mg_rate_payload_shadow_v1(
        n, meta_flat, 12, rates_flat, 7, max_terms,
        out_i64, 16, out_f64, 4, timing_f64, int(timing_f64.size), stats_i64, int(stats_i64.size),
        buf, ctypes.sizeof(buf),
    )
    elapsed = _time.perf_counter() - t0
    message = buf.value.decode("utf-8", errors="replace")
    if rc != 0:
        raise RuntimeError(message or f"xstar_engine_eval_mg_rate_payload_shadow_v1 failed with code {rc}")
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



def eval_mg_rate_payload_native_scalar_shadow_cpp(
    records: list[dict[str, Any]],
    *,
    epi_eV: Any,
    bremsa: Any,
) -> tuple[list[dict[str, Any]], str, dict[str, float]]:
    """Evaluate native C++ scalar channels for Mg 3:63 and 42:88 records.

    The call is diagnostic only.  For 3:63 C++ receives quantum numbers,
    endpoint level context, temperature, and electron density.  For 42:88 it
    receives raw alternating energy/cross-section pairs and one shared live
    radiation grid.  No returned scalar can enter a live matrix in v0.6.33. Type-88 callers must supply the full high-resolution radiation grid.
    """
    lib = _load_library("engine")
    symbol = "xstar_engine_eval_mg_rate_payload_native_scalars_v1"
    if lib is None or not hasattr(lib, symbol):
        raise RuntimeError("C++ native scalar shadow is unavailable" + (f": {cpp_import_error('engine')}" if cpp_import_error('engine') else ""))
    _time = __import__("time")
    packing_t0 = _time.perf_counter()
    n = len(records)
    meta = np.zeros((n, 14), dtype=np.int64)
    context = np.zeros((n, 14), dtype=np.float64)
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
        ]
    meta_flat = np.ascontiguousarray(meta.reshape(-1))
    context_flat = np.ascontiguousarray(context.reshape(-1))
    payload_flat = np.ascontiguousarray(np.asarray(payload, dtype=np.float64).reshape(-1))
    epi = np.ascontiguousarray(np.asarray(epi_eV, dtype=np.float64).reshape(-1))
    brem = np.ascontiguousarray(np.asarray(bremsa, dtype=np.float64).reshape(-1))
    if epi.size < 3 or brem.size < epi.size:
        raise ValueError("native scalar shadow requires a valid live radiation grid")
    brem = np.ascontiguousarray(brem[: epi.size])
    out = np.zeros(max(1, n * 6), dtype=np.float64)
    timing = np.zeros(3, dtype=np.float64)
    stats_i64 = np.zeros(16, dtype=np.int64)
    buf = ctypes.create_string_buffer(512)
    packing_seconds = _time.perf_counter() - packing_t0
    t0 = _time.perf_counter()
    rc = lib.xstar_engine_eval_mg_rate_payload_native_scalars_v1(
        n, meta_flat, 14, context_flat, 14,
        payload_flat, int(payload_flat.size), epi, brem, int(epi.size),
        out, 6, timing, int(timing.size), stats_i64, int(stats_i64.size),
        buf, ctypes.sizeof(buf),
    )
    elapsed = _time.perf_counter() - t0
    message = buf.value.decode("utf-8", errors="replace")
    if rc != 0:
        raise RuntimeError(message or f"{symbol} failed with code {rc}")
    values = out[: n * 6].reshape((n, 6)) if n else np.zeros((0, 6), dtype=np.float64)
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
        })
    decode_seconds = _time.perf_counter() - decode_t0
    names = (
        "records_seen", "records_evaluated", "scalar_fields_emitted", "reserved3",
        "unsupported_records", "invalid_records", "reserved6", "valid",
        "family_3_63", "family_42_88",
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
        "output_bytes": float(n * 6 * 8),
        "payload_values": float(payload_flat.size),
        "radiation_grid_points": float(epi.size),
        "allocation_count": 7.0,
    })
    return rows, message, stats
