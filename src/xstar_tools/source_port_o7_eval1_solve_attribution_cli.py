"""Capture pure-Python O VII eval-1 detailed-population/Lucy solve state.

Diagnostic-only helper for xstar_tools 0.6.48.12.3.6.  It executes only the
first call-1 DSEC fixed-state evaluation, requests the translated Python Lucy
trace for oxygen, serializes the exact compact solve input/matrix/source-term
stream and every outer/fixed iteration, then terminates before evaluation 2.
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
from .xstar.radial_transfer import run_bounded_radial_shell


class _StopAfterEval1(RuntimeError):
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


def _write_f64(path: Path, values: Any) -> int:
    arr = np.asarray(values, dtype=np.float64)
    path.parent.mkdir(parents=True, exist_ok=True)
    arr.tofile(path)
    return int(arr.size)


def _target_element(result: Any, element_z: int) -> Any:
    for item in result.element_results:
        if int(item.request.element_z) == int(element_z):
            return item
    raise RuntimeError(f"fixed-state result has no element Z={element_z}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Capture pure-Python O eval-1 Lucy solve attribution")
    ap.add_argument("--run-script", required=True)
    ap.add_argument("--atdb", required=True)
    ap.add_argument("--coheat-data")
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--cache-dir")
    ap.add_argument("--element-z", type=int, default=8)
    ap.add_argument("--progress", action="store_true")
    ns = ap.parse_args(argv)

    target_z = int(ns.element_z)
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

    captured: dict[str, Any] = {}

    def gate(evaluation_index: int, snapshot: Any, result: Any) -> None:
        if int(evaluation_index) != 1:
            raise RuntimeError("0.6.48.12.3.6 eval-1 diagnostic unexpectedly reached evaluation >1")
        item = _target_element(result, target_z)
        equilibrium = item.equilibrium
        assembly = equilibrium.assembly
        solve = equilibrium.solve
        if solve is None or solve.trace is None:
            raise RuntimeError("oxygen eval-1 solve did not return a Lucy iteration trace")
        basis = assembly.basis
        trace = solve.trace
        n = int(basis.n_rows)
        nsp = int(basis.n_superlevels)

        basis_rows: list[dict[str, Any]] = []
        physical_stage = basis.ion_stage
        initial = np.asarray(assembly.initial_populations[1:n+1], dtype=float)
        lte = np.asarray(assembly.lte_populations[1:n+1], dtype=float) if assembly.lte_populations is not None else np.zeros(n)
        final = np.asarray(solve.populations, dtype=float)
        outer = np.asarray(solve.final_outer_start_populations, dtype=float)
        for row in basis.rows:
            idx = int(row.compact_index) - 1
            basis_rows.append({
                "compact_row": int(row.compact_index),
                "superlevel": int(row.superlevel),
                "ion_counter": int(row.ion_counter),
                "ion_stage": int(physical_stage[int(row.compact_index)]),
                "ion_charge": int(physical_stage[int(row.compact_index)]) - 1,
                "is_normalization_row": int(int(row.compact_index) == int(basis.normalization_row)),
                "roles_json": json.dumps(row.roles, sort_keys=True, separators=(",", ":")),
                "initial_population": float(initial[idx]),
                "lte_population": float(lte[idx]),
                "final_outer_start_population": float(outer[idx]),
                "final_population": float(final[idx]),
            })

        term_rows: list[dict[str, Any]] = []
        for source_order_index, term in enumerate(assembly.terms, start=1):
            term_rows.append({
                "source_order_index": source_order_index,
                "term_index": int(term.term_index),
                "record": int(term.record),
                "data_type": int(term.data_type),
                "rate_type": int(term.rate_type),
                "ion_stage": int(term.ion_stage),
                "role": str(term.role),
                "compact_row": int(term.row),
                "compact_column": int(term.column),
                "aj1": float(term.aj1),
                "aj2": float(term.aj2),
                "cj": float(term.cj),
                "cj2": float(term.cj2),
                "idest1": int(term.idest1),
                "idest2": int(term.idest2),
                "lower_endpoint": int(term.lower_endpoint),
                "upper_endpoint": int(term.upper_endpoint),
                "ucalc_status": str(term.ucalc_status),
                "source_row_unclamped": int(term.source_row_unclamped),
                "source_column_unclamped": int(term.source_column_unclamped),
                "source_ipmat_clamped": int(bool(term.source_ipmat_clamped)),
            })

        ion_rows: list[dict[str, Any]] = []
        for counter in range(1, int(basis.n_ions) + 1):
            stage = int(basis.ion_stage_by_counter.get(counter, basis.min_ion_stage + counter - 1))
            ion_rows.append({
                "ion_counter": counter,
                "ion_stage": stage,
                "ion_charge": stage - 1,
                "final_fraction_from_element": float(item.ion_fractions.get(stage, item.fully_stripped_fraction if stage == target_z + 1 else 0.0)),
                "solve_ion_population_total_outer_start": float(solve.ion_population_totals[counter - 1]) if counter - 1 < len(solve.ion_population_totals) else 0.0,
                "solve_ion_population_total_final": float(solve.ion_population_totals_final_vector[counter - 1]) if counter - 1 < len(solve.ion_population_totals_final_vector) else 0.0,
                "ionization_total": float(solve.ionization_totals[counter - 1]) if counter - 1 < len(solve.ionization_totals) else 0.0,
                "recombination_total": float(solve.recombination_totals[counter - 1]) if counter - 1 < len(solve.recombination_totals) else 0.0,
            })

        _write(out / "python_eval1_basis_rows.csv", basis_rows)
        _write(out / "python_eval1_matrix_terms.csv", term_rows)
        _write(out / "python_eval1_outer_rows.csv", list(trace.outer_level_rows))
        _write(out / "python_eval1_superlevels.csv", list(trace.superlevel_rows))
        _write(out / "python_eval1_condensed_matrix.csv", list(trace.condensed_matrix_rows))
        _write(out / "python_eval1_fixed_rows.csv", list(trace.fixed_point_rows))
        _write(out / "python_eval1_ion_reconstruction.csv", ion_rows)

        files = {
            "dense_matrix": ("python_eval1_dense_matrix.bin", _write_f64(out / "python_eval1_dense_matrix.bin", assembly.dense_matrix)),
            "heating_matrix": ("python_eval1_heating_matrix.bin", _write_f64(out / "python_eval1_heating_matrix.bin", assembly.heating_matrix)),
            "heating_matrix2": ("python_eval1_heating_matrix2.bin", _write_f64(out / "python_eval1_heating_matrix2.bin", assembly.heating_matrix2)),
            "rhs": ("python_eval1_rhs.bin", _write_f64(out / "python_eval1_rhs.bin", assembly.rhs)),
            "solver_input": ("python_eval1_solver_input.bin", _write_f64(out / "python_eval1_solver_input.bin", initial)),
            "final_outer_start": ("python_eval1_final_outer_start.bin", _write_f64(out / "python_eval1_final_outer_start.bin", outer)),
            "final": ("python_eval1_final.bin", _write_f64(out / "python_eval1_final.bin", final)),
        }
        manifest = {
            "schema": "xstar-tools-v06481236-python-o7-eval1-solve-attribution-v1",
            "element_z": target_z,
            "evaluation_index": 1,
            "temperature_k": float(snapshot.temperature_k),
            "electron_fraction_input": float(snapshot.electron_fraction_xee),
            "active_min_stage": int(item.selected_min_ion_stage),
            "active_max_stage": int(item.selected_max_ion_stage),
            "n_rows": n,
            "n_superlevels": nsp,
            "n_ions": int(basis.n_ions),
            "normalization_row": int(basis.normalization_row),
            "outer_iterations": int(solve.outer_iterations),
            "total_fixed_point_iterations": int(solve.fixed_point_iterations),
            "final_outer_difference": float(solve.final_outer_difference),
            "final_fixed_point_difference": float(solve.final_fixed_point_difference),
            "solver_method": str(solve.solver_method),
            "normalization": float(solve.normalization),
            "normalization_error": float(solve.normalization_error),
            "files": {k: {"path": v[0], "count": v[1]} for k, v in files.items()},
            "csv": {
                "basis_rows": "python_eval1_basis_rows.csv",
                "matrix_terms": "python_eval1_matrix_terms.csv",
                "outer_rows": "python_eval1_outer_rows.csv",
                "superlevels": "python_eval1_superlevels.csv",
                "condensed_matrix": "python_eval1_condensed_matrix.csv",
                "fixed_rows": "python_eval1_fixed_rows.csv",
                "ion_reconstruction": "python_eval1_ion_reconstruction.csv",
            },
        }
        (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        captured.update(manifest)
        raise _StopAfterEval1()

    state.control["zone1_dsec_capture_all_inputs"] = True
    state.control["zone1_dsec_capture_lucy_trace_element_z"] = target_z
    state.control["zone1_dsec_evaluation_gate_callback"] = gate
    state.control["diagnostics_mode"] = "none"
    state.control["progress_debug"] = bool(ns.progress)

    try:
        try:
            run_bounded_radial_shell(state, zone_index=1, pass_index=1, direction=-1, fixed_state=False)
        except _StopAfterEval1:
            pass
        if not captured:
            raise RuntimeError("eval-1 solve attribution did not capture oxygen")
        print("V06481236_PYTHON_O7_EVAL1_SOLVE_ATTRIBUTION=ACCEPT")
        print(f"V06481236_PYTHON_O7_EVAL1_N_ROWS={captured['n_rows']}")
        print(f"V06481236_PYTHON_O7_EVAL1_N_SUPERLEVELS={captured['n_superlevels']}")
        print(f"V06481236_PYTHON_O7_EVAL1_OUTER_ITERATIONS={captured['outer_iterations']}")
        print(f"V06481236_PYTHON_O7_EVAL1_FIXED_ITERATIONS={captured['total_fixed_point_iterations']}")
        print(f"V06481236_PYTHON_O7_EVAL1_MANIFEST={out / 'manifest.json'}")
        return 0
    finally:
        built.atomic_state.close()


if __name__ == "__main__":
    raise SystemExit(main())
