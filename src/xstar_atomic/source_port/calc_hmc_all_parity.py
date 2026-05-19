"""Parity checks for the bounded XSTAR ``calc_hmc_all`` probe."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
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


@dataclass
class CalcHMCAllPreContinuumParityResult:
    call_id: int
    rows: List[CalcHMCAllParityRow]
    n_missing_python_keys: int
    n_missing_xstar_keys: int
    max_absolute_difference: float
    max_relative_difference: float
    n_outside_tolerance: int
    pre_matrix_ready: bool
    pre_continuum_state_ready: bool
    pre_continuum_summary_ready: Optional[bool]
    pre_continuum_summary_status: str
    global_ion_ready: bool
    global_level_ready: bool
    global_arrays_ready: bool
    parity_ready: bool
    diagnostics: Dict[str, Any] = field(default_factory=dict)


def _read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        raise CalcHMCAllParityError(f"missing probe file: {path}")
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
) -> CalcHMCAllParityRow:
    diff = abs(float(python) - float(xstar))
    scale = max(abs(float(python)), abs(float(xstar)), 1.0e-300)
    rel = diff / scale
    ok = diff <= float(atol) + float(rtol) * abs(float(xstar))
    return CalcHMCAllParityRow(
        component, key, float(python), float(xstar), diff, rel, bool(ok)
    )


def _nonzero(values: Sequence[float | int]) -> bool:
    return any(float(value) != 0.0 for value in values)


def compare_calc_hmc_all_pre_continuum_probe(
    result: FixedStateCalcHMCAllResult,
    probe_dir: str | Path,
    *,
    call_id: Optional[int] = None,
    rtol: float = 5.0e-3,
    atol: float = 1.0e-12,
) -> CalcHMCAllPreContinuumParityResult:
    """Compare Python first-pass and pre-``comp2`` products to XSTAR.

    The all-element totals are compared only when the Python request covers the
    complete element/abundance scope.  Element-local ion and level arrays are
    always compared when their global XSTAR indices are available.
    """

    if rtol < 0.0 or atol < 0.0:
        raise CalcHMCAllParityError("rtol and atol must be nonnegative")
    root = Path(probe_dir)
    element_rows_all = _read_csv(root / "xstar_calc_hmc_element_pre_matrix_probe.csv")
    summary_rows_all = _read_csv(root / "xstar_calc_hmc_all_pre_continuum_summary_probe.csv")
    ion_rows_all = _read_csv(root / "xstar_calc_hmc_all_pre_continuum_ions_probe.csv")
    level_rows_all = _read_csv(root / "xstar_calc_hmc_all_pre_continuum_levels_probe.csv")
    selected_call = _resolve_call_id(
        element_rows_all + summary_rows_all + ion_rows_all + level_rows_all,
        call_id,
    )
    element_rows = [r for r in element_rows_all if int(r["calc_hmc_all_call_id"]) == selected_call]
    summary_rows = [r for r in summary_rows_all if int(r["calc_hmc_all_call_id"]) == selected_call]
    ion_rows = [r for r in ion_rows_all if int(r["calc_hmc_all_call_id"]) == selected_call]
    level_rows = [r for r in level_rows_all if int(r["calc_hmc_all_call_id"]) == selected_call]
    if len(summary_rows) != 1:
        raise CalcHMCAllParityError(
            f"expected one pre-continuum summary for call {selected_call}, got {len(summary_rows)}"
        )

    rows: List[CalcHMCAllParityRow] = []
    pre_matrix_missing_python = 0
    pre_matrix_missing_xstar = 0
    ion_missing_python = 0
    ion_missing_xstar = 0
    level_missing_python = 0
    level_missing_xstar = 0

    # First-pass calc_ion_rates -> istruc products.
    xstar_keys = {(int(r["element_z"]), int(r["ion_stage"])) for r in element_rows}
    probe_elements = {z for z, _ in xstar_keys}
    python_keys = {
        key for key in result.preliminary_ion_fractions if key[0] in probe_elements
    }
    pre_matrix_missing_python += len(xstar_keys - python_keys)
    pre_matrix_missing_xstar += len(python_keys - xstar_keys)

    for record in element_rows:
        z = int(record["element_z"])
        stage = int(record["ion_stage"])
        key = (z, stage)
        if key not in result.preliminary_ion_fractions:
            continue
        rows.append(_metric(
            "istruc_fraction", f"Z={z},stage={stage}",
            result.preliminary_ion_fractions[key], float(record["xitp"]),
            rtol=rtol, atol=atol,
        ))
        if stage <= z:
            rows.append(_metric(
                "calc_ion_rates_pirt", f"Z={z},stage={stage}",
                result.pirt.get(key, 0.0), float(record["pirt"]),
                rtol=rtol, atol=atol,
            ))
            rows.append(_metric(
                "calc_ion_rates_rrrt", f"Z={z},stage={stage}",
                result.rrrt.get(key, 0.0), float(record["rrrt"]),
                rtol=rtol, atol=atol,
            ))

    # mml, mmu, and critf are element-level values, not ion-level values.
    for z in sorted(probe_elements):
        zrows = [row for row in element_rows if int(row["element_z"]) == z]
        x_mml = _unique_int(zrows, "mml", context=f"call {selected_call}, Z={z}")
        x_mmu = _unique_int(zrows, "mmu", context=f"call {selected_call}, Z={z}")
        x_critf = _unique_float(zrows, "critf", context=f"call {selected_call}, Z={z}")
        rows.append(_metric(
            "ion_limit_mml", f"Z={z}", float(result.mml.get(z, 0)), float(x_mml),
            rtol=0.0, atol=0.0,
        ))
        rows.append(_metric(
            "ion_limit_mmu", f"Z={z}", float(result.mmu.get(z, 0)), float(x_mmu),
            rtol=0.0, atol=0.0,
        ))
        python_critf = next(
            (float(item.request.critf) for item in result.element_results if int(item.request.element_z) == z),
            0.0,
        )
        rows.append(_metric(
            "ion_limit_critf", f"Z={z}", python_critf, x_critf,
            rtol=0.0, atol=0.0,
        ))

    # The thermodynamic state is scope independent.
    summary = summary_rows[0]
    for name, python_value, xstar_value in (
        ("temperature_k", result.temperature_k, float(summary["temperature_k"])),
        ("xee", result.electron_fraction_xee, float(summary["xee"])),
        ("xpx", result.hydrogen_density_cm3, float(summary["xpx"])),
    ):
        rows.append(_metric(
            "pre_continuum_state", name, python_value, xstar_value,
            rtol=rtol, atol=atol,
        ))

    state_ready = all(
        row.within_tolerance for row in rows if row.component == "pre_continuum_state"
    )

    # All-element sums are meaningful only for a complete element/abundance scope.
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
                rtol=rtol, atol=atol,
            ))
        summary_ready: Optional[bool] = all(
            row.within_tolerance for row in rows
            if row.component == "pre_continuum_summary"
        )
        summary_status = "ready" if summary_ready else "failed"
    else:
        summary_ready = None
        summary_status = "not_comparable_subset_scope"
        deferred_summary_fields = [
            "httot", "cltot", "httot2", "cltot2", "enelec", "elcter"
        ]

    # Global ion arrays. The XSTAR probe uses true global ion indices for
    # xiin/rrrt/pirt/stotg/atotg/xtotg, but htt/cll arrays are indexed by Z.
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
                component,
                f"global_ion={global_index},Z={key[0]},stage={key[1]}",
                float(values.get(key, 0.0)), float(record[field_name]),
                rtol=rtol, atol=atol,
            ))

    # Per-element heating/cooling arrays occupy indices 1..nl in the same
    # probe record even though the CSV column retains the legacy index name.
    for z in sorted(probe_elements):
        record = ion_by_index.get(z)
        if record is None:
            if _nonzero((
                result.htt.get(z, 0.0), result.cll.get(z, 0.0),
                result.htt2.get(z, 0.0), result.cll2.get(z, 0.0),
            )):
                ion_missing_xstar += 1
            continue
        for component, values, field_name in (
            ("element_htt", result.htt, "htt"),
            ("element_cll", result.cll, "cll"),
            ("element_htt2", result.htt2, "htt2"),
            ("element_cll2", result.cll2, "cll2"),
        ):
            rows.append(_metric(
                component, f"Z={z}", values.get(z, 0.0), float(record[field_name]),
                rtol=rtol, atol=atol,
            ))

    ion_metric_components = {
        component for component, _, _ in ion_components
    } | {"element_htt", "element_cll", "element_htt2", "element_cll2"}
    global_ion_ready = (
        ion_missing_python == 0
        and ion_missing_xstar == 0
        and all(row.within_tolerance for row in rows if row.component in ion_metric_components)
    )

    # Global level arrays.
    level_by_index = {int(row["global_level_index"]): row for row in level_rows}
    level_index_by_key = dict(getattr(result, "global_level_index_by_key", {}))
    level_components = (
        ("global_level_xilevg", result.xilevg, "xilevg", False),
        ("global_level_rnisg", result.rnisg, "rnisg", False),
        ("global_level_bilevg", result.bilevg, "bilevg", False),
        ("global_level_gammag", result.gammag, "gammag", False),
        ("global_level_alphag", result.alphag, "alphag", False),
        ("global_level_igammamax", result.igammamaxg, "igammamax_record", True),
        ("global_level_ialphamax", result.ialphamaxg, "ialphamax_record", True),
    )
    compared_level_indices = set()
    selected_level_keys = set()
    for _, values, _, _ in level_components:
        selected_level_keys.update(values)
    for key in sorted(selected_level_keys):
        if key[0] not in probe_elements:
            continue
        global_index = level_index_by_key.get(key)
        if global_index is None:
            python_values = [values.get(key, 0) for _, values, _, _ in level_components]
            if _nonzero(python_values):
                level_missing_xstar += 1
            continue
        record = level_by_index.get(int(global_index))
        python_values = [values.get(key, 0) for _, values, _, _ in level_components]
        if record is None:
            if _nonzero(python_values):
                level_missing_xstar += 1
            continue
        compared_level_indices.add(int(global_index))
        for component, values, field_name, exact in level_components:
            rows.append(_metric(
                component,
                f"global_level={global_index},Z={key[0]},stage={key[1]},level={key[2]}",
                float(values.get(key, 0)), float(record[field_name]),
                rtol=0.0 if exact else rtol,
                atol=0.0 if exact else atol,
            ))

    level_metric_components = {component for component, _, _, _ in level_components}
    global_level_ready = (
        level_missing_python == 0
        and level_missing_xstar == 0
        and all(row.within_tolerance for row in rows if row.component in level_metric_components)
    )
    global_arrays_ready = bool(global_ion_ready and global_level_ready)

    missing_python = pre_matrix_missing_python + ion_missing_python + level_missing_python
    missing_xstar = pre_matrix_missing_xstar + ion_missing_xstar + level_missing_xstar
    outside = sum(not row.within_tolerance for row in rows)
    max_abs = max((row.absolute_difference for row in rows), default=0.0)
    max_rel = max((row.relative_difference for row in rows), default=0.0)
    pre_matrix_components = {
        "istruc_fraction", "calc_ion_rates_pirt", "calc_ion_rates_rrrt",
        "ion_limit_mml", "ion_limit_mmu", "ion_limit_critf",
    }
    pre_matrix_ready = (
        pre_matrix_missing_python == 0
        and pre_matrix_missing_xstar == 0
        and all(row.within_tolerance for row in rows if row.component in pre_matrix_components)
    )
    summary_gate = summary_ready is not False
    ready = bool(
        pre_matrix_ready
        and state_ready
        and global_arrays_ready
        and summary_gate
    )
    return CalcHMCAllPreContinuumParityResult(
        call_id=selected_call,
        rows=rows,
        n_missing_python_keys=missing_python,
        n_missing_xstar_keys=missing_xstar,
        max_absolute_difference=max_abs,
        max_relative_difference=max_rel,
        n_outside_tolerance=outside,
        pre_matrix_ready=pre_matrix_ready,
        pre_continuum_state_ready=state_ready,
        pre_continuum_summary_ready=summary_ready,
        pre_continuum_summary_status=summary_status,
        global_ion_ready=global_ion_ready,
        global_level_ready=global_level_ready,
        global_arrays_ready=global_arrays_ready,
        parity_ready=ready,
        diagnostics={
            "probe_dir": str(root),
            "rtol": float(rtol),
            "atol": float(atol),
            "summary_scope_complete": summary_comparable,
            "deferred_summary_fields": deferred_summary_fields,
            "n_global_ion_probe_rows": len(ion_rows),
            "n_global_level_probe_rows": len(level_rows),
            "n_compared_global_level_indices": len(compared_level_indices),
            "pre_matrix_missing_python_keys": pre_matrix_missing_python,
            "pre_matrix_missing_xstar_keys": pre_matrix_missing_xstar,
            "global_ion_missing_python_keys": ion_missing_python,
            "global_ion_missing_xstar_keys": ion_missing_xstar,
            "global_level_missing_python_keys": level_missing_python,
            "global_level_missing_xstar_keys": level_missing_xstar,
        },
    )


def write_calc_hmc_all_pre_continuum_parity_products(
    result: CalcHMCAllPreContinuumParityResult,
    out_dir: str | Path,
) -> Dict[str, str]:
    """Write row-level CSV and compact JSON/Markdown summaries."""

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    details = out / "xstar_calc_hmc_all_pre_continuum_parity_details.csv"
    with details.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=(
            "component", "key", "python_value", "xstar_value",
            "absolute_difference", "relative_difference", "within_tolerance",
        ))
        writer.writeheader()
        for row in result.rows:
            writer.writerow(row.__dict__)

    payload = {
        "port_version": "v0.4.25",
        "call_id": result.call_id,
        "n_rows": len(result.rows),
        "n_missing_python_keys": result.n_missing_python_keys,
        "n_missing_xstar_keys": result.n_missing_xstar_keys,
        "n_outside_tolerance": result.n_outside_tolerance,
        "max_absolute_difference": result.max_absolute_difference,
        "max_relative_difference": result.max_relative_difference,
        "pre_matrix_ready": result.pre_matrix_ready,
        "pre_continuum_state_ready": result.pre_continuum_state_ready,
        "pre_continuum_summary_ready": result.pre_continuum_summary_ready,
        "pre_continuum_summary_status": result.pre_continuum_summary_status,
        "global_ion_ready": result.global_ion_ready,
        "global_level_ready": result.global_level_ready,
        "global_arrays_ready": result.global_arrays_ready,
        "parity_ready": result.parity_ready,
        "diagnostics": result.diagnostics,
    }
    json_path = out / "xstar_calc_hmc_all_pre_continuum_parity_summary.json"
    json_path.write_text(json.dumps(payload, indent=2) + "\n")
    md = out / "xstar_calc_hmc_all_pre_continuum_parity_summary.md"
    md.write_text(
        "# calc_hmc_all pre-continuum parity\n\n"
        f"- Call ID: `{result.call_id}`\n"
        f"- Compared rows: `{len(result.rows)}`\n"
        f"- Outside tolerance: `{result.n_outside_tolerance}`\n"
        f"- Missing Python keys: `{result.n_missing_python_keys}`\n"
        f"- Missing XSTAR keys: `{result.n_missing_xstar_keys}`\n"
        f"- Pre-matrix ready: `{result.pre_matrix_ready}`\n"
        f"- Runtime state ready: `{result.pre_continuum_state_ready}`\n"
        f"- Summary status: `{result.pre_continuum_summary_status}`\n"
        f"- Summary ready: `{result.pre_continuum_summary_ready}`\n"
        f"- Global ion arrays ready: `{result.global_ion_ready}`\n"
        f"- Global level arrays ready: `{result.global_level_ready}`\n"
        f"- Global arrays ready: `{result.global_arrays_ready}`\n"
        f"- Overall parity ready: `{result.parity_ready}`\n"
    )
    return {"details_csv": str(details), "json": str(json_path), "markdown": str(md)}


__all__ = [
    "CalcHMCAllParityError",
    "CalcHMCAllProbeCritfReference",
    "CalcHMCAllParityRow",
    "CalcHMCAllPreContinuumParityResult",
    "load_calc_hmc_all_probe_critf",
    "compare_calc_hmc_all_pre_continuum_probe",
    "write_calc_hmc_all_pre_continuum_parity_products",
]
