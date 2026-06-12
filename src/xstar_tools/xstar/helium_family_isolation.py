"""Helium non-type-53 matrix contribution isolation for xstar_tools v0.6.48.7.9.

The workflow preserves the 31 independently qualified He II type-53 records,
constructs source-position and row-level matrix ledgers, runs one-family-at-a-
time helium matrix ablations, and audits type 30 separately as a preliminary
ion-balance contribution.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import shutil
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

RELEASE = "0.6.48.7.9"
SCHEMA = "xstar-tools-v064875-helium-family-isolation-v1"
MATRIX_FAMILIES = (50, 54, 56, 57, 63, 69, 71, 74, 76, 77, 95, 99)
PRELIMINARY_FAMILY = 30
ORACLE_SHA256 = "76c4a59d168120f70d810790d763fbfba1ea7a3d3b98cb3c9e5267380dfafcdb"
RADIATION_SHA256 = "8cd5771924724d5aa8fcf5af8c533f5b5ca9887e24a94ac2d7b4557c0ff7b108"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})
    os.replace(tmp, path)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def discover_reference(root: Path, name: str) -> Path:
    candidates = (
        root / "src/xstar_tools/benchmarks/v06486_qualification_reference_v0472" / name,
        root / "src/xstar_tools/benchmarks/v0648_compiled_case_helike_type69_mg11_ne1e8" / name,
    )
    for candidate in candidates:
        if candidate.is_file() and candidate.stat().st_size:
            return candidate.resolve()
    raise FileNotFoundError(f"cannot locate {name}; checked: " + ", ".join(map(str, candidates)))


def run_command(command: list[str], *, cwd: Path, env: dict[str, str]) -> str:
    print("$ " + " ".join(command))
    result = subprocess.run(command, cwd=cwd, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print(result.stdout, end="")
    if result.returncode:
        raise RuntimeError(f"command failed with status {result.returncode}: {' '.join(command)}")
    return result.stdout


def clone_program_for_ablation(source: Path, destination: Path, family: int, mode: str) -> int:
    destination.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        target = destination / item.name
        if item.name == "records.csv":
            continue
        if item.is_file():
            try:
                target.symlink_to(item.resolve())
            except OSError:
                shutil.copy2(item, target)
    rows = read_csv(source / "records.csv")
    changed = 0
    fields = list(rows[0]) if rows else []
    for row in rows:
        if int(row["element_index"]) != 1 or int(row["data_type"]) != family:
            continue
        if mode == "matrix":
            if int(row.get("matrix_enabled", "1")) != 0:
                row["matrix_enabled"] = "0"
                changed += 1
        elif mode == "preliminary":
            # Type 30 is matrix-disabled already.  Setting rate_type to zero
            # leaves the raw evaluator intact while excluding it from the
            # preliminary ionization/recombination accumulator.
            if int(row["rate_type"]) != 0:
                row["rate_type"] = "0"
                changed += 1
        else:
            raise ValueError(f"unknown ablation mode: {mode}")
    if changed == 0:
        raise ValueError(f"ablation selected no helium type-{family} records")
    write_csv(destination / "records.csv", rows, fields)
    return changed


def run_fixed_evaluation(
    executable: Path,
    case_dir: Path,
    trajectory: Path,
    radiation: Path,
    output_dir: Path,
    evaluation: int,
    *,
    root: Path,
    env: dict[str, str],
    matrix_ablation_type: int = 0,
    preliminary_ablation_type: int = 0,
    source_ablation_position: int = 0,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    run_env = dict(env)
    run_env.pop("XSTAR_HELIUM_ABLATE_MATRIX_TYPE", None)
    run_env.pop("XSTAR_HELIUM_ABLATE_PRELIMINARY_TYPE", None)
    run_env.pop("XSTAR_HELIUM_ABLATE_SOURCE_POSITION", None)
    if matrix_ablation_type or preliminary_ablation_type or source_ablation_position:
        run_env["XSTAR_QUALIFICATION_ABLATION"] = "1"
    else:
        run_env.pop("XSTAR_QUALIFICATION_ABLATION", None)
    if matrix_ablation_type:
        run_env["XSTAR_HELIUM_ABLATE_MATRIX_TYPE"] = str(matrix_ablation_type)
    if preliminary_ablation_type:
        run_env["XSTAR_HELIUM_ABLATE_PRELIMINARY_TYPE"] = str(preliminary_ablation_type)
    if source_ablation_position:
        run_env["XSTAR_HELIUM_ABLATE_SOURCE_POSITION"] = str(source_ablation_position)
    run_command([
        str(executable), "run-fixed-evaluation",
        "--case-dir", str(case_dir),
        "--trajectory-csv", str(trajectory),
        "--evaluation", str(evaluation),
        "--radiation-csv", str(radiation),
        "--diagnostics-dir", str(output_dir / "diagnostics"),
        "--output-dir", str(output_dir),
    ], cwd=root, env=run_env)


def load_oracle(oracle_dir: Path) -> dict[tuple[int, int], tuple[float, ...]]:
    csv_path = oracle_dir / "type53_runtime_oracle.csv"
    if not csv_path.is_file() or sha256(csv_path) != ORACLE_SHA256:
        raise RuntimeError("frozen type-53 oracle is missing or modified")
    result: dict[tuple[int, int], tuple[float, ...]] = {}
    for row in read_csv(csv_path):
        key = (int(row["source_position"]), int(row["record"]))
        result[key] = tuple(float(row[f"ans{i}"]) for i in range(1, 7))
    if len(result) != 31:
        raise RuntimeError(f"expected 31 frozen oracle records, found {len(result)}")
    return result


def verify_type53_invariant(output_dir: Path, oracle: dict[tuple[int, int], tuple[float, ...]], evaluation: int) -> dict[str, Any]:
    records = read_csv(output_dir / "diagnostics" / f"evaluation_{evaluation:04d}_records.csv")
    selected = [
        row for row in records
        if int(row["element_z"]) == 2 and int(row["ion_stage"]) == 2 and int(row["data_type"]) == 53
    ]
    if len(selected) != 31:
        raise RuntimeError(f"He II type-53 invariant expected 31 records, found {len(selected)}")
    for row in selected:
        key = (int(row["source_position"]), int(row["record"]))
        expected = oracle.get(key)
        if expected is None:
            raise RuntimeError(f"missing type-53 oracle key {key}")
        applied = tuple(float(row[f"ans{i}"]) for i in range(1, 7))
        shadow = tuple(float(row[f"type53_shadow_ans{i}"]) for i in range(1, 7))
        if applied != expected or shadow != expected:
            raise RuntimeError(f"type-53 invariant changed at source_position={key[0]} record={key[1]}")
    return {"records": 31, "applied_exact": True, "shadow_exact": True, "oracle_sha256": ORACLE_SHA256}


def state_metrics(output_dir: Path, evaluation: int) -> dict[str, Any]:
    summary = json.loads((output_dir / "native_evaluation_summary.json").read_text(encoding="utf-8"))
    ion_rows = read_csv(output_dir / "diagnostics" / f"evaluation_{evaluation:04d}_ion_balance.csv")
    helium = {int(row["stage"]): row for row in ion_rows if int(row["element_z"]) == 2}
    metrics: dict[str, Any] = {
        "native_electron_fraction": float(summary["native_electron_fraction"]),
        "native_charge_residual": float(summary["native_charge_residual"]),
        "native_hmctot": float(summary["native_hmctot"]),
        "records_evaluated": int(summary["records_evaluated"]),
        "python_callbacks": int(summary["python_callbacks"]),
    }
    for stage in (1, 2, 3):
        row = helium[stage]
        metrics[f"he{stage}_preliminary_fraction"] = float(row["preliminary_fraction"])
        metrics[f"he{stage}_final_fraction"] = float(row["final_fraction"])
        metrics[f"he{stage}_preliminary_ionization"] = float(row["preliminary_ionization"])
        metrics[f"he{stage}_preliminary_recombination"] = float(row["preliminary_recombination"])
    return metrics


def term_rows(records: list[dict[str, str]], populations: dict[int, float]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    roles = ("forward_gain", "reverse_gain", "forward_diag_loss", "reverse_diag_loss")
    for row in records:
        if int(row["element_z"]) != 2 or int(row["data_type"]) not in MATRIX_FAMILIES or int(row["matrix_committed"]) != 1:
            continue
        lower, upper = int(row["lower_row"]), int(row["upper_row"])
        ans = [float(row[f"ans{i}"]) for i in range(1, 7)]
        density = float(row["density_scale"])
        term_values = (
            (upper, lower, ans[0], ans[1], 0.0, 0.0),
            (lower, upper, ans[1], ans[0], 0.0, 0.0),
            (lower, lower, -ans[0], -ans[0], ans[3] * density, ans[5] * density),
            (upper, upper, -ans[1], -ans[1], -ans[2] * density, -ans[4] * density),
        )
        for offset, (role, values) in enumerate(zip(roles, term_values)):
            matrix_row, column, aj1, aj2, cj, cj2 = values
            population = populations.get(column, 0.0)
            residual = aj1 * population
            heat = cj * populations.get(matrix_row, 0.0) if matrix_row == column else 0.0
            heat2 = cj2 * populations.get(matrix_row, 0.0) if matrix_row == column else 0.0
            output.append({
                "evaluation_ordinal": int(row["evaluation_ordinal"]),
                "data_type": int(row["data_type"]),
                "source_position": int(row["source_position"]),
                "term_source_position": int(row["source_position"]) + offset,
                "record": int(row["record"]),
                "ion_stage": int(row["ion_stage"]),
                "lower_row": lower,
                "upper_row": upper,
                "role": role,
                "row": matrix_row,
                "column": column,
                "aj1": aj1,
                "aj2": aj2,
                "cj": cj,
                "cj2": cj2,
                "column_population": population,
                "row_population": populations.get(matrix_row, 0.0),
                "row_residual_contribution": residual,
                "heating_matrix_contribution": heat,
                "heating2_matrix_contribution": heat2,
            })
    return output


def build_ledgers(baseline: Path, output_dir: Path, evaluation: int) -> dict[str, Any]:
    diagnostics = baseline / "diagnostics"
    records = read_csv(diagnostics / f"evaluation_{evaluation:04d}_records.csv")
    pop_rows = read_csv(diagnostics / f"evaluation_{evaluation:04d}_populations.csv")
    populations = {int(row["element_row"]): float(row["final_population"]) for row in pop_rows if int(row["element_z"]) == 2}
    terms = term_rows(records, populations)
    term_fields = list(terms[0]) if terms else []
    write_csv(output_dir / "helium_matrix_terms.csv", terms, term_fields)

    source_groups: dict[tuple[int, int, int], dict[str, Any]] = {}
    row_groups: dict[tuple[int, int], dict[str, Any]] = {}
    for term in terms:
        skey = (term["data_type"], term["source_position"], term["record"])
        source = source_groups.setdefault(skey, {
            "data_type": skey[0], "source_position": skey[1], "record": skey[2],
            "terms": 0, "net_row_residual_contribution": 0.0, "l1_row_residual_contribution": 0.0,
            "net_heating_matrix_contribution": 0.0, "net_heating2_matrix_contribution": 0.0,
        })
        source["terms"] += 1
        source["net_row_residual_contribution"] += term["row_residual_contribution"]
        source["l1_row_residual_contribution"] += abs(term["row_residual_contribution"])
        source["net_heating_matrix_contribution"] += term["heating_matrix_contribution"]
        source["net_heating2_matrix_contribution"] += term["heating2_matrix_contribution"]
        rkey = (term["data_type"], term["row"])
        rgroup = row_groups.setdefault(rkey, {
            "data_type": rkey[0], "row": rkey[1], "terms": 0,
            "net_row_residual_contribution": 0.0, "l1_row_residual_contribution": 0.0,
        })
        rgroup["terms"] += 1
        rgroup["net_row_residual_contribution"] += term["row_residual_contribution"]
        rgroup["l1_row_residual_contribution"] += abs(term["row_residual_contribution"])
    source_rows = sorted(source_groups.values(), key=lambda x: (x["data_type"], x["source_position"]))
    row_rows = sorted(row_groups.values(), key=lambda x: (x["data_type"], x["row"]))
    write_csv(output_dir / "helium_source_position_ledger.csv", source_rows, list(source_rows[0]) if source_rows else [])
    write_csv(output_dir / "helium_row_residuals.csv", row_rows, list(row_rows[0]) if row_rows else [])
    return {"matrix_terms": len(terms), "source_records": len(source_rows), "family_rows": len(row_rows)}


def isolate(
    package_dir: Path,
    lowered_program: Path,
    output_dir: Path,
    *,
    evaluation: int = 61,
    radiation_csv: Path | None = None,
) -> dict[str, Any]:
    root = package_dir.resolve()
    lowered = lowered_program.resolve()
    output = output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if not (lowered / "manifest.txt").is_file():
        raise FileNotFoundError(f"invalid lowered program: {lowered}")
    trajectory = discover_reference(root, "trajectory.csv")
    radiation = radiation_csv.resolve() if radiation_csv else discover_reference(root, "reference_radiation_v0472_full.csv")
    if sha256(radiation) != RADIATION_SHA256:
        raise RuntimeError("qualification radiation SHA-256 mismatch")
    oracle_dir = root / "src/xstar_tools/benchmarks/v064873_type53_runtime_oracle_v0472"
    oracle = load_oracle(oracle_dir)
    executable = root / "src/xstar_tools/xstar/cpp/xstar_cpp"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root / "src") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    run_command(["make", "-C", str(root / "src/xstar_tools/xstar/cpp"), "-j2"], cwd=root, env=env)

    baseline = output / "baseline"
    if not (baseline / "native_evaluation_summary.json").is_file():
        run_fixed_evaluation(executable, lowered, trajectory, radiation, baseline, evaluation, root=root, env=env)
    baseline_invariant = verify_type53_invariant(baseline, oracle, evaluation)
    baseline_metrics = state_metrics(baseline, evaluation)
    ledgers = build_ledgers(baseline, output, evaluation)

    scenarios: list[dict[str, Any]] = []
    preliminary_rows: list[dict[str, Any]] = []
    final_delta_rows: list[dict[str, Any]] = []
    record_inventory = read_csv(lowered / "records.csv")
    for family in (*MATRIX_FAMILIES, PRELIMINARY_FAMILY):
            mode = "preliminary" if family == PRELIMINARY_FAMILY else "matrix"
            selected = [row for row in record_inventory if int(row["element_index"]) == 1 and int(row["data_type"]) == family]
            changed = sum(1 for row in selected if mode == "preliminary" or int(row.get("matrix_enabled", "1")) != 0)
            if changed == 0:
                raise RuntimeError(f"ablation selected no helium type-{family} records")
            scenario_output = output / "ablations" / f"type_{family}"
            if not (scenario_output / "native_evaluation_summary.json").is_file():
                run_fixed_evaluation(
                    executable, lowered, trajectory, radiation, scenario_output, evaluation, root=root, env=env,
                    matrix_ablation_type=family if mode == "matrix" else 0,
                    preliminary_ablation_type=family if mode == "preliminary" else 0,
                )
            invariant = verify_type53_invariant(scenario_output, oracle, evaluation)
            metrics = state_metrics(scenario_output, evaluation)
            row: dict[str, Any] = {
                "scenario": f"ablate_type_{family}",
                "data_type": family,
                "ablation_mode": mode,
                "records_modified": changed,
                "type53_records_exact": invariant["records"],
            }
            for key, base_value in baseline_metrics.items():
                if isinstance(base_value, (int, float)):
                    row[f"baseline_{key}"] = base_value
                    row[f"ablated_{key}"] = metrics[key]
                    row[f"delta_{key}"] = metrics[key] - base_value
            scenarios.append(row)
            for stage in (1, 2, 3):
                preliminary_rows.append({
                    "scenario": row["scenario"], "data_type": family, "ablation_mode": mode, "stage": stage,
                    "baseline_ionization": baseline_metrics[f"he{stage}_preliminary_ionization"],
                    "ablated_ionization": metrics[f"he{stage}_preliminary_ionization"],
                    "delta_ionization": metrics[f"he{stage}_preliminary_ionization"] - baseline_metrics[f"he{stage}_preliminary_ionization"],
                    "baseline_recombination": baseline_metrics[f"he{stage}_preliminary_recombination"],
                    "ablated_recombination": metrics[f"he{stage}_preliminary_recombination"],
                    "delta_recombination": metrics[f"he{stage}_preliminary_recombination"] - baseline_metrics[f"he{stage}_preliminary_recombination"],
                    "baseline_fraction": baseline_metrics[f"he{stage}_preliminary_fraction"],
                    "ablated_fraction": metrics[f"he{stage}_preliminary_fraction"],
                    "delta_fraction": metrics[f"he{stage}_preliminary_fraction"] - baseline_metrics[f"he{stage}_preliminary_fraction"],
                })
                final_delta_rows.append({
                    "scenario": row["scenario"], "data_type": family, "ablation_mode": mode, "stage": stage,
                    "baseline_final_fraction": baseline_metrics[f"he{stage}_final_fraction"],
                    "ablated_final_fraction": metrics[f"he{stage}_final_fraction"],
                    "delta_final_fraction": metrics[f"he{stage}_final_fraction"] - baseline_metrics[f"he{stage}_final_fraction"],
                })

    scenario_fields = list(scenarios[0]) if scenarios else []
    write_csv(output / "helium_family_ablation.csv", scenarios, scenario_fields)
    write_csv(output / "helium_preliminary_rates.csv", preliminary_rows, list(preliminary_rows[0]) if preliminary_rows else [])
    write_csv(output / "helium_final_population_deltas.csv", final_delta_rows, list(final_delta_rows[0]) if final_delta_rows else [])

    ranked_charge = sorted(scenarios, key=lambda x: abs(x["delta_native_charge_residual"]), reverse=True)
    ranked_he3 = sorted(scenarios, key=lambda x: abs(x["delta_he3_final_fraction"]), reverse=True)
    preliminary_candidate_family = ranked_he3[0]["data_type"] if ranked_he3 else None
    baseline_records = read_csv(baseline / "diagnostics" / f"evaluation_{evaluation:04d}_records.csv")
    candidate_positions = sorted({
        int(row["source_position"]) for row in baseline_records
        if int(row["element_z"]) == 2 and int(row["data_type"]) == preliminary_candidate_family and int(row["matrix_committed"]) == 1
    }) if preliminary_candidate_family is not None else []
    source_scenarios: list[dict[str, Any]] = []
    for source_position in candidate_positions:
        source_output = output / "source_ablations" / f"source_{source_position}"
        if not (source_output / "native_evaluation_summary.json").is_file():
            run_fixed_evaluation(
                executable, lowered, trajectory, radiation, source_output, evaluation, root=root, env=env,
                source_ablation_position=source_position,
            )
        invariant = verify_type53_invariant(source_output, oracle, evaluation)
        metrics = state_metrics(source_output, evaluation)
        source_record = next(row for row in baseline_records if int(row["source_position"]) == source_position)
        source_row: dict[str, Any] = {
            "scenario": f"ablate_source_{source_position}",
            "data_type": preliminary_candidate_family,
            "source_position": source_position,
            "record": int(source_record["record"]),
            "lower_row": int(source_record["lower_row"]),
            "upper_row": int(source_record["upper_row"]),
            "type53_records_exact": invariant["records"],
        }
        for key, base_value in baseline_metrics.items():
            if isinstance(base_value, (int, float)):
                source_row[f"baseline_{key}"] = base_value
                source_row[f"ablated_{key}"] = metrics[key]
                source_row[f"delta_{key}"] = metrics[key] - base_value
        source_scenarios.append(source_row)
    write_csv(
        output / "helium_source_position_ablation.csv",
        source_scenarios,
        list(source_scenarios[0]) if source_scenarios else [],
    )
    ranked_source_he3 = sorted(source_scenarios, key=lambda x: abs(x["delta_he3_final_fraction"]), reverse=True)
    matrix_results = [row for row in scenarios if row["ablation_mode"] == "matrix"]
    type30 = next(row for row in scenarios if row["data_type"] == PRELIMINARY_FAMILY)
    candidate_family = preliminary_candidate_family
    source_ledger_rows = read_csv(output / "helium_source_position_ledger.csv")
    candidate_sources = [row for row in source_ledger_rows if int(row["data_type"]) == candidate_family] if candidate_family is not None else []
    candidate_sources.sort(key=lambda row: float(row["l1_row_residual_contribution"]), reverse=True)
    candidate_source = candidate_sources[0] if candidate_sources else None
    causal_candidate_source = ranked_source_he3[0] if ranked_source_he3 else None
    co_dominant = [
        {"data_type": row["data_type"], "delta_he3_final_fraction": row["delta_he3_final_fraction"],
         "delta_native_charge_residual": row["delta_native_charge_residual"], "records_modified": row["records_modified"]}
        for row in ranked_he3[:3]
    ]
    summary = {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT",
        "evaluation_ordinal": evaluation,
        "lowered_program": str(lowered),
        "output_directory": str(output),
        "matrix_families": list(MATRIX_FAMILIES),
        "preliminary_family": PRELIMINARY_FAMILY,
        "matrix_family_ablations": len(matrix_results),
        "preliminary_family_ablations": 1,
        "baseline": baseline_metrics,
        "type53_invariant": baseline_invariant,
        "type53_invariant_preserved_all_scenarios": all(row["type53_records_exact"] == 31 for row in scenarios + source_scenarios),
        "oracle_sha256": ORACLE_SHA256,
        "radiation_sha256": RADIATION_SHA256,
        "ledger_counts": ledgers,
        "largest_charge_residual_effect": ranked_charge[0] if ranked_charge else None,
        "largest_heiii_effect": ranked_he3[0] if ranked_he3 else None,
        "type30_preliminary_effect": type30,
        "isolated_candidate_family": candidate_family,
        "source_position_ablations": len(source_scenarios),
        "isolated_candidate_source_position": int(causal_candidate_source["source_position"]) if causal_candidate_source else None,
        "isolated_candidate_record": int(causal_candidate_source["record"]) if causal_candidate_source else None,
        "isolated_candidate_source_delta_heiii": float(causal_candidate_source["delta_he3_final_fraction"]) if causal_candidate_source else None,
        "isolated_candidate_source_delta_charge_residual": float(causal_candidate_source["delta_native_charge_residual"]) if causal_candidate_source else None,
        "isolated_candidate_source_l1_row_residual": float(candidate_source["l1_row_residual_contribution"]) if candidate_source else None,
        "co_dominant_family_ranking": co_dominant,
        "isolated_candidate_basis": "largest absolute final He III family-ablation response followed by one-source-position causal ablation; candidate only, not a promoted correction",
        "full_type53_family_promotion_ready": False,
        "fixed_state_parity": False,
        "production_promotion_ready": False,
        "remaining_blockers": [
            "candidate non-type-53 family requires source-semantic or independent runtime-oracle verification before correction",
            "type-53 ions outside the 31-record He II scope remain unqualified",
            "whole fixed-state electron, charge, and thermal parity remain blocked",
        ],
    }
    write_json(output / "summary.json", summary)
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package_dir", type=Path)
    parser.add_argument("lowered_program", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--evaluation", type=int, default=61)
    parser.add_argument("--radiation-csv", type=Path)
    parser.add_argument("--output-json", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = isolate(args.package_dir, args.lowered_program, args.output_dir, evaluation=args.evaluation, radiation_csv=args.radiation_csv)
        if args.output_json:
            write_json(args.output_json.resolve(), report)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"helium family isolation failed: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
