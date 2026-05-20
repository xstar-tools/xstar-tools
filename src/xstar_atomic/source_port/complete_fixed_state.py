"""Complete fixed-state ``calc_hmc_all`` thermal and charge parity.

This v0.4.43 closure layer does not translate a new physical leaf.  It executes
all previously translated source routines in literal order::

    element loop -> comp2 -> freef -> bremem -> heatf

and compares the final caller-visible thermal and charge state against one
same-call XSTAR probe written immediately before ``calc_hmc_all`` returns.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import csv
import json
import math
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence, Tuple

from .fortran_numbers import parse_fortran_float
from .local_zone import FixedStateCalcHMCAllResult


class CompleteFixedStateParityError(RuntimeError):
    """Raised when the final same-call probe is missing or inconsistent."""


@dataclass(frozen=True)
class CalcHMCAllFinalStateReference:
    call_id: int
    temperature_t4: float
    temperature_k: float
    electron_fraction_xee: float
    hydrogen_density_cm3: float
    electron_density_cm3: float
    electron_contribution: float
    elcter: float
    htfreef: float
    cmp1: float
    cmp2: float
    htcomp: float
    clcomp: float
    clbrems: float
    httot: float
    cltot: float
    httot2: float
    cltot2: float
    hmctot: float
    summary_path: str


@dataclass(frozen=True)
class CompleteFixedStateParityRow:
    category: str
    quantity: str
    python_value: float
    xstar_value: float
    absolute_difference: float
    relative_difference: float
    rtol: float
    atol: float
    within_tolerance: bool


@dataclass(frozen=True)
class CompleteFixedStateParityResult:
    call_id: int
    reference: CalcHMCAllFinalStateReference
    rows: Tuple[CompleteFixedStateParityRow, ...]
    fixed_state_calc_hmc_all_translated: bool
    pre_matrix_ready: bool
    element_loop_ready: bool
    charge_scope_complete: bool
    continuum_sequence_complete: bool
    runtime_state_parity_ready: bool
    continuum_component_parity_ready: bool
    primary_heating_cooling_totals_parity_ready: bool
    secondary_heating_cooling_totals_parity_ready: bool
    electron_contribution_parity_ready: bool
    charge_residual_parity_ready: bool
    charge_identity_ready: bool
    hmctot_parity_ready: bool
    complete_fixed_state_ready: bool
    max_absolute_difference: float
    max_relative_difference: float
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    @property
    def ready(self) -> bool:
        return bool(
            self.fixed_state_calc_hmc_all_translated
            and self.pre_matrix_ready
            and self.element_loop_ready
            and self.charge_scope_complete
            and self.continuum_sequence_complete
            and self.runtime_state_parity_ready
            and self.continuum_component_parity_ready
            and self.primary_heating_cooling_totals_parity_ready
            and self.secondary_heating_cooling_totals_parity_ready
            and self.electron_contribution_parity_ready
            and self.charge_residual_parity_ready
            and self.charge_identity_ready
            and self.hmctot_parity_ready
            and self.complete_fixed_state_ready
        )


def _resolve_final_probe(path: str | Path) -> Path:
    target = Path(path)
    if target.is_dir():
        target = target / "xstar_calc_hmc_all_final_state_probe.csv"
    if not target.is_file():
        raise CompleteFixedStateParityError(f"missing final-state probe: {target}")
    return target


def load_calc_hmc_all_final_state_reference(
    path: str | Path,
    *,
    call_id: int = 73,
) -> CalcHMCAllFinalStateReference:
    target = _resolve_final_probe(path)
    with target.open(newline="", encoding="utf-8") as handle:
        rows = [row for row in csv.DictReader(handle) if int(row["calc_hmc_all_call_id"]) == int(call_id)]
    if len(rows) != 1:
        raise CompleteFixedStateParityError(
            f"expected one final-state row for call {call_id}, found {len(rows)} in {target}"
        )
    row = rows[0]
    f = parse_fortran_float
    return CalcHMCAllFinalStateReference(
        call_id=int(row["calc_hmc_all_call_id"]),
        temperature_t4=f(row["temperature_t4"]),
        temperature_k=f(row["temperature_k"]),
        electron_fraction_xee=f(row["electron_fraction_xee"]),
        hydrogen_density_cm3=f(row["hydrogen_density_cm3"]),
        electron_density_cm3=f(row["electron_density_cm3"]),
        electron_contribution=f(row["enelec"]),
        elcter=f(row["elcter"]),
        htfreef=f(row["htfreef"]),
        cmp1=f(row["cmp1"]),
        cmp2=f(row["cmp2"]),
        htcomp=f(row["htcomp"]),
        clcomp=f(row["clcomp"]),
        clbrems=f(row["clbrems"]),
        httot=f(row["httot"]),
        cltot=f(row["cltot"]),
        httot2=f(row["httot2"]),
        cltot2=f(row["cltot2"]),
        hmctot=f(row["hmctot"]),
        summary_path=str(target),
    )


def _row(
    category: str,
    quantity: str,
    python_value: float,
    xstar_value: float,
    *,
    rtol: float,
    atol: float,
) -> CompleteFixedStateParityRow:
    py = float(python_value)
    xs = float(xstar_value)
    absolute = abs(py - xs)
    relative = absolute / max(abs(xs), 1.0e-300)
    return CompleteFixedStateParityRow(
        category=category,
        quantity=quantity,
        python_value=py,
        xstar_value=xs,
        absolute_difference=absolute,
        relative_difference=relative,
        rtol=float(rtol),
        atol=float(atol),
        within_tolerance=math.isclose(py, xs, rel_tol=float(rtol), abs_tol=float(atol)),
    )


def compare_complete_fixed_state_calc_hmc_all(
    result: FixedStateCalcHMCAllResult,
    reference: CalcHMCAllFinalStateReference,
    *,
    rtol: float = 5.0e-3,
    atol: float = 1.0e-12,
    continuum_rtol: float = 5.0e-12,
    continuum_atol: float = 1.0e-30,
    runtime_rtol: float = 5.0e-12,
    runtime_atol: float = 1.0e-30,
) -> CompleteFixedStateParityResult:
    diagnostics = dict(result.continuum.diagnostics)
    cmp1 = float(diagnostics.get("cmp1", float("nan")))
    cmp2 = float(diagnostics.get("cmp2", float("nan")))

    rows = [
        _row("runtime", "temperature_t4", result.temperature_k / 1.0e4, reference.temperature_t4, rtol=runtime_rtol, atol=runtime_atol),
        _row("runtime", "temperature_k", result.temperature_k, reference.temperature_k, rtol=runtime_rtol, atol=runtime_atol),
        _row("runtime", "electron_fraction_xee", result.electron_fraction_xee, reference.electron_fraction_xee, rtol=runtime_rtol, atol=runtime_atol),
        _row("runtime", "hydrogen_density_cm3", result.hydrogen_density_cm3, reference.hydrogen_density_cm3, rtol=runtime_rtol, atol=runtime_atol),
        _row("runtime", "electron_density_cm3", result.electron_density_cm3, reference.electron_density_cm3, rtol=runtime_rtol, atol=runtime_atol),
        _row("continuum_component", "htfreef", result.continuum.htfreef, reference.htfreef, rtol=continuum_rtol, atol=continuum_atol),
        _row("continuum_component", "cmp1", cmp1, reference.cmp1, rtol=continuum_rtol, atol=continuum_atol),
        _row("continuum_component", "cmp2", cmp2, reference.cmp2, rtol=continuum_rtol, atol=continuum_atol),
        _row("continuum_component", "htcomp", result.continuum.htcomp, reference.htcomp, rtol=continuum_rtol, atol=continuum_atol),
        _row("continuum_component", "clcomp", result.continuum.clcomp, reference.clcomp, rtol=continuum_rtol, atol=continuum_atol),
        _row("continuum_component", "clbrems", result.continuum.clbrems, reference.clbrems, rtol=continuum_rtol, atol=continuum_atol),
        _row("primary_total", "httot", result.httot, reference.httot, rtol=rtol, atol=atol),
        _row("primary_total", "cltot", result.cltot, reference.cltot, rtol=rtol, atol=atol),
        _row("secondary_total", "httot2", result.httot2, reference.httot2, rtol=rtol, atol=atol),
        _row("secondary_total", "cltot2", result.cltot2, reference.cltot2, rtol=rtol, atol=atol),
        _row("charge", "enelec", result.electron_contribution, reference.electron_contribution, rtol=rtol, atol=atol),
        _row("charge", "elcter", result.elcter, reference.elcter, rtol=rtol, atol=atol),
        _row("thermal_residual", "hmctot", result.hmctot, reference.hmctot, rtol=rtol, atol=atol),
    ]

    by_category: Dict[str, Sequence[CompleteFixedStateParityRow]] = {}
    for category in {item.category for item in rows}:
        by_category[category] = tuple(item for item in rows if item.category == category)

    source_flags = (
        diagnostics.get("comp2_translated") is True,
        diagnostics.get("freef_translated") is True,
        diagnostics.get("bremem_translated") is True,
        diagnostics.get("heatf_translated") is True,
    )
    python_charge_identity = math.isclose(
        result.elcter,
        result.electron_fraction_xee - result.electron_contribution,
        rel_tol=runtime_rtol,
        abs_tol=runtime_atol,
    )
    xstar_charge_identity = math.isclose(
        reference.elcter,
        reference.electron_fraction_xee - reference.electron_contribution,
        rel_tol=runtime_rtol,
        abs_tol=runtime_atol,
    )
    max_abs = max((item.absolute_difference for item in rows), default=0.0)
    max_rel = max((item.relative_difference for item in rows), default=0.0)

    return CompleteFixedStateParityResult(
        call_id=reference.call_id,
        reference=reference,
        rows=tuple(rows),
        fixed_state_calc_hmc_all_translated=True,
        pre_matrix_ready=bool(result.pre_matrix_ready),
        element_loop_ready=bool(result.element_loop_ready),
        charge_scope_complete=bool(result.charge_closure_scope_complete),
        continuum_sequence_complete=bool(result.continuum.complete and all(source_flags)),
        runtime_state_parity_ready=all(item.within_tolerance for item in by_category["runtime"]),
        continuum_component_parity_ready=all(item.within_tolerance for item in by_category["continuum_component"]),
        primary_heating_cooling_totals_parity_ready=all(item.within_tolerance for item in by_category["primary_total"]),
        secondary_heating_cooling_totals_parity_ready=all(item.within_tolerance for item in by_category["secondary_total"]),
        electron_contribution_parity_ready=next(item for item in rows if item.quantity == "enelec").within_tolerance,
        charge_residual_parity_ready=next(item for item in rows if item.quantity == "elcter").within_tolerance,
        charge_identity_ready=bool(python_charge_identity and xstar_charge_identity),
        hmctot_parity_ready=next(item for item in rows if item.quantity == "hmctot").within_tolerance,
        complete_fixed_state_ready=bool(result.complete_fixed_state_ready),
        max_absolute_difference=max_abs,
        max_relative_difference=max_rel,
        diagnostics={
            "rtol": float(rtol),
            "atol": float(atol),
            "continuum_rtol": float(continuum_rtol),
            "continuum_atol": float(continuum_atol),
            "runtime_rtol": float(runtime_rtol),
            "runtime_atol": float(runtime_atol),
            "reference_summary_path": reference.summary_path,
            "source_sequence": "element loop -> comp2 -> freef -> bremem -> heatf -> return",
            "dsec_deferred": True,
        },
    )


def write_complete_fixed_state_parity_products(
    parity: CompleteFixedStateParityResult,
    out_dir: str | Path,
    *,
    port_version: str = "v0.4.43",
) -> Dict[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    csv_path = out / "xstar_calc_hmc_all_complete_fixed_state_parity.csv"
    fields = tuple(CompleteFixedStateParityRow.__dataclass_fields__)
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for item in parity.rows:
            writer.writerow({name: getattr(item, name) for name in fields})

    summary = {
        "port_version": port_version,
        "calc_hmc_all_call_id": parity.call_id,
        "fixed_state_calc_hmc_all_translated": parity.fixed_state_calc_hmc_all_translated,
        "pre_matrix_ready": parity.pre_matrix_ready,
        "element_loop_ready": parity.element_loop_ready,
        "charge_scope_complete": parity.charge_scope_complete,
        "continuum_sequence_complete": parity.continuum_sequence_complete,
        "runtime_state_parity_ready": parity.runtime_state_parity_ready,
        "continuum_component_parity_ready": parity.continuum_component_parity_ready,
        "primary_heating_cooling_totals_parity_ready": parity.primary_heating_cooling_totals_parity_ready,
        "secondary_heating_cooling_totals_parity_ready": parity.secondary_heating_cooling_totals_parity_ready,
        "electron_contribution_parity_ready": parity.electron_contribution_parity_ready,
        "charge_residual_parity_ready": parity.charge_residual_parity_ready,
        "charge_identity_ready": parity.charge_identity_ready,
        "hmctot_parity_ready": parity.hmctot_parity_ready,
        "complete_fixed_state_ready": parity.complete_fixed_state_ready,
        "complete_fixed_state_parity_ready": parity.ready,
        "max_absolute_difference": parity.max_absolute_difference,
        "max_relative_difference": parity.max_relative_difference,
        "reference_summary_path": parity.reference.summary_path,
        "diagnostics": dict(parity.diagnostics),
    }
    json_path = out / "xstar_calc_hmc_all_complete_fixed_state_parity_summary.json"
    json_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path = out / "xstar_calc_hmc_all_complete_fixed_state_parity_summary.md"
    md_path.write_text(
        "# Complete fixed-state calc_hmc_all parity\n\n"
        + "\n".join(f"- {key}: `{value}`" for key, value in summary.items())
        + "\n",
        encoding="utf-8",
    )
    return {"csv": csv_path, "json": json_path, "markdown": md_path}


__all__ = [
    "CompleteFixedStateParityError",
    "CalcHMCAllFinalStateReference",
    "CompleteFixedStateParityRow",
    "CompleteFixedStateParityResult",
    "load_calc_hmc_all_final_state_reference",
    "compare_complete_fixed_state_calc_hmc_all",
    "write_complete_fixed_state_parity_products",
]
