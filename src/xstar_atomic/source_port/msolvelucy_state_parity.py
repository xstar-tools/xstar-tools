"""Iteration-level parity between instrumented XSTAR and Python ``msolvelucy``.

The comparator consumes the CSVs produced by
:mod:`xstar_atomic.xstar_msolvelucy_state_probe` and the long-form Python trace
captured by :func:`xstar_atomic.source_port.element_equilibrium.msolvelucy`.
It is intentionally a pure comparison layer: no probed quantity is inserted
into the production matrix or population solve.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
import csv
import json
import math

from .element_equilibrium import LucyIterationTrace


class MSolveStateParityError(RuntimeError):
    """Raised when state-probe products are missing or inconsistent."""


@dataclass(frozen=True)
class StateComponentMetrics:
    component: str
    n_values: int
    max_abs_difference: float
    l1_difference: float
    max_active_relative_difference: float
    n_outside_tolerance: int
    ready: bool


@dataclass
class MSolveStateParityResult:
    solve_call_id: str
    source_dir: str
    comparison_trace_source: str
    component_metrics: List[StateComponentMetrics]
    detail_rows: List[Dict[str, Any]]
    msolvelucy_state_parity_ready: bool
    first_failing_component: str
    first_failing_comparison_key: str
    first_failing_outer_iteration: int
    first_failing_fixed_iteration: int
    diagnosis: str
    absolute_tolerance: float
    relative_tolerance: float
    relative_floor: float


def _as_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    try:
        if value is None or str(value).strip() == "":
            return default
        number = float(value)
        return int(round(number)) if math.isfinite(number) else default
    except Exception:
        return default


def _as_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None or str(value).strip() == "":
            return default
        number = float(value)
        return number if math.isfinite(number) else default
    except Exception:
        return default


def _read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(str(path))
    with path.open("r", newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _probe_path(root: Path, filename: str) -> Path:
    direct = root / filename
    if direct.is_file():
        return direct
    hits = sorted(root.rglob(filename))
    if hits:
        return hits[0]
    raise FileNotFoundError(f"{filename} not found under {root}")


def _filter_solve(rows: Iterable[Mapping[str, str]], solve_call_id: str) -> List[Dict[str, str]]:
    token = str(solve_call_id).strip()
    return [dict(row) for row in rows if str(row.get("solve_call_id") or "").strip() == token]


def _append_detail(
    details: List[Dict[str, Any]],
    *,
    component: str,
    key: str,
    xstar_value: float,
    python_value: float,
    absolute_tolerance: float,
    relative_tolerance: float,
    relative_floor: float,
    metadata: Mapping[str, Any],
) -> None:
    absolute = abs(float(python_value) - float(xstar_value))
    active = abs(float(xstar_value)) > float(relative_floor)
    relative = absolute / abs(float(xstar_value)) if active else 0.0
    tolerance = float(absolute_tolerance) + float(relative_tolerance) * abs(float(xstar_value))
    details.append(
        {
            "component": component,
            "comparison_key": key,
            **dict(metadata),
            "xstar_value": float(xstar_value),
            "python_value": float(python_value),
            "signed_difference": float(python_value) - float(xstar_value),
            "absolute_difference": absolute,
            "relative_difference": relative,
            "reference_active": active,
            "tolerance": tolerance,
            "within_tolerance": bool(absolute <= tolerance),
        }
    )


def compare_msolvelucy_state_probe(
    trace: LucyIterationTrace,
    probe_dir: str | Path,
    *,
    solve_call_id: str,
    comparison_trace_source: str,
    absolute_tolerance: float = 1.0e-10,
    relative_tolerance: float = 5.0e-5,
    relative_floor: float = 1.0e-30,
) -> MSolveStateParityResult:
    """Compare all available XSTAR state-probe rows to one Python trace."""
    root = Path(probe_dir)
    levels = _filter_solve(_read_csv(_probe_path(root, "xstar_msolvelucy_levels_probe.csv")), solve_call_id)
    rr_rows = _filter_solve(_read_csv(_probe_path(root, "xstar_msolvelucy_rr_probe.csv")), solve_call_id)
    superlevels = _filter_solve(_read_csv(_probe_path(root, "xstar_msolvelucy_superlevels_probe.csv")), solve_call_id)
    matrix_rows = _filter_solve(_read_csv(_probe_path(root, "xstar_msolvelucy_condensed_matrix_probe.csv")), solve_call_id)
    fixed_rows = _filter_solve(_read_csv(_probe_path(root, "xstar_msolvelucy_fixed_probe.csv")), solve_call_id)
    if not levels:
        raise MSolveStateParityError(f"no state rows for solve_call_id={solve_call_id}")

    py_outer = {
        (int(row["outer_iteration"]), int(row["compact_index"])): row
        for row in trace.outer_level_rows
    }
    py_super = {
        (int(row["outer_iteration"]), int(row["superlevel"])): row
        for row in trace.superlevel_rows
    }
    py_matrix = {
        (int(row["outer_iteration"]), int(row["row_superlevel"]), int(row["column_superlevel"])): row
        for row in trace.condensed_matrix_rows
    }
    py_fixed = {
        (int(row["outer_iteration"]), int(row["fixed_iteration"]), int(row["compact_index"])): row
        for row in trace.fixed_point_rows
    }

    details: List[Dict[str, Any]] = []

    level_field = {
        "outer_start": "population_outer_start",
        "after_condensed_solve": "population_after_condensed",
        "outer_end": "population_after_fixed_point",
    }
    for row in levels:
        phase = str(row.get("phase") or "").strip()
        field = level_field.get(phase)
        if field is None:
            continue
        key = (_as_int(row.get("outer_iteration"), 0) or 0, _as_int(row.get("compact_index"), 0) or 0)
        py = py_outer.get(key)
        if py is None:
            raise MSolveStateParityError(f"missing Python outer trace row {key}")
        _append_detail(
            details,
            component=f"level_{phase}",
            key=f"outer={key[0]},row={key[1]}",
            xstar_value=_as_float(row.get("population"), 0.0) or 0.0,
            python_value=float(py[field]),
            absolute_tolerance=absolute_tolerance,
            relative_tolerance=relative_tolerance,
            relative_floor=relative_floor,
            metadata={"outer_iteration": key[0], "compact_index": key[1], "phase": phase},
        )

    for row in rr_rows:
        key = (_as_int(row.get("outer_iteration"), 0) or 0, _as_int(row.get("compact_index"), 0) or 0)
        py = py_outer.get(key)
        if py is None:
            raise MSolveStateParityError(f"missing Python rr trace row {key}")
        for component, column, field in (
            ("rr_population", "population", "population_outer_start"),
            ("rr_fraction", "rr", "rr"),
        ):
            _append_detail(
                details,
                component=component,
                key=f"outer={key[0]},row={key[1]}",
                xstar_value=_as_float(row.get(column), 0.0) or 0.0,
                python_value=float(py[field]),
                absolute_tolerance=absolute_tolerance,
                relative_tolerance=relative_tolerance,
                relative_floor=relative_floor,
                metadata={"outer_iteration": key[0], "compact_index": key[1]},
            )

    for row in superlevels:
        outer = _as_int(row.get("outer_iteration"), 0) or 0
        superlevel = _as_int(row.get("superlevel"), 0) or 0
        phase = str(row.get("phase") or "").strip()
        py = py_super.get((outer, superlevel))
        if py is None:
            raise MSolveStateParityError(f"missing Python superlevel trace row {(outer, superlevel)}")
        field = (
            "population_before_condensed_solve"
            if phase == "before_condensed_solve"
            else "population_after_condensed_solve"
        )
        _append_detail(
            details,
            component=f"superlevel_{phase}",
            key=f"outer={outer},superlevel={superlevel}",
            xstar_value=_as_float(row.get("population"), 0.0) or 0.0,
            python_value=float(py[field]),
            absolute_tolerance=absolute_tolerance,
            relative_tolerance=relative_tolerance,
            relative_floor=relative_floor,
            metadata={"outer_iteration": outer, "superlevel": superlevel, "phase": phase},
        )

    for row in matrix_rows:
        key = (
            _as_int(row.get("outer_iteration"), 0) or 0,
            _as_int(row.get("row_superlevel"), 0) or 0,
            _as_int(row.get("column_superlevel"), 0) or 0,
        )
        py = py_matrix.get(key)
        if py is None:
            raise MSolveStateParityError(f"missing Python condensed matrix row {key}")
        _append_detail(
            details,
            component="condensed_matrix_raw",
            key=f"outer={key[0]},row={key[1]},column={key[2]}",
            xstar_value=_as_float(row.get("matrix_value"), 0.0) or 0.0,
            python_value=float(py["raw_matrix_value"]),
            absolute_tolerance=absolute_tolerance,
            relative_tolerance=relative_tolerance,
            relative_floor=relative_floor,
            metadata={"outer_iteration": key[0], "row_superlevel": key[1], "column_superlevel": key[2]},
        )

    fixed_fields = (
        ("fixed_population_before", "population_before", "population_before"),
        ("fixed_riu", "riu", "riu"),
        ("fixed_rui", "rui", "rui"),
        ("fixed_ril", "ril", "ril"),
        ("fixed_rli", "rli", "rli"),
        ("fixed_population_after", "population_after", "population_after"),
    )
    for row in fixed_rows:
        key = (
            _as_int(row.get("outer_iteration"), 0) or 0,
            _as_int(row.get("fixed_iteration"), 0) or 0,
            _as_int(row.get("compact_index"), 0) or 0,
        )
        py = py_fixed.get(key)
        if py is None:
            raise MSolveStateParityError(f"missing Python fixed-point trace row {key}")
        for component, column, field in fixed_fields:
            _append_detail(
                details,
                component=component,
                key=f"outer={key[0]},fixed={key[1]},row={key[2]}",
                xstar_value=_as_float(row.get(column), 0.0) or 0.0,
                python_value=float(py[field]),
                absolute_tolerance=absolute_tolerance,
                relative_tolerance=relative_tolerance,
                relative_floor=relative_floor,
                metadata={"outer_iteration": key[0], "fixed_iteration": key[1], "compact_index": key[2]},
            )

    if not details:
        raise MSolveStateParityError("state-probe comparison produced no matched values")

    component_order = [
        "level_outer_start",
        "rr_population",
        "rr_fraction",
        "superlevel_before_condensed_solve",
        "condensed_matrix_raw",
        "superlevel_after_condensed_solve",
        "level_after_condensed_solve",
        "fixed_population_before",
        "fixed_riu",
        "fixed_rui",
        "fixed_ril",
        "fixed_rli",
        "fixed_population_after",
        "level_outer_end",
    ]
    metrics: List[StateComponentMetrics] = []
    by_component: Dict[str, List[Dict[str, Any]]] = {}
    for row in details:
        by_component.setdefault(str(row["component"]), []).append(row)
    for component in component_order + sorted(set(by_component) - set(component_order)):
        rows = by_component.get(component)
        if not rows:
            continue
        active_rel = [float(row["relative_difference"]) for row in rows if row["reference_active"]]
        metrics.append(
            StateComponentMetrics(
                component=component,
                n_values=len(rows),
                max_abs_difference=max(float(row["absolute_difference"]) for row in rows),
                l1_difference=sum(float(row["absolute_difference"]) for row in rows),
                max_active_relative_difference=max(active_rel) if active_rel else 0.0,
                n_outside_tolerance=sum(not bool(row["within_tolerance"]) for row in rows),
                ready=all(bool(row["within_tolerance"]) for row in rows),
            )
        )
    # Component-level metrics aggregate all outer iterations.  Once an early
    # matrix mismatch changes the population vector, every outer-start value in
    # the following iteration also differs.  Selecting the first failed
    # *component aggregate* therefore misdiagnoses a downstream outer-start
    # difference as an input-seed problem.  Identify the first failed scalar in
    # actual msolvelucy execution order instead.
    fixed_component_order = {
        "fixed_population_before": 0,
        "fixed_riu": 1,
        "fixed_rui": 2,
        "fixed_ril": 3,
        "fixed_rli": 4,
        "fixed_population_after": 5,
    }
    phase_order = {
        "level_outer_start": 0,
        "rr_population": 1,
        "rr_fraction": 2,
        "superlevel_before_condensed_solve": 3,
        "condensed_matrix_raw": 4,
        "superlevel_after_condensed_solve": 5,
        "level_after_condensed_solve": 6,
        "level_outer_end": 8,
    }

    def execution_key(row: Mapping[str, Any]) -> Tuple[int, int, int, int, int, int, str]:
        component = str(row.get("component") or "")
        outer = int(row.get("outer_iteration") or 0)
        fixed = int(row.get("fixed_iteration") or 0)
        compact = int(row.get("compact_index") or 0)
        superlevel = int(row.get("superlevel") or 0)
        matrix_row = int(row.get("row_superlevel") or 0)
        matrix_column = int(row.get("column_superlevel") or 0)
        if component in fixed_component_order:
            return (
                outer,
                7,
                fixed,
                fixed_component_order[component],
                compact,
                0,
                str(row.get("comparison_key") or ""),
            )
        index1 = compact or superlevel or matrix_row
        index2 = matrix_column
        return (
            outer,
            phase_order.get(component, 99),
            0,
            0,
            index1,
            index2,
            str(row.get("comparison_key") or ""),
        )

    failing_rows = sorted(
        (row for row in details if not bool(row["within_tolerance"])),
        key=execution_key,
    )
    first_failure_row = failing_rows[0] if failing_rows else None
    first_failure = "" if first_failure_row is None else str(first_failure_row["component"])
    first_failure_key = "" if first_failure_row is None else str(first_failure_row["comparison_key"])
    first_failure_outer = 0 if first_failure_row is None else int(first_failure_row.get("outer_iteration") or 0)
    first_failure_fixed = 0 if first_failure_row is None else int(first_failure_row.get("fixed_iteration") or 0)
    ready = first_failure_row is None
    diagnosis_map = {
        "level_outer_start": "xstar_before_seed_or_iteration_selection_mismatch",
        "rr_population": "outer_start_population_mismatch",
        "rr_fraction": "superlevel_partition_rr_mismatch",
        "superlevel_before_condensed_solve": "superlevel_population_aggregation_mismatch",
        "condensed_matrix_raw": "condensed_matrix_or_rate_assembly_mismatch",
        "superlevel_after_condensed_solve": "condensed_linear_solve_mismatch",
        "level_after_condensed_solve": "rr_times_superlevel_redistribution_mismatch",
        "fixed_population_before": "fixed_point_entry_state_mismatch",
        "fixed_riu": "fixed_point_upward_loss_rate_mismatch",
        "fixed_rui": "fixed_point_upward_source_mismatch",
        "fixed_ril": "fixed_point_downward_loss_rate_mismatch",
        "fixed_rli": "fixed_point_downward_source_mismatch",
        "fixed_population_after": "fixed_point_update_or_normalization_mismatch",
        "level_outer_end": "outer_iteration_end_state_mismatch",
    }
    diagnosis = "msolvelucy_iteration_state_parity_reproduced" if ready else diagnosis_map.get(first_failure, "msolvelucy_state_mismatch")
    return MSolveStateParityResult(
        solve_call_id=str(solve_call_id),
        source_dir=str(root),
        comparison_trace_source=str(comparison_trace_source),
        component_metrics=metrics,
        detail_rows=details,
        msolvelucy_state_parity_ready=ready,
        first_failing_component=first_failure,
        first_failing_comparison_key=first_failure_key,
        first_failing_outer_iteration=first_failure_outer,
        first_failing_fixed_iteration=first_failure_fixed,
        diagnosis=diagnosis,
        absolute_tolerance=float(absolute_tolerance),
        relative_tolerance=float(relative_tolerance),
        relative_floor=float(relative_floor),
    )


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields: List[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(str(key))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields or ["status"], extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_msolvelucy_state_parity_products(
    result: MSolveStateParityResult,
    out_dir: str | Path,
    *,
    port_version: str = "v0.4.28",
) -> Dict[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    detail_csv = out / "xstar_msolvelucy_state_parity_details.csv"
    component_csv = out / "xstar_msolvelucy_state_parity_components.csv"
    _write_csv(detail_csv, result.detail_rows)
    _write_csv(component_csv, [metric.__dict__ for metric in result.component_metrics])
    summary = {
        "port_version": port_version,
        "status": "xstar_msolvelucy_state_parity_completed",
        "solve_call_id": result.solve_call_id,
        "source_dir": result.source_dir,
        "comparison_trace_source": result.comparison_trace_source,
        "absolute_tolerance": result.absolute_tolerance,
        "relative_tolerance": result.relative_tolerance,
        "relative_floor": result.relative_floor,
        "n_compared_values": len(result.detail_rows),
        "msolvelucy_state_parity_ready": result.msolvelucy_state_parity_ready,
        "first_failing_component": result.first_failing_component,
        "first_failing_comparison_key": result.first_failing_comparison_key,
        "first_failing_outer_iteration": result.first_failing_outer_iteration,
        "first_failing_fixed_iteration": result.first_failing_fixed_iteration,
        "msolvelucy_state_parity_diagnosis": result.diagnosis,
        "component_metrics": [metric.__dict__ for metric in result.component_metrics],
    }
    json_path = out / "xstar_msolvelucy_state_parity_summary.json"
    json_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    markdown_path = out / "xstar_msolvelucy_state_parity_summary.md"
    markdown_path.write_text(
        "\n".join(
            [
                "# XSTAR/Python `msolvelucy` state parity",
                "",
                f"- Port version: `{port_version}`",
                f"- Solve call: `{result.solve_call_id}`",
                f"- Compared values: `{len(result.detail_rows)}`",
                f"- Trace source: `{result.comparison_trace_source}`",
                f"- State parity ready: `{result.msolvelucy_state_parity_ready}`",
                f"- First failing component: `{result.first_failing_component}`",
                f"- First failing comparison: `{result.first_failing_comparison_key}`",
                f"- First failing outer iteration: `{result.first_failing_outer_iteration}`",
                f"- First failing fixed iteration: `{result.first_failing_fixed_iteration}`",
                f"- Diagnosis: `{result.diagnosis}`",
            ]
        )
        + "\n"
    )
    return {
        "msolvelucy_state_parity_details_csv": detail_csv,
        "msolvelucy_state_parity_components_csv": component_csv,
        "msolvelucy_state_parity_json": json_path,
        "msolvelucy_state_parity_markdown": markdown_path,
    }
