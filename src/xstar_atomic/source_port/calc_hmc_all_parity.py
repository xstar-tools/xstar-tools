"""Parity checks for the bounded XSTAR ``calc_hmc_all`` probe."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence
import csv
import json
import re

from .local_zone import FixedStateCalcHMCAllResult
from .calc_hmc_all_closure import (
    XSTARVectorMatrixClosureResult,
    build_xstar_vector_matrix_closure,
)
from .fortran_numbers import parse_fortran_float
from .calc_hmc_all_matrix_parity import (
    SameCallMatrixParityResult,
    ThermalFamilyParityResult,
    Rate7CJ2DiagnosisResult,
    compare_same_call_matrix_terms,
    compare_thermal_families,
    diagnose_rate7_cj2_records,
)
from .msolvelucy_final_snapshot import (
    MSolveLucyFinalSnapshotParityResult,
    compare_msolvelucy_final_snapshot,
)
from .leveltemp_energy_parity import (
    LeveltempEnergyParityResult,
    compare_leveltemp_energy_probe,
)
from .msolvelucy_initial_state import (
    MSolveLucyInitialPopulationParityResult,
    compare_msolvelucy_initial_population,
    compare_msolvelucy_initial_populations,
    load_msolvelucy_initial_population_reference,
)


class CalcHMCAllParityError(RuntimeError):
    """Raised when bounded probe products are missing or malformed."""


@dataclass(frozen=True)
class CalcHMCAllProbeCritfReference:
    """Captured source ``critf`` and element limits for one probe call."""

    call_id: int
    element_z: int
    critf: float
    mml: int
    mmu: int


@dataclass(frozen=True)
class CalcHMCAllProbeElementReference:
    """Captured element-array context for one bounded calc_hmc_all call."""

    call_id: int
    element_index: int
    element_z: int
    abundance: float
    mml: int
    mmu: int


@dataclass(frozen=True)
class CalcHMCAllParityRow:
    component: str
    key: str
    python_value: float
    xstar_value: float
    absolute_difference: float
    relative_difference: float
    within_tolerance: bool
    parity_class: str = "other"
    active_level: bool = False
    milestone_blocking: bool = True


@dataclass
class CalcHMCAllPreContinuumParityResult:
    call_id: int
    rows: List[CalcHMCAllParityRow]
    n_missing_python_keys: int
    n_missing_xstar_keys: int
    max_absolute_difference: float
    max_relative_difference: float
    n_outside_tolerance: int
    n_blocking_outside_tolerance: int
    pre_matrix_ready: bool
    pre_continuum_state_ready: bool
    pre_continuum_summary_ready: Optional[bool]
    pre_continuum_summary_status: str
    element_array_ready: Optional[bool]
    element_array_status: str
    global_ion_ready: bool
    global_level_primary_ready: bool
    global_level_active_ready: bool
    global_level_derived_ready: bool
    global_level_ready: bool
    global_arrays_ready: bool
    matrix_closure_ready: Optional[bool]
    matrix_closure_status: str
    element_thermal_diagnostic_ready: bool
    same_call_matrix_ready: Optional[bool]
    same_call_matrix_status: str
    same_call_matrix_topology_ready: Optional[bool]
    same_call_matrix_coefficient_ready: Optional[bool]
    same_call_matrix_active_closure_ready: Optional[bool]
    thermal_family_ready: Optional[bool]
    thermal_family_status: str
    initial_solver_population_ready: Optional[bool]
    initial_solver_population_status: str
    final_solver_snapshot_ready: Optional[bool]
    final_solver_snapshot_status: str
    final_solver_same_iteration_ready: Optional[bool]
    final_solver_iteration_tuple_ready: Optional[bool]
    final_solver_matrix_dimension_ready: Optional[bool]
    final_solver_population_columns_ready: Optional[bool]
    final_solver_topology_ready: Optional[bool]
    final_solver_coefficient_ready: Optional[bool]
    final_solver_active_population_ready: Optional[bool]
    final_solver_outer_start_ready: Optional[bool]
    final_solver_source_xtot_ready: Optional[bool]
    rate7_cj2_ready: Optional[bool]
    rate7_cj2_status: str
    type53_rate7_cj2_ready: Optional[bool]
    leveltemp_energy_ready: Optional[bool]
    leveltemp_energy_status: str
    type53_leveltemp_energy_ready: Optional[bool]
    oxygen_reassessment_ready: Optional[bool]
    oxygen_reassessment_status: str
    acceptance_gate_ready: bool
    oxygen_pre_continuum_acceptance_ready: bool
    all_element_pre_continuum_acceptance_ready: Optional[bool]
    all_element_active_solver_ready: Optional[bool]
    all_element_thermal_ready: Optional[bool]
    all_element_element_readiness: List[Dict[str, Any]]
    strict_parity_ready: bool
    parity_ready: bool
    active_population_threshold: float
    matrix_closure: Optional[XSTARVectorMatrixClosureResult] = None
    same_call_matrix: Optional[SameCallMatrixParityResult] = None
    thermal_family_parity: Optional[ThermalFamilyParityResult] = None
    initial_solver_population: Optional[MSolveLucyInitialPopulationParityResult] = None
    final_solver_snapshot: Optional[MSolveLucyFinalSnapshotParityResult] = None
    rate7_cj2_diagnosis: Optional[Rate7CJ2DiagnosisResult] = None
    leveltemp_energy_parity: Optional[LeveltempEnergyParityResult] = None
    population_weighted_attribution: List[Dict[str, Any]] = field(default_factory=list)
    active_population_ion_resolution: List[Dict[str, Any]] = field(default_factory=list)
    oxygen_reassessment: List[Dict[str, Any]] = field(default_factory=list)
    diagnostics: Dict[str, Any] = field(default_factory=dict)


def _read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        raise CalcHMCAllParityError(f"missing probe file: {path}")
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _read_csv_optional(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _resolve_call_id(rows: Sequence[Mapping[str, str]], requested: Optional[int]) -> int:
    ids = sorted({int(row["calc_hmc_all_call_id"]) for row in rows})
    if not ids:
        raise CalcHMCAllParityError("probe contains no calc_hmc_all call ids")
    if requested is None:
        return ids[-1]
    if int(requested) not in ids:
        raise CalcHMCAllParityError(f"call id {requested} not present; available={ids}")
    return int(requested)


def _unique_int(rows: Sequence[Mapping[str, str]], name: str, *, context: str) -> int:
    values = {int(row[name]) for row in rows}
    if len(values) != 1:
        raise CalcHMCAllParityError(f"expected one {name} for {context}, got {sorted(values)}")
    return values.pop()


def _unique_float(rows: Sequence[Mapping[str, str]], name: str, *, context: str) -> float:
    values = [parse_fortran_float(row[name]) for row in rows]
    if not values:
        raise CalcHMCAllParityError(f"missing {name} for {context}")
    reference = values[0]
    if any(abs(value - reference) > max(1.0e-15, 1.0e-12 * abs(reference)) for value in values[1:]):
        raise CalcHMCAllParityError(f"inconsistent {name} for {context}: {values}")
    return reference


def load_calc_hmc_all_probe_critf(
    probe_dir: str | Path,
    *,
    element_z: int,
    call_id: Optional[int] = None,
) -> CalcHMCAllProbeCritfReference:
    """Read the effective source ``critf`` before running the Python core."""

    root = Path(probe_dir)
    rows = _read_csv(root / "xstar_calc_hmc_element_pre_matrix_probe.csv")
    selected_call = _resolve_call_id(rows, call_id)
    rows = [
        row for row in rows
        if int(row["calc_hmc_all_call_id"]) == selected_call
        and int(row["element_z"]) == int(element_z)
    ]
    if not rows:
        raise CalcHMCAllParityError(
            f"no pre-matrix rows for call {selected_call}, element Z={element_z}"
        )
    return CalcHMCAllProbeCritfReference(
        call_id=selected_call,
        element_z=int(element_z),
        critf=_unique_float(rows, "critf", context=f"call {selected_call}, Z={element_z}"),
        mml=_unique_int(rows, "mml", context=f"call {selected_call}, Z={element_z}"),
        mmu=_unique_int(rows, "mmu", context=f"call {selected_call}, Z={element_z}"),
    )


def load_calc_hmc_all_probe_element_reference(
    probe_dir: str | Path,
    *,
    element_z: int,
    call_id: Optional[int] = None,
) -> CalcHMCAllProbeElementReference:
    """Read the captured XSTAR element abundance and array index."""

    root = Path(probe_dir)
    rows = _read_csv(root / "xstar_calc_hmc_all_pre_continuum_elements_probe.csv")
    selected_call = _resolve_call_id(rows, call_id)
    rows = [
        row for row in rows
        if int(row["calc_hmc_all_call_id"]) == selected_call
        and int(row["element_z"]) == int(element_z)
    ]
    if not rows:
        raise CalcHMCAllParityError(
            f"no element-array row for call {selected_call}, element Z={element_z}"
        )
    return CalcHMCAllProbeElementReference(
        call_id=selected_call,
        element_index=_unique_int(rows, "element_index", context=f"call {selected_call}, Z={element_z}"),
        element_z=int(element_z),
        abundance=_unique_float(rows, "abundance", context=f"call {selected_call}, Z={element_z}"),
        mml=_unique_int(rows, "mml", context=f"call {selected_call}, Z={element_z}"),
        mmu=_unique_int(rows, "mmu", context=f"call {selected_call}, Z={element_z}"),
    )


def _metric(
    component: str,
    key: str,
    python: float,
    xstar: float,
    *,
    rtol: float,
    atol: float,
    parity_class: str = "other",
    active_level: bool = False,
    milestone_blocking: bool = True,
) -> CalcHMCAllParityRow:
    diff = abs(float(python) - float(xstar))
    scale = max(abs(float(python)), abs(float(xstar)), 1.0e-300)
    rel = diff / scale
    ok = diff <= float(atol) + float(rtol) * abs(float(xstar))
    return CalcHMCAllParityRow(
        component=component,
        key=key,
        python_value=float(python),
        xstar_value=float(xstar),
        absolute_difference=diff,
        relative_difference=rel,
        within_tolerance=bool(ok),
        parity_class=parity_class,
        active_level=bool(active_level),
        milestone_blocking=bool(milestone_blocking),
    )


def _nonzero(values: Sequence[float | int]) -> bool:
    return any(float(value) != 0.0 for value in values)


def _xstar_population_for_compact_row(
    *,
    element_z: int,
    compact_row: int,
    equilibrium: Any,
    level_index_by_key: Mapping[tuple[int, int, int], int],
    level_by_index: Mapping[int, Mapping[str, str]],
) -> tuple[Optional[float], Optional[int], Optional[tuple[int, int, int]]]:
    basis_row = equilibrium.assembly.basis.row(int(compact_row))
    candidates: List[tuple[float, int, tuple[int, int, int]]] = []
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
        candidates.append((float(record["xilevg"]), int(global_index), key))
    if not candidates:
        return None, None, None
    # Shared aliases represent one compact population. Prefer the nonzero or
    # largest-magnitude captured role, which is robust to zero-filled aliases.
    return max(candidates, key=lambda item: abs(item[0]))


def _build_population_weighted_attribution(
    *,
    result: FixedStateCalcHMCAllResult,
    failed_level_rows: Sequence[CalcHMCAllParityRow],
    level_by_index: Mapping[int, Mapping[str, str]],
    level_index_by_key: Mapping[tuple[int, int, int], int],
) -> List[Dict[str, Any]]:
    """Attribute failing xilevg/alphag rows to the largest Python feed term.

    The XSTAR coefficient for the term is not available in this bounded probe,
    so the audit cleanly separates the population-factor estimate from an
    unavailable rate-difference term. No XSTAR value enters the operator.
    """

    failed_indices: Dict[int, set[str]] = {}
    for row in failed_level_rows:
        if row.within_tolerance or row.component not in {
            "global_level_xilevg", "global_level_alphag"
        }:
            continue
        try:
            global_index = int(row.key.split("global_level=", 1)[1].split(",", 1)[0])
        except (IndexError, ValueError):
            continue
        failed_indices.setdefault(global_index, set()).add(row.component)

    reverse_level_map = {int(index): key for key, index in level_index_by_key.items()}
    element_by_z = {
        int(item.request.element_z): item
        for item in getattr(result, "element_results", ())
        if getattr(item, "equilibrium", None) is not None
    }
    rows: List[Dict[str, Any]] = []
    for global_index, components in sorted(failed_indices.items()):
        key = reverse_level_map.get(global_index)
        if key is None:
            continue
        z, stage, local_level = key
        element = element_by_z.get(int(z))
        if element is None or element.equilibrium.solve is None:
            continue
        equilibrium = element.equilibrium
        block = next(
            (b for b in equilibrium.assembly.basis.blocks if int(b.ion_stage) == int(stage)),
            None,
        )
        if block is None:
            continue
        target_row = int(block.compact_index(local_level))
        populations = equilibrium.solve.populations
        candidates = []
        for term in equilibrium.assembly.terms:
            if int(term.row) != target_row or int(term.row) == int(term.column):
                continue
            feed_row = min(len(populations), int(term.column))
            python_feed_population = float(populations[feed_row - 1])
            coefficient = abs(float(term.aj1))
            weighted = coefficient * python_feed_population
            candidates.append((weighted, coefficient, python_feed_population, term, feed_row))
        if not candidates:
            continue
        weighted, coefficient, py_feed, term, feed_row = max(candidates, key=lambda item: item[0])
        xs_feed, xs_feed_global, xs_feed_key = _xstar_population_for_compact_row(
            element_z=z,
            compact_row=feed_row,
            equilibrium=equilibrium,
            level_index_by_key=level_index_by_key,
            level_by_index=level_by_index,
        )
        xstar_target = level_by_index.get(global_index, {})
        xs_weighted = None if xs_feed is None else coefficient * float(xs_feed)
        rows.append({
            "target_global_level_index": global_index,
            "element_z": z,
            "ion_stage": stage,
            "local_level": local_level,
            "target_compact_row": target_row,
            "failing_components": ";".join(sorted(components)),
            "python_target_population": float(result.xilevg.get(key, 0.0)),
            "xstar_target_population": float(xstar_target.get("xilevg", 0.0)),
            "python_target_alpha": float(result.alphag.get(key, 0.0)),
            "xstar_target_alpha": float(xstar_target.get("alphag", 0.0)),
            "dominant_record": int(term.record),
            "dominant_data_type": int(term.data_type),
            "dominant_rate_type": int(term.rate_type),
            "dominant_term_role": str(term.role),
            "dominant_source_row": int(term.row),
            "dominant_source_column": int(term.column),
            "dominant_coefficient_s_inv": coefficient,
            "python_feeding_population": py_feed,
            "xstar_feeding_population": xs_feed,
            "xstar_feeding_global_level_index": xs_feed_global,
            "xstar_feeding_physical_key": "" if xs_feed_key is None else str(xs_feed_key),
            "python_population_weighted_contribution_s_inv": weighted,
            "xstar_population_weighted_contribution_same_coefficient_s_inv": xs_weighted,
            "estimated_population_factor_difference_s_inv": (
                None if xs_weighted is None else weighted - xs_weighted
            ),
            "rate_difference_status": "not_available_without_xstar_matrix_term_probe",
            "diagnostic_role": "fixed_coefficient_population_factor_attribution",
        })
    return rows



def _build_active_population_ion_matrix_resolution(
    *,
    result: FixedStateCalcHMCAllResult,
    parity_rows: Sequence[CalcHMCAllParityRow],
    same_call_matrix: SameCallMatrixParityResult,
) -> List[Dict[str, Any]]:
    """Classify failed active-level and global-ion rows with same-call evidence."""

    elements = {
        int(item.request.element_z): item
        for item in getattr(result, "element_results", ())
        if getattr(item, "equilibrium", None) is not None
    }
    active_by_row = {
        (int(row.get("element_z", 0)), int(row.get("compact_row", 0))): row
        for row in same_call_matrix.active_row_rows
    }
    terms_by_row: Dict[tuple[int, int], List[Mapping[str, Any]]] = {}
    for row in same_call_matrix.term_rows:
        if row.get("python_row_compact") in (None, ""):
            continue
        key = (int(row.get("element_z", 0)), int(row["python_row_compact"]))
        terms_by_row.setdefault(key, []).append(row)

    output: List[Dict[str, Any]] = []
    level_pattern = re.compile(
        r"global_level=(?P<global>\d+),Z=(?P<z>\d+),stage=(?P<stage>\d+),level=(?P<level>\d+)"
    )
    ion_pattern = re.compile(
        r"global_ion=(?P<global>\d+),Z=(?P<z>\d+),stage=(?P<stage>\d+)"
    )
    for metric in parity_rows:
        if metric.within_tolerance:
            continue
        is_active_level = (
            metric.component in {"global_level_xilevg", "global_level_alphag"}
            and metric.milestone_blocking
        )
        is_global_ion = metric.component.startswith("global_ion_")
        if not (is_active_level or is_global_ion):
            continue
        match = level_pattern.fullmatch(metric.key) if is_active_level else ion_pattern.fullmatch(metric.key)
        if match is None:
            continue
        z = int(match.group("z"))
        stage = int(match.group("stage"))
        global_index = int(match.group("global"))
        element = elements.get(z)
        if element is None:
            compact_rows: List[int] = []
        else:
            basis = element.equilibrium.assembly.basis
            if is_active_level:
                local_level = int(match.group("level"))
                compact_rows = sorted({
                    int(row.compact_index)
                    for row in basis.rows
                    if any(
                        int(role.get("ion_stage", 0)) == stage
                        and int(role.get("local_level", 0)) == local_level
                        for role in row.roles
                    )
                })
            else:
                local_level = None
                compact_rows = sorted({
                    int(row.compact_index)
                    for row in basis.rows
                    if any(int(role.get("ion_stage", 0)) == stage for role in row.roles)
                })

        active_candidates = [
            active_by_row[(z, compact)]
            for compact in compact_rows
            if (z, compact) in active_by_row
        ]
        dominant_active = max(
            active_candidates,
            key=lambda row: abs(float(row.get("matrix_difference_xstar_vector_residual", 0.0))),
            default=None,
        )
        term_candidates = [
            row for compact in compact_rows for row in terms_by_row.get((z, compact), ())
        ]
        dominant_term = max(
            term_candidates,
            key=lambda row: abs(float(row.get("delta_population_weighted_aj1", 0.0))),
            default=None,
        )
        if dominant_active is not None:
            classification = str(dominant_active.get("classification", "same_call_matrix_attributed"))
        elif dominant_term is not None and not bool(dominant_term.get("within_tolerance", True)):
            classification = "coefficient_driven_nonactive_row"
        else:
            classification = "population_propagation_or_ion_aggregation"
        output.append({
            "component": metric.component,
            "key": metric.key,
            "element_z": z,
            "ion_stage": stage,
            "local_level": local_level,
            "global_index": global_index,
            "python_value": metric.python_value,
            "xstar_value": metric.xstar_value,
            "absolute_difference": metric.absolute_difference,
            "relative_difference": metric.relative_difference,
            "compact_rows": ";".join(str(value) for value in compact_rows),
            "n_compact_rows": len(compact_rows),
            "classification": classification,
            "dominant_compact_row": None if dominant_active is None else dominant_active.get("compact_row"),
            "dominant_python_matrix_residual": None if dominant_active is None else dominant_active.get("python_matrix_xstar_vector_residual"),
            "dominant_xstar_matrix_residual": None if dominant_active is None else dominant_active.get("xstar_matrix_xstar_vector_residual"),
            "dominant_matrix_difference_residual": None if dominant_active is None else dominant_active.get("matrix_difference_xstar_vector_residual"),
            "dominant_term_index": None if dominant_term is None else dominant_term.get("term_index"),
            "dominant_record": None if dominant_term is None else dominant_term.get("record"),
            "dominant_data_type": None if dominant_term is None else dominant_term.get("data_type"),
            "dominant_rate_type": None if dominant_term is None else dominant_term.get("rate_type"),
            "dominant_role": None if dominant_term is None else dominant_term.get("role"),
            "dominant_python_aj1": None if dominant_term is None else dominant_term.get("python_aj1"),
            "dominant_xstar_aj1": None if dominant_term is None else dominant_term.get("xstar_aj1"),
            "dominant_population_weighted_coefficient_difference": (
                None if dominant_term is None else dominant_term.get("delta_population_weighted_aj1")
            ),
            "diagnostic_role": "same_call_matrix_resolution_of_active_level_or_global_ion_residual",
        })
    return output

def _parity_row_element_z(row: CalcHMCAllParityRow) -> Optional[int]:
    """Extract a source element from the stable diagnostic key."""

    match = re.search(r"(?:^|,)Z=(\d+)", str(row.key))
    if match:
        return int(match.group(1))
    return None


def _all_element_acceptance_summary(
    result: FixedStateCalcHMCAllResult,
    *,
    rows: Sequence[CalcHMCAllParityRow],
    blocking_outside: int,
    initial: MSolveLucyInitialPopulationParityResult,
    matrix: SameCallMatrixParityResult,
    thermal: ThermalFamilyParityResult,
    final: MSolveLucyFinalSnapshotParityResult,
) -> tuple[Optional[bool], Optional[bool], Optional[bool], List[Dict[str, Any]]]:
    """Build the v0.4.36 H/He/O all-element acceptance gate.

    The gate is defined only for the complete positive-abundance element mode.
    It keeps the accepted oxygen call-73 product as an independent mandatory
    regression and requires each captured element to pass initial state,
    record-keyed matrix topology/active closure, active final and outer-start
    populations, source ``xtot``, and thermal-family parity.
    """

    if getattr(result, "diagnostics", {}).get("element_scope") != "all_positive_abundance_elements_from_xstar_probe":
        return None, None, None, []

    element_zs = sorted(int(item.request.element_z) for item in result.element_results)
    initial_by_z = {
        int(item.get("element_z", 0)): item
        for item in initial.element_results
    }
    matrix_rows_by_z: Dict[int, List[Dict[str, Any]]] = {}
    for row in matrix.term_rows:
        matrix_rows_by_z.setdefault(int(row.get("element_z", 0)), []).append(row)
    matrix_active_bad_by_z: Dict[int, int] = {z: 0 for z in element_zs}
    matrix_active_seen = {
        int(z) for z in matrix.diagnostics.get("closure_elements_evaluated", [])
    }
    for row in matrix.active_row_rows:
        z = int(row.get("element_z", 0))
        if not bool(row.get("matrix_difference_within_tolerance", False)):
            matrix_active_bad_by_z[z] = matrix_active_bad_by_z.get(z, 0) + 1

    final_rows_by_z: Dict[int, List[Dict[str, Any]]] = {}
    for row in final.population_rows:
        final_rows_by_z.setdefault(int(row.get("element_z", 0)), []).append(row)
    xtot_rows_by_z: Dict[int, List[Dict[str, Any]]] = {}
    for row in final.ion_total_rows:
        xtot_rows_by_z.setdefault(int(row.get("element_z", 0)), []).append(row)
    thermal_rows_by_z: Dict[int, List[Dict[str, Any]]] = {}
    for row in thermal.rows:
        thermal_rows_by_z.setdefault(int(row.get("element_z", 0)), []).append(row)

    blocker_by_z: Dict[int, int] = {z: 0 for z in element_zs}
    for row in rows:
        z = _parity_row_element_z(row)
        if z in blocker_by_z and row.milestone_blocking and not row.within_tolerance:
            blocker_by_z[z] += 1

    summaries: List[Dict[str, Any]] = []
    for z in element_zs:
        irow = initial_by_z.get(z, {})
        mrows = matrix_rows_by_z.get(z, [])
        frows = final_rows_by_z.get(z, [])
        xrows = xtot_rows_by_z.get(z, [])
        trows = thermal_rows_by_z.get(z, [])
        initial_ready = bool(irow and irow.get("ready") is True)
        topology_ready = bool(mrows and all(bool(row.get("topology_match", False)) for row in mrows))
        active_matrix_ready = bool(
            z in matrix_active_seen and matrix_active_bad_by_z.get(z, 0) == 0
        )
        active_final_rows = [row for row in frows if bool(row.get("active_population", False))]
        final_ready = bool(
            active_final_rows
            and all(bool(row.get("final_population_within_tolerance", False))
                    for row in active_final_rows)
        )
        outer_ready = bool(
            active_final_rows
            and all(bool(row.get("outer_start_population_within_tolerance", False))
                    for row in active_final_rows)
        )
        xtot_ready = bool(
            xrows and all(bool(row.get("source_xtot_within_tolerance", False)) for row in xrows)
        )
        thermal_ready = bool(
            trows and all(bool(row.get("within_tolerance", False)) for row in trows)
        )
        no_blockers = blocker_by_z.get(z, 0) == 0
        detailed_ready = bool(
            initial_ready and topology_ready and active_matrix_ready
            and final_ready and outer_ready and xtot_ready and thermal_ready
            and no_blockers
        )
        summaries.append({
            "element_z": z,
            "initial_population_ready": initial_ready,
            "matrix_topology_ready": topology_ready,
            "matrix_active_closure_ready": active_matrix_ready,
            "active_final_population_ready": final_ready,
            "active_outer_start_population_ready": outer_ready,
            "source_xtot_ready": xtot_ready,
            "thermal_family_ready": thermal_ready,
            "n_milestone_blocking_rows": blocker_by_z.get(z, 0),
            "detailed_parity_ready": detailed_ready,
            "n_initial_population_rows": int(irow.get("n_rows", 0) or 0),
            "n_matrix_term_rows": len(mrows),
            "n_active_final_population_rows": len(active_final_rows),
            "n_thermal_family_rows": len(trows),
        })

    active_solver_ready = bool(
        summaries and all(
            row["active_final_population_ready"]
            and row["active_outer_start_population_ready"]
            and row["source_xtot_ready"]
            for row in summaries
        )
    )
    all_thermal_ready = bool(summaries and all(row["thermal_family_ready"] for row in summaries))
    oxygen_regression_ready = result.diagnostics.get("oxygen_call73_regression_ready") is True
    ready = bool(
        oxygen_regression_ready
        and summaries
        and all(row["detailed_parity_ready"] for row in summaries)
        and active_solver_ready
        and all_thermal_ready
        and blocking_outside == 0
    )
    return ready, active_solver_ready, all_thermal_ready, summaries


def compare_calc_hmc_all_pre_continuum_probe(
    result: FixedStateCalcHMCAllResult,
    probe_dir: str | Path,
    *,
    call_id: Optional[int] = None,
    rtol: float = 5.0e-3,
    atol: float = 1.0e-12,
    active_population_threshold: float = 1.0e-12,
    matrix_closure_active_row_scale_threshold: float = 1.0e-12,
) -> CalcHMCAllPreContinuumParityResult:
    """Compare Python first-pass and pre-``comp2`` products to XSTAR.

    Strict comparisons remain in the details table. The Milestone-4 level gate
    requires all LTE/gamma rows and active-population xilevg/alphag rows; tiny
    inactive populations and derived departure/record products are classified
    separately rather than silently discarded.
    """

    if (rtol < 0.0 or atol < 0.0 or active_population_threshold < 0.0
            or matrix_closure_active_row_scale_threshold < 0.0):
        raise CalcHMCAllParityError(
            "rtol, atol, population threshold, and closure row threshold must be nonnegative"
        )
    root = Path(probe_dir)
    element_rows_all = _read_csv(root / "xstar_calc_hmc_element_pre_matrix_probe.csv")
    summary_rows_all = _read_csv(root / "xstar_calc_hmc_all_pre_continuum_summary_probe.csv")
    ion_rows_all = _read_csv(root / "xstar_calc_hmc_all_pre_continuum_ions_probe.csv")
    level_rows_all = _read_csv(root / "xstar_calc_hmc_all_pre_continuum_levels_probe.csv")
    element_array_path = root / "xstar_calc_hmc_all_pre_continuum_elements_probe.csv"
    element_array_rows_all = _read_csv_optional(element_array_path)
    matrix_rows_all = _read_csv_optional(root / "xstar_calc_hmc_all_matrix_terms_probe.csv")
    thermal_data_type_rows_all = _read_csv_optional(
        root / "xstar_calc_hmc_all_thermal_data_type_probe.csv"
    )
    thermal_rate_type_rows_all = _read_csv_optional(
        root / "xstar_calc_hmc_all_thermal_rate_type_probe.csv"
    )
    final_matrix_rows_all = _read_csv_optional(
        root / "xstar_calc_hmc_all_msolvelucy_final_matrix_probe.csv"
    )
    final_population_rows_all = _read_csv_optional(
        root / "xstar_calc_hmc_all_msolvelucy_final_population_probe.csv"
    )
    initial_population_rows_all = _read_csv_optional(
        root / "xstar_calc_hmc_all_msolvelucy_initial_population_probe.csv"
    )
    leveltemp_energy_rows_all = _read_csv_optional(
        root / "xstar_calc_hmc_all_leveltemp_energy_probe.csv"
    )
    all_probe_rows = (
        element_rows_all + summary_rows_all + ion_rows_all + level_rows_all
        + element_array_rows_all + matrix_rows_all
        + thermal_data_type_rows_all + thermal_rate_type_rows_all
        + final_matrix_rows_all + final_population_rows_all
        + initial_population_rows_all + leveltemp_energy_rows_all
    )
    selected_call = _resolve_call_id(all_probe_rows, call_id)
    element_rows = [r for r in element_rows_all if int(r["calc_hmc_all_call_id"]) == selected_call]
    summary_rows = [r for r in summary_rows_all if int(r["calc_hmc_all_call_id"]) == selected_call]
    ion_rows = [r for r in ion_rows_all if int(r["calc_hmc_all_call_id"]) == selected_call]
    level_rows = [r for r in level_rows_all if int(r["calc_hmc_all_call_id"]) == selected_call]
    element_array_rows = [
        r for r in element_array_rows_all
        if int(r["calc_hmc_all_call_id"]) == selected_call
    ]
    matrix_rows = [
        r for r in matrix_rows_all
        if int(r["calc_hmc_all_call_id"]) == selected_call
    ]
    thermal_data_type_rows = [
        r for r in thermal_data_type_rows_all
        if int(r["calc_hmc_all_call_id"]) == selected_call
    ]
    thermal_rate_type_rows = [
        r for r in thermal_rate_type_rows_all
        if int(r["calc_hmc_all_call_id"]) == selected_call
    ]
    final_matrix_rows = [
        r for r in final_matrix_rows_all
        if int(r["calc_hmc_all_call_id"]) == selected_call
    ]
    final_population_rows = [
        r for r in final_population_rows_all
        if int(r["calc_hmc_all_call_id"]) == selected_call
    ]
    initial_population_rows = [
        r for r in initial_population_rows_all
        if int(r["calc_hmc_all_call_id"]) == selected_call
    ]
    leveltemp_energy_rows = [
        r for r in leveltemp_energy_rows_all
        if int(r["calc_hmc_all_call_id"]) == selected_call
    ]
    if len(summary_rows) != 1:
        raise CalcHMCAllParityError(
            f"expected one pre-continuum summary for call {selected_call}, got {len(summary_rows)}"
        )

    rows: List[CalcHMCAllParityRow] = []
    pre_matrix_missing_python = pre_matrix_missing_xstar = 0
    ion_missing_python = ion_missing_xstar = 0
    level_missing_python = level_missing_xstar = 0
    element_missing_python = element_missing_xstar = 0

    xstar_keys = {(int(r["element_z"]), int(r["ion_stage"])) for r in element_rows}
    probe_elements = {z for z, _ in xstar_keys}
    python_keys = {key for key in result.preliminary_ion_fractions if key[0] in probe_elements}
    pre_matrix_missing_python += len(xstar_keys - python_keys)
    pre_matrix_missing_xstar += len(python_keys - xstar_keys)
    for record in element_rows:
        z, stage = int(record["element_z"]), int(record["ion_stage"])
        key = (z, stage)
        if key not in result.preliminary_ion_fractions:
            continue
        rows.append(_metric(
            "istruc_fraction", f"Z={z},stage={stage}",
            result.preliminary_ion_fractions[key], float(record["xitp"]),
            rtol=rtol, atol=atol, parity_class="pre_matrix",
        ))
        if stage <= z:
            rows.append(_metric(
                "calc_ion_rates_pirt", f"Z={z},stage={stage}",
                result.preliminary_pirt.get(key, 0.0), float(record["pirt"]),
                rtol=rtol, atol=atol, parity_class="pre_matrix",
            ))
            rows.append(_metric(
                "calc_ion_rates_rrrt", f"Z={z},stage={stage}",
                result.preliminary_rrrt.get(key, 0.0), float(record["rrrt"]),
                rtol=rtol, atol=atol, parity_class="pre_matrix",
            ))

    for z in sorted(probe_elements):
        zrows = [row for row in element_rows if int(row["element_z"]) == z]
        x_mml = _unique_int(zrows, "mml", context=f"call {selected_call}, Z={z}")
        x_mmu = _unique_int(zrows, "mmu", context=f"call {selected_call}, Z={z}")
        x_critf = _unique_float(zrows, "critf", context=f"call {selected_call}, Z={z}")
        rows.extend((
            _metric("ion_limit_mml", f"Z={z}", result.mml.get(z, 0), x_mml,
                    rtol=0.0, atol=0.0, parity_class="pre_matrix"),
            _metric("ion_limit_mmu", f"Z={z}", result.mmu.get(z, 0), x_mmu,
                    rtol=0.0, atol=0.0, parity_class="pre_matrix"),
        ))
        python_critf = next(
            (float(item.request.critf) for item in result.element_results
             if int(item.request.element_z) == z), 0.0,
        )
        rows.append(_metric(
            "ion_limit_critf", f"Z={z}", python_critf, x_critf,
            rtol=0.0, atol=0.0, parity_class="pre_matrix",
        ))

    summary = summary_rows[0]
    for name, python_value, xstar_value in (
        ("temperature_k", result.temperature_k, float(summary["temperature_k"])),
        ("xee", result.electron_fraction_xee, float(summary["xee"])),
        ("xpx", result.hydrogen_density_cm3, float(summary["xpx"])),
    ):
        rows.append(_metric(
            "pre_continuum_state", name, python_value, xstar_value,
            rtol=rtol, atol=atol, parity_class="runtime_state",
        ))
    state_ready = all(row.within_tolerance for row in rows if row.component == "pre_continuum_state")

    summary_comparable = bool(getattr(result, "charge_closure_scope_complete", True))
    deferred_summary_fields: List[str] = []
    if summary_comparable:
        for name, python_value, xstar_value in (
            ("httot", result.httot, float(summary["httot"])),
            ("cltot", result.cltot, float(summary["cltot"])),
            ("httot2", result.httot2, float(summary["httot2"])),
            ("cltot2", result.cltot2, float(summary["cltot2"])),
            ("enelec", result.electron_contribution, float(summary["enelec"])),
            ("elcter", result.elcter, float(summary["elcter"])),
        ):
            rows.append(_metric(
                "pre_continuum_summary", name, python_value, xstar_value,
                rtol=rtol, atol=atol, parity_class="all_element_summary",
            ))
        summary_ready: Optional[bool] = all(
            row.within_tolerance for row in rows if row.component == "pre_continuum_summary"
        )
        summary_status = "ready" if summary_ready else "failed"
    else:
        summary_ready = None
        summary_status = "not_comparable_subset_scope"
        deferred_summary_fields = ["httot", "cltot", "httot2", "cltot2", "enelec", "elcter"]

    ion_by_index = {int(row["global_ion_index"]): row for row in ion_rows}
    ion_index_by_key = dict(getattr(result, "global_ion_index_by_key", {}))
    ion_components = (
        ("global_ion_xiin", result.ion_fractions, "xiin"),
        ("global_ion_rrrt", result.rrrt, "rrrt"),
        ("global_ion_pirt", result.pirt, "pirt"),
        ("global_ion_stotg", result.stotg, "stotg"),
        ("global_ion_atotg", result.atotg, "atotg"),
        ("global_ion_xtotg", result.xtotg, "xtotg"),
    )
    for key, global_index in sorted(ion_index_by_key.items(), key=lambda item: item[1]):
        if key[0] not in probe_elements:
            continue
        record = ion_by_index.get(int(global_index))
        python_values = [values.get(key, 0.0) for _, values, _ in ion_components]
        if record is None:
            if _nonzero(python_values):
                ion_missing_xstar += 1
            continue
        for component, values, field_name in ion_components:
            rows.append(_metric(
                component, f"global_ion={global_index},Z={key[0]},stage={key[1]}",
                values.get(key, 0.0), float(record[field_name]),
                rtol=rtol, atol=atol, parity_class="global_ion",
            ))
    ion_metric_components = {component for component, _, _ in ion_components}
    global_ion_ready = (
        ion_missing_python == 0 and ion_missing_xstar == 0
        and all(row.within_tolerance for row in rows if row.component in ion_metric_components)
    )

    element_index_by_z = dict(getattr(result, "global_element_index_by_z", {}))
    if not element_array_rows_all:
        element_array_ready = None
        element_array_status = "not_comparable_missing_element_probe"
    else:
        element_by_z = {int(row["element_z"]): row for row in element_array_rows}
        for z in sorted(probe_elements):
            record = element_by_z.get(z)
            if record is None:
                if _nonzero((result.htt.get(z, 0.0), result.cll.get(z, 0.0), result.htt2.get(z, 0.0), result.cll2.get(z, 0.0))):
                    element_missing_xstar += 1
                continue
            expected_index = element_index_by_z.get(z)
            if expected_index is not None:
                rows.append(_metric(
                    "element_index", f"Z={z}", expected_index, int(record["element_index"]),
                    rtol=0.0, atol=0.0, parity_class="element_array",
                ))
            python_abundance = next(
                (float(getattr(item.request, "abundance", record["abundance"]))
                 for item in result.element_results
                 if int(item.request.element_z) == z),
                float(record["abundance"]),
            )
            rows.append(_metric(
                "element_abundance", f"Z={z}", python_abundance, float(record["abundance"]),
                rtol=rtol, atol=atol, parity_class="element_array",
            ))
            for component, values, field_name in (
                ("element_htt", result.htt, "htt"),
                ("element_cll", result.cll, "cll"),
                ("element_htt2", result.htt2, "htt2"),
                ("element_cll2", result.cll2, "cll2"),
            ):
                rows.append(_metric(
                    component, f"element_index={record['element_index']},Z={z}",
                    values.get(z, 0.0), float(record[field_name]),
                    rtol=rtol, atol=atol, parity_class="element_array",
                ))
        element_components = {
            "element_index", "element_abundance", "element_htt",
            "element_cll", "element_htt2", "element_cll2",
        }
        element_array_ready = (
            element_missing_python == 0 and element_missing_xstar == 0
            and all(row.within_tolerance for row in rows if row.component in element_components)
        )
        element_array_status = "ready" if element_array_ready else "failed"

    level_by_index = {int(row["global_level_index"]): row for row in level_rows}
    level_index_by_key = dict(getattr(result, "global_level_index_by_key", {}))
    level_components = (
        ("global_level_xilevg", result.xilevg, "xilevg", False, "global_level_primary"),
        ("global_level_rnisg", result.rnisg, "rnisg", False, "global_level_primary"),
        ("global_level_bilevg", result.bilevg, "bilevg", False, "global_level_derived"),
        ("global_level_gammag", result.gammag, "gammag", False, "global_level_primary"),
        ("global_level_alphag", result.alphag, "alphag", False, "global_level_primary"),
        ("global_level_igammamax", result.igammamaxg, "igammamax_record", True, "global_level_derived"),
        ("global_level_ialphamax", result.ialphamaxg, "ialphamax_record", True, "global_level_derived"),
    )
    compared_level_indices = set()
    selected_level_keys = set()
    for _, values, _, _, _ in level_components:
        selected_level_keys.update(values)
    for key in sorted(selected_level_keys):
        if key[0] not in probe_elements:
            continue
        global_index = level_index_by_key.get(key)
        if global_index is None:
            if _nonzero([values.get(key, 0) for _, values, _, _, _ in level_components]):
                level_missing_xstar += 1
            continue
        record = level_by_index.get(int(global_index))
        python_values = [values.get(key, 0) for _, values, _, _, _ in level_components]
        if record is None:
            if _nonzero(python_values):
                level_missing_xstar += 1
            continue
        compared_level_indices.add(int(global_index))
        active = max(abs(float(result.xilevg.get(key, 0.0))), abs(float(record["xilevg"]))) >= active_population_threshold
        for component, values, field_name, exact, parity_class in level_components:
            blocking = parity_class == "global_level_primary" and (
                component in {"global_level_rnisg", "global_level_gammag"} or active
            )
            rows.append(_metric(
                component,
                f"global_level={global_index},Z={key[0]},stage={key[1]},level={key[2]}",
                values.get(key, 0), float(record[field_name]),
                rtol=0.0 if exact else rtol,
                atol=0.0 if exact else atol,
                parity_class=parity_class,
                active_level=active,
                milestone_blocking=blocking,
            ))

    primary_rows = [row for row in rows if row.parity_class == "global_level_primary"]
    derived_rows = [row for row in rows if row.parity_class == "global_level_derived"]
    active_gate_rows = [row for row in primary_rows if row.milestone_blocking]
    no_level_missing = level_missing_python == 0 and level_missing_xstar == 0
    global_level_primary_ready = no_level_missing and all(row.within_tolerance for row in primary_rows)
    global_level_active_ready = no_level_missing and all(row.within_tolerance for row in active_gate_rows)
    global_level_derived_ready = no_level_missing and all(row.within_tolerance for row in derived_rows)
    global_level_ready = bool(global_level_primary_ready and global_level_derived_ready)
    element_gate = element_array_ready is not False
    global_arrays_ready = bool(global_ion_ready and global_level_active_ready and element_gate)

    closure = build_xstar_vector_matrix_closure(
        result,
        level_probe_rows=level_rows,
        element_probe_rows=element_array_rows,
        rtol=rtol,
        atol=atol,
        active_row_scale_threshold=matrix_closure_active_row_scale_threshold,
    )
    matrix_closure_ready: Optional[bool] = closure.ready if closure.elements else None
    matrix_closure_status = (
        "ready" if matrix_closure_ready is True
        else "failed" if matrix_closure_ready is False
        else "not_comparable_missing_closure_rows"
    )
    element_thermal_diagnostic_ready = bool(
        closure.elements
        and all(
            all(row.get("captured_xstar_per_abundance") is not None
                for row in item.thermal_summary_rows)
            for item in closure.elements
        )
    )

    same_call_matrix = compare_same_call_matrix_terms(
        result, matrix_probe_rows=matrix_rows, closure=closure,
        rtol=rtol, atol=atol,
        active_row_scale_threshold=matrix_closure_active_row_scale_threshold,
    )
    thermal_family_parity = compare_thermal_families(
        closure=closure,
        data_type_probe_rows=thermal_data_type_rows,
        rate_type_probe_rows=thermal_rate_type_rows,
        rtol=rtol, atol=atol,
    )
    initial_element_zs = sorted({int(item.request.element_z) for item in result.element_results})
    if initial_population_rows:
        initial_solver_population = compare_msolvelucy_initial_populations(
            {
                int(item.request.element_z): item.equilibrium.assembly.initial_populations
                for item in result.element_results
                if getattr(item, "equilibrium", None) is not None
            },
            root,
            element_zs=initial_element_zs,
            call_id=selected_call,
            rtol=rtol,
            atol=atol,
        )
    else:
        initial_solver_population = MSolveLucyInitialPopulationParityResult(
            ready=False,
            status="not_comparable_missing_initial_population_probe",
            call_id=selected_call,
            element_z=0,
            compact_dimension=None,
            n_rows=0,
            n_outside_tolerance=0,
            max_absolute_difference=None,
            max_relative_difference=None,
            rows=[],
            element_results=[
                {
                    "element_z": z,
                    "ready": False,
                    "status": "not_comparable_missing_initial_population_probe",
                }
                for z in initial_element_zs
            ],
        )


    final_solver_snapshot = compare_msolvelucy_final_snapshot(
        result,
        final_matrix_rows=final_matrix_rows,
        final_population_rows=final_population_rows,
        rtol=rtol,
        atol=atol,
        active_population_threshold=active_population_threshold,
    )
    rate7_cj2_diagnosis = diagnose_rate7_cj2_records(
        result,
        same_call_matrix=same_call_matrix,
        rtol=rtol,
        atol=atol,
    )
    leveltemp_energy_parity = compare_leveltemp_energy_probe(
        result,
        probe_rows=leveltemp_energy_rows,
        element_z=8,
    )

    attribution = _build_population_weighted_attribution(
        result=result,
        failed_level_rows=rows,
        level_by_index=level_by_index,
        level_index_by_key=level_index_by_key,
    )
    matrix_term_by_key = {
        (int(row.get("element_z", 0)), int(row.get("term_index", 0))): row
        for row in same_call_matrix.term_rows
        if row.get("term_index") not in (None, "")
    }
    for row in attribution:
        matrix_row = matrix_term_by_key.get((
            int(row.get("element_z", 0)), int(row.get("dominant_source_row", 0))
        ))
        # dominant_source_row is a compact row, not a term index.  Prefer an
        # exact record/role match when the same-call term probe is available.
        candidates = [
            item for item in same_call_matrix.term_rows
            if int(item.get("element_z", 0)) == int(row.get("element_z", 0))
            and int(item.get("record", -1)) == int(row.get("dominant_record", -2))
            and str(item.get("role", "")) == str(row.get("dominant_term_role", ""))
            and int(item.get("python_row_compact", 0)) == int(row.get("target_compact_row", 0))
        ]
        if candidates:
            matrix_row = max(
                candidates,
                key=lambda item: abs(float(item.get("delta_population_weighted_aj1", 0.0))),
            )
        if matrix_row is not None:
            row["xstar_same_call_coefficient_s_inv"] = matrix_row.get("xstar_aj1")
            row["same_call_coefficient_difference_s_inv"] = matrix_row.get("aj1_difference")
            row["same_call_matrix_term_index"] = matrix_row.get("term_index")
            row["rate_difference_status"] = (
                "same_call_coefficient_outside_tolerance"
                if not bool(matrix_row.get("within_tolerance", False))
                else "same_call_coefficient_within_tolerance"
            )

    active_population_ion_resolution = _build_active_population_ion_matrix_resolution(
        result=result, parity_rows=rows, same_call_matrix=same_call_matrix
    )
    oxygen_reassessment_rows = list(final_solver_snapshot.oxygen_reassessment_rows)
    # Also retain any still-failing exported O III--O V active levels and
    # O III/O IV ion totals after the synchronized solver comparison.
    for item in active_population_ion_resolution:
        z = int(item.get("element_z", 0))
        stage = int(item.get("ion_stage", 0))
        if z == 8 and ((3 <= stage <= 5 and item.get("component") in {"global_level_xilevg", "global_level_alphag"})
                       or (stage in {3, 4} and str(item.get("component", "")).startswith("global_ion_"))):
            oxygen_reassessment_rows.append({
                **item,
                "reassessment_kind": "exported_global_array",
                "milestone_blocking": True,
            })
    oxygen_reassessment_ready: Optional[bool]
    if final_solver_snapshot.ready is None:
        oxygen_reassessment_ready = None
        oxygen_reassessment_status = "not_comparable_missing_final_solver_snapshot"
    else:
        oxygen_reassessment_ready = len(oxygen_reassessment_rows) == 0
        oxygen_reassessment_status = "ready" if oxygen_reassessment_ready else "failed"

    missing_python = pre_matrix_missing_python + ion_missing_python + level_missing_python + element_missing_python
    missing_xstar = pre_matrix_missing_xstar + ion_missing_xstar + level_missing_xstar + element_missing_xstar
    outside = sum(not row.within_tolerance for row in rows)
    blocking_outside = sum((not row.within_tolerance) and row.milestone_blocking for row in rows)
    max_abs = max((row.absolute_difference for row in rows), default=0.0)
    max_rel = max((row.relative_difference for row in rows), default=0.0)
    (
        all_element_pre_continuum_acceptance_ready,
        all_element_active_solver_ready,
        all_element_thermal_ready,
        all_element_element_readiness,
    ) = _all_element_acceptance_summary(
        result,
        rows=rows,
        blocking_outside=blocking_outside,
        initial=initial_solver_population,
        matrix=same_call_matrix,
        thermal=thermal_family_parity,
        final=final_solver_snapshot,
    )
    pre_matrix_components = {
        "istruc_fraction", "calc_ion_rates_pirt", "calc_ion_rates_rrrt",
        "ion_limit_mml", "ion_limit_mmu", "ion_limit_critf",
    }
    pre_matrix_ready = (
        pre_matrix_missing_python == 0 and pre_matrix_missing_xstar == 0
        and all(row.within_tolerance for row in rows if row.component in pre_matrix_components)
    )
    summary_gate = summary_ready is not False
    legacy_probe_present = bool(
        matrix_rows or thermal_data_type_rows or thermal_rate_type_rows
    )
    final_snapshot_probe_present = bool(final_matrix_rows or final_population_rows)
    same_call_matrix_gate = (
        same_call_matrix.ready is True if legacy_probe_present else True
    )
    thermal_family_gate = (
        thermal_family_parity.ready is True if legacy_probe_present else True
    )
    matrix_operator_gate = (
        same_call_matrix_gate
        if legacy_probe_present
        else matrix_closure_ready is not False
    )
    # v0.4.33 oxygen acceptance is intentionally stricter than the historical
    # v0.4.29/v0.4.30 gate.  It requires the synchronized final-solver probe
    # pair, source-order xtot parity, type-53 rate-7 cj2 closure, and no
    # remaining O III--O V/O III--O IV blocker.
    final_solver_gate = bool(
        final_solver_snapshot.ready is True
        and final_solver_snapshot.topology_ready is True
        and final_solver_snapshot.active_final_population_ready is True
        and final_solver_snapshot.active_outer_start_population_ready is True
        and final_solver_snapshot.source_xtot_ready is True
    )
    type53_cj2_gate = rate7_cj2_diagnosis.type53_ready is True
    leveltemp_energy_gate = bool(
        leveltemp_energy_parity.ready is True
        and leveltemp_energy_parity.type53_ready is True
    )
    oxygen_reassessment_gate = oxygen_reassessment_ready is True
    legacy_acceptance_ready = bool(
        pre_matrix_ready
        and state_ready
        and global_ion_ready
        and global_level_active_ready
        and element_array_ready is True
        and matrix_operator_gate
        and thermal_family_gate
        and summary_gate
    )
    initial_solver_population_gate = initial_solver_population.ready is True
    oxygen_pre_continuum_acceptance_ready = bool(
        legacy_acceptance_ready
        and initial_solver_population_gate
        and final_solver_gate
        and type53_cj2_gate
        and leveltemp_energy_gate
        and oxygen_reassessment_gate
    )
    # Preserve the historical comparator contract for old five/six-hook probe
    # directories.  As soon as either v0.4.33 final-snapshot file is present,
    # the public acceptance gate becomes the stricter synchronized oxygen gate.
    acceptance_gate_ready = (
        oxygen_pre_continuum_acceptance_ready
        if final_snapshot_probe_present else legacy_acceptance_ready
    )
    strict_matrix_coefficient_gate = (
        same_call_matrix.coefficient_ready is True if legacy_probe_present else True
    )
    legacy_strict_ready = bool(
        legacy_acceptance_ready and global_level_ready and strict_matrix_coefficient_gate
    )
    strict_parity_ready = (
        bool(
            oxygen_pre_continuum_acceptance_ready
            and global_level_ready
            and strict_matrix_coefficient_gate
            and final_solver_snapshot.coefficient_ready is True
            and rate7_cj2_diagnosis.ready is True
        )
        if final_snapshot_probe_present else legacy_strict_ready
    )
    ready = acceptance_gate_ready
    return CalcHMCAllPreContinuumParityResult(
        call_id=selected_call,
        rows=rows,
        n_missing_python_keys=missing_python,
        n_missing_xstar_keys=missing_xstar,
        max_absolute_difference=max_abs,
        max_relative_difference=max_rel,
        n_outside_tolerance=outside,
        n_blocking_outside_tolerance=blocking_outside,
        pre_matrix_ready=pre_matrix_ready,
        pre_continuum_state_ready=state_ready,
        pre_continuum_summary_ready=summary_ready,
        pre_continuum_summary_status=summary_status,
        element_array_ready=element_array_ready,
        element_array_status=element_array_status,
        global_ion_ready=global_ion_ready,
        global_level_primary_ready=global_level_primary_ready,
        global_level_active_ready=global_level_active_ready,
        global_level_derived_ready=global_level_derived_ready,
        global_level_ready=global_level_ready,
        global_arrays_ready=global_arrays_ready,
        matrix_closure_ready=matrix_closure_ready,
        matrix_closure_status=matrix_closure_status,
        element_thermal_diagnostic_ready=element_thermal_diagnostic_ready,
        same_call_matrix_ready=same_call_matrix.ready,
        same_call_matrix_status=same_call_matrix.status,
        same_call_matrix_topology_ready=same_call_matrix.topology_ready,
        same_call_matrix_coefficient_ready=same_call_matrix.coefficient_ready,
        same_call_matrix_active_closure_ready=same_call_matrix.active_closure_ready,
        thermal_family_ready=thermal_family_parity.ready,
        thermal_family_status=thermal_family_parity.status,
        initial_solver_population_ready=initial_solver_population.ready,
        initial_solver_population_status=initial_solver_population.status,
        final_solver_snapshot_ready=final_solver_snapshot.ready,
        final_solver_snapshot_status=final_solver_snapshot.status,
        final_solver_same_iteration_ready=final_solver_snapshot.same_iteration_ready,
        final_solver_iteration_tuple_ready=final_solver_snapshot.iteration_tuple_ready,
        final_solver_matrix_dimension_ready=final_solver_snapshot.matrix_dimension_ready,
        final_solver_population_columns_ready=final_solver_snapshot.matrix_population_columns_ready,
        final_solver_topology_ready=final_solver_snapshot.topology_ready,
        final_solver_coefficient_ready=final_solver_snapshot.coefficient_ready,
        final_solver_active_population_ready=final_solver_snapshot.active_final_population_ready,
        final_solver_outer_start_ready=final_solver_snapshot.active_outer_start_population_ready,
        final_solver_source_xtot_ready=final_solver_snapshot.source_xtot_ready,
        rate7_cj2_ready=rate7_cj2_diagnosis.ready,
        rate7_cj2_status=rate7_cj2_diagnosis.status,
        type53_rate7_cj2_ready=rate7_cj2_diagnosis.type53_ready,
        leveltemp_energy_ready=leveltemp_energy_parity.ready,
        leveltemp_energy_status=leveltemp_energy_parity.status,
        type53_leveltemp_energy_ready=leveltemp_energy_parity.type53_ready,
        oxygen_reassessment_ready=oxygen_reassessment_ready,
        oxygen_reassessment_status=oxygen_reassessment_status,
        acceptance_gate_ready=acceptance_gate_ready,
        oxygen_pre_continuum_acceptance_ready=oxygen_pre_continuum_acceptance_ready,
        all_element_pre_continuum_acceptance_ready=all_element_pre_continuum_acceptance_ready,
        all_element_active_solver_ready=all_element_active_solver_ready,
        all_element_thermal_ready=all_element_thermal_ready,
        all_element_element_readiness=all_element_element_readiness,
        strict_parity_ready=strict_parity_ready,
        parity_ready=ready,
        active_population_threshold=float(active_population_threshold),
        matrix_closure=closure,
        same_call_matrix=same_call_matrix,
        thermal_family_parity=thermal_family_parity,
        initial_solver_population=initial_solver_population,
        final_solver_snapshot=final_solver_snapshot,
        rate7_cj2_diagnosis=rate7_cj2_diagnosis,
        leveltemp_energy_parity=leveltemp_energy_parity,
        population_weighted_attribution=attribution,
        active_population_ion_resolution=active_population_ion_resolution,
        oxygen_reassessment=oxygen_reassessment_rows,
        diagnostics={
            "probe_dir": str(root),
            "rtol": float(rtol),
            "atol": float(atol),
            "active_population_threshold": float(active_population_threshold),
            "matrix_closure_active_row_scale_threshold": float(matrix_closure_active_row_scale_threshold),
            "matrix_closure_status": matrix_closure_status,
            "matrix_closure_active_rows_outside_tolerance": closure.n_active_rows_outside_tolerance,
            "matrix_closure_missing_rows": closure.n_missing_rows,
            "element_thermal_diagnostic_ready": element_thermal_diagnostic_ready,
            "legacy_same_call_probe_present": legacy_probe_present,
            "v0431_final_snapshot_probe_present": final_snapshot_probe_present,
            "legacy_acceptance_ready": legacy_acceptance_ready,
            "matrix_operator_gate": matrix_operator_gate,
            "matrix_operator_gate_source": (
                "same_call_matrix_parity" if legacy_probe_present
                else "legacy_python_xstar_vector_closure"
            ),
            "same_call_matrix_status": same_call_matrix.status,
            "same_call_matrix_topology_ready": same_call_matrix.topology_ready,
            "same_call_matrix_coefficient_ready": same_call_matrix.coefficient_ready,
            "same_call_matrix_active_closure_ready": same_call_matrix.active_closure_ready,
            "same_call_matrix_active_rows_outside_tolerance": same_call_matrix.n_active_rows_outside_tolerance,
            "thermal_family_status": thermal_family_parity.status,
            "thermal_family_rows_outside_tolerance": thermal_family_parity.n_outside_tolerance,
            "initial_solver_population_status": initial_solver_population.status,
            "initial_solver_population_ready": initial_solver_population.ready,
            "initial_solver_population_probe_present": bool(initial_population_rows),
            "initial_population_sources_by_element": {
                str(int(item.request.element_z)): getattr(item.request, "initial_population_source", None)
                for item in result.element_results
            },
            "initial_solver_population_element_results": initial_solver_population.element_results,
            "final_solver_snapshot_status": final_solver_snapshot.status,
            "final_solver_same_iteration_ready": final_solver_snapshot.same_iteration_ready,
            "final_solver_iteration_tuple_ready": final_solver_snapshot.iteration_tuple_ready,
            "final_solver_matrix_dimension_ready": final_solver_snapshot.matrix_dimension_ready,
            "final_solver_population_columns_ready": final_solver_snapshot.matrix_population_columns_ready,
            "final_solver_source_xtot_ready": final_solver_snapshot.source_xtot_ready,
            "rate7_cj2_status": rate7_cj2_diagnosis.status,
            "type53_rate7_cj2_ready": rate7_cj2_diagnosis.type53_ready,
            "oxygen_reassessment_status": oxygen_reassessment_status,
            "n_oxygen_reassessment_rows": len(oxygen_reassessment_rows),
            "all_element_pre_continuum_acceptance_ready": all_element_pre_continuum_acceptance_ready,
            "all_element_active_solver_ready": all_element_active_solver_ready,
            "all_element_thermal_ready": all_element_thermal_ready,
            "all_element_element_readiness": all_element_element_readiness,
            "all_element_acceptance_definition": (
                "oxygen_call73_regression && H/He/O detailed parity && all active final/xo "
                "&& source_xtot && all thermal families && zero milestone blockers"
            ),
            "acceptance_gate_definition": (
                "pre_matrix && runtime_state && global_ion && global_level_active "
                "&& element_array && matrix_operator_gate && thermal_family_parity "
                "&& same_call_initial_xileve && synchronized_final_msolvelucy_snapshot && source_xtot "
                "&& type53_rate7_cj2 && oxygen_reassessment && summary_scope_gate"
            ),
            "summary_scope_complete": summary_comparable,
            "deferred_summary_fields": deferred_summary_fields,
            "element_array_probe_present": bool(element_array_rows_all),
            "n_element_array_probe_rows": len(element_array_rows),
            "n_same_call_matrix_probe_rows": len(matrix_rows),
            "n_thermal_data_type_probe_rows": len(thermal_data_type_rows),
            "n_thermal_rate_type_probe_rows": len(thermal_rate_type_rows),
            "n_final_solver_matrix_probe_rows": len(final_matrix_rows),
            "n_final_solver_population_probe_rows": len(final_population_rows),
            "n_initial_solver_population_probe_rows": len(initial_population_rows),
            "n_active_population_ion_resolution_rows": len(active_population_ion_resolution),
            "n_global_ion_probe_rows": len(ion_rows),
            "global_element_index_by_z": element_index_by_z,
            "n_global_level_probe_rows": len(level_rows),
            "n_compared_global_level_indices": len(compared_level_indices),
            "n_active_level_primary_rows": len(active_gate_rows),
            "n_population_weighted_attribution_rows": len(attribution),
            "pre_matrix_missing_python_keys": pre_matrix_missing_python,
            "pre_matrix_missing_xstar_keys": pre_matrix_missing_xstar,
            "global_ion_missing_python_keys": ion_missing_python,
            "global_ion_missing_xstar_keys": ion_missing_xstar,
            "element_array_missing_python_keys": element_missing_python,
            "element_array_missing_xstar_keys": element_missing_xstar,
            "global_level_missing_python_keys": level_missing_python,
            "global_level_missing_xstar_keys": level_missing_xstar,
        },
    )


def write_calc_hmc_all_pre_continuum_parity_products(
    result: CalcHMCAllPreContinuumParityResult,
    out_dir: str | Path,
    *,
    port_version: str = "v0.4.36",
) -> Dict[str, str]:
    """Write row-level, attribution, JSON, and Markdown products."""

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    details = out / "xstar_calc_hmc_all_pre_continuum_parity_details.csv"
    with details.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=(
            "component", "key", "python_value", "xstar_value",
            "absolute_difference", "relative_difference", "within_tolerance",
            "parity_class", "active_level", "milestone_blocking",
        ))
        writer.writeheader()
        for row in result.rows:
            writer.writerow(row.__dict__)

    attribution_path = out / "xstar_calc_hmc_all_population_weighted_difference_attribution.csv"
    attribution_fields = (
        "target_global_level_index", "element_z", "ion_stage", "local_level",
        "target_compact_row", "failing_components", "python_target_population",
        "xstar_target_population", "python_target_alpha", "xstar_target_alpha",
        "dominant_record", "dominant_data_type", "dominant_rate_type",
        "dominant_term_role", "dominant_source_row", "dominant_source_column",
        "dominant_coefficient_s_inv", "python_feeding_population",
        "xstar_feeding_population", "xstar_feeding_global_level_index",
        "xstar_feeding_physical_key", "python_population_weighted_contribution_s_inv",
        "xstar_population_weighted_contribution_same_coefficient_s_inv",
        "estimated_population_factor_difference_s_inv",
        "xstar_same_call_coefficient_s_inv",
        "same_call_coefficient_difference_s_inv",
        "same_call_matrix_term_index",
        "rate_difference_status", "diagnostic_role",
    )
    with attribution_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=attribution_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(result.population_weighted_attribution)

    closure_rows_path = out / "xstar_calc_hmc_all_xstar_vector_matrix_closure_rows.csv"
    closure_summary_path = out / "xstar_calc_hmc_all_xstar_vector_matrix_closure_summary.csv"
    thermal_rows_path = out / "xstar_calc_hmc_all_thermal_contribution_audit.csv"
    thermal_summary_path = out / "xstar_calc_hmc_all_thermal_channel_summary.csv"
    thermal_family_path = out / "xstar_calc_hmc_all_thermal_family_summary.csv"
    same_call_terms_path = out / "xstar_calc_hmc_all_same_call_matrix_term_parity.csv"
    same_call_families_path = out / "xstar_calc_hmc_all_same_call_matrix_family_parity.csv"
    same_call_active_rows_path = out / "xstar_calc_hmc_all_same_call_active_row_attribution.csv"
    thermal_family_parity_path = out / "xstar_calc_hmc_all_xstar_thermal_family_parity.csv"
    active_population_ion_resolution_path = (
        out / "xstar_calc_hmc_all_active_population_ion_matrix_resolution.csv"
    )
    initial_solver_population_path = (
        out / "xstar_calc_hmc_all_msolvelucy_initial_population_parity.csv"
    )
    final_solver_term_path = out / "xstar_calc_hmc_all_msolvelucy_final_term_parity.csv"
    final_solver_population_path = out / "xstar_calc_hmc_all_msolvelucy_final_population_parity.csv"
    final_solver_ion_total_path = out / "xstar_calc_hmc_all_msolvelucy_final_ion_totals.csv"
    rate7_cj2_path = out / "xstar_calc_hmc_all_rate7_cj2_record_terms.csv"
    rate7_cj2_record_path = out / "xstar_calc_hmc_all_rate7_cj2_record_summary.csv"
    leveltemp_energy_path = out / "xstar_calc_hmc_all_leveltemp_energy_parity.csv"
    leveltemp_trace_path = out / "xstar_calc_hmc_all_leveltemp_workspace_trace.csv"
    type53_leveltemp_trace_path = out / "xstar_calc_hmc_all_type53_leveltemp_trace.csv"
    oxygen_reassessment_path = out / "xstar_calc_hmc_all_oxygen_active_population_ion_reassessment.csv"
    closure_rows = []
    closure_summaries = []
    thermal_rows = []
    thermal_summaries = []
    if result.matrix_closure is not None:
        for item in result.matrix_closure.elements:
            closure_rows.extend(item.row_rows)
            thermal_rows.extend(item.thermal_rows)
            thermal_summaries.extend(item.thermal_summary_rows)
            closure_summaries.append({
                "element_z": item.element_z,
                "abundance": item.abundance,
                "n_compact_rows": item.n_compact_rows,
                "n_mapped_rows": item.n_mapped_rows,
                "n_missing_rows": item.n_missing_rows,
                "xstar_vector_normalization": item.xstar_vector_normalization,
                "xstar_vector_normalization_error": item.xstar_vector_normalization_error,
                "native_l1_residual": item.native_l1_residual,
                "native_l1_relative_residual": item.native_l1_relative_residual,
                "xstar_vector_l1_residual": item.xstar_vector_l1_residual,
                "xstar_vector_l1_relative_residual": item.xstar_vector_l1_relative_residual,
                "xstar_vector_max_relative_residual": item.xstar_vector_max_relative_residual,
                "xstar_vector_max_active_relative_residual": item.xstar_vector_max_active_relative_residual,
                "n_active_rows": item.n_active_rows,
                "n_active_rows_outside_tolerance": item.n_active_rows_outside_tolerance,
                "ready": item.ready,
            })

    def _write_rows(path: Path, data: List[Dict[str, Any]]) -> None:
        with path.open("w", newline="") as handle:
            if not data:
                handle.write("")
                return
            fields = list(data[0].keys())
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(data)

    family_accumulator: Dict[tuple[int, str, int, int], Dict[str, Any]] = {}
    for row in thermal_rows:
        key = (
            int(row["element_z"]), str(row["thermal_channel"]),
            int(row["data_type"]), int(row["rate_type"]),
        )
        item = family_accumulator.setdefault(key, {
            "element_z": key[0], "thermal_channel": key[1],
            "data_type": key[2], "rate_type": key[3], "n_terms": 0,
            "python_contribution_per_abundance": 0.0,
            "xstar_vector_contribution_per_abundance": 0.0,
            "population_effect_per_abundance": 0.0,
        })
        item["n_terms"] += 1
        item["python_contribution_per_abundance"] += float(row["python_contribution_per_abundance"])
        item["xstar_vector_contribution_per_abundance"] += float(row["xstar_vector_contribution_per_abundance"])
        item["population_effect_per_abundance"] += float(row["population_effect_per_abundance"])
    thermal_family_rows = [family_accumulator[key] for key in sorted(family_accumulator)]

    _write_rows(closure_rows_path, closure_rows)
    _write_rows(closure_summary_path, closure_summaries)
    _write_rows(thermal_rows_path, thermal_rows)
    _write_rows(thermal_summary_path, thermal_summaries)
    _write_rows(thermal_family_path, thermal_family_rows)
    _write_rows(
        same_call_terms_path,
        [] if result.same_call_matrix is None else result.same_call_matrix.term_rows,
    )
    _write_rows(
        same_call_families_path,
        [] if result.same_call_matrix is None else result.same_call_matrix.family_rows,
    )
    _write_rows(
        same_call_active_rows_path,
        [] if result.same_call_matrix is None else result.same_call_matrix.active_row_rows,
    )
    _write_rows(
        thermal_family_parity_path,
        [] if result.thermal_family_parity is None else result.thermal_family_parity.rows,
    )
    _write_rows(active_population_ion_resolution_path, result.active_population_ion_resolution)
    _write_rows(
        initial_solver_population_path,
        [] if result.initial_solver_population is None else result.initial_solver_population.rows,
    )
    _write_rows(final_solver_term_path, [] if result.final_solver_snapshot is None else result.final_solver_snapshot.term_rows)
    _write_rows(final_solver_population_path, [] if result.final_solver_snapshot is None else result.final_solver_snapshot.population_rows)
    _write_rows(final_solver_ion_total_path, [] if result.final_solver_snapshot is None else result.final_solver_snapshot.ion_total_rows)
    _write_rows(rate7_cj2_path, [] if result.rate7_cj2_diagnosis is None else result.rate7_cj2_diagnosis.rows)
    _write_rows(rate7_cj2_record_path, [] if result.rate7_cj2_diagnosis is None else result.rate7_cj2_diagnosis.record_rows)
    _write_rows(leveltemp_energy_path, [] if result.leveltemp_energy_parity is None else result.leveltemp_energy_parity.rows)
    _write_rows(leveltemp_trace_path, [] if result.leveltemp_energy_parity is None else result.leveltemp_energy_parity.workspace_trace_rows)
    _write_rows(type53_leveltemp_trace_path, [] if result.leveltemp_energy_parity is None else result.leveltemp_energy_parity.type53_trace_rows)
    _write_rows(oxygen_reassessment_path, result.oxygen_reassessment)

    payload = {
        "port_version": port_version,
        "call_id": result.call_id,
        "n_rows": len(result.rows),
        "n_missing_python_keys": result.n_missing_python_keys,
        "n_missing_xstar_keys": result.n_missing_xstar_keys,
        "n_outside_tolerance": result.n_outside_tolerance,
        "n_blocking_outside_tolerance": result.n_blocking_outside_tolerance,
        "max_absolute_difference": result.max_absolute_difference,
        "max_relative_difference": result.max_relative_difference,
        "pre_matrix_ready": result.pre_matrix_ready,
        "pre_continuum_state_ready": result.pre_continuum_state_ready,
        "pre_continuum_summary_ready": result.pre_continuum_summary_ready,
        "pre_continuum_summary_status": result.pre_continuum_summary_status,
        "element_array_ready": result.element_array_ready,
        "element_array_status": result.element_array_status,
        "global_ion_ready": result.global_ion_ready,
        "global_level_primary_ready": result.global_level_primary_ready,
        "global_level_active_ready": result.global_level_active_ready,
        "global_level_derived_ready": result.global_level_derived_ready,
        "global_level_ready": result.global_level_ready,
        "global_arrays_ready": result.global_arrays_ready,
        "matrix_closure_ready": result.matrix_closure_ready,
        "matrix_closure_status": result.matrix_closure_status,
        "element_thermal_diagnostic_ready": result.element_thermal_diagnostic_ready,
        "same_call_matrix_ready": result.same_call_matrix_ready,
        "same_call_matrix_status": result.same_call_matrix_status,
        "same_call_matrix_topology_ready": result.same_call_matrix_topology_ready,
        "same_call_matrix_coefficient_ready": result.same_call_matrix_coefficient_ready,
        "same_call_matrix_active_closure_ready": result.same_call_matrix_active_closure_ready,
        "thermal_family_ready": result.thermal_family_ready,
        "thermal_family_status": result.thermal_family_status,
        "initial_solver_population_ready": result.initial_solver_population_ready,
        "initial_solver_population_status": result.initial_solver_population_status,
        "final_solver_snapshot_ready": result.final_solver_snapshot_ready,
        "final_solver_snapshot_status": result.final_solver_snapshot_status,
        "final_solver_same_iteration_ready": result.final_solver_same_iteration_ready,
        "final_solver_iteration_tuple_ready": result.final_solver_iteration_tuple_ready,
        "final_solver_matrix_dimension_ready": result.final_solver_matrix_dimension_ready,
        "final_solver_population_columns_ready": result.final_solver_population_columns_ready,
        "final_solver_topology_ready": result.final_solver_topology_ready,
        "final_solver_coefficient_ready": result.final_solver_coefficient_ready,
        "final_solver_active_population_ready": result.final_solver_active_population_ready,
        "final_solver_outer_start_ready": result.final_solver_outer_start_ready,
        "final_solver_source_xtot_ready": result.final_solver_source_xtot_ready,
        "rate7_cj2_ready": result.rate7_cj2_ready,
        "rate7_cj2_status": result.rate7_cj2_status,
        "type53_rate7_cj2_ready": result.type53_rate7_cj2_ready,
        "leveltemp_energy_ready": result.leveltemp_energy_ready,
        "leveltemp_energy_status": result.leveltemp_energy_status,
        "type53_leveltemp_energy_ready": result.type53_leveltemp_energy_ready,
        "oxygen_reassessment_ready": result.oxygen_reassessment_ready,
        "oxygen_reassessment_status": result.oxygen_reassessment_status,
        "acceptance_gate_ready": result.acceptance_gate_ready,
        "oxygen_pre_continuum_acceptance_ready": result.oxygen_pre_continuum_acceptance_ready,
        "all_element_pre_continuum_acceptance_ready": result.all_element_pre_continuum_acceptance_ready,
        "all_element_active_solver_ready": result.all_element_active_solver_ready,
        "all_element_thermal_ready": result.all_element_thermal_ready,
        "all_element_element_readiness": result.all_element_element_readiness,
        "strict_parity_ready": result.strict_parity_ready,
        "parity_ready": result.parity_ready,
        "active_population_threshold": result.active_population_threshold,
        "n_population_weighted_attribution_rows": len(result.population_weighted_attribution),
        "n_active_population_ion_resolution_rows": len(result.active_population_ion_resolution),
        "n_oxygen_reassessment_rows": len(result.oxygen_reassessment),
        "diagnostics": result.diagnostics,
    }
    json_path = out / "xstar_calc_hmc_all_pre_continuum_parity_summary.json"
    json_path.write_text(json.dumps(payload, indent=2) + "\n")
    md = out / "xstar_calc_hmc_all_pre_continuum_parity_summary.md"
    md.write_text(
        "# calc_hmc_all pre-continuum parity\n\n"
        f"- Call ID: `{result.call_id}`\n"
        f"- Compared rows: `{len(result.rows)}`\n"
        f"- Outside tolerance, strict: `{result.n_outside_tolerance}`\n"
        f"- Outside tolerance, milestone-blocking: `{result.n_blocking_outside_tolerance}`\n"
        f"- Missing Python keys: `{result.n_missing_python_keys}`\n"
        f"- Missing XSTAR keys: `{result.n_missing_xstar_keys}`\n"
        f"- Pre-matrix ready: `{result.pre_matrix_ready}`\n"
        f"- Runtime state ready: `{result.pre_continuum_state_ready}`\n"
        f"- Summary status: `{result.pre_continuum_summary_status}`\n"
        f"- Element-array status: `{result.element_array_status}`\n"
        f"- Global ion arrays ready: `{result.global_ion_ready}`\n"
        f"- Global level primary, strict: `{result.global_level_primary_ready}`\n"
        f"- Global level active milestone gate: `{result.global_level_active_ready}`\n"
        f"- Global level derived, strict: `{result.global_level_derived_ready}`\n"
        f"- Global level all strict: `{result.global_level_ready}`\n"
        f"- Global arrays milestone ready: `{result.global_arrays_ready}`\n"
        f"- XSTAR-vector matrix closure: `{result.matrix_closure_status}`\n"
        f"- Element thermal diagnostic ready: `{result.element_thermal_diagnostic_ready}`\n"
        f"- Same-call matrix status: `{result.same_call_matrix_status}`\n"
        f"- Same-call topology ready: `{result.same_call_matrix_topology_ready}`\n"
        f"- Same-call coefficients, all strict: `{result.same_call_matrix_coefficient_ready}`\n"
        f"- Same-call active closure ready: `{result.same_call_matrix_active_closure_ready}`\n"
        f"- XSTAR thermal-family status: `{result.thermal_family_status}`\n"
        f"- Same-call initial solver population: `{result.initial_solver_population_status}`\n"
        f"- Same-call initial solver population ready: `{result.initial_solver_population_ready}`\n"
        f"- Final msolvelucy snapshot status: `{result.final_solver_snapshot_status}`\n"
        f"- Final snapshot synchronization gate: `{result.final_solver_same_iteration_ready}`\n"
        f"- Final snapshot iteration tuple: `{result.final_solver_iteration_tuple_ready}`\n"
        f"- Final snapshot dimensions: `{result.final_solver_matrix_dimension_ready}`\n"
        f"- Final snapshot population columns: `{result.final_solver_population_columns_ready}`\n"
        f"- Final snapshot topology: `{result.final_solver_topology_ready}`\n"
        f"- Final snapshot active populations: `{result.final_solver_active_population_ready}`\n"
        f"- Final outer-start populations: `{result.final_solver_outer_start_ready}`\n"
        f"- Source-order xtot: `{result.final_solver_source_xtot_ready}`\n"
        f"- Rate-7 cj2 status: `{result.rate7_cj2_status}`\n"
        f"- Type-53/rate-7 cj2 ready: `{result.type53_rate7_cj2_ready}`\n"
        f"- Exact leveltemp energy status: `{result.leveltemp_energy_status}`\n"
        f"- Type-53 exact leveltemp energy ready: `{result.type53_leveltemp_energy_ready}`\n"
        f"- Oxygen O III--O V reassessment: `{result.oxygen_reassessment_status}`\n"
        f"- Oxygen pre-continuum acceptance: `{result.oxygen_pre_continuum_acceptance_ready}`\n"
        f"- All-element pre-continuum acceptance: `{result.all_element_pre_continuum_acceptance_ready}`\n"
        f"- All-element active solver ready: `{result.all_element_active_solver_ready}`\n"
        f"- All-element thermal ready: `{result.all_element_thermal_ready}`\n"
        f"- Acceptance gate ready: `{result.acceptance_gate_ready}`\n"
        f"- All-strict parity ready: `{result.strict_parity_ready}`\n"
        f"- Overall parity ready: `{result.parity_ready}`\n"
        f"- Population-weighted attribution rows: `{len(result.population_weighted_attribution)}`\n"
        f"- Active level/global-ion matrix-resolution rows: `{len(result.active_population_ion_resolution)}`\n"
        f"- Oxygen reassessment rows: `{len(result.oxygen_reassessment)}`\n"
    )
    return {
        "details_csv": str(details),
        "population_weighted_attribution_csv": str(attribution_path),
        "xstar_vector_matrix_closure_rows_csv": str(closure_rows_path),
        "xstar_vector_matrix_closure_summary_csv": str(closure_summary_path),
        "thermal_contribution_audit_csv": str(thermal_rows_path),
        "thermal_channel_summary_csv": str(thermal_summary_path),
        "thermal_family_summary_csv": str(thermal_family_path),
        "same_call_matrix_term_parity_csv": str(same_call_terms_path),
        "same_call_matrix_family_parity_csv": str(same_call_families_path),
        "same_call_active_row_attribution_csv": str(same_call_active_rows_path),
        "xstar_thermal_family_parity_csv": str(thermal_family_parity_path),
        "active_population_ion_matrix_resolution_csv": str(active_population_ion_resolution_path),
        "msolvelucy_initial_population_parity_csv": str(initial_solver_population_path),
        "msolvelucy_final_term_parity_csv": str(final_solver_term_path),
        "msolvelucy_final_population_parity_csv": str(final_solver_population_path),
        "msolvelucy_final_ion_totals_csv": str(final_solver_ion_total_path),
        "rate7_cj2_record_terms_csv": str(rate7_cj2_path),
        "rate7_cj2_record_summary_csv": str(rate7_cj2_record_path),
        "leveltemp_energy_parity_csv": str(leveltemp_energy_path),
        "leveltemp_workspace_trace_csv": str(leveltemp_trace_path),
        "type53_leveltemp_trace_csv": str(type53_leveltemp_trace_path),
        "oxygen_active_population_ion_reassessment_csv": str(oxygen_reassessment_path),
        "json": str(json_path),
        "markdown": str(md),
    }


__all__ = [
    "CalcHMCAllParityError",
    "CalcHMCAllProbeCritfReference",
    "CalcHMCAllProbeElementReference",
    "CalcHMCAllParityRow",
    "CalcHMCAllPreContinuumParityResult",
    "load_calc_hmc_all_probe_critf",
    "load_calc_hmc_all_probe_element_reference",
    "compare_calc_hmc_all_pre_continuum_probe",
    "write_calc_hmc_all_pre_continuum_parity_products",
]
