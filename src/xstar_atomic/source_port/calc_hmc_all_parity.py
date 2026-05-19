"""Parity checks for the bounded XSTAR ``calc_hmc_all`` probe."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
import csv
import json
import math

from .local_zone import FixedStateCalcHMCAllResult


class CalcHMCAllParityError(RuntimeError):
    """Raised when bounded probe products are missing or malformed."""


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
    pre_continuum_summary_ready: bool
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


def _metric(component: str, key: str, python: float, xstar: float, *, rtol: float, atol: float) -> CalcHMCAllParityRow:
    diff = abs(float(python) - float(xstar))
    scale = max(abs(float(python)), abs(float(xstar)), 1.0e-300)
    rel = diff / scale
    ok = diff <= float(atol) + float(rtol) * abs(float(xstar))
    return CalcHMCAllParityRow(component, key, float(python), float(xstar), diff, rel, bool(ok))


def compare_calc_hmc_all_pre_continuum_probe(
    result: FixedStateCalcHMCAllResult,
    probe_dir: str | Path,
    *,
    call_id: Optional[int] = None,
    rtol: float = 5.0e-3,
    atol: float = 1.0e-12,
) -> CalcHMCAllPreContinuumParityResult:
    """Compare Python first-pass and pre-``comp2`` products to XSTAR."""
    if rtol < 0.0 or atol < 0.0:
        raise CalcHMCAllParityError("rtol and atol must be nonnegative")
    root = Path(probe_dir)
    element_rows = _read_csv(root / "xstar_calc_hmc_element_pre_matrix_probe.csv")
    summary_rows = _read_csv(root / "xstar_calc_hmc_all_pre_continuum_summary_probe.csv")
    selected_call = _resolve_call_id(element_rows + summary_rows, call_id)
    element_rows = [r for r in element_rows if int(r["calc_hmc_all_call_id"]) == selected_call]
    summary_rows = [r for r in summary_rows if int(r["calc_hmc_all_call_id"]) == selected_call]
    if len(summary_rows) != 1:
        raise CalcHMCAllParityError(
            f"expected one pre-continuum summary for call {selected_call}, got {len(summary_rows)}"
        )

    rows: List[CalcHMCAllParityRow] = []
    missing_python = 0
    missing_xstar = 0

    xstar_keys = {(int(r["element_z"]), int(r["ion_stage"])) for r in element_rows}
    python_keys = set(result.preliminary_ion_fractions)
    # Only elements explicitly present in the probe are in scope.
    probe_elements = {z for z, _ in xstar_keys}
    python_keys = {key for key in python_keys if key[0] in probe_elements}
    missing_python += len(xstar_keys - python_keys)
    missing_xstar += len(python_keys - xstar_keys)

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
        rows.append(_metric(
            "ion_limit_mml", f"Z={z}", float(result.mml.get(z, 0)), float(record["mml"]),
            rtol=0.0, atol=0.0,
        ))
        rows.append(_metric(
            "ion_limit_mmu", f"Z={z}", float(result.mmu.get(z, 0)), float(record["mmu"]),
            rtol=0.0, atol=0.0,
        ))

    summary = summary_rows[0]
    summary_pairs = (
        ("temperature_k", result.temperature_k, float(summary["temperature_k"])),
        ("xee", result.electron_fraction_xee, float(summary["xee"])),
        ("xpx", result.hydrogen_density_cm3, float(summary["xpx"])),
        ("httot", result.httot, float(summary["httot"])),
        ("cltot", result.cltot, float(summary["cltot"])),
        ("httot2", result.httot2, float(summary["httot2"])),
        ("cltot2", result.cltot2, float(summary["cltot2"])),
        ("enelec", result.electron_contribution, float(summary["enelec"])),
        ("elcter", result.elcter, float(summary["elcter"])),
    )
    for name, python_value, xstar_value in summary_pairs:
        rows.append(_metric(
            "pre_continuum_summary", name, python_value, xstar_value,
            rtol=rtol, atol=atol,
        ))

    outside = sum(not row.within_tolerance for row in rows)
    max_abs = max((row.absolute_difference for row in rows), default=0.0)
    max_rel = max((row.relative_difference for row in rows), default=0.0)
    pre_matrix_components = {
        "istruc_fraction", "calc_ion_rates_pirt", "calc_ion_rates_rrrt",
        "ion_limit_mml", "ion_limit_mmu",
    }
    pre_matrix_ready = (
        missing_python == 0
        and missing_xstar == 0
        and all(row.within_tolerance for row in rows if row.component in pre_matrix_components)
    )
    summary_ready = all(
        row.within_tolerance for row in rows if row.component == "pre_continuum_summary"
    )
    ready = bool(pre_matrix_ready and summary_ready)
    return CalcHMCAllPreContinuumParityResult(
        call_id=selected_call,
        rows=rows,
        n_missing_python_keys=missing_python,
        n_missing_xstar_keys=missing_xstar,
        max_absolute_difference=max_abs,
        max_relative_difference=max_rel,
        n_outside_tolerance=outside,
        pre_matrix_ready=pre_matrix_ready,
        pre_continuum_summary_ready=summary_ready,
        parity_ready=ready,
        diagnostics={
            "probe_dir": str(root),
            "rtol": float(rtol),
            "atol": float(atol),
            "global_ion_probe_present": (root / "xstar_calc_hmc_all_pre_continuum_ions_probe.csv").exists(),
            "global_level_probe_present": (root / "xstar_calc_hmc_all_pre_continuum_levels_probe.csv").exists(),
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
        "port_version": "v0.4.24",
        "call_id": result.call_id,
        "n_rows": len(result.rows),
        "n_missing_python_keys": result.n_missing_python_keys,
        "n_missing_xstar_keys": result.n_missing_xstar_keys,
        "n_outside_tolerance": result.n_outside_tolerance,
        "max_absolute_difference": result.max_absolute_difference,
        "max_relative_difference": result.max_relative_difference,
        "pre_matrix_ready": result.pre_matrix_ready,
        "pre_continuum_summary_ready": result.pre_continuum_summary_ready,
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
        f"- Pre-continuum summary ready: `{result.pre_continuum_summary_ready}`\n"
        f"- Overall parity ready: `{result.parity_ready}`\n"
    )
    return {"details_csv": str(details), "json": str(json_path), "markdown": str(md)}


__all__ = [
    "CalcHMCAllParityError",
    "CalcHMCAllParityRow",
    "CalcHMCAllPreContinuumParityResult",
    "compare_calc_hmc_all_pre_continuum_probe",
    "write_calc_hmc_all_pre_continuum_parity_products",
]
