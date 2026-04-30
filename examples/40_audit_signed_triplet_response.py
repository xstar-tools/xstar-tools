#!/usr/bin/env python3
"""Audit signed versus absolute He-like triplet response for source levels.

This diagnostic asks whether negative f/i/r response components in the
source-basis scans are physical or are produced by subtracting a baseline
solver triplet emissivity.  It runs one baseline solve with no external source,
then one solve per requested source level.  For each level it reports the
baseline triplet, the source-injected triplet, absolute injected fractions,
delta triplet = injected - baseline, signed normalized delta response, sign
pattern, and whether negative deltas are caused by baseline subtraction.

The script is diagnostic only.  It does not change the solver or fitted weights.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

import numpy as np


COMPONENTS = ["forbidden", "intercombination", "resonance"]



def resolve_optional_fitsfile(path: Optional[str]) -> str:
    """Resolve optional atdb.fits path without rewriting datapath.

    If a path is supplied, return it unchanged; this avoids changing the
    persistent datapath during ordinary example runs.  If omitted, defer to the
    package data resolver, which uses XSTAR_ATDB_FITS, datapath, or data/.
    """
    if path is not None:
        return str(path)
    from xstar_atomic.data import resolve_atdb_path
    return str(resolve_atdb_path(None, prompt=False, remember_explicit=False))

def _maybe_float(value) -> Optional[float]:
    try:
        out = float(value)
    except Exception:
        return None
    if not math.isfinite(out):
        return None
    return out


def _fmt(value, precision: int = 6) -> str:
    val = _maybe_float(value)
    if val is None:
        return "NA"
    return f"{val:.{precision}g}"


def parse_level_list(text: str) -> List[int]:
    out: List[int] = []
    for part in str(text).replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            a, b = part.split(":", 1)
            start, stop = int(a), int(b)
            step = 1 if stop >= start else -1
            out.extend(list(range(start, stop + step, step)))
        else:
            out.append(int(part))
    # preserve order while removing duplicates
    seen = set()
    uniq = []
    for lev in out:
        if lev not in seen:
            uniq.append(int(lev))
            seen.add(int(lev))
    return uniq


def write_csv(path: Path, rows: List[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: List[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    if not fields:
        fields = ["warning"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def read_triplet_csv(path: Path) -> Dict[str, Optional[float]]:
    if not path.exists():
        return {"forbidden": 0.0, "intercombination": 0.0, "resonance": 0.0, "R_f_over_i": None, "G_f_plus_i_over_r": None}
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return {"forbidden": 0.0, "intercombination": 0.0, "resonance": 0.0, "R_f_over_i": None, "G_f_plus_i_over_r": None}
    row = rows[0]
    return {
        "forbidden": float(row.get("forbidden_energy_per_ion_erg_s^-1") or row.get("forbidden") or 0.0),
        "intercombination": float(row.get("intercombination_energy_per_ion_erg_s^-1") or row.get("intercombination") or 0.0),
        "resonance": float(row.get("resonance_energy_per_ion_erg_s^-1") or row.get("resonance") or 0.0),
        "R_f_over_i": _maybe_float(row.get("R_f_over_i")),
        "G_f_plus_i_over_r": _maybe_float(row.get("G_f_plus_i_over_r")),
    }




_ROMAN_BY_STAGE = {
    1: "i", 2: "ii", 3: "iii", 4: "iv", 5: "v", 6: "vi", 7: "vii", 8: "viii",
    9: "ix", 10: "x", 11: "xi", 12: "xii", 13: "xiii", 14: "xiv", 15: "xv",
    16: "xvi", 17: "xvii", 18: "xviii", 19: "xix", 20: "xx", 21: "xxi",
    22: "xxii", 23: "xxiii", 24: "xxiv", 25: "xxv",
}


def expected_ion_aliases(element: str, ion_stage: int) -> set[str]:
    sym = str(element).strip().lower()
    aliases = {f"{sym}{int(ion_stage)}"}
    roman = _ROMAN_BY_STAGE.get(int(ion_stage))
    if roman:
        aliases.add(f"{sym}{roman}")
    return aliases


def normalize_ion_text(text: str) -> str:
    return str(text or "").strip().lower().replace(" ", "").replace("_", "")


def classify_helike_triplet_row(row: dict) -> Optional[str]:
    lower = str(row.get("lower_level", "") or row.get("lower", "")).replace(" ", "")
    upper = str(row.get("upper_level", "") or row.get("upper", "")).replace(" ", "")
    if "1s2.1S_0" in lower or "1s2" in lower:
        if "1s1.2s1.3S_1" in upper or "2s1.3S_1" in upper:
            return "forbidden"
        if "1s1.2p1.1P_1" in upper or "2p1.1P_1" in upper:
            return "resonance"
        if "1s1.2p1.3P_" in upper or "2p1.3P_" in upper:
            return "intercombination"
    return None


def read_xstar_triplet_reference(path: Path, element: str, ion_stage: int, value_column: str) -> dict:
    totals = {name: 0.0 for name in COMPONENTS}
    counts = {name: 0 for name in COMPONENTS}
    if not path.exists():
        return {"available": False, "reason": "missing_file", "path": str(path)}
    aliases = expected_ion_aliases(element, int(ion_stage))
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            ion_text = normalize_ion_text(row.get("ion", ""))
            if ion_text and ion_text not in aliases:
                continue
            val = _maybe_float(row.get(value_column))
            if val is None:
                continue
            kind = classify_helike_triplet_row(row)
            if kind is None:
                continue
            totals[kind] += float(val)
            counts[kind] += 1
    missing = [name for name in COMPONENTS if counts[name] <= 0]
    if missing:
        return {"available": False, "reason": "incomplete_triplet", "missing_components": missing, "counts": counts, "path": str(path)}
    vec = np.asarray([totals[name] for name in COMPONENTS], dtype=float)
    norm = normalize_positive(vec)
    out = {"available": True, "path": str(path), "counts": counts, "value_column": value_column}
    out.update(component_flags("target", vec))
    out.update(component_flags("target_norm", norm))
    out.update({f"target_{k}": v for k, v in ratios(vec).items()})
    return out


def project_to_simplex(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, dtype=float)
    if v.size == 0:
        return v
    u = np.sort(v)[::-1]
    cssv = np.cumsum(u)
    rho_candidates = u * np.arange(1, len(u) + 1) > (cssv - 1.0)
    if not np.any(rho_candidates):
        return np.full_like(v, 1.0 / len(v))
    rho = np.nonzero(rho_candidates)[0][-1]
    theta = (cssv[rho] - 1.0) / float(rho + 1)
    w = np.maximum(v - theta, 0.0)
    sw = float(w.sum())
    return w / sw if sw > 0.0 else np.full_like(v, 1.0 / len(v))


def fit_raw_response_simplex(raw_response: np.ndarray, target_norm: np.ndarray, max_iter: int = 50000, tol: float = 1e-13) -> Tuple[np.ndarray, dict]:
    """Fit nonnegative simplex weights to positive absolute triplet responses.

    This is intentionally based on source-injected absolute emissivities, not
    on injected-minus-baseline deltas.  It therefore avoids the negative
    baseline-subtracted response columns that triggered the non-O VII failures.
    """
    Y = np.asarray(raw_response, dtype=float)
    n = int(Y.shape[0]) if Y.ndim == 2 else 0
    if n == 0:
        return np.array([], dtype=float), {"status": "empty_response_matrix", "objective": None}
    target = np.asarray(target_norm, dtype=float)
    tsum = float(np.sum(target))
    if not math.isfinite(tsum) or tsum <= 0.0:
        return np.full(n, 1.0 / n, dtype=float), {"status": "invalid_target", "objective": None}
    target = target / tsum
    Y = np.where(np.isfinite(Y) & (Y > 0.0), Y, 0.0)
    row_sums = np.sum(Y, axis=1)
    scale = float(np.nanmax(np.where(np.isfinite(row_sums) & (row_sums > 0.0), row_sums, 0.0))) if Y.size else 0.0
    if not np.isfinite(scale) or scale <= 0.0:
        return np.full(n, 1.0 / n, dtype=float), {"status": "zero_absolute_response_matrix", "objective": None}
    Ys = Y / scale
    Z = Ys - np.sum(Ys, axis=1)[:, None] * target[None, :]
    w = np.full(n, 1.0 / n, dtype=float)
    try:
        spectral = float(np.linalg.norm(Z, ord=2))
    except Exception:
        spectral = float(np.linalg.norm(Z))
    step = 1.0 / max(2.0 * spectral * spectral, 1e-30)
    prev = float("inf")
    status = "max_iter"
    it = 0
    for it in range(int(max_iter)):
        resid = w @ Z
        obj = float(np.dot(resid, resid))
        if abs(prev - obj) < tol * max(1.0, prev):
            status = "converged"
            break
        prev = obj
        grad = 2.0 * (Z @ resid)
        w = project_to_simplex(w - step * grad)
    final_raw = w @ Y
    final_norm = normalize_positive(final_raw)
    final_centered = w @ Z
    info = {
        "status": status,
        "iterations": int(it + 1),
        "objective": float(np.dot(final_centered, final_centered)),
        "step": step,
        "absolute_response_scale": scale,
        "combined_absolute_triplet_sum": float(np.sum(final_raw)),
        "combined_normalized_forbidden": float(final_norm[0]),
        "combined_normalized_intercombination": float(final_norm[1]),
        "combined_normalized_resonance": float(final_norm[2]),
    }
    return w, info

def vec_from_triplet(trip: Dict[str, Optional[float]]) -> np.ndarray:
    return np.asarray([_maybe_float(trip.get(k)) or 0.0 for k in COMPONENTS], dtype=float)


def ratios(vec: Sequence[float]) -> Dict[str, Optional[float]]:
    f, i, r = [float(x) for x in vec]
    return {
        "R_f_over_i": (f / i) if i > 0.0 else None,
        "G_f_plus_i_over_r": ((f + i) / r) if r > 0.0 else None,
    }


def normalize_positive(vec: Sequence[float]) -> np.ndarray:
    arr = np.asarray(vec, dtype=float)
    arr = np.where(np.isfinite(arr) & (arr > 0.0), arr, 0.0)
    total = float(arr.sum())
    if total <= 0.0:
        return np.zeros_like(arr)
    return arr / total


def normalize_signed_abs(vec: Sequence[float]) -> np.ndarray:
    arr = np.asarray(vec, dtype=float)
    arr = np.where(np.isfinite(arr), arr, 0.0)
    denom = float(np.sum(np.abs(arr)))
    if denom <= 0.0:
        return np.zeros_like(arr)
    return arr / denom


def sign_pattern(delta: Sequence[float], zero_tol: float) -> str:
    arr = np.asarray(delta, dtype=float)
    pos = bool(np.any(arr > abs(zero_tol)))
    neg = bool(np.any(arr < -abs(zero_tol)))
    nonzero = pos or neg
    if not nonzero:
        return "zero"
    if pos and neg:
        return "mixed"
    if pos:
        return "positive"
    return "negative"


def append_common_solver_args(cmd: List[str], args) -> None:
    cmd += [
        "--linear-solver", str(args.linear_solver),
        "--rank-deficient-action", str(args.rank_deficient_action),
        "--negative-population-action", str(args.negative_population_action),
        "--negative-population-tol", f"{float(args.negative_population_tol):.16g}",
    ]
    if args.residual_l2_max is not None:
        cmd += ["--residual-l2-max", f"{float(args.residual_l2_max):.16g}"]
    if args.residual_linf_max is not None:
        cmd += ["--residual-linf-max", f"{float(args.residual_linf_max):.16g}"]
    if args.reject_large_residual:
        cmd += ["--reject-large-residual"]
    if args.prune_null_rate_levels:
        cmd += ["--prune-null-rate-levels", "--null-rate-floor", f"{float(args.null_rate_floor):.16g}"]
    if args.collision_rate_scale not in (None, 1.0):
        cmd += ["--collision-rate-scale", f"{float(args.collision_rate_scale):.16g}"]
    for spec in args.collision_data_type_scale or []:
        cmd += ["--collision-data-type-scale", str(spec)]
    for spec in args.collision_pair_scale or []:
        cmd += ["--collision-pair-scale", str(spec)]
    for spec in args.collision_record_scale or []:
        cmd += ["--collision-record-scale", str(spec)]
    for spec in args.collision_record_direction_scale or []:
        cmd += ["--collision-record-direction-scale", str(spec)]
    if args.collision_type69_ground_excitation_mode != "include":
        cmd += ["--collision-type69-ground-excitation-mode", str(args.collision_type69_ground_excitation_mode)]
    if args.index_cache:
        if args.index_cache_path:
            cmd += ["--index-cache", str(args.index_cache_path), "--index-cache-format", args.index_cache_format]
        else:
            cmd += ["--index-cache", "--index-cache-format", args.index_cache_format]


def solver_command(args, triplet_csv: Path, lines_csv: Path, summary_json: Path, source_level: Optional[int] = None) -> List[str]:
    cmd = [
        sys.executable, "-m", "xstar_atomic.solver", str(args.fitsfile),
        "--element", str(args.element), "--ion-stage", str(int(args.ion_stage)),
        "--temperatures", f"{float(args.temperature):.16g}",
        "--electron-densities", f"{float(args.electron_density):.16g}",
        "--wavelength-min", f"{float(args.wavelength_min):.16g}",
        "--wavelength-max", f"{float(args.wavelength_max):.16g}",
        "--out-lines-csv", str(lines_csv),
        "--out-triplet-csv", str(triplet_csv),
        "--summary-json", str(summary_json),
    ]
    if source_level is not None:
        cmd += ["--source-level", str(int(source_level)), f"{float(args.source_rate):.16g}"]
    append_common_solver_args(cmd, args)
    return cmd


def run_command(cmd: List[str], stdout_path: Path, stderr_path: Path, dry_run: bool = False) -> int:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_path.write_text(" ".join(cmd) + "\n", encoding="utf-8")
    stderr_path.write_text("", encoding="utf-8")
    if dry_run:
        return 0
    with stdout_path.open("a", encoding="utf-8") as out, stderr_path.open("a", encoding="utf-8") as err:
        proc = subprocess.run(cmd, stdout=out, stderr=err, text=True)
    return int(proc.returncode)


def component_flags(prefix: str, vec: Sequence[float]) -> Dict[str, float]:
    arr = np.asarray(vec, dtype=float)
    return {f"{prefix}_{name}": float(arr[idx]) for idx, name in enumerate(COMPONENTS)}


def audit_source_level(level: int, baseline: np.ndarray, injected: np.ndarray, zero_tol: float) -> dict:
    delta = injected - baseline
    baseline_norm = normalize_positive(baseline)
    injected_norm = normalize_positive(injected)
    delta_signed_norm = normalize_signed_abs(delta)
    delta_positive_norm = normalize_positive(delta)
    row: Dict[str, object] = {"source_level": int(level)}
    row.update(component_flags("baseline", baseline))
    row.update(component_flags("baseline_norm", baseline_norm))
    row.update(component_flags("injected", injected))
    row.update(component_flags("injected_norm", injected_norm))
    row.update(component_flags("delta", delta))
    row.update(component_flags("delta_signed_absnorm", delta_signed_norm))
    row.update(component_flags("delta_positive_norm", delta_positive_norm))
    row.update({f"increases_{name}": bool(delta[idx] > abs(zero_tol)) for idx, name in enumerate(COMPONENTS)})
    row.update({f"decreases_{name}": bool(delta[idx] < -abs(zero_tol)) for idx, name in enumerate(COMPONENTS)})
    neg_components = [name for idx, name in enumerate(COMPONENTS) if delta[idx] < -abs(zero_tol)]
    pos_components = [name for idx, name in enumerate(COMPONENTS) if delta[idx] > abs(zero_tol)]
    baseline_sub_neg = [name for idx, name in enumerate(COMPONENTS) if delta[idx] < -abs(zero_tol) and baseline[idx] > injected[idx]]
    row["sign_pattern"] = sign_pattern(delta, zero_tol)
    row["positive_delta_components"] = ";".join(pos_components)
    row["negative_delta_components"] = ";".join(neg_components)
    row["baseline_subtraction_negative_components"] = ";".join(baseline_sub_neg)
    row["negative_response_caused_by_baseline_subtraction"] = bool(neg_components and len(baseline_sub_neg) == len(neg_components))
    row["any_absolute_component_increased"] = bool(pos_components)
    row["n_absolute_components_increased"] = int(len(pos_components))
    row["baseline_triplet_sum"] = float(np.sum(baseline))
    row["injected_triplet_sum"] = float(np.sum(injected))
    row["delta_triplet_sum"] = float(np.sum(delta))
    row["delta_triplet_abs_sum"] = float(np.sum(np.abs(delta)))
    row["baseline_to_delta_abs_sum_ratio"] = (float(np.sum(baseline)) / float(np.sum(np.abs(delta)))) if float(np.sum(np.abs(delta))) > 0.0 else None
    row.update({f"baseline_{k}": v for k, v in ratios(baseline).items()})
    row.update({f"injected_{k}": v for k, v in ratios(injected).items()})
    row.update({f"delta_positive_{k}": v for k, v in ratios(delta_positive_norm).items()})
    return row


def summarize_rows(rows: List[dict]) -> dict:
    if not rows:
        return {"n_source_levels": 0}
    patterns: Dict[str, int] = {}
    neg_sub = 0
    inc = {name: 0 for name in COMPONENTS}
    dec = {name: 0 for name in COMPONENTS}
    for row in rows:
        patterns[str(row.get("sign_pattern"))] = patterns.get(str(row.get("sign_pattern")), 0) + 1
        if row.get("negative_response_caused_by_baseline_subtraction"):
            neg_sub += 1
        for name in COMPONENTS:
            if row.get(f"increases_{name}"):
                inc[name] += 1
            if row.get(f"decreases_{name}"):
                dec[name] += 1
    return {
        "n_source_levels": len(rows),
        "sign_pattern_counts": patterns,
        "n_negative_due_to_baseline_subtraction": neg_sub,
        "n_increases_forbidden": inc["forbidden"],
        "n_increases_intercombination": inc["intercombination"],
        "n_increases_resonance": inc["resonance"],
        "n_decreases_forbidden": dec["forbidden"],
        "n_decreases_intercombination": dec["intercombination"],
        "n_decreases_resonance": dec["resonance"],
    }


def write_markdown(path: Path, rows: List[dict], summary: dict, args) -> None:
    lines = []
    lines.append("# Signed/absolute He-like triplet response audit")
    lines.append("")
    lines.append(f"Element/ion: `{args.element} {args.ion_stage}`")
    lines.append(f"T = `{args.temperature:g}` K, ne = `{args.electron_density:g}` cm^-3")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Source levels audited: {summary.get('n_source_levels', 0)}")
    lines.append(f"- Sign-pattern counts: `{summary.get('sign_pattern_counts', {})}`")
    lines.append(f"- Negative responses caused by baseline subtraction: {summary.get('n_negative_due_to_baseline_subtraction', 0)}")
    lines.append(f"- Levels increasing f/i/r: {summary.get('n_increases_forbidden', 0)} / {summary.get('n_increases_intercombination', 0)} / {summary.get('n_increases_resonance', 0)}")
    fit = summary.get("absolute_response_fit") or {}
    if fit.get("enabled"):
        lines.append(f"- Absolute-response fit status: `{fit.get('status')}`")
        lines.append(f"- Absolute-response fit candidates: {fit.get('n_candidate_source_levels', 'NA')}")
        lines.append(f"- Absolute-response fit L2 error: {_fmt(fit.get('component_l2_error'))}")
        lines.append(f"- Absolute-response top levels: `{fit.get('top_source_levels', [])}`")
    lines.append("")
    lines.append("## Per-level overview")
    lines.append("")
    lines.append("| level | sign | increases | decreases | baseline-subtraction negative? | delta f/i/r | injected f/i/r |")
    lines.append("|---:|---|---|---|---|---|---|")
    for row in rows[:200]:
        inc = ";".join([name for name in COMPONENTS if row.get(f"increases_{name}")]) or "none"
        dec = ";".join([name for name in COMPONENTS if row.get(f"decreases_{name}")]) or "none"
        d = f"{_fmt(row.get('delta_forbidden'))}/{_fmt(row.get('delta_intercombination'))}/{_fmt(row.get('delta_resonance'))}"
        inj = f"{_fmt(row.get('injected_forbidden'))}/{_fmt(row.get('injected_intercombination'))}/{_fmt(row.get('injected_resonance'))}"
        lines.append(f"| {row.get('source_level')} | {row.get('sign_pattern')} | {inc} | {dec} | {row.get('negative_response_caused_by_baseline_subtraction')} | {d} | {inj} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fitsfile", nargs="?", default=None, help="Optional XSTAR atdb.fits path. If omitted, use XSTAR_ATDB_FITS, datapath, or data/atdb.fits.")
    parser.add_argument("--element", default="O")
    parser.add_argument("--ion-stage", type=int, default=7)
    parser.add_argument("--temperature", type=float, default=1.0e6)
    parser.add_argument("--electron-density", type=float, default=1.0)
    parser.add_argument("--source-levels", default="2,3,4,5,7,8,9,10,11,12,13,14,15,16,17,18,19,20")
    parser.add_argument("--source-rate", type=float, default=1.0)
    parser.add_argument("--wavelength-min", type=float, default=21.5)
    parser.add_argument("--wavelength-max", type=float, default=22.2)
    parser.add_argument("--linear-solver", choices=["dense", "sparse", "auto", "lstsq", "svd"], default="svd")
    parser.add_argument("--rank-deficient-action", choices=["warn", "lstsq", "svd", "reject"], default="svd")
    parser.add_argument("--negative-population-action", choices=["clip", "zero-small", "keep", "reject"], default="keep")
    parser.add_argument("--negative-population-tol", type=float, default=1.0e-8)
    parser.add_argument("--residual-l2-max", type=float)
    parser.add_argument("--residual-linf-max", type=float)
    parser.add_argument("--reject-large-residual", action="store_true")
    parser.add_argument("--prune-null-rate-levels", action="store_true", default=True)
    parser.add_argument("--no-prune-null-rate-levels", dest="prune_null_rate_levels", action="store_false")
    parser.add_argument("--null-rate-floor", type=float, default=0.0)
    parser.add_argument("--collision-rate-scale", type=float, default=1.0)
    parser.add_argument("--collision-data-type-scale", action="append", default=[])
    parser.add_argument("--collision-pair-scale", action="append", default=[])
    parser.add_argument("--collision-record-scale", action="append", default=[])
    parser.add_argument("--collision-record-direction-scale", action="append", default=[])
    parser.add_argument("--collision-type69-ground-excitation-mode", choices=["include", "suppress-resonance", "suppress-all"], default="include")
    parser.add_argument("--index-cache", action="store_true")
    parser.add_argument("--index-cache-path")
    parser.add_argument("--index-cache-format", choices=["npz", "pickle"], default="npz")
    parser.add_argument("--zero-tol", type=float, default=0.0)
    parser.add_argument("--fit-mode", choices=["none", "absolute-response"], default="none", help="Optional fit mode. absolute-response fits XSTAR target fractions using positive absolute source-injected triplet emissivities, not baseline-subtracted deltas.")
    parser.add_argument("--xstar-lines-csv", help="Converted XSTAR He-like triplet line CSV used as the target for --fit-mode absolute-response.")
    parser.add_argument("--xstar-value-column", default="emit_outward", help="XSTAR line CSV value column used for the target triplet.")
    parser.add_argument("--absolute-fit-min-triplet-sum", type=float, default=0.0, help="Minimum positive absolute injected f+i+r sum required for a source level to enter the absolute-response fit.")
    parser.add_argument("--fit-max-iter", type=int, default=50000, help="Maximum projected-gradient iterations for absolute-response fitting.")
    parser.add_argument("--out-dir", default="helike_signed_triplet_response_audit")
    parser.add_argument("--dry-run", action="store_true", help="Write commands and output skeleton without running xstar_atomic.solver")
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()
    args.fitsfile = resolve_optional_fitsfile(args.fitsfile)

    out_dir = Path(args.out_dir)
    run_dir = out_dir / "solver_runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(parents=True, exist_ok=True)

    source_levels = parse_level_list(args.source_levels)
    command_rows: List[dict] = []

    baseline_triplet = run_dir / "baseline_triplet.csv"
    baseline_lines = run_dir / "baseline_lines.csv"
    baseline_summary = run_dir / "baseline_summary.json"
    baseline_cmd = solver_command(args, baseline_triplet, baseline_lines, baseline_summary, source_level=None)
    rc = run_command(baseline_cmd, run_dir / "baseline.stdout.log", run_dir / "baseline.stderr.log", dry_run=args.dry_run)
    command_rows.append({"kind": "baseline", "source_level": "", "returncode": rc, "command": " ".join(baseline_cmd)})
    if rc != 0 and not args.dry_run:
        raise SystemExit(f"Baseline solver run failed; see {run_dir / 'baseline.stderr.log'}")
    baseline = vec_from_triplet(read_triplet_csv(baseline_triplet)) if not args.dry_run else np.zeros(3, dtype=float)

    rows: List[dict] = []
    for lev in source_levels:
        lev_dir = run_dir / f"level_{lev}"
        triplet = lev_dir / "triplet.csv"
        lines = lev_dir / "lines.csv"
        summary = lev_dir / "summary.json"
        cmd = solver_command(args, triplet, lines, summary, source_level=int(lev))
        rc = run_command(cmd, lev_dir / "stdout.log", lev_dir / "stderr.log", dry_run=args.dry_run)
        command_rows.append({"kind": "source", "source_level": int(lev), "returncode": rc, "command": " ".join(cmd)})
        if rc != 0 and not args.dry_run:
            rows.append({"source_level": int(lev), "run_status": "failed", "stderr_log": str(lev_dir / "stderr.log")})
            continue
        injected = vec_from_triplet(read_triplet_csv(triplet)) if not args.dry_run else np.zeros(3, dtype=float)
        row = audit_source_level(int(lev), baseline, injected, args.zero_tol)
        row.update({
            "run_status": "dry_run" if args.dry_run else "ok",
            "triplet_csv": str(triplet),
            "lines_csv": str(lines),
            "summary_json": str(summary),
        })
        rows.append(row)


    absolute_fit_summary: dict = {"enabled": False, "mode": args.fit_mode}
    absolute_fit_rows: List[dict] = []
    if args.fit_mode == "absolute-response":
        if not args.xstar_lines_csv:
            absolute_fit_summary = {"enabled": False, "mode": args.fit_mode, "status": "missing_--xstar-lines-csv"}
        elif args.dry_run:
            absolute_fit_summary = {"enabled": True, "mode": args.fit_mode, "status": "dry_run", "xstar_lines_csv": str(args.xstar_lines_csv)}
        else:
            target_ref = read_xstar_triplet_reference(Path(args.xstar_lines_csv), args.element, int(args.ion_stage), args.xstar_value_column)
            if not target_ref.get("available"):
                absolute_fit_summary = {"enabled": True, "mode": args.fit_mode, "status": "invalid_xstar_target", "xstar_reference": target_ref}
            else:
                target = np.asarray([target_ref[f"target_norm_{name}"] for name in COMPONENTS], dtype=float)
                fit_candidates: List[dict] = []
                Y_abs: List[List[float]] = []
                for row in rows:
                    if row.get("run_status") != "ok":
                        continue
                    injected = np.asarray([_maybe_float(row.get(f"injected_{name}")) or 0.0 for name in COMPONENTS], dtype=float)
                    abs_pos = np.where(np.isfinite(injected) & (injected > 0.0), injected, 0.0)
                    abs_sum = float(np.sum(abs_pos))
                    if abs_sum <= float(args.absolute_fit_min_triplet_sum):
                        continue
                    fit_candidates.append(row)
                    Y_abs.append([float(x) for x in abs_pos])
                Y = np.asarray(Y_abs, dtype=float)
                weights, fit_info = fit_raw_response_simplex(Y, target, max_iter=int(args.fit_max_iter))
                pred_raw = weights @ Y if weights.size else np.zeros(3, dtype=float)
                pred = normalize_positive(pred_raw)
                l2 = float(np.linalg.norm(pred - target)) if pred.size == 3 else None
                l1 = float(np.sum(np.abs(pred - target))) if pred.size == 3 else None
                pred_ratios = ratios(pred)
                target_ratios = ratios(target)
                absolute_fit_summary = {
                    "enabled": True,
                    "mode": args.fit_mode,
                    "status": fit_info.get("status"),
                    "xstar_reference": target_ref,
                    "n_candidate_source_levels": len(fit_candidates),
                    "n_input_source_levels": len(source_levels),
                    "min_triplet_sum": float(args.absolute_fit_min_triplet_sum),
                    "component_l1_error": l1,
                    "component_l2_error": l2,
                    "pred_forbidden": float(pred[0]),
                    "pred_intercombination": float(pred[1]),
                    "pred_resonance": float(pred[2]),
                    "target_forbidden": float(target[0]),
                    "target_intercombination": float(target[1]),
                    "target_resonance": float(target[2]),
                    "pred_R_f_over_i": pred_ratios.get("R_f_over_i"),
                    "pred_G_f_plus_i_over_r": pred_ratios.get("G_f_plus_i_over_r"),
                    "target_R_f_over_i": target_ratios.get("R_f_over_i"),
                    "target_G_f_plus_i_over_r": target_ratios.get("G_f_plus_i_over_r"),
                    "fit_info": fit_info,
                    "top_source_levels": [],
                }
                for idx, row in enumerate(fit_candidates):
                    lev = int(row.get("source_level"))
                    inj = np.asarray([_maybe_float(row.get(f"injected_{name}")) or 0.0 for name in COMPONENTS], dtype=float)
                    abs_pos = np.where(np.isfinite(inj) & (inj > 0.0), inj, 0.0)
                    norm = normalize_positive(abs_pos)
                    weight = float(weights[idx]) if idx < len(weights) else 0.0
                    out = {
                        "source_level": lev,
                        "absolute_fit_weight_norm": weight,
                        "absolute_fit_basis_member": bool(weight > 0.0),
                        "absolute_forbidden": float(abs_pos[0]),
                        "absolute_intercombination": float(abs_pos[1]),
                        "absolute_resonance": float(abs_pos[2]),
                        "absolute_triplet_sum": float(np.sum(abs_pos)),
                        "absolute_norm_forbidden": float(norm[0]),
                        "absolute_norm_intercombination": float(norm[1]),
                        "absolute_norm_resonance": float(norm[2]),
                        "sign_pattern": row.get("sign_pattern"),
                        "negative_response_caused_by_baseline_subtraction": row.get("negative_response_caused_by_baseline_subtraction"),
                        "fit_raw_contribution_forbidden": float(weight * abs_pos[0]),
                        "fit_raw_contribution_intercombination": float(weight * abs_pos[1]),
                        "fit_raw_contribution_resonance": float(weight * abs_pos[2]),
                    }
                    absolute_fit_rows.append(out)
                absolute_fit_rows.sort(key=lambda r: float(r.get("absolute_fit_weight_norm") or 0.0), reverse=True)
                absolute_fit_summary["top_source_levels"] = [int(r["source_level"]) for r in absolute_fit_rows[:10] if float(r.get("absolute_fit_weight_norm") or 0.0) > 0.0]

    summary = summarize_rows([r for r in rows if r.get("run_status") in ("ok", "dry_run")])
    summary.update({
        "fitsfile": str(args.fitsfile),
        "element": args.element,
        "ion_stage": int(args.ion_stage),
        "temperature_K": float(args.temperature),
        "electron_density_cm^-3": float(args.electron_density),
        "source_rate_s^-1": float(args.source_rate),
        "source_levels": source_levels,
        "baseline_triplet": {k: float(v) for k, v in zip(COMPONENTS, baseline)},
        "dry_run": bool(args.dry_run),
        "absolute_response_fit": absolute_fit_summary,
    })

    write_csv(out_dir / "helike_signed_triplet_response_audit.csv", rows)
    write_csv(out_dir / "helike_signed_triplet_response_commands.csv", command_rows)
    write_csv(out_dir / "helike_absolute_response_fit_weights.csv", absolute_fit_rows)
    (out_dir / "helike_signed_triplet_response_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_markdown(out_dir / "helike_signed_triplet_response_audit.md", rows, summary, args)

    if args.print_summary:
        print("Signed/absolute He-like triplet response audit")
        print("------------------------------------------------")
        print(f"baseline f/i/r={_fmt(baseline[0])}/{_fmt(baseline[1])}/{_fmt(baseline[2])}")
        print(f"levels={len(source_levels)} patterns={summary.get('sign_pattern_counts', {})} baseline_sub_neg={summary.get('n_negative_due_to_baseline_subtraction', 0)}")
        fit = summary.get("absolute_response_fit") or {}
        if fit.get("enabled"):
            print(
                f"absolute_response_fit status={fit.get('status')} candidates={fit.get('n_candidate_source_levels', 'NA')} "
                f"l2={_fmt(fit.get('component_l2_error'))} top={fit.get('top_source_levels', [])}"
            )
        elif fit.get("status"):
            print(f"absolute_response_fit status={fit.get('status')}")
        for row in rows:
            if row.get("run_status") == "failed":
                print(f"level {row.get('source_level')}: failed; see {row.get('stderr_log')}")
                continue
            print(
                f"level {row.get('source_level')}: sign={row.get('sign_pattern')} "
                f"inc={row.get('positive_delta_components') or 'none'} "
                f"dec={row.get('negative_delta_components') or 'none'} "
                f"baseline_sub_neg={row.get('negative_response_caused_by_baseline_subtraction')}"
            )
        print(f"wrote: {out_dir / 'helike_signed_triplet_response_audit.md'}")


if __name__ == "__main__":
    main()
