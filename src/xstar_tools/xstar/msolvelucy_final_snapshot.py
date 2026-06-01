"""Same-iteration final ``msolvelucy`` matrix/population parity.

The XSTAR probe consumed here is diagnostic only.  It captures the effective
``ajisb/cjisb`` operator, the returned population vector ``x``, and ``xo``
(the vector at the start of the final Lucy outer iteration) in one call made
immediately after the outer iteration loop.  Captured values are never used by
the production Python solver.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from .fortran_numbers import parse_fortran_float
from .local_zone import FixedStateCalcHMCAllResult


def _int(row: Mapping[str, Any], name: str, default: int = 0) -> int:
    value = row.get(name)
    if value in (None, ""):
        return int(default)
    return int(value)


def _float(row: Mapping[str, Any], name: str, default: float = 0.0) -> float:
    value = row.get(name)
    if value in (None, ""):
        return float(default)
    if isinstance(value, (int, float, np.number)):
        return float(value)
    return parse_fortran_float(str(value))


def _within(py: float, xs: float, rtol: float, atol: float) -> bool:
    return abs(py - xs) <= atol + rtol * abs(xs)


@dataclass
class MSolveLucyFinalSnapshotParityResult:
    status: str
    ready: Optional[bool]
    probe_pair_present: bool
    same_iteration_ready: Optional[bool]
    iteration_tuple_ready: Optional[bool]
    matrix_dimension_ready: Optional[bool]
    matrix_population_columns_ready: Optional[bool]
    topology_ready: Optional[bool]
    coefficient_ready: Optional[bool]
    active_final_population_ready: Optional[bool]
    active_outer_start_population_ready: Optional[bool]
    source_xtot_ready: Optional[bool]
    final_vector_xtot_ready: Optional[bool]
    n_matrix_rows: int
    n_population_rows: int
    n_topology_mismatches: int
    n_coefficient_rows_outside_tolerance: int
    n_active_final_population_rows_outside_tolerance: int
    n_active_outer_start_rows_outside_tolerance: int
    n_source_xtot_rows_outside_tolerance: int
    term_rows: List[Dict[str, Any]] = field(default_factory=list)
    population_rows: List[Dict[str, Any]] = field(default_factory=list)
    ion_total_rows: List[Dict[str, Any]] = field(default_factory=list)
    oxygen_reassessment_rows: List[Dict[str, Any]] = field(default_factory=list)
    diagnostics: Dict[str, Any] = field(default_factory=dict)


def _basis_row_metadata(basis: Any, compact: int) -> Dict[str, Any]:
    row = basis.row(compact)
    roles = list(getattr(row, "roles", ()) or ())
    stages = sorted({int(r.get("ion_stage", 0)) for r in roles if int(r.get("ion_stage", 0)) > 0})
    levels = sorted({int(r.get("local_level", r.get("level", 0))) for r in roles
                     if int(r.get("local_level", r.get("level", 0))) > 0})
    role_names = [str(r.get("role", "")) for r in roles if str(r.get("role", ""))]
    return {
        "physical_ion_stages": ";".join(map(str, stages)),
        "physical_local_levels": ";".join(map(str, levels)),
        "basis_roles": ";".join(role_names),
        "representative_ion_stage": max(stages) if stages else 0,
        "representative_local_level": levels[0] if len(levels) == 1 else 0,
        "python_superlevel": int(row.superlevel),
        "python_ion_counter": int(row.ion_counter),
    }


def compare_msolvelucy_final_snapshot(
    result: FixedStateCalcHMCAllResult,
    *,
    final_matrix_rows: Sequence[Mapping[str, Any]],
    final_population_rows: Sequence[Mapping[str, Any]],
    rtol: float = 5.0e-3,
    atol: float = 1.0e-12,
    active_population_threshold: float = 1.0e-12,
) -> MSolveLucyFinalSnapshotParityResult:
    """Compare a synchronized final XSTAR solver snapshot with Python.

    The milestone gate uses exact topology, active final/outer-start
    populations, and source-order ``xtot`` totals.  Strict coefficient and
    final-vector-total parity remain independently visible.
    """

    if rtol < 0.0 or atol < 0.0 or active_population_threshold < 0.0:
        raise ValueError("rtol, atol, and active_population_threshold must be nonnegative")

    pair_present = bool(final_matrix_rows and final_population_rows)
    if not final_matrix_rows and not final_population_rows:
        return MSolveLucyFinalSnapshotParityResult(
            status="not_comparable_missing_final_snapshot_probe",
            ready=None,
            probe_pair_present=False,
            same_iteration_ready=None,
            iteration_tuple_ready=None,
            matrix_dimension_ready=None,
            matrix_population_columns_ready=None,
            topology_ready=None,
            coefficient_ready=None,
            active_final_population_ready=None,
            active_outer_start_population_ready=None,
            source_xtot_ready=None,
            final_vector_xtot_ready=None,
            n_matrix_rows=0,
            n_population_rows=0,
            n_topology_mismatches=0,
            n_coefficient_rows_outside_tolerance=0,
            n_active_final_population_rows_outside_tolerance=0,
            n_active_outer_start_rows_outside_tolerance=0,
            n_source_xtot_rows_outside_tolerance=0,
            diagnostics={"diagnostic_only": True, "probe_values_enter_solver": False},
        )
    if not pair_present:
        return MSolveLucyFinalSnapshotParityResult(
            status="failed_incomplete_final_snapshot_probe_pair",
            ready=False,
            probe_pair_present=False,
            same_iteration_ready=False,
            iteration_tuple_ready=False,
            matrix_dimension_ready=False,
            matrix_population_columns_ready=False,
            topology_ready=False,
            coefficient_ready=False,
            active_final_population_ready=False,
            active_outer_start_population_ready=False,
            source_xtot_ready=False,
            final_vector_xtot_ready=False,
            n_matrix_rows=len(final_matrix_rows),
            n_population_rows=len(final_population_rows),
            n_topology_mismatches=0,
            n_coefficient_rows_outside_tolerance=0,
            n_active_final_population_rows_outside_tolerance=0,
            n_active_outer_start_rows_outside_tolerance=0,
            n_source_xtot_rows_outside_tolerance=0,
            diagnostics={"diagnostic_only": True, "probe_values_enter_solver": False},
        )

    matrix_by_z: Dict[int, List[Mapping[str, Any]]] = {}
    pop_by_z: Dict[int, List[Mapping[str, Any]]] = {}
    for row in final_matrix_rows:
        matrix_by_z.setdefault(_int(row, "element_z"), []).append(row)
    for row in final_population_rows:
        pop_by_z.setdefault(_int(row, "element_z"), []).append(row)

    iteration_tuple_consistent = True
    matrix_dimensions_match = True
    matrix_population_columns_match = True
    topology = True
    coefficients = True
    active_final = True
    active_outer = True
    source_xtot = True
    final_xtot = True
    n_top = n_coef_bad = n_final_bad = n_outer_bad = n_source_xtot_bad = 0
    term_out: List[Dict[str, Any]] = []
    pop_out: List[Dict[str, Any]] = []
    ion_out: List[Dict[str, Any]] = []
    oxygen_out: List[Dict[str, Any]] = []
    compared_elements = 0
    unmatched_elements: List[int] = []

    metadata_fields = (
        "outer_iteration", "fixed_iteration", "global_fixed_iteration",
        "compact_dimension", "final_outer_difference", "final_fixed_difference",
    )

    for element in getattr(result, "element_results", ()):
        equilibrium = getattr(element, "equilibrium", None)
        solve = getattr(equilibrium, "solve", None)
        assembly = getattr(equilibrium, "assembly", None)
        if solve is None or assembly is None:
            continue
        z = int(element.request.element_z)
        mrows = matrix_by_z.get(z, [])
        prows = pop_by_z.get(z, [])
        if not mrows or not prows:
            unmatched_elements.append(z)
            iteration_tuple_consistent = False
            matrix_dimensions_match = False
            matrix_population_columns_match = False
            topology = active_final = active_outer = source_xtot = False
            continue
        compared_elements += 1
        basis = assembly.basis
        n = int(basis.n_rows)

        # Snapshot synchronization is an internal XSTAR property.  It does
        # not require Python and XSTAR to converge in the same number of
        # iterations.  Require one XSTAR iteration tuple shared by both files.
        def _iteration_tuple(row: Mapping[str, Any]) -> Tuple[Any, ...]:
            return (
                _int(row, "outer_iteration"),
                _int(row, "fixed_iteration"),
                _int(row, "global_fixed_iteration"),
                _float(row, "final_outer_difference"),
                _float(row, "final_fixed_difference"),
            )

        matrix_iteration_tuples = {_iteration_tuple(row) for row in mrows}
        population_iteration_tuples = {_iteration_tuple(row) for row in prows}
        element_iteration_tuple_ready = bool(
            len(matrix_iteration_tuples) == 1
            and len(population_iteration_tuples) == 1
            and matrix_iteration_tuples == population_iteration_tuples
        )
        iteration_tuple_consistent &= element_iteration_tuple_ready

        matrix_dimensions = {_int(row, "compact_dimension") for row in mrows}
        population_dimensions = {_int(row, "compact_dimension") for row in prows}
        element_dimension_ready = bool(
            matrix_dimensions == {n}
            and population_dimensions == {n}
            and len(prows) == n
        )
        matrix_dimensions_match &= element_dimension_ready

        pmap = {_int(row, "compact_index"): row for row in prows}
        if set(pmap) != set(range(1, n + 1)):
            topology = False
            n_top += len(set(range(1, n + 1)) ^ set(pmap))

        xs_final = np.zeros(n, dtype=float)
        xs_outer = np.zeros(n, dtype=float)
        xs_nion = np.zeros(n, dtype=int)
        for compact in range(1, n + 1):
            row = pmap.get(compact)
            if row is None:
                continue
            xs_final[compact - 1] = _float(row, "population")
            xs_outer[compact - 1] = _float(row, "final_outer_start_population")
            xs_nion[compact - 1] = _int(row, "ion_counter")
            meta = _basis_row_metadata(basis, compact)
            py_final = float(solve.populations[compact - 1])
            py_outer = float(solve.final_outer_start_populations[compact - 1])
            final_ok = _within(py_final, xs_final[compact - 1], rtol, atol)
            outer_ok = _within(py_outer, xs_outer[compact - 1], rtol, atol)
            active = max(abs(py_final), abs(xs_final[compact - 1]), abs(py_outer), abs(xs_outer[compact - 1])) >= active_population_threshold
            if active and not final_ok:
                n_final_bad += 1
                active_final = False
            if active and not outer_ok:
                n_outer_bad += 1
                active_outer = False
            superlevel_match = int(meta["python_superlevel"]) == _int(row, "superlevel")
            ion_counter_match = int(meta["python_ion_counter"]) == _int(row, "ion_counter")
            topology &= superlevel_match and ion_counter_match
            if not (superlevel_match and ion_counter_match):
                n_top += 1
            outrow = {
                "element_z": z,
                "compact_index": compact,
                **meta,
                "xstar_superlevel": _int(row, "superlevel"),
                "xstar_ion_counter": _int(row, "ion_counter"),
                "superlevel_match": superlevel_match,
                "ion_counter_match": ion_counter_match,
                "active_population": active,
                "python_final_population": py_final,
                "xstar_final_population": xs_final[compact - 1],
                "final_population_difference": py_final - xs_final[compact - 1],
                "final_population_relative_difference": abs(py_final - xs_final[compact - 1]) / max(abs(xs_final[compact - 1]), 1.0e-300),
                "final_population_within_tolerance": final_ok,
                "python_final_outer_start_population": py_outer,
                "xstar_final_outer_start_population": xs_outer[compact - 1],
                "outer_start_population_difference": py_outer - xs_outer[compact - 1],
                "outer_start_population_relative_difference": abs(py_outer - xs_outer[compact - 1]) / max(abs(xs_outer[compact - 1]), 1.0e-300),
                "outer_start_population_within_tolerance": outer_ok,
                "same_iteration_metadata_ready": bool(
                    element_iteration_tuple_ready and element_dimension_ready
                ),
                "iteration_tuple_ready": element_iteration_tuple_ready,
                "matrix_dimension_ready": element_dimension_ready,
            }
            pop_out.append(outrow)
            stage = int(meta["representative_ion_stage"])
            if z == 8 and 3 <= stage <= 5 and active and (not final_ok or not outer_ok):
                oxygen_out.append({
                    **outrow,
                    "reassessment_kind": "active_compact_population",
                    "classification": (
                        "final_and_outer_start_population_difference" if not final_ok and not outer_ok
                        else "final_population_difference" if not final_ok
                        else "final_outer_start_population_difference"
                    ),
                    "milestone_blocking": True,
                })

        # Compare exact sparse terms and also verify that matrix-row population
        # columns are synchronized with the population table.
        pymap = {int(term.term_index): term for term in assembly.terms}
        xsmap = {_int(row, "term_index"): row for row in mrows}
        for index in sorted(set(pymap) | set(xsmap)):
            py = pymap.get(index)
            xs = xsmap.get(index)
            if py is None or xs is None:
                topology = False
                n_top += 1
                term_out.append({
                    "element_z": z, "term_index": index,
                    "match_status": "missing_python" if py is None else "missing_xstar",
                    "topology_match": False, "coefficient_within_tolerance": False,
                })
                continue
            top_ok = (
                int(py.record) == _int(xs, "source_record")
                and int(py.row) == _int(xs, "row_compact")
                and int(py.column) == _int(xs, "column_compact")
                and int(py.source_row_unclamped) == _int(xs, "row_raw")
                and int(py.source_column_unclamped) == _int(xs, "column_raw")
            )
            if not top_ok:
                topology = False
                n_top += 1
            fields = {
                "aj1": (float(py.aj1), _float(xs, "aj1")),
                "aj2": (float(py.aj2), _float(xs, "aj2")),
                "cj": (float(py.cj), _float(xs, "cj")),
                "cj2": (float(py.cj2), _float(xs, "cj2")),
            }
            coef_ok = all(_within(a, b, rtol, atol) for a, b in fields.values())
            if not coef_ok:
                coefficients = False
                n_coef_bad += 1
            rowc = min(n, max(1, _int(xs, "row_compact")))
            colc = min(n, max(1, _int(xs, "column_compact")))
            matrix_pop_ok = (
                _within(_float(xs, "row_population"), xs_final[rowc - 1], 0.0, max(atol, 1.0e-30))
                and _within(_float(xs, "column_population"), xs_final[colc - 1], 0.0, max(atol, 1.0e-30))
                and _within(_float(xs, "row_outer_start_population"), xs_outer[rowc - 1], 0.0, max(atol, 1.0e-30))
                and _within(_float(xs, "column_outer_start_population"), xs_outer[colc - 1], 0.0, max(atol, 1.0e-30))
            )
            matrix_population_columns_match &= matrix_pop_ok
            term_out.append({
                "element_z": z,
                "term_index": index,
                "record": int(py.record),
                "data_type": int(py.data_type),
                "rate_type": int(py.rate_type),
                "role": str(py.role),
                "python_row_raw": int(py.source_row_unclamped),
                "xstar_row_raw": _int(xs, "row_raw"),
                "python_column_raw": int(py.source_column_unclamped),
                "xstar_column_raw": _int(xs, "column_raw"),
                "python_row_compact": int(py.row),
                "xstar_row_compact": _int(xs, "row_compact"),
                "python_column_compact": int(py.column),
                "xstar_column_compact": _int(xs, "column_compact"),
                "topology_match": top_ok,
                "python_aj1": fields["aj1"][0], "xstar_aj1": fields["aj1"][1],
                "python_aj2": fields["aj2"][0], "xstar_aj2": fields["aj2"][1],
                "python_cj": fields["cj"][0], "xstar_cj": fields["cj"][1],
                "python_cj2": fields["cj2"][0], "xstar_cj2": fields["cj2"][1],
                "aj1_difference": fields["aj1"][0] - fields["aj1"][1],
                "aj2_difference": fields["aj2"][0] - fields["aj2"][1],
                "cj_difference": fields["cj"][0] - fields["cj"][1],
                "cj2_difference": fields["cj2"][0] - fields["cj2"][1],
                "coefficient_within_tolerance": coef_ok,
                "matrix_population_columns_same_iteration": matrix_pop_ok,
            })

        # Source xtot is accumulated from xo and excludes the final compact
        # row.  Compare both that source product and the final-vector diagnostic.
        nions = int(basis.n_ions)
        xs_source = np.zeros(nions, dtype=float)
        xs_final_totals = np.zeros(nions, dtype=float)
        for idx in range(max(0, n - 1)):
            slot = int(xs_nion[idx]) - 1
            if 0 <= slot < nions:
                xs_source[slot] += xs_outer[idx]
                xs_final_totals[slot] += xs_final[idx]
        for slot in range(nions):
            stage = int(
                getattr(basis, "ion_stage_by_counter", {}).get(
                    slot + 1, int(basis.min_ion_stage) + slot
                )
            )
            py_source = float(solve.ion_population_totals[slot])
            py_final_total = float(solve.ion_population_totals_final_vector[slot])
            source_ok = _within(py_source, xs_source[slot], rtol, atol)
            final_total_ok = _within(py_final_total, xs_final_totals[slot], rtol, atol)
            if not source_ok:
                source_xtot = False
                n_source_xtot_bad += 1
            if not final_total_ok:
                final_xtot = False
            ionrow = {
                "element_z": z,
                "ion_counter": slot + 1,
                "ion_stage": stage,
                "python_source_xtot": py_source,
                "xstar_source_xtot": float(xs_source[slot]),
                "source_xtot_difference": py_source - float(xs_source[slot]),
                "source_xtot_within_tolerance": source_ok,
                "python_final_vector_xtot": py_final_total,
                "xstar_final_vector_xtot": float(xs_final_totals[slot]),
                "final_vector_xtot_difference": py_final_total - float(xs_final_totals[slot]),
                "final_vector_xtot_within_tolerance": final_total_ok,
                "source_semantics": "sum(final_outer_start_population), excluding final compact row",
            }
            ion_out.append(ionrow)
            if z == 8 and stage in {3, 4} and not source_ok:
                oxygen_out.append({
                    **ionrow,
                    "reassessment_kind": "source_ion_total",
                    "classification": (
                        "source_xtot_iteration_semantics_difference"
                        if final_total_ok else "population_or_ion_aggregation_difference"
                    ),
                    "milestone_blocking": True,
                })

    if unmatched_elements:
        source_xtot = active_final = active_outer = topology = False
        iteration_tuple_consistent = False
        matrix_dimensions_match = False
        matrix_population_columns_match = False
    topology_ready = bool(topology and compared_elements > 0)
    coefficient_ready = bool(topology_ready and coefficients)
    iteration_tuple_ready = bool(iteration_tuple_consistent and compared_elements > 0)
    matrix_dimension_ready = bool(matrix_dimensions_match and compared_elements > 0)
    matrix_population_columns_ready = bool(
        matrix_population_columns_match and compared_elements > 0
    )
    # Public snapshot readiness is limited to synchronization of the XSTAR
    # pair.  Physical Python/XSTAR topology, population, and xtot parity remain
    # independent gates in the oxygen acceptance workflow.
    same_iteration_ready = bool(
        iteration_tuple_ready
        and matrix_dimension_ready
        and matrix_population_columns_ready
    )
    final_ready = bool(active_final and compared_elements > 0)
    outer_ready = bool(active_outer and compared_elements > 0)
    source_ready = bool(source_xtot and compared_elements > 0)
    final_xtot_ready = bool(final_xtot and compared_elements > 0)
    ready = bool(pair_present and same_iteration_ready)
    status = "ready" if ready else "failed"
    return MSolveLucyFinalSnapshotParityResult(
        status=status,
        ready=ready,
        probe_pair_present=pair_present,
        same_iteration_ready=same_iteration_ready,
        iteration_tuple_ready=iteration_tuple_ready,
        matrix_dimension_ready=matrix_dimension_ready,
        matrix_population_columns_ready=matrix_population_columns_ready,
        topology_ready=topology_ready,
        coefficient_ready=coefficient_ready,
        active_final_population_ready=final_ready,
        active_outer_start_population_ready=outer_ready,
        source_xtot_ready=source_ready,
        final_vector_xtot_ready=final_xtot_ready,
        n_matrix_rows=len(final_matrix_rows),
        n_population_rows=len(final_population_rows),
        n_topology_mismatches=n_top,
        n_coefficient_rows_outside_tolerance=n_coef_bad,
        n_active_final_population_rows_outside_tolerance=n_final_bad,
        n_active_outer_start_rows_outside_tolerance=n_outer_bad,
        n_source_xtot_rows_outside_tolerance=n_source_xtot_bad,
        term_rows=term_out,
        population_rows=pop_out,
        ion_total_rows=ion_out,
        oxygen_reassessment_rows=oxygen_out,
        diagnostics={
            "rtol": float(rtol),
            "atol": float(atol),
            "active_population_threshold": float(active_population_threshold),
            "n_compared_elements": compared_elements,
            "unmatched_element_z": unmatched_elements,
            "diagnostic_only": True,
            "probe_values_enter_solver": False,
            "source_xtot_vector": "xo at start of final Lucy outer iteration",
            "source_xtot_excludes_final_compact_row": True,
            "snapshot_gate_requirements": [
                "one_consistent_xstar_iteration_tuple_across_both_files",
                "matching_matrix_dimensions",
                "matrix_population_columns_match_population_table",
            ],
            "iteration_tuple_ready": iteration_tuple_ready,
            "matrix_dimension_ready": matrix_dimension_ready,
            "matrix_population_columns_ready": matrix_population_columns_ready,
            "python_iteration_count_enters_snapshot_gate": False,
        },
    )


__all__ = [
    "MSolveLucyFinalSnapshotParityResult",
    "compare_msolvelucy_final_snapshot",
]
