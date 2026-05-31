"""Optional C++ matrix backend loader.

v0.5.67 starts ``libxstar_matrix.so`` as the dedicated shared library for
thermal-balance/statistical-equilibrium matrix work.  The first real kernel
owns Mg record_type=7 matrix-term construction after Python has evaluated the
source-faithful ucalc ans1..ans6 values.  This duplicates the validated ABI
shape from the older rates library but reports provenance as matrix work.
"""
from __future__ import annotations

import ctypes
from dataclasses import dataclass, asdict
import os
import time
from pathlib import Path
from typing import Any

import numpy as np


@dataclass(frozen=True)
class MatrixBackendStatus:
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


_CPP_LIB: ctypes.CDLL | None = None
_CPP_LOAD_ERROR: BaseException | None = None
_CPP_LIBRARY_PATH: str | None = None


def _candidate_library_paths() -> list[Path]:
    env_path = os.environ.get("XSTAR_ATOMIC_MATRIX_LIB")
    paths: list[Path] = []
    if env_path:
        paths.append(Path(env_path).expanduser())
    here = Path(__file__).resolve().parent
    names = (
        "libxstar_matrix.so",
        "xstar_matrix.so",
        "libxstar_matrix.dylib",
        "xstar_matrix.dll",
    )
    for name in names:
        paths.append(here / "cpp" / name)
    for name in names:
        paths.append(here / name)
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
            lib.xstar_matrix_abi_version.argtypes = []
            lib.xstar_matrix_abi_version.restype = ctypes.c_int
            lib.xstar_matrix_backend_name.argtypes = []
            lib.xstar_matrix_backend_name.restype = ctypes.c_char_p
            lib.xstar_matrix_feature_flags.argtypes = []
            lib.xstar_matrix_feature_flags.restype = ctypes.c_int
            lib.xstar_matrix_probe.argtypes = [
                ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_size_t,
            ]
            lib.xstar_matrix_probe.restype = ctypes.c_int
            i64p = np.ctypeslib.ndpointer(dtype=np.int64, ndim=1, flags="C_CONTIGUOUS")
            f64p = np.ctypeslib.ndpointer(dtype=np.float64, ndim=1, flags="C_CONTIGUOUS")
            lib.xstar_matrix_build_mg_type7_terms.argtypes = [
                ctypes.c_int, ctypes.c_int, ctypes.c_int,
                i64p, i64p, i64p, i64p, i64p, i64p, i64p,
                f64p, f64p, f64p, f64p, f64p, f64p,
                ctypes.c_double,
                i64p, f64p,
                ctypes.c_char_p, ctypes.c_size_t,
            ]
            lib.xstar_matrix_build_mg_type7_terms.restype = ctypes.c_int
            try:
                lib.xstar_matrix_dense_fill_terms.argtypes = [
                    ctypes.c_int, ctypes.c_int,
                    i64p, i64p, f64p, f64p, f64p,
                    f64p, f64p, f64p,
                    ctypes.c_char_p, ctypes.c_size_t,
                ]
                lib.xstar_matrix_dense_fill_terms.restype = ctypes.c_int
            except AttributeError:
                pass
            try:
                lib.xstar_matrix_eval_simple_ucalc.argtypes = [
                    ctypes.c_int,
                    i64p, i64p, i64p, i64p, i64p,
                    f64p, f64p, f64p, f64p, f64p, f64p, f64p, f64p,
                    ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_longlong,
                    f64p, i64p, ctypes.c_char_p, ctypes.c_size_t,
                ]
                lib.xstar_matrix_eval_simple_ucalc.restype = ctypes.c_int
            except AttributeError:
                pass
            try:
                lib.xstar_matrix_eval_type51_ucalc_batch.argtypes = [
                    ctypes.c_int,
                    i64p, i64p, i64p, i64p, i64p, i64p, i64p,
                    f64p, f64p, f64p, f64p, f64p, f64p,
                    ctypes.c_double, ctypes.c_double,
                    f64p, i64p, ctypes.c_char_p, ctypes.c_size_t,
                ]
                lib.xstar_matrix_eval_type51_ucalc_batch.restype = ctypes.c_int
            except AttributeError:
                pass
            _CPP_LIB = lib
            _CPP_LIBRARY_PATH = str(path)
            return _CPP_LIB
        raise FileNotFoundError("no xstar_matrix shared library found; attempted: " + "; ".join(attempted))
    except BaseException as exc:  # pragma: no cover - optional shared library
        _CPP_LOAD_ERROR = exc
        return None


def cpp_import_error() -> str | None:
    if _CPP_LOAD_ERROR is None:
        return None
    return f"{type(_CPP_LOAD_ERROR).__name__}: {_CPP_LOAD_ERROR}"


def _backend_name(lib: ctypes.CDLL | None) -> str | None:
    if lib is None:
        return None
    try:
        raw = lib.xstar_matrix_backend_name()
        return raw.decode("ascii", errors="replace") if raw else None
    except Exception:
        return None


def _abi_version(lib: ctypes.CDLL | None) -> int | None:
    if lib is None:
        return None
    try:
        return int(lib.xstar_matrix_abi_version())
    except Exception:
        return None


def _feature_flags(lib: ctypes.CDLL | None) -> int | None:
    if lib is None:
        return None
    try:
        return int(lib.xstar_matrix_feature_flags())
    except Exception:
        return None


def matrix_backend_status(requested: str | None = None) -> MatrixBackendStatus:
    req = (requested or os.environ.get("XSTAR_ATOMIC_MATRIX_BACKEND") or "python").strip().lower()
    if req not in {"python", "cpp", "auto"}:
        req = "python"
    lib = _load_cpp_library()
    if req == "python":
        active = "python"
    elif req == "cpp":
        active = "cpp" if lib is not None else "unavailable"
    else:
        active = "cpp" if lib is not None else "python"
    return MatrixBackendStatus(
        requested=req,
        active=active,
        cpp_available=lib is not None,
        cpp_import_error=cpp_import_error(),
        cpp_library_path=_CPP_LIBRARY_PATH,
        cpp_backend_name=_backend_name(lib),
        cpp_abi_version=_abi_version(lib),
        cpp_feature_flags=_feature_flags(lib),
    )


def probe_cpp_matrix(*, n_records: int = 0, n_basis_rows: int = 0) -> str:
    lib = _load_cpp_library()
    if lib is None:
        raise RuntimeError("C++ matrix shared library is not available" + (f": {cpp_import_error()}" if cpp_import_error() else ""))
    buf = ctypes.create_string_buffer(512)
    rc = lib.xstar_matrix_probe(int(n_records), int(n_basis_rows), buf, ctypes.sizeof(buf))
    message = buf.value.decode("utf-8", errors="replace")
    if rc != 0:
        raise RuntimeError(message or f"xstar_matrix_probe failed with code {rc}")
    return message


_ROLE = {
    1: "forward_offdiag",
    2: "reverse_offdiag",
    3: "forward_diag_loss",
    4: "reverse_diag_loss",
}


def build_mg_type7_terms_matrix_cpp_detailed(
    records: list[dict[str, Any]],
    *,
    basis_n_rows: int,
    term_start: int,
    hydrogen_density_cm3: float,
) -> tuple[list[dict[str, Any]], str, dict[str, float]]:
    """Build calc_hmc_ion matrix terms for Mg type-7 records in libxstar_matrix.so."""
    lib = _load_cpp_library()
    if lib is None:
        raise RuntimeError("C++ matrix shared library is not available" + (f": {cpp_import_error()}" if cpp_import_error() else ""))
    n = int(len(records))
    t0 = time.perf_counter()
    def i64(name: str) -> np.ndarray:
        return np.ascontiguousarray([int(r[name]) for r in records], dtype=np.int64)
    def f64(name: str) -> np.ndarray:
        return np.ascontiguousarray([float(r[name]) for r in records], dtype=np.float64)
    record = i64("record")
    data_type = i64("data_type")
    ion_index = i64("ion_index")
    ion_stage = i64("ion_stage")
    compact_start = i64("compact_start")
    idest1 = i64("idest1")
    idest2 = i64("idest2")
    ans1 = f64("ans1")
    ans2 = f64("ans2")
    ans3 = f64("ans3")
    ans4 = f64("ans4")
    ans5 = f64("ans5")
    ans6 = f64("ans6")
    out_i64 = np.zeros(max(0, n) * 4 * 16, dtype=np.int64)
    out_f64 = np.zeros(max(0, n) * 4 * 4, dtype=np.float64)
    packing_seconds = time.perf_counter() - t0
    buf = ctypes.create_string_buffer(512)
    k0 = time.perf_counter()
    rc = lib.xstar_matrix_build_mg_type7_terms(
        n, int(basis_n_rows), int(term_start),
        record, data_type, ion_index, ion_stage, compact_start, idest1, idest2,
        ans1, ans2, ans3, ans4, ans5, ans6,
        float(hydrogen_density_cm3),
        out_i64, out_f64, buf, ctypes.sizeof(buf),
    )
    cpp_kernel_seconds = time.perf_counter() - k0
    message = buf.value.decode("utf-8", errors="replace")
    if rc != 0:
        raise RuntimeError(message or f"xstar_matrix_build_mg_type7_terms failed with code {rc}")
    rows: list[dict[str, Any]] = []
    oi = out_i64.reshape((max(0, n) * 4, 16)) if n else np.zeros((0, 16), dtype=np.int64)
    of = out_f64.reshape((max(0, n) * 4, 4)) if n else np.zeros((0, 4), dtype=np.float64)
    for j in range(max(0, n) * 4):
        role_code = int(oi[j, 6])
        rows.append({
            "term_index": int(oi[j, 0]),
            "record": int(oi[j, 1]),
            "data_type": int(oi[j, 2]),
            "rate_type": int(oi[j, 3]),
            "ion_index": int(oi[j, 4]),
            "ion_stage": int(oi[j, 5]),
            "role": _ROLE.get(role_code, f"role_{role_code}"),
            "row": int(oi[j, 7]),
            "column": int(oi[j, 8]),
            "idest1": int(oi[j, 9]),
            "idest2": int(oi[j, 10]),
            "lower_endpoint": int(oi[j, 11]),
            "upper_endpoint": int(oi[j, 12]),
            "source_row_unclamped": int(oi[j, 13]),
            "source_column_unclamped": int(oi[j, 14]),
            "source_ipmat_clamped": bool(int(oi[j, 15])),
            "ucalc_status": "evaluated",
            "aj1": float(of[j, 0]),
            "aj2": float(of[j, 1]),
            "cj": float(of[j, 2]),
            "cj2": float(of[j, 3]),
        })
    stats = {
        "records_batched": float(n),
        "cpp_calls": 1.0 if n else 0.0,
        "packing_seconds": float(packing_seconds),
        "cpp_kernel_seconds": float(cpp_kernel_seconds),
        "fallback_count": 0.0,
        "emitted_matrix_terms": float(len(rows)),
    }
    return rows, message, stats


def dense_fill_terms_matrix_cpp(
    terms: list[dict[str, Any]],
    *,
    n_rows: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, str, dict[str, float]]:
    """Fill dense/heating matrices from one-based matrix terms in libxstar_matrix.so."""
    lib = _load_cpp_library()
    if lib is None or not hasattr(lib, "xstar_matrix_dense_fill_terms"):
        raise RuntimeError("C++ matrix dense-fill kernel is not available" + (f": {cpp_import_error()}" if cpp_import_error() else ""))
    n = int(len(terms))
    nr = int(n_rows)
    t0 = time.perf_counter()
    rows = np.ascontiguousarray([int(t["row"]) for t in terms], dtype=np.int64)
    cols = np.ascontiguousarray([int(t["column"]) for t in terms], dtype=np.int64)
    aj1 = np.ascontiguousarray([float(t["aj1"]) for t in terms], dtype=np.float64)
    cj = np.ascontiguousarray([float(t["cj"]) for t in terms], dtype=np.float64)
    cj2 = np.ascontiguousarray([float(t["cj2"]) for t in terms], dtype=np.float64)
    dense = np.zeros((nr, nr), dtype=np.float64, order="C")
    heat = np.zeros((nr, nr), dtype=np.float64, order="C")
    heat2 = np.zeros((nr, nr), dtype=np.float64, order="C")
    packing_seconds = time.perf_counter() - t0
    buf = ctypes.create_string_buffer(512)
    k0 = time.perf_counter()
    rc = lib.xstar_matrix_dense_fill_terms(
        n, nr, rows, cols, aj1, cj, cj2,
        dense.ravel(), heat.ravel(), heat2.ravel(),
        buf, ctypes.sizeof(buf),
    )
    cpp_kernel_seconds = time.perf_counter() - k0
    message = buf.value.decode("utf-8", errors="replace")
    if rc != 0:
        raise RuntimeError(message or f"xstar_matrix_dense_fill_terms failed with code {rc}")
    stats = {
        "records_batched": float(n),
        "cpp_calls": 1.0,
        "packing_seconds": float(packing_seconds),
        "cpp_kernel_seconds": float(cpp_kernel_seconds),
        "fallback_count": 0.0,
        "matrix_dense_terms": float(n),
        "matrix_dense_rows": float(nr),
    }
    return dense, heat, heat2, message, stats


def eval_simple_ucalc_matrix_cpp(
    records: list[dict[str, Any]],
    *,
    temperature_1e4k: float,
    electron_density_cm3: float,
    neutral_h_density_cm3: float,
    ionized_h_density_cm3: float,
    nlevp: int,
) -> tuple[list[dict[str, Any]], str, dict[str, float]]:
    """Evaluate selected simple ucalc branches in libxstar_matrix.so.

    Supported data_type values are 1, 2, 3, 7, 8, and 20.  The caller remains
    responsible for parity-gating and for falling back to Python for all other
    data types or any branch requiring level/radiation-grid context.
    """
    lib = _load_cpp_library()
    if lib is None or not hasattr(lib, "xstar_matrix_eval_simple_ucalc"):
        raise RuntimeError("C++ matrix simple-ucalc kernel is not available" + (f": {cpp_import_error()}" if cpp_import_error() else ""))
    n = int(len(records))
    t0 = time.perf_counter()
    def i64(name: str) -> np.ndarray:
        return np.ascontiguousarray([int(r.get(name, 0)) for r in records], dtype=np.int64)
    def f64(name: str) -> np.ndarray:
        return np.ascontiguousarray([float(r.get(name, 0.0)) for r in records], dtype=np.float64)
    record = i64("record")
    data_type = i64("data_type")
    rate_type = i64("rate_type")
    int0 = i64("int0")
    int1 = i64("int1")
    r0 = f64("r0"); r1 = f64("r1"); r2 = f64("r2"); r3 = f64("r3")
    r4 = f64("r4"); r5 = f64("r5"); r6 = f64("r6"); r7 = f64("r7")
    out_ans = np.zeros(max(0, n) * 6, dtype=np.float64)
    out_i64 = np.zeros(max(0, n) * 6, dtype=np.int64)
    packing_seconds = time.perf_counter() - t0
    buf = ctypes.create_string_buffer(512)
    k0 = time.perf_counter()
    rc = lib.xstar_matrix_eval_simple_ucalc(
        n, record, data_type, rate_type, int0, int1,
        r0, r1, r2, r3, r4, r5, r6, r7,
        float(temperature_1e4k), float(electron_density_cm3),
        float(neutral_h_density_cm3), float(ionized_h_density_cm3), int(nlevp),
        out_ans, out_i64, buf, ctypes.sizeof(buf),
    )
    cpp_kernel_seconds = time.perf_counter() - k0
    message = buf.value.decode("utf-8", errors="replace")
    if rc != 0:
        raise RuntimeError(message or f"xstar_matrix_eval_simple_ucalc failed with code {rc}")
    ans = out_ans.reshape((max(0, n), 6)) if n else np.zeros((0, 6), dtype=np.float64)
    oi = out_i64.reshape((max(0, n), 6)) if n else np.zeros((0, 6), dtype=np.int64)
    rows: list[dict[str, Any]] = []
    applied = 0
    for k in range(n):
        status = int(oi[k, 5])
        if status == 1:
            applied += 1
        rows.append({
            "record": int(oi[k, 0]),
            "data_type": int(oi[k, 1]),
            "rate_type": int(oi[k, 2]),
            "idest1": int(oi[k, 3]),
            "idest2": int(oi[k, 4]),
            "status_code": status,
            "ans1": float(ans[k, 0]),
            "ans2": float(ans[k, 1]),
            "ans3": float(ans[k, 2]),
            "ans4": float(ans[k, 3]),
            "ans5": float(ans[k, 4]),
            "ans6": float(ans[k, 5]),
        })
    stats = {
        "records_batched": float(n),
        "cpp_calls": 1.0 if n else 0.0,
        "packing_seconds": float(packing_seconds),
        "cpp_kernel_seconds": float(cpp_kernel_seconds),
        "ucalc_cpp_applied": float(applied),
        "ucalc_cpp_unsupported": float(n - applied),
        "fallback_count": 0.0,
    }
    return rows, message, stats



def eval_type51_ucalc_matrix_cpp(
    records: list[dict[str, Any]],
    *,
    temperature_k: float,
    electron_density_cm3: float,
) -> tuple[list[dict[str, Any]], str, dict[str, float]]:
    """Evaluate batched data_type=51 Burgess-Tully collision ucalc in libxstar_matrix.so.

    This is intentionally narrow: rate_type=3, data_type=51, five-point BT rows.
    Unsupported rows are returned with status_code=0 so callers can fall back to
    the source-faithful Python evaluator without changing physics.
    """
    lib = _load_cpp_library()
    if lib is None or not hasattr(lib, "xstar_matrix_eval_type51_ucalc_batch"):
        raise RuntimeError("C++ matrix type51 ucalc kernel is not available" + (f": {cpp_import_error()}" if cpp_import_error() else ""))
    n = int(len(records))
    t0 = time.perf_counter()
    def i64(name: str) -> np.ndarray:
        return np.ascontiguousarray([int(r.get(name, 0)) for r in records], dtype=np.int64)
    def f64(name: str) -> np.ndarray:
        return np.ascontiguousarray([float(r.get(name, 0.0)) for r in records], dtype=np.float64)
    record = i64("record")
    ion_index = i64("ion_index")
    ion_stage = i64("ion_stage")
    lower_level = i64("lower_level")
    upper_level = i64("upper_level")
    bt_type = i64("bt_type")
    n_points = i64("n_points")
    eij_ryd = f64("eij_ryd")
    c_bt = f64("c_bt")
    g_lower = f64("g_lower")
    g_upper = f64("g_upper")
    delta_e_ev = f64("delta_e_ev")
    y_values = np.zeros(max(0, n) * 9, dtype=np.float64)
    for k, rec in enumerate(records):
        vals = list(rec.get("y_values", []))[:9]
        for j, val in enumerate(vals):
            y_values[9*k + j] = float(val)
    out_ans = np.zeros(max(0, n) * 6, dtype=np.float64)
    out_i64 = np.zeros(max(0, n) * 8, dtype=np.int64)
    packing_seconds = time.perf_counter() - t0
    buf = ctypes.create_string_buffer(512)
    k0 = time.perf_counter()
    rc = lib.xstar_matrix_eval_type51_ucalc_batch(
        n, record, ion_index, ion_stage, lower_level, upper_level, bt_type, n_points,
        eij_ryd, c_bt, g_lower, g_upper, delta_e_ev, y_values,
        float(temperature_k), float(electron_density_cm3),
        out_ans, out_i64, buf, ctypes.sizeof(buf),
    )
    cpp_kernel_seconds = time.perf_counter() - k0
    message = buf.value.decode("utf-8", errors="replace")
    if rc != 0:
        raise RuntimeError(message or f"xstar_matrix_eval_type51_ucalc_batch failed with code {rc}")
    ans = out_ans.reshape((max(0, n), 6)) if n else np.zeros((0, 6), dtype=np.float64)
    oi = out_i64.reshape((max(0, n), 8)) if n else np.zeros((0, 8), dtype=np.int64)
    rows: list[dict[str, Any]] = []
    applied = 0
    for k in range(n):
        status = int(oi[k, 7])
        if status == 1:
            applied += 1
        rows.append({
            "record": int(oi[k, 0]),
            "data_type": int(oi[k, 1]),
            "rate_type": int(oi[k, 2]),
            "idest1": int(oi[k, 3]),
            "idest2": int(oi[k, 4]),
            "ion_index": int(oi[k, 5]),
            "ion_stage": int(oi[k, 6]),
            "status_code": status,
            "ans1": float(ans[k, 0]),
            "ans2": float(ans[k, 1]),
            "ans3": float(ans[k, 2]),
            "ans4": float(ans[k, 3]),
            "ans5": float(ans[k, 4]),
            "ans6": float(ans[k, 5]),
        })
    stats = {
        "records_batched": float(n),
        "cpp_calls": 1.0 if n else 0.0,
        "packing_seconds": float(packing_seconds),
        "cpp_kernel_seconds": float(cpp_kernel_seconds),
        "ucalc_cpp_applied": float(applied),
        "ucalc_cpp_unsupported": float(n - applied),
        "fallback_count": float(n - applied),
    }
    return rows, message, stats
