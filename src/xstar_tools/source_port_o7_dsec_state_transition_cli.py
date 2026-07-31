"""Capture pure-Python O VII DSEC state transitions through selected call-1 evaluations.

Diagnostic-only helper for xstar_tools 0.6.48.12.3.8.  It stops during call 1
before radial/product work and records the source-semantic O full-element
population/LTE workspace plus compact solver input at every DSEC evaluation.
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from .xstar import physical_runner as pr
from .xstar.output_writers import _binary64_fnv1a_hex
from .xstar.radial_transfer import run_bounded_radial_shell


class _StopAfterSelectedEval(RuntimeError):
    pass


def _progress(event: str, details: dict[str, object]) -> None:
    stamp = datetime.now().isoformat(timespec="seconds")
    payload = " ".join(f"{key}={value}" for key, value in sorted(details.items()))
    print(f"[{stamp}] {event}" + (f" {payload}" if payload else ""), flush=True)


def _write(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _write_f64(path: Path, values: Any) -> None:
    arr = np.ascontiguousarray(np.asarray(values, dtype="<f8").reshape(-1))
    path.parent.mkdir(parents=True, exist_ok=True)
    arr.tofile(path)


def _target_element(result: Any, element_z: int) -> Any:
    for item in result.element_results:
        if int(item.request.element_z) == int(element_z):
            return item
    raise RuntimeError(f"fixed-state result has no element Z={element_z}")


def _full_element_vectors(item: Any, derived: Any, element_z: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Rebuild calc_hmc_element's overlapping full-element x/rn/bile workspace."""
    equilibrium = item.equilibrium
    basis = equilibrium.assembly.basis
    solve = equilibrium.solve
    if solve is None:
        raise RuntimeError("target element has no solve result")
    populations = np.asarray(solve.populations, dtype=float).reshape(-1)
    lte_source = getattr(equilibrium.assembly, "lte_populations", None)
    if lte_source is None:
        lte_source = equilibrium.assembly.initial_populations
    lte = np.asarray(lte_source, dtype=float).reshape(-1)
    lte_has_guard = lte.size == populations.size + 1

    ion_stages = np.asarray(getattr(derived, "ion_stage", ()), dtype=int).reshape(-1)
    ion_elements = np.asarray(getattr(derived, "ion_element_z", ()), dtype=int).reshape(-1)
    nlevs = np.asarray(getattr(derived, "nlevs", ()), dtype=int).reshape(-1)
    all_ions = [
        (int(ion_index), int(ion_stages[ion_index]), int(nlevs[ion_index]))
        for ion_index in range(1, min(ion_stages.size, ion_elements.size, nlevs.size))
        if int(ion_elements[ion_index]) == int(element_z)
    ]
    all_ions.sort(key=lambda row: row[1])
    full_nrows = 1 + sum(max(0, nlev - 1) for _, _, nlev in all_ions)
    full_x = np.zeros(full_nrows, dtype=float)
    full_rn = np.zeros(full_nrows, dtype=float)
    block_by_ion = {int(block.ion_index): block for block in basis.blocks}
    ipmat = 0
    for ion_index, _stage, nlev in all_ions:
        block = block_by_ion.get(ion_index)
        if block is not None:
            for local in range(1, nlev + 1):
                compact_index = int(block.compact_index(local))
                zero = compact_index - 1
                full_index = ipmat + local - 1
                full_x[full_index] = float(populations[zero])
                li = compact_index if lte_has_guard else zero
                full_rn[full_index] = float(lte[li]) if 0 <= li < lte.size else 0.0
        # Inactive ions remain exact zero; the following active ion may
        # overwrite the shared boundary at the same full-element position.
        ipmat += nlev - 1
    full_bile = full_x / (full_rn + 1.0e-37)
    return full_x, full_rn, full_bile


def _write_selected_solve(out: Path, idx: int, item: Any) -> None:
    equilibrium = item.equilibrium
    assembly = equilibrium.assembly
    solve = equilibrium.solve
    if solve is None:
        return
    d = out / f"evaluation_{idx:04d}_python_solve"
    d.mkdir(parents=True, exist_ok=True)
    initial = np.asarray(assembly.initial_populations, dtype=float).reshape(-1)
    if initial.size == int(assembly.basis.n_rows) + 1:
        initial = initial[1:]
    _write_f64(d / "solver_input.bin", initial)
    _write_f64(d / "final_population.bin", solve.populations)
    _write_f64(d / "dense_matrix.bin", assembly.dense_matrix)
    term_rows = []
    for order, term in enumerate(assembly.terms, start=1):
        term_rows.append({
            "source_order_index": order,
            "term_index": int(term.term_index),
            "record": int(term.record),
            "data_type": int(term.data_type),
            "rate_type": int(term.rate_type),
            "ion_stage": int(term.ion_stage),
            "role": str(term.role),
            "compact_row": int(term.row),
            "compact_column": int(term.column),
            "aj1": float(term.aj1), "aj2": float(term.aj2),
            "cj": float(term.cj), "cj2": float(term.cj2),
            "idest1": int(term.idest1), "idest2": int(term.idest2),
        })
    _write(d / "matrix_terms.csv", term_rows)
    manifest = {
        "evaluation_index": idx,
        "active_min_stage": int(item.selected_min_ion_stage),
        "active_max_stage": int(item.selected_max_ion_stage),
        "n_rows": int(assembly.basis.n_rows),
        "solver_input_hash": _binary64_fnv1a_hex(initial),
        "final_population_hash": _binary64_fnv1a_hex(solve.populations),
        "dense_matrix_hash": _binary64_fnv1a_hex(assembly.dense_matrix),
        "matrix_term_count": len(term_rows),
    }
    (d / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Capture Python O VII call-1 state transitions")
    ap.add_argument("--run-script", required=True)
    ap.add_argument("--atdb", required=True)
    ap.add_argument("--coheat-data")
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--cache-dir")
    ap.add_argument("--element-z", type=int, default=8)
    ap.add_argument("--stop-eval", type=int, default=24)
    ap.add_argument("--selected-evals", default="1,2,3,4,5,6,9,15,21,24")
    ap.add_argument("--progress", action="store_true")
    ns = ap.parse_args(argv)
    target_z = int(ns.element_z)
    stop_eval = int(ns.stop_eval)
    selected = {int(x) for x in str(ns.selected_evals).split(",") if x.strip()}
    out = Path(ns.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    resolved_atdb = pr._resolve_runner_atdb_path(ns.atdb)
    normalized = pr.normalize_xstar_parameters(pr.parse_run_xstar_script(ns.run_script))
    pointer_cache, metadata_cache = pr._cache_paths(resolved_atdb, ns.cache_dir)
    state, built = pr._build_initial_state(
        normalized,
        atdb_path=resolved_atdb,
        coheat_path=ns.coheat_data,
        pointer_cache=pointer_cache,
        metadata_cache=metadata_cache,
        use_cache=True,
        rebuild_cache=False,
        progress_callback=_progress if ns.progress else None,
    )
    rows: list[dict[str, Any]] = []

    def gate(evaluation_index: int, snapshot: Any, result: Any) -> None:
        idx = int(evaluation_index)
        item = _target_element(result, target_z)
        full_x, full_rn, full_bile = _full_element_vectors(item, built.atomic_state.derived, target_z)
        initial = np.asarray(item.equilibrium.assembly.initial_populations, dtype=float).reshape(-1)
        if initial.size == int(item.equilibrium.assembly.basis.n_rows) + 1:
            initial = initial[1:]
        rows.append({
            "evaluation_index": idx,
            "temperature_k": float(snapshot.temperature_k),
            "electron_fraction_input": float(snapshot.electron_fraction_xee),
            "computed_electron_fraction": float(result.electron_contribution),
            "hmctot": float(result.hmctot),
            "elcter": float(result.elcter),
            "active_min_stage": int(item.selected_min_ion_stage),
            "active_max_stage": int(item.selected_max_ion_stage),
            "solver_input_count": int(initial.size),
            "solver_input_hash": _binary64_fnv1a_hex(initial),
            "o_full_row_count": int(full_x.size),
            "o_full_x_hash": _binary64_fnv1a_hex(full_x),
            "o_full_rnisg_hash": _binary64_fnv1a_hex(full_rn),
            "o_full_bilevg_hash": _binary64_fnv1a_hex(full_bile),
            "o_heating": float(item.heating),
            "o_cooling": float(item.cooling),
            "o_heating2": float(item.heating2),
            "o_cooling2": float(item.cooling2),
        })
        if idx in selected:
            d = out / f"evaluation_{idx:04d}_state"
            _write_f64(d / "o_full_x.bin", full_x)
            _write_f64(d / "o_full_rnisg.bin", full_rn)
            _write_f64(d / "o_full_bilevg.bin", full_bile)
            _write_f64(d / "solver_input.bin", initial)
            _write_selected_solve(out, idx, item)
        if idx >= stop_eval:
            raise _StopAfterSelectedEval()

    state.control["zone1_dsec_capture_all_inputs"] = True
    state.control["zone1_dsec_capture_lucy_trace_element_z"] = target_z
    state.control["zone1_dsec_evaluation_gate_callback"] = gate
    state.control["diagnostics_mode"] = "none"
    state.control["progress_debug"] = bool(ns.progress)
    try:
        try:
            run_bounded_radial_shell(state, zone_index=1, pass_index=1, direction=-1, fixed_state=False)
        except _StopAfterSelectedEval:
            pass
        if len(rows) < stop_eval:
            raise RuntimeError(f"Python diagnostic captured only {len(rows)} evaluations; expected {stop_eval}")
        _write(out / "python_call1_state_transitions.csv", rows)
        manifest = {
            "schema": "xstar-tools-v06481238-o7-dsec-state-transition-v1",
            "element_z": target_z,
            "evaluation_count": len(rows),
            "stop_eval": stop_eval,
            "selected_evals": sorted(selected),
            "transition_csv": "python_call1_state_transitions.csv",
        }
        (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        print("V06481238_PYTHON_O7_STATE_TRANSITIONS=ACCEPT")
        print(f"V06481238_PYTHON_O7_EVALUATIONS={len(rows)}")
        print(f"V06481238_PYTHON_O7_MANIFEST={out / 'manifest.json'}")
        return 0
    finally:
        built.atomic_state.close()


if __name__ == "__main__":
    raise SystemExit(main())
