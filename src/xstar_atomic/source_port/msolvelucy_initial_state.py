"""Same-call ``calc_hmc_element`` input population state.

XSTAR maps the current global level population array ``xilevg`` into the
compact element vector ``x`` immediately before ``msolvelucy``.  This vector
is an input state of ``calc_hmc_element``; it is not the LTE vector returned by
``levwkelement``.  The bounded probe and loader in this module preserve that
source distinction for fixed-state regression runs.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
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


__all__ = [
    "MSolveLucyInitialStateError",
    "MSolveLucyInitialPopulationReference",
    "MSolveLucyInitialPopulationParityResult",
    "load_msolvelucy_initial_population_reference",
    "compare_msolvelucy_initial_population",
]
