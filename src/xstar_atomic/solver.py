"""
xstar_atomic_level_population_solver_v2.py

Second steady-state level-population solver for XSTAR's packed atdb.fits. v2 adds connected-component diagnostics, ground-component solving, and explicit source/sink hooks.

This script builds on the validated ATDB readers/decoders:

  * xstar_atomic_hierarchy.py
  * xstar_atomic_extract_lines_v2.py
  * xstar_atomic_extract_collisions_v2b.py

It assembles a simple statistical-equilibrium matrix for one ion using:

  * radiative decays from decoded bound-bound line records, primarily type 50;
  * electron-impact excitation/de-excitation from evaluated collision records,
    currently type 56 and the implemented type-63 branch from v2b.

For each requested temperature and electron density it solves

    dn_i/dt = sum_j n_j R_{j->i} - n_i sum_j R_{i->j} = 0
    sum_i n_i = 1

and exports line emissivities using solved upper-level populations:

    photon_emissivity_per_ion_s^-1 = population_upper * A_ul
    energy_emissivity_per_ion_erg_s^-1 = population_upper * A_ul * h nu

The corresponding volume emissivity is

    j_line = n_ion * energy_emissivity_per_ion_erg_s^-1

If you want an emissivity coefficient per n_e n_ion comparable to the earlier
coronal direct-excitation table, use

    energy_emissivity_coeff_erg_cm3_s = energy_emissivity_per_ion / n_e

Caveats
-------
This is still a prototype collisional-radiative solver. v2 can add explicit
user-supplied source/sink terms and can restrict the matrix to the connected
component containing the ground level. It does not yet decode XSTAR recombination
records into level-resolved cascade sources automatically; instead it provides
source/sink hooks and clear diagnostics. The collision decoder now provides the XSTAR type-63 same-n l-mixing/amcrs
branch.  The older phenomenological same-n l-mixing option remains available
for controlled experiments, but it is separate from the XSTAR-equivalent
collision rates.

Examples
--------
# O VIII Ly-alpha with all O VIII levels in the matrix
python xstar_atomic_level_population_solver_v2.py ./xstar/data/atdb.fits \
  --element O --ion-stage 8 \
  --wavelength-min 18.8 --wavelength-max 19.1 \
  --temperatures 1e6 3e6 1e7 \
  --electron-densities 1.0 \
  --out-lines-csv o8_lya_pop_lines.csv \
  --out-populations-csv o8_populations.csv \
  --summary-json o8_solver_summary.json \
  --print-summary

# O VII triplet status with the current collision set
python xstar_atomic_level_population_solver_v2.py ./xstar/data/atdb.fits \
  --element O --ion-stage 7 \
  --wavelength-min 21.4 --wavelength-max 22.2 \
  --temperatures 1e6 3e6 1e7 \
  --electron-densities 1.0 1e4 1e8 \
  --out-lines-csv o7_triplet_pop_lines.csv \
  --summary-json o7_triplet_solver_summary.json \
  --print-summary
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

from .hierarchy import ATDB  # type: ignore
from .lines import (  # type: ignore
    choose_z,
    extract_levels,
    extract_lines,
)
from .collisions import extract_collisions  # type: ignore

HC_EV_A = 12398.419843320026
EV_TO_ERG = 1.602176634e-12


def maybe_float(x) -> Optional[float]:
    if x is None or x == "":
        return None
    try:
        v = float(x)
    except Exception:
        return None
    if not math.isfinite(v):
        return None
    return v


def maybe_int(x) -> Optional[int]:
    if x is None or x == "":
        return None
    try:
        return int(x)
    except Exception:
        try:
            return int(float(x))
        except Exception:
            return None


def write_csv(path: str | Path, rows: List[dict]) -> None:
    path = Path(path)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys: List[str] = []
    seen = set()
    for row in rows:
        for k in row.keys():
            if k not in seen:
                keys.append(k)
                seen.add(k)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)


def counts_by(rows: Iterable[dict], key: str) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for row in rows:
        val = str(row.get(key, ""))
        out[val] = out.get(val, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: kv[0]))


def is_bound_bound_radiative(row: dict, include_two_photon: bool = False, include_superlevel: bool = False) -> bool:
    rt = maybe_int(row.get("rate_type"))
    dt = maybe_int(row.get("data_type"))
    if rt == 4:
        return True
    if include_two_photon and rt == 9:
        return True
    if include_superlevel and rt == 14:
        return True
    # Most normal line rows are type 50/rate 4. Keep this conservative.
    if dt == 50 and rt == 4:
        return True
    return False


def line_energy_erg(row: dict) -> Optional[float]:
    eev = maybe_float(row.get("energy_eV"))
    if eev is not None and eev > 0:
        return eev * EV_TO_ERG
    wav = maybe_float(row.get("wavelength_A"))
    if wav is not None and wav > 0:
        return (HC_EV_A / wav) * EV_TO_ERG
    return None


def select_output_lines(lines: List[dict], args) -> List[dict]:
    out = []
    for row in lines:
        if not is_bound_bound_radiative(row, args.include_two_photon, args.include_superlevel):
            continue
        ll = maybe_int(row.get("lower_level"))
        ul = maybe_int(row.get("upper_level"))
        if ll is None or ul is None:
            continue
        wav = maybe_float(row.get("wavelength_A"))
        ene = maybe_float(row.get("energy_keV"))
        if args.wavelength_min is not None and (wav is None or wav < args.wavelength_min):
            continue
        if args.wavelength_max is not None and (wav is None or wav > args.wavelength_max):
            continue
        if args.energy_min_kev is not None and (ene is None or ene < args.energy_min_kev):
            continue
        if args.energy_max_kev is not None and (ene is None or ene > args.energy_max_kev):
            continue
        if args.lower_level is not None and ll != args.lower_level:
            continue
        if args.upper_level is not None and ul != args.upper_level:
            continue
        out.append(row)
    return out


def build_level_set(levels: List[dict], lines: List[dict], collisions: List[dict], args) -> List[int]:
    all_indices = sorted({maybe_int(r.get("level_index")) for r in levels if maybe_int(r.get("level_index")) is not None})
    all_indices = [i for i in all_indices if i is not None]

    if args.max_level is not None:
        all_indices = [i for i in all_indices if i <= args.max_level]

    if args.levels:
        explicit = sorted({int(x) for x in args.levels})
        # Always include endpoints of lines/collisions that touch explicitly selected levels.
        s = set(explicit)
        for row in list(lines) + list(collisions):
            ll = maybe_int(row.get("lower_level"))
            ul = maybe_int(row.get("upper_level"))
            if ll in s or ul in s:
                if ll is not None:
                    s.add(ll)
                if ul is not None:
                    s.add(ul)
        return sorted(i for i in s if i in set(all_indices))

    return all_indices


def build_radiative_transitions(lines: List[dict], level_set: set[int], args) -> List[dict]:
    trans = []
    for row in lines:
        if not is_bound_bound_radiative(row, args.include_two_photon, args.include_superlevel):
            continue
        ll = maybe_int(row.get("lower_level"))
        ul = maybe_int(row.get("upper_level"))
        a = maybe_float(row.get("A_s^-1"))
        if ll is None or ul is None or a is None or a <= 0:
            continue
        if ll not in level_set or ul not in level_set:
            continue
        if ul == ll:
            continue
        trans.append(row)
    return trans


def build_collision_rates_for_T(collision_eval: List[dict], level_set: set[int], temperature: float, electron_density: float) -> List[dict]:
    rows = []
    for row in collision_eval:
        T = maybe_float(row.get("temperature_K"))
        if T is None or abs(T - temperature) > max(1e-6 * max(abs(temperature), 1.0), 1e-20):
            continue
        ll = maybe_int(row.get("lower_level"))
        ul = maybe_int(row.get("upper_level"))
        if ll is None or ul is None or ll == ul:
            continue
        if ll not in level_set or ul not in level_set:
            continue
        qij = maybe_float(row.get("q_excitation_cm3_s"))
        qji = maybe_float(row.get("q_deexcitation_cm3_s"))
        if (qij is None or qij <= 0) and (qji is None or qji <= 0):
            continue
        rr = dict(row)
        rr["C_excitation_s^-1"] = (electron_density * qij) if qij is not None else None
        rr["C_deexcitation_s^-1"] = (electron_density * qji) if qji is not None else None
        rows.append(rr)
    return rows


def build_graph_edges(rad_lines: List[dict], collision_eval: List[dict], level_set: set[int]) -> List[Tuple[int, int, str]]:
    """Build undirected graph edges from any decoded transition/rate that can couple levels."""
    edges: List[Tuple[int, int, str]] = []
    for row in rad_lines:
        lo = maybe_int(row.get("lower_level"))
        up = maybe_int(row.get("upper_level"))
        A = maybe_float(row.get("A_s^-1"))
        if lo in level_set and up in level_set and lo != up and A is not None and A > 0:
            edges.append((lo, up, "radiative"))
    for row in collision_eval:
        lo = maybe_int(row.get("lower_level"))
        up = maybe_int(row.get("upper_level"))
        qij = maybe_float(row.get("q_excitation_cm3_s"))
        qji = maybe_float(row.get("q_deexcitation_cm3_s"))
        if lo in level_set and up in level_set and lo != up and ((qij is not None and qij > 0) or (qji is not None and qji > 0)):
            edges.append((lo, up, str(row.get("eval_method", "collision"))))
    return edges


def connected_components(level_indices: List[int], edges: List[Tuple[int, int, str]]) -> List[List[int]]:
    adj: Dict[int, set[int]] = {i: set() for i in level_indices}
    for a, b, _kind in edges:
        if a in adj and b in adj:
            adj[a].add(b)
            adj[b].add(a)
    seen: set[int] = set()
    comps: List[List[int]] = []
    for node in level_indices:
        if node in seen:
            continue
        stack = [node]
        seen.add(node)
        comp: List[int] = []
        while stack:
            x = stack.pop()
            comp.append(x)
            for y in adj.get(x, ()):
                if y not in seen:
                    seen.add(y)
                    stack.append(y)
        comps.append(sorted(comp))
    comps.sort(key=lambda c: (-len(c), min(c) if c else 10**9))
    return comps


def make_component_diagnostics(level_indices: List[int], edges: List[Tuple[int, int, str]], output_lines: List[dict], ground_level: int) -> dict:
    comps = connected_components(level_indices, edges)
    comp_id: Dict[int, int] = {}
    for k, comp in enumerate(comps):
        for lev in comp:
            comp_id[lev] = k
    out_levels = set()
    for line in output_lines:
        lo = maybe_int(line.get("lower_level"))
        up = maybe_int(line.get("upper_level"))
        if lo is not None:
            out_levels.add(lo)
        if up is not None:
            out_levels.add(up)
    edge_counts: Dict[int, int] = {k: 0 for k in range(len(comps))}
    edge_kind_counts: Dict[str, int] = {}
    for a, b, kind in edges:
        if comp_id.get(a) == comp_id.get(b) and comp_id.get(a) is not None:
            edge_counts[comp_id[a]] += 1
        edge_kind_counts[kind] = edge_kind_counts.get(kind, 0) + 1
    rows = []
    for k, comp in enumerate(comps):
        rows.append({
            "component_id": k,
            "n_levels": len(comp),
            "min_level": min(comp) if comp else None,
            "max_level": max(comp) if comp else None,
            "contains_ground_level": ground_level in comp,
            "contains_output_line_level": bool(out_levels & set(comp)),
            "n_output_line_levels": len(out_levels & set(comp)),
            "n_internal_edges": edge_counts.get(k, 0),
            "levels_preview": comp[:30],
            "levels_truncated": len(comp) > 30,
        })
    return {
        "n_components": len(comps),
        "n_edges": len(edges),
        "edge_kind_counts": dict(sorted(edge_kind_counts.items(), key=lambda kv: kv[0])),
        "components": rows,
        "level_to_component": comp_id,
    }


def choose_component_levels(level_indices: List[int], component_diag: dict, output_lines: List[dict], mode: str, ground_level: int) -> List[int]:
    comps = component_diag.get("components", [])
    level_to_component = component_diag.get("level_to_component", {})
    if mode == "all" or not comps:
        return level_indices
    selected_ids: set[int] = set()
    if mode == "ground":
        cid = level_to_component.get(ground_level)
        if cid is not None:
            selected_ids.add(int(cid))
    elif mode == "largest":
        selected_ids.add(int(comps[0]["component_id"]))
    elif mode == "output":
        for line in output_lines:
            for key in ("lower_level", "upper_level"):
                lev = maybe_int(line.get(key))
                cid = level_to_component.get(lev)
                if cid is not None:
                    selected_ids.add(int(cid))
    if not selected_ids:
        return level_indices
    return [lev for lev in level_indices if level_to_component.get(lev) in selected_ids]




def prune_unconnected_levels(
    level_indices: List[int],
    edges: List[Tuple[int, int, str]],
    output_lines: List[dict],
    ground_level: int,
    source_levels: Optional[Iterable[int]] = None,
) -> Tuple[List[int], dict]:
    """Remove isolated levels while preserving ground, output, and source levels.

    This is a lightweight connectivity pruning step. It is not a physical model
    reduction; it only removes levels with no radiative/collisional graph edge
    unless those levels are explicitly needed for output or source/sink tests.
    """
    connected: set[int] = set()
    for a, b, _kind in edges:
        connected.add(a)
        connected.add(b)
    keep: set[int] = set(connected)
    keep.add(int(ground_level))
    for line in output_lines:
        lo = maybe_int(line.get("lower_level"))
        up = maybe_int(line.get("upper_level"))
        if lo is not None:
            keep.add(lo)
        if up is not None:
            keep.add(up)
    for lev in source_levels or []:
        if lev is not None:
            keep.add(int(lev))
    pruned = [lev for lev in level_indices if lev in keep]
    removed = [lev for lev in level_indices if lev not in keep]
    return pruned, {
        "enabled": True,
        "n_levels_before": len(level_indices),
        "n_levels_after": len(pruned),
        "n_levels_removed": len(removed),
        "removed_levels_preview": removed[:50],
        "removed_levels_truncated": len(removed) > 50,
    }


def collect_explicit_source_levels(args) -> List[int]:
    """Return levels explicitly mentioned by command-line source/sink options.

    CSV source files are temperature dependent and are applied later, so this
    helper only captures levels visible from the command line at setup time.
    """
    out: set[int] = set()
    for pairs in (args.source_level or [], args.sink_level or []):
        try:
            out.add(int(pairs[0]))
        except Exception:
            pass
    return sorted(out)

def load_level_rate_csv(path: Optional[str], temperature: float, electron_density: float) -> Tuple[Dict[int, float], Dict[int, float], List[str]]:
    """Load level source/sink rates from CSV. Optional columns: temperature_K, electron_density_cm^-3."""
    src: Dict[int, float] = {}
    sink: Dict[int, float] = {}
    notes: List[str] = []
    if not path:
        return src, sink, notes
    with Path(path).open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            lev = maybe_int(row.get("level_index") or row.get("level") or row.get("upper_level"))
            if lev is None:
                continue
            rowT = maybe_float(row.get("temperature_K"))
            rowne = maybe_float(row.get("electron_density_cm^-3") or row.get("ne_cm^-3"))
            if rowT is not None and abs(rowT - temperature) > max(1e-6 * max(abs(temperature), 1.0), 1e-20):
                continue
            if rowne is not None and abs(rowne - electron_density) > max(1e-6 * max(abs(electron_density), 1.0), 1e-20):
                continue
            srate = maybe_float(row.get("source_s^-1") or row.get("source_rate_s^-1") or row.get("recombination_source_s^-1"))
            krate = maybe_float(row.get("sink_s^-1") or row.get("sink_rate_s^-1") or row.get("ionization_sink_s^-1"))
            if srate is not None and srate > 0:
                src[lev] = src.get(lev, 0.0) + srate
            if krate is not None and krate > 0:
                sink[lev] = sink.get(lev, 0.0) + krate
    notes.append(f"loaded level source/sink CSV: {path}")
    return src, sink, notes


def build_source_sink_vectors(level_indices: List[int], args, temperature: float, electron_density: float) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    idx = {lev: k for k, lev in enumerate(level_indices)}
    source = np.zeros(len(level_indices), dtype=float)
    sink = np.zeros(len(level_indices), dtype=float)
    notes: List[str] = []
    for pair in (args.source_level or []):
        lev = int(pair[0]); rate = float(pair[1])
        if lev in idx and rate > 0:
            source[idx[lev]] += rate
            notes.append(f"manual source level {lev}: {rate:g} s^-1")
    for pair in (args.sink_level or []):
        lev = int(pair[0]); rate = float(pair[1])
        if lev in idx and rate > 0:
            sink[idx[lev]] += rate
            notes.append(f"manual sink level {lev}: {rate:g} s^-1")
    for csv_path in [args.source_csv, args.recombination_source_csv, args.adjacent_ion_source_csv]:
        src_map, sink_map, csv_notes = load_level_rate_csv(csv_path, temperature, electron_density)
        notes.extend(csv_notes)
        for lev, rate in src_map.items():
            if lev in idx:
                source[idx[lev]] += rate
        for lev, rate in sink_map.items():
            if lev in idx:
                sink[idx[lev]] += rate
    if args.auto_recombination_cascade:
        notes.append("auto recombination/cascade requested but not yet decoded from ATDB records; use --recombination-source-csv for level-resolved sources")
    return source, sink, notes




def summarize_source_sink_vectors(level_indices: List[int], source: np.ndarray, sink: np.ndarray, notes: List[str]) -> dict:
    """Compact diagnostic summary for level source/sink vectors."""
    rows = []
    for k, lev in enumerate(level_indices):
        s = float(source[k]) if k < len(source) else 0.0
        t = float(sink[k]) if k < len(sink) else 0.0
        if s != 0.0 or t != 0.0:
            rows.append({"level_index": lev, "source_s^-1": s, "sink_s^-1": t})
    return {
        "n_source_terms_nonzero": int(np.count_nonzero(source)),
        "n_sink_terms_nonzero": int(np.count_nonzero(sink)),
        "source_sum_s^-1": float(np.sum(source)),
        "sink_sum_s^-1": float(np.sum(sink)),
        "nonzero_level_terms": rows,
        "notes": list(notes),
    }

def build_same_n_lmixing_rows(level_indices: List[int], level_by_index: Dict[int, dict], electron_density: float, coeff_cm3_s: Optional[float]) -> List[dict]:
    """Optional phenomenological same-n adjacent-l mixing; not an XSTAR amcrs port."""
    if coeff_cm3_s is None or coeff_cm3_s <= 0:
        return []
    rows: List[dict] = []
    levs = sorted(level_indices)
    for i, a in enumerate(levs):
        la = level_by_index.get(a, {})
        na = maybe_int(la.get("n")); ella = maybe_int(la.get("l"))
        if na is None or ella is None:
            continue
        for b in levs[i+1:]:
            lb = level_by_index.get(b, {})
            nb = maybe_int(lb.get("n")); ellb = maybe_int(lb.get("l"))
            if nb == na and ellb is not None and abs(ellb - ella) == 1:
                rate = electron_density * coeff_cm3_s
                rows.append({
                    "kind": "phenomenological_same_n_lmixing",
                    "lower_level": a,
                    "upper_level": b,
                    "C_ab_s^-1": rate,
                    "C_ba_s^-1": rate,
                    "eval_method": "phenomenological_same_n_lmixing_not_xstar_amcrs",
                })
    return rows


def assemble_rate_matrix(level_indices: List[int], rad_lines: List[dict], coll_rows_T: List[dict], same_n_lmix_rows: Optional[List[dict]] = None) -> Tuple[np.ndarray, List[dict]]:
    """Return rate matrix R where R[i,j] is rate j -> i, plus transition log."""
    n = len(level_indices)
    idx = {lev: k for k, lev in enumerate(level_indices)}
    R = np.zeros((n, n), dtype=float)
    transition_log: List[dict] = []

    # Radiative: upper -> lower at A_ul.
    for row in rad_lines:
        lower = maybe_int(row.get("lower_level"))
        upper = maybe_int(row.get("upper_level"))
        A = maybe_float(row.get("A_s^-1"))
        if lower not in idx or upper not in idx or A is None or A <= 0:
            continue
        i = idx[lower]
        j = idx[upper]
        R[i, j] += A
        transition_log.append({
            "kind": "radiative_decay",
            "from_level": upper,
            "to_level": lower,
            "rate_s^-1": A,
            "record": row.get("record"),
            "source_method": f"data_type_{row.get('data_type')}_rate_type_{row.get('rate_type')}",
        })

    # Collisions: lower -> upper and upper -> lower.
    for row in coll_rows_T:
        lower = maybe_int(row.get("lower_level"))
        upper = maybe_int(row.get("upper_level"))
        if lower not in idx or upper not in idx:
            continue
        qij_rate = maybe_float(row.get("C_excitation_s^-1"))
        qji_rate = maybe_float(row.get("C_deexcitation_s^-1"))
        if qij_rate is not None and qij_rate > 0:
            R[idx[upper], idx[lower]] += qij_rate
            transition_log.append({
                "kind": "collisional_excitation",
                "from_level": lower,
                "to_level": upper,
                "rate_s^-1": qij_rate,
                "record": row.get("record"),
                "source_method": row.get("eval_method"),
            })
        if qji_rate is not None and qji_rate > 0:
            R[idx[lower], idx[upper]] += qji_rate
            transition_log.append({
                "kind": "collisional_deexcitation",
                "from_level": upper,
                "to_level": lower,
                "rate_s^-1": qji_rate,
                "record": row.get("record"),
                "source_method": row.get("eval_method"),
            })

    # Optional phenomenological same-n l-mixing.
    for row in same_n_lmix_rows or []:
        a = maybe_int(row.get("lower_level"))
        b = maybe_int(row.get("upper_level"))
        rab = maybe_float(row.get("C_ab_s^-1"))
        rba = maybe_float(row.get("C_ba_s^-1"))
        if a in idx and b in idx and a != b:
            if rab is not None and rab > 0:
                R[idx[b], idx[a]] += rab
                transition_log.append({"kind": "phenomenological_same_n_lmixing", "from_level": a, "to_level": b, "rate_s^-1": rab, "source_method": row.get("eval_method")})
            if rba is not None and rba > 0:
                R[idx[a], idx[b]] += rba
                transition_log.append({"kind": "phenomenological_same_n_lmixing", "from_level": b, "to_level": a, "rate_s^-1": rba, "source_method": row.get("eval_method")})

    return R, transition_log


def solve_steady_state(
    R: np.ndarray,
    source_vector: Optional[np.ndarray] = None,
    sink_rates: Optional[np.ndarray] = None,
    *,
    linear_solver: str = "dense",
) -> Tuple[np.ndarray, dict]:
    """Solve statistical equilibrium for ``R[i, j] = rate j -> i``.

    Optional ``source_vector`` adds ``+S_i`` to ``dn_i/dt``. Optional
    ``sink_rates`` adds ``-K_i n_i``. The normalization equation is still
    imposed, so source/sink terms should be interpreted as controlled prototype
    drivers unless a full adjacent-ion balance is supplied.

    Parameters
    ----------
    R:
        Dense transition-rate matrix.
    source_vector, sink_rates:
        Optional source and sink terms in s^-1.
    linear_solver:
        ``"dense"`` uses NumPy ``solve``/``lstsq``. ``"sparse"`` attempts
        SciPy sparse ``spsolve`` and falls back to dense least-squares if
        SciPy is unavailable or the sparse solve fails. ``"auto"`` uses sparse
        for matrices with at least 64 levels when SciPy is available.
    """
    n = R.shape[0]
    A = np.zeros((n, n), dtype=float)
    for i in range(n):
        for j in range(n):
            if i != j:
                A[i, j] += R[i, j]
        A[i, i] -= np.sum(R[:, i]) - R[i, i]
    if sink_rates is not None:
        for i in range(n):
            if sink_rates[i] > 0:
                A[i, i] -= sink_rates[i]

    # Replace last equation by normalization. For source terms, solve A n = -S
    # plus normalization in the final row.
    M = A.copy()
    b = np.zeros(n, dtype=float)
    if source_vector is not None:
        b[:] = -source_vector
    M[-1, :] = 1.0
    b[-1] = 1.0

    requested_solver = str(linear_solver or "dense").lower()
    nnz = int(np.count_nonzero(M))
    abs_M = np.abs(M)
    diag_abs = np.abs(np.diag(M)) if n else np.array([], dtype=float)
    row_abs_sum = np.sum(abs_M, axis=1) if n else np.array([], dtype=float)
    info = {
        "matrix_size": n,
        "matrix_nnz": nnz,
        "matrix_density": float(nnz / (n * n)) if n else None,
        "matrix_rank": None,
        "matrix_effective_rank_tol": None,
        "matrix_singular_value_min": None,
        "matrix_singular_value_max": None,
        "condition_number": None,
        "diagonal_abs_min": float(np.min(diag_abs)) if diag_abs.size else None,
        "diagonal_abs_max": float(np.max(diag_abs)) if diag_abs.size else None,
        "row_abs_sum_min": float(np.min(row_abs_sum)) if row_abs_sum.size else None,
        "row_abs_sum_max": float(np.max(row_abs_sum)) if row_abs_sum.size else None,
        "solver": None,
        "solver_requested": requested_solver,
        "solver_warning": "",
        "sparse_available": False,
        "sparse_used": False,
        "n_source_terms_nonzero": int(np.count_nonzero(source_vector)) if source_vector is not None else 0,
        "n_sink_terms_nonzero": int(np.count_nonzero(sink_rates)) if sink_rates is not None else 0,
        "source_sum_s^-1": float(np.sum(source_vector)) if source_vector is not None else 0.0,
        "sink_sum_s^-1": float(np.sum(sink_rates)) if sink_rates is not None else 0.0,
    }

    scipy_sparse = None
    scipy_splinalg = None
    try:
        import scipy.sparse as scipy_sparse  # type: ignore
        import scipy.sparse.linalg as scipy_splinalg  # type: ignore
        info["sparse_available"] = True
    except Exception:
        pass

    use_sparse = requested_solver == "sparse" or (requested_solver == "auto" and info["sparse_available"] and n >= 64)

    # Dense diagnostics are useful but can be expensive for very large matrices.
    if n <= 800:
        try:
            sv = np.linalg.svd(M, compute_uv=False)
            if sv.size:
                info["matrix_singular_value_min"] = float(np.min(sv))
                info["matrix_singular_value_max"] = float(np.max(sv))
                tol = float(max(M.shape) * np.finfo(float).eps * np.max(sv))
                info["matrix_effective_rank_tol"] = tol
                info["matrix_rank"] = int(np.sum(sv > tol))
                if np.min(sv) > 0:
                    cond = float(np.max(sv) / np.min(sv))
                    if math.isfinite(cond):
                        info["condition_number"] = cond
        except Exception:
            try:
                info["matrix_rank"] = int(np.linalg.matrix_rank(M))
            except Exception:
                pass
            try:
                cond = float(np.linalg.cond(M))
                if math.isfinite(cond):
                    info["condition_number"] = cond
            except Exception:
                pass

    try:
        if use_sparse:
            if scipy_sparse is None or scipy_splinalg is None:
                raise RuntimeError("SciPy sparse solver requested but scipy is not available")
            info["solver"] = "scipy.sparse.linalg.spsolve"
            info["sparse_used"] = True
            pop = scipy_splinalg.spsolve(scipy_sparse.csr_matrix(M), b)
            pop = np.asarray(pop, dtype=float)
            if not np.all(np.isfinite(pop)):
                raise RuntimeError("sparse solve returned non-finite populations")
        else:
            info["solver"] = "numpy.linalg.solve"
            pop = np.linalg.solve(M, b)
    except Exception as exc:
        info["solver"] = "numpy.linalg.lstsq"
        info["solver_warning"] = f"solve failed: {exc}; used least-squares"
        pop, *_ = np.linalg.lstsq(M, b, rcond=None)

    # Clean tiny numerical negatives and renormalize.
    pop[np.abs(pop) < 1e-300] = 0.0
    if np.any(pop < -1e-8):
        info["solver_warning"] = (info.get("solver_warning", "") + "; negative populations present").strip("; ")
    pop = np.where(pop < 0.0, 0.0, pop)
    s = float(np.sum(pop))
    if s > 0:
        pop /= s
    else:
        # Fallback: put all population in ground if something pathological happens.
        pop[:] = 0.0
        pop[0] = 1.0
        info["solver_warning"] = (info.get("solver_warning", "") + "; zero population sum fallback").strip("; ")
    info["population_sum"] = float(np.sum(pop))
    info["min_population"] = float(np.min(pop)) if len(pop) else None
    info["max_population"] = float(np.max(pop)) if len(pop) else None
    try:
        residual = M @ pop - b
        info["linear_residual_l2"] = float(np.linalg.norm(residual))
        info["linear_residual_linf"] = float(np.max(np.abs(residual))) if residual.size else 0.0
        info["normalization_residual"] = float(abs(np.sum(pop) - 1.0))
    except Exception:
        info["linear_residual_l2"] = None
        info["linear_residual_linf"] = None
        info["normalization_residual"] = None
    return pop, info


def make_population_rows(level_indices: List[int], level_by_index: Dict[int, dict], pop: np.ndarray, T: float, ne: float, solve_info: dict) -> List[dict]:
    rows = []
    for k, lev in enumerate(level_indices):
        base = level_by_index.get(lev, {})
        rows.append({
            "temperature_K": T,
            "electron_density_cm^-3": ne,
            "level_index": lev,
            "population_fraction": float(pop[k]),
            "level_label": base.get("label"),
            "energy_eV": base.get("energy_eV"),
            "g": base.get("g"),
            "n": base.get("n"),
            "l": base.get("l"),
            "solver": solve_info.get("solver"),
            "solver_warning": solve_info.get("solver_warning"),
        })
    return rows


def make_line_output_rows(output_lines: List[dict], level_indices: List[int], pop: np.ndarray, T: float, ne: float, solve_info: dict, level_by_index: Dict[int, dict], rad_rates_from_upper: Dict[int, float]) -> List[dict]:
    idx = {lev: k for k, lev in enumerate(level_indices)}
    rows = []
    for line in output_lines:
        lower = maybe_int(line.get("lower_level"))
        upper = maybe_int(line.get("upper_level"))
        Aul = maybe_float(line.get("A_s^-1"))
        Eerg = line_energy_erg(line)
        if lower not in idx or upper not in idx or Aul is None or Aul <= 0 or Eerg is None:
            population_upper = 0.0
            photon_per_ion = None
            energy_per_ion = None
            coeff = None
        else:
            population_upper = float(pop[idx[upper]])
            photon_per_ion = population_upper * Aul
            energy_per_ion = photon_per_ion * Eerg
            coeff = energy_per_ion / ne if ne > 0 else None
        total_A_upper = rad_rates_from_upper.get(upper or -999, 0.0)
        branching = Aul / total_A_upper if Aul is not None and total_A_upper > 0 else None
        rows.append({
            "temperature_K": T,
            "electron_density_cm^-3": ne,
            "record": line.get("record"),
            "element": line.get("element"),
            "ion_stage": line.get("ion_stage"),
            "ion_roman": line.get("ion_roman"),
            "lower_level": lower,
            "upper_level": upper,
            "lower_label": line.get("lower_label"),
            "upper_label": line.get("upper_label"),
            "wavelength_A": line.get("wavelength_A"),
            "energy_eV": line.get("energy_eV"),
            "energy_keV": line.get("energy_keV"),
            "A_s^-1": Aul,
            "branching_ratio_within_decoded_lines": branching,
            "upper_population_fraction": population_upper,
            "line_photon_emissivity_per_ion_s^-1": photon_per_ion,
            "line_energy_emissivity_per_ion_erg_s^-1": energy_per_ion,
            "line_energy_emissivity_coeff_per_ne_nion_erg_cm3_s": coeff,
            "matrix_size": solve_info.get("matrix_size"),
            "matrix_rank": solve_info.get("matrix_rank"),
            "condition_number": solve_info.get("condition_number"),
            "solver": solve_info.get("solver"),
            "solver_warning": solve_info.get("solver_warning"),
        })
    return rows




def classify_o7_triplet_line(row: dict) -> Optional[str]:
    """Classify common O VII triplet components by wavelength/upper level.

    Returns ``f`` for the forbidden line near 22.101 Å, ``i`` for the
    intercombination components near 21.804--21.807 Å, and ``r`` for the
    resonance line near 21.602 Å.  The classification is intentionally narrow
    and used only for O VII diagnostic summaries.
    """
    wav = maybe_float(row.get("wavelength_A"))
    upper = maybe_int(row.get("upper_level"))
    if wav is None:
        return None
    if abs(wav - 22.1012) < 0.02 or upper == 2:
        return "f"
    if abs(wav - 21.8070) < 0.03 or upper in (3, 5):
        return "i"
    if abs(wav - 21.6020) < 0.02 or upper == 7:
        return "r"
    return None


def make_o7_triplet_diagnostics(line_rows: List[dict]) -> List[dict]:
    """Compute O VII triplet diagnostics R=f/i and G=(f+i)/r.

    The diagnostics use the solver line-energy emissivity per ion. If those
    quantities are absent, the output values are left as ``None``.  This helper
    is useful for stress-testing the solver but should not be interpreted as a
    final physical O VII triplet prediction unless the source/cascade model is
    physically complete.
    """
    grouped: Dict[Tuple[float, float], Dict[str, float]] = {}
    counts: Dict[Tuple[float, float], Dict[str, int]] = {}
    for row in line_rows:
        if str(row.get("element", "")).strip().upper() != "O" or maybe_int(row.get("ion_stage")) != 7:
            continue
        kind = classify_o7_triplet_line(row)
        if not kind:
            continue
        T = maybe_float(row.get("temperature_K"))
        ne = maybe_float(row.get("electron_density_cm^-3"))
        val = maybe_float(row.get("line_energy_emissivity_per_ion_erg_s^-1"))
        if T is None or ne is None:
            continue
        key = (T, ne)
        grouped.setdefault(key, {"f": 0.0, "i": 0.0, "r": 0.0})
        counts.setdefault(key, {"f": 0, "i": 0, "r": 0})
        if val is not None:
            grouped[key][kind] += val
        counts[key][kind] += 1
    rows: List[dict] = []
    for (T, ne), vals in sorted(grouped.items()):
        f = vals.get("f", 0.0)
        i = vals.get("i", 0.0)
        r = vals.get("r", 0.0)
        rows.append({
            "temperature_K": T,
            "electron_density_cm^-3": ne,
            "forbidden_energy_per_ion_erg_s^-1": f,
            "intercombination_energy_per_ion_erg_s^-1": i,
            "resonance_energy_per_ion_erg_s^-1": r,
            "R_f_over_i": (f / i) if i > 0 else None,
            "G_f_plus_i_over_r": ((f + i) / r) if r > 0 else None,
            "n_forbidden_components": counts[(T, ne)].get("f", 0),
            "n_intercombination_components": counts[(T, ne)].get("i", 0),
            "n_resonance_components": counts[(T, ne)].get("r", 0),
            "diagnostic_note": "prototype solver diagnostic; requires physical source/cascade model for final interpretation",
        })
    return rows

def summarize(levels: List[dict], rad_lines_matrix: List[dict], output_lines: List[dict], collisions: List[dict], collision_eval: List[dict], used_collision_eval: List[dict], line_rows: List[dict], population_rows: List[dict], solve_infos: List[dict]) -> dict:
    matched_pairs = {(maybe_int(r.get("lower_level")), maybe_int(r.get("upper_level"))) for r in used_collision_eval}
    output_pairs = {(maybe_int(r.get("lower_level")), maybe_int(r.get("upper_level"))) for r in output_lines}
    return {
        "n_levels_total_decoded": len(levels),
        "n_levels_in_population_output": len({r.get("level_index") for r in population_rows}),
        "n_radiative_lines_in_matrix": len(rad_lines_matrix),
        "n_output_lines_selected": len(output_lines),
        "n_collision_records_total": len(collisions),
        "n_collision_eval_rows_total": len(collision_eval),
        "n_collision_eval_rows_used_in_matrix": len(used_collision_eval),
        "n_population_rows": len(population_rows),
        "n_line_output_rows": len(line_rows),
        "n_output_level_pairs": len(output_pairs),
        "n_collision_level_pairs_used": len(matched_pairs),
        "n_output_pairs_with_used_collision": len(output_pairs & matched_pairs),
        "radiative_line_counts_by_data_type": counts_by(rad_lines_matrix, "data_type"),
        "collision_counts_by_data_type": counts_by(collisions, "data_type"),
        "collision_eval_counts_by_method_total": counts_by(collision_eval, "eval_method"),
        "collision_eval_counts_by_method_used": counts_by(used_collision_eval, "eval_method"),
        "solves": solve_infos,
    }


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description="Solve first-pass XSTAR Atomic level populations and line emissivities.")
    p.add_argument("fitsfile")
    p.add_argument("--element", required=True, help="Element symbol, e.g. O, Ne, Fe")
    p.add_argument("--ion-stage", type=int, required=True, help="Ion stage, e.g. 8 for O VIII")
    p.add_argument("--temperatures", type=float, nargs="+", required=True, help="Temperatures in K")
    p.add_argument("--electron-densities", type=float, nargs="+", default=[1.0], help="Electron densities in cm^-3")
    p.add_argument("--wavelength-min", type=float)
    p.add_argument("--wavelength-max", type=float)
    p.add_argument("--energy-min-kev", type=float)
    p.add_argument("--energy-max-kev", type=float)
    p.add_argument("--lower-level", type=int)
    p.add_argument("--upper-level", type=int)
    p.add_argument("--levels", type=int, nargs="*", help="Optional explicit levels to include; endpoints connected to them are also included")
    p.add_argument("--max-level", type=int, help="Only include decoded levels with level_index <= this value")
    p.add_argument("--prune-unconnected-levels", action="store_true",
                   help="Remove isolated levels before solving while preserving ground, output, and explicit source/sink levels")
    p.add_argument("--component-mode", choices=["all", "ground", "largest", "output"], default="all",
                   help="Restrict matrix to connected component(s): all, ground, largest, or components containing output lines")
    p.add_argument("--ground-level", type=int, default=1, help="Ground/reference level for component-mode=ground")
    p.add_argument("--component-json", help="Write connected-component diagnostics JSON")
    p.add_argument("--source-level", nargs=2, action="append", metavar=("LEVEL", "RATE_S_INV"),
                   help="Add explicit source into a level, in s^-1 per ion normalization unit; may be repeated")
    p.add_argument("--sink-level", nargs=2, action="append", metavar=("LEVEL", "RATE_S_INV"),
                   help="Add explicit sink out of a level, in s^-1; may be repeated")
    p.add_argument("--source-csv", help="CSV with level_index, source_s^-1 and/or sink_s^-1; optional temperature_K and electron_density_cm^-3")
    p.add_argument("--recombination-source-csv", help="Alias/source CSV for level-resolved recombination/cascade sources")
    p.add_argument("--adjacent-ion-source-csv", help="CSV hook for explicit adjacent-ion source/sink terms")
    p.add_argument("--auto-recombination-cascade", action="store_true",
                   help="Record a diagnostic that automatic ATDB recombination/cascade decoding is requested but not yet implemented")
    p.add_argument("--phenomenological-same-n-lmixing-rate-coeff", type=float,
                   help="Optional experimental same-n adjacent-l mixing coefficient in cm^3 s^-1; not an XSTAR amcrs port")
    p.add_argument("--electron-density-for-lmixing", type=float, default=None,
                   help="Electron density in cm^-3 used by the XSTAR type-63 same-n l-mixing impact-parameter cutoff; defaults to the first --electron-densities value")
    p.add_argument("--linear-solver", choices=["dense", "sparse", "auto"], default="dense",
                   help="Linear algebra backend for the statistical-equilibrium solve. Sparse uses scipy.sparse.linalg.spsolve when available.")
    p.add_argument("--include-two-photon", action="store_true")
    p.add_argument("--include-superlevel", action="store_true")
    p.add_argument("--out-lines-csv", default="level_population_lines.csv")
    p.add_argument("--out-populations-csv")
    p.add_argument("--out-transitions-csv")
    p.add_argument("--out-triplet-csv", help="Write O VII triplet diagnostic CSV with R=f/i and G=(f+i)/r when applicable")
    p.add_argument("--triplet-diagnostics", choices=["auto", "o7", "none"], default="auto",
                   help="Compute O VII triplet R/G diagnostics for O VII output lines")
    p.add_argument("--summary-json")
    p.add_argument("--print-summary", action="store_true")
    p.add_argument("--index-cache", nargs="?", const=True, default=False,
                   help="Use an on-disk ATDB hierarchy index cache. Optionally provide a cache filename; default is atdb.fits.xstar_atomic_index.npz")
    p.add_argument("--rebuild-index-cache", action="store_true",
                   help="Rebuild the ATDB hierarchy index cache before solving")
    p.add_argument("--index-cache-format", choices=["npz", "pickle"], default="npz",
                   help="On-disk index cache format; npz is compact and preferred, pickle is legacy")
    args = p.parse_args(argv)

    z = choose_z(args.element)
    if z is None:
        raise SystemExit(f"Could not map element {args.element!r} to Z")

    db = ATDB(args.fitsfile)
    # ATDB from xstar_atomic_hierarchy.py exposes build_index(), not index_records().
    cache_setting = args.index_cache
    use_cache = bool(cache_setting) or bool(args.rebuild_index_cache)
    cache_path = None if cache_setting is True or cache_setting is False else cache_setting
    cache_format = getattr(args, "index_cache_format", "npz")
    if use_cache and cache_format == "npz":
        # Fast array-backed path: select only records for this ion, then convert
        # only those rows to IndexedRecord objects.
        records = db.select_records(
            z=z,
            ion_stage=args.ion_stage,
            use_cache=True,
            cache_path=cache_path,
            rebuild_cache=args.rebuild_index_cache,
            cache_format="npz",
        )
        elements = db._index_elements or []
        ions = db._index_ions or []
    else:
        records, elements, ions = db.build_index(
            use_cache=use_cache,
            cache_path=cache_path,
            rebuild_cache=args.rebuild_index_cache,
            cache_format=cache_format,
        )

    levels = extract_levels(db, records, z, args.ion_stage)
    level_by_index: Dict[int, dict] = {maybe_int(r.get("level_index")): r for r in levels if maybe_int(r.get("level_index")) is not None}

    all_lines = extract_lines(db, records, z, args.ion_stage)
    output_lines = select_output_lines(all_lines, args)

    # Collision decoder evaluates at all requested temperatures once.  Most q_ij are density-independent;
    # type-63 same-n l-mixing uses this density only for the impact-parameter cutoff.
    lmix_ne = args.electron_density_for_lmixing if args.electron_density_for_lmixing is not None else float(args.electron_densities[0])
    collisions, _collision_grid, collision_eval = extract_collisions(
        db, records, z, args.ion_stage, args.temperatures, electron_density_cm3=lmix_ne
    )

    level_indices_initial = build_level_set(levels, all_lines, collisions, args)
    level_set_initial = set(level_indices_initial)

    rad_lines_initial = build_radiative_transitions(all_lines, level_set_initial, args)
    graph_edges = build_graph_edges(rad_lines_initial, collision_eval, level_set_initial)
    component_diagnostics_initial = make_component_diagnostics(
        level_indices_initial, graph_edges, output_lines, args.ground_level
    )

    level_indices = choose_component_levels(
        level_indices_initial, component_diagnostics_initial, output_lines, args.component_mode, args.ground_level
    )
    pruning_diagnostics = {"enabled": False}
    if args.prune_unconnected_levels:
        selected_edges_for_pruning = build_graph_edges(
            build_radiative_transitions(all_lines, set(level_indices), args),
            collision_eval,
            set(level_indices),
        )
        level_indices, pruning_diagnostics = prune_unconnected_levels(
            level_indices,
            selected_edges_for_pruning,
            output_lines,
            args.ground_level,
            collect_explicit_source_levels(args),
        )
    level_set = set(level_indices)

    rad_lines_matrix = build_radiative_transitions(all_lines, level_set, args)
    # Only output lines in the included matrix level set.
    output_lines = [r for r in output_lines if maybe_int(r.get("lower_level")) in level_set and maybe_int(r.get("upper_level")) in level_set]

    component_diagnostics_selected = make_component_diagnostics(
        level_indices, build_graph_edges(rad_lines_matrix, collision_eval, level_set), output_lines, args.ground_level
    )
    if args.component_json:
        Path(args.component_json).write_text(json.dumps({
            "initial": component_diagnostics_initial,
            "selected": component_diagnostics_selected,
            "component_mode": args.component_mode,
            "ground_level": args.ground_level,
        }, indent=2), encoding="utf-8")

    rad_rates_from_upper: Dict[int, float] = {}
    for row in rad_lines_matrix:
        u = maybe_int(row.get("upper_level"))
        A = maybe_float(row.get("A_s^-1"))
        if u is not None and A is not None and A > 0:
            rad_rates_from_upper[u] = rad_rates_from_upper.get(u, 0.0) + A

    all_line_rows: List[dict] = []
    all_population_rows: List[dict] = []
    all_transition_rows: List[dict] = []
    used_collision_eval_rows: List[dict] = []
    solve_infos: List[dict] = []
    source_sink_summaries: List[dict] = []

    for T in args.temperatures:
        for ne in args.electron_densities:
            coll_T = build_collision_rates_for_T(collision_eval, level_set, T, ne)
            used_collision_eval_rows.extend(coll_T)
            same_n_rows = build_same_n_lmixing_rows(
                level_indices, level_by_index, ne, args.phenomenological_same_n_lmixing_rate_coeff
            )
            R, trans_log = assemble_rate_matrix(level_indices, rad_lines_matrix, coll_T, same_n_rows)
            source_vec, sink_vec, source_sink_notes = build_source_sink_vectors(level_indices, args, T, ne)
            ss_summary = summarize_source_sink_vectors(level_indices, source_vec, sink_vec, source_sink_notes)
            ss_summary.update({"temperature_K": T, "electron_density_cm^-3": ne})
            source_sink_summaries.append(ss_summary)
            pop, info = solve_steady_state(R, source_vec, sink_vec, linear_solver=args.linear_solver)
            info.update({
                "temperature_K": T,
                "electron_density_cm^-3": ne,
                "n_radiative_transitions_in_matrix": len([x for x in trans_log if x.get("kind") == "radiative_decay"]),
                "n_collisional_transitions_in_matrix": len([x for x in trans_log if str(x.get("kind", "")).startswith("collisional")]),
                "n_phenomenological_same_n_lmixing_transitions": len([x for x in trans_log if x.get("kind") == "phenomenological_same_n_lmixing"]),
                "source_sink_notes": source_sink_notes,
                "auto_recombination_cascade_status": "not_implemented_use_recombination_source_csv" if args.auto_recombination_cascade else "not_requested",
            })
            solve_infos.append(info)
            all_population_rows.extend(make_population_rows(level_indices, level_by_index, pop, T, ne, info))
            all_line_rows.extend(make_line_output_rows(output_lines, level_indices, pop, T, ne, info, level_by_index, rad_rates_from_upper))
            for tr in trans_log:
                tr = dict(tr)
                tr["temperature_K"] = T
                tr["electron_density_cm^-3"] = ne
                all_transition_rows.append(tr)

    write_csv(args.out_lines_csv, all_line_rows)
    if args.out_populations_csv:
        write_csv(args.out_populations_csv, all_population_rows)
    if args.out_transitions_csv:
        write_csv(args.out_transitions_csv, all_transition_rows)

    do_triplet = args.triplet_diagnostics == "o7" or (
        args.triplet_diagnostics == "auto" and str(args.element).strip().upper() == "O" and int(args.ion_stage) == 7
    )
    triplet_rows = make_o7_triplet_diagnostics(all_line_rows) if do_triplet else []
    if args.out_triplet_csv:
        write_csv(args.out_triplet_csv, triplet_rows)

    summary = summarize(levels, rad_lines_matrix, output_lines, collisions, collision_eval, used_collision_eval_rows, all_line_rows, all_population_rows, solve_infos)
    summary.update({
        "fitsfile": args.fitsfile,
        "element": args.element,
        "z": z,
        "ion_stage": args.ion_stage,
        "temperatures_K": args.temperatures,
        "electron_densities_cm^-3": args.electron_densities,
        "out_lines_csv": args.out_lines_csv,
        "out_populations_csv": args.out_populations_csv,
        "out_transitions_csv": args.out_transitions_csv,
        "out_triplet_csv": args.out_triplet_csv,
        "component_mode": args.component_mode,
        "prune_unconnected_levels": bool(args.prune_unconnected_levels),
        "pruning_diagnostics": pruning_diagnostics,
        "ground_level": args.ground_level,
        "n_components_initial": component_diagnostics_initial.get("n_components"),
        "n_components_selected": component_diagnostics_selected.get("n_components"),
        "n_levels_initial": len(level_indices_initial),
        "n_levels_selected": len(level_indices),
        "component_diagnostics_initial_summary": component_diagnostics_initial.get("components", [])[:10],
        "component_diagnostics_selected_summary": component_diagnostics_selected.get("components", [])[:10],
        "recombination_cascade_auto_status": "not_implemented_use_recombination_source_csv" if args.auto_recombination_cascade else "not_requested",
        "same_n_lmixing_status": ("phenomenological_extra_enabled_on_top_of_xstar_amcrs" if args.phenomenological_same_n_lmixing_rate_coeff else "xstar_amcrs_collision_decoder_enabled"),
        "source_sink_interface": {
            "manual_source_terms": args.source_level or [],
            "manual_sink_terms": args.sink_level or [],
            "source_csv": args.source_csv,
            "recombination_source_csv": args.recombination_source_csv,
            "adjacent_ion_source_csv": args.adjacent_ion_source_csv,
        },
        "source_sink_summaries": source_sink_summaries,
        "triplet_diagnostics_enabled": bool(do_triplet),
        "triplet_diagnostics": triplet_rows,
    })
    if args.summary_json:
        Path(args.summary_json).write_text(json.dumps(summary, indent=2), encoding="utf-8")
    if args.print_summary:
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
