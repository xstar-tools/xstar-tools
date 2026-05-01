"""Pure-Python reference scaffold for XSTAR-like element-coupled solvers.

This module is intentionally a *reference/diagnostic* implementation, not a
fast production backend.  It mirrors the high-level XSTAR source-code flow
``calc_hmc_element -> calc_hmc_ion -> ucalc -> msolvelucy`` by building one
Python object for an element, with one ion block per selected charge state.

The current implementation assembles XSTAR-ATDB radiative and collisional rates
for each ion block and solves the requested He-like ion with the same
statistical-equilibrium machinery used by :mod:`xstar_atomic.solver`.  It also
records adjacent-ion coupling candidates from bound-free/recombination-like ATDB
records so that later versions can replace the placeholder source terms with
XSTAR-like recombination/photoionization coupling.

The design goal is to make the physics path explicit and testable before a C++
backend is added for speed.
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from .hierarchy import ATDB, Z_TO_SYMBOL, roman
from .lines import choose_z, extract_levels, extract_lines
from .collisions import extract_collisions
from .solver import (
    assemble_rate_matrix,
    build_collision_rates_for_T,
    build_graph_edges,
    build_level_set,
    build_radiative_transitions,
    classify_helike_triplet_line,
    connected_components,
    line_energy_erg,
    make_helike_triplet_diagnostics,
    make_line_output_rows,
    maybe_float,
    maybe_int,
    prune_null_rate_levels_for_solve,
    select_output_lines,
    solve_steady_state,
)

BOUND_FREE_RATE_TYPES = {1, 2, 5, 6, 7, 8}
BOUND_FREE_DATA_TYPES = {1, 2, 6, 7, 22, 30, 49, 53, 59, 70, 74, 95, 99}


@dataclass
class IonBlockDiagnostics:
    element: str
    element_z: int
    ion_stage: int
    ion_label: str
    n_records: int
    n_levels_decoded: int
    n_levels_used: int
    n_radiative_lines_total: int
    n_radiative_lines_used: int
    n_collision_records_total: int
    n_collision_eval_rows_total: int
    n_collision_eval_rows_used: int
    n_graph_components: int
    n_graph_edges: int
    matrix_size: int
    matrix_nnz: int
    solve_status: str
    solver: str
    solver_warning: str


@dataclass
class CouplingCandidateSummary:
    element: str
    element_z: int
    lower_ion_stage: int
    upper_ion_stage: int
    n_candidate_records: int
    data_type_counts: Dict[str, int]
    rate_type_counts: Dict[str, int]
    status: str = "catalogued_not_yet_assembled"


def _counts(rows: Iterable[dict], key: str) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for row in rows:
        k = str(row.get(key, ""))
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: kv[0]))


def write_csv(path: str | Path, rows: Sequence[dict]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    keys: List[str] = []
    for row in rows:
        for key in row.keys():
            if key not in keys:
                keys.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _solver_args(**kwargs) -> SimpleNamespace:
    defaults = dict(
        include_two_photon=False,
        include_superlevel=False,
        wavelength_min=None,
        wavelength_max=None,
        energy_min_kev=None,
        energy_max_kev=None,
        lower_level=None,
        upper_level=None,
        max_level=None,
        levels=None,
        collision_rate_scale=[],
        collision_record_scale=[],
        collision_record_direction_scale=[],
        type69_ground_excitation_mode="include",
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _normalise_triplet(line_rows: Sequence[dict]) -> dict:
    sums = {"f": 0.0, "i": 0.0, "r": 0.0}
    for row in line_rows:
        comp = classify_helike_triplet_line(row)
        val = maybe_float(row.get("line_energy_emissivity_per_ion_erg_s^-1"))
        if comp in sums and val is not None and math.isfinite(val):
            sums[comp] += max(float(val), 0.0)
    total = sum(sums.values())
    if total > 0:
        frac = {f"{k}_fraction": sums[k] / total for k in ("f", "i", "r")}
    else:
        frac = {f"{k}_fraction": 0.0 for k in ("f", "i", "r")}
    R = sums["f"] / sums["i"] if sums["i"] > 0 else None
    G = (sums["f"] + sums["i"]) / sums["r"] if sums["r"] > 0 else None
    return {**{f"{k}_emissivity": sums[k] for k in ("f", "i", "r")}, **frac, "R": R, "G": G}


def _select_records(db: ATDB, z: int, ion_stage: int, *, use_cache: bool, cache_path: Optional[str]) -> list:
    return db.select_records(z=z, ion_stage=ion_stage, use_cache=use_cache, cache_path=cache_path)


def build_ion_rate_block(
    db: ATDB,
    *,
    z: int,
    ion_stage: int,
    temperature: float,
    electron_density: float,
    wavelength_min: Optional[float] = None,
    wavelength_max: Optional[float] = None,
    max_level: Optional[int] = None,
    component_mode: str = "all",
    ground_level: int = 1,
    prune_null_rate_levels: bool = True,
    linear_solver: str = "svd",
    rank_deficient_action: str = "svd",
    negative_population_action: str = "keep",
    use_cache: bool = True,
    cache_path: Optional[str] = None,
) -> Tuple[dict, List[dict], List[dict], List[dict], List[dict]]:
    """Build and solve one ion block for the reference element solver.

    Returns ``(block_summary, population_rows, line_rows, transition_rows,
    diagnostics_rows)``.  The function is deliberately verbose and writes no
    files; examples handle file I/O so this can be used in tests.
    """
    records = _select_records(db, z, ion_stage, use_cache=use_cache, cache_path=cache_path)
    levels = extract_levels(db, records, z, ion_stage)
    lines = extract_lines(db, records, z, ion_stage)
    collisions, _collision_grid, collision_eval = extract_collisions(db, records, z, ion_stage, [temperature], electron_density_cm3=electron_density)

    args = _solver_args(wavelength_min=wavelength_min, wavelength_max=wavelength_max, max_level=max_level)
    output_lines = select_output_lines(lines, args)
    level_indices = build_level_set(levels, lines, collisions, args)
    level_set = set(level_indices)
    rad_lines = build_radiative_transitions(lines, level_set, args)
    coll_rows_T = build_collision_rates_for_T(collision_eval, level_set, temperature, electron_density, args)
    edges = build_graph_edges(rad_lines, coll_rows_T, level_set)
    comps = connected_components(level_indices, edges)

    # Component pruning is intentionally conservative in this first reference
    # implementation.  It is useful for isolated-ion diagnostics but can hide
    # source/sink paths in an element-wide solve, so only ground-mode is special.
    if component_mode == "ground" and comps:
        keep = next((set(c) for c in comps if ground_level in c), set(level_indices))
        level_indices = [lev for lev in level_indices if lev in keep]
        level_set = set(level_indices)
        rad_lines = build_radiative_transitions(lines, level_set, args)
        coll_rows_T = build_collision_rates_for_T(collision_eval, level_set, temperature, electron_density, args)

    Rmat, transition_log = assemble_rate_matrix(level_indices, rad_lines, coll_rows_T)
    if prune_null_rate_levels:
        pruned, prune_info = prune_null_rate_levels_for_solve(level_indices, Rmat, np.zeros(len(level_indices)), np.zeros(len(level_indices)), output_lines, ground_level)
        if pruned != level_indices:
            keep_idx = [level_indices.index(lev) for lev in pruned]
            level_indices = pruned
            Rmat = Rmat[np.ix_(keep_idx, keep_idx)]
            level_set = set(level_indices)
            rad_lines = build_radiative_transitions(lines, level_set, args)
            coll_rows_T = build_collision_rates_for_T(collision_eval, level_set, temperature, electron_density, args)
            Rmat, transition_log = assemble_rate_matrix(level_indices, rad_lines, coll_rows_T)
    else:
        prune_info = {"enabled": False}

    if len(level_indices) == 0:
        pop = np.array([], dtype=float)
        solve_info = {"solver": "none", "solver_warning": "empty level set", "matrix_size": 0, "matrix_nnz": 0, "solution_status": "empty"}
    else:
        pop, solve_info = solve_steady_state(
            Rmat,
            linear_solver=linear_solver,
            rank_deficient_action=rank_deficient_action,
            negative_population_action=negative_population_action,
        )
        solve_info["solution_status"] = "ok" if not solve_info.get("solver_warning") else "warning"

    level_by_index = {maybe_int(row.get("level_index")): row for row in levels if maybe_int(row.get("level_index")) is not None}
    rad_rates_from_upper: Dict[int, float] = {}
    for row in rad_lines:
        u = maybe_int(row.get("upper_level"))
        A = maybe_float(row.get("A_s^-1"))
        if u is not None and A is not None and A > 0:
            rad_rates_from_upper[u] = rad_rates_from_upper.get(u, 0.0) + A

    line_rows = make_line_output_rows(output_lines, level_indices, pop, temperature, electron_density, solve_info, level_by_index, rad_rates_from_upper) if len(level_indices) else []
    pop_rows: List[dict] = []
    idx = {lev: k for k, lev in enumerate(level_indices)}
    for lev in level_indices:
        base = level_by_index.get(lev, {})
        pop_rows.append({
            "element": Z_TO_SYMBOL.get(z, str(z)),
            "ion_stage": ion_stage,
            "ion_roman": roman(ion_stage),
            "level_index": lev,
            "level_label": base.get("level_label"),
            "energy_eV": base.get("energy_eV"),
            "population_fraction": float(pop[idx[lev]]) if len(pop) else 0.0,
            "temperature_K": temperature,
            "electron_density_cm^-3": electron_density,
        })

    for row in transition_log:
        row["element"] = Z_TO_SYMBOL.get(z, str(z))
        row["ion_stage"] = ion_stage
        row["temperature_K"] = temperature
        row["electron_density_cm^-3"] = electron_density

    block_diag = IonBlockDiagnostics(
        element=Z_TO_SYMBOL.get(z, str(z)),
        element_z=z,
        ion_stage=ion_stage,
        ion_label=f"{Z_TO_SYMBOL.get(z, str(z))} {roman(ion_stage)}",
        n_records=len(records),
        n_levels_decoded=len(levels),
        n_levels_used=len(level_indices),
        n_radiative_lines_total=len(lines),
        n_radiative_lines_used=len(rad_lines),
        n_collision_records_total=len(collisions),
        n_collision_eval_rows_total=len(collision_eval),
        n_collision_eval_rows_used=len(coll_rows_T),
        n_graph_components=len(comps),
        n_graph_edges=len(edges),
        matrix_size=int(Rmat.shape[0]) if Rmat is not None else 0,
        matrix_nnz=int(np.count_nonzero(Rmat)) if Rmat is not None else 0,
        solve_status=str(solve_info.get("solution_status", "unknown")),
        solver=str(solve_info.get("solver", "")),
        solver_warning=str(solve_info.get("solver_warning", "")),
    )
    block_summary = asdict(block_diag)
    block_summary["prune_null_rate_levels"] = prune_info
    block_summary["triplet"] = _normalise_triplet(line_rows)
    return block_summary, pop_rows, line_rows, transition_log, make_helike_triplet_diagnostics(line_rows)


def catalog_adjacent_coupling_candidates(
    db: ATDB,
    *,
    z: int,
    lower_ion_stage: int,
    upper_ion_stage: int,
    use_cache: bool = True,
    cache_path: Optional[str] = None,
) -> CouplingCandidateSummary:
    """Catalogue ATDB records likely involved in adjacent-ion coupling.

    XSTAR's element-wide solver couples adjacent ions through many record types.
    This first Python reference version does not evaluate those rates yet; it
    records how many candidate records exist so the next implementation step is
    explicit and reproducible.
    """
    rows: List[dict] = []
    for stage in (lower_ion_stage, upper_ion_stage):
        records = _select_records(db, z, stage, use_cache=use_cache, cache_path=cache_path)
        for rec in records:
            if rec.rate_type in BOUND_FREE_RATE_TYPES or rec.data_type in BOUND_FREE_DATA_TYPES:
                rows.append({"data_type": rec.data_type, "rate_type": rec.rate_type, "ion_stage": stage, "record": rec.recno})
    return CouplingCandidateSummary(
        element=Z_TO_SYMBOL.get(z, str(z)),
        element_z=z,
        lower_ion_stage=lower_ion_stage,
        upper_ion_stage=upper_ion_stage,
        n_candidate_records=len(rows),
        data_type_counts=_counts(rows, "data_type"),
        rate_type_counts=_counts(rows, "rate_type"),
    )


def solve_element_reference(
    fitsfile: str | Path | None,
    *,
    element: str | int,
    he_like_stage: int,
    temperature: float,
    electron_density: float,
    adjacent_stages: Optional[Sequence[int]] = None,
    wavelength_min: Optional[float] = None,
    wavelength_max: Optional[float] = None,
    max_level: Optional[int] = None,
    component_mode: str = "all",
    prune_null_rate_levels: bool = True,
    linear_solver: str = "svd",
    rank_deficient_action: str = "svd",
    negative_population_action: str = "keep",
    index_cache: bool = True,
    index_cache_path: Optional[str] = None,
) -> dict:
    z = choose_z(str(element)) if not isinstance(element, int) else int(element)
    if z is None:
        raise ValueError(f"Could not parse element {element!r}")
    stages = list(adjacent_stages) if adjacent_stages else [he_like_stage + 1, he_like_stage]
    stages = sorted({int(s) for s in stages if int(s) > 0}, reverse=True)
    with ATDB(fitsfile, load_reals=False, prompt_for_data=False) as db:
        ion_blocks: List[dict] = []
        populations: List[dict] = []
        line_rows: List[dict] = []
        transitions: List[dict] = []
        triplet_rows: List[dict] = []
        for stage in stages:
            block, pops, lines, trans, trips = build_ion_rate_block(
                db,
                z=z,
                ion_stage=stage,
                temperature=temperature,
                electron_density=electron_density,
                wavelength_min=wavelength_min if stage == he_like_stage else None,
                wavelength_max=wavelength_max if stage == he_like_stage else None,
                max_level=max_level,
                component_mode=component_mode,
                prune_null_rate_levels=prune_null_rate_levels,
                linear_solver=linear_solver,
                rank_deficient_action=rank_deficient_action,
                negative_population_action=negative_population_action,
                use_cache=index_cache,
                cache_path=index_cache_path,
            )
            ion_blocks.append(block)
            populations.extend(pops)
            line_rows.extend(lines)
            transitions.extend(trans)
            for tr in trips:
                tr["diagnostic_ion_stage"] = stage
                triplet_rows.append(tr)
        coupling = []
        if he_like_stage + 1 in stages:
            coupling.append(asdict(catalog_adjacent_coupling_candidates(
                db,
                z=z,
                lower_ion_stage=he_like_stage,
                upper_ion_stage=he_like_stage + 1,
                use_cache=index_cache,
                cache_path=index_cache_path,
            )))
    selected_lines = [r for r in line_rows if maybe_int(r.get("ion_stage")) == he_like_stage]
    return {
        "summary": {
            "mode": "pure_python_reference_element_solver_scaffold",
            "element": Z_TO_SYMBOL.get(z, str(z)),
            "element_z": z,
            "he_like_stage": he_like_stage,
            "temperature_K": temperature,
            "electron_density_cm^-3": electron_density,
            "stages": stages,
            "n_ion_blocks": len(ion_blocks),
            "n_population_rows": len(populations),
            "n_line_rows": len(line_rows),
            "n_transition_rows": len(transitions),
            "adjacent_coupling_status": "catalogued_not_yet_assembled",
            "he_like_triplet": _normalise_triplet(selected_lines),
        },
        "ion_blocks": ion_blocks,
        "coupling_candidates": coupling,
        "populations": populations,
        "line_rows": line_rows,
        "transition_rows": transitions,
        "triplet_rows": triplet_rows,
    }


def write_element_solver_outputs(result: dict, out_dir: str | Path) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "xstar_like_element_solver_ion_blocks.csv", result.get("ion_blocks", []))
    write_csv(out / "xstar_like_element_solver_coupling_candidates.csv", result.get("coupling_candidates", []))
    write_csv(out / "xstar_like_element_solver_populations.csv", result.get("populations", []))
    write_csv(out / "xstar_like_element_solver_lines.csv", result.get("line_rows", []))
    write_csv(out / "xstar_like_element_solver_transitions.csv", result.get("transition_rows", []))
    write_csv(out / "xstar_like_element_solver_triplet.csv", result.get("triplet_rows", []))
    (out / "xstar_like_element_solver_summary.json").write_text(json.dumps(result.get("summary", {}), indent=2), encoding="utf-8")
    lines = ["# XSTAR-like element-solver summary", "", "This is a pure-Python reference/scaffold run.", ""]
    summ = result.get("summary", {})
    for key in sorted(summ):
        lines.append(f"- **{key}**: `{summ[key]}`")
    lines.append("")
    lines.append("Adjacent-ion coupling records are currently catalogued but not yet assembled into the rate matrix.")
    (out / "xstar_like_element_solver_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
