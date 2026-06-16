"""Audit source compact-basis and transformed-seed restoration for all 61 states."""
from __future__ import annotations

import argparse
import csv
import json
import struct
from pathlib import Path
from typing import Any, Iterable

RELEASE = "0.6.48.7.45"
SCHEMA = "xstar-tools-v0648745-all61-source-compact-basis-seed-restoration-v1"
SUMMARY_NAME = "all61_source_compact_basis_seed_restoration_summary.json"
COMPARISON_NAME = "all61_source_compact_basis_seed_comparison.csv"
INVENTORY_NAME = "all61_post_seed_solve_inventory.csv"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, fields: list[str], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)


def _exact(a: float, b: float) -> bool:
    return struct.pack(">d", float(a)) == struct.pack(">d", float(b))


def _gate(flag: bool, failure: str = "REJECT") -> str:
    return "ACCEPT" if flag else failure


def audit(source_dir: Path, native_dir: Path, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    source_path = source_dir / "v0472_all61_element_solve_rows.csv"
    native_summary_path = native_dir / "native_dsec_summary.json"
    diagnostics = native_dir / "qualification_diagnostics"
    if not diagnostics.is_dir():
        diagnostics = native_dir / "diagnostics"
    missing = []
    if not source_path.is_file(): missing.append(str(source_path))
    if not native_summary_path.is_file(): missing.append(str(native_summary_path))
    if not diagnostics.is_dir(): missing.append(str(diagnostics))
    if missing:
        report = {
            "schema": SCHEMA, "release": RELEASE, "result": "REJECT",
            "errors": [f"missing:{path}" for path in missing],
            "gates": {
                "ALL_61_NATIVE_EVALUATIONS": "NOT_RUN_MISSING_INPUT",
                "ALL_61_SOURCE_COMPACT_BASIS_WINDOWS_EXACT": "NOT_RUN_MISSING_INPUT",
                "ALL_61_SOURCE_TRANSFORMED_SEEDS_EXACT": "NOT_RUN_MISSING_INPUT",
                "V06487_FIXED_STATE_PARITY": "REJECT",
                "V06488_THERMAL_PARITY_READY": "NO_FIXED_STATE_GATE_NOT_ACCEPTED",
                "THERMAL_PARITY": "BLOCKED", "PRODUCTION_PROMOTION": "BLOCKED",
            },
            "qualification_only": True, "production_promotion_ready": False,
            "thermal_parity_started": False,
        }
        (output_dir / SUMMARY_NAME).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        return report

    source_rows = _read_csv(source_path)
    source_by_element: dict[tuple[int, int], list[dict[str, str]]] = {}
    for row in source_rows:
        key = (int(row["sequence"]), int(row["element_z"]))
        source_by_element.setdefault(key, []).append(row)
    for rows in source_by_element.values():
        rows.sort(key=lambda row: int(row["compact_row"]))

    native_summary = json.loads(native_summary_path.read_text())
    native_by_element: dict[tuple[int, int], list[dict[str, str]]] = {}
    missing_native_files: list[int] = []
    for sequence in range(1, 62):
        path = diagnostics / f"evaluation_{sequence:04d}_all_element_solve_rows.csv"
        if not path.is_file():
            missing_native_files.append(sequence)
            continue
        for row in _read_csv(path):
            z = int(row["element_z"])
            if z in (1, 2, 12):
                native_by_element.setdefault((sequence, z), []).append(row)
    for rows in native_by_element.values():
        rows.sort(key=lambda row: int(row["compact_row"]))

    comparison: list[dict[str, Any]] = []
    inventory: list[dict[str, Any]] = []
    windows_exact = 0
    seed_exact = 0
    total_rows = 0
    source_normalization_zero = 0
    native_normalization_zero = 0
    normalization_total = 0
    first_call_zero_exact = 0
    first_call_total = 0
    post_seed_divergent = 0
    exact_elements = 0
    commit_only = 0
    he_call2_exact = False

    for sequence in range(1, 62):
        for z in (1, 2, 12):
            key = (sequence, z)
            source = source_by_element.get(key, [])
            native = native_by_element.get(key, [])
            source_min = int(source[0]["active_min_stage"]) if source else 0
            source_max = int(source[0]["active_max_stage"]) if source else 0
            native_min = int(native[0]["active_min_stage"]) if native else 0
            native_max = int(native[0]["active_max_stage"]) if native else 0
            basis_exact = bool(source and native and len(source) == len(native) and source_min == native_min and source_max == native_max)
            windows_exact += int(basis_exact)
            element_seed_exact = basis_exact
            element_final_exact = basis_exact
            first_final_divergence = 0
            for index in range(max(len(source), len(native))):
                srow = source[index] if index < len(source) else None
                nrow = native[index] if index < len(native) else None
                s_initial = float(srow["transformed_initial_population"]) if srow else float("nan")
                n_initial = float(nrow["initial_population"]) if nrow else float("nan")
                initial_exact = bool(srow and nrow and _exact(s_initial, n_initial))
                element_seed_exact &= initial_exact
                s_final = float(srow["final_population"]) if srow else float("nan")
                n_final = float(nrow["final_population"]) if nrow else float("nan")
                final_exact = bool(srow and nrow and _exact(s_final, n_final))
                element_final_exact &= final_exact
                if not final_exact and first_final_divergence == 0:
                    first_final_divergence = index + 1
                is_norm = bool(srow and int(srow["is_normalization_row"]) == 1)
                if is_norm:
                    normalization_total += 1
                    source_normalization_zero += int(_exact(s_initial, 0.0))
                    native_normalization_zero += int(nrow is not None and _exact(n_initial, 0.0))
                if sequence == 1:
                    first_call_total += 1
                    first_call_zero_exact += int(srow is not None and nrow is not None and _exact(s_initial, 0.0) and _exact(n_initial, 0.0))
                total_rows += 1
                seed_exact += int(initial_exact)
                comparison.append({
                    "sequence": sequence, "element_z": z, "compact_row": index + 1,
                    "source_active_min_stage": source_min, "source_active_max_stage": source_max,
                    "native_active_min_stage": native_min, "native_active_max_stage": native_max,
                    "source_initial": s_initial, "native_initial": n_initial,
                    "initial_exact": int(initial_exact), "source_final": s_final,
                    "native_final": n_final, "final_exact": int(final_exact),
                })
            if element_final_exact:
                classification = "ION_BOUNDARY_EXACT"
                exact_elements += 1
            elif element_seed_exact:
                classification = "POST_SEED_ELEMENT_SOLVE_DIVERGENCE"
                post_seed_divergent += 1
            else:
                classification = "SOURCE_COMPACT_RESTORATION_INCOMPLETE"
            inventory.append({
                "sequence": sequence, "element_z": z, "classification": classification,
                "source_rows": len(source), "native_rows": len(native),
                "source_active_min_stage": source_min, "source_active_max_stage": source_max,
                "native_active_min_stage": native_min, "native_active_max_stage": native_max,
                "seed_exact": int(element_seed_exact), "final_exact": int(element_final_exact),
                "first_final_divergence_row": first_final_divergence,
            })
            if sequence == 22 and z == 2:
                he_call2_exact = element_final_exact

    _write_csv(output_dir / COMPARISON_NAME,
               ["sequence","element_z","compact_row","source_active_min_stage","source_active_max_stage",
                "native_active_min_stage","native_active_max_stage","source_initial","native_initial","initial_exact",
                "source_final","native_final","final_exact"], comparison)
    _write_csv(output_dir / INVENTORY_NAME,
               ["sequence","element_z","classification","source_rows","native_rows","source_active_min_stage",
                "source_active_max_stage","native_active_min_stage","native_active_max_stage","seed_exact","final_exact",
                "first_final_divergence_row"], inventory)

    total_evaluations = int(native_summary.get("total_evaluations", 0))
    callbacks = int(native_summary.get("python_callbacks", -1))
    all61 = total_evaluations == 61 and not missing_native_files and len(native_by_element) == 183
    basis_all = windows_exact == 183
    seed_all = total_rows == len(source_rows) == 40149 and seed_exact == total_rows
    norm_all = normalization_total == 183 and source_normalization_zero == 183 and native_normalization_zero == 183
    first_zero_all = first_call_total > 0 and first_call_zero_exact == first_call_total
    isolated = basis_all and seed_all and post_seed_divergent + exact_elements + commit_only == 183
    h_post = sum(1 for row in inventory if row["element_z"] == 1 and row["classification"] == "POST_SEED_ELEMENT_SOLVE_DIVERGENCE")
    mg_window_removed = all(row["source_active_min_stage"] == row["native_active_min_stage"] and row["source_active_max_stage"] == row["native_active_max_stage"] for row in inventory if row["element_z"] == 12)

    gates = {
        "ALL_61_NATIVE_EVALUATIONS": _gate(all61),
        "PYTHON_CALLBACKS_ZERO": _gate(callbacks == 0),
        "ALL_61_SOURCE_COMPACT_BASIS_WINDOWS_EXACT": _gate(basis_all),
        "ALL_61_SOURCE_TRANSFORMED_SEEDS_EXACT": _gate(seed_all),
        "ALL_61_NORMALIZATION_ROWS_ZERO": _gate(norm_all),
        "ALL_61_EMPTY_FIRST_CALL_SEEDS_ZERO": _gate(first_zero_all),
        "MG_ACTIVE_WINDOW_TRUNCATION_REMOVED": _gate(mg_window_removed),
        "SEED_TRANSFORM_DIVERGENCES_REMOVED": _gate(seed_all),
        "POST_SEED_SOLVE_RESIDUAL_ISOLATED": _gate(isolated),
        "H_POST_SEED_SOLVE_DIVERGENCE_CONFIRMED": _gate(h_post == 61),
        "HE_CALL2_LOCAL_EXACTNESS_CONFIRMED": _gate(he_call2_exact),
        "V06487_SOURCE_COMPACT_BASIS_SEED_RESTORATION": _gate(all61 and callbacks == 0 and basis_all and seed_all and norm_all and first_zero_all and isolated and mg_window_removed and he_call2_exact),
        "V06487_FIXED_STATE_PARITY": "REJECT",
        "V06488_THERMAL_PARITY_READY": "NO_FIXED_STATE_GATE_NOT_ACCEPTED",
        "THERMAL_PARITY": "BLOCKED",
        "CONTROLLER_PARITY": "NOT_RUN_V06489",
        "PRODUCT_PARITY": "BLOCKED",
        "PRODUCTION_PROMOTION": "BLOCKED",
    }
    result_ok = all(value == "ACCEPT" for key, value in gates.items() if key in {
        "ALL_61_NATIVE_EVALUATIONS", "PYTHON_CALLBACKS_ZERO",
        "ALL_61_SOURCE_COMPACT_BASIS_WINDOWS_EXACT", "ALL_61_SOURCE_TRANSFORMED_SEEDS_EXACT",
        "ALL_61_NORMALIZATION_ROWS_ZERO", "ALL_61_EMPTY_FIRST_CALL_SEEDS_ZERO",
        "MG_ACTIVE_WINDOW_TRUNCATION_REMOVED", "SEED_TRANSFORM_DIVERGENCES_REMOVED",
        "POST_SEED_SOLVE_RESIDUAL_ISOLATED", "H_POST_SEED_SOLVE_DIVERGENCE_CONFIRMED",
        "HE_CALL2_LOCAL_EXACTNESS_CONFIRMED", "V06487_SOURCE_COMPACT_BASIS_SEED_RESTORATION"})
    report = {
        "schema": SCHEMA, "release": RELEASE, "result": "ACCEPT" if result_ok else "REJECT",
        "gates": gates, "source_rows": len(source_rows), "native_rows": sum(len(v) for v in native_by_element.values()),
        "element_inventories": len(inventory), "basis_exact_elements": windows_exact,
        "seed_exact_rows": seed_exact, "seed_total_rows": total_rows,
        "normalization_rows": normalization_total, "normalization_source_zero": source_normalization_zero,
        "normalization_native_zero": native_normalization_zero, "first_call_zero_rows": first_call_zero_exact,
        "first_call_total_rows": first_call_total, "post_seed_divergent_elements": post_seed_divergent,
        "exact_elements": exact_elements, "hydrogen_post_seed_divergence_evaluations": h_post,
        "he_call2_local_exact": he_call2_exact, "qualification_only": True,
        "source_compact_basis_seed_oracle": True, "production_promotion_ready": False,
        "thermal_parity_started": False,
    }
    (output_dir / SUMMARY_NAME).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-capture", type=Path, required=True)
    parser.add_argument("--native-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args()
    result = audit(args.source_capture, args.native_run, args.output)
    if args.output_json:
        args.output_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("result") == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
