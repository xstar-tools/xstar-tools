"""Persistent one-call native element matrix/Lucy engine for v0.6.45.1.

The public C ABI lives in ``cpp/xstar_element_engine.h`` and the implementation
is compiled into ``libxstar_engine.so``.  Python remains responsible for the
source-faithful atomic-data traversal and scalar UCalc dispatch in this release;
once compact source-ordered record contributions exist, term construction, matrix construction,
normalization, Lucy iteration, derived-rate totals, and state commit are owned
by one native call per element.
"""
from __future__ import annotations

import ctypes
import os
from pathlib import Path
import threading
import time
from typing import Any
from types import SimpleNamespace

import numpy as np

_ABI = 60451
_LIB: ctypes.CDLL | None = None
_LOAD_ERROR: str | None = None
_TLS = threading.local()


class _Term(ctypes.Structure):
    _fields_ = [
        ("source_position", ctypes.c_int64),
        ("term_index", ctypes.c_int64),
        ("record", ctypes.c_int64),
        ("data_type", ctypes.c_int32),
        ("rate_type", ctypes.c_int32),
        ("ion_index", ctypes.c_int32),
        ("ion_stage", ctypes.c_int32),
        ("row", ctypes.c_int32),
        ("column", ctypes.c_int32),
        ("reserved0", ctypes.c_int32),
        ("reserved1", ctypes.c_int32),
        ("aj1", ctypes.c_double),
        ("aj2", ctypes.c_double),
        ("cj", ctypes.c_double),
        ("cj2", ctypes.c_double),
    ]


class _Contribution(ctypes.Structure):
    _fields_ = [
        ("source_position", ctypes.c_int64),
        ("record", ctypes.c_int64),
        ("data_type", ctypes.c_int32),
        ("rate_type", ctypes.c_int32),
        ("ion_index", ctypes.c_int32),
        ("ion_stage", ctypes.c_int32),
        ("lower_row", ctypes.c_int32),
        ("upper_row", ctypes.c_int32),
        ("reserved0", ctypes.c_int32),
        ("reserved1", ctypes.c_int32),
        ("ans1", ctypes.c_double),
        ("ans2", ctypes.c_double),
        ("ans3", ctypes.c_double),
        ("ans4", ctypes.c_double),
        ("ans5", ctypes.c_double),
        ("ans6", ctypes.c_double),
        ("density_scale", ctypes.c_double),
    ]


class _Input(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("abi_version", ctypes.c_uint32),
        ("flags", ctypes.c_uint32),
        ("element_z", ctypes.c_int32),
        ("n_rows", ctypes.c_int32),
        ("n_superlevels", ctypes.c_int32),
        ("n_ions", ctypes.c_int32),
        ("normalization_row", ctypes.c_int32),
        ("max_lucy_iterations", ctypes.c_int32),
        ("max_fixed_point_iterations", ctypes.c_int32),
        ("reserved0", ctypes.c_int32),
        ("lucy_tolerance", ctypes.c_double),
        ("fixed_point_tolerance", ctypes.c_double),
        ("superlevel_by_row", ctypes.POINTER(ctypes.c_int32)),
        ("ion_by_row", ctypes.POINTER(ctypes.c_int32)),
        ("initial_populations", ctypes.POINTER(ctypes.c_double)),
        ("terms", ctypes.POINTER(_Term)),
        ("term_count", ctypes.c_size_t),
    ]


class _Output(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("abi_version", ctypes.c_uint32),
        ("status_flags", ctypes.c_uint32),
        ("element_z", ctypes.c_int32),
        ("outer_iterations", ctypes.c_int32),
        ("fixed_point_iterations", ctypes.c_int32),
        ("n_negative_populations", ctypes.c_int32),
        ("condensed_dimension", ctypes.c_int32),
        ("reserved0", ctypes.c_int32),
        ("final_outer_difference", ctypes.c_double),
        ("final_fixed_point_difference", ctypes.c_double),
        ("normalization", ctypes.c_double),
        ("normalization_error", ctypes.c_double),
        ("heating", ctypes.c_double),
        ("cooling", ctypes.c_double),
        ("heating2", ctypes.c_double),
        ("cooling2", ctypes.c_double),
        ("max_relative_row_residual", ctypes.c_double),
        ("max_active_relative_row_residual", ctypes.c_double),
        ("l1_row_residual", ctypes.c_double),
        ("l1_relative_row_residual", ctypes.c_double),
        ("matrix_assembly_seconds", ctypes.c_double),
        ("solver_seconds", ctypes.c_double),
        ("state_commit_seconds", ctypes.c_double),
        ("construction_seconds", ctypes.c_double),
        ("records_constructed", ctypes.c_uint64),
        ("terms_constructed", ctypes.c_uint64),
        ("populations", ctypes.POINTER(ctypes.c_double)),
        ("populations_capacity", ctypes.c_size_t),
        ("populations_count", ctypes.c_size_t),
        ("final_outer_start_populations", ctypes.POINTER(ctypes.c_double)),
        ("final_outer_start_capacity", ctypes.c_size_t),
        ("final_outer_start_count", ctypes.c_size_t),
        ("dense_matrix", ctypes.POINTER(ctypes.c_double)),
        ("dense_matrix_capacity", ctypes.c_size_t),
        ("dense_matrix_count", ctypes.c_size_t),
        ("heating_matrix", ctypes.POINTER(ctypes.c_double)),
        ("heating_matrix_capacity", ctypes.c_size_t),
        ("heating_matrix_count", ctypes.c_size_t),
        ("heating_matrix2", ctypes.POINTER(ctypes.c_double)),
        ("heating_matrix2_capacity", ctypes.c_size_t),
        ("heating_matrix2_count", ctypes.c_size_t),
        ("rhs", ctypes.POINTER(ctypes.c_double)),
        ("rhs_capacity", ctypes.c_size_t),
        ("rhs_count", ctypes.c_size_t),
        ("gamma", ctypes.POINTER(ctypes.c_double)),
        ("gamma_capacity", ctypes.c_size_t),
        ("alpha", ctypes.POINTER(ctypes.c_double)),
        ("alpha_capacity", ctypes.c_size_t),
        ("fgamma", ctypes.POINTER(ctypes.c_double)),
        ("fgamma_capacity", ctypes.c_size_t),
        ("falpha", ctypes.POINTER(ctypes.c_double)),
        ("falpha_capacity", ctypes.c_size_t),
        ("igammamax_record", ctypes.POINTER(ctypes.c_int64)),
        ("igammamax_capacity", ctypes.c_size_t),
        ("ialphamax_record", ctypes.POINTER(ctypes.c_int64)),
        ("ialphamax_capacity", ctypes.c_size_t),
        ("ion_population_totals", ctypes.POINTER(ctypes.c_double)),
        ("ion_population_totals_capacity", ctypes.c_size_t),
        ("ion_population_totals_final_vector", ctypes.POINTER(ctypes.c_double)),
        ("ion_population_totals_final_capacity", ctypes.c_size_t),
        ("ionization_totals", ctypes.POINTER(ctypes.c_double)),
        ("ionization_totals_capacity", ctypes.c_size_t),
        ("recombination_totals", ctypes.POINTER(ctypes.c_double)),
        ("recombination_totals_capacity", ctypes.c_size_t),
        ("ionization_components", ctypes.POINTER(ctypes.c_double)),
        ("ionization_components_capacity", ctypes.c_size_t),
        ("recombination_components", ctypes.POINTER(ctypes.c_double)),
        ("recombination_components_capacity", ctypes.c_size_t),
        ("row_residual", ctypes.POINTER(ctypes.c_double)),
        ("row_residual_capacity", ctypes.c_size_t),
        ("row_scale", ctypes.POINTER(ctypes.c_double)),
        ("row_scale_capacity", ctypes.c_size_t),
        ("relative_row_residual", ctypes.POINTER(ctypes.c_double)),
        ("relative_row_residual_capacity", ctypes.c_size_t),
        ("solver_method", ctypes.c_char * 128),
        ("message", ctypes.c_char * 1024),
    ]


def _p64(array: np.ndarray) -> ctypes.POINTER(ctypes.c_double):
    return array.ctypes.data_as(ctypes.POINTER(ctypes.c_double))


def _pi32(array: np.ndarray) -> ctypes.POINTER(ctypes.c_int32):
    return array.ctypes.data_as(ctypes.POINTER(ctypes.c_int32))


def _pi64(array: np.ndarray) -> ctypes.POINTER(ctypes.c_int64):
    return array.ctypes.data_as(ctypes.POINTER(ctypes.c_int64))


def _load() -> ctypes.CDLL:
    global _LIB, _LOAD_ERROR
    if _LIB is not None:
        return _LIB
    candidates: list[Path] = []
    explicit = os.environ.get("XSTAR_ATOMIC_CPP_ENGINE_LIB", "").strip()
    if explicit:
        candidates.append(Path(explicit))
    candidates.append(Path(__file__).resolve().parent / "cpp" / "libxstar_engine.so")
    errors: list[str] = []
    for path in candidates:
        try:
            lib = ctypes.CDLL(str(path))
            lib.xstar_element_engine_abi_version.restype = ctypes.c_uint32
            if int(lib.xstar_element_engine_abi_version()) != _ABI:
                raise RuntimeError("element-engine ABI mismatch")
            lib.xstar_element_engine_context_create_v1.argtypes = [
                ctypes.POINTER(ctypes.c_void_p), ctypes.c_char_p, ctypes.c_size_t
            ]
            lib.xstar_element_engine_context_create_v1.restype = ctypes.c_int
            lib.xstar_element_engine_context_destroy.argtypes = [ctypes.c_void_p]
            lib.xstar_element_engine_context_destroy.restype = None
            lib.xstar_element_engine_run_element_v1.argtypes = [
                ctypes.c_void_p, ctypes.POINTER(_Input), ctypes.POINTER(_Output),
                ctypes.c_char_p, ctypes.c_size_t
            ]
            lib.xstar_element_engine_run_element_v1.restype = ctypes.c_int
            lib.xstar_element_engine_run_construction_v1.argtypes = [
                ctypes.c_void_p, ctypes.POINTER(_Input), ctypes.POINTER(_Contribution), ctypes.c_size_t,
                ctypes.POINTER(_Output), ctypes.c_char_p, ctypes.c_size_t
            ]
            lib.xstar_element_engine_run_construction_v1.restype = ctypes.c_int
            _LIB = lib
            _LOAD_ERROR = None
            return lib
        except Exception as exc:  # pragma: no cover - environment dependent
            errors.append(f"{path}: {exc}")
    _LOAD_ERROR = "; ".join(errors)
    raise RuntimeError(_LOAD_ERROR or "libxstar_engine.so unavailable")


def _context() -> ctypes.c_void_p:
    ctx = getattr(_TLS, "context", None)
    if ctx:
        return ctx
    lib = _load()
    value = ctypes.c_void_p()
    error = ctypes.create_string_buffer(1024)
    rc = lib.xstar_element_engine_context_create_v1(
        ctypes.byref(value), error, len(error)
    )
    if rc != 0 or not value.value:
        raise RuntimeError(error.value.decode("utf-8", "replace") or f"context create failed: {rc}")
    _TLS.context = value
    return value


def element_engine_status() -> dict[str, Any]:
    try:
        lib = _load()
        lib.xstar_element_engine_backend_name.restype = ctypes.c_char_p
        name = lib.xstar_element_engine_backend_name()
        return {
            "available": True,
            "abi_version": int(lib.xstar_element_engine_abi_version()),
            "implementation": name.decode() if name else "unknown",
            "load_error": None,
        }
    except Exception as exc:
        return {"available": False, "abi_version": None, "implementation": None, "load_error": str(exc)}


def _env_true(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def element_engine_cpp_product_enabled(element_z: int) -> bool:
    if not _env_true("XSTAR_ATOMIC_ELEMENT_ENGINE_CPP"):
        return False
    allowed = os.environ.get("XSTAR_ATOMIC_ELEMENT_ENGINE_CPP_ELEMENTS", "1,2,12")
    try:
        selected = {int(item.strip()) for item in allowed.split(",") if item.strip()}
    except ValueError:
        selected = {1, 2, 12}
    return int(element_z) in selected and _env_true("XSTAR_ATOMIC_ELEMENT_ENGINE_CPP_PRODUCT")


def element_engine_cpp_shadow_enabled(element_z: int) -> bool:
    if not _env_true("XSTAR_ATOMIC_ELEMENT_ENGINE_CPP"):
        return False
    allowed = os.environ.get("XSTAR_ATOMIC_ELEMENT_ENGINE_CPP_ELEMENTS", "1,2,12")
    try:
        selected = {int(item.strip()) for item in allowed.split(",") if item.strip()}
    except ValueError:
        selected = {1, 2, 12}
    return int(element_z) in selected and _env_true("XSTAR_ATOMIC_ELEMENT_ENGINE_CPP_SHADOW")


def _contributions_from_terms(terms: Any, density_scale: float) -> list[Any]:
    values = list(terms)
    if len(values) % 4 != 0:
        raise RuntimeError(f"term stream length {len(values)} is not divisible by four")
    result: list[Any] = []
    for offset in range(0, len(values), 4):
        group = values[offset:offset + 4]
        roles = {str(term.role): term for term in group}
        required = {"forward_offdiag", "reverse_offdiag", "forward_diag_loss", "reverse_diag_loss"}
        if set(roles) != required:
            raise RuntimeError(f"term group at {offset} lacks canonical four-row roles")
        forward = roles["forward_offdiag"]
        reverse = roles["reverse_offdiag"]
        lower_diag = roles["forward_diag_loss"]
        upper_diag = roles["reverse_diag_loss"]
        if density_scale == 0.0:
            raise RuntimeError("density scale is zero")
        result.append(SimpleNamespace(
            source_position=offset + 1, record=int(forward.record),
            data_type=int(forward.data_type), rate_type=int(forward.rate_type),
            ion_index=int(forward.ion_index), ion_stage=int(forward.ion_stage),
            lower_row=int(forward.column), upper_row=int(forward.row),
            ans1=float(forward.aj1), ans2=float(reverse.aj1),
            ans3=float(-upper_diag.cj / density_scale),
            ans4=float(lower_diag.cj / density_scale),
            ans5=float(-upper_diag.cj2 / density_scale),
            ans6=float(lower_diag.cj2 / density_scale),
            density_scale=float(density_scale),
        ))
    return result


def run_element_engine_cpp(assembly: Any, context: Any) -> tuple[Any, dict[str, Any]]:
    """Run native matrix construction, Lucy solve, and derived state commit."""
    from .element_equilibrium import LucySolveResult

    packing_t0 = time.perf_counter()
    basis = assembly.basis
    n = int(basis.n_rows)
    nsp = int(basis.n_superlevels)
    nion = int(basis.n_ions)
    diagnostics_mode = str((context.profile_control or {}).get("diagnostics_mode", "full")).lower()
    summary = diagnostics_mode in {"summary", "full"}

    superlevels = np.ascontiguousarray(np.asarray(basis.nsup[1 : n + 1], dtype=np.int32))
    ions = np.ascontiguousarray(np.asarray(basis.nion[1 : n + 1], dtype=np.int32))
    initial = np.ascontiguousarray(np.asarray(assembly.initial_populations[1 : n + 1], dtype=np.float64))

    native_contributions = getattr(assembly.terms, "native_contributions", None)
    construction_shadow = _env_true("XSTAR_ATOMIC_ELEMENT_CONSTRUCTION_CPP_SHADOW")
    if native_contributions is None and construction_shadow:
        native_contributions = _contributions_from_terms(
            assembly.terms, float(getattr(context, "hydrogen_density_cm3", 1.0))
        )
    construction_mode = native_contributions is not None
    contribution_array = None
    term_array = None
    if construction_mode:
        contribution_array = (_Contribution * len(native_contributions))()
        for index, item in enumerate(native_contributions):
            contribution_array[index] = _Contribution(
                int(item.source_position), int(item.record), int(item.data_type), int(item.rate_type),
                int(item.ion_index), int(item.ion_stage), int(item.lower_row), int(item.upper_row), 0, 0,
                float(item.ans1), float(item.ans2), float(item.ans3), float(item.ans4),
                float(item.ans5), float(item.ans6), float(item.density_scale),
            )
    else:
        term_array = (_Term * len(assembly.terms))()
        for index, term in enumerate(assembly.terms):
            term_array[index] = _Term(
                int(index + 1),
                int(term.term_index), int(term.record), int(term.data_type), int(term.rate_type),
                int(term.ion_index), int(term.ion_stage), int(term.row), int(term.column), 0, 0,
                float(term.aj1), float(term.aj2), float(term.cj), float(term.cj2),
            )

    populations = np.empty(n, dtype=np.float64)
    final_outer = np.empty(n, dtype=np.float64)
    dense = np.empty((n, n), dtype=np.float64)
    heat = np.empty((n, n), dtype=np.float64)
    heat2 = np.empty((n, n), dtype=np.float64)
    rhs = np.empty(n, dtype=np.float64)
    gamma = np.empty(n, dtype=np.float64)
    alpha = np.empty(n, dtype=np.float64)
    fgamma = np.empty((5, n), dtype=np.float64)
    falpha = np.empty((5, n), dtype=np.float64)
    igamma = np.empty(n, dtype=np.int64)
    ialpha = np.empty(n, dtype=np.int64)
    ion_totals = np.empty(nion, dtype=np.float64)
    ion_totals_final = np.empty(nion, dtype=np.float64)
    ionize = np.empty(nion, dtype=np.float64)
    recombine = np.empty(nion, dtype=np.float64)
    ionize_components = np.empty((3, nion), dtype=np.float64)
    recombine_components = np.empty((3, nion), dtype=np.float64)
    residual = np.empty(n, dtype=np.float64)
    row_scale = np.empty(n, dtype=np.float64)
    relative_residual = np.empty(n, dtype=np.float64)

    flags = 1 | 4  # strict source order + return matrices
    if summary:
        flags |= 2
    if bool(context.allow_dense_matrix_rescue):
        flags |= 8
    inp = _Input(
        ctypes.sizeof(_Input), _ABI, flags, int(basis.element_z), n, nsp, nion,
        int(basis.normalization_row), int(context.max_lucy_iterations),
        int(context.max_fixed_point_iterations), 0, float(context.lucy_tolerance),
        float(context.fixed_point_tolerance), _pi32(superlevels), _pi32(ions), _p64(initial),
        (ctypes.cast(term_array, ctypes.POINTER(_Term)) if term_array is not None else None),
        (len(assembly.terms) if not construction_mode else 0),
    )
    out = _Output()
    out.struct_size = ctypes.sizeof(_Output)
    out.abi_version = _ABI
    out.populations, out.populations_capacity = _p64(populations), populations.size
    out.final_outer_start_populations, out.final_outer_start_capacity = _p64(final_outer), final_outer.size
    out.dense_matrix, out.dense_matrix_capacity = _p64(dense), dense.size
    out.heating_matrix, out.heating_matrix_capacity = _p64(heat), heat.size
    out.heating_matrix2, out.heating_matrix2_capacity = _p64(heat2), heat2.size
    out.rhs, out.rhs_capacity = _p64(rhs), rhs.size
    out.gamma, out.gamma_capacity = _p64(gamma), gamma.size
    out.alpha, out.alpha_capacity = _p64(alpha), alpha.size
    out.fgamma, out.fgamma_capacity = _p64(fgamma), fgamma.size
    out.falpha, out.falpha_capacity = _p64(falpha), falpha.size
    out.igammamax_record, out.igammamax_capacity = _pi64(igamma), igamma.size
    out.ialphamax_record, out.ialphamax_capacity = _pi64(ialpha), ialpha.size
    out.ion_population_totals, out.ion_population_totals_capacity = _p64(ion_totals), ion_totals.size
    out.ion_population_totals_final_vector, out.ion_population_totals_final_capacity = _p64(ion_totals_final), ion_totals_final.size
    out.ionization_totals, out.ionization_totals_capacity = _p64(ionize), ionize.size
    out.recombination_totals, out.recombination_totals_capacity = _p64(recombine), recombine.size
    out.ionization_components, out.ionization_components_capacity = _p64(ionize_components), ionize_components.size
    out.recombination_components, out.recombination_components_capacity = _p64(recombine_components), recombine_components.size
    out.row_residual, out.row_residual_capacity = _p64(residual), residual.size
    out.row_scale, out.row_scale_capacity = _p64(row_scale), row_scale.size
    out.relative_row_residual, out.relative_row_residual_capacity = _p64(relative_residual), relative_residual.size

    lib = _load()
    error = ctypes.create_string_buffer(1024)
    packing_seconds = time.perf_counter() - packing_t0
    call_t0 = time.perf_counter()
    if construction_mode:
        rc = lib.xstar_element_engine_run_construction_v1(
            _context(), ctypes.byref(inp),
            ctypes.cast(contribution_array, ctypes.POINTER(_Contribution)), len(native_contributions),
            ctypes.byref(out), error, len(error)
        )
    else:
        rc = lib.xstar_element_engine_run_element_v1(
            _context(), ctypes.byref(inp), ctypes.byref(out), error, len(error)
        )
    call_seconds = time.perf_counter() - call_t0
    if rc != 0:
        raise RuntimeError(error.value.decode("utf-8", "replace") or f"native element engine failed: {rc}")

    assembly.dense_matrix = dense
    assembly.heating_matrix = heat
    assembly.heating_matrix2 = heat2
    assembly.rhs = rhs
    if diagnostics_mode != "none":
        normalized = dense.copy()
        normalized[int(basis.normalization_row) - 1, :] = 1.0
        assembly.normalized_matrix = normalized
    else:
        assembly.normalized_matrix = np.empty((0, 0), dtype=float)

    empty = np.asarray([], dtype=float)
    notes = [
        "v0.6.45.1 native element engine owns dense matrix construction, normalization, Lucy solve, and state commit",
        "compact source-ordered record contributions were supplied by the Python atomic-data/rate traversal",
    ]
    solve = LucySolveResult(
        populations=populations,
        converged=bool(out.status_flags & 1),
        outer_iterations=int(out.outer_iterations),
        fixed_point_iterations=int(out.fixed_point_iterations),
        final_outer_difference=float(out.final_outer_difference),
        final_fixed_point_difference=float(out.final_fixed_point_difference),
        n_negative_populations=int(out.n_negative_populations),
        normalization=float(out.normalization),
        normalization_error=float(out.normalization_error),
        max_relative_row_residual=float(out.max_relative_row_residual),
        max_active_relative_row_residual=float(out.max_active_relative_row_residual),
        l1_row_residual=float(out.l1_row_residual),
        l1_relative_row_residual=float(out.l1_relative_row_residual),
        n_zero_scale_rows=(int(np.count_nonzero(row_scale <= 1.0e-300)) if summary else -1),
        row_residual=(residual if summary else empty),
        row_scale=(row_scale if summary else empty),
        relative_row_residual=(relative_residual if summary else empty),
        solver_method=bytes(out.solver_method).split(b"\0", 1)[0].decode("utf-8", "replace"),
        condensed_rank=-1,
        condensed_dimension=int(out.condensed_dimension),
        dense_rank=-1,
        dense_condition_number=float("nan"),
        heating=float(out.heating), cooling=float(out.cooling),
        heating2=float(out.heating2), cooling2=float(out.cooling2),
        gamma=gamma, alpha=alpha, fgamma=fgamma, falpha=falpha,
        igammamax_record=igamma, ialphamax_record=ialpha,
        ion_population_totals=ion_totals,
        ion_population_totals_final_vector=ion_totals_final,
        ion_population_totals_source="final_outer_iteration_start_vector",
        final_outer_start_populations=(final_outer if summary else empty),
        ionization_totals=ionize, recombination_totals=recombine,
        ionization_components=ionize_components,
        recombination_components=recombine_components,
        notes=notes,
        trace=None,
    )
    metrics = {
        "element_z": int(basis.element_z),
        "rows": n,
        "terms": len(assembly.terms),
        "records": int(len(native_contributions) if construction_mode else 0),
        "python_matrix_terms_materialized": int(
            getattr(assembly.terms, "materialized_term_count", len(assembly.terms))
            if not construction_shadow else len(assembly.terms)
        ),
        "construction_mode": bool(construction_mode),
        "packing_seconds": packing_seconds,
        "ffi_call_seconds": call_seconds,
        "native_matrix_assembly_seconds": float(out.matrix_assembly_seconds),
        "native_solver_seconds": float(out.solver_seconds),
        "native_state_commit_seconds": float(out.state_commit_seconds),
        "native_construction_seconds": float(out.construction_seconds),
        "native_records_constructed": int(out.records_constructed),
        "native_terms_constructed": int(out.terms_constructed),
        "status_flags": int(out.status_flags),
        "implementation": element_engine_status().get("implementation"),
    }
    return solve, metrics
