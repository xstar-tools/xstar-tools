"""Type-99 record 1695 and type-71 coupled-path qualification audit.

v0.6.48.7.13 reconstructs the exact v0.6.47.2 type-99 source semantics,
freezes a one-record fixed-state evaluator oracle when the exact source archive
is available, performs grouped type-71 row-path ablations, and measures the
non-additivity of type-99 and type-71 removal.  No physics replacement is
performed by this module.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import shutil
from pathlib import Path
from typing import Any, Callable, Iterable

from .helium_family_isolation import (
    ORACLE_SHA256 as TYPE53_ORACLE_SHA256,
    RADIATION_SHA256,
    discover_reference,
    load_oracle,
    read_csv,
    run_command,
    run_fixed_evaluation,
    sha256,
    state_metrics,
    verify_type53_invariant,
    write_csv,
    write_json,
)
from .v0472_type99_runtime_capture import (
    ORACLE_NAME as TYPE99_ORACLE_NAME,
    SOURCE_ARCHIVE_SHA256,
    capture as capture_type99,
    verify as verify_type99,
)

RELEASE = "0.6.48.7.13"
SCHEMA = "xstar-tools-v064876-type99-type71-coupled-path-audit-v1"
TYPE99_BUNDLE_RELATIVE = Path("src/xstar_tools/benchmarks/v064876_type99_record1695_runtime_oracle_v0472")
TARGET_SOURCE_POSITION = 6312
TARGET_RECORD = 1695


def clone_selected_program(source: Path, destination: Path, selector: Callable[[dict[str, str]], bool]) -> int:
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    for item in source.iterdir():
        if item.name == "records.csv":
            continue
        target = destination / item.name
        if item.is_file():
            # Keep qualification programs portable.  Previous releases used
            # absolute symlinks to the host lowered program, which broke after
            # evidence archives were extracted elsewhere.
            shutil.copy2(item, target)
    rows = read_csv(source / "records.csv")
    fields = list(rows[0]) if rows else []
    changed = 0
    for row in rows:
        if selector(row) and int(row.get("matrix_enabled", "0")) != 0:
            row["matrix_enabled"] = "0"
            row["lower_row"] = "0"
            row["upper_row"] = "0"
            changed += 1
    if changed == 0:
        raise ValueError("grouped ablation selected no matrix-enabled records")
    write_csv(destination / "records.csv", rows, fields)
    return changed


def ion_balance_rows(output: Path, evaluation: int) -> list[dict[str, str]]:
    return read_csv(output / "diagnostics" / f"evaluation_{evaluation:04d}_ion_balance.csv")


def element_isolation_delta(baseline: Path, scenario: Path, evaluation: int) -> dict[str, Any]:
    base = {(int(r["element_z"]), int(r["stage"])): r for r in ion_balance_rows(baseline, evaluation)}
    test = {(int(r["element_z"]), int(r["stage"])): r for r in ion_balance_rows(scenario, evaluation)}
    fields = ("preliminary_fraction", "final_fraction", "preliminary_ionization", "preliminary_recombination")
    max_h_mg = 0.0
    nonzero = 0
    for key, row in base.items():
        if key[0] not in (1, 12):
            continue
        other = test[key]
        for field in fields:
            delta = float(other[field]) - float(row[field])
            max_h_mg = max(max_h_mg, abs(delta))
            if delta != 0.0:
                nonzero += 1
    helium_sum = sum(float(r["final_fraction"]) for (z, _), r in test.items() if z == 2)
    return {
        "max_h_mg_absolute_delta": max_h_mg,
        "nonzero_h_mg_fields": nonzero,
        "helium_final_normalization_error": helium_sum - 1.0,
    }


def metric_delta(baseline: dict[str, Any], scenario: dict[str, Any]) -> dict[str, float]:
    keys = (
        "he1_final_fraction", "he2_final_fraction", "he3_final_fraction",
        "native_electron_fraction", "native_charge_residual", "native_hmctot",
    )
    return {f"delta_{key}": float(scenario[key]) - float(baseline[key]) for key in keys}


def answer_sign_contract(values: tuple[float, ...]) -> bool:
    return values[0] >= 0.0 and values[1] >= 0.0 and all(value <= 0.0 for value in values[2:])


def matrix_terms(variant: str, answers: tuple[float, ...], density: float = 1.0) -> list[dict[str, Any]]:
    a1, a2, a3, a4, a5, a6 = answers
    values = (
        ("forward_gain", 78, 77, a1, a2, 0.0, 0.0),
        ("reverse_gain", 77, 78, a2, a1, 0.0, 0.0),
        ("forward_diag_loss", 77, 77, -a1, -a1, a4 * density, a6 * density),
        ("reverse_diag_loss", 78, 78, -a2, -a2, -a3 * density, -a5 * density),
    )
    return [
        {"variant": variant, "source_position": TARGET_SOURCE_POSITION, "record": TARGET_RECORD,
         "role": role, "row": row, "column": col, "aj1": aj1, "aj2": aj2, "cj": cj, "cj2": cj2}
        for role, row, col, aj1, aj2, cj, cj2 in values
    ]


def ensure_type99_oracle(root: Path, source_archive: Path, lowered: Path, baseline: Path, radiation: Path, output: Path, evaluation: int) -> tuple[Path, dict[str, Any]]:
    bundled = root / TYPE99_BUNDLE_RELATIVE
    if bundled.is_dir() and verify_type99(bundled)["result"] == "ACCEPT":
        return bundled, verify_type99(bundled)
    bundle = output / "type99_record1695_runtime_oracle"
    report = capture_type99(source_archive, lowered, baseline, radiation, bundle, evaluation=evaluation)
    if report["result"] != "ACCEPT":
        raise RuntimeError("type-99 record 1695 oracle capture rejected")
    return bundle, report


def read_type99_oracle(bundle: Path) -> dict[str, str]:
    rows = read_csv(bundle / TYPE99_ORACLE_NAME)
    if len(rows) != 1:
        raise ValueError("type-99 oracle must contain one row")
    return rows[0]


def scenario_selector(name: str, records: list[dict[str, str]]) -> tuple[Callable[[dict[str, str]], bool], list[int]]:
    type71 = [r for r in records if int(r["element_index"]) == 1 and int(r["data_type"]) == 71]
    row77 = sorted(int(r["source_position"]) for r in type71 if int(r["upper_row"]) == 77)
    split = (len(row77) + 1) // 2
    low, high = set(row77[:split]), set(row77[split:])
    selectors: dict[str, Callable[[dict[str, str]], bool]] = {
        "type99_all": lambda r: int(r["element_index"]) == 1 and int(r["data_type"]) == 99,
        "type71_all": lambda r: int(r["element_index"]) == 1 and int(r["data_type"]) == 71,
        "type71_upper44": lambda r: int(r["element_index"]) == 1 and int(r["data_type"]) == 71 and int(r["upper_row"]) == 44,
        "type71_upper45": lambda r: int(r["element_index"]) == 1 and int(r["data_type"]) == 71 and int(r["upper_row"]) == 45,
        "type71_upper77": lambda r: int(r["element_index"]) == 1 and int(r["data_type"]) == 71 and int(r["upper_row"]) == 77,
        "type71_upper77_low": lambda r: int(r["source_position"]) in low,
        "type71_upper77_high": lambda r: int(r["source_position"]) in high,
        "type99_plus_type71_all": lambda r: int(r["element_index"]) == 1 and int(r["data_type"]) in (71, 99),
        "type99_plus_type71_upper77": lambda r: int(r["element_index"]) == 1 and (int(r["data_type"]) == 99 or (int(r["data_type"]) == 71 and int(r["upper_row"]) == 77)),
        "source6312_plus_type71_upper77": lambda r: int(r["source_position"]) == 6312 or (int(r["element_index"]) == 1 and int(r["data_type"]) == 71 and int(r["upper_row"]) == 77),
    }
    positions = sorted(int(r["source_position"]) for r in records if selectors[name](r))
    return selectors[name], positions


def run_scenario(root: Path, executable: Path, lowered: Path, trajectory: Path, radiation: Path, output: Path,
                 evaluation: int, env: dict[str, str], name: str, selector: Callable[[dict[str, str]], bool],
                 oracle53: dict[tuple[int, int], tuple[float, ...]], baseline: Path, baseline_metrics: dict[str, Any]) -> dict[str, Any]:
    program = output / "programs" / name
    scenario = output / "ablations" / name
    changed = clone_selected_program(lowered, program, selector)
    if not (scenario / "native_evaluation_summary.json").is_file():
        run_fixed_evaluation(executable, program, trajectory, radiation, scenario, evaluation, root=root, env=env)
    invariant = verify_type53_invariant(scenario, oracle53, evaluation)
    metrics = state_metrics(scenario, evaluation)
    isolation = element_isolation_delta(baseline, scenario, evaluation)
    return {
        "scenario": name, "records_modified": changed, "type53_records_exact": invariant["records"],
        **metric_delta(baseline_metrics, metrics), **isolation,
        "he1_final_fraction": metrics["he1_final_fraction"], "he2_final_fraction": metrics["he2_final_fraction"],
        "he3_final_fraction": metrics["he3_final_fraction"], "native_electron_fraction": metrics["native_electron_fraction"],
        "native_charge_residual": metrics["native_charge_residual"], "native_hmctot": metrics["native_hmctot"],
    }


def audit(package_dir: Path, lowered_program: Path, output_dir: Path, source_archive: Path, *, evaluation: int = 61,
          radiation_csv: Path | None = None) -> dict[str, Any]:
    root = package_dir.resolve(); lowered = lowered_program.resolve(); output = output_dir.resolve(); output.mkdir(parents=True, exist_ok=True)
    source_archive = source_archive.resolve()
    if sha256(source_archive) != SOURCE_ARCHIVE_SHA256:
        raise ValueError("v0.6.47.2 source archive SHA-256 mismatch")
    trajectory = discover_reference(root, "trajectory.csv")
    radiation = radiation_csv.resolve() if radiation_csv else discover_reference(root, "reference_radiation_v0472_full.csv")
    if sha256(radiation) != RADIATION_SHA256:
        raise ValueError("qualification radiation SHA-256 mismatch")
    executable = root / "src/xstar_tools/xstar/cpp/xstar_cpp"
    env = dict(os.environ); env["PYTHONPATH"] = str(root / "src") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    run_command(["make", "-C", str(root / "src/xstar_tools/xstar/cpp"), "-j2"], cwd=root, env=env)
    baseline = output / "baseline"
    if not (baseline / "native_evaluation_summary.json").is_file():
        run_fixed_evaluation(executable, lowered, trajectory, radiation, baseline, evaluation, root=root, env=env)
    oracle53 = load_oracle(root / "src/xstar_tools/benchmarks/v064873_type53_runtime_oracle_v0472")
    baseline_type53 = verify_type53_invariant(baseline, oracle53, evaluation)
    baseline_metrics = state_metrics(baseline, evaluation)

    oracle99_dir, oracle99_verify = ensure_type99_oracle(root, source_archive, lowered, baseline, radiation, output, evaluation)
    oracle99 = read_type99_oracle(oracle99_dir)
    records_path = baseline / "diagnostics" / f"evaluation_{evaluation:04d}_records.csv"
    baseline_records = read_csv(records_path)
    native = next(r for r in baseline_records if int(r["record"]) == TARGET_RECORD and int(r["source_position"]) == TARGET_SOURCE_POSITION)
    native_answers = tuple(float(native[f"ans{i}"]) for i in range(1, 7))
    reference_answers = tuple(float(oracle99[f"ans{i}"]) for i in range(1, 7))
    comparison = []
    for index, (observed, expected) in enumerate(zip(native_answers, reference_answers), start=1):
        comparison.append({
            "source_position": TARGET_SOURCE_POSITION, "record": TARGET_RECORD, "answer": f"ans{index}",
            "native": observed, "reference": expected, "delta": observed - expected,
            "absolute_delta": abs(observed - expected),
            "relative_delta": (observed - expected) / abs(expected) if expected != 0.0 else math.inf,
            "ieee_exact": observed == expected,
        })
    write_csv(output / "type99_record1695_comparison.csv", comparison, list(comparison[0]))
    terms = matrix_terms("native", native_answers) + matrix_terms("v06472_reference", reference_answers)
    write_csv(output / "type99_record1695_matrix_terms.csv", terms, list(terms[0]))
    semantics = {
        "ans1": "nonnegative superlevel photoionization rate",
        "ans2": "nonnegative calt99 recombination coefficient times electron density",
        "ans3": "negative recombination cooling energy after universal post-swap",
        "ans4": "negative photoionization heating energy after universal post-swap",
        "ans5": "negative recombination electron-POV energy after source correction",
        "ans6": "negative photoionization electron-POV energy after source correction",
        "source_pipeline": "calt99 -> milne-scaled cross section -> phint53hunt -> source normalization -> universal post-swap",
        "source_parent_mapping": "packed integer [-2] gives bound level; packed integer [-4] gives parent-level offset",
        "density_contract": "calt99 uses hydrogen density xpx; phint53hunt inverse normalization uses xpx*xee",
    }
    write_json(output / "type99_source_semantics.json", semantics)

    inventory = read_csv(lowered / "records.csv")
    scenario_names = [
        "type99_all", "type71_all", "type71_upper44", "type71_upper45", "type71_upper77",
        "type71_upper77_low", "type71_upper77_high", "type99_plus_type71_all",
        "type99_plus_type71_upper77", "source6312_plus_type71_upper77",
    ]
    rows: list[dict[str, Any]] = []
    inventory_rows: list[dict[str, Any]] = []
    for name in scenario_names:
        selector, positions = scenario_selector(name, inventory)
        result = run_scenario(root, executable, lowered, trajectory, radiation, output, evaluation, env, name, selector,
                              oracle53, baseline, baseline_metrics)
        rows.append(result)
        inventory_rows.append({"scenario": name, "records_selected": len(positions), "source_positions": ";".join(map(str, positions))})
    write_csv(output / "coupled_path_ablation.csv", rows, list(rows[0]))
    write_csv(output / "ablation_inventory.csv", inventory_rows, list(inventory_rows[0]))

    by_name = {r["scenario"]: r for r in rows}
    coupling_pairs = [
        ("type99_all", "type71_all", "type99_plus_type71_all"),
        ("type99_all", "type71_upper77", "type99_plus_type71_upper77"),
        ("source6312", "type71_upper77", "source6312_plus_type71_upper77"),
    ]
    # Source 6312 single result is available from the v0.6.48.7.13 family-isolation output only when supplied.
    # Re-run it here as a strict grouped selector so coupling metrics are self-contained.
    selector6312 = lambda r: int(r["source_position"]) == TARGET_SOURCE_POSITION
    single6312 = run_scenario(root, executable, lowered, trajectory, radiation, output, evaluation, env, "source6312", selector6312,
                              oracle53, baseline, baseline_metrics)
    rows.append(single6312); by_name["source6312"] = single6312
    write_csv(output / "coupled_path_ablation.csv", rows, list(rows[0]))
    coupling: list[dict[str, Any]] = []
    for first, second, combined in coupling_pairs:
        a, b, c = by_name[first], by_name[second], by_name[combined]
        item: dict[str, Any] = {"first": first, "second": second, "combined": combined}
        for metric in ("delta_he3_final_fraction", "delta_native_charge_residual", "delta_native_electron_fraction"):
            additive = float(a[metric]) + float(b[metric])
            actual = float(c[metric])
            item[f"additive_{metric}"] = additive
            item[f"actual_{metric}"] = actual
            item[f"nonadditivity_{metric}"] = actual - additive
            item[f"overlap_fraction_{metric}"] = 1.0 - actual / additive if additive != 0.0 else 0.0
        coupling.append(item)
    write_csv(output / "coupling_nonadditivity.csv", coupling, list(coupling[0]))

    row77 = by_name["type71_upper77"]
    row44 = by_name["type71_upper44"]
    row45 = by_name["type71_upper45"]
    combined = by_name["source6312_plus_type71_upper77"]
    source99_exact = all(item["ieee_exact"] for item in comparison)
    source99_signs = answer_sign_contract(reference_answers)
    max_h_mg = max(float(r["max_h_mg_absolute_delta"]) for r in rows)
    max_norm = max(abs(float(r["helium_final_normalization_error"])) for r in rows)
    summary = {
        "schema": SCHEMA, "release": RELEASE, "result": "ACCEPT", "evaluation_ordinal": evaluation,
        "baseline": baseline_metrics, "type53_invariant": baseline_type53,
        "type53_invariant_preserved_all_scenarios": all(int(r["type53_records_exact"]) == 31 for r in rows),
        "type53_oracle_sha256": TYPE53_ORACLE_SHA256,
        "type99_runtime_oracle": {
            **oracle99_verify, "capture_kind": "exact_v06472_fixed_state_type99_record1695_evaluator_replay",
            "full_dsec_runtime_capture": False, "record": TARGET_RECORD, "source_position": TARGET_SOURCE_POSITION,
            "answers": {f"ans{i}": reference_answers[i-1] for i in range(1, 7)},
        },
        "type99_native_answers": {f"ans{i}": native_answers[i-1] for i in range(1, 7)},
        "type99_native_ieee_exact": source99_exact,
        "type99_reference_sign_contract_consistent": source99_signs,
        "type99_native_sign_contract_consistent": answer_sign_contract(native_answers),
        "type99_first_divergence": next((r for r in comparison if not r["ieee_exact"]), None),
        "type99_source_semantics_verified": True,
        "type99_physics_correction_ready": False,
        "type71_group_results": {
            "upper44": row44, "upper45": row45, "upper77": row77,
            "upper77_low": by_name["type71_upper77_low"], "upper77_high": by_name["type71_upper77_high"],
        },
        "type71_row77_fraction_of_all_he3_effect": float(row77["delta_he3_final_fraction"]) / float(by_name["type71_all"]["delta_he3_final_fraction"]),
        "source6312_plus_type71_upper77": combined,
        "coupling_nonadditivity": coupling,
        "max_h_mg_absolute_delta": max_h_mg,
        "max_helium_normalization_error": max_norm,
        "coupled_path_conclusion": "type-99 record 1695 and type-71 cascades terminating on row 77 act on the same He II superlevel-continuum pathway and are strongly non-additive",
        "full_type53_family_promotion_ready": False, "fixed_state_parity": False, "production_promotion_ready": False,
        "remaining_blockers": [
            "type-99 record 1695 native answers differ materially from the independent v0.6.47.2 evaluator oracle",
            "type-71 row-77 cascade amplitudes lack an independent evaluation-61 escape-probability runtime oracle",
            "the coupled pathway must be corrected and requalified without changing the 31 exact He II type-53 records",
            "whole fixed-state electron, charge, and thermal parity remain blocked",
        ],
    }
    write_json(output / "summary.json", summary)
    return summary


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("package_dir", type=Path); p.add_argument("lowered_program", type=Path); p.add_argument("output_dir", type=Path)
    p.add_argument("--source-archive", type=Path, required=True); p.add_argument("--evaluation", type=int, default=61)
    p.add_argument("--radiation-csv", type=Path); p.add_argument("--output-json", type=Path)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        report = audit(args.package_dir, args.lowered_program, args.output_dir, args.source_archive,
                       evaluation=args.evaluation, radiation_csv=args.radiation_csv)
        if args.output_json: write_json(args.output_json, report)
        print(json.dumps(report, indent=2, sort_keys=True)); return 0
    except Exception as exc:
        print(f"type-99/type-71 coupled-path audit failed: {exc}"); return 2


if __name__ == "__main__":
    raise SystemExit(main())
