"""XSTAR-vector matrix closure and element thermal diagnostics.

This module is diagnostic only.  It evaluates the translated Python matrix
with populations captured from XSTAR and never substitutes probe values into
the production operator or the native population solve.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from .local_zone import FixedStateCalcHMCAllResult
from .fortran_numbers import parse_fortran_float


@dataclass
class ElementXSTARVectorClosure:
    """Closure diagnostics for one translated element matrix."""

    element_z: int
    abundance: float
    n_compact_rows: int
    n_mapped_rows: int
    n_missing_rows: int
    xstar_vector_normalization: float
    xstar_vector_normalization_error: float
    native_l1_residual: float
    native_l1_relative_residual: float
    xstar_vector_l1_residual: float
    xstar_vector_l1_relative_residual: float
    xstar_vector_max_relative_residual: float
    xstar_vector_max_active_relative_residual: float
    n_active_rows: int
    n_active_rows_outside_tolerance: int
    ready: bool
    row_rows: List[Dict[str, Any]] = field(default_factory=list)
    thermal_rows: List[Dict[str, Any]] = field(default_factory=list)
    thermal_summary_rows: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class XSTARVectorMatrixClosureResult:
    """All-element fixed-state closure products."""

    elements: List[ElementXSTARVectorClosure]
    ready: bool
    n_active_rows_outside_tolerance: int
    n_missing_rows: int
    diagnostics: Dict[str, Any] = field(default_factory=dict)


def _compact_row_probe_population(
    *,
    element_z: int,
    compact_row: int,
    equilibrium: Any,
    level_index_by_key: Mapping[Tuple[int, int, int], int],
    level_by_index: Mapping[int, Mapping[str, str]],
) -> Tuple[Optional[float], Optional[int], Optional[Tuple[int, int, int]], float, int]:
    """Return one XSTAR population for a compact row and alias diagnostics."""

    basis_row = equilibrium.assembly.basis.row(int(compact_row))
    candidates: List[Tuple[float, int, Tuple[int, int, int]]] = []
    for role in basis_row.roles:
        key = (
            int(element_z),
            int(role.get("ion_stage", 0)),
            int(role.get("local_level", 0)),
        )
        global_index = level_index_by_key.get(key)
        record = level_by_index.get(int(global_index)) if global_index is not None else None
        if record is None:
            continue
        candidates.append((parse_fortran_float(record["xilevg"]), int(global_index), key))
    if not candidates:
        return None, None, None, 0.0, 0
    chosen = max(candidates, key=lambda item: abs(item[0]))
    spread = max(value for value, _, _ in candidates) - min(value for value, _, _ in candidates)
    return chosen[0], chosen[1], chosen[2], float(spread), len(candidates)


def _thermal_channel(coefficient: float, *, second_moment: bool) -> Tuple[str, float]:
    if coefficient > 0.0:
        return ("cooling2" if second_moment else "cooling"), coefficient
    return ("heating2" if second_moment else "heating"), -coefficient


def _captured_element_record(
    element_z: int,
    rows: Sequence[Mapping[str, str]],
) -> Optional[Mapping[str, str]]:
    matches = [row for row in rows if int(row["element_z"]) == int(element_z)]
    if not matches:
        return None
    # The bounded helper writes one selected call.  Multiple identical rows are
    # tolerated, but inconsistent values are handled by the parity layer.
    return matches[-1]


def build_xstar_vector_matrix_closure(
    result: FixedStateCalcHMCAllResult,
    *,
    level_probe_rows: Sequence[Mapping[str, str]],
    element_probe_rows: Sequence[Mapping[str, str]] = (),
    rtol: float = 5.0e-3,
    atol: float = 1.0e-12,
    active_row_scale_threshold: float = 1.0e-12,
) -> XSTARVectorMatrixClosureResult:
    """Evaluate every Python element matrix with the captured XSTAR vector.

    ``A_python @ x_XSTAR`` is a diagnostic closure residual.  The same captured
    vector is also used with Python ``cj/cj2`` coefficients to split element
    thermal differences into a population-vector part and a remaining
    coefficient/source-semantic part.
    """

    if rtol < 0.0 or atol < 0.0 or active_row_scale_threshold < 0.0:
        raise ValueError("closure tolerances and active row threshold must be nonnegative")

    level_by_index = {
        int(row["global_level_index"]): row
        for row in level_probe_rows
    }
    level_index_by_key = dict(getattr(result, "global_level_index_by_key", {}))
    outputs: List[ElementXSTARVectorClosure] = []

    for element in result.element_results:
        z = int(element.request.element_z)
        equilibrium = getattr(element, "equilibrium", None)
        solve = None if equilibrium is None else getattr(equilibrium, "solve", None)
        if equilibrium is None or solve is None:
            continue
        assembly = equilibrium.assembly
        n = int(assembly.basis.n_rows)
        xstar = np.zeros(n, dtype=float)
        mapped = np.zeros(n, dtype=bool)
        representative: Dict[int, Tuple[Optional[int], Optional[Tuple[int, int, int]], float, int]] = {}
        for compact_row in range(1, n + 1):
            value, global_index, key, alias_spread, n_aliases = _compact_row_probe_population(
                element_z=z,
                compact_row=compact_row,
                equilibrium=equilibrium,
                level_index_by_key=level_index_by_key,
                level_by_index=level_by_index,
            )
            representative[compact_row] = (global_index, key, alias_spread, n_aliases)
            if value is not None:
                xstar[compact_row - 1] = float(value)
                mapped[compact_row - 1] = True

        native = np.asarray(solve.populations, dtype=float)
        matrix = np.asarray(assembly.dense_matrix, dtype=float)
        residual = matrix @ xstar
        row_scale = np.sum(np.abs(matrix) * np.abs(xstar[np.newaxis, :]), axis=1)
        relative = np.abs(residual) / np.maximum(row_scale, 1.0e-300)
        active = row_scale >= float(active_row_scale_threshold)
        within = np.abs(residual) <= float(atol) + float(rtol) * row_scale

        row_rows: List[Dict[str, Any]] = []
        for row_index in range(1, n + 1):
            terms = [term for term in assembly.terms if int(term.row) == row_index]
            dominant = None
            dominant_value = 0.0
            for term in terms:
                column = min(n, int(term.column))
                contribution = float(term.aj1) * float(xstar[column - 1])
                if dominant is None or abs(contribution) > abs(dominant_value):
                    dominant = term
                    dominant_value = contribution
            global_index, key, alias_spread, n_aliases = representative[row_index]
            row_rows.append({
                "element_z": z,
                "compact_row": row_index,
                "representative_global_level_index": global_index,
                "representative_physical_key": "" if key is None else str(key),
                "n_probe_aliases": n_aliases,
                "probe_alias_population_spread": alias_spread,
                "python_population": float(native[row_index - 1]),
                "xstar_population": float(xstar[row_index - 1]),
                "population_difference": float(native[row_index - 1] - xstar[row_index - 1]),
                "mapped_from_probe": bool(mapped[row_index - 1]),
                "native_row_residual": float(solve.row_residual[row_index - 1]),
                "native_relative_row_residual": float(solve.relative_row_residual[row_index - 1]),
                "xstar_vector_row_residual": float(residual[row_index - 1]),
                "xstar_vector_row_scale": float(row_scale[row_index - 1]),
                "xstar_vector_relative_row_residual": float(relative[row_index - 1]),
                "active_row": bool(active[row_index - 1]),
                "within_closure_tolerance": bool(within[row_index - 1]),
                "dominant_record": 0 if dominant is None else int(dominant.record),
                "dominant_data_type": 0 if dominant is None else int(dominant.data_type),
                "dominant_rate_type": 0 if dominant is None else int(dominant.rate_type),
                "dominant_role": "" if dominant is None else str(dominant.role),
                "dominant_column": 0 if dominant is None else int(dominant.column),
                "dominant_matrix_population_contribution": float(dominant_value),
            })

        thermal_rows: List[Dict[str, Any]] = []
        channel_native = {name: 0.0 for name in ("heating", "cooling", "heating2", "cooling2")}
        channel_xstar = {name: 0.0 for name in channel_native}
        for term in assembly.terms:
            if int(term.row) != int(term.column):
                continue
            compact_row = min(n, int(term.row))
            for coefficient, second_moment in ((float(term.cj), False), (float(term.cj2), True)):
                if coefficient == 0.0:
                    continue
                channel, magnitude_coefficient = _thermal_channel(
                    coefficient, second_moment=second_moment
                )
                py_contribution = float(native[compact_row - 1]) * magnitude_coefficient
                xs_contribution = float(xstar[compact_row - 1]) * magnitude_coefficient
                channel_native[channel] += py_contribution
                channel_xstar[channel] += xs_contribution
                global_index, key, _, _ = representative[compact_row]
                thermal_rows.append({
                    "element_z": z,
                    "record": int(term.record),
                    "data_type": int(term.data_type),
                    "rate_type": int(term.rate_type),
                    "role": str(term.role),
                    "compact_row": compact_row,
                    "global_level_index": global_index,
                    "physical_key": "" if key is None else str(key),
                    "thermal_channel": channel,
                    "source_signed_coefficient": coefficient,
                    "magnitude_coefficient": magnitude_coefficient,
                    "python_population": float(native[compact_row - 1]),
                    "xstar_population": float(xstar[compact_row - 1]),
                    "python_contribution_per_abundance": py_contribution,
                    "xstar_vector_contribution_per_abundance": xs_contribution,
                    "population_effect_per_abundance": xs_contribution - py_contribution,
                })

        probe_record = _captured_element_record(z, element_probe_rows)
        captured_abundance = None if probe_record is None else parse_fortran_float(probe_record["abundance"])
        captured_scaled = {
            "heating": None if probe_record is None else parse_fortran_float(probe_record["htt"]),
            "cooling": None if probe_record is None else parse_fortran_float(probe_record["cll"]),
            "heating2": None if probe_record is None else parse_fortran_float(probe_record["htt2"]),
            "cooling2": None if probe_record is None else parse_fortran_float(probe_record["cll2"]),
        }
        thermal_summary_rows: List[Dict[str, Any]] = []
        for channel in ("heating", "cooling", "heating2", "cooling2"):
            captured_per_abundance = None
            if captured_abundance is not None and captured_abundance > 0.0:
                captured_per_abundance = float(captured_scaled[channel]) / captured_abundance
            xs_value = channel_xstar[channel]
            residual_to_xstar = None if captured_per_abundance is None else captured_per_abundance - xs_value
            relative_to_xstar = None
            if captured_per_abundance is not None:
                relative_to_xstar = abs(residual_to_xstar) / max(abs(captured_per_abundance), 1.0e-300)
            population_effect = xs_value - channel_native[channel]
            total_gap = None if captured_per_abundance is None else captured_per_abundance - channel_native[channel]
            if captured_per_abundance is None:
                diagnosis = "missing_xstar_element_probe"
            elif abs(total_gap) <= 1.0e-300:
                diagnosis = "closed"
            elif abs(residual_to_xstar) > abs(population_effect):
                diagnosis = "coefficient_or_source_semantics_dominated"
            else:
                diagnosis = "population_vector_dominated"
            thermal_summary_rows.append({
                "element_z": z,
                "thermal_channel": channel,
                "python_effective_abundance": float(element.request.abundance),
                "xstar_captured_abundance": captured_abundance,
                "python_native_per_abundance": channel_native[channel],
                "xstar_vector_python_coefficients_per_abundance": xs_value,
                "captured_xstar_per_abundance": captured_per_abundance,
                "total_python_to_xstar_gap_per_abundance": total_gap,
                "population_vector_effect_per_abundance": population_effect,
                "remaining_coefficient_or_semantics_gap_per_abundance": residual_to_xstar,
                "remaining_relative_gap": relative_to_xstar,
                "gap_diagnosis": diagnosis,
                "captured_xstar_scaled": captured_scaled[channel],
            })

        active_outside = int(np.count_nonzero(active & ~within))
        xstar_l1 = float(np.sum(np.abs(residual)))
        xstar_scale_l1 = float(np.sum(row_scale))
        outputs.append(ElementXSTARVectorClosure(
            element_z=z,
            abundance=float(element.request.abundance),
            n_compact_rows=n,
            n_mapped_rows=int(np.count_nonzero(mapped)),
            n_missing_rows=int(np.count_nonzero(~mapped)),
            xstar_vector_normalization=float(np.sum(xstar)),
            xstar_vector_normalization_error=abs(float(np.sum(xstar)) - 1.0),
            native_l1_residual=float(solve.l1_row_residual),
            native_l1_relative_residual=float(solve.l1_relative_row_residual),
            xstar_vector_l1_residual=xstar_l1,
            xstar_vector_l1_relative_residual=xstar_l1 / max(xstar_scale_l1, 1.0e-300),
            xstar_vector_max_relative_residual=float(np.max(relative)) if relative.size else 0.0,
            xstar_vector_max_active_relative_residual=(
                float(np.max(relative[active])) if np.any(active) else 0.0
            ),
            n_active_rows=int(np.count_nonzero(active)),
            n_active_rows_outside_tolerance=active_outside,
            ready=bool(np.all(mapped) and active_outside == 0),
            row_rows=row_rows,
            thermal_rows=thermal_rows,
            thermal_summary_rows=thermal_summary_rows,
        ))

    return XSTARVectorMatrixClosureResult(
        elements=outputs,
        ready=bool(outputs and all(item.ready for item in outputs)),
        n_active_rows_outside_tolerance=sum(item.n_active_rows_outside_tolerance for item in outputs),
        n_missing_rows=sum(item.n_missing_rows for item in outputs),
        diagnostics={
            "rtol": float(rtol),
            "atol": float(atol),
            "active_row_scale_threshold": float(active_row_scale_threshold),
            "diagnostic_only": True,
            "probe_values_enter_production_operator": False,
        },
    )


__all__ = [
    "ElementXSTARVectorClosure",
    "XSTARVectorMatrixClosureResult",
    "build_xstar_vector_matrix_closure",
]
