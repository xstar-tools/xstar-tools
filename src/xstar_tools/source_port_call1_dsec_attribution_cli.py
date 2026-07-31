"""Capture a compact pure-Python call-1 DSEC attribution trajectory.

Diagnostic-only helper for v0.6.48.12.3.5/12.3.5.1/12.3.5.2.  It runs one source-faithful
radial shell and serializes every DSEC trial before any later radial call.
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .xstar import physical_runner as pr
from .xstar.fixed_state_attribution import python_element_attribution_rows
from .xstar.radial_transfer import run_bounded_radial_shell


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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Capture pure-Python call-1 DSEC attribution trajectory")
    ap.add_argument("--run-script", required=True)
    ap.add_argument("--atdb", required=True)
    ap.add_argument("--coheat-data")
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--cache-dir")
    ap.add_argument("--element-z", type=int, default=8)
    ap.add_argument("--progress", action="store_true")
    ns = ap.parse_args(argv)

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

    evaluation_rows: list[dict[str, Any]] = []
    element_rows: list[dict[str, Any]] = []
    stage_rows: list[dict[str, Any]] = []
    preliminary_rows: list[dict[str, Any]] = []
    family_rows: list[dict[str, Any]] = []
    record_rows: list[dict[str, Any]] = []
    compact_rows: list[dict[str, Any]] = []
    target_z = int(ns.element_z)

    def gate(evaluation_index: int, snapshot: Any, result: Any) -> None:
        idx = int(evaluation_index)
        evaluation_rows.append({
            "evaluation_index": idx,
            "temperature_k": float(snapshot.temperature_k),
            "temperature_t4": float(snapshot.temperature_t4),
            "electron_fraction_input": float(snapshot.electron_fraction_xee),
            "computed_electron_fraction": float(result.electron_contribution),
            "hmctot": float(result.hmctot),
            "elcter": float(result.elcter),
            "total_heating": float(result.httot),
            "total_cooling": float(result.cltot),
            "total_heating2": float(result.httot2),
            "total_cooling2": float(result.cltot2),
        })
        for item in result.element_results:
            z = int(item.request.element_z)
            element_rows.append({
                "evaluation_index": idx,
                "element_z": z,
                "temperature_k": float(snapshot.temperature_k),
                "electron_fraction_input": float(snapshot.electron_fraction_xee),
                "active_min_stage": int(item.selected_min_ion_stage),
                "active_max_stage": int(item.selected_max_ion_stage),
                "heating": float(item.heating),
                "cooling": float(item.cooling),
                "heating2": float(item.heating2),
                "cooling2": float(item.cooling2),
                "electron_contribution": float(item.electron_contribution),
            })
            if z != target_z:
                continue
            for stage in range(1, target_z + 2):
                final_fraction = float(item.fully_stripped_fraction) if stage == target_z + 1 else float(item.ion_fractions.get(stage, 0.0))
                preliminary_fraction = float(item.preliminary_ion_fractions.get(stage, 0.0))
                stage_rows.append({
                    "evaluation_index": idx,
                    "element_z": target_z,
                    "active_min_stage": int(item.selected_min_ion_stage),
                    "active_max_stage": int(item.selected_max_ion_stage),
                    "stage": stage,
                    "ion_charge": stage - 1,
                    "preliminary_fraction": preliminary_fraction,
                    "final_fraction": final_fraction,
                })
                preliminary_rows.append({
                    "evaluation_index": idx,
                    "element_z": target_z,
                    "stage": stage,
                    "ion_charge": stage - 1,
                    "preliminary_ionization": float(item.preliminary_pirt.get(stage, 0.0)),
                    "preliminary_recombination": float(item.preliminary_rrrt.get(stage, 0.0)),
                    "preliminary_fraction": preliminary_fraction,
                })

        attribution = python_element_attribution_rows(result, element_z=target_z)
        for row in attribution["thermal_by_data_type"]:
            family_rows.append({"evaluation_index": idx, **row})
        for row in attribution["thermal_records"]:
            # Source semantic identity is stage-based.  Keep the implementation
            # specific ion_index as a diagnostic column but never key on it.
            record_rows.append({"evaluation_index": idx, **row})
        for row in attribution["compact_populations"]:
            compact_rows.append({"evaluation_index": idx, **row})

    state.control["zone1_dsec_capture_all_inputs"] = True
    state.control["zone1_dsec_evaluation_gate_callback"] = gate
    # The callback serializes everything needed here.  Avoid retaining dozens
    # of complete FixedStateCalcHMCAllResult objects in the DSEC evaluator.
    state.control["diagnostics_mode"] = "none"
    state.control["progress_debug"] = bool(ns.progress)

    try:
        run_bounded_radial_shell(state, zone_index=1, pass_index=1, direction=-1, fixed_state=False)
        out = Path(ns.output_dir)
        out.mkdir(parents=True, exist_ok=True)
        _write(out / "python_call1_evaluations.csv", evaluation_rows)
        _write(out / "python_call1_element_thermal.csv", element_rows)
        _write(out / f"python_z{target_z}_stage_fractions.csv", stage_rows)
        _write(out / f"python_z{target_z}_preliminary_rates.csv", preliminary_rows)
        _write(out / f"python_z{target_z}_thermal_by_family.csv", family_rows)
        _write(out / f"python_z{target_z}_thermal_records.csv", record_rows)
        _write(out / f"python_z{target_z}_compact_populations.csv", compact_rows)
        controller_rows = list(state.control.get("dsec_residual_trajectory_summary", []))
        _write(out / "python_call1_controller_events.csv", controller_rows)
        terminals = list(state.control.get("dsec_terminal_summary", []))
        terminal = terminals[0] if terminals else {}
        manifest = {
            "schema": "xstar-tools-v06481235-python-call1-dsec-attribution-v1",
            "element_z": target_z,
            "evaluation_count": len(evaluation_rows),
            "terminal": terminal,
            "files": {
                "evaluations": "python_call1_evaluations.csv",
                "elements": "python_call1_element_thermal.csv",
                "stage_fractions": f"python_z{target_z}_stage_fractions.csv",
                "preliminary_rates": f"python_z{target_z}_preliminary_rates.csv",
                "thermal_by_family": f"python_z{target_z}_thermal_by_family.csv",
                "thermal_records": f"python_z{target_z}_thermal_records.csv",
                "compact_populations": f"python_z{target_z}_compact_populations.csv",
                "controller_events": "python_call1_controller_events.csv",
            },
        }
        (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print("V06481235_PYTHON_CALL1_DSEC_ATTRIBUTION=ACCEPT")
        print(f"V06481235_PYTHON_CALL1_DSEC_EVALUATIONS={len(evaluation_rows)}")
        print(f"V06481235_PYTHON_CALL1_DSEC_TERMINAL_NTOTIT={terminal.get('ntotit', '')}")
        print(f"V06481235_PYTHON_CALL1_DSEC_MANIFEST={out / 'manifest.json'}")
        return 0
    finally:
        built.atomic_state.close()


if __name__ == "__main__":
    raise SystemExit(main())
