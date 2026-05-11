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
import tempfile

from .context import XSTARContext, context_from_xstar_run
from .workflow import TripletResult, calc_triplet, solve_populations
from .xstar_outputs import load_xstar_lines, read_xout_parameters, read_xout_spectra, write_csv

DEFAULT_HELIKE_WINDOWS_A: dict[str, tuple[float, float]] = {
    "C V": (40.0, 42.0),
    "O VII": (21.0, 23.0),
    "Mg XI": (9.0, 9.4),
    "Ca XIX": (3.0, 3.35),
}

DEFAULT_HELIKE_BENCHMARK_RUNS: tuple[tuple[str, str], ...] = (
    ("C V", "helike_type69/c5_ne1e8"),
    ("O VII", "helike_type69/o7_ne1e8"),
    ("Mg XI", "helike_type69/mg11_ne1e8"),
    ("Ca XIX", "helike_type69/ca19_xi3_ne1e8"),
)


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


def default_helike_benchmark_cases(
    xstar_runs_root: str | Path = "xstar_runs",
) -> list[dict[str, str]]:
    """Return the canonical C V / O VII / Mg XI / Ca XIX benchmark cases.

    The returned dictionaries can be passed directly to
    :func:`run_xstar_benchmark_suite` or written to a CSV file.  The directory
    layout matches the XSTAR run tree used throughout the He-like local-state
    validation sequence::

        xstar_runs/helike_type69/c5_ne1e8
        xstar_runs/helike_type69/o7_ne1e8
        xstar_runs/helike_type69/mg11_ne1e8
        xstar_runs/helike_type69/ca19_xi3_ne1e8
    """
    root = Path(xstar_runs_root)
    cases: list[dict[str, str]] = []
    for ion, rel in DEFAULT_HELIKE_BENCHMARK_RUNS:
        cases.append({"ion": ion, "run_dir": str(root / rel)})
    return cases


def write_default_helike_cases_csv(
    path: str | Path,
    *,
    xstar_runs_root: str | Path = "xstar_runs",
) -> Path:
    """Write the canonical four-ion benchmark case table.

    The CSV has the columns expected by ``examples/56_reproduce_xstar_local_outputs.py``:
    ``ion`` and ``run_dir``.
    """
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    cases = default_helike_benchmark_cases(xstar_runs_root=xstar_runs_root)
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["ion", "run_dir"])
        writer.writeheader()
        writer.writerows(cases)
    return out


def find_xstar_run_files(
    run_dir: str | Path,
    *,
    xout_abund_filename: str | None = None,
    xout_lines_filename: str | None = None,
    xout_cont_filename: str | None = None,
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
    cont_candidates = []
    if xout_cont_filename:
        cont_candidates.append(run_path / xout_cont_filename)
    cont_candidates.extend([run_path / "xout_cont1.fits", run_path / "xout_spect1.fits"])
    abund = next((p for p in abund_candidates if p.exists()), None)
    lines = next((p for p in line_candidates if p.exists()), None)
    cont = next((p for p in cont_candidates if p.exists()), None)
    return {"xout_abund": abund, "xout_lines": lines, "xout_cont": cont}


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except Exception:
        return None
    return out if math.isfinite(out) else None


def _parameter_value_from_xout(path: str | Path | None, *names: str) -> float | None:
    """Return a numeric XSTAR run parameter from a FITS PARAMETERS table.

    XSTAR writes input parameters via ``fparmlist.f90`` to a ``PARAMETERS``
    extension with columns ``parameter`` and ``value``.  This helper is used
    for source-code matched quantities such as ``cfrac``.  It is deliberately
    tolerant of capitalization, spaces, underscores and hyphens.
    """
    if not path:
        return None
    wanted = {str(n).strip().lower().replace("_", "").replace("-", "").replace(" ", "") for n in names if str(n).strip()}
    if not wanted:
        return None
    try:
        rows = read_xout_parameters(path)
    except Exception:
        return None
    for row in rows or []:
        key = str(row.get("parameter") or row.get("name") or row.get("parname") or "").strip()
        key_norm = key.lower().replace("_", "").replace("-", "").replace(" ", "")
        if key_norm in wanted:
            val = _as_float(row.get("value") or row.get("parval") or row.get("val"))
            if val is not None:
                return val
    return None


def _xstar_cfrac_from_target(target: "XSTARLocalTarget" | None) -> tuple[float | None, str]:
    """Return ``(cfrac, provenance)`` from same-run XSTAR output.

    ``ucalc.f90`` multiplies type-50 line pumping by ``max(0,1-cfrac)``.
    The previous v0.3.144--v0.3.146 benchmark preset hard-coded ``cfrac=0``
    and therefore forced maximum pumping even for runs whose XSTAR input used
    another value.  Source matching requires using the run parameter when it is
    available.
    """
    if target is None:
        return None, "no_target"
    for path in (target.xout_abund_path, target.xout_lines_path, target.xout_cont_path):
        val = _parameter_value_from_xout(path, "cfrac", "covering fraction", "covering_fraction", "coveringfrac")
        if val is not None:
            # Clamp only to the physically meaningful range used by max(0,1-cfrac).
            val = max(0.0, min(1.0, float(val)))
            return val, f"xstar_parameters:{Path(path).name}"
    return None, "not_found_in_xstar_parameters"


def _difference(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    return float(a) - float(b)


def _ratio(num: float | None, den: float | None) -> float | None:
    if num is None or den in (None, 0.0):
        return None
    try:
        out = float(num) / float(den)
    except Exception:
        return None
    return out if math.isfinite(out) else None


def _triplet_metrics_from_fir(f: float | None, i: float | None, r: float | None) -> dict[str, float | None]:
    """Return R=f/i, G=(f+i)/r and normalized total for f/i/r fractions."""
    total = None
    if f is not None and i is not None and r is not None:
        total = float(f) + float(i) + float(r)
    return {
        "R_f_over_i": _ratio(f, i),
        "G_f_plus_i_over_r": _ratio((float(f) + float(i)) if f is not None and i is not None else None, r),
        "fraction_sum": total,
    }


def _l2_to_target(sf: float | None, si: float | None, sr: float | None, tf: float | None, ti: float | None, tr: float | None) -> float | None:
    vals = (sf, si, sr, tf, ti, tr)
    if any(v is None for v in vals):
        return None
    try:
        out = math.sqrt((float(sf) - float(tf)) ** 2 + (float(si) - float(ti)) ** 2 + (float(sr) - float(tr)) ** 2)
    except Exception:
        return None
    return out if math.isfinite(out) else None


def _normalized_triplet_mapping(triplet: Mapping[str, Any] | None) -> dict[str, Any]:
    """Normalize f/i/r, R, G and L2-like keys from several solver layouts."""
    if not triplet:
        return {}
    src = dict(triplet)
    f = _as_float(src.get("f_fraction") or src.get("f") or src.get("solver_f"))
    i = _as_float(src.get("i_fraction") or src.get("i") or src.get("solver_i"))
    r = _as_float(src.get("r_fraction") or src.get("r") or src.get("solver_r"))
    metrics = _triplet_metrics_from_fir(f, i, r)
    R = _as_float(src.get("R") or src.get("R_f_over_i") or src.get("solver_R_f_over_i"))
    G = _as_float(src.get("G") or src.get("G_f_plus_i_over_r") or src.get("solver_G_f_plus_i_over_r"))
    l2 = _as_float(src.get("l2_distance_to_target") or src.get("L2") or src.get("solver_l2_distance_to_target"))
    out = dict(src)
    out.update({
        "f_fraction": f,
        "i_fraction": i,
        "r_fraction": r,
        "R_f_over_i": R if R is not None else metrics["R_f_over_i"],
        "G_f_plus_i_over_r": G if G is not None else metrics["G_f_plus_i_over_r"],
        "fraction_sum": metrics["fraction_sum"],
    })
    if l2 is not None:
        out["l2_distance_to_target"] = l2
    return out


def _has_triplet_fractions(triplet: Mapping[str, Any] | None) -> bool:
    """Return True when a mapping contains finite f/i/r triplet fractions."""
    norm = _normalized_triplet_mapping(triplet)
    return all(_as_float(norm.get(f"{comp}_fraction")) is not None for comp in ("f", "i", "r"))


def _comparison_row_triplet(row: Mapping[str, Any], *, source_label: str) -> dict[str, Any]:
    """Normalize a full-global comparison summary row into a triplet mapping."""
    out = _normalized_triplet_mapping(row)
    out["solver_triplet_source"] = source_label
    if row.get("comparison_case"):
        out["comparison_case"] = row.get("comparison_case")
    if row.get("solve_status"):
        out["solve_status"] = row.get("solve_status")
    return out


def _summary_triplet_candidates(result: Mapping[str, Any], summary: Mapping[str, Any]) -> list[tuple[str, Mapping[str, Any]]]:
    """Return solver triplet candidates in source-code-preference order.

    The first v0.3.134--v0.3.138 benchmark implementation extracted
    ``summary["he_like_triplet"]``.  That is a quick convenience summary from
    the current He-like ion line rows, not the source-code-first local-state
    validation path used in examples 51--52.  Prefer XSTAR-style full-global and
    ``calc_emis_ion`` postprocess summaries when they are present, and use the
    convenience summary only as a final fallback.
    """
    candidates: list[tuple[str, Mapping[str, Any]]] = []
    fgn = result.get("full_global_normalized_solve_comparison")
    if isinstance(fgn, Sequence) and not isinstance(fgn, (str, bytes)):
        # Match the historical local-state validation workflow generated by
        # examples/51_run_helike_local_state_validation.py and compared by
        # examples/52_summarize_helike_local_state_comparison.py.  Those
        # benchmarks used the full-global ``xstar_tau0_calc_emis_ion`` branch
        # as the primary solver/XSTAR comparison.  The reference-depth
        # postprocess branch is still useful, and was essential for the earlier
        # O VII depth-scale diagnostic, but preferring it here silently changed
        # the C/O/Mg/Ca local-state benchmark after the API reorganization.
        preferred_cases = (
            "full_global_xstar_tau0_calc_emis_ion",
            "full_global_xstar_reference_depth_emit_outward_calc_emis_ion",
            "full_global_xstar_continuum_alias_superlevels",
            "full_global_type71_type99_type53_phint53",
        )
        rows = [r for r in fgn if isinstance(r, Mapping) and str(r.get("row_kind", "")).lower() == "summary"]
        for case in preferred_cases:
            for row in rows:
                if str(row.get("comparison_case", "")) == case and _has_triplet_fractions(row):
                    candidates.append((f"full_global_normalized_solve_comparison:{case}", _comparison_row_triplet(row, source_label=f"full_global:{case}")))
        for row in rows:
            if _has_triplet_fractions(row):
                case = str(row.get("comparison_case", "summary"))
                candidates.append((f"full_global_normalized_solve_comparison:{case}", _comparison_row_triplet(row, source_label=f"full_global:{case}")))
    ce_summary = summary.get("calc_emis_ion_triplet_emergent_summary") if isinstance(summary, Mapping) else None
    if isinstance(ce_summary, Mapping):
        for key in (
            "xstar_reference_depth_emit_outward_calc_emis_ion",
            "xstar_tau0_calc_emis_ion",
            "transparent_tau0_calc_emis_ion",
            "raw_pop_A_E",
        ):
            cand = ce_summary.get(key)
            if isinstance(cand, Mapping) and _has_triplet_fractions(cand):
                candidates.append((f"calc_emis_ion_triplet_emergent_summary:{key}", _comparison_row_triplet(cand, source_label=f"calc_emis_ion:{key}")))
    direct = [
        ("result.triplet", result.get("triplet")),
        ("result.triplet_summary", result.get("triplet_summary")),
        ("result.xstar_like_element_solver_triplet", result.get("xstar_like_element_solver_triplet")),
        ("summary.he_like_triplet", summary.get("he_like_triplet") if isinstance(summary, Mapping) else None),
        ("summary.calc_emis_ion_triplet_emergent_summary", summary.get("calc_emis_ion_triplet_emergent_summary") if isinstance(summary, Mapping) else None),
        ("summary.calc_emis_triplet_audit_summary", summary.get("calc_emis_triplet_audit_summary") if isinstance(summary, Mapping) else None),
        ("summary.triplet_emissivity_branch_audit_summary", summary.get("triplet_emissivity_branch_audit_summary") if isinstance(summary, Mapping) else None),
    ]
    for label, cand in direct:
        if isinstance(cand, Mapping) and _has_triplet_fractions(cand):
            c = _normalized_triplet_mapping(cand)
            c.setdefault("solver_triplet_source", label)
            candidates.append((label, c))
    return candidates


def _extract_solver_triplet_from_result(result: Any) -> tuple[Mapping[str, Any], Mapping[str, Any], tuple[str, ...]]:
    """Extract the best available normalized solver triplet.

    This function now records the provenance of the extracted solver triplet.
    In particular, it avoids silently using the quick ``summary.he_like_triplet``
    when an XSTAR-like full-global comparison or calc_emis_ion postprocess
    triplet is available.
    """
    if not isinstance(result, Mapping):
        return {}, {}, ("solver_returned_non_mapping_result",)
    summary = result.get("summary", result) if isinstance(result.get("summary", result), Mapping) else {}
    candidates = _summary_triplet_candidates(result, summary)
    if candidates:
        label, cand = candidates[0]
        out = dict(cand)
        out.setdefault("solver_triplet_source", label)
        warnings = []
        if label == "summary.he_like_triplet":
            warnings.append("solver_triplet_from_quick_summary_not_full_xstar_validation_path")
        return out, dict(summary), tuple(warnings)
    return {}, dict(summary), ("solver_returned_no_finite_triplet_fractions",)


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
    xout_cont_path: str | None = None
    xstar_cfrac: float | None = None
    xstar_cfrac_source: str = ""
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
            "xstar_cfrac": self.xstar_cfrac,
            "xstar_cfrac_source": self.xstar_cfrac_source,
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
            "xout_cont_path": self.xout_cont_path,
            "xstar_cfrac": self.xstar_cfrac,
            "xstar_cfrac_source": self.xstar_cfrac_source,
            "wavelength_window_A": list(self.wavelength_window_A) if self.wavelength_window_A else None,
            "value_column": self.value_column,
            "local_state": self.local_state_row(),
            "triplet": self.triplet_row(),
            "context": self.context.to_dict(),
            "line_rows": [dict(r) for r in self.line_rows],
            "status": self.status,
            "warnings": list(self.warnings),
        }


def _xstar_pescl_escape_probability(tau: object) -> float | None:
    """Return XSTAR ``pescl`` for a line optical depth.

    This mirrors ``xstarlib/src/pescl.f90`` sufficiently for benchmark
    diagnosis: the function returns the directional escape probability, i.e.
    it includes the final division by two used by XSTAR.
    """
    val = _as_float(tau)
    if val is None:
        return None
    tau_f = max(0.0, float(val))
    if tau_f < 1.0e-5:
        return 0.5
    if tau_f < 1.0:
        aa = 2.0 * tau_f
        return ((1.0 - math.exp(-aa)) / aa) / 2.0
    tauw = 1.0e5
    bb = 0.5 * math.sqrt(max(math.log(tau_f), 0.0)) / (1.0 + tau_f / tauw)
    return (1.0 / (tau_f * math.sqrt(math.pi) * (1.2 + bb))) / 2.0


def _xstar_reference_resonance_escape_diagnostics(target: XSTARLocalTarget) -> dict[str, Any]:
    """Return same-run XSTAR resonance-line depth and escape diagnostics."""
    r_rows = [dict(r) for r in target.line_rows if str(r.get('triplet_component') or '').lower() == 'r']
    if not r_rows:
        return {
            'xstar_reference_resonance_depth_inward': None,
            'xstar_reference_resonance_depth_outward': None,
            'xstar_reference_resonance_ptmp1_cfrac0': None,
            'xstar_reference_resonance_ptmp2_cfrac0': None,
            'xstar_reference_resonance_ptmp_sum_cfrac0': None,
            'xstar_reference_resonance_escape_vs_scalar_0p35': None,
            'xstar_reference_resonance_escape_diagnosis': 'no_resonance_reference_line_row',
        }
    r_rows.sort(key=lambda r: _as_float(r.get(str(target.value_column))) or 0.0, reverse=True)
    row = r_rows[0]
    tau1 = max(0.0, float(_as_float(row.get('depth_inward')) or 0.0))
    tau2 = max(0.0, float(_as_float(row.get('depth_outward')) or 0.0))
    p1 = _xstar_pescl_escape_probability(tau1)
    p2 = _xstar_pescl_escape_probability(tau2)
    psum = (p1 or 0.0) + (p2 or 0.0)
    ratio = psum / 0.35 if psum is not None and 0.35 > 0.0 else None
    if ratio is None:
        diag = 'missing_reference_escape'
    elif ratio > 1.5:
        diag = 'same_run_depth_escape_much_larger_than_scalar_0p35_proxy'
    elif ratio < 0.67:
        diag = 'same_run_depth_escape_smaller_than_scalar_0p35_proxy'
    else:
        diag = 'same_run_depth_escape_comparable_to_scalar_0p35_proxy'
    return {
        'xstar_reference_resonance_depth_inward': tau1,
        'xstar_reference_resonance_depth_outward': tau2,
        'xstar_reference_resonance_ptmp1_cfrac0': p1,
        'xstar_reference_resonance_ptmp2_cfrac0': p2,
        'xstar_reference_resonance_ptmp_sum_cfrac0': psum,
        'xstar_reference_resonance_escape_vs_scalar_0p35': ratio,
        'xstar_reference_resonance_escape_diagnosis': diag,
        'xstar_reference_resonance_escape_formula': 'pescl(depth_inward)+pescl(depth_outward), assuming cfrac=0 for diagnosis',
    }


def _safe_ratio(num: object, den: object) -> float | None:
    n = _as_float(num)
    d = _as_float(den)
    if n is None or d is None or abs(d) <= 0.0:
        return None
    return n / d


def _triplet_residual_pattern(df: object, di: object, dr: object) -> str:
    f = _as_float(df)
    i = _as_float(di)
    r = _as_float(dr)
    if f is None or i is None or r is None:
        return 'target_only_or_missing_solver_triplet'
    tol = 1.0e-6
    if f > tol and r < -tol:
        if i < -tol:
            return 'solver_f_high_i_low_r_low'
        if i > tol:
            return 'solver_f_high_i_high_r_low'
        return 'solver_f_high_r_low'
    if r > tol and f < -tol:
        return 'solver_r_high_f_low'
    if abs(f) <= tol and abs(i) <= tol and abs(r) <= tol:
        return 'solver_matches_triplet_fractions_within_tolerance'
    return 'mixed_triplet_residuals'


def _source_code_gap_diagnosis(
    *,
    pattern: str,
    solver_summary: Mapping[str, Any] | None,
    resonance_escape_diag: Mapping[str, Any],
) -> dict[str, Any]:
    """Return source-code-first diagnosis for the current He-like residuals."""
    summ = solver_summary or {}
    treatment = str(summ.get('type50_bound_bound_treatment') or '')
    escape_factor = summ.get('type50_escape_factor')
    escape_source = str(summ.get('type50_escape_source') or '')
    pumping_scale = summ.get('type50_photoexcitation_scale')
    radiation_mode = str(summ.get('radiation_field_mode') or '')
    bremsa_scale = summ.get('radiation_bremsa_scale')
    escape_diag = str(resonance_escape_diag.get('xstar_reference_resonance_escape_diagnosis') or '')
    issues: list[str] = []
    if pattern.startswith('solver_f_high') and 'r_low' in pattern:
        issues.append('common residual is high forbidden fraction and low resonance fraction')
    if treatment == 'xstar-line-escape-and-pumping':
        cf = _as_float(summ.get('type50_cfrac'))
        if cf is not None and cf >= 1.0:
            issues.append('type-50 photoexcitation branch is enabled but XSTAR cfrac suppresses pumping via max(0,1-cfrac)')
        else:
            issues.append('type-50 lower-to-upper photoexcitation is enabled in the population matrix')
    elif str(pumping_scale) in {'0', '0.0', ''}:
        issues.append('type-50 lower-to-upper photoexcitation is not injected into the population matrix')
    if 'larger_than_scalar_0p35' in escape_diag and escape_source not in {'xstar-reference-lines', 'same-run-xout-lines', 'xout-lines', 'reference-lines'}:
        issues.append('same-run XSTAR resonance depth implies larger escape probability than scalar 0.35 proxy')
    if escape_source in {'xstar-reference-lines', 'same-run-xout-lines', 'xout-lines', 'reference-lines'}:
        issues.append('population matrix uses same-run xout_lines1 depths for matching type-50 lines')
    if radiation_mode == 'xstar-output':
        issues.append('solver radiation field uses same-run xout_cont1/xout_spect1 spectrum converted to bremsa-like grid')
    elif radiation_mode and radiation_mode != 'xstar-run-bremsa':
        issues.append('solver radiation field is a proxy rather than the same-run XSTAR bremsa(nb1) field')
    if not issues:
        issues.append('no single source-code gap identified by lightweight benchmark diagnosis')
    return {
        'solver_type50_bound_bound_treatment': treatment,
        'solver_type50_escape_factor': escape_factor,
        'solver_type50_escape_source': summ.get('type50_escape_source'),
        'solver_type50_photoexcitation_scale': pumping_scale,
        'solver_type50_cfrac': summ.get('type50_cfrac'),
        'solver_type50_cfrac_source': summ.get('type50_cfrac_source'),
        'solver_radiation_field_mode': radiation_mode,
        'solver_radiation_bremsa_scale': bremsa_scale,
        'solver_xstar_radiation_spectrum_csv': summ.get('xstar_radiation_spectrum_csv'),
        'solver_xstar_radiation_column': summ.get('xstar_radiation_column'),
        'solver_xstar_radiation_grid_status': summ.get('xstar_radiation_grid_status'),
        'solver_n_xstar_radiation_grid_points': summ.get('n_xstar_radiation_grid_points'),
        'source_code_gap_diagnosis': '; '.join(issues),
        'source_code_next_action': 'verify same-run local bremsa normalization and cfrac against XSTAR prints; compare injected type-50 pumping matrix terms against ucalc.f90 term-by-term',
        'source_code_paths_to_check': 'calc_hmc_ion.f90 rate assembly; ucalc.f90 type-50; calc_emis_ion.f90 line output; pescl.f90 escape probability',
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
        solver = _normalized_triplet_mapping(self.solver_triplet)
        sf = _as_float(solver.get("f_fraction"))
        si = _as_float(solver.get("i_fraction"))
        sr = _as_float(solver.get("r_fraction"))
        sR = _as_float(solver.get("R_f_over_i"))
        sG = _as_float(solver.get("G_f_plus_i_over_r"))
        xl2 = 0.0 if all(_as_float(getattr(self.target.triplet, comp)) is not None for comp in ("f", "i", "r")) else None
        sl2 = _l2_to_target(sf, si, sr, self.target.triplet.f, self.target.triplet.i, self.target.triplet.r)
        df = _difference(sf, self.target.triplet.f)
        di = _difference(si, self.target.triplet.i)
        dr = _difference(sr, self.target.triplet.r)
        dR = _difference(sR, self.target.triplet.R_f_over_i)
        dG = _difference(sG, self.target.triplet.G_f_plus_i_over_r)
        pattern = _triplet_residual_pattern(df, di, dr)
        escape_diag = _xstar_reference_resonance_escape_diagnostics(self.target)
        source_diag = _source_code_gap_diagnosis(
            pattern=pattern,
            solver_summary=self.solver_summary,
            resonance_escape_diag=escape_diag,
        )
        row.update({
            "xstar_L2_to_xstar": xl2,
            "solver_f_fraction": sf,
            "solver_i_fraction": si,
            "solver_r_fraction": sr,
            "solver_R_f_over_i": sR,
            "solver_G_f_plus_i_over_r": sG,
            "solver_fraction_sum": _as_float(solver.get("fraction_sum")),
            "solver_l2_distance_to_target_reported": _as_float(solver.get("l2_distance_to_target")),
            "solver_L2_to_xstar": sl2,
            "solver_triplet_source": solver.get("solver_triplet_source") or solver.get("comparison_case") or "",
            "solver_to_xstar_f_ratio": _safe_ratio(sf, self.target.triplet.f),
            "solver_to_xstar_i_ratio": _safe_ratio(si, self.target.triplet.i),
            "solver_to_xstar_r_ratio": _safe_ratio(sr, self.target.triplet.r),
            "solver_to_xstar_R_ratio": _safe_ratio(sR, self.target.triplet.R_f_over_i),
            "solver_to_xstar_G_ratio": _safe_ratio(sG, self.target.triplet.G_f_plus_i_over_r),
            "delta_f_solver_minus_xstar": df,
            "delta_i_solver_minus_xstar": di,
            "delta_r_solver_minus_xstar": dr,
            "delta_R_solver_minus_xstar": dR,
            "delta_G_solver_minus_xstar": dG,
            "triplet_residual_pattern": pattern,
            "comparison_status": self.status,
            "comparison_warnings": "; ".join(self.warnings),
        })
        row.update(escape_diag)
        row.update(source_diag)
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
    xout_cont_filename: str | None = None,
) -> XSTARLocalTarget:
    """Extract the exact local-state and triplet target from one XSTAR run.

    This function is the benchmark anchor for C V, O VII, Mg XI, and Ca XIX. It
    reads ``xout_abund1.fits`` for the local ``T``, ``ne``, ``log xi`` and ion
    fraction, and reads ``xout_lines1.fits`` for the triplet line values.  The
    returned target is the reference against which any future solver correction
    must be compared.
    """
    run_path = Path(run_dir)
    files = find_xstar_run_files(run_path, xout_abund_filename=xout_abund_filename, xout_lines_filename=xout_lines_filename, xout_cont_filename=xout_cont_filename)
    abund_path = files["xout_abund"]
    lines_path = files["xout_lines"]
    cont_path = files.get("xout_cont")
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
    cfrac_val, cfrac_source = _xstar_cfrac_from_target(XSTARLocalTarget(
        ion=_ion_label(ion) or ion,
        run_dir=str(run_path),
        context=ctx,
        triplet=triplet,
        line_rows=tuple(dict(r) for r in triplet.lines),
        xout_abund_path=str(abund_path),
        xout_lines_path=str(lines_path),
        xout_cont_path=str(cont_path) if cont_path is not None else None,
        wavelength_window_A=window,
        value_column=value_column,
        status="ok" if triplet.status == "ok" else "target_incomplete",
        warnings=tuple(warnings),
    ))
    if cfrac_val is None:
        warnings.append("xstar_cfrac_not_found_in_PARAMETERS; source-matched type-50 pumping should not assume cfrac=0")
    return XSTARLocalTarget(
        ion=_ion_label(ion) or ion,
        run_dir=str(run_path),
        context=ctx,
        triplet=triplet,
        line_rows=tuple(dict(r) for r in triplet.lines),
        xout_abund_path=str(abund_path),
        xout_lines_path=str(lines_path),
        xout_cont_path=str(cont_path) if cont_path is not None else None,
        xstar_cfrac=cfrac_val,
        xstar_cfrac_source=cfrac_source,
        wavelength_window_A=window,
        value_column=value_column,
        status="ok" if triplet.status == "ok" else "target_incomplete",
        warnings=tuple(warnings),
    )






def _is_fits_path(path: object) -> bool:
    """Return True when *path* looks like a FITS file rather than CSV."""
    if path is None:
        return False
    text = str(path).strip().lower()
    return text.endswith((".fits", ".fit", ".fts", ".fits.gz", ".fit.gz", ".fts.gz"))


def _write_solver_reference_lines_csv(target: "XSTARLocalTarget") -> Path | None:
    """Write the target's selected XSTAR line rows to a temporary CSV.

    ``solve_element_reference`` expects ``xstar_reference_lines_csv`` to be a
    converted CSV table, not the binary/ascii FITS table itself.  The benchmark
    target is built from ``xout_lines1.fits`` via :func:`load_xstar_lines`, so
    we already have the needed rows in memory.  This helper writes those rows to
    a temporary CSV and returns the path for the duration of the solver call.
    """
    rows = [dict(r) for r in (target.line_rows or ())]
    if not rows:
        return None
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        suffix="_xstar_reference_lines.csv",
        prefix="xstar_atomic_",
        delete=False,
        newline="",
        encoding="utf-8",
    )
    path = Path(handle.name)
    handle.close()
    write_csv(rows, path)
    return path


def _write_solver_radiation_spectrum_csv(target: "XSTARLocalTarget") -> Path | None:
    """Write the same-run XSTAR continuum spectrum to a temporary CSV."""
    if not target.xout_cont_path:
        return None
    try:
        rows = read_xout_spectra(target.xout_cont_path)
    except Exception:
        return None
    if not rows:
        return None
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        suffix="_xstar_radiation_spectrum.csv",
        prefix="xstar_atomic_",
        delete=False,
        newline="",
        encoding="utf-8",
    )
    path = Path(handle.name)
    handle.close()
    write_csv(rows, path)
    return path

def xstar_local_state_solver_kwargs(target: XSTARLocalTarget | None = None) -> dict[str, Any]:
    """Return the source-code-first local-state validation solver settings.

    These settings mirror the generated commands from
    ``examples/51_run_helike_local_state_validation.py``.  They are not a new
    physics correction; they make the benchmark use the same mature diagnostic
    path that previously produced the all-ion local-state comparisons, instead
    of the much lighter convenience defaults used by ``solve_populations``.
    """
    window = target.wavelength_window_A if target is not None else None
    out: dict[str, Any] = {
        "max_level": 80,
        "adjacent_coupling_mode": "recombination-source",
        "adjacent_coupling_source_mode": "record-destination",
        "index_cache": True,
        "type57_energy_convention": "abs-rlev4",
        "triplet_source_mode": "type74-direct-diagnostic",
        "type99_proxy_scale": "0,1e-8,1e-6,1e-4,1e-2,1,1e2",
        # Historical local-state validation preset.  This intentionally mirrors
        # examples/51--52 and does not force post-processed xout_lines1 depths
        # or xout_cont1 spectra into the population matrix.  XSTAR's calc_hmc_ion
        # uses the live zone-local tau0(:,:) and bremsa(:) arrays, not the final
        # line/spectrum tables written after transfer.
        "radiation_field_mode": "xstar-powerlaw",
        "radiation_bremsa_scale": 1.0e18,
        "radiation_powerlaw_index": 1.0,
        "radiation_n_energy_grid": 512,
        "type53_flat_proxy_scale": 1.0,
        "type53_phint53_scale": "1,1e5,1e10,1e15,1e18,1e20",
        "inverse_recombination_mode": "xstar-ucalc",
        "ion_fraction_closure": "xstar-calc-ion-rates",
        "full_global_linear_solver": "xstar-lucy",
        "full_global_topology": "xstar-continuum-alias-superlevels",
        "type50_bound_bound_treatment": "xstar-line-escape",
        "type50_escape_factor": 0.35,
        "type50_escape_source": "matrix-row",
        "type50_cfrac": target.xstar_cfrac if (target is not None and target.xstar_cfrac is not None) else 1.0,
    }
    if window:
        out["wavelength_min"] = float(window[0])
        out["wavelength_max"] = float(window[1])
    if target is not None and target.xout_lines_path:
        out["xstar_reference_lines_csv"] = target.xout_lines_path
        out["xstar_reference_value_column"] = target.value_column
    return out


def xstar_local_state_experimental_pumping_solver_kwargs(target: XSTARLocalTarget | None = None) -> dict[str, Any]:
    """Return the experimental v0.3.144--0.3.147 type-50 pumping preset.

    This preset is intentionally separate from ``xstar-local-state`` because
    XSTAR's live ``bremsa(nb1)`` and ``tau0`` arrays are not available in the
    standard output FITS tables.  It can be used for audits, but it is not the
    source-code-parity benchmark.
    """
    out = xstar_local_state_solver_kwargs(target)
    out.update({
        "radiation_field_mode": "xstar-output" if (target is not None and target.xout_cont_path) else "none",
        "radiation_bremsa_scale": 1.0,
        "type50_bound_bound_treatment": "xstar-line-escape-and-pumping",
        "type50_escape_source": "unsafe-xout-lines-depths",
        "type50_cfrac": target.xstar_cfrac if (target is not None and target.xstar_cfrac is not None) else 1.0,
    })
    if target is not None and target.xout_cont_path:
        out["xstar_radiation_spectrum_csv"] = target.xout_cont_path
        out["xstar_radiation_column"] = "transmitted"
        out["xstar_radiation_radius_cm"] = target.context.plasma.radius_cm
    return out


def solver_kwargs_from_preset(preset: str | None, target: XSTARLocalTarget | None = None) -> dict[str, Any]:
    """Resolve named benchmark solver presets."""
    key = str(preset or "workflow-default").strip().lower().replace("_", "-")
    if key in {"", "none", "workflow", "workflow-default", "quick", "current"}:
        return {}
    if key in {"xstar-local-state", "local-state", "validation", "v03124", "v03123", "source-code-first"}:
        return xstar_local_state_solver_kwargs(target)
    if key in {"xstar-local-state-experimental-pumping", "experimental-pumping", "xstar-output-pumping"}:
        return xstar_local_state_experimental_pumping_solver_kwargs(target)
    raise ValueError(f"Unknown solver preset {preset!r}; use workflow-default, xstar-local-state, or xstar-local-state-experimental-pumping")

def compare_solver_to_xstar_target(
    target: XSTARLocalTarget,
    *,
    db: Any = None,
    fitsfile: str | Path | None = None,
    run_solver: bool = False,
    solver_triplet: Mapping[str, Any] | None = None,
    solver_kwargs: Mapping[str, Any] | None = None,
    solver_preset: str | None = None,
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
            # Accept --atdb, XSTAR_ATDB_FITS, XSTAR_ATDB, or configured datapath.
            # A blank shell expansion such as --atdb "$XSTAR_ATDB" with an
            # unset variable is treated as not provided, instead of becoming
            # ./atdb.fits.  The database resolver inside solve_populations then
            # handles environment/datapath lookup.
            solver_fitsfile = fitsfile if str(fitsfile or "").strip() else None
            preset_kwargs = solver_kwargs_from_preset(solver_preset, target)
            merged_kwargs = {**preset_kwargs, **dict(solver_kwargs or {})}
            temporary_reference_csv: Path | None = None
            temporary_radiation_csv: Path | None = None
            try:
                # The xstar-local-state preset mirrors examples/51, where
                # xout_lines1.fits is first converted to CSV before it is used
                # by the full-global solver.  Passing the FITS file directly to
                # solve_element_reference causes a UnicodeDecodeError because
                # that lower-level reader intentionally expects CSV.  Keep the
                # benchmark self-contained by writing the already-loaded target
                # line rows to a temporary CSV when needed.
                if _is_fits_path(merged_kwargs.get("xstar_reference_lines_csv")):
                    temporary_reference_csv = _write_solver_reference_lines_csv(target)
                    if temporary_reference_csv is not None:
                        merged_kwargs["xstar_reference_lines_csv"] = str(temporary_reference_csv)
                        warnings.append("converted_xout_lines_fits_to_temporary_solver_reference_csv")
                    else:
                        merged_kwargs.pop("xstar_reference_lines_csv", None)
                        warnings.append("xout_lines_fits_not_passed_to_solver_no_reference_rows")

                if _is_fits_path(merged_kwargs.get("xstar_radiation_spectrum_csv")):
                    temporary_radiation_csv = _write_solver_radiation_spectrum_csv(target)
                    if temporary_radiation_csv is not None:
                        merged_kwargs["xstar_radiation_spectrum_csv"] = str(temporary_radiation_csv)
                        warnings.append("converted_xout_cont_fits_to_temporary_solver_radiation_csv")
                    else:
                        merged_kwargs.pop("xstar_radiation_spectrum_csv", None)
                        merged_kwargs["radiation_field_mode"] = "none"
                        warnings.append("xout_cont_fits_not_passed_to_solver_no_radiation_rows")
                result = solve_populations(target.ion, context=target.context, db=db, fitsfile=solver_fitsfile, **merged_kwargs)
            finally:
                if temporary_reference_csv is not None:
                    try:
                        temporary_reference_csv.unlink()
                    except FileNotFoundError:
                        pass
                if temporary_radiation_csv is not None:
                    try:
                        temporary_radiation_csv.unlink()
                    except FileNotFoundError:
                        pass
            triplet, summary, extract_warnings = _extract_solver_triplet_from_result(result)
            if isinstance(summary, Mapping):
                summary = dict(summary)
                summary.setdefault("type50_cfrac", merged_kwargs.get("type50_cfrac"))
                summary.setdefault("type50_cfrac_source", target.xstar_cfrac_source or "fallback_1p0_when_unavailable")
            warnings.extend(extract_warnings)
            status = "solver_compared" if _has_triplet_fractions(triplet) else "solver_no_triplet_values"
        except Exception as exc:  # pragma: no cover - exercised with real ATDB runs
            warnings.append(f"solver_failed: {exc}")
            status = "solver_failed"
    elif solver_triplet is not None:
        status = "solver_compared" if _has_triplet_fractions(solver_triplet) else "solver_no_triplet_values"
        if status != "solver_compared":
            warnings.append("solver_triplet_has_no_finite_triplet_fractions")
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
    solver_preset: str | None = None,
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
        solver_preset=solver_preset,
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
        "| status | source | solver f/i/r | solver R | solver G | solver L2 | Δf/Δi/Δr | ΔR | ΔG |",
        "|---|---|---|---:|---:|---:|---|---:|---:|",
        f"| {comparison.status} | {comp.get('solver_triplet_source','')} | {_fmt(comp.get('solver_f_fraction'))}/{_fmt(comp.get('solver_i_fraction'))}/{_fmt(comp.get('solver_r_fraction'))} | {_fmt(comp.get('solver_R_f_over_i'))} | {_fmt(comp.get('solver_G_f_plus_i_over_r'))} | {_fmt(comp.get('solver_L2_to_xstar'))} | {_fmt(comp.get('delta_f_solver_minus_xstar'))}/{_fmt(comp.get('delta_i_solver_minus_xstar'))}/{_fmt(comp.get('delta_r_solver_minus_xstar'))} | {_fmt(comp.get('delta_R_solver_minus_xstar'))} | {_fmt(comp.get('delta_G_solver_minus_xstar'))} |",
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
        "| Ion | T (K) | ne (cm^-3) | log xi | ion fraction | XSTAR f/i/r | XSTAR R/G/L2 | solver f/i/r | solver R/G/L2 | Δf/Δi/Δr | ΔR/ΔG | residual pattern | source-code diagnosis | source | status |",
        "|---|---:|---:|---:|---:|---|---|---|---|---|---|---|---|---|---|",
    ]
    for c in comparisons:
        row = c.comparison_row()
        target = f"{_fmt(row.get('xstar_f_fraction'))}/{_fmt(row.get('xstar_i_fraction'))}/{_fmt(row.get('xstar_r_fraction'))}"
        target_diag = f"{_fmt(row.get('xstar_R_f_over_i'))}/{_fmt(row.get('xstar_G_f_plus_i_over_r'))}/{_fmt(row.get('xstar_L2_to_xstar'))}"
        solver = f"{_fmt(row.get('solver_f_fraction'))}/{_fmt(row.get('solver_i_fraction'))}/{_fmt(row.get('solver_r_fraction'))}"
        solver_diag = f"{_fmt(row.get('solver_R_f_over_i'))}/{_fmt(row.get('solver_G_f_plus_i_over_r'))}/{_fmt(row.get('solver_L2_to_xstar'))}"
        delta = f"{_fmt(row.get('delta_f_solver_minus_xstar'))}/{_fmt(row.get('delta_i_solver_minus_xstar'))}/{_fmt(row.get('delta_r_solver_minus_xstar'))}"
        delta_diag = f"{_fmt(row.get('delta_R_solver_minus_xstar'))}/{_fmt(row.get('delta_G_solver_minus_xstar'))}"
        lines.append(
            f"| {row.get('ion','')} | {_fmt(row.get('temperature_K'))} | {_fmt(row.get('electron_density_cm^-3'))} | {_fmt(row.get('log_xi'))} | {_fmt(row.get('ion_fraction'))} | {target} | {target_diag} | {solver} | {solver_diag} | {delta} | {delta_diag} | {row.get('triplet_residual_pattern','')} | {row.get('source_code_gap_diagnosis','')} | {row.get('solver_triplet_source','')} | {c.status} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_xstar_benchmark_suite(
    cases: Sequence[Mapping[str, Any]],
    *,
    value_column: str = "emit_outward",
    run_solver: bool = False,
    db: Any = None,
    fitsfile: str | Path | None = None,
    solver_kwargs: Mapping[str, Any] | None = None,
    solver_preset: str | None = None,
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
            solver_kwargs=solver_kwargs,
            solver_preset=solver_preset,
        ))
    return out


def read_cases_csv(path: str | Path) -> list[dict[str, Any]]:
    """Read a simple cases CSV with at least ``ion`` and ``run_dir`` columns."""
    p = Path(path)
    if not p.exists():
        recipe = (
            "Create it with:\n"
            "cat > helike_reproduction_cases.csv <<'EOF'\n"
            "ion,run_dir\n"
            "C V,xstar_runs/helike_type69/c5_ne1e8\n"
            "O VII,xstar_runs/helike_type69/o7_ne1e8\n"
            "Mg XI,xstar_runs/helike_type69/mg11_ne1e8\n"
            "Ca XIX,xstar_runs/helike_type69/ca19_xi3_ne1e8\n"
            "EOF\n"
            "or use --standard-helike-suite --xstar-runs-root xstar_runs."
        )
        raise FileNotFoundError(f"Cases CSV not found: {p}\n{recipe}")
    with p.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


__all__ = [
    "DEFAULT_HELIKE_WINDOWS_A",
    "DEFAULT_HELIKE_BENCHMARK_RUNS",
    "XSTARLocalTarget",
    "XSTARBenchmarkComparison",
    "default_helike_wavelength_window",
    "default_helike_benchmark_cases",
    "write_default_helike_cases_csv",
    "find_xstar_run_files",
    "build_xstar_local_target",
    "compare_solver_to_xstar_target",
    "reproduce_xstar_run",
    "run_xstar_benchmark_suite",
    "read_cases_csv",
    "write_xstar_benchmark_outputs",
    "write_xstar_benchmark_suite",
    "solver_kwargs_from_preset",
    "xstar_local_state_solver_kwargs",
]
