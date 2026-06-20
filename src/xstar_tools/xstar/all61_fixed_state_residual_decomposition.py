"""Decompose all-61 H/He/Mg fixed-state residuals at element boundaries.

This is a qualification diagnostic.  An ACCEPT result means that every
remaining fixed-state mismatch has been localized to a source/native element
boundary or solve row; it does not mean fixed-state parity has been reached.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import struct
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

RELEASE = "0.6.48.7.46.20.2"
SCHEMA = "xstar-tools-v0648744-all61-fixed-state-residual-decomposition-v1"
SUMMARY_NAME = "all61_fixed_state_residual_decomposition_summary.json"
BOUNDARY_NAME = "all61_element_boundary_decomposition.csv"
CHARGE_NAME = "all61_charge_contribution_decomposition.csv"
FIRST_NAME = "all61_first_divergence_inventory.csv"
SOLVE_NAME = "all61_source_native_solve_row_comparison.csv"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, fields: list[str], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)


def _bits(value: float) -> bytes:
    return struct.pack(">d", float(value))


def _exact(a: float, b: float) -> bool:
    return _bits(a) == _bits(b)


def _finite(value: float) -> bool:
    return math.isfinite(float(value))


def _load_native_solve_rows(native_dir: Path) -> list[dict[str, str]]:
    candidates = [native_dir / "qualification_diagnostics", native_dir / "diagnostics", native_dir / "diag"]
    rows: list[dict[str, str]] = []
    for directory in candidates:
        if not directory.is_dir():
            continue
        for sequence in range(1, 62):
            path = directory / f"evaluation_{sequence:04d}_all_element_solve_rows.csv"
            if path.is_file():
                rows.extend(_read_csv(path))
        if rows:
            return rows
    return rows


def _load_native_ions(native_dir: Path) -> dict[tuple[int, int, int], float]:
    candidates = [native_dir / "qualification_diagnostics", native_dir / "diagnostics", native_dir / "diag"]
    result: dict[tuple[int, int, int], float] = {}
    for directory in candidates:
        if not directory.is_dir():
            continue
        for sequence in range(1, 62):
            path = directory / f"evaluation_{sequence:04d}_ion_balance.csv"
            if not path.is_file():
                continue
            for row in _read_csv(path):
                z = int(row["element_z"])
                if z in (1, 2, 12):
                    result[(sequence, z, int(row["stage"]))] = float(row["final_fraction"])
        if result:
            return result
    return result


def _classify_element(
    sequence: int,
    z: int,
    source_ions: dict[tuple[int, int, int], float],
    native_ions: dict[tuple[int, int, int], float],
    source_rows: list[dict[str, str]],
    native_rows: list[dict[str, str]],
) -> tuple[str, dict[str, Any]]:
    stages = range(1, z + 2)
    ion_exact = all(
        (sequence, z, stage) in native_ions
        and _exact(source_ions.get((sequence, z, stage), float("nan")), native_ions[(sequence, z, stage)])
        for stage in stages
    )
    if ion_exact:
        return "ION_BOUNDARY_EXACT", {}
    if not native_rows:
        return "NATIVE_SOLVE_ROWS_MISSING", {}
    active_min = min(int(r["active_min_stage"]) for r in native_rows)
    active_max = max(int(r["active_max_stage"]) for r in native_rows)
    outside_mass = sum(
        source_ions.get((sequence, z, stage), 0.0)
        for stage in stages
        if stage < active_min or stage > active_max + 1
    )
    if outside_mass != 0.0:
        return "ACTIVE_WINDOW_EXCLUDES_SOURCE_POPULATION", {
            "active_min_stage": active_min, "active_max_stage": active_max,
            "source_population_outside_active_window": outside_mass,
        }
    if not source_rows:
        return "SOURCE_SOLVE_ROWS_MISSING", {
            "active_min_stage": active_min, "active_max_stage": active_max,
        }
    source_map = {int(r["compact_row"]): r for r in source_rows}
    native_map = {int(r["compact_row"]): r for r in native_rows}
    common = sorted(set(source_map) & set(native_map))
    first_seed = None
    first_final = None
    for compact in common:
        s = source_map[compact]; n = native_map[compact]
        if first_seed is None and not _exact(float(s["transformed_initial_population"]), float(n["initial_population"])):
            first_seed = compact
        if first_final is None and not _exact(float(s["final_population"]), float(n["final_population"])):
            first_final = compact
    if len(source_map) != len(native_map):
        return "COMPACT_BASIS_DIMENSION_DIVERGENCE", {
            "source_rows": len(source_map), "native_rows": len(native_map),
            "first_seed_divergence_row": first_seed or 0,
            "first_final_divergence_row": first_final or 0,
        }
    if first_seed is not None:
        return "SEED_TRANSFORM_DIVERGENCE", {
            "first_seed_divergence_row": first_seed,
            "first_final_divergence_row": first_final or 0,
        }
    if first_final is not None:
        return "POST_SEED_ELEMENT_SOLVE_DIVERGENCE", {
            "first_seed_divergence_row": 0,
            "first_final_divergence_row": first_final,
        }
    return "GLOBAL_ELEMENT_COMMIT_DIVERGENCE", {
        "first_seed_divergence_row": 0, "first_final_divergence_row": 0,
    }


def decompose(source_dir: Path, native_dir: Path, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    required = {
        "source_states": source_dir / "v0472_all61_fixed_state_rows.csv",
        "source_ions": source_dir / "v0472_all61_ion_populations.csv",
        "source_solve": source_dir / "v0472_all61_element_solve_rows.csv",
        "native_summary": native_dir / "native_dsec_summary.json",
        "native_states": native_dir / "native_dsec_trajectory.csv",
    }
    missing = [name for name, path in required.items() if not path.is_file()]
    native_rows = _load_native_solve_rows(native_dir)
    native_ions = _load_native_ions(native_dir)
    if not native_rows:
        missing.append("native_solve_rows")
    if not native_ions:
        missing.append("native_ion_rows")
    if missing:
        result = {
            "schema": SCHEMA, "release": RELEASE, "result": "REJECT",
            "errors": [f"missing:{name}" for name in missing],
            "gates": {
                "ALL_61_SOURCE_SOLVE_ROWS_CAPTURED": "REJECT_MISSING_INPUT",
                "ALL_61_NATIVE_SOLVE_ROWS_CAPTURED": "REJECT_MISSING_INPUT",
                "ALL_61_FIRST_DIVERGENCES_IDENTIFIED": "NOT_RUN_MISSING_INPUT",
                "V06487_FIXED_STATE_PARITY": "REJECT",
                "V06488_THERMAL_PARITY_READY": "NO_FIXED_STATE_GATE_NOT_ACCEPTED",
                "THERMAL_PARITY": "BLOCKED", "PRODUCTION_PROMOTION": "BLOCKED",
            },
            "qualification_only": True, "production_promotion_ready": False,
        }
        (output_dir / SUMMARY_NAME).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        return result

    source_states = _read_csv(required["source_states"])
    source_ion_rows = _read_csv(required["source_ions"])
    source_rows = _read_csv(required["source_solve"])
    native_summary = json.loads(required["native_summary"].read_text())
    native_states = {int(r["sequence"]): r for r in _read_csv(required["native_states"])}
    source_ions = {(int(r["sequence"]), int(r["element_z"]), int(r["stage"])): float(r["population"]) for r in source_ion_rows}
    source_by_element: dict[tuple[int, int], list[dict[str, str]]] = defaultdict(list)
    native_by_element: dict[tuple[int, int], list[dict[str, str]]] = defaultdict(list)
    for row in source_rows:
        source_by_element[(int(row["sequence"]), int(row["element_z"]))].append(row)
    for row in native_rows:
        sequence = int(row.get("evaluation_ordinal", row.get("sequence", 0)))
        native_by_element[(sequence, int(row["element_z"]))].append(row)

    solve_rows: list[dict[str, Any]] = []
    solve_exact = {"initial": 0, "outer": 0, "final": 0, "rhs": 0}
    solve_total = 0
    for key in sorted(set(source_by_element) | set(native_by_element)):
        src = {int(r["compact_row"]): r for r in source_by_element.get(key, [])}
        nat = {int(r["compact_row"]): r for r in native_by_element.get(key, [])}
        for compact in sorted(set(src) | set(nat)):
            s = src.get(compact); n = nat.get(compact)
            values: dict[str, tuple[float, float, bool]] = {}
            for label, sf, nf in (
                ("initial", "transformed_initial_population", "initial_population"),
                ("outer", "final_outer_start_population", "final_outer_start_population"),
                ("final", "final_population", "final_population"),
                ("rhs", "rhs", "rhs"),
            ):
                sv = float("nan") if s is None else float(s[sf])
                nv = float("nan") if n is None else float(n[nf])
                exact = s is not None and n is not None and _exact(sv, nv)
                values[label] = (sv, nv, exact)
                solve_exact[label] += int(exact)
            solve_total += 1
            solve_rows.append({
                "sequence": key[0], "element_z": key[1], "compact_row": compact,
                "ion_stage": (s or n or {}).get("ion_stage", ""),
                "superlevel": (s or n or {}).get("superlevel", ""),
                "is_normalization_row": (s or n or {}).get("is_normalization_row", ""),
                "source_initial": values["initial"][0], "native_initial": values["initial"][1], "initial_exact": int(values["initial"][2]),
                "source_outer": values["outer"][0], "native_outer": values["outer"][1], "outer_exact": int(values["outer"][2]),
                "source_final": values["final"][0], "native_final": values["final"][1], "final_exact": int(values["final"][2]),
                "source_rhs": values["rhs"][0], "native_rhs": values["rhs"][1], "rhs_exact": int(values["rhs"][2]),
            })
    _write_csv(output_dir / SOLVE_NAME,
               ["sequence","element_z","compact_row","ion_stage","superlevel","is_normalization_row",
                "source_initial","native_initial","initial_exact","source_outer","native_outer","outer_exact",
                "source_final","native_final","final_exact","source_rhs","native_rhs","rhs_exact"], solve_rows)

    abundances = {1: 1.0, 2: 0.1, 12: 3.5e-5}
    charge_rows: list[dict[str, Any]] = []
    charge_attributed = 0
    state_map = {int(r["sequence"]): r for r in source_states}
    for sequence in range(1, 62):
        source_total = 0.0; native_total = 0.0
        per: list[tuple[int, float, float]] = []
        for z in (1, 2, 12):
            sc = abundances[z] * sum((stage - 1) * source_ions.get((sequence, z, stage), 0.0) for stage in range(1, z + 2))
            nc = abundances[z] * sum((stage - 1) * native_ions.get((sequence, z, stage), 0.0) for stage in range(1, z + 2))
            source_total += sc; native_total += nc; per.append((z, sc, nc))
        expected_delta = native_total - source_total
        source_state = state_map.get(sequence, {})
        native_state = native_states.get(sequence, {})
        source_xee = float(source_state.get("computed_electron_fraction", "nan"))
        source_residual = float(source_state.get("charge_residual", "nan"))
        input_xee = float(source_state.get("electron_fraction_input", "nan"))
        direct_source_exact = _finite(source_xee) and _exact(source_total, source_xee)
        residual_identity_exact = _finite(source_residual) and _exact(input_xee - source_residual, source_xee)
        native_xee = float(native_state.get("computed_electron_fraction", "nan"))
        observed_delta = native_xee - source_xee
        attribution_exact = _finite(observed_delta) and math.isclose(expected_delta, observed_delta, rel_tol=0.0, abs_tol=2.0e-15)
        charge_attributed += int(attribution_exact)
        for z, sc, nc in per:
            charge_rows.append({
                "sequence": sequence, "element_z": z, "abundance": abundances[z],
                "source_charge_contribution": sc, "native_charge_contribution": nc,
                "signed_contribution_delta": nc - sc,
                "source_total_charge": source_total, "native_total_charge": native_total,
                "total_charge_delta": expected_delta, "observed_electron_fraction_delta": observed_delta,
                "element_delta_sum_matches_observed": int(attribution_exact),
                "source_charge_matches_computed_xee": int(direct_source_exact),
                "source_residual_identity_exact": int(residual_identity_exact),
            })
    _write_csv(output_dir / CHARGE_NAME,
               ["sequence","element_z","abundance","source_charge_contribution","native_charge_contribution",
                "signed_contribution_delta","source_total_charge","native_total_charge","total_charge_delta",
                "observed_electron_fraction_delta","element_delta_sum_matches_observed",
                "source_charge_matches_computed_xee","source_residual_identity_exact"], charge_rows)

    boundary_rows: list[dict[str, Any]] = []
    first_rows: list[dict[str, Any]] = []
    classes: dict[str, int] = defaultdict(int)
    mg_window_count = 0; h_post_seed_count = 0; he_call2_local_exact = False
    for sequence in range(1, 62):
        for z in (1, 2, 12):
            classification, details = _classify_element(
                sequence, z, source_ions, native_ions,
                source_by_element.get((sequence, z), []), native_by_element.get((sequence, z), []),
            )
            classes[classification] += 1
            if z == 12 and classification == "ACTIVE_WINDOW_EXCLUDES_SOURCE_POPULATION":
                mg_window_count += 1
            if z == 1 and classification == "POST_SEED_ELEMENT_SOLVE_DIVERGENCE":
                h_post_seed_count += 1
            if sequence == 22 and z == 2:
                rows22 = [r for r in solve_rows if int(r["sequence"]) == 22 and int(r["element_z"]) == 2]
                he_call2_local_exact = bool(rows22) and all(int(r["initial_exact"]) and int(r["final_exact"]) and int(r["rhs_exact"]) for r in rows22)
            row = {
                "sequence": sequence, "element_z": z, "classification": classification,
                "source_solve_rows": len(source_by_element.get((sequence, z), [])),
                "native_solve_rows": len(native_by_element.get((sequence, z), [])),
                **details,
            }
            boundary_rows.append(row)
            first_rows.append({
                "sequence": sequence, "element_z": z, "first_divergence": classification,
                "first_seed_divergence_row": details.get("first_seed_divergence_row", 0),
                "first_final_divergence_row": details.get("first_final_divergence_row", 0),
                "source_population_outside_active_window": details.get("source_population_outside_active_window", 0.0),
            })
    _write_csv(output_dir / BOUNDARY_NAME,
               ["sequence","element_z","classification","source_solve_rows","native_solve_rows",
                "active_min_stage","active_max_stage","source_population_outside_active_window",
                "source_rows","native_rows","first_seed_divergence_row","first_final_divergence_row"], boundary_rows)
    _write_csv(output_dir / FIRST_NAME,
               ["sequence","element_z","first_divergence","first_seed_divergence_row","first_final_divergence_row",
                "source_population_outside_active_window"], first_rows)

    source_inventory = len(source_by_element) == 61 * 3
    native_inventory = len(native_by_element) == 61 * 3
    all61_native = int(native_summary.get("total_evaluations", 0)) == 61
    callbacks_zero = int(native_summary.get("python_callbacks", -1)) == 0
    first_identified = len(first_rows) == 61 * 3 and all(r["first_divergence"] not in {"SOURCE_SOLVE_ROWS_MISSING", "NATIVE_SOLVE_ROWS_MISSING"} for r in first_rows)
    charge_ok = charge_attributed == 61
    decomposition_complete = source_inventory and native_inventory and all61_native and callbacks_zero and first_identified and charge_ok
    gates = {
        "ALL_61_NATIVE_EVALUATIONS": "ACCEPT" if all61_native else "REJECT",
        "PYTHON_CALLBACKS_ZERO": "ACCEPT" if callbacks_zero else "REJECT",
        "ALL_61_SOURCE_SOLVE_ROWS_CAPTURED": "ACCEPT" if source_inventory else "REJECT",
        "ALL_61_NATIVE_SOLVE_ROWS_CAPTURED": "ACCEPT" if native_inventory else "REJECT",
        "ALL_61_FIRST_DIVERGENCES_IDENTIFIED": "ACCEPT" if first_identified else "REJECT",
        "ALL_61_CHARGE_RESIDUAL_ATTRIBUTED_BY_ELEMENT": "ACCEPT" if charge_ok else "REJECT",
        "MG_ACTIVE_WINDOW_TRUNCATION_IDENTIFIED": "ACCEPT" if mg_window_count > 0 else "NOT_OBSERVED",
        "H_POST_SEED_SOLVE_DIVERGENCE_IDENTIFIED": "ACCEPT" if h_post_seed_count > 0 else "NOT_OBSERVED",
        "HE_CALL2_LOCAL_EXACTNESS_CONFIRMED": "ACCEPT" if he_call2_local_exact else "REJECT",
        "V06487_FIXED_STATE_RESIDUAL_DECOMPOSITION": "ACCEPT" if decomposition_complete else "REJECT",
        "V06487_FIXED_STATE_PARITY": "REJECT",
        "V06488_THERMAL_PARITY_READY": "NO_FIXED_STATE_GATE_NOT_ACCEPTED",
        "THERMAL_PARITY": "BLOCKED",
        "CONTROLLER_PARITY": "NOT_RUN_V06489",
        "PRODUCT_PARITY": "BLOCKED",
        "PRODUCTION_PROMOTION": "BLOCKED",
    }
    result = {
        "schema": SCHEMA, "release": RELEASE,
        "result": "ACCEPT" if decomposition_complete else "REJECT",
        "gates": gates, "source_solve_rows": len(source_rows), "native_solve_rows": len(native_rows),
        "source_element_solve_inventories": len(source_by_element), "native_element_solve_inventories": len(native_by_element),
        "solve_row_comparison_total": solve_total, "solve_row_exact_counts": solve_exact,
        "classification_counts": dict(sorted(classes.items())),
        "mg_active_window_truncation_evaluations": mg_window_count,
        "hydrogen_post_seed_divergence_evaluations": h_post_seed_count,
        "he_call2_local_exact": he_call2_local_exact,
        "qualification_only": True, "production_promotion_ready": False,
        "thermal_parity_started": False,
    }
    (output_dir / SUMMARY_NAME).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-capture", type=Path, required=True)
    parser.add_argument("--native-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args(argv)
    try:
        result = decompose(args.source_capture, args.native_run, args.output)
    except Exception as exc:
        result = {
            "schema": SCHEMA, "release": RELEASE, "result": "REJECT", "errors": [str(exc)],
            "gates": {"V06487_FIXED_STATE_RESIDUAL_DECOMPOSITION": "REJECT",
                      "V06487_FIXED_STATE_PARITY": "REJECT",
                      "V06488_THERMAL_PARITY_READY": "NO_FIXED_STATE_GATE_NOT_ACCEPTED",
                      "THERMAL_PARITY": "BLOCKED", "PRODUCTION_PROMOTION": "BLOCKED"},
            "qualification_only": True, "production_promotion_ready": False,
        }
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / SUMMARY_NAME).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    if args.output_json:
        args.output_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("result") == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
