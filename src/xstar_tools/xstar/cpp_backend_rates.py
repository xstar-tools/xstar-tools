# XSTAR-PYTHON-SOURCE-CORRESPONDENCE-BEGIN
# Source correspondence:
#   Fortran: ucalc.f90 / calc_hmc_ion.f90
#   Role: Python/native bridge for low-level rate evaluation and packed record exchange.
#   Relation: Bridge layer over source-equivalent C++ rate kernels.
#   Concordance: MATRIX-001; ION-001
#   Qualification: accepted science revision 0.6.48.12.3.45.3.3.8; frozen C++ baseline 0.6.48.12.3.44.
# Atomic-data note (XSTAR Manual Ch. 12; Mendoza et al. 2021, Appendix A):
#   Rule: data type selects the record formula/interpretation; rate type selects downstream use.
#   Preserve data_type and rate_type independently in native payloads: formula selection and downstream
#   rate ownership are distinct ATDB fields.
# XSTAR-PYTHON-SOURCE-CORRESPONDENCE-END

"""Optional C++ rates backend loader.

This module intentionally exposes only a small status/probe interface in
v0.5.54 adds a conservative Mg record_type=7 batch kernel.  The
source-faithful Python ucalc formulas still produce ans1..ans6; this module can
then ask C++ to build the repeated calc_hmc_ion matrix/rate terms from compact
arrays.  Keeping the ABI as a plain C interface makes the same C++ source usable
from Python, hydrodynamic post-processing workflows, and a future standalone
xstar_tools executable.
"""
from __future__ import annotations

import ctypes
from dataclasses import dataclass, asdict
import os
import time
from pathlib import Path
from typing import Any

import numpy as np

from xstar_tools.native_runtime import native_library_candidates, prepare_native_library_search


@dataclass(frozen=True)
class RatesBackendStatus:
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


_CPP_LIB: ctypes.CDLL | None = None
_CPP_LOAD_ERROR: BaseException | None = None
_CPP_LIBRARY_PATH: str | None = None


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the candidate library paths operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: Backend adapter/provenance helper; the underlying scientific routine is documented in the corresponding XSTAR Manual section.
# XSTAR-FUNCTION-COMMENT-END
def _candidate_library_paths() -> list[Path]:
    return native_library_candidates(
        "xstar_rates",
        env_var="XSTAR_ATOMIC_RATES_LIB",
        compatibility_names=("xstar_rates.so", "xstar_rates.dll"),
    )


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Load cpp library for this module while preserving the surrounding source/runtime invariants.
# Reference context: Backend adapter/provenance helper; the underlying scientific routine is documented in the corresponding XSTAR Manual section.
# XSTAR-FUNCTION-COMMENT-END
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
            prepare_native_library_search(path)
            lib = ctypes.CDLL(str(path))
            lib.xstar_rates_abi_version.argtypes = []
            lib.xstar_rates_abi_version.restype = ctypes.c_int
            lib.xstar_rates_backend_name.argtypes = []
            lib.xstar_rates_backend_name.restype = ctypes.c_char_p
            lib.xstar_rates_feature_flags.argtypes = []
            lib.xstar_rates_feature_flags.restype = ctypes.c_int
            lib.xstar_rates_eval_mg.argtypes = [
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_void_p,
                ctypes.c_size_t,
                ctypes.c_char_p,
                ctypes.c_size_t,
            ]
            lib.xstar_rates_eval_mg.restype = ctypes.c_int
            i64p = np.ctypeslib.ndpointer(dtype=np.int64, ndim=1, flags="C_CONTIGUOUS")
            f64p = np.ctypeslib.ndpointer(dtype=np.float64, ndim=1, flags="C_CONTIGUOUS")
            lib.xstar_rates_build_mg_type7_terms.argtypes = [
                ctypes.c_int, ctypes.c_int, ctypes.c_int,
                i64p, i64p, i64p, i64p, i64p, i64p, i64p,
                f64p, f64p, f64p, f64p, f64p, f64p,
                ctypes.c_double,
                i64p, f64p,
                ctypes.c_char_p, ctypes.c_size_t,
            ]
            lib.xstar_rates_build_mg_type7_terms.restype = ctypes.c_int
            try:
                lib.xstar_rates_build_mg_type4_line_emissivity.argtypes = [
                    ctypes.c_int,
                    i64p, i64p, i64p, i64p, i64p, i64p,
                    f64p, f64p, f64p, f64p, f64p, f64p, f64p, f64p, f64p,
                    ctypes.c_double,
                    i64p, f64p,
                    ctypes.c_char_p, ctypes.c_size_t,
                ]
                lib.xstar_rates_build_mg_type4_line_emissivity.restype = ctypes.c_int
            except AttributeError:
                # Older v0.5.54-v0.5.57 libraries do not expose the line-emissivity kernel.
                pass
            try:
                lib.xstar_rates_apply_linopac_profile.argtypes = [
                    ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double,
                    ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double,
                    f64p, ctypes.c_int, f64p, ctypes.c_int, f64p, f64p, i64p, f64p,
                    ctypes.c_char_p, ctypes.c_size_t,
                ]
                lib.xstar_rates_apply_linopac_profile.restype = ctypes.c_int
            except AttributeError:
                # Older libraries do not expose the C++ linopac side-effect kernel.
                pass
            try:
                lib.xstar_rates_apply_mg_type4_type50_coarse.argtypes = [
                    ctypes.c_int,
                    i64p, i64p, i64p, i64p, i64p, i64p,
                    f64p, f64p, f64p, f64p, f64p, f64p, f64p, f64p, f64p, f64p, f64p,
                    ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double,
                    f64p, f64p, ctypes.c_int, f64p, ctypes.c_int, f64p, f64p, f64p, ctypes.c_int, f64p, ctypes.c_int, f64p,
                    i64p, f64p, ctypes.c_char_p, ctypes.c_size_t,
                ]
                lib.xstar_rates_apply_mg_type4_type50_coarse.restype = ctypes.c_int
            except AttributeError:
                # Older libraries do not expose the coarse selected type-50 backend.
                pass
            _CPP_LIB = lib
            _CPP_LIBRARY_PATH = str(path)
            return _CPP_LIB
        raise FileNotFoundError("no xstar_rates shared library found; attempted: " + "; ".join(attempted))
    except BaseException as exc:  # pragma: no cover - optional shared library
        _CPP_LOAD_ERROR = exc
        return None


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the cpp import error operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: Backend adapter/provenance helper; the underlying scientific routine is documented in the corresponding XSTAR Manual section.
# XSTAR-FUNCTION-COMMENT-END
def cpp_import_error() -> str | None:
    if _CPP_LOAD_ERROR is None:
        return None
    return f"{type(_CPP_LOAD_ERROR).__name__}: {_CPP_LOAD_ERROR}"


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the backend name operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: Backend adapter/provenance helper; the underlying scientific routine is documented in the corresponding XSTAR Manual section.
# XSTAR-FUNCTION-COMMENT-END
def _backend_name(lib: ctypes.CDLL | None) -> str | None:
    if lib is None:
        return None
    try:
        raw = lib.xstar_rates_backend_name()
        return raw.decode("ascii", errors="replace") if raw else None
    except Exception:
        return None


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the abi version operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: Backend adapter/provenance helper; the underlying scientific routine is documented in the corresponding XSTAR Manual section.
# XSTAR-FUNCTION-COMMENT-END
def _abi_version(lib: ctypes.CDLL | None) -> int | None:
    if lib is None:
        return None
    try:
        return int(lib.xstar_rates_abi_version())
    except Exception:
        return None


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the feature flags operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: Backend adapter/provenance helper; the underlying scientific routine is documented in the corresponding XSTAR Manual section.
# XSTAR-FUNCTION-COMMENT-END
def _feature_flags(lib: ctypes.CDLL | None) -> int | None:
    if lib is None:
        return None
    try:
        return int(lib.xstar_rates_feature_flags())
    except Exception:
        return None


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the rates backend status operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: Backend adapter/provenance helper; the underlying scientific routine is documented in the corresponding XSTAR Manual section.
# XSTAR-FUNCTION-COMMENT-END
def rates_backend_status(requested: str | None = None) -> RatesBackendStatus:
    req = (requested or os.environ.get("XSTAR_ATOMIC_RATES_BACKEND") or "python").strip().lower()
    if req not in {"python", "cpp", "auto"}:
        req = "python"
    lib = _load_cpp_library()
    if req == "python":
        active = "python"
    elif req == "cpp":
        active = "cpp" if lib is not None else "unavailable"
    else:
        active = "cpp" if lib is not None else "python"
    return RatesBackendStatus(
        requested=req,
        active=active,
        cpp_available=lib is not None,
        cpp_import_error=cpp_import_error(),
        cpp_library_path=_CPP_LIBRARY_PATH,
        cpp_backend_name=_backend_name(lib),
        cpp_abi_version=_abi_version(lib),
        cpp_feature_flags=_feature_flags(lib),
    )


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the probe cpp mg rates operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: Backend adapter/provenance helper; the underlying scientific routine is documented in the corresponding XSTAR Manual section.
# XSTAR-FUNCTION-COMMENT-END
def probe_cpp_mg_rates(*, n_ions: int = 0, n_records: int = 0) -> str:
    """Call the v0.5.53 skeleton Mg rates entry point.

    This is a build/ABI smoke probe only.  It does not compute physics yet.
    """
    lib = _load_cpp_library()
    if lib is None:
        raise RuntimeError("C++ rates shared library is not available" + (f": {cpp_import_error()}" if cpp_import_error() else ""))
    errbuf = ctypes.create_string_buffer(512)
    rc = lib.xstar_rates_eval_mg(
        ctypes.c_int(int(n_ions)),
        ctypes.c_int(int(n_records)),
        None,
        ctypes.c_size_t(0),
        errbuf,
        ctypes.c_size_t(len(errbuf)),
    )
    message = errbuf.value.decode("utf-8", errors="replace")
    if rc != 0:
        raise RuntimeError(message or f"xstar_rates_eval_mg failed with code {rc}")
    return message


_ROLE_BY_CODE = {
    1: "forward_offdiag",
    2: "reverse_offdiag",
    3: "forward_diag_loss",
    4: "reverse_diag_loss",
}


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Build mg type7 terms cpp detailed for this module while preserving the surrounding source/runtime invariants.
# Reference context: Backend adapter/provenance helper; the underlying scientific routine is documented in the corresponding XSTAR Manual section.
# XSTAR-FUNCTION-COMMENT-END
def build_mg_type7_terms_cpp_detailed(
    records: list[dict[str, Any]],
    *,
    basis_n_rows: int,
    term_start: int,
    hydrogen_density_cm3: float,
) -> tuple[list[dict[str, Any]], str, dict[str, float]]:
    """Build Mg record_type=7 matrix terms with the C++ rates backend.

    The input records must already contain source-faithful Python ``ucalc``
    results for a single compact Mg ion block, including ans1..ans6, idest1,
    idest2, compact_start, ion_index, and ion_stage.  C++ owns the repeated
    calc_hmc_ion four-term construction and endpoint clamping.  It returns
    dictionaries that map directly onto ``MatrixTerm`` fields, leaving physics
    formulas in the Python reference path until the next parity milestone.
    """
    if not records:
        return [], "no_records", {"records_batched": 0.0, "cpp_calls": 0.0, "packing_seconds": 0.0, "cpp_kernel_seconds": 0.0, "fallback_count": 0.0, "emitted_matrix_terms": 0.0}
    lib = _load_cpp_library()
    if lib is None:
        raise RuntimeError("C++ rates shared library is not available" + (f": {cpp_import_error()}" if cpp_import_error() else ""))

    n = len(records)
    packing_t0 = time.perf_counter()
    # XSTAR-FUNCTION-COMMENT-BEGIN
    # Purpose: Implement the i64 operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
    # Reference context: Backend adapter/provenance helper; the underlying scientific routine is documented in the corresponding XSTAR Manual section.
    # XSTAR-FUNCTION-COMMENT-END
    def i64(name: str) -> np.ndarray:
        return np.ascontiguousarray([int(r[name]) for r in records], dtype=np.int64)
    # XSTAR-FUNCTION-COMMENT-BEGIN
    # Purpose: Implement the f64 operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
    # Reference context: Backend adapter/provenance helper; the underlying scientific routine is documented in the corresponding XSTAR Manual section.
    # XSTAR-FUNCTION-COMMENT-END
    def f64(name: str) -> np.ndarray:
        return np.ascontiguousarray([float(r[name]) for r in records], dtype=np.float64)

    record_arr = i64("record")
    data_type_arr = i64("data_type")
    ion_index_arr = i64("ion_index")
    ion_stage_arr = i64("ion_stage")
    compact_start_arr = i64("compact_start")
    idest1_arr = i64("idest1")
    idest2_arr = i64("idest2")
    ans1_arr = f64("ans1")
    ans2_arr = f64("ans2")
    ans3_arr = f64("ans3")
    ans4_arr = f64("ans4")
    ans5_arr = f64("ans5")
    ans6_arr = f64("ans6")
    out_i64 = np.zeros(n * 4 * 16, dtype=np.int64)
    out_f64 = np.zeros(n * 4 * 4, dtype=np.float64)
    packing_seconds = time.perf_counter() - packing_t0
    errbuf = ctypes.create_string_buffer(512)
    cpp_t0 = time.perf_counter()
    rc = lib.xstar_rates_build_mg_type7_terms(
        ctypes.c_int(n),
        ctypes.c_int(int(basis_n_rows)),
        ctypes.c_int(int(term_start)),
        record_arr, data_type_arr, ion_index_arr, ion_stage_arr, compact_start_arr,
        idest1_arr, idest2_arr,
        ans1_arr, ans2_arr, ans3_arr, ans4_arr, ans5_arr, ans6_arr,
        ctypes.c_double(float(hydrogen_density_cm3)),
        out_i64, out_f64,
        errbuf, ctypes.c_size_t(len(errbuf)),
    )
    cpp_kernel_seconds = time.perf_counter() - cpp_t0
    message = errbuf.value.decode("utf-8", errors="replace")
    if rc != 0:
        raise RuntimeError(message or f"xstar_rates_build_mg_type7_terms failed with code {rc}")

    ints = out_i64.reshape((n * 4, 16))
    floats = out_f64.reshape((n * 4, 4))
    terms: list[dict[str, Any]] = []
    for row_i, row_f in zip(ints, floats):
        role_code = int(row_i[6])
        terms.append({
            "term_index": int(row_i[0]),
            "record": int(row_i[1]),
            "data_type": int(row_i[2]),
            "rate_type": int(row_i[3]),
            "ion_index": int(row_i[4]),
            "ion_stage": int(row_i[5]),
            "role": _ROLE_BY_CODE.get(role_code, f"role_{role_code}"),
            "row": int(row_i[7]),
            "column": int(row_i[8]),
            "idest1": int(row_i[9]),
            "idest2": int(row_i[10]),
            "lower_endpoint": int(row_i[11]),
            "upper_endpoint": int(row_i[12]),
            "source_row_unclamped": int(row_i[13]),
            "source_column_unclamped": int(row_i[14]),
            "source_ipmat_clamped": bool(int(row_i[15])),
            "aj1": float(row_f[0]),
            "aj2": float(row_f[1]),
            "cj": float(row_f[2]),
            "cj2": float(row_f[3]),
            "ucalc_status": "evaluated",
        })
    stats = {
        "records_batched": float(n),
        "cpp_calls": 1.0,
        "packing_seconds": float(packing_seconds),
        "cpp_kernel_seconds": float(cpp_kernel_seconds),
        "fallback_count": 0.0,
        "emitted_matrix_terms": float(len(terms)),
    }
    return terms, message, stats


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Build mg type7 terms cpp for this module while preserving the surrounding source/runtime invariants.
# Reference context: Backend adapter/provenance helper; the underlying scientific routine is documented in the corresponding XSTAR Manual section.
# XSTAR-FUNCTION-COMMENT-END
def build_mg_type7_terms_cpp(
    records: list[dict[str, Any]],
    *,
    basis_n_rows: int,
    term_start: int,
    hydrogen_density_cm3: float,
) -> tuple[list[dict[str, Any]], str]:
    terms, message, _stats = build_mg_type7_terms_cpp_detailed(
        records,
        basis_n_rows=basis_n_rows,
        term_start=term_start,
        hydrogen_density_cm3=hydrogen_density_cm3,
    )
    return terms, message



# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Build mg type4 line emissivity cpp detailed for this module while preserving the surrounding source/runtime invariants.
# Reference context: Backend adapter/provenance helper; the underlying scientific routine is documented in the corresponding XSTAR Manual section.
# XSTAR-FUNCTION-COMMENT-END
def build_mg_type4_line_emissivity_cpp_detailed(
    records: list[dict[str, Any]],
    *,
    erg_per_ev: float,
) -> tuple[list[dict[str, Any]], str, dict[str, float]]:
    """Build Mg record_type=4 line-emissivity scalar products in C++.

    Python still evaluates source-faithful ``ucalc`` and applies the linopac
    side effects.  v0.5.59 batches contiguous Mg type-4 records before this backend owns the repeated scalar arithmetic
    after ``ucalc`` for ranked Mg line records and returns values that map
    directly to fline/flinel/oplin inputs.
    """
    if not records:
        return [], "no_records", {
            "records_batched": 0.0,
            "cpp_calls": 0.0,
            "packing_seconds": 0.0,
            "cpp_kernel_seconds": 0.0,
            "fallback_count": 0.0,
            "emitted_matrix_terms": 0.0,
        }
    lib = _load_cpp_library()
    if lib is None:
        raise RuntimeError("C++ rates shared library is not available" + (f": {cpp_import_error()}" if cpp_import_error() else ""))
    if not hasattr(lib, "xstar_rates_build_mg_type4_line_emissivity"):
        raise RuntimeError("C++ rates shared library does not expose xstar_rates_build_mg_type4_line_emissivity")

    n = len(records)
    packing_t0 = time.perf_counter()

    # XSTAR-FUNCTION-COMMENT-BEGIN
    # Purpose: Implement the i64 operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
    # Reference context: Backend adapter/provenance helper; the underlying scientific routine is documented in the corresponding XSTAR Manual section.
    # XSTAR-FUNCTION-COMMENT-END
    def i64(name: str) -> np.ndarray:
        return np.ascontiguousarray([int(r[name]) for r in records], dtype=np.int64)

    # XSTAR-FUNCTION-COMMENT-BEGIN
    # Purpose: Implement the f64 operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
    # Reference context: Backend adapter/provenance helper; the underlying scientific routine is documented in the corresponding XSTAR Manual section.
    # XSTAR-FUNCTION-COMMENT-END
    def f64(name: str) -> np.ndarray:
        return np.ascontiguousarray([float(r[name]) for r in records], dtype=np.float64)

    record_arr = i64("record")
    data_type_arr = i64("data_type")
    ion_index_arr = i64("ion_index")
    ion_stage_arr = i64("ion_stage")
    line_index_arr = i64("line_index")
    nb1_arr = i64("nb1")
    ans1_arr = f64("ans1")
    ans2_arr = f64("ans2")
    opakab_arr = f64("opakab")
    abund1_arr = f64("abund1")
    abund2_arr = f64("abund2")
    ptmp1_arr = f64("ptmp1")
    ptmp2_arr = f64("ptmp2")
    energy_arr = f64("energy_ev")
    width_arr = f64("bin_width_ev")
    out_i64 = np.zeros(n * 8, dtype=np.int64)
    out_f64 = np.zeros(n * 5, dtype=np.float64)
    packing_seconds = time.perf_counter() - packing_t0

    errbuf = ctypes.create_string_buffer(512)
    cpp_t0 = time.perf_counter()
    rc = lib.xstar_rates_build_mg_type4_line_emissivity(
        ctypes.c_int(n),
        record_arr, data_type_arr, ion_index_arr, ion_stage_arr, line_index_arr, nb1_arr,
        ans1_arr, ans2_arr, opakab_arr, abund1_arr, abund2_arr, ptmp1_arr, ptmp2_arr,
        energy_arr, width_arr,
        ctypes.c_double(float(erg_per_ev)),
        out_i64, out_f64,
        errbuf, ctypes.c_size_t(len(errbuf)),
    )
    cpp_kernel_seconds = time.perf_counter() - cpp_t0
    message = errbuf.value.decode("utf-8", errors="replace")
    if rc != 0:
        raise RuntimeError(message or f"xstar_rates_build_mg_type4_line_emissivity failed with code {rc}")

    ints = out_i64.reshape((n, 8))
    floats = out_f64.reshape((n, 5))
    rows: list[dict[str, Any]] = []
    for row_i, row_f in zip(ints, floats):
        rows.append({
            "record": int(row_i[0]),
            "data_type": int(row_i[1]),
            "rate_type": int(row_i[2]),
            "ion_index": int(row_i[3]),
            "ion_stage": int(row_i[4]),
            "line_index": int(row_i[5]),
            "nb1": int(row_i[6]),
            "status_code": int(row_i[7]),
            "opakb1": float(row_f[0]),
            "net": float(row_f[1]),
            "rcem1": float(row_f[2]),
            "rcem2": float(row_f[3]),
            "flinel_delta": float(row_f[4]),
        })
    stats = {
        "records_batched": float(n),
        "cpp_calls": 1.0,
        "packing_seconds": float(packing_seconds),
        "cpp_kernel_seconds": float(cpp_kernel_seconds),
        "fallback_count": 0.0,
        "emitted_matrix_terms": 0.0,
    }
    return rows, message, stats



# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Apply mg type4 type50 coarse cpp detailed for this module while preserving the surrounding source/runtime invariants.
# Reference context: Backend adapter/provenance helper; the underlying scientific routine is documented in the corresponding XSTAR Manual section.
# XSTAR-FUNCTION-COMMENT-END
def apply_mg_type4_type50_coarse_cpp_detailed(
    records: list[dict[str, Any]],
    *,
    cfrac: float,
    hydrogen_density_cm3: float,
    turbulent_velocity_km_s: float,
    temperature_1e4K: float,
    atomic_mass_amu: float,
    erg_per_ev: float,
    epi: np.ndarray,
    opakc: np.ndarray,
    rccemis: np.ndarray,
    oplin: np.ndarray,
    fline: np.ndarray,
    flinel: np.ndarray,
) -> tuple[list[dict[str, Any]], str, dict[str, float]]:
    """Apply selected Mg type-4/data_type=50 ucalc+linopac+array updates in C++.

    This is the first coarse per-ion/per-zone style line-emissivity backend: the
    C++ call evaluates the selected type-50 ucalc branch and updates the live
    opacity/emissivity arrays for all records in the batch.  Per-row status
    values allow Python to replay unsupported records through the source path.
    """
    if not records:
        return [], "no_records", {"records_batched": 0.0, "cpp_calls": 0.0, "packing_seconds": 0.0, "cpp_kernel_seconds": 0.0, "fallback_count": 0.0}
    lib = _load_cpp_library()
    if lib is None:
        raise RuntimeError("C++ rates shared library is not available" + (f": {cpp_import_error()}" if cpp_import_error() else ""))
    if not hasattr(lib, "xstar_rates_apply_mg_type4_type50_coarse"):
        raise RuntimeError("C++ rates shared library does not expose xstar_rates_apply_mg_type4_type50_coarse")
    n = len(records)
    packing_t0 = time.perf_counter()
    # XSTAR-FUNCTION-COMMENT-BEGIN
    # Purpose: Implement the i64 operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
    # Reference context: Backend adapter/provenance helper; the underlying scientific routine is documented in the corresponding XSTAR Manual section.
    # XSTAR-FUNCTION-COMMENT-END
    def i64(name: str) -> np.ndarray:
        return np.ascontiguousarray([int(r[name]) for r in records], dtype=np.int64)
    # XSTAR-FUNCTION-COMMENT-BEGIN
    # Purpose: Implement the f64 operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
    # Reference context: Backend adapter/provenance helper; the underlying scientific routine is documented in the corresponding XSTAR Manual section.
    # XSTAR-FUNCTION-COMMENT-END
    def f64(name: str) -> np.ndarray:
        return np.ascontiguousarray([float(r[name]) for r in records], dtype=np.float64)
    record_arr=i64("record"); data_type_arr=i64("data_type"); ion_index_arr=i64("ion_index"); ion_stage_arr=i64("ion_stage"); line_index_arr=i64("line_index"); nb1_arr=i64("nb1")
    wavelength_arr=f64("wavelength_A"); aij_arr=f64("aij_s"); gu_arr=f64("source_upper_weight"); gl_arr=f64("source_lower_weight"); endpoint_arr=f64("endpoint_energy_ev")
    bremsa_arr=f64("bremsa_nb1"); ptmp1_arr=f64("ptmp1"); ptmp2_arr=f64("ptmp2"); abund1_arr=f64("abund1"); abund2_arr=f64("abund2"); width_arr=f64("bin_width_ev"); natural_arr=f64("natural_width_ev")
    seed_radius=10
    seed_profile_arr=np.ascontiguousarray(
        np.asarray([r["linopac_seed_profiles"] for r in records], dtype=np.float64).reshape(-1)
    )
    epi_arr=np.ascontiguousarray(epi, dtype=np.float64)
    opakc_arr=np.asarray(opakc, dtype=np.float64); rcc_arr=np.asarray(rccemis, dtype=np.float64); oplin_arr=np.asarray(oplin, dtype=np.float64)
    fline_arr=np.asarray(fline, dtype=np.float64); flinel_arr=np.asarray(flinel, dtype=np.float64)
    if not (opakc_arr.flags.c_contiguous and rcc_arr.flags.c_contiguous and oplin_arr.flags.c_contiguous and fline_arr.flags.c_contiguous and flinel_arr.flags.c_contiguous):
        raise RuntimeError("coarse type50 C++ arrays must be C-contiguous")
    out_i64=np.zeros(n*12, dtype=np.int64); out_f64=np.zeros(n*12, dtype=np.float64)
    packing_seconds=time.perf_counter()-packing_t0
    errbuf=ctypes.create_string_buffer(512)
    cpp_t0=time.perf_counter()
    rc=lib.xstar_rates_apply_mg_type4_type50_coarse(
        ctypes.c_int(n), record_arr, data_type_arr, ion_index_arr, ion_stage_arr, line_index_arr, nb1_arr,
        wavelength_arr, aij_arr, gu_arr, gl_arr, endpoint_arr, bremsa_arr, ptmp1_arr, ptmp2_arr, abund1_arr, abund2_arr, width_arr,
        ctypes.c_double(float(cfrac)), ctypes.c_double(float(hydrogen_density_cm3)), ctypes.c_double(float(turbulent_velocity_km_s)),
        ctypes.c_double(float(temperature_1e4K)), ctypes.c_double(float(atomic_mass_amu)), ctypes.c_double(float(erg_per_ev)),
        natural_arr, seed_profile_arr, ctypes.c_int(seed_radius),
        epi_arr, ctypes.c_int(int(epi_arr.size)), opakc_arr, rcc_arr.reshape(-1), oplin_arr, ctypes.c_int(int(oplin_arr.size)),
        fline_arr.reshape(-1), ctypes.c_int(int(fline_arr.shape[1] if fline_arr.ndim == 2 else max(1, oplin_arr.size))), flinel_arr,
        out_i64, out_f64, errbuf, ctypes.c_size_t(len(errbuf)))
    cpp_kernel_seconds=time.perf_counter()-cpp_t0
    message=errbuf.value.decode("utf-8", errors="replace")
    if rc != 0:
        raise RuntimeError(message or f"xstar_rates_apply_mg_type4_type50_coarse failed with code {rc}")
    ints=out_i64.reshape((n,12)); floats=out_f64.reshape((n,12))
    # XSTAR-FUNCTION-COMMENT-BEGIN
    # Purpose: Implement the status reason operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
    # Reference context: Backend adapter/provenance helper; the underlying scientific routine is documented in the corresponding XSTAR Manual section.
    # XSTAR-FUNCTION-COMMENT-END
    def _status_reason(code: int) -> str:
        return {
            1: "full_cpp_applied",
            2: "linopac_voigt_python_fallback",
            -50: "unsupported_data_type",
            -6: "linopac_cpp_failure",
            -1: "invalid_or_nonfinite_input",
        }.get(int(code), f"status_{int(code)}")

    rows=[]; applied=0; full_applied=0; hybrid_applied=0; fallback=0; lin_bins=0
    reason_counts: dict[str, float] = {}
    for row_i,row_f in zip(ints,floats):
        status=int(row_i[7])
        reason = _status_reason(status)
        reason_counts[reason] = reason_counts.get(reason, 0.0) + 1.0
        if status in (1, 2):
            applied += 1
            if status == 1:
                full_applied += 1
                lin_bins += int(row_i[8])
            else:
                hybrid_applied += 1
        else:
            fallback += 1
        rows.append({
            "record": int(row_i[0]), "data_type": int(row_i[1]), "rate_type": int(row_i[2]), "ion_index": int(row_i[3]), "ion_stage": int(row_i[4]),
            "line_index": int(row_i[5]), "nb1": int(row_i[6]), "status_code": status, "status_reason": reason,
            "linopac_updated_bins": int(row_i[8]), "center_bin_one_based": int(row_i[9]),
            "ans1": float(row_f[0]), "ans2": float(row_f[1]), "ans3": float(row_f[2]), "ans4": float(row_f[3]), "opakab": float(row_f[4]),
            "opakb1": float(row_f[5]), "net": float(row_f[6]), "rcem1": float(row_f[7]), "rcem2": float(row_f[8]), "flinel_delta": float(row_f[9]),
            "oscillator_strength": float(row_f[10]), "vtherm_cm_s": float(row_f[11]),
        })
    stats={"records_batched": float(n), "cpp_calls": 1.0, "packing_seconds": float(packing_seconds), "cpp_kernel_seconds": float(cpp_kernel_seconds),
           "fallback_count": float(fallback), "type50_coarse_cpp_applied": float(applied), "type50_coarse_cpp_full_applied": float(full_applied),
           "type50_coarse_cpp_hybrid_applied": float(hybrid_applied), "type50_coarse_cpp_fallback": float(fallback),
           "linopac_cpp_calls": float(full_applied), "linopac_cpp_updated_bins": float(lin_bins)}
    for reason, count in reason_counts.items():
        stats[f"type50_reason_{reason}"] = float(count)
    return rows, message, stats


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Apply linopac profile cpp for this module while preserving the surrounding source/runtime invariants.
# Reference context: Backend adapter/provenance helper; the underlying scientific routine is documented in the corresponding XSTAR Manual section.
# XSTAR-FUNCTION-COMMENT-END
def apply_linopac_profile_cpp(
    *,
    optpp: float,
    rcem1: float,
    rcem2: float,
    line_energy_eV: float,
    vturb_km_s: float,
    temperature_1e4K: float,
    atomic_mass_amu: float,
    natural_width_eV: float,
    seed_profiles: tuple[float, ...],
    epi: np.ndarray,
    opakc: np.ndarray,
    rccemis: np.ndarray,
    ncn2: int,
) -> tuple[dict[str, Any], str, dict[str, float]]:
    """Apply the Mg line ``linopac`` profile side effect in C++.

    v0.5.61 keeps this deliberately conservative: the C++ ABI owns the
    full-profile Gaussian opacity handoff into ``opakc``.  If the source
    natural-width Voigt branch is required, the C++ function returns an
    unsupported status and the Python caller falls back to the source-faithful
    Python implementation.
    """
    lib = _load_cpp_library()
    if lib is None:
        raise RuntimeError("C++ rates shared library is not available" + (f": {cpp_import_error()}" if cpp_import_error() else ""))
    if not hasattr(lib, "xstar_rates_apply_linopac_profile"):
        raise RuntimeError("C++ rates shared library does not expose xstar_rates_apply_linopac_profile")
    n = int(ncn2)
    epi_arr = np.ascontiguousarray(epi[:n], dtype=np.float64)
    opakc_arr = np.asarray(opakc, dtype=np.float64)
    rcc_arr = np.asarray(rccemis, dtype=np.float64)
    if not opakc_arr.flags.c_contiguous:
        raise RuntimeError("opakc must be C-contiguous for the C++ linopac kernel")
    if not rcc_arr.flags.c_contiguous:
        raise RuntimeError("rccemis must be C-contiguous for the C++ linopac kernel")
    if opakc_arr.size < n or rcc_arr.size < 2 * n:
        raise RuntimeError("opakc/rccemis arrays are too small for the C++ linopac kernel")
    out_i64 = np.zeros(8, dtype=np.int64)
    out_f64 = np.zeros(12, dtype=np.float64)
    errbuf = ctypes.create_string_buffer(512)
    seed_radius = (len(seed_profiles) - 1) // 2
    if len(seed_profiles) != 2 * seed_radius + 1 or seed_radius < 0:
        raise RuntimeError("linopac seed profile shape is invalid")
    seed_profile_arr = np.ascontiguousarray(seed_profiles, dtype=np.float64)
    cpp_t0 = time.perf_counter()
    rc = lib.xstar_rates_apply_linopac_profile(
        ctypes.c_double(float(optpp)),
        ctypes.c_double(float(rcem1)),
        ctypes.c_double(float(rcem2)),
        ctypes.c_double(float(line_energy_eV)),
        ctypes.c_double(float(vturb_km_s)),
        ctypes.c_double(float(temperature_1e4K)),
        ctypes.c_double(float(atomic_mass_amu)),
        ctypes.c_double(float(natural_width_eV)),
        seed_profile_arr,
        ctypes.c_int(seed_radius),
        epi_arr,
        ctypes.c_int(n),
        opakc_arr,
        rcc_arr.reshape(-1),
        out_i64,
        out_f64,
        errbuf,
        ctypes.c_size_t(len(errbuf)),
    )
    cpp_kernel_seconds = time.perf_counter() - cpp_t0
    message = errbuf.value.decode("utf-8", errors="replace")
    if rc != 0:
        raise RuntimeError(message or f"xstar_rates_apply_linopac_profile failed with code {rc}")
    diag = {
        "updated_bins": int(out_i64[0]),
        "status_code": int(out_i64[1]),
        "center_bin_one_based": int(out_i64[2]),
        "source_nbtpp": int(out_i64[3]),
        "ncut": int(out_i64[4]),
        "ml1min": int(out_i64[5]),
        "ml1max": int(out_i64[6]),
        "profile_samples_total": int(out_i64[7]),
        "max_added_opacity": float(out_f64[0]),
        "e0_eV": float(out_f64[1]),
        "dele_eV": float(out_f64[2]),
        "deleused_eV": float(out_f64[3]),
        "prftmp": float(out_f64[4]),
        "opsv4": float(out_f64[5]),
        "aasmall": float(out_f64[6]),
        "optpp_input": float(out_f64[7]),
        "lfast_branch": "full_profile_cpp_gaussian",
        "fortran_source_compare": "linopac.f90 optp2=opsum/sume; C++ v0.5.61 Gaussian branch",
    }
    stats = {
        "linopac_cpp_calls": 1.0,
        "linopac_cpp_kernel_seconds": float(cpp_kernel_seconds),
        "linopac_cpp_updated_bins": float(diag["updated_bins"]),
        "linopac_cpp_fallback_count": 0.0,
        "linopac_cpp_parity_failures": 0.0,
        "linopac_cpp_parity_checks": 0.0,
    }
    return diag, message, stats
