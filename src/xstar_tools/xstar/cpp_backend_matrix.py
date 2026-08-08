# XSTAR-PYTHON-SOURCE-CORRESPONDENCE-BEGIN
# Source correspondence:
#   Fortran: calc_hmc_ion.f90 / calc_hmc_element.f90 / msolvelucy.f90 / ucalc.f90
#   Role: Python/native bridge and attribution helpers for the C++ statistical-equilibrium matrix path.
#   Relation: Bridge/diagnostic layer; does not redefine the source matrix equations.
#   Concordance: MATRIX-001; LEVEL-001
#   Qualification: accepted science revision 0.6.48.12.3.45.3.3.8; frozen C++ baseline 0.6.48.12.3.44.
# Atomic-data note (XSTAR Manual Ch. 12; Mendoza et al. 2021, Appendix A):
#   Rule: data type selects the record formula/interpretation; rate type selects downstream use.
#   When record metadata crosses the bridge, data type selects the native UCalc/operator branch and rate
#   type retains source application semantics.
# XSTAR-PYTHON-SOURCE-CORRESPONDENCE-END

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
from typing import Any, Mapping

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
_COMPACT_ARRAY_CACHE: dict[tuple[int, int], tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = {}
_SOURCE_HEADER_CACHE: dict[tuple[int, int], tuple[np.ndarray, np.ndarray]] = {}
_MG_SIMPLE_PAYLOAD_IMMUTABLE_CACHE: dict[tuple[int, int], dict[str, Any]] = {}


def _mg_simple_payload_immutable_cache(master: Any, derived: Any) -> tuple[dict[str, Any], bool, int]:
    """Return run-local immutable Mg source arrays and cache diagnostics.

    The cache owns C-contiguous views/copies of the atomic database arrays.
    These arrays are immutable during one XSTAR process and can therefore be
    reused by every element-evaluation shadow call.
    """
    key = (id(master), id(derived))
    cached = _MG_SIMPLE_PAYLOAD_IMMUTABLE_CACHE.get(key)
    if cached is not None:
        return cached, True, 0
    # Bound retained run-local caches in unusual multi-dataset processes.
    if len(_MG_SIMPLE_PAYLOAD_IMMUTABLE_CACHE) >= 4:
        _MG_SIMPLE_PAYLOAD_IMMUTABLE_CACHE.clear()
    compact_existed = key in _COMPACT_ARRAY_CACHE
    npfi, npar, npnxt, ptrs, rdat, idat = _compact_matrix_arrays(master, derived)
    immutable_bytes = int(sum(x.nbytes for x in (npfi, npar, npnxt, ptrs, rdat, idat)))
    cached = {
        "npfi": npfi, "npar": npar, "npnxt": npnxt, "ptrs": ptrs,
        "rdat": rdat, "idat": idat, "immutable_bytes": immutable_bytes,
        "support_index": {}, "source_count_index": {},
    }
    _MG_SIMPLE_PAYLOAD_IMMUTABLE_CACHE[key] = cached
    # If the generic compact cache already existed, no immutable bytes were
    # copied for this shadow call; otherwise this first miss materialized them.
    return cached, False, 0 if compact_existed else immutable_bytes


def _mg_simple_payload_support_counts(
    cache: dict[str, Any], ion_specs: list[dict[str, int]]
) -> tuple[dict[tuple[int, int], int], dict[tuple[int, int], int], int, int, float]:
    """Build/cache exact static supported/source counts for active ions."""
    started = time.perf_counter()
    npfi = cache["npfi"]; npar = cache["npar"]; npnxt = cache["npnxt"]; ptrs = cache["ptrs"]
    support_index: dict[tuple[int, int], int] = cache["support_index"]
    source_index: dict[tuple[int, int], int] = cache["source_count_index"]
    hits = 0; misses = 0
    for spec in ion_specs:
        ion_index = int(spec["ion_index"]); ion_record = int(spec["ion_record"]); key = (ion_index, ion_record)
        if key in support_index:
            hits += 1
            continue
        misses += 1
        supported = 0; seen = 0
        if 0 <= ion_index < int(npfi.shape[1]):
            for data_chain in range(1, int(npfi.shape[0])):
                rec = int(npfi[data_chain, ion_index]); guard = 0
                while 0 < rec <= int(ptrs.shape[0]) and int(npar[rec]) == ion_record:
                    guard += 1
                    if guard > int(ptrs.shape[0]):
                        break
                    seen += 1
                    dt = int(ptrs[rec - 1, 1]); rt = int(ptrs[rec - 1, 2]); nreal = int(ptrs[rec - 1, 4])
                    if not ((rt == 1 and dt == 53) or rt == 8 or rt == 15):
                        if ((dt == 1 and nreal >= 2) or (dt == 2 and nreal >= 4) or
                            (dt == 3 and nreal >= 2) or (dt == 7 and nreal >= 4) or
                            (dt == 8 and nreal >= 8) or (dt == 20 and nreal >= 5)):
                            supported += 1
                    rec = int(npnxt[rec]) if 0 < rec < int(npnxt.size) else 0
        support_index[key] = int(supported); source_index[key] = int(seen)
    return support_index, source_index, hits, misses, time.perf_counter() - started


def _record_header_arrays_from_ptrs(ptrs: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return cached 1-based record rate/data-type arrays for source scans.

    The Mg source scanner is called once per ion.  Rebuilding these two
    n_records+1 arrays for every ion was responsible for most of the
    source-scan packing time after v0.6.0a16 moved type-49/type-53 to C++.
    Cache by the contiguous ptrs array identity/shape and keep the flat C++ ABI.
    """
    n_records = int(ptrs.shape[0])
    key = (id(ptrs), n_records)
    cached = _SOURCE_HEADER_CACHE.get(key)
    if cached is not None:
        return cached
    record_data_type = np.zeros(n_records + 1, dtype=np.int64)
    record_rate_type = np.zeros(n_records + 1, dtype=np.int64)
    if n_records:
        record_data_type[1:] = ptrs[:, 1]
        record_rate_type[1:] = ptrs[:, 2]
    cached = (record_rate_type, record_data_type)
    _SOURCE_HEADER_CACHE[key] = cached
    return cached


def _compact_matrix_arrays(master: Any, derived: Any) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return cached C-contiguous compact ATDB arrays for matrix backends."""
    key = (id(master), id(derived))
    cached = _COMPACT_ARRAY_CACHE.get(key)
    if cached is not None:
        return cached
    npfi = np.ascontiguousarray(np.asarray(derived.npfi, dtype=np.int64))
    npar = np.ascontiguousarray(np.asarray(derived.npar, dtype=np.int64))
    npnxt = np.ascontiguousarray(np.asarray(derived.npnxt, dtype=np.int64))
    ptrs = np.ascontiguousarray(np.asarray(master.nptrs.numpy(copy=False), dtype=np.int64))
    rdat = np.ascontiguousarray(np.asarray(master.rdat1.numpy(copy=False), dtype=np.float64))
    idat = np.ascontiguousarray(np.asarray(master.idat1.numpy(copy=False), dtype=np.int64))
    cached = (npfi, npar, npnxt, ptrs, rdat, idat)
    _COMPACT_ARRAY_CACHE[key] = cached
    return cached


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
    # Single shared-library location: src/xstar_tools/xstar/cpp/.
    for name in names:
        paths.append(here / "cpp" / name)
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
                lib.xstar_matrix_build_mg_rates_and_matrix.argtypes = [
                    ctypes.c_int, ctypes.c_int, ctypes.c_int,
                    i64p, i64p, i64p, i64p, i64p, i64p, i64p, i64p,
                    f64p, f64p, f64p, f64p, f64p, f64p,
                    ctypes.c_double,
                    i64p, f64p, i64p,
                    ctypes.c_char_p, ctypes.c_size_t,
                ]
                lib.xstar_matrix_build_mg_rates_and_matrix.restype = ctypes.c_int
            except AttributeError:
                pass
            try:
                lib.xstar_matrix_build_mg_type51_rates_and_matrix.argtypes = [
                    ctypes.c_int, ctypes.c_int, ctypes.c_int,
                    i64p, i64p, i64p, i64p, i64p, i64p, i64p, i64p,
                    f64p, f64p, f64p, f64p, f64p, f64p,
                    ctypes.c_double, ctypes.c_double, ctypes.c_double,
                    i64p, f64p, i64p,
                    ctypes.c_char_p, ctypes.c_size_t,
                ]
                lib.xstar_matrix_build_mg_type51_rates_and_matrix.restype = ctypes.c_int
            except AttributeError:
                pass
            try:
                lib.xstar_matrix_eval_mg_ion_type51_rates_and_matrix.argtypes = [
                    ctypes.c_int, ctypes.c_int, ctypes.c_int,
                    ctypes.c_longlong, ctypes.c_longlong, ctypes.c_longlong,
                    i64p, i64p, i64p, i64p, i64p, i64p, i64p, i64p,
                    f64p, f64p, f64p, f64p, f64p, f64p,
                    ctypes.c_double, ctypes.c_double, ctypes.c_double,
                    i64p, f64p, i64p,
                    ctypes.c_char_p, ctypes.c_size_t,
                ]
                lib.xstar_matrix_eval_mg_ion_type51_rates_and_matrix.restype = ctypes.c_int
            except AttributeError:
                pass
            try:
                lib.xstar_matrix_scan_mg_ion_source_records.argtypes = [
                    ctypes.c_int, ctypes.c_int, ctypes.c_longlong, ctypes.c_longlong,
                    i64p, i64p, i64p, i64p, i64p,
                    i64p, i64p, ctypes.c_char_p, ctypes.c_size_t,
                ]
                lib.xstar_matrix_scan_mg_ion_source_records.restype = ctypes.c_int
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
                lib.xstar_matrix_eval_mg_ion_source_simple_payloads.argtypes = [
                    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                    ctypes.c_longlong, ctypes.c_longlong,
                    i64p, i64p, i64p, i64p, f64p, i64p,
                    ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_longlong,
                    i64p, f64p, i64p, ctypes.c_char_p, ctypes.c_size_t,
                ]
                lib.xstar_matrix_eval_mg_ion_source_simple_payloads.restype = ctypes.c_int
            except AttributeError:
                pass
            try:
                lib.xstar_matrix_eval_mg_ion_source_simple_payloads_batch.argtypes = [
                    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                    i64p, i64p, i64p, i64p,
                    i64p, i64p, i64p, i64p, f64p, i64p,
                    ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double,
                    i64p, f64p, i64p, ctypes.c_char_p, ctypes.c_size_t,
                ]
                lib.xstar_matrix_eval_mg_ion_source_simple_payloads_batch.restype = ctypes.c_int
            except AttributeError:
                pass
            try:
                lib.xstar_matrix_accumulate_mg_ion_source_simple_terms.argtypes = [
                    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                    ctypes.c_int, ctypes.c_int, ctypes.c_int,
                    ctypes.c_longlong, ctypes.c_longlong, ctypes.c_longlong, ctypes.c_longlong, ctypes.c_longlong,
                    i64p, i64p, i64p, i64p, f64p, i64p,
                    ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double,
                    i64p, f64p, i64p, ctypes.c_char_p, ctypes.c_size_t,
                ]
                lib.xstar_matrix_accumulate_mg_ion_source_simple_terms.restype = ctypes.c_int
            except AttributeError:
                pass
            try:
                lib.xstar_matrix_accumulate_mg_ion_rate7_type49_terms.argtypes = [
                    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                    ctypes.c_int, ctypes.c_int, ctypes.c_int,
                    ctypes.c_longlong, ctypes.c_longlong, ctypes.c_longlong, ctypes.c_longlong,
                    i64p, i64p, i64p, i64p, i64p, f64p, f64p,
                    f64p, i64p, f64p, f64p, f64p, f64p, f64p, f64p,
                    ctypes.c_double, ctypes.c_double, ctypes.c_double,
                    i64p, f64p, i64p, ctypes.c_char_p, ctypes.c_size_t,
                ]
                lib.xstar_matrix_accumulate_mg_ion_rate7_type49_terms.restype = ctypes.c_int
            except AttributeError:
                pass
            try:
                lib.xstar_matrix_accumulate_mg_ion_rate7_type53_terms.argtypes = [
                    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                    ctypes.c_int, ctypes.c_int, ctypes.c_int,
                    ctypes.c_longlong, ctypes.c_longlong, ctypes.c_longlong, ctypes.c_longlong,
                    i64p, i64p, i64p, i64p, i64p, f64p, f64p,
                    f64p, i64p, f64p, f64p, f64p, f64p, f64p, f64p,
                    ctypes.c_double, ctypes.c_double, ctypes.c_double,
                    i64p, f64p, i64p, f64p, ctypes.c_int, ctypes.c_char_p, ctypes.c_size_t,
                ]
                lib.xstar_matrix_accumulate_mg_ion_rate7_type53_terms.restype = ctypes.c_int
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
    5: "scalar_pirt",
    6: "scalar_rrrt",
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




def build_mg_rates_and_matrix_cpp_detailed(
    records: list[dict[str, Any]],
    *,
    basis_n_rows: int,
    term_start: int,
    hydrogen_density_cm3: float,
) -> tuple[list[dict[str, Any]], str, dict[str, float]]:
    """Build Mg rate+matrix terms with the coarse libxstar_matrix.so ABI.

    The first supported group is rate_type=3/data_type=51.  The ABI accepts
    already evaluated ans1..ans6 values in this release so it can be attached
    safely to the real calc_hmc_all hot path before moving source traversal and
    ucalc into C++ in later releases.
    """
    lib = _load_cpp_library()
    if lib is None or not hasattr(lib, "xstar_matrix_build_mg_rates_and_matrix"):
        raise RuntimeError("C++ Mg rates+matrix kernel is not available" + (f": {cpp_import_error()}" if cpp_import_error() else ""))
    n = int(len(records))
    t0 = time.perf_counter()
    def i64(name: str) -> np.ndarray:
        return np.ascontiguousarray([int(r.get(name, 0)) for r in records], dtype=np.int64)
    def f64(name: str) -> np.ndarray:
        return np.ascontiguousarray([float(r.get(name, 0.0)) for r in records], dtype=np.float64)
    record = i64("record")
    rate_type = i64("rate_type")
    data_type = i64("data_type")
    ion_index = i64("ion_index")
    ion_stage = i64("ion_stage")
    compact_start = i64("compact_start")
    idest1 = i64("idest1")
    idest2 = i64("idest2")
    ans1 = f64("ans1"); ans2 = f64("ans2"); ans3 = f64("ans3")
    ans4 = f64("ans4"); ans5 = f64("ans5"); ans6 = f64("ans6")
    out_i64 = np.zeros(max(0, n) * 4 * 16, dtype=np.int64)
    out_f64 = np.zeros(max(0, n) * 4 * 4, dtype=np.float64)
    out_stats = np.zeros(8, dtype=np.int64)
    packing_seconds = time.perf_counter() - t0
    buf = ctypes.create_string_buffer(512)
    k0 = time.perf_counter()
    rc = lib.xstar_matrix_build_mg_rates_and_matrix(
        n, int(basis_n_rows), int(term_start),
        record, rate_type, data_type, ion_index, ion_stage, compact_start, idest1, idest2,
        ans1, ans2, ans3, ans4, ans5, ans6,
        float(hydrogen_density_cm3), out_i64, out_f64, out_stats, buf, ctypes.sizeof(buf),
    )
    cpp_kernel_seconds = time.perf_counter() - k0
    message = buf.value.decode("utf-8", errors="replace")
    if rc != 0:
        raise RuntimeError(message or f"xstar_matrix_build_mg_rates_and_matrix failed with code {rc}")
    emitted = int(out_stats[4])
    oi = out_i64.reshape((max(0, n) * 4, 16)) if n else np.zeros((0, 16), dtype=np.int64)
    of = out_f64.reshape((max(0, n) * 4, 4)) if n else np.zeros((0, 4), dtype=np.float64)
    rows: list[dict[str, Any]] = []
    for j in range(max(0, emitted)):
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
    records_supported = int(out_stats[1])
    stats = {
        "records_seen": float(out_stats[0]),
        "records_supported": float(records_supported),
        "records_batched": float(out_stats[2]),
        "cpp_calls": float(out_stats[3]),
        "packing_seconds": float(packing_seconds),
        "cpp_kernel_seconds": float(cpp_kernel_seconds),
        "fallback_count": float(max(0, int(out_stats[0]) - records_supported)),
        "fallback_unsupported_rate_data": float(out_stats[5]),
        "fallback_nonpositive_endpoint": float(out_stats[6]),
        "fallback_nonfinite_answer": float(out_stats[7]),
        "emitted_matrix_terms": float(len(rows)),
    }
    return rows, message, stats


def build_mg_type51_rates_and_matrix_cpp_detailed(
    records: list[dict[str, Any]],
    *,
    basis_n_rows: int,
    term_start: int,
    temperature_k: float,
    electron_density_cm3: float,
    hydrogen_density_cm3: float,
) -> tuple[list[dict[str, Any]], str, dict[str, float]]:
    """Evaluate Mg rate_type=3/data_type=51 ucalc and matrix terms in C++.

    ``records`` must already be in source traversal order and contain decoded
    Burgess-Tully payload fields.  This ABI is the coarse hot-path replacement:
    C++ evaluates the type-51 collision rate and emits the four calc_hmc_ion
    matrix rows in one call.
    """
    lib = _load_cpp_library()
    if lib is None or not hasattr(lib, "xstar_matrix_build_mg_type51_rates_and_matrix"):
        raise RuntimeError("C++ matrix Mg type51 rates+matrix kernel is not available" + (f": {cpp_import_error()}" if cpp_import_error() else ""))
    n = int(len(records))
    t0 = time.perf_counter()
    def i64(name: str) -> np.ndarray:
        return np.ascontiguousarray([int(r.get(name, 0)) for r in records], dtype=np.int64)
    def f64(name: str) -> np.ndarray:
        return np.ascontiguousarray([float(r.get(name, 0.0)) for r in records], dtype=np.float64)
    record = i64("record")
    ion_index = i64("ion_index")
    ion_stage = i64("ion_stage")
    compact_start = i64("compact_start")
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
            y_values[9 * k + j] = float(val)
    max_terms = max(0, n) * 4
    out_i64 = np.zeros(max_terms * 20, dtype=np.int64)
    out_f64 = np.zeros(max_terms * 10, dtype=np.float64)
    out_stats = np.zeros(10, dtype=np.int64)
    packing_seconds = time.perf_counter() - t0
    buf = ctypes.create_string_buffer(512)
    k0 = time.perf_counter()
    rc = lib.xstar_matrix_build_mg_type51_rates_and_matrix(
        n, int(basis_n_rows), int(term_start),
        record, ion_index, ion_stage, compact_start, lower_level, upper_level, bt_type, n_points,
        eij_ryd, c_bt, g_lower, g_upper, delta_e_ev, y_values,
        float(temperature_k), float(electron_density_cm3), float(hydrogen_density_cm3),
        out_i64, out_f64, out_stats, buf, ctypes.sizeof(buf),
    )
    cpp_kernel_seconds = time.perf_counter() - k0
    message = buf.value.decode("utf-8", errors="replace")
    if rc != 0:
        raise RuntimeError(message or f"xstar_matrix_build_mg_type51_rates_and_matrix failed with code {rc}")
    emitted = int(out_stats[4])
    oi = out_i64[: emitted * 20].reshape((emitted, 20)) if emitted else np.zeros((0, 20), dtype=np.int64)
    of = out_f64[: emitted * 10].reshape((emitted, 10)) if emitted else np.zeros((0, 10), dtype=np.float64)
    rows: list[dict[str, Any]] = []
    role_name = _ROLE.get
    for j in range(emitted):
        rows.append({
            "term_index": int(oi[j, 0]),
            "record": int(oi[j, 1]),
            "data_type": int(oi[j, 2]),
            "rate_type": int(oi[j, 3]),
            "ion_index": int(oi[j, 4]),
            "ion_stage": int(oi[j, 5]),
            "role": role_name(int(oi[j, 6]), "unknown"),
            "row": int(oi[j, 7]),
            "column": int(oi[j, 8]),
            "idest1": int(oi[j, 9]),
            "idest2": int(oi[j, 10]),
            "lower_endpoint": int(oi[j, 11]),
            "upper_endpoint": int(oi[j, 12]),
            "source_row_unclamped": int(oi[j, 13]),
            "source_column_unclamped": int(oi[j, 14]),
            "source_ipmat_clamped": bool(int(oi[j, 15])),
            "ucalc_status": "evaluated" if int(oi[j, 16]) == 1 else "unsupported",
            "bt_type": int(oi[j, 17]),
            "n_points": int(oi[j, 18]),
            "aj1": float(of[j, 0]),
            "aj2": float(of[j, 1]),
            "cj": float(of[j, 2]),
            "cj2": float(of[j, 3]),
            "ans1": float(of[j, 4]),
            "ans2": float(of[j, 5]),
            "ans3": float(of[j, 6]),
            "ans4": float(of[j, 7]),
            "ans5": float(of[j, 8]),
            "ans6": float(of[j, 9]),
        })
    supported = int(out_stats[1])
    stats = {
        "records_seen": float(out_stats[0]),
        "records_supported": float(supported),
        "records_batched": float(out_stats[2]),
        "cpp_calls": float(out_stats[3]),
        "packing_seconds": float(packing_seconds),
        "cpp_kernel_seconds": float(cpp_kernel_seconds),
        "fallback_count": float(max(0, int(out_stats[0]) - supported)),
        "fallback_unsupported_rate_data": float(out_stats[5]),
        "fallback_nonpositive_endpoint": float(out_stats[6]),
        "fallback_nonfinite_answer": float(out_stats[7]),
        "ucalc_cpp_applied": float(out_stats[8]),
        "ucalc_cpp_unsupported": float(out_stats[9]),
        "emitted_matrix_terms": float(emitted),
    }
    return rows, message, stats



def eval_mg_ion_type51_rates_and_matrix_cpp_detailed(
    records: list[dict[str, Any]],
    *,
    basis_n_rows: int,
    term_start: int,
    ion_index: int,
    ion_stage: int,
    nlev: int,
    temperature_k: float,
    electron_density_cm3: float,
    hydrogen_density_cm3: float,
) -> tuple[list[dict[str, Any]], str, dict[str, float]]:
    """Evaluate one Mg ion's supported type-51 rates+matrix rows in C++.

    v0.6.0a8 widens the public ABI boundary to an ion-level call.  Python still
    decodes source records into compact payload rows in this release, but the
    caller now sends one ion block to C++ and receives ion-level counters.  This
    is the stable call site for moving source-pointer traversal into C++ next.
    """
    lib = _load_cpp_library()
    if lib is None or not hasattr(lib, "xstar_matrix_eval_mg_ion_type51_rates_and_matrix"):
        # Fall back to the record-batch function on older locally-built libs.
        rows, message, stats = build_mg_type51_rates_and_matrix_cpp_detailed(
            records,
            basis_n_rows=basis_n_rows,
            term_start=term_start,
            temperature_k=temperature_k,
            electron_density_cm3=electron_density_cm3,
            hydrogen_density_cm3=hydrogen_density_cm3,
        )
        stats = dict(stats)
        stats.setdefault("ion_cpp_calls", stats.get("cpp_calls", 0.0))
        stats.setdefault("ion_records_batched", stats.get("records_batched", 0.0))
        return rows, message, stats
    n = int(len(records))
    t0 = time.perf_counter()
    def i64(name: str) -> np.ndarray:
        return np.ascontiguousarray([int(r.get(name, 0)) for r in records], dtype=np.int64)
    def f64(name: str) -> np.ndarray:
        return np.ascontiguousarray([float(r.get(name, 0.0)) for r in records], dtype=np.float64)
    record = i64("record")
    ion_index_arr = i64("ion_index")
    ion_stage_arr = i64("ion_stage")
    compact_start = i64("compact_start")
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
            y_values[9 * k + j] = float(val)
    max_terms = max(0, n) * 4
    out_i64 = np.zeros(max_terms * 20, dtype=np.int64)
    out_f64 = np.zeros(max_terms * 10, dtype=np.float64)
    out_stats = np.zeros(12, dtype=np.int64)
    packing_seconds = time.perf_counter() - t0
    buf = ctypes.create_string_buffer(512)
    k0 = time.perf_counter()
    rc = lib.xstar_matrix_eval_mg_ion_type51_rates_and_matrix(
        n, int(basis_n_rows), int(term_start),
        int(ion_index), int(ion_stage), int(nlev),
        record, ion_index_arr, ion_stage_arr, compact_start, lower_level, upper_level, bt_type, n_points,
        eij_ryd, c_bt, g_lower, g_upper, delta_e_ev, y_values,
        float(temperature_k), float(electron_density_cm3), float(hydrogen_density_cm3),
        out_i64, out_f64, out_stats, buf, ctypes.sizeof(buf),
    )
    cpp_kernel_seconds = time.perf_counter() - k0
    message = buf.value.decode("utf-8", errors="replace")
    if rc != 0:
        raise RuntimeError(message or f"xstar_matrix_eval_mg_ion_type51_rates_and_matrix failed with code {rc}")
    emitted = int(out_stats[4])
    oi = out_i64[: emitted * 20].reshape((emitted, 20)) if emitted else np.zeros((0, 20), dtype=np.int64)
    of = out_f64[: emitted * 10].reshape((emitted, 10)) if emitted else np.zeros((0, 10), dtype=np.float64)
    rows: list[dict[str, Any]] = []
    role_name = _ROLE.get
    for j in range(emitted):
        rows.append({
            "term_index": int(oi[j, 0]),
            "record": int(oi[j, 1]),
            "data_type": int(oi[j, 2]),
            "rate_type": int(oi[j, 3]),
            "ion_index": int(oi[j, 4]),
            "ion_stage": int(oi[j, 5]),
            "role": role_name(int(oi[j, 6]), "unknown"),
            "row": int(oi[j, 7]),
            "column": int(oi[j, 8]),
            "idest1": int(oi[j, 9]),
            "idest2": int(oi[j, 10]),
            "lower_endpoint": int(oi[j, 11]),
            "upper_endpoint": int(oi[j, 12]),
            "source_row_unclamped": int(oi[j, 13]),
            "source_column_unclamped": int(oi[j, 14]),
            "source_ipmat_clamped": bool(int(oi[j, 15])),
            "ucalc_status": "evaluated" if int(oi[j, 16]) == 1 else "unsupported",
            "bt_type": int(oi[j, 17]),
            "n_points": int(oi[j, 18]),
            "aj1": float(of[j, 0]),
            "aj2": float(of[j, 1]),
            "cj": float(of[j, 2]),
            "cj2": float(of[j, 3]),
            "ans1": float(of[j, 4]),
            "ans2": float(of[j, 5]),
            "ans3": float(of[j, 6]),
            "ans4": float(of[j, 7]),
            "ans5": float(of[j, 8]),
            "ans6": float(of[j, 9]),
        })
    supported = int(out_stats[1])
    stats = {
        "records_seen": float(out_stats[0]),
        "records_supported": float(supported),
        "records_batched": float(out_stats[2]),
        "cpp_calls": float(out_stats[3]),
        "packing_seconds": float(packing_seconds),
        "cpp_kernel_seconds": float(cpp_kernel_seconds),
        "fallback_count": float(max(0, int(out_stats[0]) - supported)),
        "fallback_unsupported_rate_data": float(out_stats[5]),
        "fallback_nonpositive_endpoint": float(out_stats[6]),
        "fallback_nonfinite_answer": float(out_stats[7]),
        "ucalc_cpp_applied": float(out_stats[8]),
        "ucalc_cpp_unsupported": float(out_stats[9]),
        "emitted_matrix_terms": float(emitted),
        "ion_cpp_calls": float(out_stats[10]) if out_stats.size > 10 else float(out_stats[3]),
        "ion_records_batched": float(out_stats[11]) if out_stats.size > 11 else float(out_stats[2]),
    }
    return rows, message, stats


def scan_mg_ion_source_records_cpp_detailed(
    *,
    master: Any,
    derived: Any,
    ion_index: int,
    ion_record: int,
) -> tuple[list[dict[str, Any]], str, dict[str, float]]:
    """Traverse one Mg ion's source-pointer chains in C++.

    This is the v0.6.0a8 boundary-widening step: C++ owns the
    ``npfi -> npnxt`` linked-list traversal and returns source-ordered record
    headers for Python fallback/evaluation.  It does not yet decode every
    atomic payload, but it removes the Python pointer walk and provides the
    stable ion-level ABI for moving more rate/data groups into C++.
    """
    lib = _load_cpp_library()
    if lib is None or not hasattr(lib, "xstar_matrix_scan_mg_ion_source_records"):
        raise RuntimeError("C++ Mg ion source scanner is not available" + (f": {cpp_import_error()}" if cpp_import_error() else ""))
    t0 = time.perf_counter()
    npfi_all, npar, npnxt, ptrs, _rdat, _idat = _compact_matrix_arrays(master, derived)
    npfi = np.ascontiguousarray(npfi_all[:, int(ion_index)])
    n_records = int(ptrs.shape[0])
    record_rate_type, record_data_type = _record_header_arrays_from_ptrs(ptrs)
    max_out = max(1, n_records)
    out_i64 = np.zeros(max_out * 8, dtype=np.int64)
    out_stats = np.zeros(12, dtype=np.int64)
    packing_seconds = time.perf_counter() - t0
    buf = ctypes.create_string_buffer(512)
    k0 = time.perf_counter()
    rc = lib.xstar_matrix_scan_mg_ion_source_records(
        int(npfi.size), int(n_records), int(ion_index), int(ion_record),
        npfi, npar, npnxt, record_rate_type, record_data_type,
        out_i64, out_stats, buf, ctypes.sizeof(buf),
    )
    cpp_kernel_seconds = time.perf_counter() - k0
    message = buf.value.decode("utf-8", errors="replace")
    if rc != 0:
        raise RuntimeError(message or f"xstar_matrix_scan_mg_ion_source_records failed with code {rc}")
    emitted = int(out_stats[4])
    oi = out_i64[: emitted * 8].reshape((emitted, 8)) if emitted else np.zeros((0, 8), dtype=np.int64)
    rows: list[dict[str, Any]] = []
    for j in range(emitted):
        rows.append({
            "ordinal": int(oi[j, 0]),
            "record": int(oi[j, 1]),
            "rate_type": int(oi[j, 2]),
            "data_type": int(oi[j, 3]),
            "data_type_chain": int(oi[j, 4]),
            "next_record": int(oi[j, 5]),
            "supported_mask": int(oi[j, 6]),
            "skip_mask": int(oi[j, 7]),
        })
    stats = {
        "records_seen": float(out_stats[0]),
        "records_supported": float(out_stats[1]),
        "records_batched": float(out_stats[2]),
        "cpp_calls": float(out_stats[3]),
        "emitted_records": float(emitted),
        "mg_ion_source_traversal_cpp_calls": float(out_stats[3]),
        "mg_ion_source_records_seen": float(out_stats[0]),
        "mg_ion_source_records_supported": float(out_stats[1]),
        "mg_ion_source_type51_records": float(out_stats[5]),
        "mg_ion_source_type7_records": float(out_stats[6]),
        "mg_ion_source_simple_records": float(out_stats[7]),
        "mg_ion_source_skipped_records": float(out_stats[8]),
        "mg_ion_source_loop_guard_hits": float(out_stats[9]),
        "packing_seconds": float(packing_seconds),
        "cpp_kernel_seconds": float(cpp_kernel_seconds),
        "fallback_count": 0.0,
    }
    return rows, message, stats


def eval_mg_ion_source_simple_payloads_cpp_detailed(
    *,
    master: Any,
    derived: Any,
    ion_index: int,
    ion_record: int,
    temperature_1e4k: float,
    electron_density_cm3: float,
    neutral_h_density_cm3: float,
    ionized_h_density_cm3: float,
    nlevp: int,
) -> tuple[list[dict[str, Any]], str, dict[str, float]]:
    """Evaluate accepted per-ion Mg simple payloads with stage-level timings."""
    lib = _load_cpp_library()
    if lib is None or not hasattr(lib, "xstar_matrix_eval_mg_ion_source_simple_payloads"):
        raise RuntimeError("C++ Mg ion source simple-payload evaluator is not available" + (f": {cpp_import_error()}" if cpp_import_error() else ""))

    prep0 = time.perf_counter()
    npfi = np.ascontiguousarray(np.asarray(derived.npfi[:, int(ion_index)], dtype=np.int64))
    npar = np.ascontiguousarray(np.asarray(derived.npar, dtype=np.int64))
    npnxt = np.ascontiguousarray(np.asarray(derived.npnxt, dtype=np.int64))
    ptrs = np.ascontiguousarray(np.asarray(master.nptrs.numpy(copy=False), dtype=np.int64))
    rdat = np.ascontiguousarray(np.asarray(master.rdat1.numpy(copy=False), dtype=np.float64))
    idat = np.ascontiguousarray(np.asarray(master.idat1.numpy(copy=False), dtype=np.int64))
    n_records = int(ptrs.shape[0])
    max_out = max(1, n_records)
    out_i64 = np.zeros(max_out * 10, dtype=np.int64)
    out_f64 = np.zeros(max_out * 6, dtype=np.float64)
    out_stats = np.zeros(20, dtype=np.int64)
    input_preparation_seconds = time.perf_counter() - prep0
    input_bytes = int(npfi.nbytes + npar.nbytes + npnxt.nbytes + ptrs.nbytes + rdat.nbytes + idat.nbytes)
    output_capacity_bytes = int(out_i64.nbytes + out_f64.nbytes + out_stats.nbytes)
    allocation_count = 9

    buf = ctypes.create_string_buffer(512)
    call0 = time.perf_counter()
    rc = lib.xstar_matrix_eval_mg_ion_source_simple_payloads(
        int(npfi.size), int(n_records), int(rdat.size), int(idat.size),
        int(ion_index), int(ion_record),
        npfi, npar, npnxt, ptrs.ravel(), rdat, idat,
        float(temperature_1e4k), float(electron_density_cm3),
        float(neutral_h_density_cm3), float(ionized_h_density_cm3), int(nlevp),
        out_i64, out_f64, out_stats, buf, ctypes.sizeof(buf),
    )
    python_to_cpp_call_seconds = time.perf_counter() - call0
    message = buf.value.decode("utf-8", errors="replace")
    if rc != 0:
        raise RuntimeError(message or f"xstar_matrix_eval_mg_ion_source_simple_payloads failed with code {rc}")

    unpack0 = time.perf_counter()
    emitted = int(out_stats[4])
    oi = out_i64[: emitted * 10].reshape((emitted, 10)) if emitted else np.zeros((0, 10), dtype=np.int64)
    of = out_f64[: emitted * 6].reshape((emitted, 6)) if emitted else np.zeros((0, 6), dtype=np.float64)
    rows: list[dict[str, Any]] = []
    for j in range(emitted):
        rows.append({
            "record": int(oi[j, 0]), "rate_type": int(oi[j, 1]), "data_type": int(oi[j, 2]),
            "data_type_chain": int(oi[j, 3]), "next_record": int(oi[j, 4]),
            "idest1": int(oi[j, 5]), "idest2": int(oi[j, 6]), "status_code": int(oi[j, 7]),
            "supported_mask": int(oi[j, 8]), "skip_mask": int(oi[j, 9]),
            "ans1": float(of[j, 0]), "ans2": float(of[j, 1]), "ans3": float(of[j, 2]),
            "ans4": float(of[j, 3]), "ans5": float(of[j, 4]), "ans6": float(of[j, 5]),
        })
    output_copy_commit_seconds = time.perf_counter() - unpack0
    output_emitted_bytes = int(emitted * (10 * 8 + 6 * 8))
    cpp_kernel_compute_seconds = float(out_stats[16]) * 1.0e-9
    stats = {
        "records_seen": float(out_stats[0]), "records_supported": float(out_stats[1]),
        "records_batched": float(out_stats[2]), "cpp_calls": float(out_stats[3]),
        "packing_seconds": float(input_preparation_seconds),
        "cpp_kernel_seconds": float(python_to_cpp_call_seconds),
        "input_preparation_seconds": float(input_preparation_seconds),
        "python_to_cpp_call_seconds": float(python_to_cpp_call_seconds),
        "cpp_kernel_compute_seconds": float(cpp_kernel_compute_seconds),
        "output_copy_commit_seconds": float(output_copy_commit_seconds),
        "allocation_count": float(allocation_count), "input_bytes": float(input_bytes),
        "output_capacity_bytes": float(output_capacity_bytes),
        "output_emitted_bytes": float(output_emitted_bytes),
        "bytes_copied": float(input_bytes + output_emitted_bytes),
        "fallback_count": float(out_stats[12]), "ucalc_cpp_applied": float(out_stats[1]),
        "ucalc_cpp_unsupported": float(out_stats[12]), "emitted_records": float(emitted),
        "payload_length": float(emitted), "terms_processed": float(emitted),
        "records_processed": float(out_stats[0]), "source_records": float(out_stats[0]),
        "mg_ion_payload_type1_records": float(out_stats[5]),
        "mg_ion_payload_type2_records": float(out_stats[6]),
        "mg_ion_payload_type3_records": float(out_stats[7]),
        "mg_ion_payload_type7_records": float(out_stats[8]),
        "mg_ion_payload_type8_records": float(out_stats[9]),
        "mg_ion_payload_type20_records": float(out_stats[10]),
        "mg_ion_payload_skipped_records": float(out_stats[11]),
        "mg_ion_payload_loop_guard_hits": float(out_stats[13]),
    }
    return rows, message, stats


def eval_mg_element_simple_payloads_batch_shadow_cpp_detailed(
    *,
    master: Any,
    derived: Any,
    ion_specs: list[dict[str, int]],
    temperature_1e4k: float,
    electron_density_cm3: float,
    neutral_h_density_cm3: float,
    ionized_h_density_cm3: float,
) -> tuple[list[dict[str, Any]], str, dict[str, float]]:
    """Evaluate supported Mg ions in one cached C++ call.

    The caller decides whether the validated result is shadow-only or a guarded
    promoted product path. Immutable arrays are cached once per process; per
    evaluation only compact active-ion metadata is packed.
    """
    lib = _load_cpp_library()
    if lib is None or not hasattr(lib, "xstar_matrix_eval_mg_ion_source_simple_payloads_batch"):
        raise RuntimeError("C++ Mg element simple-payload batch shadow evaluator is not available" + (f": {cpp_import_error()}" if cpp_import_error() else ""))
    if not ion_specs:
        return [], "no ion specs", {"cpp_calls": 0.0, "batch_ion_count": 0.0, "cache_hits": 0.0, "cache_misses": 0.0}

    prep0 = time.perf_counter()
    cache, cache_hit, immutable_copy_bytes = _mg_simple_payload_immutable_cache(master, derived)
    support_index, source_index, support_hits, support_misses, support_index_seconds = _mg_simple_payload_support_counts(cache, ion_specs)
    active_specs = [x for x in ion_specs if support_index.get((int(x["ion_index"]), int(x["ion_record"])), 0) > 0]
    zero_output_ions_skipped = int(len(ion_specs) - len(active_specs))
    expected_supported_records = int(sum(support_index[(int(x["ion_index"]), int(x["ion_record"]))] for x in active_specs))
    expected_source_records = int(sum(source_index.get((int(x["ion_index"]), int(x["ion_record"])), 0) for x in active_specs))

    if not active_specs or expected_supported_records <= 0:
        elapsed = time.perf_counter() - prep0
        immutable_bytes = int(cache["immutable_bytes"])
        return [], "batch simple payload shadow no supported ions", {
            "batch_ion_count": 0.0, "total_ion_count": float(len(ion_specs)),
            "zero_output_ions_skipped": float(zero_output_ions_skipped),
            "expected_supported_records": 0.0, "records_seen": 0.0,
            "records_supported": 0.0, "emitted_records": 0.0, "cpp_calls": 0.0,
            "input_preparation_seconds": float(elapsed), "python_to_cpp_call_seconds": 0.0,
            "cpp_kernel_compute_seconds": 0.0, "output_copy_commit_seconds": 0.0,
            "support_index_seconds": float(support_index_seconds),
            "cache_hits": float(1 if cache_hit else 0), "cache_misses": float(0 if cache_hit else 1),
            "support_index_hits": float(support_hits), "support_index_misses": float(support_misses),
            "immutable_cache_bytes": float(immutable_bytes), "immutable_copy_bytes": float(immutable_copy_bytes),
            "evaluation_input_bytes": 0.0, "compact_ion_metadata_bytes": 0.0,
            "npfi_slice_bytes": 0.0, "source_index_entries": 0.0, "output_capacity_bytes": 0.0,
            "output_emitted_bytes": 0.0, "actual_bytes_copied": float(immutable_copy_bytes),
            "bytes_copied": float(immutable_copy_bytes), "peak_working_set_bytes": float(immutable_bytes),
            "allocation_count": float(0 if cache_hit else 6), "payload_length": 0.0,
            "terms_processed": 0.0, "records_processed": 0.0, "source_records": 0.0,
        }

    npfi_all = cache["npfi"]; npar = cache["npar"]; npnxt = cache["npnxt"]
    ptrs = cache["ptrs"]; rdat = cache["rdat"]; idat = cache["idat"]
    ion_indices = np.asarray([int(x["ion_index"]) for x in active_specs], dtype=np.int64)
    ion_records = np.asarray([int(x["ion_record"]) for x in active_specs], dtype=np.int64)
    ion_stages = np.asarray([int(x["ion_stage"]) for x in active_specs], dtype=np.int64)
    nlevp = np.asarray([int(x["nlevp"]) for x in active_specs], dtype=np.int64)
    npfi_matrix = np.ascontiguousarray(npfi_all[:, ion_indices].T, dtype=np.int64)
    max_out = expected_supported_records
    out_i64 = np.empty(max_out * 14, dtype=np.int64)
    out_f64 = np.empty(max_out * 6, dtype=np.float64)
    out_stats = np.zeros(20, dtype=np.int64)
    compact_ion_metadata_bytes = int(sum(x.nbytes for x in (ion_indices, ion_records, ion_stages, nlevp)))
    npfi_slice_bytes = int(npfi_matrix.nbytes)
    evaluation_input_bytes = int(compact_ion_metadata_bytes + npfi_slice_bytes)
    output_capacity_bytes = int(out_i64.nbytes + out_f64.nbytes + out_stats.nbytes)
    immutable_bytes = int(cache["immutable_bytes"])
    input_preparation_seconds = time.perf_counter() - prep0
    allocation_count = int(9 + (0 if cache_hit else 6))

    buf = ctypes.create_string_buffer(512)
    call0 = time.perf_counter()
    rc = lib.xstar_matrix_eval_mg_ion_source_simple_payloads_batch(
        int(len(active_specs)), int(npfi_matrix.shape[1]), int(ptrs.shape[0]), int(rdat.size), int(idat.size), int(max_out),
        ion_indices, ion_records, ion_stages, nlevp,
        npfi_matrix.ravel(), npar, npnxt, ptrs.ravel(), rdat, idat,
        float(temperature_1e4k), float(electron_density_cm3),
        float(neutral_h_density_cm3), float(ionized_h_density_cm3),
        out_i64, out_f64, out_stats, buf, ctypes.sizeof(buf),
    )
    python_to_cpp_call_seconds = time.perf_counter() - call0
    message = buf.value.decode("utf-8", errors="replace")
    if rc != 0:
        raise RuntimeError(message or f"xstar_matrix_eval_mg_ion_source_simple_payloads_batch failed with code {rc}")

    unpack0 = time.perf_counter()
    emitted = int(out_stats[3])
    oi = out_i64[: emitted * 14].reshape((emitted, 14)) if emitted else np.empty((0, 14), dtype=np.int64)
    of = out_f64[: emitted * 6].reshape((emitted, 6)) if emitted else np.empty((0, 6), dtype=np.float64)
    rows: list[dict[str, Any]] = []
    for j in range(emitted):
        rows.append({
            "ion_ordinal": int(oi[j, 0]), "ion_index": int(oi[j, 1]), "ion_record": int(oi[j, 2]),
            "ion_stage": int(oi[j, 3]), "record": int(oi[j, 4]), "rate_type": int(oi[j, 5]),
            "data_type": int(oi[j, 6]), "data_type_chain": int(oi[j, 7]), "next_record": int(oi[j, 8]),
            "idest1": int(oi[j, 9]), "idest2": int(oi[j, 10]), "status_code": int(oi[j, 11]),
            "supported_mask": int(oi[j, 12]), "skip_mask": int(oi[j, 13]),
            "ans1": float(of[j, 0]), "ans2": float(of[j, 1]), "ans3": float(of[j, 2]),
            "ans4": float(of[j, 3]), "ans5": float(of[j, 4]), "ans6": float(of[j, 5]),
        })
    output_copy_commit_seconds = time.perf_counter() - unpack0
    output_emitted_bytes = int(emitted * (14 * 8 + 6 * 8))
    actual_bytes_copied = int(immutable_copy_bytes + evaluation_input_bytes + output_emitted_bytes)
    peak_working_set_bytes = int(immutable_bytes + evaluation_input_bytes + output_capacity_bytes)
    stats = {
        "batch_ion_count": float(out_stats[0]), "total_ion_count": float(len(ion_specs)),
        "zero_output_ions_skipped": float(zero_output_ions_skipped),
        "expected_supported_records": float(expected_supported_records),
        "expected_source_records": float(expected_source_records),
        "records_seen": float(out_stats[1]), "records_supported": float(out_stats[2]),
        "emitted_records": float(out_stats[3]), "cpp_calls": float(out_stats[4]),
        "input_preparation_seconds": float(input_preparation_seconds),
        "python_to_cpp_call_seconds": float(python_to_cpp_call_seconds),
        "cpp_kernel_compute_seconds": float(out_stats[15]) * 1.0e-9,
        "output_copy_commit_seconds": float(output_copy_commit_seconds),
        "support_index_seconds": float(support_index_seconds),
        "packing_seconds": float(input_preparation_seconds), "cpp_kernel_seconds": float(python_to_cpp_call_seconds),
        "cache_hits": float(1 if cache_hit else 0), "cache_misses": float(0 if cache_hit else 1),
        "support_index_hits": float(support_hits), "support_index_misses": float(support_misses),
        "immutable_cache_bytes": float(immutable_bytes), "immutable_copy_bytes": float(immutable_copy_bytes),
        "evaluation_input_bytes": float(evaluation_input_bytes),
        "compact_ion_metadata_bytes": float(compact_ion_metadata_bytes),
        "npfi_slice_bytes": float(npfi_slice_bytes),
        "source_index_entries": float(len(active_specs)),
        "output_capacity_bytes": float(output_capacity_bytes), "output_emitted_bytes": float(output_emitted_bytes),
        "actual_bytes_copied": float(actual_bytes_copied), "bytes_copied": float(actual_bytes_copied),
        "peak_working_set_bytes": float(peak_working_set_bytes), "allocation_count": float(allocation_count),
        "payload_length": float(emitted), "terms_processed": float(emitted),
        "records_processed": float(out_stats[1]), "source_records": float(out_stats[1]),
        "fallback_count": float(out_stats[12]),
        "output_overflow": float(out_stats[14]),
        "mg_ion_payload_type1_records": float(out_stats[5]), "mg_ion_payload_type2_records": float(out_stats[6]),
        "mg_ion_payload_type3_records": float(out_stats[7]), "mg_ion_payload_type7_records": float(out_stats[8]),
        "mg_ion_payload_type8_records": float(out_stats[9]), "mg_ion_payload_type20_records": float(out_stats[10]),
        "mg_ion_payload_skipped_records": float(out_stats[11]), "mg_ion_payload_loop_guard_hits": float(out_stats[13]),
    }
    return rows, message, stats

def accumulate_mg_ion_source_simple_terms_cpp_detailed(
    *,
    master: Any,
    derived: Any,
    ion_index: int,
    ion_stage: int,
    ion_record: int,
    compact_start: int,
    basis_n_rows: int,
    term_start: int,
    temperature_1e4k: float,
    electron_density_cm3: float,
    neutral_h_density_cm3: float,
    ionized_h_density_cm3: float,
    hydrogen_density_cm3: float,
    nlevp: int,
) -> tuple[list[dict[str, Any]], str, dict[str, float]]:
    """Experimental direct Mg-ion accumulator for selected simple payloads.

    C++ walks the Mg ion source-pointer chains, decodes selected simple
    payloads, evaluates their rates, and emits matrix terms directly.  This is
    opt-in until full benchmark parity and timing improvement are proven.
    """
    lib = _load_cpp_library()
    if lib is None or not hasattr(lib, "xstar_matrix_accumulate_mg_ion_source_simple_terms"):
        raise RuntimeError("C++ Mg ion direct simple-term accumulator is not available" + (f": {cpp_import_error()}" if cpp_import_error() else ""))
    t0 = time.perf_counter()
    npfi_all, npar, npnxt, ptrs, rdat, idat = _compact_matrix_arrays(master, derived)
    npfi = np.ascontiguousarray(npfi_all[:, int(ion_index)])
    n_records = int(ptrs.shape[0])
    # Bound output by this ion's source records, not by the whole ATDB.
    # This avoids the a9/a10 regression where every ion allocated buffers
    # sized as n_records * 4.
    source_count = 0
    for data_chain in range(1, int(npfi.size)):
        rec = int(npfi[data_chain])
        guard = 0
        while rec > 0 and rec <= n_records and int(npar[rec]) == int(ion_record):
            source_count += 1
            guard += 1
            if guard > n_records:
                break
            rec = int(npnxt[rec])
    max_terms = max(4, source_count * 4)
    out_i64 = np.zeros(max_terms * 16, dtype=np.int64)
    out_f64 = np.zeros(max_terms * 4, dtype=np.float64)
    out_stats = np.zeros(18, dtype=np.int64)
    packing_seconds = time.perf_counter() - t0
    buf = ctypes.create_string_buffer(512)
    k0 = time.perf_counter()
    rc = lib.xstar_matrix_accumulate_mg_ion_source_simple_terms(
        int(npfi.size), int(n_records), int(rdat.size), int(idat.size),
        int(basis_n_rows), int(term_start), int(max_terms),
        int(ion_index), int(ion_stage), int(ion_record), int(compact_start), int(nlevp),
        npfi, npar, npnxt, ptrs.ravel(), rdat, idat,
        float(temperature_1e4k), float(electron_density_cm3),
        float(neutral_h_density_cm3), float(ionized_h_density_cm3), float(hydrogen_density_cm3),
        out_i64, out_f64, out_stats, buf, ctypes.sizeof(buf),
    )
    cpp_kernel_seconds = time.perf_counter() - k0
    message = buf.value.decode("utf-8", errors="replace")
    if rc != 0:
        raise RuntimeError(message or f"xstar_matrix_accumulate_mg_ion_source_simple_terms failed with code {rc}")
    emitted_terms = int(out_stats[2])
    oi = out_i64[: emitted_terms * 16].reshape((emitted_terms, 16)) if emitted_terms else np.zeros((0, 16), dtype=np.int64)
    of = out_f64[: emitted_terms * 4].reshape((emitted_terms, 4)) if emitted_terms else np.zeros((0, 4), dtype=np.float64)
    rows: list[dict[str, Any]] = []
    for j in range(emitted_terms):
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
        "records_seen": float(out_stats[0]),
        "records_supported": float(out_stats[1]),
        "source_records_scanned_python": float(source_count),
        "direct_accum_max_terms": float(max_terms),
        "records_batched": float(out_stats[4]),
        "cpp_calls": float(out_stats[3]),
        "packing_seconds": float(packing_seconds),
        "cpp_kernel_seconds": float(cpp_kernel_seconds),
        "fallback_count": float(out_stats[12]),
        "ucalc_cpp_applied": float(out_stats[1]),
        "emitted_matrix_terms": float(sum(1 for r in rows if str(r.get("role")) not in {"scalar_pirt", "scalar_rrrt"})),
        "emitted_scalar_rows": float(sum(1 for r in rows if str(r.get("role")) in {"scalar_pirt", "scalar_rrrt"})),
        "mg_ion_direct_rate7_seen": float(out_stats[14]) if out_stats.size > 14 else 0.0,
        "mg_ion_direct_rate7_supported": float(out_stats[15]) if out_stats.size > 15 else 0.0,
        "mg_ion_direct_type1_records": float(out_stats[5]),
        "mg_ion_direct_type2_records": float(out_stats[6]),
        "mg_ion_direct_type3_records": float(out_stats[7]),
        "mg_ion_direct_type7_records": float(out_stats[8]),
        "mg_ion_direct_type8_records": float(out_stats[9]),
        "mg_ion_direct_type20_records": float(out_stats[10]),
        "mg_ion_direct_skipped_records": float(out_stats[11]),
        "mg_ion_direct_loop_guard_hits": float(out_stats[13]),
    }
    return rows, message, stats



def _radiation_grid_arrays_for_type49(radiation: Any) -> tuple[np.ndarray, np.ndarray]:
    """Return literal calc_hmc caller-owned reduced epim/bremsam arrays.

    These C++ bridge functions are matrix/rate accumulators used by
    calc_hmc_all, not calc_emis_all.  Literal XSTAR passes epim/ncn2m/bremsam
    here.  Full epi/bremsa remains owned by the later spectral emissivity pass.
    """
    for e_name, b_name in (("epim_eV", "bremsam"), ("epim", "bremsam")):
        if not hasattr(radiation, e_name) or not hasattr(radiation, b_name):
            continue
        try:
            epi = np.asarray(getattr(radiation, e_name), dtype=np.float64).reshape(-1)
            brem = np.asarray(getattr(radiation, b_name), dtype=np.float64).reshape(-1)
            if (epi.size >= 3 and brem.size >= epi.size and np.all(np.isfinite(epi))
                    and np.all(np.isfinite(brem[: epi.size])) and np.all(np.diff(epi) > 0.0)):
                return np.ascontiguousarray(epi), np.ascontiguousarray(brem[: epi.size])
        except Exception:
            continue
    # Development-fixture compatibility only: old fixtures may not expose
    # the reduced workspace.  Production/readiness gates require 999 bins.
    for e_name in ("epi_eV", "epi"):
        if hasattr(radiation, e_name):
            try:
                epi = np.asarray(getattr(radiation, e_name), dtype=np.float64).reshape(-1)
                if epi.size >= 3 and np.all(np.diff(epi) > 0.0):
                    break
            except Exception:
                continue
    else:
        epi = np.zeros(0, dtype=np.float64)
    brem = np.asarray(getattr(radiation, "bremsa", ()), dtype=np.float64).reshape(-1)
    if brem.size < epi.size:
        brem = np.zeros(int(epi.size), dtype=np.float64)
    return np.ascontiguousarray(epi), np.ascontiguousarray(brem[: epi.size])

def _radiation_extrap_max_points_for_type49(radiation: Any, full_grid_size: int) -> int:
    """Return Python ``phextrap`` capacity for type49/type53 shadow parity.

    Python evaluates type49 as ``phextrap(..., len(self._mapped_grid(c)))``;
    ``_mapped_grid`` uses the reduced ``epim`` grid even though phint53 later
    integrates on the full live ``epi`` grid.  The C++ shadow path must use the
    same extrapolation capacity; otherwise high-threshold records receive extra
    extrapolated cross-section points and pirt is too large.
    """
    try:
        epim = np.asarray(getattr(radiation, "epim_eV", getattr(radiation, "epim", ())), dtype=np.float64).reshape(-1)
        if epim.size >= 3 and np.all(np.isfinite(epim)) and np.all(np.diff(epim) > 0.0):
            return int(epim.size)
    except Exception:
        pass
    return int(full_grid_size)


def _radiation_grid_arrays_for_type53(radiation: Any) -> tuple[np.ndarray, np.ndarray]:
    """Return the calc_hmc reduced grid shared by Type49 and Type53 matrix rates."""
    return _radiation_grid_arrays_for_type49(radiation)


def accumulate_mg_ion_rate7_type49_terms_cpp_detailed(
    *,
    master: Any,
    derived: Any,
    levels: Any,
    radiation: Any,
    ion_index: int,
    ion_stage: int,
    compact_start: int,
    basis_n_rows: int,
    term_start: int,
    temperature_k: float,
    hydrogen_density_cm3: float,
    electron_fraction_xee: float,
    nlevp: int,
    candidates: list[tuple[int, float, float]],
) -> tuple[list[dict[str, Any]], str, dict[str, float]]:
    """Evaluate rate_type=7/data_type=49 Mg photoionization records in C++.

    The caller supplies one ion's candidate source records and continuum escape
    factors.  C++ decodes the packed type-49 payload, evaluates a phint53-like
    photoionization/Milne branch, and emits scalar plus matrix rows directly.
    """
    lib = _load_cpp_library()
    if lib is None or not hasattr(lib, "xstar_matrix_accumulate_mg_ion_rate7_type49_terms"):
        raise RuntimeError("C++ Mg type-49 direct accumulator is not available" + (f": {cpp_import_error()}" if cpp_import_error() else ""))
    if not candidates:
        return [], "no candidates", {"records_seen": 0.0, "records_supported": 0.0, "cpp_calls": 0.0}
    t0 = time.perf_counter()
    _npfi_all, _npar, _npnxt, ptrs, rdat, idat = _compact_matrix_arrays(master, derived)
    recs = np.ascontiguousarray([int(x[0]) for x in candidates], dtype=np.int64)
    ptmp1 = np.ascontiguousarray([float(x[1]) for x in candidates], dtype=np.float64)
    ptmp2 = np.ascontiguousarray([float(x[2]) for x in candidates], dtype=np.float64)
    nreal = np.ascontiguousarray([int(ptrs[int(r) - 1, 4]) for r in recs], dtype=np.int64)
    real_ptr = np.ascontiguousarray([int(ptrs[int(r) - 1, 7]) for r in recs], dtype=np.int64)
    nint = np.ascontiguousarray([int(ptrs[int(r) - 1, 5]) for r in recs], dtype=np.int64)
    int_ptr = np.ascontiguousarray([int(ptrs[int(r) - 1, 8]) for r in recs], dtype=np.int64)
    nlev = int(nlevp)
    # Preserve Python ucalc's leveltemp semantics for parent destinations.
    # Type-49/53 records can have idest2 > nlevp; Python looks up these
    # persistent higher leveltemp columns for the final electron-POV ans5/ans6
    # energy correction.  Passing only 1..nlevp made C++ silently fall back to
    # the continuum energy and produced correct ans1..ans4 but wrong cj2.
    max_level_index = nlev
    if len(recs):
        try:
            parent_offsets = [max(0, int(idat[int(int_ptr[j] + int(nint[j]) - 4) - 1])) for j in range(len(recs)) if int(nint[j]) >= 4]
            if parent_offsets:
                max_level_index = max(max_level_index, max(int(nlevp) + int(off) - 1 for off in parent_offsets))
        except Exception:
            max_level_index = nlev
    lev_energy = np.zeros(max_level_index + 1, dtype=np.float64)
    lev_weight = np.zeros(max_level_index + 1, dtype=np.float64)
    lev_ionpot = np.zeros(max_level_index + 1, dtype=np.float64)
    lev_cont = np.zeros(max_level_index + 1, dtype=np.float64)
    # Type49 does not use the explicit type53 excited-parent map.  v0.6.0a40
    # accidentally copied type53 parent-map counters into this scope without
    # defining _parent_energy/_parent_weight, causing every attempted type49
    # applied C++ batch to raise NameError and fall back to Python.
    for idx in range(1, max_level_index + 1):
        lev = levels.get(idx) if hasattr(levels, "get") else None
        if lev is not None:
            lev_energy[idx] = float(getattr(lev, "energy_ev", 0.0) or 0.0)
            lev_weight[idx] = float(getattr(lev, "statistical_weight", 0.0) or 0.0)
            lev_ionpot[idx] = float(getattr(lev, "ionization_potential_ev", 0.0) or 0.0)
            lev_cont[idx] = float(getattr(lev, "continuum_energy_ev", 0.0) or 0.0)
    epi, brem = _radiation_grid_arrays_for_type49(radiation)
    extrap_max_points = _radiation_extrap_max_points_for_type49(radiation, int(epi.size))
    max_terms = max(8, int(len(candidates)) * 5)
    out_i64 = np.zeros(max_terms * 16, dtype=np.int64)
    out_f64 = np.zeros(max_terms * 4, dtype=np.float64)
    out_stats = np.zeros(16, dtype=np.int64)
    packing_seconds = time.perf_counter() - t0
    buf = ctypes.create_string_buffer(512)
    k0 = time.perf_counter()
    rc = lib.xstar_matrix_accumulate_mg_ion_rate7_type49_terms(
        int(len(candidates)), int(rdat.size), int(idat.size), int(max_level_index + 1), int(epi.size), int(extrap_max_points),
        int(basis_n_rows), int(term_start), int(max_terms),
        int(ion_index), int(ion_stage), int(compact_start), int(nlevp),
        recs, nreal, real_ptr, nint, int_ptr, ptmp1, ptmp2,
        rdat, idat, lev_energy, lev_weight, lev_ionpot, lev_cont, epi, brem,
        float(temperature_k), float(hydrogen_density_cm3), float(electron_fraction_xee),
        out_i64, out_f64, out_stats, buf, ctypes.sizeof(buf),
    )
    cpp_kernel_seconds = time.perf_counter() - k0
    message = buf.value.decode("utf-8", errors="replace")
    if rc != 0:
        raise RuntimeError(message or f"xstar_matrix_accumulate_mg_ion_rate7_type49_terms failed with code {rc}")
    emitted = int(out_stats[2])
    oi = out_i64[: emitted * 16].reshape((emitted, 16)) if emitted else np.zeros((0, 16), dtype=np.int64)
    of = out_f64[: emitted * 4].reshape((emitted, 4)) if emitted else np.zeros((0, 4), dtype=np.float64)
    rows: list[dict[str, Any]] = []
    for j in range(emitted):
        rows.append({
            "term_index": int(oi[j, 0]), "record": int(oi[j, 1]), "data_type": int(oi[j, 2]), "rate_type": int(oi[j, 3]),
            "ion_index": int(oi[j, 4]), "ion_stage": int(oi[j, 5]), "role": _ROLE.get(int(oi[j, 6]), f"role_{int(oi[j, 6])}"),
            "row": int(oi[j, 7]), "column": int(oi[j, 8]), "idest1": int(oi[j, 9]), "idest2": int(oi[j, 10]),
            "lower_endpoint": int(oi[j, 11]), "upper_endpoint": int(oi[j, 12]),
            "source_row_unclamped": int(oi[j, 13]), "source_column_unclamped": int(oi[j, 14]), "source_ipmat_clamped": bool(int(oi[j, 15])),
            "ucalc_status": "evaluated", "aj1": float(of[j, 0]), "aj2": float(of[j, 1]), "cj": float(of[j, 2]), "cj2": float(of[j, 3]),
        })
    stats = {
        "records_seen": float(out_stats[0]), "records_supported": float(out_stats[1]), "records_batched": float(out_stats[1]),
        "cpp_calls": float(out_stats[3]), "emitted_matrix_terms": float(out_stats[4]), "emitted_scalar_rows": float(out_stats[5]),
        "type49_invalid": float(out_stats[6]), "type49_no_pairs": float(out_stats[7]), "type49_bad_context": float(out_stats[8]),
        "type49_outside_grid": float(out_stats[9]), "type49_output_overflow": float(out_stats[10]), "fallback_count": float(out_stats[11]),
        "packing_seconds": float(packing_seconds), "cpp_kernel_seconds": float(cpp_kernel_seconds),
        "ucalc_cpp_applied": float(out_stats[1]), "mg_ion_direct_rate7_type49_seen": float(out_stats[0]),
        "mg_ion_direct_rate7_type49_supported": float(out_stats[1]),
    }
    return rows, message, stats

def accumulate_mg_ion_rate7_type53_terms_cpp_detailed(
    *,
    master: Any,
    derived: Any,
    levels: Any,
    radiation: Any,
    ion_index: int,
    ion_stage: int,
    compact_start: int,
    basis_n_rows: int,
    term_start: int,
    temperature_k: float,
    hydrogen_density_cm3: float,
    electron_fraction_xee: float,
    nlevp: int,
    candidates: list[tuple[int, float, float]],
    context_extras: Mapping[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], str, dict[str, float]]:
    """Evaluate rate_type=7/data_type=53 Mg OP photoionization records in C++.

    The caller supplies one ion's candidate source records and continuum escape
    factors.  C++ decodes the packed type-53 payload, evaluates a phint53-like
    photoionization/Milne branch, and emits scalar plus matrix rows directly.
    """
    lib = _load_cpp_library()
    if lib is None or not hasattr(lib, "xstar_matrix_accumulate_mg_ion_rate7_type53_terms"):
        raise RuntimeError("C++ Mg type-53 direct accumulator is not available" + (f": {cpp_import_error()}" if cpp_import_error() else ""))
    if not candidates:
        return [], "no candidates", {"records_seen": 0.0, "records_supported": 0.0, "cpp_calls": 0.0}
    t0 = time.perf_counter()
    _npfi_all, _npar, _npnxt, ptrs, rdat, idat = _compact_matrix_arrays(master, derived)
    recs = np.ascontiguousarray([int(x[0]) for x in candidates], dtype=np.int64)
    ptmp1 = np.ascontiguousarray([float(x[1]) for x in candidates], dtype=np.float64)
    ptmp2 = np.ascontiguousarray([float(x[2]) for x in candidates], dtype=np.float64)
    nreal = np.ascontiguousarray([int(ptrs[int(r) - 1, 4]) for r in recs], dtype=np.int64)
    real_ptr = np.ascontiguousarray([int(ptrs[int(r) - 1, 7]) for r in recs], dtype=np.int64)
    nint = np.ascontiguousarray([int(ptrs[int(r) - 1, 5]) for r in recs], dtype=np.int64)
    int_ptr = np.ascontiguousarray([int(ptrs[int(r) - 1, 8]) for r in recs], dtype=np.int64)
    nlev = int(nlevp)
    # Preserve Python ucalc's leveltemp semantics for parent destinations.
    # Type-49/53 records can have idest2 > nlevp; Python looks up these
    # persistent higher leveltemp columns for the final electron-POV ans5/ans6
    # energy correction.  Passing only 1..nlevp made C++ silently fall back to
    # the continuum energy and produced correct ans1..ans4 but wrong cj2.
    max_level_index = nlev
    if len(recs):
        try:
            parent_offsets = [max(0, int(idat[int(int_ptr[j] + int(nint[j]) - 4) - 1])) for j in range(len(recs)) if int(nint[j]) >= 4]
            if parent_offsets:
                max_level_index = max(max_level_index, max(int(nlevp) + int(off) - 1 for off in parent_offsets))
        except Exception:
            max_level_index = nlev
    lev_energy = np.zeros(max_level_index + 1, dtype=np.float64)
    lev_weight = np.zeros(max_level_index + 1, dtype=np.float64)
    lev_ionpot = np.zeros(max_level_index + 1, dtype=np.float64)
    # For type53, this array is used by C++ as the excited-parent energy map
    # for destinations above nlevp.  Python type53 gets this from
    # context.extras["parent_level_energy_ev_by_destination"], not from the
    # mutable leveltemp workspace.
    lev_cont = np.zeros(max_level_index + 1, dtype=np.float64)
    _extras = dict(context_extras or {})
    _parent_energy = _extras.get("parent_level_energy_ev_by_destination", {})
    _parent_weight = _extras.get("parent_level_stat_weight_by_destination", {})
    parent_energy_entries_available = float(len(_parent_energy) if isinstance(_parent_energy, Mapping) else 0)
    parent_weight_entries_available = float(len(_parent_weight) if isinstance(_parent_weight, Mapping) else 0)
    parent_energy_entries_packed = 0.0
    parent_weight_entries_packed = 0.0

    def _map_lookup_number(mapping: Any, key: int) -> float | None:
        """Return numeric map value for integer/string destination keys.

        The parent-level maps are serialized through summary/provenance paths in
        some runs and can arrive with string keys.  v0.6.0a34 only checked the
        integer key, so the C++ type53 bridge still packed zero parent
        excitation and used the base threshold for idest2 > nlevp.
        """
        if not isinstance(mapping, Mapping):
            return None
        candidates = (key, str(key), float(key), f"{key}.0")
        for cand in candidates:
            try:
                if cand in mapping:
                    return float(mapping[cand] or 0.0)
            except Exception:
                continue
        return None

    for idx in range(1, max_level_index + 1):
        lev = levels.get(idx) if hasattr(levels, "get") else None
        if lev is not None:
            # leveltemp workspace energy; Python uses this for final destination
            # energy correction when present.
            lev_energy[idx] = float(getattr(lev, "energy_ev", 0.0) or 0.0)
            lev_weight[idx] = float(getattr(lev, "statistical_weight", 0.0) or 0.0)
            lev_ionpot[idx] = float(getattr(lev, "ionization_potential_ev", 0.0) or 0.0)
            lev_cont[idx] = float(getattr(lev, "continuum_energy_ev", 0.0) or 0.0)
        if idx > int(nlevp):
            parent_e = _map_lookup_number(_parent_energy, idx)
            if parent_e is not None:
                lev_cont[idx] = parent_e
                parent_energy_entries_packed += 1.0
            parent_g = _map_lookup_number(_parent_weight, idx)
            if parent_g is not None:
                lev_weight[idx] = parent_g
                parent_weight_entries_packed += 1.0
    epi, brem = _radiation_grid_arrays_for_type53(radiation)
    extrap_max_points = _radiation_extrap_max_points_for_type49(radiation, int(epi.size))
    max_terms = max(8, int(len(candidates)) * 5)
    out_i64 = np.zeros(max_terms * 16, dtype=np.int64)
    out_f64 = np.zeros(max_terms * 4, dtype=np.float64)
    # v0.6.0a32: per-emitted-row type53 debug intermediates.
    # Columns: threshold, rnist, sumr, sumi, sumh, sumh2, sumc, sumc2,
    # ans1..ans6, nb1_1based, klmax_1based.
    debug_stride = 16
    out_debug_f64 = np.zeros(max_terms * debug_stride, dtype=np.float64)
    out_stats = np.zeros(16, dtype=np.int64)
    packing_seconds = time.perf_counter() - t0
    buf = ctypes.create_string_buffer(512)
    k0 = time.perf_counter()
    rc = lib.xstar_matrix_accumulate_mg_ion_rate7_type53_terms(
        int(len(candidates)), int(rdat.size), int(idat.size), int(max_level_index + 1), int(epi.size), int(extrap_max_points),
        int(basis_n_rows), int(term_start), int(max_terms),
        int(ion_index), int(ion_stage), int(compact_start), int(nlevp),
        recs, nreal, real_ptr, nint, int_ptr, ptmp1, ptmp2,
        rdat, idat, lev_energy, lev_weight, lev_ionpot, lev_cont, epi, brem,
        float(temperature_k), float(hydrogen_density_cm3), float(electron_fraction_xee),
        out_i64, out_f64, out_stats, out_debug_f64, int(debug_stride), buf, ctypes.sizeof(buf),
    )
    cpp_kernel_seconds = time.perf_counter() - k0
    message = buf.value.decode("utf-8", errors="replace")
    if rc != 0:
        raise RuntimeError(message or f"xstar_matrix_accumulate_mg_ion_rate7_type53_terms failed with code {rc}")
    emitted = int(out_stats[2])
    oi = out_i64[: emitted * 16].reshape((emitted, 16)) if emitted else np.zeros((0, 16), dtype=np.int64)
    of = out_f64[: emitted * 4].reshape((emitted, 4)) if emitted else np.zeros((0, 4), dtype=np.float64)
    od = out_debug_f64[: emitted * debug_stride].reshape((emitted, debug_stride)) if emitted else np.zeros((0, debug_stride), dtype=np.float64)
    debug_names = (
        "cpp_threshold_eV", "cpp_rnist", "cpp_sumr", "cpp_sumi", "cpp_sumh", "cpp_sumh2", "cpp_sumc", "cpp_sumc2",
        "cpp_ans1", "cpp_ans2", "cpp_ans3", "cpp_ans4", "cpp_ans5", "cpp_ans6", "cpp_nb1_1based", "cpp_klmax_1based",
    )
    rows: list[dict[str, Any]] = []
    for j in range(emitted):
        _debug = {debug_names[k]: float(od[j, k]) for k in range(min(debug_stride, len(debug_names)))}
        rows.append({
            "term_index": int(oi[j, 0]), "record": int(oi[j, 1]), "data_type": int(oi[j, 2]), "rate_type": int(oi[j, 3]),
            "ion_index": int(oi[j, 4]), "ion_stage": int(oi[j, 5]), "role": _ROLE.get(int(oi[j, 6]), f"role_{int(oi[j, 6])}"),
            "row": int(oi[j, 7]), "column": int(oi[j, 8]), "idest1": int(oi[j, 9]), "idest2": int(oi[j, 10]),
            "lower_endpoint": int(oi[j, 11]), "upper_endpoint": int(oi[j, 12]),
            "source_row_unclamped": int(oi[j, 13]), "source_column_unclamped": int(oi[j, 14]), "source_ipmat_clamped": bool(int(oi[j, 15])),
            "ucalc_status": "evaluated", "aj1": float(of[j, 0]), "aj2": float(of[j, 1]), "cj": float(of[j, 2]), "cj2": float(of[j, 3]),
            **_debug,
        })
    stats = {
        "records_seen": float(out_stats[0]), "records_supported": float(out_stats[1]), "records_batched": float(out_stats[1]),
        "cpp_calls": float(out_stats[3]), "emitted_matrix_terms": float(out_stats[4]), "emitted_scalar_rows": float(out_stats[5]),
        "type53_invalid": float(out_stats[6]), "type53_no_pairs": float(out_stats[7]), "type53_bad_context": float(out_stats[8]),
        "type53_outside_grid": float(out_stats[9]), "type53_output_overflow": float(out_stats[10]), "fallback_count": float(out_stats[11]),
        "parent_energy_entries_available": float(parent_energy_entries_available),
        "parent_weight_entries_available": float(parent_weight_entries_available),
        "parent_energy_entries_packed": float(parent_energy_entries_packed),
        "parent_weight_entries_packed": float(parent_weight_entries_packed),
        "packing_seconds": float(packing_seconds), "cpp_kernel_seconds": float(cpp_kernel_seconds),
        "ucalc_cpp_applied": float(out_stats[1]), "mg_ion_direct_rate7_type53_seen": float(out_stats[0]),
        "mg_ion_direct_rate7_type53_supported": float(out_stats[1]),
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
