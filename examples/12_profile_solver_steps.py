#!/usr/bin/env python3
"""Profile major stages of the xstar-atomic level-population solver.

This example decomposes one representative solver run into coarse wall-clock
stages so that future Python/C++ backend work can target the real hot spots.
It reports separate timings for::

  open/read ATDB
  build_index
  extract_levels
  extract_lines
  extract_collisions
  evaluate_collisions
  build_matrix
  solve_matrix
  write_outputs

Example
-------

::

  PYTHONPATH=src python examples/12_profile_solver_steps.py \
    ../xstar/data/atdb.fits \
    --element O --ion-stage 8 \
    --wavelength-min 18.8 --wavelength-max 19.1 \
    --temperature 1e6 --electron-density 1.0 \
    --linear-solver sparse \
    --out-dir solver_profile_example
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from xstar_atomic.hierarchy import ATDB
from xstar_atomic.lines import choose_z, extract_levels, extract_lines
from xstar_atomic.collisions import (
    COLLISION_DATA_TYPES,
    decode_collision_record,
    evaluate_collision_row,
    level_maps,
    row_match,
)
from xstar_atomic.solver import (
    assemble_rate_matrix,
    build_collision_rates_for_T,
    build_graph_edges,
    build_level_set,
    build_radiative_transitions,
    build_same_n_lmixing_rows,
    build_source_sink_vectors,
    choose_component_levels,
    collect_explicit_source_levels,
    make_component_diagnostics,
    make_line_output_rows,
    make_population_rows,
    maybe_int,
    prune_unconnected_levels,
    select_output_lines,
    solve_steady_state,
    write_csv,
)


def _elapsed(start: float) -> float:
    return time.perf_counter() - start


def _write_timing_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    keys: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                keys.append(key)
                seen.add(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fitsfile")
    parser.add_argument("--element", default="O")
    parser.add_argument("--ion-stage", type=int, default=8)
    parser.add_argument("--temperature", type=float, default=1.0e6)
    parser.add_argument("--electron-density", type=float, default=1.0)
    parser.add_argument("--electron-density-for-lmixing", type=float, default=1.0)
    parser.add_argument("--wavelength-min", type=float, default=18.8)
    parser.add_argument("--wavelength-max", type=float, default=19.1)
    parser.add_argument("--energy-min-kev", type=float)
    parser.add_argument("--energy-max-kev", type=float)
    parser.add_argument("--lower-level", type=int)
    parser.add_argument("--upper-level", type=int)
    parser.add_argument("--component-mode", choices=["all", "ground", "largest", "output"], default="ground")
    parser.add_argument("--ground-level", type=int, default=1)
    parser.add_argument("--prune-unconnected-levels", action="store_true")
    parser.add_argument("--linear-solver", choices=["dense", "sparse", "auto"], default="sparse")
    parser.add_argument("--phenomenological-same-n-lmixing-rate-coeff", type=float)
    parser.add_argument("--include-two-photon", action="store_true")
    parser.add_argument("--include-superlevel", action="store_true")
    parser.add_argument("--out-dir", default="solver_profile_example")
    parser.add_argument("--out-csv", default="solver_step_profile.csv")
    parser.add_argument("--summary-json", default="solver_step_profile_summary.json")
    parser.add_argument("--print-json", action="store_true")
    parser.add_argument("--index-cache", nargs="?", const=True, default=False,
                        help="Use an on-disk ATDB hierarchy index cache. Optionally provide a cache filename; default is atdb.fits.xstar_atomic_index.npz")
    parser.add_argument("--rebuild-index-cache", action="store_true",
                        help="Rebuild the ATDB hierarchy index cache before profiling")
    parser.add_argument("--index-cache-format", choices=["npz", "pickle"], default="npz",
                        help="On-disk index cache format; npz is compact and preferred, pickle is legacy")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    z = choose_z(args.element)
    if z is None:
        raise SystemExit(f"Could not map element {args.element!r} to Z")

    solver_args = SimpleNamespace(
        wavelength_min=args.wavelength_min,
        wavelength_max=args.wavelength_max,
        energy_min_kev=args.energy_min_kev,
        energy_max_kev=args.energy_max_kev,
        lower_level=args.lower_level,
        upper_level=args.upper_level,
        include_two_photon=args.include_two_photon,
        include_superlevel=args.include_superlevel,
        max_level=None,
        levels=None,
        component_mode=args.component_mode,
        ground_level=args.ground_level,
        prune_unconnected_levels=args.prune_unconnected_levels,
        source_level=None,
        sink_level=None,
        source_csv=None,
        recombination_source_csv=None,
        adjacent_ion_source_csv=None,
        auto_recombination_cascade=False,
        phenomenological_same_n_lmixing_rate_coeff=args.phenomenological_same_n_lmixing_rate_coeff,
    )

    stages: list[dict[str, Any]] = []
    total_start = time.perf_counter()

    start = time.perf_counter()
    db = ATDB(args.fitsfile)
    stages.append({"stage": "open_read_atdb", "elapsed_s": _elapsed(start)})

    start = time.perf_counter()
    cache_setting = args.index_cache
    use_cache = bool(cache_setting) or bool(args.rebuild_index_cache)
    cache_path = None if cache_setting is True or cache_setting is False else cache_setting
    cache_format = getattr(args, "index_cache_format", "npz")
    if use_cache and cache_format == "npz":
        records = db.select_records(
            z=z,
            ion_stage=args.ion_stage,
            use_cache=True,
            cache_path=cache_path,
            rebuild_cache=args.rebuild_index_cache,
            cache_format="npz",
        )
        _elements, _ions = db._index_elements or [], db._index_ions or []
    else:
        records, _elements, _ions = db.build_index(
            use_cache=use_cache,
            cache_path=cache_path,
            rebuild_cache=args.rebuild_index_cache,
            cache_format=cache_format,
        )
    stages.append({
        "stage": "build_index",
        "elapsed_s": _elapsed(start),
        "n_records": len(records),
        "index_cache_status": db.index_cache_status,
        "index_cache_path": str(db.index_cache_path) if db.index_cache_path is not None else "",
    })

    start = time.perf_counter()
    levels = extract_levels(db, records, z, args.ion_stage)
    level_by_index = {maybe_int(r.get("level_index")): r for r in levels if maybe_int(r.get("level_index")) is not None}
    stages.append({"stage": "extract_levels", "elapsed_s": _elapsed(start), "n_levels": len(levels)})

    start = time.perf_counter()
    all_lines = extract_lines(db, records, z, args.ion_stage)
    output_lines = select_output_lines(all_lines, solver_args)
    stages.append({"stage": "extract_lines", "elapsed_s": _elapsed(start), "n_lines": len(all_lines), "n_output_lines": len(output_lines)})

    start = time.perf_counter()
    level_by_index2, labels, energies, gs = level_maps(levels)
    collision_rows: list[dict[str, Any]] = []
    collision_grid_rows: list[dict[str, Any]] = []
    grid_by_record: dict[int, list[dict[str, Any]]] = {}
    for record in records:
        if not row_match(record, z, args.ion_stage):
            continue
        if record.rate_type != 3 and record.data_type not in COLLISION_DATA_TYPES:
            continue
        if record.data_type not in COLLISION_DATA_TYPES:
            continue
        summary, grid = decode_collision_record(db, record, labels, energies, gs, level_by_index2)
        collision_rows.append(summary)
        expanded_grid: list[dict[str, Any]] = []
        for g in grid:
            gg = {
                "record": record.recno,
                "element": summary.get("element"),
                "ion_stage": summary.get("ion_stage"),
                "ion_roman": summary.get("ion_roman"),
                "data_type": summary.get("data_type"),
                "rate_type": summary.get("rate_type"),
                "lower_level": summary.get("lower_level"),
                "upper_level": summary.get("upper_level"),
                "lower_label": summary.get("lower_label"),
                "upper_label": summary.get("upper_label"),
                **g,
            }
            expanded_grid.append(gg)
        grid_by_record[record.recno] = expanded_grid
        collision_grid_rows.extend(expanded_grid)
    stages.append({"stage": "extract_collisions", "elapsed_s": _elapsed(start), "n_collision_records": len(collision_rows), "n_collision_grid_rows": len(collision_grid_rows)})

    start = time.perf_counter()
    collision_eval = [
        evaluate_collision_row(row, args.temperature, grid_by_record.get(int(row.get("record") or -1), []), electron_density_cm3=args.electron_density_for_lmixing)
        for row in collision_rows
    ]
    stages.append({"stage": "evaluate_collisions", "elapsed_s": _elapsed(start), "n_collision_eval_rows": len(collision_eval)})

    start = time.perf_counter()
    level_indices_initial = build_level_set(levels, all_lines, collision_rows, solver_args)
    level_set_initial = set(level_indices_initial)
    rad_lines_initial = build_radiative_transitions(all_lines, level_set_initial, solver_args)
    graph_edges = build_graph_edges(rad_lines_initial, collision_eval, level_set_initial)
    component_diag = make_component_diagnostics(level_indices_initial, graph_edges, output_lines, args.ground_level)
    level_indices = choose_component_levels(level_indices_initial, component_diag, output_lines, args.component_mode, args.ground_level)
    pruning_diagnostics = {"enabled": False}
    if args.prune_unconnected_levels:
        selected_edges = build_graph_edges(build_radiative_transitions(all_lines, set(level_indices), solver_args), collision_eval, set(level_indices))
        level_indices, pruning_diagnostics = prune_unconnected_levels(
            level_indices, selected_edges, output_lines, args.ground_level, collect_explicit_source_levels(solver_args)
        )
    level_set = set(level_indices)
    rad_lines_matrix = build_radiative_transitions(all_lines, level_set, solver_args)
    output_lines = [r for r in output_lines if maybe_int(r.get("lower_level")) in level_set and maybe_int(r.get("upper_level")) in level_set]
    rad_rates_from_upper: dict[int, float] = {}
    for row in rad_lines_matrix:
        upper = maybe_int(row.get("upper_level"))
        aval = row.get("A_s^-1")
        try:
            aval_f = float(aval)
        except Exception:
            continue
        if upper is not None and aval_f > 0:
            rad_rates_from_upper[upper] = rad_rates_from_upper.get(upper, 0.0) + aval_f
    coll_T = build_collision_rates_for_T(collision_eval, level_set, args.temperature, args.electron_density)
    same_n_rows = build_same_n_lmixing_rows(level_indices, level_by_index, args.electron_density, args.phenomenological_same_n_lmixing_rate_coeff)
    R, transition_log = assemble_rate_matrix(level_indices, rad_lines_matrix, coll_T, same_n_rows)
    source_vec, sink_vec, source_sink_notes = build_source_sink_vectors(level_indices, solver_args, args.temperature, args.electron_density)
    stages.append({"stage": "build_matrix", "elapsed_s": _elapsed(start), "matrix_size": len(level_indices), "n_radiative_lines": len(rad_lines_matrix), "n_collision_rows_T": len(coll_T), "matrix_nnz_raw_R": int((R != 0).sum())})

    start = time.perf_counter()
    pop, solve_info = solve_steady_state(R, source_vec, sink_vec, linear_solver=args.linear_solver)
    stages.append({"stage": "solve_matrix", "elapsed_s": _elapsed(start), **{k: solve_info.get(k) for k in ("solver", "sparse_used", "matrix_size", "matrix_nnz", "matrix_density", "condition_number", "linear_residual_linf", "normalization_residual")}})

    start = time.perf_counter()
    population_rows = make_population_rows(level_indices, level_by_index, pop, args.temperature, args.electron_density, solve_info)
    line_rows = make_line_output_rows(output_lines, level_indices, pop, args.temperature, args.electron_density, solve_info, level_by_index, rad_rates_from_upper)
    transition_rows = [dict(row, temperature_K=args.temperature, electron_density_cm3=args.electron_density) for row in transition_log]
    write_csv(out_dir / "profile_lines.csv", line_rows)
    write_csv(out_dir / "profile_populations.csv", population_rows)
    write_csv(out_dir / "profile_transitions.csv", transition_rows)
    stages.append({"stage": "write_outputs", "elapsed_s": _elapsed(start), "n_line_rows": len(line_rows), "n_population_rows": len(population_rows), "n_transition_rows": len(transition_rows)})

    total_elapsed = time.perf_counter() - total_start
    stages.append({"stage": "total", "elapsed_s": total_elapsed})

    summary = {
        "fitsfile": args.fitsfile,
        "element": args.element,
        "z": z,
        "ion_stage": args.ion_stage,
        "temperature_K": args.temperature,
        "electron_density_cm^-3": args.electron_density,
        "linear_solver": args.linear_solver,
        "index_cache_status": db.index_cache_status,
        "index_cache_path": str(db.index_cache_path) if db.index_cache_path is not None else None,
        "pruning_diagnostics": pruning_diagnostics,
        "source_sink_notes": source_sink_notes,
        "solve_info": solve_info,
        "stages": stages,
    }
    out_csv = out_dir / args.out_csv
    out_json = out_dir / args.summary_json
    _write_timing_csv(out_csv, stages)
    out_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("Solver step profile")
    print("-------------------")
    for row in stages:
        print(f"{row['stage']:24s} {float(row['elapsed_s']):10.6f} s")
    print(f"Wrote step timing CSV: {out_csv}")
    print(f"Wrote step summary JSON: {out_json}")
    if args.print_json:
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
