"""XSTAR-output reproduction benchmarks for local He-like validation.

This module separates two questions that were previously mixed in the example
scripts:

1. What exactly did the same XSTAR run write to ``xout_abund1.fits`` and
   ``xout_lines1.fits`` for the selected local zone and He-like triplet?
2. How far is an ``xstar-atomic`` solver/audit product from those exact targets?

The helpers here intentionally make the first step an identity-style target
extraction.  They should reproduce the values in the XSTAR output files exactly
up to the explicit unit conversions documented in the output tables
(``temperature`` in ``xout_abund1.fits`` is stored in units of 10^4 K, and the
local electron density is reconstructed as ``x_e * n_p``).  Solver physics is
not modified here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence
import csv
import json
import math

from .context import XSTARContext, context_from_xstar_run
from .workflow import TripletResult, calc_triplet, solve_populations
from .xstar_outputs import load_xstar_lines, write_csv

DEFAULT_HELIKE_WINDOWS_A: dict[str, tuple[float, float]] = {
    "C V": (40.0, 42.0),
    "O VII": (21.0, 23.0),
    "Mg XI": (9.0, 9.4),
    "Ca XIX": (3.0, 3.35),
}


def _ion_label(ion: str | None) -> str | None:
    """Normalize a simple ion label without importing the FITS-backed API."""
    if ion is None:
        return None
    import re

    text = str(ion).strip()
    if not text:
        return None
    text = re.sub(r"[_\-./]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    parts = text.split()
    if len(parts) >= 2:
        elem = parts[0][0].upper() + parts[0][1:].lower()
        stage_text = parts[1].upper()
    else:
        m = re.match(r"^([A-Za-z]{1,2})([0-9]+|[IVXLCDMivxlcdm]+)$", parts[0])
        if not m:
            return text
        elem = m.group(1)[0].upper() + m.group(1)[1:].lower()
        stage_text = m.group(2).upper()
    if stage_text.isdigit():
        stage_text = _int_to_roman(int(stage_text))
    return f"{elem} {stage_text}"


def _int_to_roman(number: int) -> str:
    vals = [
        (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
        (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
        (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
    ]
    out: list[str] = []
    n = int(number)
    for value, glyph in vals:
        while n >= value:
            out.append(glyph)
            n -= value
    return "".join(out)


def default_helike_wavelength_window(ion: str | None) -> tuple[float, float] | None:
    """Return the default He-like triplet wavelength window for common benchmarks."""
    label = _ion_label(ion)
    if label is None:
        return None
    return DEFAULT_HELIKE_WINDOWS_A.get(label)


def find_xstar_run_files(
    run_dir: str | Path,
    *,
    xout_abund_filename: str | None = None,
    xout_lines_filename: str | None = None,
) -> dict[str, Path | None]:
    """Locate the local-state and line-output files for one XSTAR run.

    Both the correct ``xout_abund1.fits`` spelling and the common typo
    ``xout_abubd1.fits`` are checked so command-line workflows fail less
    mysteriously when a user types the filename from memory.
    """
    run_path = Path(run_dir)
    abund_candidates = []
    if xout_abund_filename:
        abund_candidates.append(run_path / xout_abund_filename)
    abund_candidates.extend([run_path / "xout_abund1.fits", run_path / "xout_abubd1.fits"])
    line_candidates = []
    if xout_lines_filename:
        line_candidates.append(run_path / xout_lines_filename)
    line_candidates.append(run_path / "xout_lines1.fits")
    abund = next((p for p in abund_candidates if p.exists()), None)
    lines = next((p for p in line_candidates if p.exists()), None)
    return {"xout_abund": abund, "xout_lines": lines}


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except Exception:
        return None
    return out if math.isfinite(out) else None


def _difference(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    return float(a) - float(b)


@dataclass(frozen=True)
class XSTARLocalTarget:
    """Exact same-run target extracted from XSTAR local output files."""

    ion: str | None
    run_dir: str
    context: XSTARContext
    triplet: TripletResult
    line_rows: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    xout_abund_path: str | None = None
    xout_lines_path: str | None = None
    wavelength_window_A: tuple[float, float] | None = None
    value_column: str = "emit_outward"
    status: str = "ok"
    warnings: tuple[str, ...] = ()

    def local_state_row(self) -> dict[str, Any]:
        """Return the selected local-state target as one flat row."""
        p = self.context.plasma
        return {
            "ion": self.ion,
            "run_dir": self.run_dir,
            "xout_abund_path": self.xout_abund_path,
            "selection": self.context.metadata.get("selection"),
            "zone_index": p.zone_index,
            "temperature_K": p.temperature_K,
            "electron_density_cm^-3": p.electron_density_cm3,
            "log_xi": p.log_xi,
            "xi_erg_cm_s^-1": p.ionization_parameter,
            "ion_fraction": p.ion_fraction,
            "ion_fraction_column": self.context.metadata.get("ion_fraction_column"),
            "radius_cm": p.radius_cm,
            "thickness_cm": p.thickness_cm,
            "status": self.status,
            "warnings": "; ".join(self.warnings),
        }

    def triplet_row(self) -> dict[str, Any]:
        """Return the selected XSTAR triplet target as one flat row."""
        t = self.triplet
        return {
            "ion": self.ion,
            "run_dir": self.run_dir,
            "xout_lines_path": self.xout_lines_path,
            "wavelength_min_A": self.wavelength_window_A[0] if self.wavelength_window_A else None,
            "wavelength_max_A": self.wavelength_window_A[1] if self.wavelength_window_A else None,
            "value_column": self.value_column,
            "xstar_forbidden": t.forbidden,
            "xstar_intercombination": t.intercombination,
            "xstar_resonance": t.resonance,
            "xstar_f_fraction": t.f,
            "xstar_i_fraction": t.i,
            "xstar_r_fraction": t.r,
            "xstar_R_f_over_i": t.R_f_over_i,
            "xstar_G_f_plus_i_over_r": t.G_f_plus_i_over_r,
            "xstar_triplet_total": t.total,
            "n_triplet_lines": len(t.lines),
            "status": t.status,
            "warnings": "; ".join(t.warnings),
        }

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly nested representation."""
        return {
            "ion": self.ion,
            "run_dir": self.run_dir,
            "xout_abund_path": self.xout_abund_path,
            "xout_lines_path": self.xout_lines_path,
            "wavelength_window_A": list(self.wavelength_window_A) if self.wavelength_window_A else None,
            "value_column": self.value_column,
            "local_state": self.local_state_row(),
            "triplet": self.triplet_row(),
            "context": self.context.to_dict(),
            "line_rows": [dict(r) for r in self.line_rows],
            "status": self.status,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class XSTARBenchmarkComparison:
    """Comparison between an ``xstar-atomic`` result and an XSTAR target."""

    target: XSTARLocalTarget
    solver_triplet: Mapping[str, Any] | None = None
    solver_summary: Mapping[str, Any] | None = None
    status: str = "target_only"
    warnings: tuple[str, ...] = ()

    def comparison_row(self) -> dict[str, Any]:
        """Return one flat row with target and solver residuals when available."""
        row = self.target.triplet_row()
        row.update(self.target.local_state_row())
        solver = dict(self.solver_triplet or {})
        sf = _as_float(solver.get("f_fraction") or solver.get("f") or solver.get("solver_f"))
        si = _as_float(solver.get("i_fraction") or solver.get("i") or solver.get("solver_i"))
        sr = _as_float(solver.get("r_fraction") or solver.get("r") or solver.get("solver_r"))
        row.update({
            "solver_f_fraction": sf,
            "solver_i_fraction": si,
            "solver_r_fraction": sr,
            "delta_f_solver_minus_xstar": _difference(sf, self.target.triplet.f),
            "delta_i_solver_minus_xstar": _difference(si, self.target.triplet.i),
            "delta_r_solver_minus_xstar": _difference(sr, self.target.triplet.r),
            "comparison_status": self.status,
            "comparison_warnings": "; ".join(self.warnings),
        })
        return row

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly representation."""
        return {
            "target": self.target.to_dict(),
            "solver_triplet": dict(self.solver_triplet or {}),
            "solver_summary": dict(self.solver_summary or {}),
            "comparison": self.comparison_row(),
            "status": self.status,
            "warnings": list(self.warnings),
        }


def build_xstar_local_target(
    run_dir: str | Path,
    *,
    ion: str | None,
    zone_index: int | None = None,
    selection: str = "max_fraction",
    wavelength: tuple[float, float] | None = None,
    value_column: str = "emit_outward",
    xout_abund_filename: str | None = None,
    xout_lines_filename: str | None = None,
) -> XSTARLocalTarget:
    """Extract the exact local-state and triplet target from one XSTAR run.

    This function is the benchmark anchor for C V, O VII, Mg XI, and Ca XIX. It
    reads ``xout_abund1.fits`` for the local ``T``, ``ne``, ``log xi`` and ion
    fraction, and reads ``xout_lines1.fits`` for the triplet line values.  The
    returned target is the reference against which any future solver correction
    must be compared.
    """
    run_path = Path(run_dir)
    files = find_xstar_run_files(run_path, xout_abund_filename=xout_abund_filename, xout_lines_filename=xout_lines_filename)
    abund_path = files["xout_abund"]
    lines_path = files["xout_lines"]
    if abund_path is None:
        raise FileNotFoundError(f"Could not find xout_abund1.fits in {run_path}")
    if lines_path is None:
        raise FileNotFoundError(f"Could not find xout_lines1.fits in {run_path}")
    ctx = context_from_xstar_run(
        run_path,
        ion=ion,
        zone_index=zone_index,
        selection=selection,
        xout_abund_filename=abund_path.name,
    )
    window = wavelength if wavelength is not None else default_helike_wavelength_window(ion)
    rows = load_xstar_lines(
        lines_path,
        ion=ion,
        wavelength_min=window[0] if window else None,
        wavelength_max=window[1] if window else None,
    )
    triplet = calc_triplet(ion=ion, context=ctx, rows=rows, value_column=value_column, wavelength=window)
    warnings: list[str] = []
    if triplet.status != "ok":
        warnings.extend(triplet.warnings)
    return XSTARLocalTarget(
        ion=_ion_label(ion) or ion,
        run_dir=str(run_path),
        context=ctx,
        triplet=triplet,
        line_rows=tuple(dict(r) for r in triplet.lines),
        xout_abund_path=str(abund_path),
        xout_lines_path=str(lines_path),
        wavelength_window_A=window,
        value_column=value_column,
        status="ok" if triplet.status == "ok" else "target_incomplete",
        warnings=tuple(warnings),
    )


def compare_solver_to_xstar_target(
    target: XSTARLocalTarget,
    *,
    db: Any = None,
    fitsfile: str | Path | None = None,
    run_solver: bool = False,
    solver_triplet: Mapping[str, Any] | None = None,
    solver_kwargs: Mapping[str, Any] | None = None,
) -> XSTARBenchmarkComparison:
    """Compare a solver/product triplet with an exact XSTAR local target.

    By default this is target-only.  Set ``run_solver=True`` to call the current
    population solver wrapper, or pass ``solver_triplet`` from an existing solver
    output/comparison summary.  No new type-50 photoexcitation physics is
    injected here.
    """
    warnings: list[str] = []
    summary: Mapping[str, Any] | None = None
    triplet = solver_triplet
    status = "target_only"
    if run_solver:
        if target.ion is None:
            raise ValueError("run_solver=True requires target.ion")
        try:
            result = solve_populations(target.ion, context=target.context, db=db, fitsfile=fitsfile, **dict(solver_kwargs or {}))
            summary = result.get("summary", result) if isinstance(result, Mapping) else {}
            if isinstance(result, Mapping):
                # Several solver products store triplet values under different
                # keys.  Keep this defensive so the comparison API can consume
                # old result dictionaries.
                triplet = (
                    result.get("triplet")
                    or result.get("triplet_summary")
                    or result.get("xstar_like_element_solver_triplet")
                    or {}
                )
            status = "solver_compared"
        except Exception as exc:  # pragma: no cover - exercised with real ATDB runs
            warnings.append(f"solver_failed: {exc}")
            status = "solver_failed"
    elif solver_triplet is not None:
        status = "solver_compared"
    return XSTARBenchmarkComparison(target=target, solver_triplet=triplet, solver_summary=summary, status=status, warnings=tuple(warnings))


def reproduce_xstar_run(
    run_dir: str | Path,
    *,
    ion: str | None,
    zone_index: int | None = None,
    selection: str = "max_fraction",
    wavelength: tuple[float, float] | None = None,
    value_column: str = "emit_outward",
    run_solver: bool = False,
    db: Any = None,
    fitsfile: str | Path | None = None,
    solver_kwargs: Mapping[str, Any] | None = None,
) -> XSTARBenchmarkComparison:
    """Extract exact XSTAR targets and optionally compare a solver run."""
    target = build_xstar_local_target(
        run_dir,
        ion=ion,
        zone_index=zone_index,
        selection=selection,
        wavelength=wavelength,
        value_column=value_column,
    )
    return compare_solver_to_xstar_target(
        target,
        db=db,
        fitsfile=fitsfile,
        run_solver=run_solver,
        solver_kwargs=solver_kwargs,
    )


def write_xstar_benchmark_outputs(
    comparison: XSTARBenchmarkComparison,
    out_dir: str | Path,
    *,
    prefix: str = "xstar_local_reproduction",
) -> dict[str, str]:
    """Write CSV/JSON/Markdown files for one reproduction benchmark."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    local_csv = out / f"{prefix}_local_state.csv"
    triplet_csv = out / f"{prefix}_triplet_target.csv"
    lines_csv = out / f"{prefix}_triplet_lines.csv"
    compare_csv = out / f"{prefix}_comparison.csv"
    json_path = out / f"{prefix}.json"
    md_path = out / f"{prefix}.md"
    write_csv([comparison.target.local_state_row()], local_csv)
    write_csv([comparison.target.triplet_row()], triplet_csv)
    write_csv([dict(r) for r in comparison.target.line_rows], lines_csv)
    write_csv([comparison.comparison_row()], compare_csv)
    json_path.write_text(json.dumps(comparison.to_dict(), indent=2, default=str) + "\n", encoding="utf-8")
    _write_benchmark_md(comparison, md_path)
    return {
        "local_state_csv": str(local_csv),
        "triplet_target_csv": str(triplet_csv),
        "triplet_lines_csv": str(lines_csv),
        "comparison_csv": str(compare_csv),
        "json": str(json_path),
        "markdown": str(md_path),
    }


def _fmt(value: Any, prec: int = 8) -> str:
    if value is None or value == "":
        return ""
    try:
        v = float(value)
    except Exception:
        return str(value)
    if not math.isfinite(v):
        return ""
    return f"{v:.{prec}g}"


def _write_benchmark_md(comparison: XSTARBenchmarkComparison, path: Path) -> None:
    target = comparison.target
    local = target.local_state_row()
    triplet = target.triplet_row()
    comp = comparison.comparison_row()
    lines = [
        "# XSTAR local-output reproduction benchmark",
        "",
        "This file records the exact target values extracted from the same XSTAR run.  It is not a new solver-physics correction.",
        "",
        "## Local state from xout_abund1.fits",
        "",
        "| Ion | zone | T (K) | ne (cm^-3) | log xi | ion fraction |",
        "|---|---:|---:|---:|---:|---:|",
        f"| {local.get('ion','')} | {local.get('zone_index','')} | {_fmt(local.get('temperature_K'))} | {_fmt(local.get('electron_density_cm^-3'))} | {_fmt(local.get('log_xi'))} | {_fmt(local.get('ion_fraction'))} |",
        "",
        "## Triplet target from xout_lines1.fits",
        "",
        "| Ion | f | i | r | R=f/i | G=(f+i)/r | total | n lines |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
        f"| {triplet.get('ion','')} | {_fmt(triplet.get('xstar_f_fraction'))} | {_fmt(triplet.get('xstar_i_fraction'))} | {_fmt(triplet.get('xstar_r_fraction'))} | {_fmt(triplet.get('xstar_R_f_over_i'))} | {_fmt(triplet.get('xstar_G_f_plus_i_over_r'))} | {_fmt(triplet.get('xstar_triplet_total'))} | {triplet.get('n_triplet_lines','')} |",
        "",
        "## Solver comparison",
        "",
        "| status | solver f | solver i | solver r | Δf | Δi | Δr |",
        "|---|---:|---:|---:|---:|---:|---:|",
        f"| {comparison.status} | {_fmt(comp.get('solver_f_fraction'))} | {_fmt(comp.get('solver_i_fraction'))} | {_fmt(comp.get('solver_r_fraction'))} | {_fmt(comp.get('delta_f_solver_minus_xstar'))} | {_fmt(comp.get('delta_i_solver_minus_xstar'))} | {_fmt(comp.get('delta_r_solver_minus_xstar'))} |",
        "",
        "## Source files",
        "",
        f"- abundance/local state: `{target.xout_abund_path}`",
        f"- lines/triplet target: `{target.xout_lines_path}`",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_xstar_benchmark_suite(
    comparisons: Sequence[XSTARBenchmarkComparison],
    out_dir: str | Path,
    *,
    prefix: str = "xstar_local_reproduction_suite",
) -> dict[str, str]:
    """Write aggregate CSV/JSON/Markdown files for multiple benchmarks."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    local_rows = [c.target.local_state_row() for c in comparisons]
    triplet_rows = [c.target.triplet_row() for c in comparisons]
    comparison_rows = [c.comparison_row() for c in comparisons]
    local_csv = out / f"{prefix}_local_states.csv"
    triplet_csv = out / f"{prefix}_triplet_targets.csv"
    comparison_csv = out / f"{prefix}_comparisons.csv"
    json_path = out / f"{prefix}.json"
    md_path = out / f"{prefix}.md"
    write_csv(local_rows, local_csv)
    write_csv(triplet_rows, triplet_csv)
    write_csv(comparison_rows, comparison_csv)
    json_path.write_text(json.dumps([c.to_dict() for c in comparisons], indent=2, default=str) + "\n", encoding="utf-8")
    _write_suite_md(comparisons, md_path)
    return {
        "local_states_csv": str(local_csv),
        "triplet_targets_csv": str(triplet_csv),
        "comparisons_csv": str(comparison_csv),
        "json": str(json_path),
        "markdown": str(md_path),
    }


def _write_suite_md(comparisons: Sequence[XSTARBenchmarkComparison], path: Path) -> None:
    lines = [
        "# XSTAR local-output reproduction benchmark suite",
        "",
        "The XSTAR columns below are copied from same-run `xout_abund1.fits` and `xout_lines1.fits` targets.  Solver columns are present only when a solver comparison was requested or supplied.",
        "",
        "| Ion | T (K) | ne (cm^-3) | log xi | ion fraction | XSTAR f/i/r | solver f/i/r | Δf/Δi/Δr | status |",
        "|---|---:|---:|---:|---:|---|---|---|---|",
    ]
    for c in comparisons:
        row = c.comparison_row()
        target = f"{_fmt(row.get('xstar_f_fraction'))}/{_fmt(row.get('xstar_i_fraction'))}/{_fmt(row.get('xstar_r_fraction'))}"
        solver = f"{_fmt(row.get('solver_f_fraction'))}/{_fmt(row.get('solver_i_fraction'))}/{_fmt(row.get('solver_r_fraction'))}"
        delta = f"{_fmt(row.get('delta_f_solver_minus_xstar'))}/{_fmt(row.get('delta_i_solver_minus_xstar'))}/{_fmt(row.get('delta_r_solver_minus_xstar'))}"
        lines.append(
            f"| {row.get('ion','')} | {_fmt(row.get('temperature_K'))} | {_fmt(row.get('electron_density_cm^-3'))} | {_fmt(row.get('log_xi'))} | {_fmt(row.get('ion_fraction'))} | {target} | {solver} | {delta} | {c.status} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_xstar_benchmark_suite(
    cases: Sequence[Mapping[str, Any]],
    *,
    value_column: str = "emit_outward",
    run_solver: bool = False,
    db: Any = None,
    fitsfile: str | Path | None = None,
) -> list[XSTARBenchmarkComparison]:
    """Run :func:`reproduce_xstar_run` for a list of case dictionaries."""
    out: list[XSTARBenchmarkComparison] = []
    for case in cases:
        window = case.get("wavelength") or case.get("wavelength_window_A")
        if isinstance(window, str):
            parts = [float(x) for x in window.replace(",", " ").split()]
            window = (parts[0], parts[1]) if len(parts) >= 2 else None
        if isinstance(window, (list, tuple)) and len(window) >= 2:
            window = (float(window[0]), float(window[1]))
        else:
            window = None
        out.append(reproduce_xstar_run(
            case.get("run_dir") or case.get("xstar_run_dir"),
            ion=case.get("ion"),
            zone_index=int(case["zone_index"]) if case.get("zone_index") not in (None, "") else None,
            selection=str(case.get("selection", "max_fraction")),
            wavelength=window,
            value_column=str(case.get("value_column", value_column)),
            run_solver=run_solver,
            db=db,
            fitsfile=fitsfile,
        ))
    return out


def read_cases_csv(path: str | Path) -> list[dict[str, Any]]:
    """Read a simple cases CSV with at least ``ion`` and ``run_dir`` columns."""
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


__all__ = [
    "DEFAULT_HELIKE_WINDOWS_A",
    "XSTARLocalTarget",
    "XSTARBenchmarkComparison",
    "default_helike_wavelength_window",
    "find_xstar_run_files",
    "build_xstar_local_target",
    "compare_solver_to_xstar_target",
    "reproduce_xstar_run",
    "run_xstar_benchmark_suite",
    "read_cases_csv",
    "write_xstar_benchmark_outputs",
    "write_xstar_benchmark_suite",
]
