#!/usr/bin/env python3
"""Diagnose He-like source-level response failures across density-grid runs.

This diagnostic expands the run-level comparison in example 35 down to the
individual fitted source levels.  It is intended to answer why a fitted
linear-response source vector is not reproduced by the full simultaneous solver.

The script primarily reads products from examples/20--22.  If ``--fitsfile`` is
supplied, it also annotates source levels with ATDB level labels and extracts
radiative/collisional rate summaries directly from ATDB for the selected
T/ne.  If combined solver population/transition CSVs are present, those are
used for source-component population and dominant transition diagnostics; older
runs that did not write those CSVs are still supported and report ``NA`` for
those columns.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Iterable

import numpy as np

try:
    from xstar_atomic.hierarchy import ATDB
    from xstar_atomic.lines import choose_z, extract_levels, extract_lines
    from xstar_atomic.collisions import extract_collisions
    from xstar_atomic.solver import build_collision_rates_for_T
except Exception:  # pragma: no cover - import failure is handled at runtime
    ATDB = None  # type: ignore
    choose_z = extract_levels = extract_lines = extract_collisions = None  # type: ignore
    build_collision_rates_for_T = None  # type: ignore


TRIPLET_COMPONENTS = ("forbidden", "intercombination", "resonance")
ZERO_TOL = 0.0
NEGATIVE_RAW_TOL = 1.0e-12


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        x = float(value)
        return x if math.isfinite(x) else None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", "na"}:
        return None
    try:
        x = float(text)
    except ValueError:
        return None
    return x if math.isfinite(x) else None


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except Exception:
        try:
            return int(float(value))
        except Exception:
            return None


def _fmt(value: Any, digits: int = 6) -> str:
    x = _as_float(value)
    if x is None:
        return "NA"
    return f"{x:.{digits}g}"


def _read_csv(path: Path | None) -> list[dict[str, str]]:
    if path is None or not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _read_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    with path.open() as handle:
        return json.load(handle)


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _find_first(paths: Iterable[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def _strip_known_suffixes(name: str) -> str:
    suffixes = (
        "_solver_source_fit_density_xstar_grid",
        "_source_fit_density_xstar_grid",
        "_density_xstar_grid",
    )
    for suffix in suffixes:
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def _infer_tag(run_dir: Path, summary: dict[str, Any]) -> str:
    dirname = _strip_known_suffixes(run_dir.name)
    if dirname == "o7_solver_source_fit_density_xstar_grid_type69_suppressed":
        return "o7_suppressed"
    if dirname.startswith("o7_solver_source_fit_density_xstar_grid"):
        return "o7"
    if dirname and dirname not in {"solver", "o7"}:
        return dirname
    element = str(summary.get("element") or "").lower()
    ion_stage = summary.get("ion_stage")
    if element and ion_stage is not None:
        return f"{element}{ion_stage}"
    return dirname or run_dir.name


def _ion_prefix(tag: str, summary: dict[str, Any]) -> str:
    element = str(summary.get("element") or "").lower()
    ion_stage = summary.get("ion_stage")
    if element and ion_stage is not None:
        return f"{element}{ion_stage}"
    return tag.split("_")[0]


def _density_sort_key(path: Path) -> float:
    token = path.name.replace("fit_ne_", "")
    try:
        return float(token.replace("e", "E"))
    except ValueError:
        return float("inf")


def _find_fit_summary(fit_dir: Path, prefix: str = "") -> Path | None:
    candidates = []
    if prefix:
        candidates.append(fit_dir / f"{prefix}_solver_source_fit_summary.json")
    candidates += [fit_dir / "o7_solver_source_fit_summary.json", *fit_dir.glob("*_solver_source_fit_summary.json")]
    return _find_first(candidates)


def _find_response_matrix(fit_dir: Path, prefix: str) -> Path | None:
    return _find_first([
        fit_dir / f"{prefix}_solver_response_matrix.csv",
        fit_dir / "o7_solver_response_matrix.csv",
        *fit_dir.glob("*_solver_response_matrix.csv"),
    ])


def _find_weight_csv(fit_dir: Path, prefix: str) -> Path | None:
    return _find_first([
        fit_dir / f"{prefix}_solver_source_fit_weights.csv",
        fit_dir / "o7_solver_source_fit_weights.csv",
        *fit_dir.glob("*_solver_source_fit_weights.csv"),
    ])


def _find_combined_file(fit_dir: Path, prefix: str, stem: str) -> Path | None:
    cdir = fit_dir / "combined_source_validation"
    return _find_first([
        cdir / f"{prefix}_{stem}",
        cdir / f"o7_{stem}",
        *cdir.glob(f"*_{stem}"),
    ])


def _merge_response_and_weights(response_rows: list[dict[str, str]], weight_rows: list[dict[str, str]]) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for row in response_rows:
        lev = _as_int(row.get("source_level"))
        if lev is None:
            continue
        out.setdefault(lev, {}).update({f"response_{k}": v for k, v in row.items()})
        out[lev]["source_level"] = lev
    for row in weight_rows:
        lev = _as_int(row.get("source_level"))
        if lev is None:
            continue
        out.setdefault(lev, {}).update({f"weight_{k}": v for k, v in row.items()})
        out[lev]["source_level"] = lev
    return out


def _build_level_components(levels: set[int], rad_edges: list[tuple[int, int]], coll_edges: list[tuple[int, int]]) -> dict[int, int]:
    adj: dict[int, set[int]] = {lev: set() for lev in levels}
    for a, b in rad_edges + coll_edges:
        if a in adj and b in adj:
            adj[a].add(b)
            adj[b].add(a)
    comp: dict[int, int] = {}
    cid = 0
    for lev in sorted(levels):
        if lev in comp:
            continue
        q = deque([lev])
        comp[lev] = cid
        while q:
            x = q.popleft()
            for y in adj.get(x, ()): 
                if y not in comp:
                    comp[y] = cid
                    q.append(y)
        cid += 1
    return comp


def _safe_label_from_rows(level: int, line_rows: list[dict[str, str]]) -> str:
    for row in line_rows:
        if _as_int(row.get("upper_level")) == level:
            return row.get("upper_label") or row.get("upper_level_label") or ""
        if _as_int(row.get("lower_level")) == level:
            return row.get("lower_label") or row.get("lower_level_label") or ""
    return ""


def _build_atdb_context(fitsfile: str | None, element: str, ion_stage: int, temperature: float, electron_density: float) -> dict[str, Any]:
    if not fitsfile:
        return {}
    if ATDB is None:
        raise RuntimeError("xstar_atomic modules are not importable; cannot use --fitsfile context")
    db = ATDB(fitsfile)
    # ATDB exposes build_index() in current xstar_atomic versions.  Some
    # early development notes referred to index_records(); keep a defensive
    # fallback so the diagnostic works across local trees.
    if hasattr(db, "build_index"):
        records, _elements, _ions = db.build_index()
    elif hasattr(db, "index_records"):
        records = db.index_records()  # type: ignore[attr-defined]
    else:  # pragma: no cover - protects against incompatible external ATDB APIs
        raise AttributeError("ATDB object has neither build_index() nor index_records()")
    z = choose_z(element)  # type: ignore[misc]
    levels = extract_levels(db, records, z, ion_stage)  # type: ignore[misc]
    lines = extract_lines(db, records, z, ion_stage)  # type: ignore[misc]
    level_by_index = {int(row["level_index"]): row for row in levels if row.get("level_index") is not None}
    level_set = set(level_by_index)
    rad_edges = []
    rad_by_upper: dict[int, list[dict[str, Any]]] = defaultdict(list)
    rad_by_level: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in lines:
        lo = _as_int(row.get("lower_level")); up = _as_int(row.get("upper_level")); A = _as_float(row.get("A_s^-1"))
        if lo is None or up is None or A is None or A <= 0:
            continue
        rad_edges.append((lo, up))
        rad_by_upper[up].append(row)
        rad_by_level[lo].append(row); rad_by_level[up].append(row)
    _, _, coll_eval = extract_collisions(db, records, z, ion_stage, [temperature], electron_density_cm3=electron_density)  # type: ignore[misc]
    class _Args:
        collision_rate_scale = 1.0
        _collision_data_type_scales = {}
        _collision_pair_scales = {}
        _collision_record_scales = {}
        _collision_record_direction_scales = {}
        collision_type69_ground_excitation_mode = "include"
    coll_T = build_collision_rates_for_T(coll_eval, level_set, temperature, electron_density, _Args())  # type: ignore[misc]
    coll_edges = []
    coll_by_level: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in coll_T:
        lo = _as_int(row.get("lower_level")); up = _as_int(row.get("upper_level"))
        if lo is None or up is None:
            continue
        exc = _as_float(row.get("C_excitation_s^-1")) or 0.0
        de = _as_float(row.get("C_deexcitation_s^-1")) or 0.0
        if exc > 0 or de > 0:
            coll_edges.append((lo, up))
            coll_by_level[lo].append(row); coll_by_level[up].append(row)
    comp = _build_level_components(level_set, rad_edges, coll_edges)
    return {
        "level_by_index": level_by_index,
        "rad_by_upper": rad_by_upper,
        "rad_by_level": rad_by_level,
        "coll_by_level": coll_by_level,
        "component_id_by_level": comp,
        "component_sizes": {cid: sum(1 for x in comp.values() if x == cid) for cid in set(comp.values())},
    }


def _dominant_radiative(level: int, atdb_context: dict[str, Any], combined_lines: list[dict[str, str]]) -> dict[str, Any]:
    # Prefer ATDB full radiative decay rates if available.
    rows = atdb_context.get("rad_by_upper", {}).get(level, []) if atdb_context else []
    best = None
    best_rate = -1.0
    for row in rows:
        rate = _as_float(row.get("A_s^-1")) or 0.0
        if rate > best_rate:
            best = row; best_rate = rate
    if best is not None:
        return {
            "dominant_radiative_path": f"{level}->{best.get('lower_level')}",
            "dominant_radiative_to_level": best.get("lower_level"),
            "dominant_radiative_to_label": best.get("lower_label"),
            "dominant_radiative_A_s^-1": best_rate,
            "dominant_radiative_record": best.get("record"),
            "dominant_radiative_source": "ATDB A-value",
        }
    # Fall back to selected line outputs for existing archives.
    for row in sorted(combined_lines, key=lambda r: _as_float(r.get("A_s^-1")) or -1.0, reverse=True):
        if _as_int(row.get("upper_level")) == level:
            return {
                "dominant_radiative_path": f"{level}->{row.get('lower_level')}",
                "dominant_radiative_to_level": row.get("lower_level"),
                "dominant_radiative_to_label": row.get("lower_label"),
                "dominant_radiative_A_s^-1": _as_float(row.get("A_s^-1")),
                "dominant_radiative_record": row.get("record"),
                "dominant_radiative_source": "selected solver line CSV",
            }
    return {"dominant_radiative_path": "", "dominant_radiative_source": "unavailable"}


def _dominant_collision(level: int, atdb_context: dict[str, Any]) -> dict[str, Any]:
    rows = atdb_context.get("coll_by_level", {}).get(level, []) if atdb_context else []
    best = None; best_rate = -1.0; best_kind = ""
    for row in rows:
        lo = _as_int(row.get("lower_level")); up = _as_int(row.get("upper_level"))
        exc = _as_float(row.get("C_excitation_s^-1")) or 0.0
        de = _as_float(row.get("C_deexcitation_s^-1")) or 0.0
        if lo == level and exc > best_rate:
            best, best_rate, best_kind = row, exc, "sink/excitation"
        if up == level and de > best_rate:
            best, best_rate, best_kind = row, de, "sink/deexcitation"
        if up == level and exc > best_rate:
            best, best_rate, best_kind = row, exc, "source/excitation_into_level"
        if lo == level and de > best_rate:
            best, best_rate, best_kind = row, de, "source/deexcitation_into_level"
    if best is None:
        return {"dominant_collision_path": "", "dominant_collision_source": "unavailable"}
    lo = _as_int(best.get("lower_level")); up = _as_int(best.get("upper_level"))
    if best_kind.endswith("excitation") or best_kind.startswith("sink/excitation"):
        path = f"{lo}->{up}"
    else:
        path = f"{up}->{lo}"
    return {
        "dominant_collision_path": path,
        "dominant_collision_kind": best_kind,
        "dominant_collision_rate_s^-1": best_rate,
        "dominant_collision_record": best.get("record"),
        "dominant_collision_data_type": best.get("data_type"),
        "dominant_collision_method": best.get("eval_method"),
        "dominant_collision_source": "ATDB evaluated collision rate",
    }


def _population_by_level(pop_rows: list[dict[str, str]]) -> dict[int, float]:
    out = {}
    for row in pop_rows:
        lev = _as_int(row.get("level_index") or row.get("level"))
        if lev is None:
            continue
        val = _as_float(row.get("population_fraction") or row.get("population"))
        if val is not None:
            out[lev] = val
    return out


def _component_population(level: int, pop: dict[int, float], comp: dict[int, int]) -> tuple[float | None, int | None, int | None]:
    if not pop:
        return None, None, None
    cid = comp.get(level)
    if cid is None:
        return pop.get(level), None, None
    levels = [lev for lev, c in comp.items() if c == cid]
    total = sum(pop.get(lev, 0.0) for lev in levels)
    return total, cid, len(levels)


def _classify_level(row: dict[str, Any]) -> str:
    # Flags: zero response, negative raw response, no combined population, weak connectivity.
    reasons = []
    zeros = [row.get(f"response_{c}_is_zero") for c in TRIPLET_COMPONENTS]
    if all(zeros):
        reasons.append("zero f/i/r response")
    elif any(zeros):
        reasons.append("partial zero f/i/r response")
    neg = [_as_float(row.get(f"response_{c}_raw")) for c in TRIPLET_COMPONENTS]
    if any(x is not None and x < -NEGATIVE_RAW_TOL for x in neg):
        reasons.append("negative raw component")
    if row.get("weakly_connected"):
        reasons.append("weakly connected")
    if row.get("possibly_pruned_or_null_rate"):
        reasons.append("possibly pruned/null-rate")
    return "; ".join(reasons) if reasons else "active"




def _positive_response_norm(f: float | None, i: float | None, r: float | None) -> tuple[float, float, float]:
    vals = [max(_as_float(x) or 0.0, 0.0) for x in (f, i, r)]
    total = sum(vals)
    if total <= ZERO_TOL:
        return 0.0, 0.0, 0.0
    return tuple(v / total for v in vals)  # type: ignore[return-value]


def _fit_contributions_from_raw(weight: float | None, f: float | None, i: float | None, r: float | None) -> tuple[float, float, float]:
    w = _as_float(weight) or 0.0
    nf, ni, nr = _positive_response_norm(f, i, r)
    return w * nf, w * ni, w * nr

def _collect_fit_dir(run_tag: str, fit_dir: Path, fitsfile: str | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    summary_path = _find_fit_summary(fit_dir)
    summary = _read_json(summary_path)
    tag = run_tag
    prefix = _ion_prefix(tag, summary)
    density = _as_float(summary.get("electron_density_cm^-3"))
    element = str(summary.get("element") or "")
    ion_stage = _as_int(summary.get("ion_stage")) or 0
    temperature = _as_float(summary.get("temperature_K")) or 1.0e6
    matrix_rows = _read_csv(_find_response_matrix(fit_dir, prefix))
    weight_rows = _read_csv(_find_weight_csv(fit_dir, prefix))
    merged = _merge_response_and_weights(matrix_rows, weight_rows)
    combined_summary = summary.get("combined_source_validation") or {}
    cdir = fit_dir / "combined_source_validation"
    combined_lines = _read_csv(_find_combined_file(fit_dir, prefix, "combined_solver_lines.csv"))
    combined_pops = _read_csv(_find_combined_file(fit_dir, prefix, "combined_solver_populations.csv"))
    combined_trans = _read_csv(_find_combined_file(fit_dir, prefix, "combined_solver_transitions.csv"))
    # New v0.3.0 files are named o7_combined_solver_populations.csv/transitions.csv; older archives have none.
    if not combined_pops:
        combined_pops = _read_csv(_find_first([cdir / "o7_combined_solver_populations.csv", *cdir.glob("*_combined_solver_populations.csv")]))
    if not combined_trans:
        combined_trans = _read_csv(_find_first([cdir / "o7_combined_solver_transitions.csv", *cdir.glob("*_combined_solver_transitions.csv")]))
    pop = _population_by_level(combined_pops)
    atdb_context = _build_atdb_context(fitsfile, element, ion_stage, temperature, density or 1.0) if fitsfile and element and ion_stage else {}
    # If no ATDB context, derive weak graph from combined selected output lines only.
    comp = atdb_context.get("component_id_by_level", {}) if atdb_context else {}
    rows: list[dict[str, Any]] = []
    for lev in sorted(merged):
        data = merged[lev]
        label = ""
        config = ""
        if atdb_context:
            levrow = atdb_context.get("level_by_index", {}).get(lev, {})
            label = str(levrow.get("level_label") or "")
            config = label
        if not label:
            label = _safe_label_from_rows(lev, combined_lines)
            config = label
        f = _as_float(data.get("response_raw_forbidden") or data.get("weight_raw_forbidden_per_unit_source"))
        i = _as_float(data.get("response_raw_intercombination") or data.get("weight_raw_intercombination_per_unit_source"))
        r = _as_float(data.get("response_raw_resonance") or data.get("weight_raw_resonance_per_unit_source"))
        source_weight = _as_float(data.get("weight_fit_weight_norm"))
        nf, ni, nr = _positive_response_norm(f, i, r)
        fn, inn, rn = _fit_contributions_from_raw(source_weight, f, i, r)
        comp_pop, cid, comp_size = _component_population(lev, pop, comp)
        rad = _dominant_radiative(lev, atdb_context, combined_lines)
        coll = _dominant_collision(lev, atdb_context)
        raw_abs_sum = sum(abs(x or 0.0) for x in (f, i, r))
        weak = False
        if atdb_context and cid is not None:
            weak = (comp_size or 0) <= 1
        elif raw_abs_sum == 0:
            weak = True
        row: dict[str, Any] = {
            "tag": tag,
            "fit_dir": str(fit_dir),
            "density_cm^-3": density,
            "element": element,
            "ion_stage": ion_stage,
            "source_level": lev,
            "source_level_label": label,
            "source_level_configuration": config,
            "fitted_source_weight": source_weight,
            "fit_source_rate_s^-1": _as_float(data.get("weight_fit_source_rate_s^-1")),
            "response_forbidden_raw": f,
            "response_intercombination_raw": i,
            "response_resonance_raw": r,
            "response_forbidden_norm": nf,
            "response_intercombination_norm": ni,
            "response_resonance_norm": nr,
            "fit_contribution_forbidden": fn,
            "fit_contribution_intercombination": inn,
            "fit_contribution_resonance": rn,
            "response_forbidden_is_zero": abs(f or 0.0) <= ZERO_TOL,
            "response_intercombination_is_zero": abs(i or 0.0) <= ZERO_TOL,
            "response_resonance_is_zero": abs(r or 0.0) <= ZERO_TOL,
            "solver_population_source_level": pop.get(lev),
            "solver_population_source_component": comp_pop,
            "source_component_id": cid,
            "source_component_n_levels": comp_size,
            "population_source": "combined solver population CSV" if pop else "unavailable; rerun v0.3.0 examples/20--22 to emit populations",
            "possibly_pruned_or_null_rate": bool(raw_abs_sum == 0 and (source_weight or 0.0) > 0),
            "weakly_connected": weak,
            "combined_R": _as_float(combined_summary.get("R_f_over_i")),
            "combined_G": _as_float(combined_summary.get("G_f_plus_i_over_r")),
            "combined_solver_residual_l2": _as_float((combined_summary.get("solver_diagnostics") or {}).get("linear_residual_l2")),
            "combined_solver_warning": (combined_summary.get("solver_diagnostics") or {}).get("solver_warning"),
        }
        row.update(rad)
        row.update(coll)
        row["level_failure_flags"] = _classify_level(row)
        rows.append(row)
    nonzero = [r for r in rows if (_as_float(r.get("fitted_source_weight")) or 0) > 1.0e-8]
    bad = [r for r in rows if r["level_failure_flags"] != "active"]
    zero_response_weight_sum = sum(
        (_as_float(r.get("fitted_source_weight")) or 0.0)
        for r in rows
        if all(bool(r.get(f"response_{c}_is_zero")) for c in TRIPLET_COMPONENTS)
    )
    negative_response_weight_sum = sum(
        (_as_float(r.get("fitted_source_weight")) or 0.0)
        for r in rows
        if any((_as_float(r.get(f"response_{c}_raw")) or 0.0) < -NEGATIVE_RAW_TOL for c in TRIPLET_COMPONENTS)
    )
    summary_row = {
        "tag": tag,
        "fit_dir": str(fit_dir),
        "density_cm^-3": density,
        "element": element,
        "ion_stage": ion_stage,
        "n_source_levels": len(rows),
        "n_nonzero_fitted_weights": len(nonzero),
        "n_levels_with_failure_flags": len(bad),
        "n_all_zero_response": sum(1 for r in rows if all(r.get(f"response_{c}_is_zero") for c in TRIPLET_COMPONENTS)),
        "n_partial_zero_response": sum(1 for r in rows if any(r.get(f"response_{c}_is_zero") for c in TRIPLET_COMPONENTS) and not all(r.get(f"response_{c}_is_zero") for c in TRIPLET_COMPONENTS)),
        "n_negative_raw_response": sum(1 for r in rows if any((_as_float(r.get(f"response_{c}_raw")) or 0.0) < -NEGATIVE_RAW_TOL for c in TRIPLET_COMPONENTS)),
        "n_population_available": sum(1 for r in rows if r.get("solver_population_source_level") not in (None, "")),
        "population_status": "available" if any(r.get("solver_population_source_level") not in (None, "") for r in rows) else "unavailable",
        "zero_response_fitted_weight_sum": zero_response_weight_sum,
        "negative_response_fitted_weight_sum": negative_response_weight_sum,
        "n_weakly_connected": sum(1 for r in rows if r.get("weakly_connected")),
        "max_fit_weight_level": max(rows, key=lambda r: _as_float(r.get("fitted_source_weight")) or -1).get("source_level") if rows else None,
        "max_fit_weight": max((_as_float(r.get("fitted_source_weight")) or 0.0) for r in rows) if rows else None,
        "combined_R": _as_float(combined_summary.get("R_f_over_i")),
        "combined_G": _as_float(combined_summary.get("G_f_plus_i_over_r")),
        "combined_solver_residual_l2": _as_float((combined_summary.get("solver_diagnostics") or {}).get("linear_residual_l2")),
    }
    return rows, summary_row


def _collect_run(run_dir: Path, fitsfile: str | None, densities: set[float] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    fit_dirs = sorted([p for p in run_dir.glob("fit_ne_*") if p.is_dir()], key=_density_sort_key)
    if densities:
        fit_dirs = [p for p in fit_dirs if _density_sort_key(p) in densities]
    first_summary = _read_json(_find_fit_summary(fit_dirs[0])) if fit_dirs else {}
    tag = _infer_tag(run_dir, first_summary)
    all_rows: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    if not fit_dirs:
        summaries.append({
            "tag": tag,
            "fit_dir": "",
            "density_cm^-3": None,
            "element": first_summary.get("element", ""),
            "ion_stage": first_summary.get("ion_stage", ""),
            "n_source_levels": 0,
            "n_nonzero_fitted_weights": 0,
            "n_levels_with_failure_flags": 0,
            "n_all_zero_response": 0,
            "n_partial_zero_response": 0,
            "n_negative_raw_response": 0,
            "n_population_available": None,
            "population_status": "unavailable",
            "n_weakly_connected": 0,
            "max_fit_weight_level": None,
            "max_fit_weight": None,
            "combined_R": None,
            "combined_G": None,
            "combined_solver_residual_l2": None,
            "run_warning": f"No fit_ne_* directories found under {run_dir}; run examples/22 after the XSTAR mapping CSV points to converted triplet files.",
        })
        return all_rows, summaries
    for fit_dir in fit_dirs:
        rows, summary = _collect_fit_dir(tag, fit_dir, fitsfile)
        all_rows.extend(rows)
        summaries.append(summary)
    return all_rows, summaries


def _write_markdown(path: Path, summaries: list[dict[str, Any]], rows: list[dict[str, Any]], top_n: int = 12) -> None:
    lines = ["# He-like source-level failure diagnostics", ""]
    lines += [
        "This diagnostic compares fitted source levels, response components, population availability, and dominant rate paths.",
        "Population and full collisional/radiative path columns require either v0.3.0 combined-solver population/transition outputs or `--fitsfile` ATDB context.",
        "",
        "## Density-level summary",
        "",
        "| tag | density | levels | nonzero weights | all-zero response | zero-response weight | partial-zero response | negative raw response | negative-response weight | weakly connected | population | combined R/G | residual L2 | warning |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---|",
    ]
    for s in summaries:
        lines.append(
            f"| {s['tag']} | {_fmt(s['density_cm^-3'])} | {s['n_source_levels']} | {s['n_nonzero_fitted_weights']} | "
            f"{s['n_all_zero_response']} | {_fmt(s.get('zero_response_fitted_weight_sum'))} | {s['n_partial_zero_response']} | "
            f"{s['n_negative_raw_response']} | {_fmt(s.get('negative_response_fitted_weight_sum'))} | {s['n_weakly_connected']} | "
            f"{s.get('population_status', s.get('n_population_available', 'unavailable'))} | {_fmt(s['combined_R'])}/{_fmt(s['combined_G'])} | {_fmt(s['combined_solver_residual_l2'])} | {s.get('run_warning','')} |"
        )
    lines += ["", "## Highest-weight source levels with failure flags", "", "| tag | density | level | label | weight | response f/i/r | contribution f/i/r | component population | dominant radiative | dominant collision | flags |", "|---|---:|---:|---|---:|---:|---:|---:|---|---|---|"]
    top_rows = sorted(rows, key=lambda r: (_as_float(r.get("fitted_source_weight")) or 0.0), reverse=True)[:top_n]
    for r in top_rows:
        lines.append(
            f"| {r['tag']} | {_fmt(r['density_cm^-3'])} | {r['source_level']} | {r.get('source_level_label','')} | {_fmt(r['fitted_source_weight'])} | "
            f"{_fmt(r['response_forbidden_raw'])}/{_fmt(r['response_intercombination_raw'])}/{_fmt(r['response_resonance_raw'])} | "
            f"{_fmt(r['fit_contribution_forbidden'])}/{_fmt(r['fit_contribution_intercombination'])}/{_fmt(r['fit_contribution_resonance'])} | "
            f"{_fmt(r.get('solver_population_source_component'))} | {r.get('dominant_radiative_path','')} | {r.get('dominant_collision_path','')} | {r.get('level_failure_flags','')} |"
        )
    lines += [
        "",
        "## Interpretation guide",
        "",
        "- `all-zero response` means the source level contributes no usable f/i/r response in the unit-source matrix.",
        "- `partial-zero response` means at least one of f, i, or r is missing; these levels can make R or G undefined even when the formal fit has nonzero weight.",
        "- `negative raw response` indicates the linearized response is not physically positive for one or more components; this commonly correlates with rank-deficient/ill-conditioned simultaneous solves.",
        "- `population = unavailable` means the run folder does not contain the v0.3.0 combined-solver population export; rerunning examples/20--22 with v0.3.1 or newer will fill those columns.",
        "- A row with `levels = 0` means no `fit_ne_*` output directories were found; usually the density-grid driver only wrote a template mapping and exited before running fits.",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dirs", nargs="+", type=Path, help="Density-grid output directories from examples/22.")
    parser.add_argument("--fitsfile", help="Optional atdb.fits for level labels and dominant radiative/collisional paths.")
    parser.add_argument("--densities", nargs="*", type=float, help="Optional density subset to inspect.")
    parser.add_argument("--out-dir", type=Path, default=Path("helike_source_level_failure_diagnostics"))
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()

    densities = set(args.densities) if args.densities else None
    all_rows: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    for run_dir in args.run_dirs:
        rows, ss = _collect_run(run_dir, args.fitsfile, densities)
        all_rows.extend(rows)
        summaries.extend(ss)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(args.out_dir / "helike_source_level_diagnostics.csv", all_rows)
    _write_csv(args.out_dir / "helike_source_level_density_summary.csv", summaries)
    with (args.out_dir / "helike_source_level_diagnostics.json").open("w") as handle:
        json.dump({"density_summaries": summaries, "source_levels": all_rows}, handle, indent=2)
    _write_markdown(args.out_dir / "helike_source_level_diagnostics.md", summaries, all_rows, top_n=args.top_n)

    if args.print_summary:
        print("He-like source-level failure diagnostics")
        print("-----------------------------------------")
        for s in summaries:
            print(
                f"{s['tag']} ne={_fmt(s['density_cm^-3'])}: "
                f"levels={s['n_source_levels']} nonzero={s['n_nonzero_fitted_weights']} "
                f"zero={s['n_all_zero_response']} partial_zero={s['n_partial_zero_response']} "
                f"negative={s['n_negative_raw_response']} weak={s['n_weakly_connected']} "
                f"zero_w={_fmt(s.get('zero_response_fitted_weight_sum'))} neg_w={_fmt(s.get('negative_response_fitted_weight_sum'))} "
                f"pop={s.get('population_status', s.get('n_population_available', 'unavailable'))} residual={_fmt(s['combined_solver_residual_l2'])}"
                + (f" warning={s.get('run_warning')}" if s.get('run_warning') else "")
            )
        print(f"wrote: {args.out_dir / 'helike_source_level_diagnostics.md'}")


if __name__ == "__main__":
    main()
