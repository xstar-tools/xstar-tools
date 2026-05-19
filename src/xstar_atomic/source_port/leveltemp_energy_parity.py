"""Exact mutable-``leveltemp`` parity for XSTAR rate-7 energy channels."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
import math

from .fortran_numbers import parse_fortran_float


@dataclass
class LeveltempEnergyParityResult:
    """Record-resolved exact workspace-energy comparison."""

    status: str
    ready: Optional[bool]
    type53_ready: Optional[bool]
    n_xstar_rows: int = 0
    n_python_rows: int = 0
    n_missing_python: int = 0
    n_missing_xstar: int = 0
    n_topology_mismatch: int = 0
    n_energy_outside_tolerance: int = 0
    n_type53_energy_outside_tolerance: int = 0
    rows: List[Dict[str, Any]] = field(default_factory=list)
    workspace_trace_rows: List[Dict[str, Any]] = field(default_factory=list)
    type53_trace_rows: List[Dict[str, Any]] = field(default_factory=list)


def _coerce_float(value: Any) -> float:
    """Return a parser-compatible float or NaN for missing diagnostics."""
    if value is None:
        return float("nan")
    if isinstance(value, str) and not value.strip():
        return float("nan")
    try:
        return parse_fortran_float(value)
    except (TypeError, ValueError):
        return float("nan")


def _float(row: Mapping[str, Any], name: str) -> float:
    return _coerce_float(row.get(name))


def _close(a: float, b: float, *, rtol: float, atol: float) -> bool:
    return math.isfinite(a) and math.isfinite(b) and abs(a - b) <= atol + rtol * abs(b)


def _python_rows(fixed_result: Any, element_z: int) -> Tuple[Dict[Tuple[int, int, int, int], Mapping[str, Any]], List[Dict[str, Any]]]:
    mapped: Dict[Tuple[int, int, int, int], Mapping[str, Any]] = {}
    trace: List[Dict[str, Any]] = []
    for element in getattr(fixed_result, "element_results", []):
        if int(getattr(element.request, "element_z", 0)) != int(element_z):
            continue
        assembly = element.equilibrium.assembly
        for write in getattr(assembly, "leveltemp_workspace_trace", ()):
            trace.append({
                "event_kind": "workspace_write",
                "element_z": int(element_z),
                **dict(write),
                "diagnostic_role": (
                    "levwkelement_or_second_pass_calc_rates_level_lte_write_order"
                ),
            })
        for row in assembly.record_results:
            try:
                data_type = int(row.get("data_type", 0))
                rate_type = int(row.get("rate_type", 0))
                record = int(row.get("record", 0))
                ion_stage = int(row.get("ion_stage", 0))
            except (TypeError, ValueError):
                continue
            if rate_type != 7 or data_type not in {49, 53, 99} or record <= 0:
                continue
            key = (record, data_type, rate_type, ion_stage)
            mapped[key] = row
            trace.append({
                "event_kind": "record_read",
                "element_z": int(element_z),
                "record": record,
                "data_type": data_type,
                "rate_type": rate_type,
                "ion_stage": ion_stage,
                "ion_index": row.get("ion_index"),
                "nlev": row.get("diag_nlev", row.get("nlev")),
                "idest1": row.get("idest1"),
                "idest2": row.get("idest2"),
                "leveltemp_e1_ev": row.get("leveltemp_idest1_energy_ev"),
                "leveltemp_e2_ev": row.get("leveltemp_idest2_energy_ev"),
                "leveltemp_e2_owner_ion_index": row.get("leveltemp_idest2_owner_ion_index"),
                "leveltemp_e2_owner_ion_stage": row.get("leveltemp_idest2_owner_ion_stage"),
                "leveltemp_e2_owner_nlev": row.get("leveltemp_idest2_owner_nlev"),
                "leveltemp_e2_owner_write_sequence": row.get("leveltemp_idest2_owner_write_sequence"),
                "leveltemp_e2_owner_phase": row.get("leveltemp_idest2_owner_phase"),
                "leveltemp_workspace_write_sequence": row.get("leveltemp_workspace_write_sequence"),
                "leveltemp_workspace_max_column": row.get("leveltemp_workspace_max_column"),
                "ans1": row.get("ans1"),
                "ans2": row.get("ans2"),
                "ans3": row.get("ans3"),
                "ans4": row.get("ans4"),
                "ans5": row.get("ans5"),
                "ans6": row.get("ans6"),
                "ucalc_status": row.get("status"),
            })
    return mapped, trace


def _build_type53_trace(
    comparison_rows: Sequence[Mapping[str, Any]],
    workspace_rows: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """Build one bounded source-order trace for a failing type-53 record."""

    type53 = [row for row in comparison_rows if int(row.get("data_type", 0)) == 53]
    if not type53:
        return []
    target = next((row for row in type53 if not bool(row.get("within_tolerance", False))), type53[0])
    record = int(target.get("record", 0))
    ion_stage = int(target.get("ion_stage", 0))
    record_read = next((
        row for row in workspace_rows
        if row.get("event_kind") == "record_read"
        and int(row.get("record", 0)) == record
        and int(row.get("ion_stage", 0)) == ion_stage
    ), None)
    write_limit = int((record_read or {}).get("leveltemp_workspace_write_sequence", 10**9))
    selected: List[Dict[str, Any]] = []
    for row in workspace_rows:
        if row.get("event_kind") == "workspace_write" and int(row.get("write_sequence", 0)) <= write_limit:
            selected.append({
                **dict(row),
                "target_record": record,
                "target_ion_stage": ion_stage,
                "trace_role": "calc_rates_level_lte_workspace_write",
            })
    if record_read is not None:
        selected.append({
            **dict(record_read),
            "target_record": record,
            "target_ion_stage": ion_stage,
            "trace_role": "ucalc_type53_exact_leveltemp_read_and_ans_channels",
        })
    selected.append({
        **dict(target),
        "event_kind": "xstar_python_comparison",
        "target_record": record,
        "target_ion_stage": ion_stage,
        "trace_role": "ans5_ans6_cj2_leveltemp_acceptance_comparison",
    })
    for step, row in enumerate(selected, start=1):
        row["trace_step"] = step
    return selected


def compare_leveltemp_energy_probe(
    fixed_result: Any,
    *,
    probe_rows: Sequence[Mapping[str, Any]],
    element_z: int = 8,
    rtol: float = 1.0e-10,
    atol: float = 1.0e-10,
) -> LeveltempEnergyParityResult:
    """Compare the exact source ``leveltemp%rlev(1,idest*)`` reads.

    The probe is intentionally independent from reconstructed physical parent
    energies.  Readiness requires a one-to-one record map, matching endpoints,
    and matching exact mutable-workspace energies for all captured type
    49/53/99 rate-7 records.
    """

    python, trace = _python_rows(fixed_result, element_z)
    selected = [row for row in probe_rows if int(row.get("element_z", 0)) == int(element_z)]
    if not selected:
        return LeveltempEnergyParityResult(
            status="not_comparable_missing_leveltemp_energy_probe",
            ready=None,
            type53_ready=None,
            n_python_rows=len(python),
            workspace_trace_rows=trace,
        )

    xstar: Dict[Tuple[int, int, int, int], Mapping[str, Any]] = {}
    for row in selected:
        key = (
            int(row["record"]), int(row["data_type"]),
            int(row["rate_type"]), int(row["ion_stage"]),
        )
        xstar[key] = row

    output: List[Dict[str, Any]] = []
    missing_python = missing_xstar = topology_bad = energy_bad = type53_bad = 0
    for key in sorted(set(python) | set(xstar)):
        py = python.get(key)
        xs = xstar.get(key)
        record, data_type, rate_type, ion_stage = key
        if py is None:
            missing_python += 1
            output.append({
                "element_z": element_z, "record": record, "data_type": data_type,
                "rate_type": rate_type, "ion_stage": ion_stage,
                "comparison_status": "missing_python_record",
                "within_tolerance": False,
            })
            if data_type == 53:
                type53_bad += 1
            continue
        if xs is None:
            missing_xstar += 1
            output.append({
                "element_z": element_z, "record": record, "data_type": data_type,
                "rate_type": rate_type, "ion_stage": ion_stage,
                "comparison_status": "missing_xstar_probe_record",
                "within_tolerance": False,
                "python_idest1": py.get("idest1"), "python_idest2": py.get("idest2"),
                "python_leveltemp_e1_ev": py.get("leveltemp_idest1_energy_ev"),
                "python_leveltemp_e2_ev": py.get("leveltemp_idest2_energy_ev"),
            })
            if data_type == 53:
                type53_bad += 1
            continue

        py_id1 = int(py.get("idest1", 0)); py_id2 = int(py.get("idest2", 0))
        xs_id1 = int(xs.get("idest1", 0)); xs_id2 = int(xs.get("idest2", 0))
        topology = py_id1 == xs_id1 and py_id2 == xs_id2
        if not topology:
            topology_bad += 1
        py_e1 = _coerce_float(py.get("leveltemp_idest1_energy_ev"))
        py_e2 = _coerce_float(py.get("leveltemp_idest2_energy_ev"))
        xs_e1 = _float(xs, "leveltemp_e1_ev")
        xs_e2 = _float(xs, "leveltemp_e2_ev")
        e1_ok = _close(py_e1, xs_e1, rtol=rtol, atol=atol)
        e2_ok = _close(py_e2, xs_e2, rtol=rtol, atol=atol)
        within = topology and e1_ok and e2_ok
        if not within:
            energy_bad += 1
            if data_type == 53:
                type53_bad += 1
        output.append({
            "element_z": element_z,
            "record": record,
            "data_type": data_type,
            "rate_type": rate_type,
            "ion_stage": ion_stage,
            "python_ion_index": py.get("ion_index"),
            "xstar_ion_index": int(xs.get("ion_index", 0)),
            "python_nlev": py.get("diag_nlev", py.get("nlev")),
            "xstar_nlev": int(xs.get("nlev", 0)),
            "python_idest1": py_id1,
            "xstar_idest1": xs_id1,
            "python_idest2": py_id2,
            "xstar_idest2": xs_id2,
            "endpoint_match": topology,
            "python_leveltemp_e1_ev": py_e1,
            "xstar_leveltemp_e1_ev": xs_e1,
            "leveltemp_e1_difference_ev": py_e1 - xs_e1,
            "leveltemp_e1_within_tolerance": e1_ok,
            "python_leveltemp_e2_ev": py_e2,
            "xstar_leveltemp_e2_ev": xs_e2,
            "leveltemp_e2_difference_ev": py_e2 - xs_e2,
            "leveltemp_e2_within_tolerance": e2_ok,
            "python_leveltemp_e2_owner_ion_index": py.get("leveltemp_idest2_owner_ion_index"),
            "python_leveltemp_e2_owner_ion_stage": py.get("leveltemp_idest2_owner_ion_stage"),
            "python_leveltemp_e2_owner_nlev": py.get("leveltemp_idest2_owner_nlev"),
            "python_leveltemp_e2_owner_write_sequence": py.get("leveltemp_idest2_owner_write_sequence"),
            "python_leveltemp_e2_owner_phase": py.get("leveltemp_idest2_owner_phase"),
            "python_ans5": py.get("ans5"),
            "xstar_ans5": _float(xs, "ans5"),
            "python_ans6": py.get("ans6"),
            "xstar_ans6": _float(xs, "ans6"),
            "comparison_status": "ready" if within else "leveltemp_energy_difference",
            "within_tolerance": within,
        })

    ready = not (missing_python or missing_xstar or topology_bad or energy_bad)
    type53_ready = type53_bad == 0 and any(int(row.get("data_type", 0)) == 53 for row in selected)
    return LeveltempEnergyParityResult(
        status="ready" if ready else "failed",
        ready=ready,
        type53_ready=type53_ready,
        n_xstar_rows=len(xstar),
        n_python_rows=len(python),
        n_missing_python=missing_python,
        n_missing_xstar=missing_xstar,
        n_topology_mismatch=topology_bad,
        n_energy_outside_tolerance=energy_bad,
        n_type53_energy_outside_tolerance=type53_bad,
        rows=output,
        workspace_trace_rows=trace,
        type53_trace_rows=_build_type53_trace(output, trace),
    )


__all__ = ["LeveltempEnergyParityResult", "compare_leveltemp_energy_probe"]
