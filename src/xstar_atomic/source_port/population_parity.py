"""Population-parity gate for the source-faithful element solver.

The v0.4.6 port can assemble and converge the complete 607-row oxygen
``msolvelucy`` problem.  This module adds the scientific acceptance layer:
load the paired XSTAR population probe immediately before and after
``msolvelucy``, compare it with the Python solve, and repeat the Python solve
from XSTAR's captured pre-solve vector.  The two-run comparison distinguishes
an initial-population mismatch from a matrix/runtime-context mismatch without
introducing fitted coefficients or probe-backed rates.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
import csv
import json
import math

import numpy as np

from .element_equilibrium import (
    ElementEquilibriumContext,
    ElementMatrixAssembly,
    LucySolveResult,
    msolvelucy,
)


class PopulationParityError(RuntimeError):
    """Raised when an XSTAR population reference cannot be selected safely."""


@dataclass(frozen=True)
class XSTARPopulationReference:
    """Paired XSTAR population vectors for one ``msolvelucy`` call."""

    source_csv: str
    solve_call_id: str
    occurrence_rank: int
    element_z: int
    n_rows: int
    before: np.ndarray
    after: np.ndarray
    nsup: np.ndarray
    nion: np.ndarray
    metadata: Dict[str, Any]




@dataclass(frozen=True)
class XSTARRuntimeContextReference:
    """Runtime state attached to one paired XSTAR ``msolvelucy`` capture."""

    source_csv: str
    solve_call_id: str
    occurrence_rank: int
    element_z: int
    n_rows: int
    temperature_k: float
    hydrogen_density_cm3: float
    electron_fraction_xee: float
    electron_density_cm3: float
    covering_fraction: float
    metadata: Dict[str, Any]


@dataclass(frozen=True)
class PopulationMetrics:
    """Scale-aware comparison of one candidate population vector."""

    candidate_sum: float
    reference_sum: float
    max_abs_difference: float
    l1_difference: float
    l2_difference: float
    total_variation_distance: float
    max_active_relative_difference: float
    n_active_reference_rows: int
    n_rows_within_tolerance: int
    n_rows_outside_tolerance: int
    ready: bool


@dataclass
class ElementPopulationParityResult:
    """Native-seed and XSTAR-before-seed comparisons against one XSTAR solve."""

    reference: XSTARPopulationReference
    python_initial: np.ndarray
    python_native_final: np.ndarray
    python_seeded_final: Optional[np.ndarray]
    seeded_solve: Optional[LucySolveResult]
    initial_metrics: PopulationMetrics
    native_final_metrics: PopulationMetrics
    seeded_final_metrics: Optional[PopulationMetrics]
    nsup_topology_matches: bool
    nion_topology_matches: bool
    xstar_population_parity_ready: bool
    diagnosis: str
    seeded_l1_improvement_factor: float
    row_records: List[Dict[str, Any]]
    aggregate_records: List[Dict[str, Any]]
    max_abs_tolerance: float
    l1_tolerance: float
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


def _numeric_sort_key(value: str) -> Tuple[int, str]:
    parsed = _as_int(value, None)
    return (parsed if parsed is not None else 10**18, str(value))


def _read_rows(path: str | Path) -> List[Dict[str, str]]:
    target = Path(path)
    if not target.is_file():
        raise FileNotFoundError(str(target))
    with target.open("r", newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _capture_groups(rows: Sequence[Mapping[str, str]]) -> List[Dict[str, Any]]:
    """Return complete capture groups from modern or legacy probe CSVs."""
    grouped: Dict[Tuple[str, str], List[Mapping[str, str]]] = {}
    for row in rows:
        capture = str(row.get("capture_index") or row.get("stage_capture_index") or "").strip()
        stage = str(row.get("stage") or "").strip()
        grouped.setdefault((capture, stage), []).append(row)
    captures: List[Dict[str, Any]] = []
    for (capture, stage), members in grouped.items():
        members_sorted = sorted(members, key=lambda r: _as_int(r.get("level_index"), 0) or 0)
        first = members_sorted[0]
        ipmat = _as_int(first.get("ipmat2"), len(members_sorted)) or len(members_sorted)
        valid_indices = [_as_int(row.get("level_index"), None) for row in members_sorted]
        complete = (
            len(members_sorted) == ipmat
            and valid_indices == list(range(1, ipmat + 1))
        )
        captures.append(
            {
                "capture_index": capture,
                "solve_call_id": str(first.get("solve_call_id") or "").strip(),
                "stage": stage,
                "element_z": _as_int(first.get("element_z"), None),
                "ipmat2": ipmat,
                "rows": members_sorted,
                "complete": complete,
                "metadata": dict(first),
            }
        )
    captures.sort(key=lambda item: _numeric_sort_key(str(item["capture_index"])))
    return captures


def _pair_captures(captures: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    modern = any(str(capture.get("solve_call_id") or "") for capture in captures)
    pairs: List[Dict[str, Any]] = []
    if modern:
        by_solve: Dict[str, Dict[str, Mapping[str, Any]]] = {}
        for capture in captures:
            solve_id = str(capture.get("solve_call_id") or "").strip()
            if not solve_id:
                continue
            by_solve.setdefault(solve_id, {})[str(capture.get("stage") or "")] = capture
        for solve_id, stages in sorted(by_solve.items(), key=lambda item: _numeric_sort_key(item[0])):
            before = stages.get("before_msolvelucy")
            after = stages.get("after_msolvelucy")
            if before is not None and after is not None:
                pairs.append({"solve_call_id": solve_id, "before": before, "after": after})
        return pairs

    # Legacy v0.3.188 fallback: pair each complete before capture with the next
    # complete after capture having the same element and matrix dimension.
    used_after: set[int] = set()
    for i, before in enumerate(captures):
        if before.get("stage") != "before_msolvelucy" or not before.get("complete"):
            continue
        for j in range(i + 1, len(captures)):
            after = captures[j]
            if j in used_after or after.get("stage") != "after_msolvelucy" or not after.get("complete"):
                continue
            if before.get("element_z") == after.get("element_z") and before.get("ipmat2") == after.get("ipmat2"):
                used_after.add(j)
                pairs.append(
                    {
                        "solve_call_id": f"legacy_{before.get('capture_index')}_{after.get('capture_index')}",
                        "before": before,
                        "after": after,
                    }
                )
                break
    return pairs




def load_xstar_runtime_context_reference(
    path: str | Path,
    *,
    element_z: int,
    solve_call_id: Optional[str] = None,
    occurrence_rank: int = -1,
) -> XSTARRuntimeContextReference:
    """Select the runtime state for one complete paired population capture.

    This selection intentionally occurs before native matrix assembly so every
    temperature- and density-dependent ``ucalc`` branch is evaluated at the
    exact XSTAR state being used for population and iteration parity.
    """
    rows = _read_rows(path)
    captures = _capture_groups(rows)
    pairs = _pair_captures(captures)
    matching = [
        pair for pair in pairs
        if _as_int(pair["before"].get("element_z"), None) == int(element_z)
        and _as_int(pair["after"].get("element_z"), None) == int(element_z)
        and bool(pair["before"].get("complete"))
        and bool(pair["after"].get("complete"))
    ]
    if not matching:
        raise PopulationParityError(
            f"no complete before/after msolvelucy pair for element_z={element_z} in {path}"
        )
    selected: Optional[Dict[str, Any]] = None
    selected_rank = 0
    if solve_call_id is not None:
        token = str(solve_call_id).strip()
        for rank, pair in enumerate(matching, start=1):
            if str(pair.get("solve_call_id") or "").strip() == token:
                selected = pair
                selected_rank = rank
                break
        if selected is None:
            raise PopulationParityError(f"solve_call_id={token} was not found among matching captures")
    else:
        if occurrence_rank == -1:
            selected = matching[-1]
            selected_rank = len(matching)
        elif 1 <= occurrence_rank <= len(matching):
            selected = matching[occurrence_rank - 1]
            selected_rank = occurrence_rank
        else:
            raise PopulationParityError(
                f"occurrence_rank={occurrence_rank} outside 1..{len(matching)}, or use -1"
            )
    assert selected is not None
    before_meta = dict(selected["before"].get("metadata") or {})
    after_meta = dict(selected["after"].get("metadata") or {})
    metadata = {**before_meta, **after_meta}
    temperature_1e4 = _as_float(metadata.get("t_xstar_1e4K"), None)
    xpx = _as_float(metadata.get("xpx"), None)
    xee = _as_float(metadata.get("xee"), None)
    cfrac = _as_float(metadata.get("cfrac"), None)
    missing = [
        name for name, value in (
            ("t_xstar_1e4K", temperature_1e4),
            ("xpx", xpx),
            ("xee", xee),
            ("cfrac", cfrac),
        ) if value is None
    ]
    if missing:
        raise PopulationParityError(
            "selected population probe lacks runtime fields: " + ", ".join(missing)
        )
    temperature_k = float(temperature_1e4) * 1.0e4
    hydrogen_density = float(xpx)
    electron_fraction = float(xee)
    covering_fraction = float(cfrac)
    if temperature_k <= 0.0 or hydrogen_density <= 0.0 or electron_fraction <= 0.0:
        raise PopulationParityError(
            "selected population probe has nonpositive temperature, xpx, or xee"
        )
    n_rows = _as_int(selected["before"].get("ipmat2"), 0) or 0
    metadata.update({
        "before_capture_index": selected["before"].get("capture_index"),
        "after_capture_index": selected["after"].get("capture_index"),
        "n_matching_pairs": len(matching),
    })
    return XSTARRuntimeContextReference(
        source_csv=str(Path(path)),
        solve_call_id=str(selected.get("solve_call_id") or ""),
        occurrence_rank=selected_rank,
        element_z=int(element_z),
        n_rows=int(n_rows),
        temperature_k=temperature_k,
        hydrogen_density_cm3=hydrogen_density,
        electron_fraction_xee=electron_fraction,
        electron_density_cm3=hydrogen_density * electron_fraction,
        covering_fraction=covering_fraction,
        metadata=metadata,
    )


def load_xstar_population_reference(
    path: str | Path,
    *,
    element_z: int,
    n_rows: int,
    solve_call_id: Optional[str] = None,
    occurrence_rank: int = -1,
) -> XSTARPopulationReference:
    """Select one complete paired population capture.

    Selection is restricted to the requested element and compact dimension.
    ``solve_call_id`` takes precedence.  Otherwise ``occurrence_rank`` is
    1-based, with ``-1`` selecting the latest matching pair.
    """
    rows = _read_rows(path)
    captures = _capture_groups(rows)
    pairs = _pair_captures(captures)
    matching = [
        pair for pair in pairs
        if _as_int(pair["before"].get("element_z"), None) == int(element_z)
        and _as_int(pair["after"].get("element_z"), None) == int(element_z)
        and _as_int(pair["before"].get("ipmat2"), None) == int(n_rows)
        and _as_int(pair["after"].get("ipmat2"), None) == int(n_rows)
        and bool(pair["before"].get("complete"))
        and bool(pair["after"].get("complete"))
    ]
    if not matching:
        raise PopulationParityError(
            f"no complete before/after msolvelucy pair for element_z={element_z}, n_rows={n_rows} in {path}"
        )
    selected: Optional[Dict[str, Any]] = None
    selected_rank = 0
    if solve_call_id is not None:
        token = str(solve_call_id).strip()
        for rank, pair in enumerate(matching, start=1):
            if str(pair.get("solve_call_id") or "").strip() == token:
                selected = pair
                selected_rank = rank
                break
        if selected is None:
            raise PopulationParityError(f"solve_call_id={token} was not found among matching captures")
    else:
        if occurrence_rank == -1:
            selected_rank = len(matching)
            selected = matching[-1]
        elif occurrence_rank >= 1 and occurrence_rank <= len(matching):
            selected_rank = occurrence_rank
            selected = matching[occurrence_rank - 1]
        else:
            raise PopulationParityError(
                f"occurrence_rank={occurrence_rank} outside 1..{len(matching)}, or use -1"
            )
    assert selected is not None

    before_rows = selected["before"]["rows"]
    after_rows = selected["after"]["rows"]
    before = np.asarray([_as_float(row.get("x_population"), 0.0) or 0.0 for row in before_rows], dtype=float)
    after = np.asarray([_as_float(row.get("x_population"), 0.0) or 0.0 for row in after_rows], dtype=float)
    nsup = np.asarray([_as_int(row.get("nsup"), 0) or 0 for row in after_rows], dtype=np.int32)
    nion = np.asarray([_as_int(row.get("nion"), 0) or 0 for row in after_rows], dtype=np.int32)
    metadata = dict(selected["after"].get("metadata") or {})
    metadata.update(
        {
            "before_capture_index": selected["before"].get("capture_index"),
            "after_capture_index": selected["after"].get("capture_index"),
            "n_matching_pairs": len(matching),
        }
    )
    return XSTARPopulationReference(
        source_csv=str(Path(path)),
        solve_call_id=str(selected.get("solve_call_id") or ""),
        occurrence_rank=selected_rank,
        element_z=int(element_z),
        n_rows=int(n_rows),
        before=before,
        after=after,
        nsup=nsup,
        nion=nion,
        metadata=metadata,
    )


def _metrics(
    candidate: np.ndarray,
    reference: np.ndarray,
    *,
    max_abs_tolerance: float,
    l1_tolerance: float,
    relative_tolerance: float,
    relative_floor: float,
) -> PopulationMetrics:
    candidate = np.asarray(candidate, dtype=float)
    reference = np.asarray(reference, dtype=float)
    if candidate.shape != reference.shape:
        raise PopulationParityError(f"population shape mismatch: {candidate.shape} versus {reference.shape}")
    delta = candidate - reference
    absolute = np.abs(delta)
    active = np.abs(reference) > float(relative_floor)
    relative = np.zeros_like(absolute)
    relative[active] = absolute[active] / np.abs(reference[active])
    tolerance_by_row = float(max_abs_tolerance) + float(relative_tolerance) * np.abs(reference)
    within = absolute <= tolerance_by_row
    l1 = float(np.sum(absolute))
    return PopulationMetrics(
        candidate_sum=float(np.sum(candidate)),
        reference_sum=float(np.sum(reference)),
        max_abs_difference=float(np.max(absolute)) if absolute.size else 0.0,
        l1_difference=l1,
        l2_difference=float(np.linalg.norm(delta)),
        total_variation_distance=0.5 * l1,
        max_active_relative_difference=float(np.max(relative[active])) if np.any(active) else 0.0,
        n_active_reference_rows=int(np.count_nonzero(active)),
        n_rows_within_tolerance=int(np.count_nonzero(within)),
        n_rows_outside_tolerance=int(np.count_nonzero(~within)),
        ready=bool(
            (float(np.max(absolute)) if absolute.size else 0.0) <= float(max_abs_tolerance)
            and l1 <= float(l1_tolerance)
        ),
    )


def compare_element_population_parity(
    assembly: ElementMatrixAssembly,
    native_solve: LucySolveResult,
    context: ElementEquilibriumContext,
    reference: XSTARPopulationReference,
    *,
    run_xstar_before_seeded_solve: bool = True,
    max_abs_tolerance: float = 5.0e-3,
    l1_tolerance: float = 5.0e-3,
    relative_tolerance: float = 5.0e-3,
    relative_floor: float = 1.0e-12,
) -> ElementPopulationParityResult:
    """Compare the native and XSTAR-before-seeded Python solves to XSTAR."""
    n = assembly.basis.n_rows
    if reference.n_rows != n:
        raise PopulationParityError(f"reference has {reference.n_rows} rows, Python basis has {n}")
    python_initial = np.asarray(assembly.initial_populations[1 : n + 1], dtype=float).copy()
    initial_sum = float(np.sum(python_initial))
    if initial_sum > 0:
        python_initial /= initial_sum
    native_final = np.asarray(native_solve.populations, dtype=float).copy()

    initial_metrics = _metrics(
        python_initial,
        reference.before,
        max_abs_tolerance=max_abs_tolerance,
        l1_tolerance=l1_tolerance,
        relative_tolerance=relative_tolerance,
        relative_floor=relative_floor,
    )
    native_metrics = _metrics(
        native_final,
        reference.after,
        max_abs_tolerance=max_abs_tolerance,
        l1_tolerance=l1_tolerance,
        relative_tolerance=relative_tolerance,
        relative_floor=relative_floor,
    )

    seeded_solve: Optional[LucySolveResult] = None
    seeded_final: Optional[np.ndarray] = None
    seeded_metrics: Optional[PopulationMetrics] = None
    if run_xstar_before_seeded_solve:
        one_based = np.zeros(n + 1, dtype=float)
        one_based[1:] = reference.before
        seeded_assembly = replace(assembly, initial_populations=one_based)
        seeded_solve = msolvelucy(seeded_assembly, context)
        seeded_final = np.asarray(seeded_solve.populations, dtype=float).copy()
        seeded_metrics = _metrics(
            seeded_final,
            reference.after,
            max_abs_tolerance=max_abs_tolerance,
            l1_tolerance=l1_tolerance,
            relative_tolerance=relative_tolerance,
            relative_floor=relative_floor,
        )

    python_nsup = assembly.basis.nsup[1:]
    python_ion_counter = assembly.basis.nion[1:]
    python_ion_stage = assembly.basis.ion_stage[1:]
    nsup_matches = bool(np.array_equal(python_nsup, reference.nsup))
    # The XSTAR population probe column named ``nion`` contains the physical
    # ion stage (O III=3, ..., O VIII=8), not the compact block ordinal
    # (1, ..., 6) used internally by the Python Lucy solver.
    nion_matches = bool(np.array_equal(python_ion_stage, reference.nion))

    if native_metrics.ready and nsup_matches and nion_matches:
        diagnosis = "population_parity_reproduced_from_python_native_seed"
        ready = True
    elif seeded_metrics is not None and seeded_metrics.ready and nsup_matches and nion_matches:
        diagnosis = "initial_population_state_mismatch"
        ready = False
    elif seeded_metrics is not None and seeded_metrics.l1_difference < 0.5 * native_metrics.l1_difference:
        diagnosis = "initial_state_contributes_but_operator_or_runtime_context_still_mismatched"
        ready = False
    elif not nsup_matches or not nion_matches:
        diagnosis = "compact_basis_nsup_or_nion_topology_mismatch"
        ready = False
    else:
        diagnosis = "assembled_operator_or_runtime_context_mismatch"
        ready = False

    improvement = 1.0
    if seeded_metrics is not None:
        improvement = native_metrics.l1_difference / max(seeded_metrics.l1_difference, 1.0e-300)

    rows: List[Dict[str, Any]] = []
    for i in range(n):
        seeded_value: Any = "" if seeded_final is None else float(seeded_final[i])
        rows.append(
            {
                "compact_index": i + 1,
                "python_nsup": int(python_nsup[i]),
                "xstar_nsup": int(reference.nsup[i]),
                "nsup_matches": bool(python_nsup[i] == reference.nsup[i]),
                "python_ion_counter": int(python_ion_counter[i]),
                "python_ion_stage": int(python_ion_stage[i]),
                "xstar_nion": int(reference.nion[i]),
                "nion_matches": bool(python_ion_stage[i] == reference.nion[i]),
                "xstar_before_population": float(reference.before[i]),
                "python_initial_population": float(python_initial[i]),
                "initial_minus_xstar_before": float(python_initial[i] - reference.before[i]),
                "xstar_after_population": float(reference.after[i]),
                "python_native_final_population": float(native_final[i]),
                "native_minus_xstar_after": float(native_final[i] - reference.after[i]),
                "python_xstar_before_seeded_final_population": seeded_value,
                "seeded_minus_xstar_after": "" if seeded_final is None else float(seeded_final[i] - reference.after[i]),
            }
        )

    aggregates: List[Dict[str, Any]] = []
    for kind, labels in (("superlevel", reference.nsup), ("ion", reference.nion)):
        for label in sorted(set(int(value) for value in labels if int(value) > 0)):
            mask = labels == label
            aggregates.append(
                {
                    "aggregate_kind": kind,
                    "aggregate_index": label,
                    "n_rows": int(np.count_nonzero(mask)),
                    "xstar_before_population": float(np.sum(reference.before[mask])),
                    "python_initial_population": float(np.sum(python_initial[mask])),
                    "xstar_after_population": float(np.sum(reference.after[mask])),
                    "python_native_final_population": float(np.sum(native_final[mask])),
                    "python_xstar_before_seeded_final_population": "" if seeded_final is None else float(np.sum(seeded_final[mask])),
                    "native_abs_difference": float(abs(np.sum(native_final[mask]) - np.sum(reference.after[mask]))),
                    "seeded_abs_difference": "" if seeded_final is None else float(abs(np.sum(seeded_final[mask]) - np.sum(reference.after[mask]))),
                }
            )

    return ElementPopulationParityResult(
        reference=reference,
        python_initial=python_initial,
        python_native_final=native_final,
        python_seeded_final=seeded_final,
        seeded_solve=seeded_solve,
        initial_metrics=initial_metrics,
        native_final_metrics=native_metrics,
        seeded_final_metrics=seeded_metrics,
        nsup_topology_matches=nsup_matches,
        nion_topology_matches=nion_matches,
        xstar_population_parity_ready=ready,
        diagnosis=diagnosis,
        seeded_l1_improvement_factor=float(improvement),
        row_records=rows,
        aggregate_records=aggregates,
        max_abs_tolerance=float(max_abs_tolerance),
        l1_tolerance=float(l1_tolerance),
        relative_tolerance=float(relative_tolerance),
        relative_floor=float(relative_floor),
    )


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields: List[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(str(key))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields or ["status"], extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _metrics_dict(prefix: str, metrics: PopulationMetrics) -> Dict[str, Any]:
    return {f"{prefix}_{key}": value for key, value in metrics.__dict__.items()}


def write_element_population_parity_products(
    result: ElementPopulationParityResult,
    out_dir: str | Path,
    *,
    port_version: str = "v0.4.27",
) -> Dict[str, Path]:
    """Write row, aggregate, JSON, Markdown, and NPZ parity products."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows_csv = out / "xstar_element_population_parity_rows.csv"
    aggregates_csv = out / "xstar_element_population_parity_aggregates.csv"
    _write_csv(rows_csv, result.row_records)
    _write_csv(aggregates_csv, result.aggregate_records)

    summary: Dict[str, Any] = {
        "port_version": port_version,
        "status": "xstar_element_population_parity_completed",
        "xstar_population_probe_csv": result.reference.source_csv,
        "selected_solve_call_id": result.reference.solve_call_id,
        "selected_occurrence_rank": result.reference.occurrence_rank,
        "element_z": result.reference.element_z,
        "n_rows": result.reference.n_rows,
        "xstar_before_population_sum": float(np.sum(result.reference.before)),
        "xstar_after_population_sum": float(np.sum(result.reference.after)),
        "nsup_topology_matches": result.nsup_topology_matches,
        "nion_topology_matches": result.nion_topology_matches,
        "xstar_population_parity_ready": result.xstar_population_parity_ready,
        "population_parity_diagnosis": result.diagnosis,
        "seeded_l1_improvement_factor": result.seeded_l1_improvement_factor,
        "max_abs_tolerance": result.max_abs_tolerance,
        "l1_tolerance": result.l1_tolerance,
        "relative_tolerance": result.relative_tolerance,
        "relative_floor": result.relative_floor,
        "xstar_probe_metadata": result.reference.metadata,
    }
    summary.update(_metrics_dict("python_initial_vs_xstar_before", result.initial_metrics))
    summary.update(_metrics_dict("python_native_final_vs_xstar_after", result.native_final_metrics))
    if result.seeded_final_metrics is not None:
        summary.update(_metrics_dict("python_xstar_before_seeded_final_vs_xstar_after", result.seeded_final_metrics))
        summary.update(
            {
                "seeded_solver_converged": bool(result.seeded_solve and result.seeded_solve.converged),
                "seeded_solver_outer_iterations": 0 if result.seeded_solve is None else result.seeded_solve.outer_iterations,
                "seeded_solver_fixed_point_iterations": 0 if result.seeded_solve is None else result.seeded_solve.fixed_point_iterations,
            }
        )

    json_path = out / "xstar_element_population_parity_summary.json"
    json_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    markdown_path = out / "xstar_element_population_parity_summary.md"
    markdown_path.write_text(
        "\n".join(
            [
                "# XSTAR element population parity",
                "",
                f"- Port version: `{port_version}`",
                f"- Selected solve call: `{result.reference.solve_call_id}`",
                f"- Rows: `{result.reference.n_rows}`",
                f"- Python initial vs XSTAR before L1: `{result.initial_metrics.l1_difference}`",
                f"- Native final vs XSTAR after L1: `{result.native_final_metrics.l1_difference}`",
                f"- XSTAR-before-seeded final vs XSTAR after L1: `{'' if result.seeded_final_metrics is None else result.seeded_final_metrics.l1_difference}`",
                f"- NSUP topology matches: `{result.nsup_topology_matches}`",
                f"- NION topology matches: `{result.nion_topology_matches}`",
                f"- Population parity ready: `{result.xstar_population_parity_ready}`",
                f"- Diagnosis: `{result.diagnosis}`",
                "",
                "No XSTAR population or matrix coefficient is inserted into the production solve. "
                "The captured pre-solve vector is used only for the controlled alternate-seed discriminator.",
            ]
        )
        + "\n"
    )
    seeded_trace_outputs: Dict[str, Path] = {}
    if result.seeded_solve is not None and result.seeded_solve.trace is not None:
        trace_specs = [
            ("seeded_lucy_outer_trace_csv", "xstar_msolvelucy_xstar_before_seeded_outer_level_trace.csv", result.seeded_solve.trace.outer_level_rows),
            ("seeded_lucy_superlevel_trace_csv", "xstar_msolvelucy_xstar_before_seeded_superlevel_trace.csv", result.seeded_solve.trace.superlevel_rows),
            ("seeded_lucy_condensed_matrix_trace_csv", "xstar_msolvelucy_xstar_before_seeded_condensed_matrix_trace.csv", result.seeded_solve.trace.condensed_matrix_rows),
            ("seeded_lucy_fixed_point_trace_csv", "xstar_msolvelucy_xstar_before_seeded_fixed_point_trace.csv", result.seeded_solve.trace.fixed_point_rows),
        ]
        for key, filename, trace_rows in trace_specs:
            path = out / filename
            _write_csv(path, trace_rows)
            seeded_trace_outputs[key] = path

    npz_path = out / "xstar_element_population_parity.npz"
    np.savez_compressed(
        npz_path,
        xstar_before=result.reference.before,
        xstar_after=result.reference.after,
        python_initial=result.python_initial,
        python_native_final=result.python_native_final,
        python_xstar_before_seeded_final=np.asarray([] if result.python_seeded_final is None else result.python_seeded_final),
        xstar_nsup=result.reference.nsup,
        xstar_nion=result.reference.nion,
    )
    return {
        "population_parity_rows_csv": rows_csv,
        "population_parity_aggregates_csv": aggregates_csv,
        "population_parity_npz": npz_path,
        "population_parity_json": json_path,
        "population_parity_markdown": markdown_path,
        **seeded_trace_outputs,
    }
