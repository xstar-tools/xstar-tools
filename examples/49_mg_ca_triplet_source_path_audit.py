#!/usr/bin/env python3
"""Mg XI / Ca XIX triplet source-path audit against XSTAR source-code branches.

This diagnostic is intentionally source-code first: it does not tune scale
factors.  It reads already generated solver-output directories, summarizes the
rate paths feeding the He-like forbidden/intercombination/resonance upper
levels, and maps each collisional data type to the corresponding XSTAR
``ucalc``/``calt`` branch that should be matched before any empirical fit is
accepted as physics.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
from pathlib import Path
from typing import Any


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
    with path.open(newline='', encoding='utf-8') as h:
        return [dict(r) for r in csv.DictReader(h)]


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text('', encoding='utf-8')
        return
    fields: list[str] = []
    for r in rows:
        for k in r:
            if k not in fields:
                fields.append(k)
    with path.open('w', newline='', encoding='utf-8') as h:
        w = csv.DictWriter(h, fieldnames=fields)
        w.writeheader(); w.writerows(rows)


def _case_from_dir(path: Path) -> tuple[str, str]:
    name = path.name.lower()
    ion = 'Mg XI' if 'mg11' in name else ('Ca XIX' if 'ca19' in name else 'unknown')
    m = re.search(r'xi([0-9]+(?:p[0-9]+)?)', name)
    xi = m.group(1).replace('p', '.') if m else 'unknown'
    return ion, xi


def _component(label: str) -> str | None:
    s = (label or '').lower()
    if '1s1.2s1.3s_1' in s or '2s1.3s' in s or '3s_1' in s:
        return 'f'
    if '1s1.2p1.3p' in s or '2p1.3p' in s or '3p_' in s:
        return 'i'
    if '1s1.2p1.1p_1' in s or '2p1.1p_1' in s or '1p_1' in s:
        return 'r'
    return None


def _xstar_branch(dt: int | None, method: str) -> dict[str, str]:
    if dt == 63 or 'type63' in method:
        return {
            'xstar_branch': 'ucalc.f90 type 63',
            'xstar_helpers': 'anl1.f90; erc.f90; amcrs.f90; velimp.f90',
            'source_formula': 'nf!=ni: anl1 angular sum -> erc shell se/sd -> ans1/ans2 branch; nf=ni: amcrs/velimp with density cutoff then final xnx multiplication',
            'source_alignment_check': 'audit literal ans1/ans2 swap, statistical weights, aa1 selector, and same-n l-mixing cutoff; do not use empirical scale as physics',
        }
    if dt == 67 or 'calt67' in method:
        return {
            'xstar_branch': 'ucalc.f90 type 67',
            'xstar_helpers': 'calt67.f90',
            'source_formula': 'temp=max(T,2.8777e6/elin); gamma=a+b log10(temp)+c log10(temp)^2; ans1=cij*xnx, ans2=cji*xnx',
            'source_alignment_check': 'v0.3.113 applies the XSTAR calt67 temperature floor before evaluating gamma',
        }
    if dt == 68 or 'calt68' in method:
        return {
            'xstar_branch': 'ucalc.f90 type 68',
            'xstar_helpers': 'calt68.f90',
            'source_formula': 'temp=max(T,2.8777e6/elin); tt=log10(temp/Z^3); gamma=a+b*tt+c*tt^2; ans1=cij*xnx, ans2=cji*xnx',
            'source_alignment_check': 'v0.3.113 applies the XSTAR calt68 temperature floor before evaluating gamma',
        }
    if dt == 69 or 'calt69' in method:
        return {
            'xstar_branch': 'ucalc.f90 type 69',
            'xstar_helpers': 'calt69.f90',
            'source_formula': 'gamma from Kato-Nakazaki fit; cji=8.626e-8*gamma/sqrt(T/1e4)/g_up; cij=cji*g_up*exp(-dE/kT)/g_lo; ans1=cij*xnx, ans2=cji*xnx',
            'source_alignment_check': 'row-by-row compare gamma/cij/cji and XSTAR detail rates if available',
        }
    if dt == 50:
        return {
            'xstar_branch': 'ucalc.f90 type 50',
            'xstar_helpers': 'pescl escape probabilities',
            'source_formula': 'ans1=Aij*(ptmp1+ptmp2), with line-specific escape probabilities when available',
            'source_alignment_check': 'type-50 3P->3S optically thin fallback already aligned for missing tau rows',
        }
    return {
        'xstar_branch': 'other/non-collisional',
        'xstar_helpers': '',
        'source_formula': '',
        'source_alignment_check': 'not a primary Mg/Ca collision-branch target',
    }


def _triplet_rate_rows(solver_dir: Path) -> list[dict[str, Any]]:
    rows = _read_csv(solver_dir / 'xstar_like_element_solver_global_bound_bound_matrix_terms.csv')
    out: list[dict[str, Any]] = []
    for r in rows:
        to_comp = _component(r.get('to_level_label', ''))
        from_comp = _component(r.get('from_level_label', ''))
        if to_comp is None and from_comp is None:
            continue
        dt = None
        try:
            if str(r.get('resonance_collisional_feed_data_type') or '').strip():
                dt = int(float(r.get('resonance_collisional_feed_data_type')))
            elif str(r.get('data_type') or '').strip():
                dt = int(float(r.get('data_type')))
        except Exception:
            dt = None
        method = str(r.get('source_method') or '')
        rate = _as_float(r.get('rate_s^-1')) or _as_float(r.get('raw_rate_s^-1')) or 0.0
        branch = _xstar_branch(dt, method)
        out.append({
            'record': r.get('record'),
            'data_type': dt,
            'source_method': method,
            'transition_kind': r.get('transition_kind'),
            'from_level': r.get('from_level'),
            'to_level': r.get('to_level'),
            'from_level_label': r.get('from_level_label'),
            'to_level_label': r.get('to_level_label'),
            'from_component': from_comp,
            'to_component': to_comp,
            'rate_s^-1': rate,
            'temperature_K': r.get('temperature_K'),
            'electron_density_cm^-3': r.get('electron_density_cm^-3'),
            **branch,
        })
    return out


def build(results_root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    detail_rows: list[dict[str, Any]] = []
    summary: dict[tuple[str, str, str, str], float] = {}
    for sdir in sorted(results_root.glob('*xstar_like_element_solver*v03111*superlevels')):
        if not sdir.is_dir():
            continue
        ion, xi = _case_from_dir(sdir)
        if ion == 'unknown':
            continue
        rows = _triplet_rate_rows(sdir)
        for r in rows:
            rr = {'ion': ion, 'log_xi': xi, 'solver_dir': sdir.name, **r}
            detail_rows.append(rr)
            comp = r.get('to_component') or 'out_of_triplet'
            key = (ion, xi, comp, str(r.get('data_type')))
            summary[key] = summary.get(key, 0.0) + float(r.get('rate_s^-1') or 0.0)
    summary_rows = [
        {'ion': k[0], 'log_xi': k[1], 'to_component': k[2], 'data_type': k[3], 'summed_rate_s^-1': v}
        for k, v in sorted(summary.items())
    ]
    payload = {
        'n_detail_rows': len(detail_rows),
        'n_summary_rows': len(summary_rows),
        'conclusion': 'This audit maps Mg XI/Ca XIX triplet-feeding paths to XSTAR source-code branches. It does not fit scale factors.',
        'source_code_first_next_steps': [
            'Compare type-63 ans1/ans2 and aa1 branch selection against XSTAR debug/detail rates.',
            'Use XSTAR radiation/log-xi normalization so solver state varies across the Mg/Ca xi grid.',
            'Use line-depth/escape context before judging emergent Mg/Ca resonance line fractions.',
        ],
    }
    return detail_rows, summary_rows, payload


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--results-root', required=True, help='Directory containing v0.3.111 Mg/Ca solver outputs')
    ap.add_argument('--out-dir', default='mg_ca_triplet_source_path_audit_v03113')
    ap.add_argument('--print-summary', action='store_true')
    args = ap.parse_args()
    results_root = Path(args.results_root)
    out_dir = Path(args.out_dir)
    detail, summary, payload = build(results_root)
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(out_dir / 'mg_ca_triplet_source_path_detail.csv', detail)
    _write_csv(out_dir / 'mg_ca_triplet_source_path_summary.csv', summary)
    (out_dir / 'mg_ca_triplet_source_path_summary.json').write_text(json.dumps(payload, indent=2, sort_keys=True), encoding='utf-8')
    md = [
        '# Mg XI / Ca XIX triplet source-path audit',
        '',
        payload['conclusion'],
        '',
        f"Detail rows: {payload['n_detail_rows']}",
        f"Summary rows: {payload['n_summary_rows']}",
        '',
        '## Source-code-first next steps',
    ]
    md.extend(f"- {x}" for x in payload['source_code_first_next_steps'])
    (out_dir / 'mg_ca_triplet_source_path_audit.md').write_text('\n'.join(md) + '\n', encoding='utf-8')
    if args.print_summary:
        print('Mg/Ca triplet source-path audit')
        print('--------------------------------')
        print(payload['conclusion'])
        print(f"detail rows={payload['n_detail_rows']} summary rows={payload['n_summary_rows']}")
        print(f"wrote: {out_dir / 'mg_ca_triplet_source_path_detail.csv'}")
        print(f"wrote: {out_dir / 'mg_ca_triplet_source_path_summary.csv'}")
        print(f"wrote: {out_dir / 'mg_ca_triplet_source_path_audit.md'}")


if __name__ == '__main__':
    main()
