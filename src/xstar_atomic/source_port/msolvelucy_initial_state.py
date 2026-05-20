"""Same-call ``calc_hmc_element`` input population state.

XSTAR maps the current global level population array ``xilevg`` into the
compact element vector ``x`` immediately before ``msolvelucy``.  This vector
is an input state of ``calc_hmc_element``; it is not the LTE vector returned by
``levwkelement``.  The bounded probe and loader in this module preserve that
source distinction for fixed-state regression runs.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence

import numpy as np

from .fortran_numbers import parse_fortran_float


class MSolveLucyInitialStateError(RuntimeError):
    """Raised when the bounded same-call input population probe is invalid."""


@dataclass(frozen=True)
class MSolveLucyInitialPopulationReference:
    """One complete compact vector captured immediately before ``msolvelucy``."""

    call_id: int
    element_index: int
    element_z: int
    compact_dimension: int
    populations: np.ndarray
    source_path: str

    @property
    def population_sum(self) -> float:
        return float(np.sum(self.populations))


def _read_rows(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        raise MSolveLucyInitialStateError(f"missing initial-population probe: {path}")
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise MSolveLucyInitialStateError(f"initial-population probe is empty: {path}")
    return rows


def _resolve_call_id(rows: Sequence[Mapping[str, str]], requested: Optional[int]) -> int:
    ids = sorted({int(row["calc_hmc_all_call_id"]) for row in rows})
    if requested is None:
        return ids[-1]
    if int(requested) not in ids:
        raise MSolveLucyInitialStateError(
            f"call id {requested} not present in initial-population probe; available={ids}"
        )
    return int(requested)


def load_msolvelucy_initial_population_reference(
    probe_dir: str | Path,
    *,
    element_z: int,
    call_id: Optional[int] = None,
) -> MSolveLucyInitialPopulationReference:
    """Load and validate the exact compact ``x`` vector entering ``msolvelucy``.

    The returned vector is zero-based and has exactly ``compact_dimension``
    entries.  No normalization or replacement is performed here: the source
    values are preserved as captured.
    """

    path = Path(probe_dir) / "xstar_calc_hmc_all_msolvelucy_initial_population_probe.csv"
    rows = _read_rows(path)
    resolved_call = _resolve_call_id(rows, call_id)
    selected = [
        row for row in rows
        if int(row["calc_hmc_all_call_id"]) == resolved_call
        and int(row["element_z"]) == int(element_z)
    ]
    if not selected:
        raise MSolveLucyInitialStateError(
            f"no initial-population rows for call={resolved_call}, element_z={element_z}"
        )

    dimensions = {int(row["compact_dimension"]) for row in selected}
    element_indices = {int(row["element_index"]) for row in selected}
    if len(dimensions) != 1:
        raise MSolveLucyInitialStateError(
            f"inconsistent compact dimensions in initial-population probe: {sorted(dimensions)}"
        )
    if len(element_indices) != 1:
        raise MSolveLucyInitialStateError(
            f"inconsistent element indices in initial-population probe: {sorted(element_indices)}"
        )
    dimension = dimensions.pop()
    if dimension <= 0:
        raise MSolveLucyInitialStateError(f"invalid compact dimension {dimension}")

    by_index: Dict[int, float] = {}
    for row in selected:
        index = int(row["compact_index"])
        value = parse_fortran_float(row["population"])
        if index in by_index:
            raise MSolveLucyInitialStateError(
                f"duplicate compact index {index} for call={resolved_call}, element_z={element_z}"
            )
        if index < 1 or index > dimension:
            raise MSolveLucyInitialStateError(
                f"compact index {index} outside 1..{dimension}"
            )
        if not np.isfinite(value) or value < 0.0:
            raise MSolveLucyInitialStateError(
                f"invalid population at compact index {index}: {value}"
            )
        by_index[index] = float(value)

    expected = set(range(1, dimension + 1))
    missing = sorted(expected - set(by_index))
    if missing:
        preview = missing[:12]
        raise MSolveLucyInitialStateError(
            f"initial-population probe misses {len(missing)} compact rows; first={preview}"
        )
    populations = np.asarray([by_index[index] for index in range(1, dimension + 1)], dtype=float)
    if float(np.sum(populations)) <= 0.0:
        raise MSolveLucyInitialStateError("captured initial population vector has non-positive sum")

    return MSolveLucyInitialPopulationReference(
        call_id=resolved_call,
        element_index=element_indices.pop(),
        element_z=int(element_z),
        compact_dimension=dimension,
        populations=populations,
        source_path=str(path),
    )


@dataclass
class MSolveLucyInitialPopulationParityResult:
    """Comparison of Python's solver seed with the same-call XSTAR input state."""

    ready: bool
    status: str
    call_id: Optional[int]
    element_z: int
    compact_dimension: Optional[int]
    n_rows: int
    n_outside_tolerance: int
    max_absolute_difference: Optional[float]
    max_relative_difference: Optional[float]
    rows: List[Dict[str, object]]
    element_results: List[Dict[str, object]] = field(default_factory=list)


def compare_msolvelucy_initial_population(
    python_populations: Sequence[float],
    reference: MSolveLucyInitialPopulationReference,
    *,
    rtol: float,
    atol: float,
) -> MSolveLucyInitialPopulationParityResult:
    """Compare a Python compact seed against the captured source input vector."""

    values = np.asarray(python_populations, dtype=float).reshape(-1)
    if values.size == reference.compact_dimension + 1:
        values = values[1:]
    if values.size != reference.compact_dimension:
        return MSolveLucyInitialPopulationParityResult(
            ready=False,
            status="failed_dimension_mismatch",
            call_id=reference.call_id,
            element_z=reference.element_z,
            compact_dimension=reference.compact_dimension,
            n_rows=0,
            n_outside_tolerance=reference.compact_dimension,
            max_absolute_difference=None,
            max_relative_difference=None,
            rows=[],
        )

    rows: List[Dict[str, object]] = []
    max_abs = 0.0
    max_rel = 0.0
    n_bad = 0
    for index, (python_value, xstar_value) in enumerate(
        zip(values, reference.populations), start=1
    ):
        absolute = abs(float(python_value) - float(xstar_value))
        scale = max(abs(float(xstar_value)), float(atol))
        relative = absolute / scale
        within = absolute <= float(atol) + float(rtol) * abs(float(xstar_value))
        max_abs = max(max_abs, absolute)
        max_rel = max(max_rel, relative)
        n_bad += int(not within)
        rows.append({
            "element_z": reference.element_z,
            "compact_index": index,
            "python_initial_population": float(python_value),
            "xstar_initial_population": float(xstar_value),
            "absolute_difference": absolute,
            "relative_difference": relative,
            "within_tolerance": within,
            "diagnostic_role": "same_call_xileve_to_compact_x_solver_seed",
        })

    ready = n_bad == 0
    return MSolveLucyInitialPopulationParityResult(
        ready=ready,
        status="ready" if ready else "failed",
        call_id=reference.call_id,
        element_z=reference.element_z,
        compact_dimension=reference.compact_dimension,
        n_rows=len(rows),
        n_outside_tolerance=n_bad,
        max_absolute_difference=max_abs,
        max_relative_difference=max_rel,
        rows=rows,
    )


def compare_msolvelucy_initial_populations(
    python_populations_by_element: Mapping[int, Sequence[float]],
    probe_dir: str | Path,
    *,
    element_zs: Sequence[int],
    call_id: Optional[int],
    rtol: float,
    atol: float,
) -> MSolveLucyInitialPopulationParityResult:
    """Compare all requested element solver seeds against one probe call.

    The returned row table is the concatenation of the element-local compact
    vectors.  ``element_results`` preserves independent H/He/O readiness so
    an oxygen-only success cannot mask a missing or failed H/He seed.
    """

    rows: List[Dict[str, object]] = []
    summaries: List[Dict[str, object]] = []
    total_dimension = 0
    total_outside = 0
    max_abs: Optional[float] = 0.0
    max_rel: Optional[float] = 0.0
    resolved_call: Optional[int] = call_id
    all_ready = True

    for element_z in sorted({int(z) for z in element_zs}):
        try:
            reference = load_msolvelucy_initial_population_reference(
                probe_dir, element_z=element_z, call_id=call_id
            )
        except MSolveLucyInitialStateError as exc:
            all_ready = False
            summaries.append({
                "element_z": element_z,
                "ready": False,
                "status": "failed_missing_or_invalid_reference",
                "compact_dimension": None,
                "n_rows": 0,
                "n_outside_tolerance": 0,
                "reason": str(exc),
            })
            continue
        resolved_call = reference.call_id
        total_dimension += reference.compact_dimension
        populations = python_populations_by_element.get(element_z)
        if populations is None:
            compared = MSolveLucyInitialPopulationParityResult(
                ready=False,
                status="failed_missing_python_element",
                call_id=reference.call_id,
                element_z=element_z,
                compact_dimension=reference.compact_dimension,
                n_rows=0,
                n_outside_tolerance=reference.compact_dimension,
                max_absolute_difference=None,
                max_relative_difference=None,
                rows=[],
            )
        else:
            compared = compare_msolvelucy_initial_population(
                populations, reference, rtol=rtol, atol=atol
            )
        rows.extend(compared.rows)
        total_outside += compared.n_outside_tolerance
        if compared.max_absolute_difference is not None:
            max_abs = max(float(max_abs or 0.0), compared.max_absolute_difference)
        if compared.max_relative_difference is not None:
            max_rel = max(float(max_rel or 0.0), compared.max_relative_difference)
        all_ready = all_ready and compared.ready
        summaries.append({
            "element_z": element_z,
            "ready": compared.ready,
            "status": compared.status,
            "compact_dimension": compared.compact_dimension,
            "n_rows": compared.n_rows,
            "n_outside_tolerance": compared.n_outside_tolerance,
            "max_absolute_difference": compared.max_absolute_difference,
            "max_relative_difference": compared.max_relative_difference,
            "reference_source_path": reference.source_path,
        })

    requested = sorted({int(z) for z in element_zs})
    present = {int(item["element_z"]) for item in summaries}
    all_ready = bool(all_ready and len(summaries) == len(requested) and present == set(requested))
    return MSolveLucyInitialPopulationParityResult(
        ready=all_ready,
        status="ready" if all_ready else "failed",
        call_id=resolved_call,
        element_z=0,
        compact_dimension=total_dimension if total_dimension else None,
        n_rows=len(rows),
        n_outside_tolerance=total_outside,
        max_absolute_difference=max_abs,
        max_relative_difference=max_rel,
        rows=rows,
        element_results=summaries,
    )


__all__ = [
    "MSolveLucyInitialStateError",
    "MSolveLucyInitialPopulationReference",
    "MSolveLucyInitialPopulationParityResult",
    "load_msolvelucy_initial_population_reference",
    "compare_msolvelucy_initial_population",
    "compare_msolvelucy_initial_populations",
]
