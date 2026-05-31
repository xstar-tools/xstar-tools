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

    def as_dict(self) -> dict[str, object]:
        return dict(asdict(self))


_CPP_LIB: ctypes.CDLL | None = None
_CPP_LOAD_ERROR: BaseException | None = None
_CPP_LIBRARY_PATH: str | None = None


def _candidate_library_paths() -> list[Path]:
    env_path = os.environ.get("XSTAR_ATOMIC_RATES_LIB")
    paths: list[Path] = []
    if env_path:
        paths.append(Path(env_path).expanduser())
    here = Path(__file__).resolve().parent
    names = (
        "libxstar_rates.so",
        "xstar_rates.so",
        "libxstar_rates.dylib",
        "xstar_rates.dll",
    )
    # Prefer the single shared-library location under source_port/cpp.
    for name in names:
        paths.append(here / "cpp" / name)
    # Backward-compatible fallback for v0.5.53-v0.5.59 runtime copies.
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
                    f64p, ctypes.c_int, f64p, f64p, i64p, f64p,
                    ctypes.c_char_p, ctypes.c_size_t,
                ]
                lib.xstar_rates_apply_linopac_profile.restype = ctypes.c_int
            except AttributeError:
                # Older libraries do not expose the C++ linopac side-effect kernel.
                pass
            _CPP_LIB = lib
            _CPP_LIBRARY_PATH = str(path)
            return _CPP_LIB
        raise FileNotFoundError("no xstar_rates shared library found; attempted: " + "; ".join(attempted))
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
        raw = lib.xstar_rates_backend_name()
        return raw.decode("ascii", errors="replace") if raw else None
    except Exception:
        return None


def _abi_version(lib: ctypes.CDLL | None) -> int | None:
    if lib is None:
        return None
    try:
        return int(lib.xstar_rates_abi_version())
    except Exception:
        return None


def _feature_flags(lib: ctypes.CDLL | None) -> int | None:
    if lib is None:
        return None
    try:
        return int(lib.xstar_rates_feature_flags())
    except Exception:
        return None


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
    def i64(name: str) -> np.ndarray:
        return np.ascontiguousarray([int(r[name]) for r in records], dtype=np.int64)
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

    def i64(name: str) -> np.ndarray:
        return np.ascontiguousarray([int(r[name]) for r in records], dtype=np.int64)

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
