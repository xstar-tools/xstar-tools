#!/usr/bin/env python3
"""C V He-like triplet f/r source-attribution and source-group scan.

This diagnostic is deliberately post-processing only.  It reads an existing
``examples/42_xstar_like_element_solver_demo.py`` output directory, attributes
triplet-source routes using the emitted audit CSVs, and then reruns the existing
full-global normalized solve after applying controlled scale factors to selected
source-family rows.

The default scan is aimed at the v0.3.104 C V residual: intercombination is now
close to the XSTAR reference, while forbidden is high and resonance is low.  The
script therefore leaves type-50 1s2p 3P_J -> 1s2s 3S1 line-escape/drain terms
unchanged and scans superlevel/source/cascade groups instead.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

def _install_minimal_astropy_fits_stub() -> None:
    # The source-attribution example only needs post-processing/solve helpers
    # from xstar_element_solver; it never opens FITS files.  Some lightweight CI
    # environments used for package tests do not install astropy, while the
    # package import path imports hierarchy.py.  A minimal stub lets us import the
    # solver helpers without weakening normal runtime behavior.
    import sys
    import types

    if "astropy.io.fits" in sys.modules:
        return
    astropy = sys.modules.get("astropy") or types.ModuleType("astropy")
    io = sys.modules.get("astropy.io") or types.ModuleType("astropy.io")
    fits = types.ModuleType("astropy.io.fits")
    io.fits = fits
    astropy.io = io
    sys.modules.setdefault("astropy", astropy)
    sys.modules.setdefault("astropy.io", io)
    sys.modules.setdefault("astropy.io.fits", fits)


try:
    from xstar_atomic.xstar_element_solver import build_full_global_normalized_solve_comparison  # type: ignore
    _HAS_XSTAR_ELEMENT_SOLVER = True
except ModuleNotFoundError as exc:  # pragma: no cover - minimal environments without astropy
    if "astropy" in str(exc):
        try:
            _install_minimal_astropy_fits_stub()
            from xstar_atomic.xstar_element_solver import build_full_global_normalized_solve_comparison  # type: ignore
            _HAS_XSTAR_ELEMENT_SOLVER = True
        except Exception as exc2:
            build_full_global_normalized_solve_comparison = None  # type: ignore
            _HAS_XSTAR_ELEMENT_SOLVER = False
            _XSTAR_ELEMENT_SOLVER_IMPORT_ERROR = str(exc2)
    else:
        build_full_global_normalized_solve_comparison = None  # type: ignore
        _HAS_XSTAR_ELEMENT_SOLVER = False
        _XSTAR_ELEMENT_SOLVER_IMPORT_ERROR = str(exc)
except Exception as exc:  # pragma: no cover
    build_full_global_normalized_solve_comparison = None  # type: ignore
    _HAS_XSTAR_ELEMENT_SOLVER = False
    _XSTAR_ELEMENT_SOLVER_IMPORT_ERROR = str(exc)


def write_csv(path: Path, rows: Sequence[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: List[str] = []
    for row in rows:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="") as f:
        if not fieldnames:
            f.write("")
            return
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


DEFAULT_CV_TARGET = (0.8077062192131096, 0.006633341501477327, 0.18566043928541306)


def _read_csv(path: Path) -> List[dict]:
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _maybe_float(value) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        x = float(value)
        return x if math.isfinite(x) else None
    s = str(value).strip()
    if not s or s.lower() in {"nan", "none", "null"}:
        return None
    try:
        x = float(s)
    except Exception:
        return None
    return x if math.isfinite(x) else None


def _maybe_int(value) -> Optional[int]:
    x = _maybe_float(value)
    if x is None:
        return None
    return int(round(x))


def _parse_scale_list(text: str) -> List[float]:
    out: List[float] = []
    for token in str(text or "").split(","):
        token = token.strip()
        if not token:
            continue
        out.append(float(token))
    return out or [1.0]


def _truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    return s in {"1", "true", "yes", "y", "t"}


def _classify_xstar_triplet_component(row: dict) -> Optional[str]:
    upper = str(row.get("upper_level") or row.get("upper") or "")
    wavelength = _maybe_float(row.get("wavelength") or row.get("wavelength_A"))
    return _classify_line_label_component(upper, wavelength)



def _classify_line_label_component(label: str, wavelength: Optional[float] = None) -> Optional[str]:
    s = str(label or "").lower().replace(" ", "")
    if "2s" in s and ".3s" in s:
        return "f"
    if "2p" in s and ".3p" in s:
        return "i"
    if "2p" in s and ".1p" in s:
        return "r"
    if wavelength is not None:
        if 41.3 <= wavelength <= 41.7:
            return "f"
        if 40.65 <= wavelength <= 40.80:
            return "i"
        if 40.15 <= wavelength <= 40.40:
            return "r"
    return None

def _triplet_target_from_xstar_csv(path: Optional[Path], value_column: str) -> Tuple[Optional[float], Optional[float], Optional[float], dict]:
    if path is None or not path.exists():
        return None, None, None, {"status": "not_provided"}
    rows = _read_csv(path)
    sums = {"f": 0.0, "i": 0.0, "r": 0.0}
    counts = {"f": 0, "i": 0, "r": 0, "unclassified": 0}
    for row in rows:
        comp = _classify_xstar_triplet_component(row)
        val = _maybe_float(row.get(value_column))
        if comp in sums and val is not None:
            sums[comp] += float(val)
            counts[comp] += 1
        else:
            counts["unclassified"] += 1
    total = sums["f"] + sums["i"] + sums["r"]
    meta = {"status": "ok" if total > 0 else "empty", "value_column": value_column, "component_sums": sums, "component_counts": counts, "total": total}
    if total <= 0:
        return None, None, None, meta
    return sums["f"] / total, sums["i"] / total, sums["r"] / total, meta


def _l2(f: Optional[float], i: Optional[float], r: Optional[float], target: Tuple[Optional[float], Optional[float], Optional[float]]) -> Optional[float]:
    if f is None or i is None or r is None or any(x is None for x in target):
        return None
    return float(math.sqrt((float(f) - float(target[0])) ** 2 + (float(i) - float(target[1])) ** 2 + (float(r) - float(target[2])) ** 2))


def _ratio_R_G(f: Optional[float], i: Optional[float], r: Optional[float]) -> Tuple[Optional[float], Optional[float]]:
    R = None if f is None or i in (None, 0.0) else float(f) / float(i)
    G = None if f is None or i is None or r in (None, 0.0) else (float(f) + float(i)) / float(r)
    return R, G


def _summary_from_solve(rows: Sequence[dict]) -> dict:
    for row in rows:
        if row.get("row_kind") == "summary" and row.get("comparison_case") == "full_global_normalized_proxy_topology_solve":
            return dict(row)
    return {}


def _component_from_global_index(global_index_rows: Sequence[dict]) -> Dict[int, str]:
    out: Dict[int, str] = {}
    for row in global_index_rows:
        g = _maybe_int(row.get("global_index"))
        comp = str(row.get("triplet_component") or "").strip().lower()
        if g is not None and comp in {"f", "i", "r"}:
            out[int(g)] = comp
    return out


def _is_offdiag_gain(row: dict) -> bool:
    kind = str(row.get("matrix_term_kind") or "").lower()
    role = str(row.get("matrix_role") or "").lower()
    signed = _maybe_float(row.get("full_global_signed_rate_s^-1") or row.get("signed_rate_s^-1"))
    return ("offdiag" in kind or "gain" in role) and signed is not None and signed > 0


def _family_for_row(row: dict, triplet_by_global: Dict[int, str]) -> Optional[str]:
    comp = str(row.get("full_global_component") or "")
    if not comp or comp.lower() == "nan":
        return None
    super_label = str(row.get("superlevel_level_label") or "")
    role = str(row.get("matrix_role") or "")
    kind = str(row.get("matrix_term_kind") or "")
    row_g = _maybe_int(row.get("matrix_row_global_index"))
    dest_comp = str(row.get("triplet_component") or row.get("destination_triplet_component") or "").strip().lower()
    if row_g is not None and not dest_comp:
        dest_comp = triplet_by_global.get(int(row_g), "")

    if comp == "type71_superlevel_cascade":
        if super_label == "sprlevlt":
            return "type71_from_sprlevlt"
        if super_label == "sprlevls":
            return "type71_from_sprlevls"
        if super_label == "superlev":
            return "type71_from_superlev"
        return "type71_from_other_superlevel"
    if comp == "type99_calt99_recombination_source":
        if "M[type99_destination,parent_continuum]" not in role and "offdiag" not in kind:
            # still scale paired diagonal with the same family below in scan, but
            # attribution avoids double-counting branch proxies from diagonal loss.
            pass
        if super_label == "sprlevlt":
            return "type99_into_sprlevlt"
        if super_label == "sprlevls":
            return "type99_into_sprlevls"
        if _truthy(row.get("type99_parent_maps_to_target_continuum_alias")) or _maybe_int(row.get("superlevel_level")) == 32:
            return "type99_continuum_alias_level32"
        return "type99_into_other_superlevel"
    if comp == "type53_xstar_ucalc_phint53_milne_inverse":
        return "type53_milne_inverse"
    if comp == "type74_calt74_inverse_recombination_diagnostic":
        return "type74_inverse_or_direct"
    if comp == "bound_bound_blocks_CVI_CV":
        if dest_comp in {"f", "i", "r"}:
            source_method = str(row.get("source_method") or "")
            trans = str(row.get("transition_kind") or "")
            if "data_type_50" in source_method or trans == "radiative_decay":
                return "direct_bound_bound_radiative_paths"
            if "collision" in trans or "type63" in source_method or "type56" in source_method or "type69" in source_method:
                return "direct_bound_bound_collisional_paths"
            return "direct_bound_bound_other_paths"
    return None


def _rate_value(row: dict) -> float:
    for key in ("full_global_signed_rate_s^-1", "signed_rate_s^-1", "full_global_rate_s^-1", "rate_s^-1"):
        x = _maybe_float(row.get(key))
        if x is not None:
            return float(x)
    return 0.0


def _make_attribution_rows(full_terms: Sequence[dict], global_index_rows: Sequence[dict]) -> List[dict]:
    triplet_by_global = _component_from_global_index(global_index_rows)
    families: Dict[str, dict] = {}

    def rec(name: str) -> dict:
        if name not in families:
            families[name] = {
                "source_family": name,
                "n_matrix_rows": 0,
                "n_offdiag_gain_rows": 0,
                "positive_gain_sum_s^-1": 0.0,
                "negative_loss_sum_s^-1": 0.0,
                "direct_f_gain_s^-1": 0.0,
                "direct_i_gain_s^-1": 0.0,
                "direct_r_gain_s^-1": 0.0,
                "branch_proxy_f_s^-1": 0.0,
                "branch_proxy_i_s^-1": 0.0,
                "branch_proxy_r_s^-1": 0.0,
                "example_records": [],
                "notes": "",
            }
        return families[name]

    for row in full_terms:
        fam = _family_for_row(row, triplet_by_global)
        if not fam:
            continue
        r = rec(fam)
        r["n_matrix_rows"] += 1
        rate = _rate_value(row)
        if rate > 0 and _is_offdiag_gain(row):
            r["n_offdiag_gain_rows"] += 1
            r["positive_gain_sum_s^-1"] += rate
            row_g = _maybe_int(row.get("matrix_row_global_index"))
            comp = str(row.get("triplet_component") or row.get("destination_triplet_component") or "").strip().lower()
            if row_g is not None and comp not in {"f", "i", "r"}:
                comp = triplet_by_global.get(int(row_g), "")
            if comp in {"f", "i", "r"}:
                r[f"direct_{comp}_gain_s^-1"] += rate
        elif rate < 0:
            r["negative_loss_sum_s^-1"] += abs(rate)
        # Type-99 has branch-proxy columns in the source matrix terms; only count
        # offdiag source rows to avoid double-counting the paired parent loss.
        if fam.startswith("type99_") and _is_offdiag_gain(row):
            base = _maybe_float(row.get("rate_s^-1") or row.get("full_global_rate_s^-1")) or 0.0
            for comp in ("f", "i", "r"):
                b = _maybe_float(row.get(f"type71_B_{comp}"))
                if b is not None:
                    r[f"branch_proxy_{comp}_s^-1"] += float(base) * float(b)
        recid = row.get("record")
        if recid not in (None, "", "nan") and len(r["example_records"]) < 8:
            r["example_records"].append(str(recid))

    rows: List[dict] = []
    for name, r in sorted(families.items()):
        total_direct = r["direct_f_gain_s^-1"] + r["direct_i_gain_s^-1"] + r["direct_r_gain_s^-1"]
        total_proxy = r["branch_proxy_f_s^-1"] + r["branch_proxy_i_s^-1"] + r["branch_proxy_r_s^-1"]
        rr = dict(r)
        rr["direct_f_fraction_within_family"] = r["direct_f_gain_s^-1"] / total_direct if total_direct > 0 else ""
        rr["direct_i_fraction_within_family"] = r["direct_i_gain_s^-1"] / total_direct if total_direct > 0 else ""
        rr["direct_r_fraction_within_family"] = r["direct_r_gain_s^-1"] / total_direct if total_direct > 0 else ""
        rr["branch_proxy_f_fraction_within_family"] = r["branch_proxy_f_s^-1"] / total_proxy if total_proxy > 0 else ""
        rr["branch_proxy_i_fraction_within_family"] = r["branch_proxy_i_s^-1"] / total_proxy if total_proxy > 0 else ""
        rr["branch_proxy_r_fraction_within_family"] = r["branch_proxy_r_s^-1"] / total_proxy if total_proxy > 0 else ""
        rr["example_records"] = ";".join(r["example_records"])
        if name == "type71_from_sprlevlt":
            rr["notes"] = "type-71 cascade out of sprlevlt; often feeds triplet/intercombination branches"
        elif name == "type71_from_sprlevls":
            rr["notes"] = "type-71 cascade out of sprlevls; includes resonance/singlet cascade branch"
        elif name.startswith("type99"):
            rr["notes"] = "type-99 calt99/phint53hunt source into a superlevel; branch proxy uses type71_B_f/i/r columns"
        rows.append(rr)
    return rows


def _match_scale_group(row: dict, group: str, triplet_by_global: Dict[int, str]) -> bool:
    comp = str(row.get("full_global_component") or "")
    super_label = str(row.get("superlevel_level_label") or "")
    row_g = _maybe_int(row.get("matrix_row_global_index"))
    trip = str(row.get("triplet_component") or row.get("destination_triplet_component") or "").strip().lower()
    if row_g is not None and trip not in {"f", "i", "r"}:
        trip = triplet_by_global.get(int(row_g), "")
    # Keep all type50 drains fixed: this function never matches bound-bound rows.
    if group == "type99_into_sprlevlt":
        return comp == "type99_calt99_recombination_source" and super_label == "sprlevlt"
    if group == "type99_into_sprlevls":
        return comp == "type99_calt99_recombination_source" and super_label == "sprlevls"
    if group == "type99_continuum_alias_level32":
        return comp == "type99_calt99_recombination_source" and (_truthy(row.get("type99_parent_maps_to_target_continuum_alias")) or _maybe_int(row.get("superlevel_level")) == 32)
    if group == "type71_from_sprlevlt":
        return comp == "type71_superlevel_cascade" and super_label == "sprlevlt"
    if group == "type71_from_sprlevls":
        return comp == "type71_superlevel_cascade" and super_label == "sprlevls"
    if group == "type71_resonance_singlet_cascade":
        # Scale the type-71 record pair whose offdiag/gain destination is the resonance/singlet upper.
        # The paired diagonal loss rows share destination flags in the audit rows.
        return comp == "type71_superlevel_cascade" and (trip == "r" or _truthy(row.get("feeds_resonance_upper")))
    if group == "type53_milne_inverse_to_resonance":
        return comp == "type53_xstar_ucalc_phint53_milne_inverse" and trip == "r"
    if group == "type74_inverse_to_resonance":
        return comp == "type74_calt74_inverse_recombination_diagnostic" and trip == "r"
    return False


def _scale_terms(rows: Sequence[dict], group: str, scale: float, triplet_by_global: Dict[int, str]) -> Tuple[List[dict], int, float]:
    out: List[dict] = []
    n = 0
    abs_sum = 0.0
    for row in rows:
        rr = dict(row)
        if _match_scale_group(rr, group, triplet_by_global):
            n += 1
            for key in ("full_global_signed_rate_s^-1", "signed_rate_s^-1", "full_global_rate_s^-1", "rate_s^-1"):
                x = _maybe_float(rr.get(key))
                if x is not None:
                    if "signed" in key:
                        rr[key] = float(x) * float(scale)
                    else:
                        rr[key] = float(x) * abs(float(scale))
                    abs_sum += abs(float(x))
            rr["cv_source_scan_scaled_group"] = group
            rr["cv_source_scan_scale_factor"] = float(scale)
        out.append(rr)
    return out, n, abs_sum



def _local_fallback_normalized_solve(
    *,
    global_index_rows: Sequence[dict],
    full_terms: Sequence[dict],
    line_rows: Sequence[dict],
    he_like_stage: int,
    target: Tuple[Optional[float], Optional[float], Optional[float]],
) -> dict:
    """Minimal dense normalized solve used only when the package solver cannot import.

    The normal runtime path uses ``build_full_global_normalized_solve_comparison``.
    This fallback keeps the example runnable in stripped-down CI containers where
    optional FITS dependencies such as astropy are absent.  It is intentionally
    labeled in the output and should not be used as the source-code-aligned XSTAR
    Lucy comparison.
    """
    indexed = []
    for r in global_index_rows:
        g = _maybe_int(r.get("global_index"))
        if g is not None:
            rr = dict(r)
            rr["global_index"] = int(g)
            indexed.append(rr)
    if not indexed:
        return {"solve_status": "empty", "solver": "local_fallback_svd", "solver_warning": "no global index rows"}
    n = max(int(r["global_index"]) for r in indexed) + 1
    M = np.zeros((n, n), dtype=float)
    used = 0
    for t in full_terms:
        row = _maybe_int(t.get("matrix_row_global_index"))
        col = _maybe_int(t.get("matrix_col_global_index"))
        if row is None or col is None or row < 0 or col < 0 or row >= n or col >= n:
            continue
        rate = _maybe_float(t.get("full_global_signed_rate_s^-1"))
        if rate is None:
            rate = _maybe_float(t.get("signed_rate_s^-1"))
        if rate is None:
            continue
        M[row, col] += float(rate)
        used += 1
    row_norm = np.sum(np.abs(M), axis=1)
    col_norm = np.sum(np.abs(M), axis=0)
    active = [i for i in range(n) if row_norm[i] > 1e-300 or col_norm[i] > 1e-300]
    if not active:
        active = list(range(n))
    A = M[np.ix_(active, active)].copy()
    b = np.zeros(len(active), dtype=float)
    A[0, :] = 1.0
    b[0] = 1.0
    try:
        x, *_ = np.linalg.lstsq(A, b, rcond=None)
        status = "ok"
    except Exception as exc:
        x = np.zeros(len(active), dtype=float)
        status = f"failed:{exc}"
    pop = np.zeros(n, dtype=float)
    for j, g in enumerate(active):
        pop[g] = x[j]
    level_to_g = {}
    for r in indexed:
        if _maybe_int(r.get("ion_stage")) == int(he_like_stage):
            lev = _maybe_int(r.get("level_index"))
            g = _maybe_int(r.get("global_index"))
            if lev is not None and g is not None:
                level_to_g[int(lev)] = int(g)
    sums = {"f": 0.0, "i": 0.0, "r": 0.0}
    for line in line_rows:
        if _maybe_int(line.get("ion_stage")) != int(he_like_stage):
            continue
        upper = _maybe_int(line.get("upper_level"))
        if upper is None or int(upper) not in level_to_g:
            continue
        comp = _classify_line_label_component(str(line.get("upper_label") or line.get("upper_level_label") or ""), _maybe_float(line.get("wavelength_A")))
        if comp not in sums:
            continue
        Aij = _maybe_float(line.get("A_s^-1")) or 0.0
        eev = _maybe_float(line.get("energy_eV")) or 1.0
        sums[comp] += max(0.0, float(pop[level_to_g[int(upper)]]) * float(Aij) * float(eev))
    total = sums["f"] + sums["i"] + sums["r"]
    if total > 0:
        f, i, r = sums["f"] / total, sums["i"] / total, sums["r"] / total
    else:
        f = i = r = None
    R, G = _ratio_R_G(f, i, r)
    return {
        "f_fraction": f,
        "i_fraction": i,
        "r_fraction": r,
        "R": R,
        "G": G,
        "l2_distance_to_target": _l2(f, i, r, target),
        "solve_status": status,
        "solver": "local_fallback_svd",
        "solver_warning": f"xstar_element_solver import unavailable; used local fallback solve: {globals().get('_XSTAR_ELEMENT_SOLVER_IMPORT_ERROR', '')}",
        "n_negative_populations": int(np.sum(pop < -1e-12)),
        "sum_population": float(np.sum(pop)),
        "rows_by_component_used": "{}",
        "n_matrix_rows_used_local_fallback": used,
    }

def _run_solve(
    *,
    global_index_rows: Sequence[dict],
    full_terms: Sequence[dict],
    line_rows: Sequence[dict],
    he_like_stage: int,
    topology: str,
    linear_solver: str,
    ion_fraction_closure: str,
    calc_ion_rates_rows: Sequence[dict],
    temperature_K: Optional[float],
    electron_density: Optional[float],
    target: Tuple[Optional[float], Optional[float], Optional[float]],
) -> dict:
    if not _HAS_XSTAR_ELEMENT_SOLVER or build_full_global_normalized_solve_comparison is None:
        return _local_fallback_normalized_solve(
            global_index_rows=global_index_rows,
            full_terms=full_terms,
            line_rows=line_rows,
            he_like_stage=he_like_stage,
            target=target,
        )
    rows = build_full_global_normalized_solve_comparison(
        global_index_rows=global_index_rows,
        full_global_matrix_terms=full_terms,
        line_rows=line_rows,
        he_like_stage=he_like_stage,
        linear_solver=linear_solver,
        full_global_topology=topology,
        ion_fraction_closure=ion_fraction_closure,
        calc_ion_rates_istruc_audit_rows=calc_ion_rates_rows,
        temperature_K=temperature_K,
        electron_density=electron_density,
    )
    s = _summary_from_solve(rows)
    f = _maybe_float(s.get("f_fraction"))
    i = _maybe_float(s.get("i_fraction"))
    r = _maybe_float(s.get("r_fraction"))
    R, G = _ratio_R_G(f, i, r)
    return {
        "f_fraction": f,
        "i_fraction": i,
        "r_fraction": r,
        "R": R,
        "G": G,
        "l2_distance_to_target": _l2(f, i, r, target),
        "solve_status": s.get("solve_status"),
        "solver": s.get("solver"),
        "solver_warning": s.get("solver_warning"),
        "n_negative_populations": s.get("n_negative_populations"),
        "sum_population": s.get("sum_population"),
        "rows_by_component_used": s.get("rows_by_component_used"),
    }


def _infer_temperature_density(summary: dict, rows: Sequence[dict]) -> Tuple[Optional[float], Optional[float]]:
    for src in [summary] + list(rows[:10]):
        t = _maybe_float(src.get("temperature_K"))
        ne = _maybe_float(src.get("electron_density_cm^-3") or src.get("electron_density"))
        if t is not None or ne is not None:
            return t, ne
    return None, None



def _stored_solver_triplet_summary(solver_dir: Path, target: Tuple[Optional[float], Optional[float], Optional[float]]) -> Optional[dict]:
    """Return the solver's already-written triplet summary when available."""
    # Prefer the user-facing comparison summary from example 43, then the raw
    # full-global comparison table from example 42.
    for path in [
        solver_dir / "xstar_detail_population_comparison_summary.json",
        solver_dir / "xstar_like_element_solver_summary.json",
    ]:
        payload = _read_json(path)
        if not payload:
            continue
        # Several historical summary schemas exist; look for direct f/i/r keys.
        candidates = [payload]
        for key in ("recommended_comparison", "full_global_triplet", "summary"):
            if isinstance(payload.get(key), dict):
                candidates.append(payload[key])
        for cand in candidates:
            f = _maybe_float(cand.get("f_fraction") or cand.get("target_f") or cand.get("triplet_f_fraction"))
            i = _maybe_float(cand.get("i_fraction") or cand.get("target_i") or cand.get("triplet_i_fraction"))
            r = _maybe_float(cand.get("r_fraction") or cand.get("target_r") or cand.get("triplet_r_fraction"))
            # The comparison summary commonly uses these names.
            if f is None:
                f = _maybe_float(cand.get("solver_f") or cand.get("f"))
            if i is None:
                i = _maybe_float(cand.get("solver_i") or cand.get("i"))
            if r is None:
                r = _maybe_float(cand.get("solver_r") or cand.get("r"))
            if f is not None and i is not None and r is not None:
                R, G = _ratio_R_G(f, i, r)
                return {
                    "f_fraction": f,
                    "i_fraction": i,
                    "r_fraction": r,
                    "R": R,
                    "G": G,
                    "l2_distance_to_target": _l2(f, i, r, target),
                    "solve_status": "stored_solver_summary",
                    "solver": cand.get("solver") or "stored_summary",
                    "solver_warning": "stored baseline from existing solver output; scan rows are recomputed after source-family scaling",
                }
    rows = _read_csv(solver_dir / "xstar_like_element_solver_full_global_normalized_solve_comparison.csv")
    for case in ["full_global_xstar_tau0_calc_emis_ion", "full_global_normalized_proxy_topology_solve"]:
        for row in rows:
            if row.get("row_kind") == "summary" and row.get("comparison_case") == case:
                f = _maybe_float(row.get("f_fraction")); i = _maybe_float(row.get("i_fraction")); r = _maybe_float(row.get("r_fraction"))
                if f is not None and i is not None and r is not None:
                    R, G = _ratio_R_G(f, i, r)
                    return {
                        "f_fraction": f,
                        "i_fraction": i,
                        "r_fraction": r,
                        "R": R,
                        "G": G,
                        "l2_distance_to_target": _l2(f, i, r, target),
                        "solve_status": "stored_solver_summary",
                        "solver": row.get("solver") or "stored_full_global_comparison",
                        "solver_warning": f"stored baseline from {case}; scan rows are recomputed after source-family scaling",
                    }
    return None


def _population_by_global_from_solver_dir(solver_dir: Path) -> Dict[int, float]:
    """Best-effort population map from already-written solver products."""
    out: Dict[int, float] = {}
    rows = _read_csv(solver_dir / "xstar_like_element_solver_full_global_normalized_solve_comparison.csv")
    for row in rows:
        if str(row.get("row_kind")) != "population":
            continue
        g = _maybe_int(row.get("global_index"))
        val = _maybe_float(row.get("xstar_xileve_emissivity_population"))
        if val is None:
            val = _maybe_float(row.get("population_fraction"))
        if g is not None and val is not None:
            out[int(g)] = float(val)
    if out:
        return out
    rows = _read_csv(solver_dir / "xstar_detail_population_comparison.csv")
    for row in rows:
        g = _maybe_int(row.get("global_index") or row.get("solver_global_index"))
        val = _maybe_float(row.get("solver_population_fraction") or row.get("population_fraction"))
        if g is not None and val is not None:
            out[int(g)] = float(val)
    return out


def _baseline_component_rates_from_solver_dir(
    solver_dir: Path,
    stored: Optional[dict],
) -> Tuple[Dict[str, float], str]:
    """Return f/i/r component strengths in photon-like s^-1 units if available."""
    rows = _read_csv(solver_dir / "xstar_like_element_solver_calc_emis_ion_triplet_emergent.csv")
    sums = {"f": 0.0, "i": 0.0, "r": 0.0}
    source = ""
    for row in rows:
        if str(row.get("row_kind")) != "calc_emis_ion_triplet_emergent_line":
            continue
        comp = str(row.get("component") or "").strip().lower()
        if comp not in sums:
            continue
        val = _maybe_float(row.get("xstar_tau0_calc_emis_net_rate_s^-1"))
        if val is None:
            val = _maybe_float(row.get("transparent_ucalc_ans2_upper_to_lower_s^-1"))
        if val is None:
            upop = _maybe_float(row.get("xstar_xileve_upper_population"))
            A = _maybe_float(row.get("A_s^-1"))
            if upop is not None and A is not None:
                val = float(upop) * float(A)
        if val is not None:
            sums[comp] += max(0.0, float(val))
            source = "calc_emis_ion_triplet_emergent_rates"
    if sum(sums.values()) > 0:
        return sums, source
    if stored:
        for comp in ("f", "i", "r"):
            val = _maybe_float(stored.get(f"{comp}_fraction"))
            if val is not None:
                sums[comp] = float(val)
        if sum(sums.values()) > 0:
            return sums, "stored_fraction_unit_total"
    return {"f": 0.0, "i": 0.0, "r": 0.0}, "unavailable"


def _make_population_weighted_attribution_rows(
    full_terms: Sequence[dict],
    global_index_rows: Sequence[dict],
    population_by_global: Dict[int, float],
) -> List[dict]:
    """Population-weighted flow attribution into triplet upper levels.

    The raw type-71/type-99 rates can look large but have negligible leverage
    when the source superlevel/parent population is tiny.  This table multiplies
    off-diagonal gains by the current stored source population.  It is a
    diagnostic first-order flow proxy, not a re-solved XSTAR matrix.
    """
    triplet_by_global = _component_from_global_index(global_index_rows)
    acc: Dict[str, dict] = {}
    for row in full_terms:
        fam = _family_for_row(row, triplet_by_global)
        if not fam:
            continue
        col = _maybe_int(row.get("matrix_col_global_index"))
        pop_col = population_by_global.get(int(col), 0.0) if col is not None else 0.0
        rate = _maybe_float(row.get("full_global_signed_rate_s^-1") or row.get("signed_rate_s^-1"))
        if rate is None or float(rate) <= 0.0 or pop_col == 0.0:
            continue
        flow = float(pop_col) * float(rate)
        r = acc.setdefault(fam, {
            "source_family": fam,
            "n_population_weighted_gain_rows": 0,
            "population_weighted_gain_sum_s^-1": 0.0,
            "population_weighted_direct_f_gain_s^-1": 0.0,
            "population_weighted_direct_i_gain_s^-1": 0.0,
            "population_weighted_direct_r_gain_s^-1": 0.0,
            "population_weighted_branch_proxy_f_gain_s^-1": 0.0,
            "population_weighted_branch_proxy_i_gain_s^-1": 0.0,
            "population_weighted_branch_proxy_r_gain_s^-1": 0.0,
            "max_source_population_used": 0.0,
            "example_records": [],
            "notes": "population-weighted first-order flow proxy; not a matrix re-solve",
        })
        r["n_population_weighted_gain_rows"] += 1
        r["population_weighted_gain_sum_s^-1"] += flow
        r["max_source_population_used"] = max(float(r["max_source_population_used"]), float(pop_col))
        row_g = _maybe_int(row.get("matrix_row_global_index"))
        comp = str(row.get("triplet_component") or row.get("destination_triplet_component") or "").strip().lower()
        if row_g is not None and comp not in {"f", "i", "r"}:
            comp = triplet_by_global.get(int(row_g), "")
        if comp in {"f", "i", "r"}:
            r[f"population_weighted_direct_{comp}_gain_s^-1"] += flow
        if fam.startswith("type99_"):
            for c in ("f", "i", "r"):
                b = _maybe_float(row.get(f"type71_B_{c}"))
                if b is not None:
                    r[f"population_weighted_branch_proxy_{c}_gain_s^-1"] += flow * float(b)
        recid = row.get("record")
        if recid not in (None, "", "nan") and len(r["example_records"]) < 8:
            r["example_records"].append(str(recid))
    rows: List[dict] = []
    for fam, r in sorted(acc.items()):
        direct_total = sum(float(r[f"population_weighted_direct_{c}_gain_s^-1"]) for c in ("f", "i", "r"))
        proxy_total = sum(float(r[f"population_weighted_branch_proxy_{c}_gain_s^-1"]) for c in ("f", "i", "r"))
        rr = dict(r)
        rr["population_weighted_triplet_direct_total_s^-1"] = direct_total
        rr["population_weighted_triplet_branch_proxy_total_s^-1"] = proxy_total
        for c in ("f", "i", "r"):
            rr[f"population_weighted_direct_{c}_fraction"] = rr[f"population_weighted_direct_{c}_gain_s^-1"] / direct_total if direct_total > 0 else ""
            rr[f"population_weighted_branch_proxy_{c}_fraction"] = rr[f"population_weighted_branch_proxy_{c}_gain_s^-1"] / proxy_total if proxy_total > 0 else ""
        rr["example_records"] = ";".join(r["example_records"])
        rows.append(rr)
    return rows


def _make_population_weighted_leverage_scan_rows(
    weighted_rows: Sequence[dict],
    baseline_component_rates: Dict[str, float],
    target: Tuple[Optional[float], Optional[float], Optional[float]],
    scales: Sequence[float],
) -> List[dict]:
    """First-order fixed-population component scan.

    This does not re-solve the population matrix.  It asks: if the currently
    population-weighted flow from a family were scaled while all other stored
    populations and type-50 drains were held fixed, which direction would f/i/r
    move?  It is intended to identify families with real leverage and to avoid
    mistaking large raw rates from nearly unpopulated superlevels for important
    routes.
    """
    base_total = sum(max(0.0, float(baseline_component_rates.get(c, 0.0))) for c in ("f", "i", "r"))
    rows: List[dict] = []
    if base_total <= 0:
        return rows
    base_frac = {c: float(baseline_component_rates.get(c, 0.0)) / base_total for c in ("f", "i", "r")}
    R, G = _ratio_R_G(base_frac["f"], base_frac["i"], base_frac["r"])
    rows.append({
        "scan_model": "population_weighted_fixed_population_first_order",
        "scan_name": "stored_component_baseline",
        "scaled_group": "stored_baseline",
        "scale_factor": 1.0,
        "weighted_family_total_s^-1": 0.0,
        "baseline_total_component_rate_s^-1": base_total,
        "f_fraction": base_frac["f"],
        "i_fraction": base_frac["i"],
        "r_fraction": base_frac["r"],
        "R": R,
        "G": G,
        "l2_distance_to_target": _l2(base_frac["f"], base_frac["i"], base_frac["r"], target),
        "notes": "baseline from stored calc_emis/component rates",
    })
    for wr in weighted_rows:
        fam = str(wr.get("source_family"))
        comp_flow = {}
        for c in ("f", "i", "r"):
            direct = _maybe_float(wr.get(f"population_weighted_direct_{c}_gain_s^-1")) or 0.0
            proxy = _maybe_float(wr.get(f"population_weighted_branch_proxy_{c}_gain_s^-1")) or 0.0
            comp_flow[c] = float(direct) + float(proxy)
        flow_total = sum(max(0.0, comp_flow[c]) for c in ("f", "i", "r"))
        for scale in scales:
            new = {c: max(0.0, float(baseline_component_rates.get(c, 0.0)) + (float(scale) - 1.0) * comp_flow[c]) for c in ("f", "i", "r")}
            total = sum(new.values())
            if total <= 0:
                continue
            f, i, r = new["f"] / total, new["i"] / total, new["r"] / total
            R, G = _ratio_R_G(f, i, r)
            rows.append({
                "scan_model": "population_weighted_fixed_population_first_order",
                "scan_name": f"{fam}_x{float(scale):g}",
                "scaled_group": fam,
                "scale_factor": float(scale),
                "weighted_family_total_s^-1": flow_total,
                "baseline_total_component_rate_s^-1": base_total,
                "family_to_baseline_total_ratio": flow_total / base_total if base_total > 0 else "",
                "weighted_f_flow_s^-1": comp_flow["f"],
                "weighted_i_flow_s^-1": comp_flow["i"],
                "weighted_r_flow_s^-1": comp_flow["r"],
                "f_fraction": f,
                "i_fraction": i,
                "r_fraction": r,
                "R": R,
                "G": G,
                "l2_distance_to_target": _l2(f, i, r, target),
                "delta_f_minus_target": "" if target[0] is None else f - float(target[0]),
                "delta_i_minus_target": "" if target[1] is None else i - float(target[1]),
                "delta_r_minus_target": "" if target[2] is None else r - float(target[2]),
                "notes": "first-order fixed-population scan; not a matrix re-solve",
            })
    return rows

def _write_markdown(path: Path, scan_rows: Sequence[dict], attr_rows: Sequence[dict], target: Tuple[Optional[float], Optional[float], Optional[float]], target_meta: dict) -> None:
    best = None
    candidates = [r for r in scan_rows if _maybe_float(r.get("l2_distance_to_target")) is not None]
    if candidates:
        best = min(candidates, key=lambda r: float(r.get("l2_distance_to_target")))
    lines = []
    lines.append("# C V f/r source-attribution diagnostic\n")
    lines.append("This diagnostic leaves type-50 1s2p 3P_J -> 1s2s 3S1 line-escape/drain terms fixed and scans selected superlevel/source/cascade families.\n")
    lines.append("## Target\n")
    lines.append(f"- target f/i/r = {target[0]} / {target[1]} / {target[2]}\n")
    lines.append(f"- target source = `{target_meta.get('status')}`; value column = `{target_meta.get('value_column', '')}`\n")
    if best:
        lines.append("## Best scan row\n")
        lines.append(f"- scan = `{best.get('scan_name')}`\n")
        lines.append(f"- group = `{best.get('scaled_group')}`\n")
        lines.append(f"- scale = `{best.get('scale_factor')}`\n")
        lines.append(f"- f/i/r = {best.get('f_fraction')} / {best.get('i_fraction')} / {best.get('r_fraction')}\n")
        lines.append(f"- R = {best.get('R')}; G = {best.get('G')}; L2 = {best.get('l2_distance_to_target')}\n")
    lines.append("## Source families\n")
    for row in attr_rows:
        lines.append(f"- `{row.get('source_family')}`: rows={row.get('n_matrix_rows')}, gains={row.get('n_offdiag_gain_rows')}, direct f/i/r={row.get('direct_f_gain_s^-1')}/{row.get('direct_i_gain_s^-1')}/{row.get('direct_r_gain_s^-1')}, branch proxy f/i/r={row.get('branch_proxy_f_s^-1')}/{row.get('branch_proxy_i_s^-1')}/{row.get('branch_proxy_r_s^-1')}\n")
    lines.append("\nSee `cv_source_group_scan.csv` and `cv_source_family_attribution.csv` for full details.\n")
    path.write_text("".join(lines))


def main(argv: Optional[Sequence[str]] = None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--solver-out-dir", required=True, help="Output directory from examples/42_xstar_like_element_solver_demo.py")
    p.add_argument("--out-dir", default="cv_source_attribution_scan", help="Directory for attribution/scan outputs")
    p.add_argument("--he-like-stage", type=int, default=5)
    p.add_argument("--xstar-triplet-lines-csv", default="", help="Optional C V XSTAR triplet line CSV used to define target f/i/r")
    p.add_argument("--xstar-value-column", default="emit_outward")
    p.add_argument("--target-f", type=float, default=float("nan"))
    p.add_argument("--target-i", type=float, default=float("nan"))
    p.add_argument("--target-r", type=float, default=float("nan"))
    p.add_argument("--sprlevlt-scales", default="0,0.25,0.5,0.75,1,1.25,1.5")
    p.add_argument("--sprlevls-scales", default="0.5,0.75,1,1.25,1.5,2")
    p.add_argument("--resonance-cascade-scales", default="0.5,0.75,1,1.25,1.5,2")
    p.add_argument("--extra-groups", default="", help="Optional comma-separated extra groups to scan: type99_continuum_alias_level32,type71_from_sprlevlt,type71_from_sprlevls,type53_milne_inverse_to_resonance,type74_inverse_to_resonance")
    p.add_argument("--extra-group-scales", default="0.5,0.75,1,1.25,1.5,2")
    p.add_argument("--population-weighted-scales", default="0,0.5,0.75,1,1.25,1.5,2", help="Scales for the population-weighted fixed-population leverage scan written to cv_population_weighted_source_scan.csv.")
    p.add_argument("--full-global-linear-solver", default="xstar-lucy", choices=["solve", "dense", "lstsq", "svd", "xstar-lucy"])
    p.add_argument("--full-global-topology", default="xstar-continuum-alias-superlevels", choices=["explicit-current", "xstar-continuum-alias", "xstar-continuum-alias-superlevels"])
    p.add_argument("--ion-fraction-closure", default="xstar-calc-ion-rates")
    p.add_argument("--print-summary", action="store_true")
    args = p.parse_args(argv)

    solver_dir = Path(args.solver_out_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    global_rows = _read_csv(solver_dir / "xstar_like_element_solver_global_index.csv")
    full_terms = _read_csv(solver_dir / "xstar_like_element_solver_full_global_matrix_terms.csv")
    line_rows = _read_csv(solver_dir / "xstar_like_element_solver_lines.csv")
    calc_ion_rows = _read_csv(solver_dir / "xstar_like_element_solver_calc_ion_rates_istruc_audit.csv")
    summary_json = _read_json(solver_dir / "xstar_like_element_solver_summary.json")
    comp_json = _read_json(solver_dir / "xstar_detail_population_comparison_summary.json")
    tK, ne = _infer_temperature_density(summary_json, full_terms)

    if not global_rows or not full_terms:
        raise FileNotFoundError("solver output must contain xstar_like_element_solver_global_index.csv and xstar_like_element_solver_full_global_matrix_terms.csv")

    target_csv = Path(args.xstar_triplet_lines_csv) if args.xstar_triplet_lines_csv else None
    csv_target = _triplet_target_from_xstar_csv(target_csv, args.xstar_value_column)
    target = list(csv_target[:3])
    target_meta = csv_target[3]
    for j, name in enumerate(["f", "i", "r"]):
        val = getattr(args, f"target_{name}")
        if math.isfinite(float(val)):
            target[j] = float(val)
    if any(x is None for x in target):
        target = list(DEFAULT_CV_TARGET)
        target_meta = dict(target_meta)
        target_meta["status"] = "default_c_v_ne1e8_emit_outward_target"
    target_tuple = (target[0], target[1], target[2])

    attr_rows = _make_attribution_rows(full_terms, global_rows)
    write_csv(out_dir / "cv_source_family_attribution.csv", attr_rows)

    # v0.3.106: raw source rates can be misleading when the source superlevel
    # population is tiny.  Add a population-weighted, fixed-population leverage
    # diagnostic that uses the stored solution products as the baseline.
    stored_for_weighting = _stored_solver_triplet_summary(solver_dir, target_tuple)
    population_by_global = _population_by_global_from_solver_dir(solver_dir)
    weighted_attr_rows = _make_population_weighted_attribution_rows(full_terms, global_rows, population_by_global)
    write_csv(out_dir / "cv_population_weighted_source_attribution.csv", weighted_attr_rows)
    baseline_component_rates, baseline_component_source = _baseline_component_rates_from_solver_dir(solver_dir, stored_for_weighting)
    weighted_scan_rows = _make_population_weighted_leverage_scan_rows(
        weighted_attr_rows,
        baseline_component_rates,
        target_tuple,
        _parse_scale_list(args.population_weighted_scales),
    )
    for row in weighted_scan_rows:
        row["baseline_component_rate_source"] = baseline_component_source
    write_csv(out_dir / "cv_population_weighted_source_scan.csv", weighted_scan_rows)

    triplet_by_global = _component_from_global_index(global_rows)
    scan_plan: List[Tuple[str, str, float]] = []
    scan_plan.append(("baseline", "none", 1.0))
    for x in _parse_scale_list(args.sprlevlt_scales):
        scan_plan.append((f"type99_into_sprlevlt_x{x:g}", "type99_into_sprlevlt", x))
    for x in _parse_scale_list(args.sprlevls_scales):
        scan_plan.append((f"type99_into_sprlevls_x{x:g}", "type99_into_sprlevls", x))
    for x in _parse_scale_list(args.resonance_cascade_scales):
        scan_plan.append((f"type71_resonance_singlet_cascade_x{x:g}", "type71_resonance_singlet_cascade", x))
    extra_scales = _parse_scale_list(args.extra_group_scales)
    for group in [g.strip() for g in str(args.extra_groups or "").split(",") if g.strip()]:
        for x in extra_scales:
            scan_plan.append((f"{group}_x{x:g}", group, x))

    scan_rows: List[dict] = []
    stored = _stored_solver_triplet_summary(solver_dir, target_tuple)
    if stored:
        scan_rows.append({
            "scan_name": "stored_solver_baseline",
            "scaled_group": "stored_baseline",
            "scale_factor": 1.0,
            "n_scaled_matrix_rows": 0,
            "scaled_abs_rate_sum_before_scale_s^-1": 0.0,
            "target_f_fraction": target_tuple[0],
            "target_i_fraction": target_tuple[1],
            "target_r_fraction": target_tuple[2],
            **stored,
        })
        for comp in ("f", "i", "r"):
            val = _maybe_float(scan_rows[-1].get(f"{comp}_fraction"))
            tar = _maybe_float(scan_rows[-1].get(f"target_{comp}_fraction"))
            scan_rows[-1][f"delta_{comp}_minus_target"] = "" if val is None or tar is None else val - tar
    for scan_name, group, scale in scan_plan:
        if group == "none":
            terms = [dict(r) for r in full_terms]
            n_scaled = 0
            scaled_abs = 0.0
        else:
            terms, n_scaled, scaled_abs = _scale_terms(full_terms, group, scale, triplet_by_global)
        sol = _run_solve(
            global_index_rows=global_rows,
            full_terms=terms,
            line_rows=line_rows,
            he_like_stage=args.he_like_stage,
            topology=args.full_global_topology,
            linear_solver=args.full_global_linear_solver,
            ion_fraction_closure=args.ion_fraction_closure,
            calc_ion_rates_rows=calc_ion_rows,
            temperature_K=tK,
            electron_density=ne,
            target=target_tuple,
        )
        row = {
            "scan_name": scan_name,
            "scaled_group": group,
            "scale_factor": scale,
            "n_scaled_matrix_rows": n_scaled,
            "scaled_abs_rate_sum_before_scale_s^-1": scaled_abs,
            "target_f_fraction": target_tuple[0],
            "target_i_fraction": target_tuple[1],
            "target_r_fraction": target_tuple[2],
            **sol,
        }
        for comp in ("f", "i", "r"):
            val = _maybe_float(row.get(f"{comp}_fraction"))
            tar = _maybe_float(row.get(f"target_{comp}_fraction"))
            row[f"delta_{comp}_minus_target"] = "" if val is None or tar is None else val - tar
        scan_rows.append(row)

    write_csv(out_dir / "cv_source_group_scan.csv", scan_rows)
    weighted_candidates = [r for r in weighted_scan_rows if r.get("l2_distance_to_target") not in (None, "")]
    best_weighted = min(weighted_candidates, key=lambda r: float(r.get("l2_distance_to_target"))) if weighted_candidates else {}
    recomputed_candidates = [r for r in scan_rows if r.get("scan_name") == "baseline" and r.get("l2_distance_to_target") not in (None, "")]
    stored_candidates = [r for r in scan_rows if r.get("scan_name") == "stored_solver_baseline" and r.get("l2_distance_to_target") not in (None, "")]
    roundtrip_delta = ""
    if recomputed_candidates and stored_candidates:
        rf = _maybe_float(recomputed_candidates[0].get("f_fraction")); sf = _maybe_float(stored_candidates[0].get("f_fraction"))
        ri = _maybe_float(recomputed_candidates[0].get("i_fraction")); si = _maybe_float(stored_candidates[0].get("i_fraction"))
        rr = _maybe_float(recomputed_candidates[0].get("r_fraction")); sr = _maybe_float(stored_candidates[0].get("r_fraction"))
        if None not in (rf, sf, ri, si, rr, sr):
            roundtrip_delta = math.sqrt((float(rf)-float(sf))**2 + (float(ri)-float(si))**2 + (float(rr)-float(sr))**2)
    summary = {
        "solver_out_dir": str(solver_dir),
        "target": {"f": target_tuple[0], "i": target_tuple[1], "r": target_tuple[2]},
        "target_meta": target_meta,
        "n_source_family_rows": len(attr_rows),
        "n_population_weighted_source_family_rows": len(weighted_attr_rows),
        "n_scan_rows": len(scan_rows),
        "n_population_weighted_scan_rows": len(weighted_scan_rows),
        "best_scan_row": min(scan_rows, key=lambda r: float(r.get("l2_distance_to_target") if r.get("l2_distance_to_target") not in (None, "") else 1e99)) if scan_rows else {},
        "best_population_weighted_scan_row": best_weighted,
        "matrix_recompute_vs_stored_baseline_l2_delta": roundtrip_delta,
        "baseline_component_rate_source": baseline_component_source,
        "notes": "Diagnostic-only source-family scaling; type-50 line-escape/drain rows are kept fixed by construction. v0.3.106 adds population-weighted fixed-population leverage scans because CSV-roundtrip matrix re-solves may not reproduce the stored in-memory solver baseline exactly.",
    }
    (out_dir / "cv_source_attribution_scan_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True))
    _write_markdown(out_dir / "cv_source_attribution_scan.md", scan_rows, attr_rows, target_tuple, target_meta)

    if args.print_summary:
        print("C V source-attribution f/r scan")
        print("--------------------------------")
        print(f"solver_out_dir={solver_dir}")
        print(f"target f/i/r={target_tuple[0]}/{target_tuple[1]}/{target_tuple[2]}")
        best = summary.get("best_scan_row") or {}
        print(f"best scan={best.get('scan_name')} group={best.get('scaled_group')} scale={best.get('scale_factor')}")
        print(f"best f/i/r={best.get('f_fraction')}/{best.get('i_fraction')}/{best.get('r_fraction')} R={best.get('R')} G={best.get('G')} L2={best.get('l2_distance_to_target')}")
        bw = summary.get("best_population_weighted_scan_row") or {}
        if bw:
            print(f"best population-weighted scan={bw.get('scan_name')} group={bw.get('scaled_group')} scale={bw.get('scale_factor')}")
            print(f"best population-weighted f/i/r={bw.get('f_fraction')}/{bw.get('i_fraction')}/{bw.get('r_fraction')} R={bw.get('R')} G={bw.get('G')} L2={bw.get('l2_distance_to_target')}")
        print(f"wrote: {out_dir / 'cv_source_family_attribution.csv'}")
        print(f"wrote: {out_dir / 'cv_population_weighted_source_attribution.csv'}")
        print(f"wrote: {out_dir / 'cv_source_group_scan.csv'}")
        print(f"wrote: {out_dir / 'cv_population_weighted_source_scan.csv'}")
        print(f"wrote: {out_dir / 'cv_source_attribution_scan.md'}")


if __name__ == "__main__":
    main()
