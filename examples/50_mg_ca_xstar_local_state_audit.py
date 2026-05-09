#!/usr/bin/env python3
"""Audit Mg XI / Ca XIX comparisons against XSTAR local zone conditions.

This diagnostic is deliberately source-code first.  It does not fit triplet
scale factors.  Instead it checks whether a solver run used the same local gas
state and radiation normalization as the XSTAR zone that produced the supplied
triplet target.

XSTAR writes the relevant local-state table to ``xout_abund1.fits`` in
``pprint.f90``.  The ``ABUNDANCES`` extension contains columns such as
``radius``, ``delta_r``, ``ion_parameter`` (the XSTAR ``xi = L/(n r^2)`` value),
``x_e``, ``n_p``, ``pressure`` and ``temperature`` in units of 10^4 K, plus one
column per ion.  For a He-like triplet target, the most useful first comparison
zone is the row where the corresponding He-like ion fraction is largest.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
from pathlib import Path
from typing import Any, Iterable, Sequence


ION_INFO = {
    "mg11": {"ion": "Mg XI", "element": "Mg", "stage": 11, "xstar_col": "mg_xi"},
    "ca19": {"ion": "Ca XIX", "element": "Ca", "stage": 19, "xstar_col": "ca_xix"},
}


def _as_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        x = float(str(v).strip())
    except Exception:
        return None
    return x if math.isfinite(x) else None


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(newline="", encoding="utf-8") as h:
        return [dict(r) for r in csv.DictReader(h)]


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    for r in rows:
        for k in r:
            if k not in fields:
                fields.append(k)
    with path.open("w", newline="", encoding="utf-8") as h:
        w = csv.DictWriter(h, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def _decode_fits_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").strip()
    try:
        import numpy as np  # type: ignore
        if isinstance(value, np.bytes_):
            return bytes(value).decode("utf-8", errors="replace").strip()
        if isinstance(value, np.generic):
            value = value.item()
    except Exception:
        pass
    if isinstance(value, str):
        return value.strip()
    return value


def _normalize_fits_col(name: str) -> str:
    return str(name).strip().lower().replace(" ", "_").replace("-", "_")


def _read_xout_abundances_lazy(path: Path) -> dict[str, list[dict[str, Any]]]:
    # Lazy import so this diagnostic can still report missing xout_abund1.fits
    # on systems where astropy is not installed.
    from astropy.io import fits  # type: ignore

    out: dict[str, list[dict[str, Any]]] = {}
    with fits.open(path) as hdul:
        for hdu_name in ("ABUNDANCES", "COLUMNS", "HEATING", "COOLING"):
            if hdu_name not in hdul:
                continue
            hdu = hdul[hdu_name]
            if getattr(hdu, "data", None) is None or getattr(hdu, "columns", None) is None:
                continue
            names = list(hdu.columns.names)
            rows: list[dict[str, Any]] = []
            for rec in hdu.data:
                row: dict[str, Any] = {}
                for name in names:
                    row[_normalize_fits_col(name)] = _decode_fits_value(rec[name])
                rows.append(row)
            if rows:
                out[hdu_name.lower()] = rows
    return out


def _case_from_name(name: str) -> tuple[str | None, str | None, str | None]:
    low = name.lower()
    tag = "mg11" if "mg11" in low else ("ca19" if "ca19" in low else None)
    m_xi = re.search(r"xi([0-9]+(?:p[0-9]+)?)", low)
    m_ne = re.search(r"ne([0-9]+(?:p[0-9]+)?(?:e[0-9]+)?)", low)
    xi = m_xi.group(1).replace("p", ".") if m_xi else None
    ne = m_ne.group(1).replace("p", ".") if m_ne else None
    return tag, xi, ne


def _xi_token(xi: str | None) -> str | None:
    if xi is None:
        return None
    try:
        x = float(xi)
    except Exception:
        return "xi" + str(xi).replace(".", "p")
    text = f"{x:.12g}".replace(".", "p")
    return "xi" + text


def _ion_column_candidates(col: str) -> list[str]:
    s = col.lower().replace(" ", "_").replace("-", "_")
    return [s, s.replace("_", ""), s.upper(), s.title()]


def _find_col(row: dict[str, Any], desired: str) -> str | None:
    keys = {str(k).lower().replace(" ", "_").replace("-", "_"): k for k in row.keys()}
    for cand in _ion_column_candidates(desired):
        key = cand.lower().replace(" ", "_").replace("-", "_")
        if key in keys:
            return str(keys[key])
    return None


def _triplet_from_csv(path: Path, value_column: str = "emit_outward") -> dict[str, Any]:
    rows = _read_csv(path)
    vals = {"f": 0.0, "i": 0.0, "r": 0.0}
    total = 0.0
    max_depth_in = 0.0
    max_depth_out = 0.0
    n_nonzero = 0
    for row in rows:
        upper = str(row.get("upper_level", "") or row.get("upper", "")).lower()
        lower = str(row.get("lower_level", "") or row.get("lower", "")).lower()
        text = upper + " " + lower
        comp = None
        if "2s1.3s" in text or "3s_1" in text:
            comp = "f"
        elif "2p1.3p" in text or "3p_" in text:
            comp = "i"
        elif "2p1.1p_1" in text or "1p_1" in text:
            comp = "r"
        val = _as_float(row.get(value_column)) or 0.0
        if val != 0.0:
            n_nonzero += 1
        if comp:
            vals[comp] += val
            total += val
        max_depth_in = max(max_depth_in, _as_float(row.get("depth_inward")) or 0.0)
        max_depth_out = max(max_depth_out, _as_float(row.get("depth_outward")) or 0.0)
    frac = {k: (v / total if total > 0 else None) for k, v in vals.items()}
    return {
        "xstar_target_csv": str(path),
        "xstar_target_rows": len(rows),
        "xstar_target_nonzero_rows": n_nonzero,
        "xstar_target_total_triplet_emit": total,
        "xstar_target_f_fraction": frac["f"],
        "xstar_target_i_fraction": frac["i"],
        "xstar_target_r_fraction": frac["r"],
        "xstar_target_R": (frac["f"] / frac["i"] if frac["f"] is not None and frac["i"] not in (None, 0) else None),
        "xstar_target_G": ((frac["f"] + frac["i"]) / frac["r"] if frac["r"] not in (None, 0) and frac["f"] is not None and frac["i"] is not None else None),
        "xstar_target_max_depth_inward": max_depth_in,
        "xstar_target_max_depth_outward": max_depth_out,
    }


def _find_target_csv(search_roots: Iterable[Path], tag: str, xi: str | None, ne: str | None) -> Path | None:
    xtok = _xi_token(xi) or "xi*"
    candidates: list[Path] = []
    for root in search_roots:
        if not root.exists():
            continue
        patterns = [
            f"**/{tag}_{xtok}_ne*/xstar_{tag}_triplet_lines.csv",
            f"**/{tag}_{xtok}*/xstar_{tag}_triplet_lines.csv",
            f"**/xstar_{tag}_triplet_lines.csv",
        ]
        for pat in patterns:
            candidates.extend(root.glob(pat))
    if not candidates:
        return None
    if xi is not None:
        want = (xtok or "").lower()
        exact = [p for p in candidates if want in str(p).lower()]
        if exact:
            candidates = exact
    return sorted(set(candidates), key=lambda p: (len(str(p)), str(p)))[0]


def _find_xout_abund(search_roots: Iterable[Path], target_csv: Path | None, tag: str, xi: str | None) -> Path | None:
    candidates: list[Path] = []
    if target_csv is not None:
        # Prefer a local XSTAR run directory next to the converted target or in
        # the corresponding generated run tree.
        candidates.append(target_csv.parent / "xout_abund1.fits")
        parent_name = target_csv.parent.name
        for root in search_roots:
            candidates.append(root / "xstar_runs" / "mg_ca_triplet_targets" / parent_name / "xout_abund1.fits")
            candidates.append(root / parent_name / "xout_abund1.fits")
    xtok = _xi_token(xi) or "xi*"
    for root in search_roots:
        if root.exists():
            candidates.extend(root.glob(f"**/{tag}_{xtok}*/xout_abund1.fits"))
            candidates.extend(root.glob(f"**/{tag}*{xtok}*/xout_abund1.fits"))
    for p in candidates:
        if p.exists():
            return p
    return None


def _select_zone(abund_path: Path | None, ion_col: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if abund_path is None or not abund_path.exists():
        return ({"xstar_local_state_status": "missing_xout_abund1_fits"}, [])
    try:
        tables = _read_xout_abundances_lazy(abund_path)
    except Exception as exc:
        return ({"xstar_local_state_status": "failed_to_read_xout_abund1_fits", "xstar_abund_error": str(exc)}, [])
    rows = tables.get("abundances", [])
    if not rows:
        return ({"xstar_local_state_status": "xout_abund1_has_no_abundances_extension", "xstar_abund_path": str(abund_path)}, [])
    col = _find_col(rows[0], ion_col)
    if col is None:
        return ({"xstar_local_state_status": "ion_column_not_found", "xstar_abund_path": str(abund_path), "requested_ion_column": ion_col, "available_columns": ";".join(rows[0].keys())}, [])
    best_i = None
    best_val = -1.0
    zone_rows: list[dict[str, Any]] = []
    for idx, row in enumerate(rows, start=1):
        frac = _as_float(row.get(col))
        radius = _as_float(row.get("radius"))
        delta_r = _as_float(row.get("delta_r"))
        xi = _as_float(row.get("ion_parameter"))
        xe = _as_float(row.get("x_e"))
        np = _as_float(row.get("n_p"))
        temp_1e4 = _as_float(row.get("temperature"))
        rec = {
            "zone_index": idx,
            "xstar_abund_path": str(abund_path),
            "xstar_ion_column": col,
            "xstar_ion_fraction": frac,
            "xstar_radius_cm": radius,
            "xstar_delta_r_cm": delta_r,
            "xstar_ion_parameter_xi_erg_cm_s^-1": xi,
            "xstar_log_xi_local": (math.log10(xi) if xi and xi > 0 else None),
            "xstar_x_e": xe,
            "xstar_n_p_cm^-3": np,
            "xstar_electron_density_cm^-3": (xe * np if xe is not None and np is not None else None),
            "xstar_temperature_1e4K": temp_1e4,
            "xstar_temperature_K": (temp_1e4 * 1.0e4 if temp_1e4 is not None else None),
            "xstar_pressure_dyn_cm^-2": _as_float(row.get("pressure")),
            "xstar_frac_heat_error": _as_float(row.get("frac_heat_error")),
        }
        zone_rows.append(rec)
        if frac is not None and frac > best_val:
            best_val = frac
            best_i = idx - 1
    if best_i is None:
        return ({"xstar_local_state_status": "ion_column_has_no_numeric_values", "xstar_abund_path": str(abund_path), "xstar_ion_column": col}, zone_rows)
    best = dict(zone_rows[best_i])
    best["xstar_local_state_status"] = "selected_max_he_like_ion_fraction_zone"
    return best, zone_rows


def _is_mg_ca_solver_dir(path: Path) -> bool:
    if not path.is_dir():
        return False
    name = path.name.lower()
    return (
        ("mg11" in name or "ca19" in name)
        and "xstar_like_element_solver" in name
        and "superlevels" in name
        and (path / "xstar_like_element_solver_summary.json").exists()
    )


def _solver_dirs(results_root: Path, explicit_solver_dirs: Sequence[Path] | None = None, include_cwd_fallback: bool = True) -> list[Path]:
    """Return Mg/Ca solver output directories.

    Historically this audit only scanned direct children of ``--results-root``.
    That made local validation brittle: if the user reran one or two solver
    cases in the current package directory and passed an older XSTAR target tree
    as ``--xstar-runs-root``, the audit could report ``cases=0`` even though the
    solver outputs were present nearby.  Keep direct-child discovery for the
    large v0.3.111 grid, but also support explicit solver directories and a
    conservative current-working-directory fallback when no cases are found.
    """
    seen: set[Path] = set()
    dirs: list[Path] = []

    def add(path: Path) -> None:
        try:
            rp = path.resolve()
        except Exception:
            rp = path.absolute()
        if rp in seen:
            return
        if _is_mg_ca_solver_dir(path):
            seen.add(rp)
            dirs.append(path)

    for p in results_root.glob("*xstar_like_element_solver*superlevels"):
        add(p)

    if explicit_solver_dirs:
        for p in explicit_solver_dirs:
            add(p)

    if not dirs and include_cwd_fallback:
        cwd = Path.cwd()
        # Direct children only; avoid accidentally walking an entire XSTAR data
        # tree.  This catches the common case where solver outputs are in the
        # current package directory but --results-root points elsewhere.
        if cwd != results_root:
            for p in cwd.glob("*xstar_like_element_solver*superlevels"):
                add(p)

    return sorted(dirs, key=lambda p: str(p))


def _solver_summary(sdir: Path) -> dict[str, Any]:
    obj = _read_json(sdir / "xstar_like_element_solver_summary.json")
    # The historical ``he_like_triplet`` block is an internal local emissivity
    # summary and may not match the printed comparison.  Prefer the same
    # calc_emis_ion/tau0 triplet summary used by examples/42 and examples/43.
    trip = obj.get("calc_emis_ion_triplet_emergent_summary") or {}
    f = trip.get("xstar_tau0_f_fraction")
    i = trip.get("xstar_tau0_i_fraction")
    r = trip.get("xstar_tau0_r_fraction")
    R = trip.get("xstar_tau0_R")
    G = trip.get("xstar_tau0_G")
    if f in (None, "") or i in (None, "") or r in (None, ""):
        comp = _read_json(sdir / "xstar_detail_population_comparison_summary.json")
        ctrip = comp.get("triplet") or {}
        f = ctrip.get("f_fraction", f)
        i = ctrip.get("i_fraction", i)
        r = ctrip.get("r_fraction", r)
        R = ctrip.get("R", R)
        G = ctrip.get("G", G)
    if f in (None, "") or i in (None, "") or r in (None, ""):
        legacy = obj.get("he_like_triplet") or {}
        f = legacy.get("f_fraction", f)
        i = legacy.get("i_fraction", i)
        r = legacy.get("r_fraction", r)
        R = legacy.get("R", R)
        G = legacy.get("G", G)
    return {
        "solver_dir": sdir.name,
        "solver_temperature_K": obj.get("temperature_K"),
        "solver_electron_density_cm^-3": obj.get("electron_density_cm^-3"),
        "solver_radiation_field_mode": obj.get("radiation_field_mode"),
        "solver_radiation_bremsa_scale": (obj.get("radiation_context_summary") or {}).get("radiation_bremsa_scale"),
        "solver_radiation_powerlaw_index": (obj.get("radiation_context_summary") or {}).get("radiation_powerlaw_index"),
        "solver_bremsa_integral_over_eV_grid": (obj.get("radiation_context_summary") or {}).get("total_bremsa_integral_over_eV_grid"),
        "solver_radiation_status": "diagnostic_bremsa_not_yet_tied_to_XSTAR_xi_or_transfer",
        "solver_f_fraction": f,
        "solver_i_fraction": i,
        "solver_r_fraction": r,
        "solver_R": R,
        "solver_G": G,
    }


def build(results_root: Path, xstar_runs_root: Path | None = None, value_column: str = "emit_outward", explicit_solver_dirs: Sequence[Path] | None = None, include_cwd_fallback: bool = True) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    roots = [results_root]
    if xstar_runs_root is not None:
        roots.append(xstar_runs_root)
    if (results_root / "xstar_test_run").exists():
        roots.append(results_root / "xstar_test_run")
    if (results_root / "xstar_runs").exists():
        roots.append(results_root / "xstar_runs")
    audit_rows: list[dict[str, Any]] = []
    zone_rows_all: list[dict[str, Any]] = []
    solver_dirs = _solver_dirs(results_root, explicit_solver_dirs=explicit_solver_dirs, include_cwd_fallback=include_cwd_fallback)
    for sdir in solver_dirs:
        tag, xi, ne = _case_from_name(sdir.name)
        if tag is None:
            continue
        info = ION_INFO[tag]
        solver = _solver_summary(sdir)
        target_csv = _find_target_csv(roots, tag, xi, ne)
        target = _triplet_from_csv(target_csv, value_column=value_column) if target_csv else {"xstar_target_status": "missing_triplet_csv"}
        abund = _find_xout_abund(roots, target_csv, tag, xi)
        state, zones = _select_zone(abund, info["xstar_col"])
        for z in zones:
            zone_rows_all.append({"ion": info["ion"], "log_xi_directory": xi, "solver_dir": sdir.name, **z})
        row = {
            "ion": info["ion"],
            "element": info["element"],
            "he_like_stage": info["stage"],
            "log_xi_directory": xi,
            "density_directory_token": ne,
            **solver,
            **target,
            **state,
        }
        st = state.get("xstar_local_state_status")
        if st == "selected_max_he_like_ion_fraction_zone":
            t_x = _as_float(state.get("xstar_temperature_K"))
            ne_x = _as_float(state.get("xstar_electron_density_cm^-3"))
            t_s = _as_float(solver.get("solver_temperature_K"))
            ne_s = _as_float(solver.get("solver_electron_density_cm^-3"))
            row["solver_over_xstar_temperature_ratio"] = t_s / t_x if t_s is not None and t_x not in (None, 0.0) else None
            row["solver_over_xstar_electron_density_ratio"] = ne_s / ne_x if ne_s is not None and ne_x not in (None, 0.0) else None
            row["recommended_next_solver_temperature_K"] = t_x
            row["recommended_next_solver_electron_density_cm^-3"] = ne_x
            row["recommended_next_action"] = "rerun solver at XSTAR selected-zone T/ne and then compare row-level type56/63/68/69 rates"
        else:
            row["recommended_next_action"] = "copy or preserve xout_abund1.fits from the matching XSTAR run; Mg/Ca f/i/r should not be interpreted until local T/ne/xi are known"
        audit_rows.append(row)
    summary = {
        "n_solver_cases": len(audit_rows),
        "n_discovered_solver_dirs": len(solver_dirs),
        "results_root": str(results_root),
        "xstar_runs_root": str(xstar_runs_root) if xstar_runs_root is not None else "",
        "cwd_fallback_enabled": include_cwd_fallback,
        "n_cases_with_xout_abund1": sum(1 for r in audit_rows if r.get("xstar_local_state_status") == "selected_max_he_like_ion_fraction_zone"),
        "n_cases_missing_xout_abund1": sum(1 for r in audit_rows if r.get("xstar_local_state_status") == "missing_xout_abund1_fits"),
        "source_code_basis": "pprint.f90 print options 11/12 write xout_abund1.fits ABUNDANCES with radius, delta_r, ion_parameter, x_e, n_p, pressure, temperature(1e4 K), frac_heat_error and ion fractions",
        "policy": "do not fit triplet scale factors before matching XSTAR local zone T/ne/xi and radiation normalization",
        "zero_case_guidance": "if n_solver_cases is zero, pass one or more --solver-out-dir paths or run from the directory containing Mg/Ca solver outputs",
    }
    return audit_rows, zone_rows_all, summary


def write_markdown(path: Path, rows: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    lines: list[str] = []
    lines.append("# Mg XI / Ca XIX XSTAR local-state audit\n")
    lines.append("This diagnostic checks whether each solver run has the same local zone state as the XSTAR run that produced the triplet target. It does not search for best empirical scale factors.\n")
    lines.append("## Source-code basis\n")
    lines.append("XSTAR `pprint.f90` print option 12 accumulates radial-zone quantities and print option 11 writes `xout_abund1.fits`. The `ABUNDANCES` extension stores `radius`, `delta_r`, `ion_parameter`, `x_e`, `n_p`, `pressure`, `temperature` in units of `10^4 K`, `frac_heat_error`, and one column per ion. The selected first comparison zone is the row where the He-like ion fraction is maximum.\n")
    lines.append("## Summary\n")
    for k, v in summary.items():
        lines.append(f"- `{k}`: `{v}`")
    lines.append("\n## Cases\n")
    for r in rows:
        lines.append(f"### {r.get('ion')} logxi={r.get('log_xi_directory')}\n")
        lines.append(f"- solver f/i/r: `{r.get('solver_f_fraction')}` / `{r.get('solver_i_fraction')}` / `{r.get('solver_r_fraction')}`")
        lines.append(f"- XSTAR target f/i/r: `{r.get('xstar_target_f_fraction')}` / `{r.get('xstar_target_i_fraction')}` / `{r.get('xstar_target_r_fraction')}`")
        lines.append(f"- local-state status: `{r.get('xstar_local_state_status')}`")
        if r.get("xstar_local_state_status") == "selected_max_he_like_ion_fraction_zone":
            lines.append(f"- selected zone: `{r.get('zone_index')}`, T=`{r.get('xstar_temperature_K')}` K, ne=`{r.get('xstar_electron_density_cm^-3')}` cm^-3, xi=`{r.get('xstar_ion_parameter_xi_erg_cm_s^-1')}`")
            lines.append(f"- solver/XSTAR T ratio: `{r.get('solver_over_xstar_temperature_ratio')}`")
            lines.append(f"- solver/XSTAR ne ratio: `{r.get('solver_over_xstar_electron_density_ratio')}`")
        lines.append(f"- recommended next action: {r.get('recommended_next_action')}\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--results-root", default=".", help="Directory containing Mg/Ca solver outputs and/or xstar_test_run targets.")
    p.add_argument("--xstar-runs-root", default="", help="Optional root containing XSTAR run directories with xout_abund1.fits and/or triplet target CSVs.")
    p.add_argument("--solver-out-dir", action="append", default=[], help="Explicit Mg/Ca solver output directory. May be supplied multiple times; useful when --results-root contains only XSTAR targets.")
    p.add_argument("--no-cwd-fallback", action="store_true", help="Disable fallback scan of the current working directory when --results-root has no solver cases.")
    p.add_argument("--xstar-value-column", default="emit_outward")
    p.add_argument("--out-dir", default="mg_ca_xstar_local_state_audit_v03117")
    p.add_argument("--print-summary", action="store_true")
    return p


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    results_root = Path(args.results_root)
    xstar_runs_root = Path(args.xstar_runs_root) if args.xstar_runs_root else None
    out_dir = Path(args.out_dir)
    explicit_solver_dirs = [Path(p) for p in args.solver_out_dir]
    rows, zone_rows, summary = build(
        results_root,
        xstar_runs_root=xstar_runs_root,
        value_column=args.xstar_value_column,
        explicit_solver_dirs=explicit_solver_dirs,
        include_cwd_fallback=not args.no_cwd_fallback,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(out_dir / "mg_ca_xstar_local_state_audit.csv", rows)
    _write_csv(out_dir / "mg_ca_xstar_local_zone_candidates.csv", zone_rows)
    (out_dir / "mg_ca_xstar_local_state_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_markdown(out_dir / "mg_ca_xstar_local_state_audit.md", rows, summary)
    if args.print_summary:
        print("Mg/Ca XSTAR local-state audit")
        print("--------------------------------")
        print("This audit checks XSTAR local zone T/ne/xi and radiation-normalization prerequisites; it does not fit triplet scale factors.")
        print(f"cases={summary['n_solver_cases']} with_xout_abund1={summary['n_cases_with_xout_abund1']} missing_xout_abund1={summary['n_cases_missing_xout_abund1']}")
        if summary['n_solver_cases'] == 0:
            print("warning: no Mg/Ca solver directories found; pass --solver-out-dir explicitly or run from the directory containing solver outputs")
        print(f"wrote: {out_dir/'mg_ca_xstar_local_state_audit.csv'}")
        print(f"wrote: {out_dir/'mg_ca_xstar_local_state_audit.md'}")


if __name__ == "__main__":
    main()
