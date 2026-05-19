"""Parity checks for the bounded XSTAR ``calc_hmc_all`` probe."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence
import csv
import json

from .local_zone import FixedStateCalcHMCAllResult


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
    parity_ready: bool
    active_population_threshold: float
    population_weighted_attribution: List[Dict[str, Any]] = field(default_factory=list)
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
    values = [float(row[name]) for row in rows]
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


def compare_calc_hmc_all_pre_continuum_probe(
    result: FixedStateCalcHMCAllResult,
    probe_dir: str | Path,
    *,
    call_id: Optional[int] = None,
    rtol: float = 5.0e-3,
    atol: float = 1.0e-12,
    active_population_threshold: float = 1.0e-12,
) -> CalcHMCAllPreContinuumParityResult:
    """Compare Python first-pass and pre-``comp2`` products to XSTAR.

    Strict comparisons remain in the details table. The Milestone-4 level gate
    requires all LTE/gamma rows and active-population xilevg/alphag rows; tiny
    inactive populations and derived departure/record products are classified
    separately rather than silently discarded.
    """

    if rtol < 0.0 or atol < 0.0 or active_population_threshold < 0.0:
        raise CalcHMCAllParityError("rtol, atol, and active threshold must be nonnegative")
    root = Path(probe_dir)
    element_rows_all = _read_csv(root / "xstar_calc_hmc_element_pre_matrix_probe.csv")
    summary_rows_all = _read_csv(root / "xstar_calc_hmc_all_pre_continuum_summary_probe.csv")
    ion_rows_all = _read_csv(root / "xstar_calc_hmc_all_pre_continuum_ions_probe.csv")
    level_rows_all = _read_csv(root / "xstar_calc_hmc_all_pre_continuum_levels_probe.csv")
    element_array_path = root / "xstar_calc_hmc_all_pre_continuum_elements_probe.csv"
    element_array_rows_all = _read_csv_optional(element_array_path)
    all_probe_rows = (
        element_rows_all + summary_rows_all + ion_rows_all + level_rows_all
        + element_array_rows_all
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
        element_components = {"element_index", "element_htt", "element_cll", "element_htt2", "element_cll2"}
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

    attribution = _build_population_weighted_attribution(
        result=result,
        failed_level_rows=rows,
        level_by_index=level_by_index,
        level_index_by_key=level_index_by_key,
    )

    missing_python = pre_matrix_missing_python + ion_missing_python + level_missing_python + element_missing_python
    missing_xstar = pre_matrix_missing_xstar + ion_missing_xstar + level_missing_xstar + element_missing_xstar
    outside = sum(not row.within_tolerance for row in rows)
    blocking_outside = sum((not row.within_tolerance) and row.milestone_blocking for row in rows)
    max_abs = max((row.absolute_difference for row in rows), default=0.0)
    max_rel = max((row.relative_difference for row in rows), default=0.0)
    pre_matrix_components = {
        "istruc_fraction", "calc_ion_rates_pirt", "calc_ion_rates_rrrt",
        "ion_limit_mml", "ion_limit_mmu", "ion_limit_critf",
    }
    pre_matrix_ready = (
        pre_matrix_missing_python == 0 and pre_matrix_missing_xstar == 0
        and all(row.within_tolerance for row in rows if row.component in pre_matrix_components)
    )
    summary_gate = summary_ready is not False
    ready = bool(pre_matrix_ready and state_ready and global_arrays_ready and summary_gate)
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
        parity_ready=ready,
        active_population_threshold=float(active_population_threshold),
        population_weighted_attribution=attribution,
        diagnostics={
            "probe_dir": str(root),
            "rtol": float(rtol),
            "atol": float(atol),
            "active_population_threshold": float(active_population_threshold),
            "summary_scope_complete": summary_comparable,
            "deferred_summary_fields": deferred_summary_fields,
            "element_array_probe_present": bool(element_array_rows_all),
            "n_element_array_probe_rows": len(element_array_rows),
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
        "estimated_population_factor_difference_s_inv", "rate_difference_status",
        "diagnostic_role",
    )
    with attribution_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=attribution_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(result.population_weighted_attribution)

    payload = {
        "port_version": "v0.4.27",
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
        "parity_ready": result.parity_ready,
        "active_population_threshold": result.active_population_threshold,
        "n_population_weighted_attribution_rows": len(result.population_weighted_attribution),
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
        f"- Overall parity ready: `{result.parity_ready}`\n"
        f"- Population-weighted attribution rows: `{len(result.population_weighted_attribution)}`\n"
    )
    return {
        "details_csv": str(details),
        "population_weighted_attribution_csv": str(attribution_path),
        "json": str(json_path),
        "markdown": str(md),
    }


__all__ = [
    "CalcHMCAllParityError",
    "CalcHMCAllProbeCritfReference",
    "CalcHMCAllParityRow",
    "CalcHMCAllPreContinuumParityResult",
    "load_calc_hmc_all_probe_critf",
    "compare_calc_hmc_all_pre_continuum_probe",
    "write_calc_hmc_all_pre_continuum_parity_products",
]
