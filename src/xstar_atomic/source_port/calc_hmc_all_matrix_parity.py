"""Same-call XSTAR matrix and thermal-family parity diagnostics.

The bounded probe products consumed here are diagnostic only.  Captured XSTAR
coefficients and populations are never substituted into the production Python
operator or native solve.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from .local_zone import FixedStateCalcHMCAllResult
from .calc_hmc_all_closure import XSTARVectorMatrixClosureResult
from .fortran_numbers import parse_fortran_float


@dataclass
class SameCallMatrixParityResult:
    status: str
    ready: Optional[bool]
    topology_ready: Optional[bool]
    coefficient_ready: Optional[bool]
    active_closure_ready: Optional[bool]
    n_python_terms: int
    n_xstar_terms: int
    n_matched_terms: int
    n_topology_mismatches: int
    n_coefficient_rows_outside_tolerance: int
    n_active_rows_outside_tolerance: int
    max_abs_aj1_difference: float
    max_abs_aj2_difference: float
    max_abs_cj_difference: float
    max_abs_cj2_difference: float
    term_rows: List[Dict[str, Any]] = field(default_factory=list)
    family_rows: List[Dict[str, Any]] = field(default_factory=list)
    active_row_rows: List[Dict[str, Any]] = field(default_factory=list)
    diagnostics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ThermalFamilyParityResult:
    status: str
    ready: Optional[bool]
    n_rows: int
    n_outside_tolerance: int
    rows: List[Dict[str, Any]] = field(default_factory=list)
    diagnostics: Dict[str, Any] = field(default_factory=dict)


def _within(py: float, xs: float, rtol: float, atol: float) -> bool:
    return abs(py - xs) <= atol + rtol * abs(xs)


def _float(row: Mapping[str, str], name: str, default: float = 0.0) -> float:
    value = row.get(name)
    if value in (None, ""):
        return float(default)
    return parse_fortran_float(value)


def _int(row: Mapping[str, str], name: str, default: int = 0) -> int:
    value = row.get(name)
    if value in (None, ""):
        return int(default)
    return int(value)


def _closure_by_z(
    closure: Optional[XSTARVectorMatrixClosureResult],
) -> Dict[int, Any]:
    if closure is None:
        return {}
    return {int(item.element_z): item for item in closure.elements}


def compare_same_call_matrix_terms(
    result: FixedStateCalcHMCAllResult,
    *,
    matrix_probe_rows: Sequence[Mapping[str, str]],
    closure: Optional[XSTARVectorMatrixClosureResult],
    rtol: float = 5.0e-3,
    atol: float = 1.0e-12,
    active_row_scale_threshold: float = 1.0e-12,
) -> SameCallMatrixParityResult:
    """Compare exact XSTAR ``aj1/aj2/cj/cj2`` terms to Python assembly."""

    if not matrix_probe_rows:
        return SameCallMatrixParityResult(
            status="not_comparable_missing_matrix_probe",
            ready=None,
            topology_ready=None,
            coefficient_ready=None,
            active_closure_ready=None,
            n_python_terms=sum(
                len(getattr(getattr(item, "equilibrium", None), "assembly", None).terms)
                for item in getattr(result, "element_results", ())
                if getattr(getattr(item, "equilibrium", None), "assembly", None) is not None
            ),
            n_xstar_terms=0,
            n_matched_terms=0,
            n_topology_mismatches=0,
            n_coefficient_rows_outside_tolerance=0,
            n_active_rows_outside_tolerance=0,
            max_abs_aj1_difference=0.0,
            max_abs_aj2_difference=0.0,
            max_abs_cj_difference=0.0,
            max_abs_cj2_difference=0.0,
            diagnostics={"diagnostic_only": True, "probe_values_enter_operator": False},
        )

    closure_map = _closure_by_z(closure)
    term_rows: List[Dict[str, Any]] = []
    family_acc: Dict[Tuple[int, int, int], Dict[str, Any]] = {}
    active_rows: List[Dict[str, Any]] = []
    n_py = n_xs = n_match = n_top = n_bad = n_field_bad = n_active_bad = 0
    n_python_source_active_bad = 0
    n_xstar_source_active_bad = 0
    n_closure_elements_evaluated = 0
    max_diffs = {name: 0.0 for name in ("aj1", "aj2", "cj", "cj2")}

    rows_by_z: Dict[int, List[Mapping[str, str]]] = {}
    for row in matrix_probe_rows:
        rows_by_z.setdefault(_int(row, "element_z"), []).append(row)

    for element in getattr(result, "element_results", ()):
        if getattr(element, "equilibrium", None) is None:
            continue
        z = int(element.request.element_z)
        assembly = element.equilibrium.assembly
        py_terms = list(assembly.terms)
        xs_rows = rows_by_z.get(z, [])
        py_by_index = {int(term.term_index): term for term in py_terms}
        xs_by_index = {_int(row, "term_index"): row for row in xs_rows}
        n_py += len(py_terms)
        n_xs += len(xs_rows)
        all_indices = sorted(set(py_by_index) | set(xs_by_index))

        n = int(assembly.basis.n_rows)
        a_xstar = np.zeros((n, n), dtype=float)
        a_python = np.asarray(assembly.dense_matrix, dtype=float)
        xstar_vector = np.zeros(n, dtype=float)
        closure_item = closure_map.get(z)
        closure_rows_by_compact: Dict[int, Mapping[str, Any]] = {}
        if closure_item is not None:
            closure_rows_by_compact = {
                int(row["compact_row"]): row for row in closure_item.row_rows
            }
            for compact, row in closure_rows_by_compact.items():
                if 1 <= compact <= n:
                    xstar_vector[compact - 1] = float(row["xstar_population"])

        delta_terms_by_row: Dict[int, List[Dict[str, Any]]] = {}
        for index in all_indices:
            py = py_by_index.get(index)
            xs = xs_by_index.get(index)
            if py is None or xs is None:
                term_rows.append({
                    "element_z": z,
                    "term_index": index,
                    "match_status": "missing_python" if py is None else "missing_xstar",
                    "topology_match": False,
                    "within_tolerance": False,
                })
                n_bad += 1
                continue
            n_match += 1
            xs_row = _int(xs, "row_compact")
            xs_col = _int(xs, "column_compact")
            xs_row_raw = _int(xs, "row_raw")
            xs_col_raw = _int(xs, "column_raw")
            xs_record = _int(xs, "source_record")
            topology = (
                int(py.row) == xs_row
                and int(py.column) == xs_col
                and int(py.source_row_unclamped) == xs_row_raw
                and int(py.source_column_unclamped) == xs_col_raw
                and int(py.record) == xs_record
            )
            if not topology:
                n_top += 1
            xs_values = {
                "aj1": _float(xs, "aj1"),
                "aj2": _float(xs, "aj2"),
                "cj": _float(xs, "cj"),
                "cj2": _float(xs, "cj2"),
            }
            py_values = {
                "aj1": float(py.aj1),
                "aj2": float(py.aj2),
                "cj": float(py.cj),
                "cj2": float(py.cj2),
            }
            field_ok = {
                name: _within(py_values[name], xs_values[name], rtol, atol)
                for name in py_values
            }
            for name in max_diffs:
                max_diffs[name] = max(
                    max_diffs[name], abs(py_values[name] - xs_values[name])
                )
            coefficient_fields_ok = all(field_ok.values())
            ok = topology and coefficient_fields_ok
            if not ok:
                n_bad += 1
            if not coefficient_fields_ok:
                n_field_bad += 1
            if 1 <= xs_row <= n and 1 <= xs_col <= n:
                a_xstar[xs_row - 1, xs_col - 1] += xs_values["aj1"]
            xcol = xstar_vector[min(n, max(1, int(py.column))) - 1]
            delta_contribution = (py_values["aj1"] - xs_values["aj1"]) * xcol
            delta_terms_by_row.setdefault(int(py.row), []).append({
                "term_index": index,
                "record": int(py.record),
                "data_type": int(py.data_type),
                "rate_type": int(py.rate_type),
                "role": str(py.role),
                "column": int(py.column),
                "python_aj1": py_values["aj1"],
                "xstar_aj1": xs_values["aj1"],
                "xstar_population_column": xcol,
                "delta_population_weighted_contribution": delta_contribution,
            })
            row = {
                "element_z": z,
                "term_index": index,
                "record": int(py.record),
                "data_type": int(py.data_type),
                "rate_type": int(py.rate_type),
                "role": str(py.role),
                "python_row_raw": int(py.source_row_unclamped),
                "xstar_row_raw": xs_row_raw,
                "python_column_raw": int(py.source_column_unclamped),
                "xstar_column_raw": xs_col_raw,
                "python_row_compact": int(py.row),
                "xstar_row_compact": xs_row,
                "python_column_compact": int(py.column),
                "xstar_column_compact": xs_col,
                "topology_match": topology,
                "python_aj1": py_values["aj1"],
                "xstar_aj1": xs_values["aj1"],
                "aj1_difference": py_values["aj1"] - xs_values["aj1"],
                "python_aj2": py_values["aj2"],
                "xstar_aj2": xs_values["aj2"],
                "aj2_difference": py_values["aj2"] - xs_values["aj2"],
                "python_cj": py_values["cj"],
                "xstar_cj": xs_values["cj"],
                "cj_difference": py_values["cj"] - xs_values["cj"],
                "python_cj2": py_values["cj2"],
                "xstar_cj2": xs_values["cj2"],
                "cj2_difference": py_values["cj2"] - xs_values["cj2"],
                "within_tolerance": ok,
                "match_status": "matched" if ok else "outside_tolerance",
                "xstar_population_column": xcol,
                "delta_population_weighted_aj1": delta_contribution,
            }
            term_rows.append(row)
            key = (z, int(py.data_type), int(py.rate_type))
            fam = family_acc.setdefault(key, {
                "element_z": z,
                "data_type": int(py.data_type),
                "rate_type": int(py.rate_type),
                "n_terms": 0,
                "n_topology_mismatches": 0,
                "n_outside_tolerance": 0,
                "l1_abs_aj1_difference": 0.0,
                "l1_abs_aj2_difference": 0.0,
                "l1_abs_cj_difference": 0.0,
                "l1_abs_cj2_difference": 0.0,
                "l1_abs_population_weighted_aj1_difference": 0.0,
            })
            fam["n_terms"] += 1
            fam["n_topology_mismatches"] += int(not topology)
            fam["n_outside_tolerance"] += int(not ok)
            for name in ("aj1", "aj2", "cj", "cj2"):
                fam[f"l1_abs_{name}_difference"] += abs(
                    py_values[name] - xs_values[name]
                )
            fam["l1_abs_population_weighted_aj1_difference"] += abs(delta_contribution)

        if closure_item is not None and np.any(xstar_vector):
            n_closure_elements_evaluated += 1
            py_residual = a_python @ xstar_vector
            xs_residual = a_xstar @ xstar_vector
            delta_residual = py_residual - xs_residual
            py_scale = np.sum(np.abs(a_python) * np.abs(xstar_vector[np.newaxis, :]), axis=1)
            xs_scale = np.sum(np.abs(a_xstar) * np.abs(xstar_vector[np.newaxis, :]), axis=1)
            active = np.maximum(py_scale, xs_scale) >= active_row_scale_threshold
            py_within = np.abs(py_residual) <= atol + rtol * py_scale
            xs_within = np.abs(xs_residual) <= atol + rtol * xs_scale
            delta_scale = np.maximum(py_scale, xs_scale)
            delta_within = np.abs(delta_residual) <= atol + rtol * delta_scale
            n_py_source_bad = int(np.count_nonzero(active & ~py_within))
            n_xs_source_bad = int(np.count_nonzero(active & ~xs_within))
            n_delta_bad_element = int(np.count_nonzero(active & ~delta_within))
            n_python_source_active_bad += n_py_source_bad
            n_xstar_source_active_bad += n_xs_source_bad
            n_active_bad += n_delta_bad_element
            for compact in range(1, n + 1):
                idx = compact - 1
                if not active[idx]:
                    continue
                if py_within[idx] and xs_within[idx] and delta_within[idx]:
                    continue
                candidates = delta_terms_by_row.get(compact, [])
                dominant = max(
                    candidates,
                    key=lambda item: abs(item["delta_population_weighted_contribution"]),
                    default=None,
                )
                if not delta_within[idx]:
                    classification = "coefficient_driven"
                elif not xs_within[idx] and not py_within[idx]:
                    classification = "xstar_solver_or_superlevel_path"
                elif not xs_within[idx]:
                    classification = "xstar_source_matrix_residual"
                elif not py_within[idx]:
                    classification = "python_matrix_residual"
                else:
                    classification = "population_or_normalization_propagation"
                closure_row = closure_rows_by_compact.get(compact, {})
                active_rows.append({
                    "element_z": z,
                    "compact_row": compact,
                    "representative_global_level_index": closure_row.get(
                        "representative_global_level_index"
                    ),
                    "python_matrix_xstar_vector_residual": float(py_residual[idx]),
                    "xstar_matrix_xstar_vector_residual": float(xs_residual[idx]),
                    "matrix_difference_xstar_vector_residual": float(delta_residual[idx]),
                    "python_row_scale": float(py_scale[idx]),
                    "xstar_row_scale": float(xs_scale[idx]),
                    "python_matrix_within_tolerance": bool(py_within[idx]),
                    "xstar_matrix_within_tolerance": bool(xs_within[idx]),
                    "matrix_difference_within_tolerance": bool(delta_within[idx]),
                    "python_matrix_relative_residual": float(
                        abs(py_residual[idx]) / max(py_scale[idx], 1.0e-300)
                    ),
                    "xstar_matrix_relative_residual": float(
                        abs(xs_residual[idx]) / max(xs_scale[idx], 1.0e-300)
                    ),
                    "matrix_difference_relative_residual": float(
                        abs(delta_residual[idx]) / max(delta_scale[idx], 1.0e-300)
                    ),
                    "classification": classification,
                    "dominant_delta_term_index": None if dominant is None else dominant["term_index"],
                    "dominant_delta_record": None if dominant is None else dominant["record"],
                    "dominant_delta_data_type": None if dominant is None else dominant["data_type"],
                    "dominant_delta_rate_type": None if dominant is None else dominant["rate_type"],
                    "dominant_delta_role": None if dominant is None else dominant["role"],
                    "dominant_delta_column": None if dominant is None else dominant["column"],
                    "dominant_delta_python_aj1": None if dominant is None else dominant["python_aj1"],
                    "dominant_delta_xstar_aj1": None if dominant is None else dominant["xstar_aj1"],
                    "dominant_delta_xstar_population": None if dominant is None else dominant["xstar_population_column"],
                    "dominant_delta_population_weighted_contribution": (
                        None if dominant is None
                        else dominant["delta_population_weighted_contribution"]
                    ),
                })

    topology_ready = bool(n_py == n_xs == n_match and n_top == 0)
    coefficient_ready = bool(topology_ready and n_field_bad == 0)
    active_ready: Optional[bool] = (
        bool(n_active_bad == 0) if n_closure_elements_evaluated > 0 else None
    )
    # Milestone matrix readiness is deliberately active/topological.  Strict
    # coefficient parity remains a separate gate so tiny inactive-family
    # differences stay visible without blocking the oxygen milestone.
    ready = bool(topology_ready and active_ready is True)
    if ready:
        status = "ready"
    elif active_ready is None:
        status = "not_comparable_missing_xstar_vector"
    else:
        status = "failed"
    return SameCallMatrixParityResult(
        status=status,
        ready=ready,
        topology_ready=topology_ready,
        coefficient_ready=coefficient_ready,
        active_closure_ready=active_ready,
        n_python_terms=n_py,
        n_xstar_terms=n_xs,
        n_matched_terms=n_match,
        n_topology_mismatches=n_top,
        n_coefficient_rows_outside_tolerance=n_field_bad,
        n_active_rows_outside_tolerance=n_active_bad,
        max_abs_aj1_difference=max_diffs["aj1"],
        max_abs_aj2_difference=max_diffs["aj2"],
        max_abs_cj_difference=max_diffs["cj"],
        max_abs_cj2_difference=max_diffs["cj2"],
        term_rows=term_rows,
        family_rows=[family_acc[key] for key in sorted(family_acc)],
        active_row_rows=active_rows,
        diagnostics={
            "rtol": float(rtol),
            "atol": float(atol),
            "active_row_scale_threshold": float(active_row_scale_threshold),
            "n_strict_term_rows_outside_tolerance_including_topology": n_bad,
            "n_coefficient_term_rows_outside_tolerance": n_field_bad,
            "topology_ready": topology_ready,
            "coefficient_ready": coefficient_ready,
            "n_python_matrix_active_rows_outside_tolerance": n_python_source_active_bad,
            "n_xstar_matrix_active_rows_outside_tolerance": n_xstar_source_active_bad,
            "n_matrix_difference_active_rows_outside_tolerance": n_active_bad,
            "n_closure_elements_evaluated": n_closure_elements_evaluated,
            "milestone_ready_definition": (
                "topology_ready && (A_python-A_xstar)@x_xstar within tolerance on active rows"
            ),
            "strict_coefficient_ready_definition": (
                "topology_ready && all aj1/aj2/cj/cj2 terms within tolerance"
            ),
            "active_closure_ready_definition": (
                "(A_python-A_xstar)@x_xstar within tolerance on active rows"
            ),
            "xstar_source_matrix_closure_is_diagnostic": True,
            "diagnostic_only": True,
            "probe_values_enter_operator": False,
        },
    )


def compare_thermal_families(
    *,
    closure: Optional[XSTARVectorMatrixClosureResult],
    data_type_probe_rows: Sequence[Mapping[str, str]],
    rate_type_probe_rows: Sequence[Mapping[str, str]],
    rtol: float = 5.0e-3,
    atol: float = 1.0e-12,
) -> ThermalFamilyParityResult:
    """Compare Python family thermal sums to XSTAR ``rntpsv/rltpsv``."""

    if closure is None or not closure.elements:
        return ThermalFamilyParityResult(
            status="not_comparable_missing_python_thermal_rows",
            ready=None,
            n_rows=0,
            n_outside_tolerance=0,
        )
    if not data_type_probe_rows or not rate_type_probe_rows:
        return ThermalFamilyParityResult(
            status="not_comparable_missing_thermal_family_probe",
            ready=None,
            n_rows=0,
            n_outside_tolerance=0,
        )

    py: Dict[Tuple[int, str, int, str], float] = {}
    for item in closure.elements:
        for row in item.thermal_rows:
            z = int(row["element_z"])
            channel = str(row["thermal_channel"])
            value = float(row["python_contribution_per_abundance"])
            for dimension, family in (
                ("data_type", int(row["data_type"])),
                ("rate_type", int(row["rate_type"])),
            ):
                key = (z, dimension, family, channel)
                py[key] = py.get(key, 0.0) + value

    xs: Dict[Tuple[int, str, int, str], float] = {}
    for dimension, rows, family_field in (
        ("data_type", data_type_probe_rows, "data_type"),
        ("rate_type", rate_type_probe_rows, "rate_type"),
    ):
        for row in rows:
            z = _int(row, "element_z")
            family = _int(row, family_field)
            for channel in ("heating", "cooling", "heating2", "cooling2"):
                xs[(z, dimension, family, channel)] = _float(row, channel)

    out: List[Dict[str, Any]] = []
    outside = 0
    for key in sorted(set(py) | set(xs)):
        py_value = py.get(key, 0.0)
        xs_value = xs.get(key, 0.0)
        ok = _within(py_value, xs_value, rtol, atol)
        outside += int(not ok)
        out.append({
            "element_z": key[0],
            "family_dimension": key[1],
            "family_index": key[2],
            "thermal_channel": key[3],
            "python_per_abundance": py_value,
            "xstar_per_abundance": xs_value,
            "absolute_difference": abs(py_value - xs_value),
            "relative_difference": abs(py_value - xs_value) / max(abs(xs_value), 1.0e-300),
            "within_tolerance": ok,
        })
    ready = outside == 0
    return ThermalFamilyParityResult(
        status="ready" if ready else "failed",
        ready=ready,
        n_rows=len(out),
        n_outside_tolerance=outside,
        rows=out,
        diagnostics={
            "rtol": float(rtol),
            "atol": float(atol),
            "diagnostic_only": True,
            "probe_values_enter_operator": False,
        },
    )


__all__ = [
    "SameCallMatrixParityResult",
    "ThermalFamilyParityResult",
    "compare_same_call_matrix_terms",
    "compare_thermal_families",
]
