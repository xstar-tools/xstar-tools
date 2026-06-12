"""Qualification-only coupled replacement audit for the 79-record He II type-50 manifold."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from .helium_family_isolation import (
    RADIATION_SHA256,
    discover_reference,
    load_oracle,
    read_csv,
    run_command,
    sha256,
    state_metrics,
    verify_type53_invariant,
    write_csv,
    write_json,
)
from .helium_matrix_residual_decomposition import (
    TARGET_RECORD,
    TARGET_SOURCE_POSITION,
    verify_type71_invariant,
    verify_type99_invariant,
)
from .type71_type99_replacement_audit import (
    TYPE71_BUNDLE,
    TYPE71_ORACLE_SHA256,
    TYPE99_BUNDLE,
    TYPE99_ORACLE_SHA256,
    element_isolation,
    metric_delta,
)
from .v0472_type71_runtime_capture import ORACLE_NAME as TYPE71_ORACLE_NAME, verify as verify_type71
from .v0472_type99_runtime_capture import ORACLE_NAME as TYPE99_ORACLE_NAME, verify as verify_type99

RELEASE = "0.6.48.7.11"
SCHEMA = "xstar-tools-v0648711-type50-manifold-replacement-audit-v1"
TYPE50_BUNDLE = Path("src/xstar_tools/benchmarks/v064879_type50_heii_rows46_54_runtime_oracle_v0472")
TYPE50_ORACLE_NAME = "type50_heii_rows46_54_runtime_oracle.csv"
TYPE50_ORACLE_SHA256 = "548cbc4f489a19cfabb199ad2f063b581af0a1b5de21b3ae4a444841a0da4d6f"
REFERENCE_DIR = Path("src/xstar_tools/benchmarks/v06487_fixed_state_reference_v0472")
WHOLE_STATE_METRICS = (
    "electron_fraction",
    "charge_residual",
    "he1_final_fraction",
    "he2_final_fraction",
    "he3_final_fraction",
    "hmctot",
)


def _oracle_rows(path: Path, name: str) -> list[dict[str, str]]:
    rows = read_csv(path / name)
    if not rows:
        raise ValueError(f"empty oracle: {path / name}")
    return rows


def _record_map(output: Path, evaluation: int) -> dict[tuple[int, int], dict[str, str]]:
    rows = read_csv(output / "diagnostics" / f"evaluation_{evaluation:04d}_records.csv")
    return {(int(r["source_position"]), int(r["record"])): r for r in rows}


def compare_type50(
    output: Path,
    oracle_rows: list[dict[str, str]],
    destination: Path,
    evaluation: int,
    label: str,
) -> dict[str, Any]:
    native = _record_map(output, evaluation)
    comparison: list[dict[str, Any]] = []
    matrix: list[dict[str, Any]] = []
    exact_by = {f"ans{i}": 0 for i in range(1, 7)}
    committed = 0
    first = None
    for ref in oracle_rows:
        key = (int(ref["source_position"]), int(ref["record"]))
        row = native.get(key)
        if row is None:
            raise RuntimeError(f"missing type-50 manifold record {key}")
        if int(row["data_type"]) != 50 or int(row["ion_stage"]) != 2:
            raise RuntimeError(f"type-50 manifold identity changed at {key}")
        if (int(row["lower_row"]), int(row["upper_row"])) != (int(ref["lower_row"]), int(ref["upper_row"])):
            raise RuntimeError(f"type-50 manifold row identity changed at {key}")
        committed += int(row["matrix_committed"]) == 1
        observed = tuple(float(row[f"ans{i}"]) for i in range(1, 7))
        expected = tuple(float(ref[f"ans{i}"]) for i in range(1, 7))
        comp: dict[str, Any] = {
            "variant": label,
            "source_position": key[0],
            "record": key[1],
            "lower_row": int(ref["lower_row"]),
            "upper_row": int(ref["upper_row"]),
            "matrix_committed": int(row["matrix_committed"]),
        }
        for i, (a, b) in enumerate(zip(observed, expected), start=1):
            exact = a == b
            exact_by[f"ans{i}"] += int(exact)
            comp.update({
                f"observed_ans{i}": a,
                f"reference_ans{i}": b,
                f"delta_ans{i}": a - b,
                f"exact_ans{i}": str(exact).lower(),
            })
            if not exact and first is None:
                first = {"source_position": key[0], "record": key[1], "answer": f"ans{i}"}
        comparison.append(comp)
        for variant, vals in ((label, observed), ("v06472_reference", expected)):
            a1, a2, a3, a4, a5, a6 = vals
            terms = (
                ("forward_gain", int(ref["upper_row"]), int(ref["lower_row"]), a1, a2, 0.0, 0.0),
                ("reverse_gain", int(ref["lower_row"]), int(ref["upper_row"]), a2, a1, 0.0, 0.0),
                ("forward_diag_loss", int(ref["lower_row"]), int(ref["lower_row"]), -a1, -a1, a4, a6),
                ("reverse_diag_loss", int(ref["upper_row"]), int(ref["upper_row"]), -a2, -a2, -a3, -a5),
            )
            for role, matrix_row, column, aj1, aj2, cj, cj2 in terms:
                matrix.append({
                    "variant": variant,
                    "source_position": key[0],
                    "record": key[1],
                    "role": role,
                    "row": matrix_row,
                    "column": column,
                    "aj1": aj1,
                    "aj2": aj2,
                    "cj": cj,
                    "cj2": cj2,
                })
    destination.mkdir(parents=True, exist_ok=True)
    write_csv(destination / f"type50_manifold_{label}_answer_comparison.csv", comparison, list(comparison[0]))
    write_csv(destination / f"type50_manifold_{label}_matrix_terms.csv", matrix, list(matrix[0]))
    return {
        "records": len(oracle_rows),
        "answers": len(oracle_rows) * 6,
        "matrix_committed_records": committed,
        "exact_by_answer": exact_by,
        "all_ieee_exact": committed == len(oracle_rows) and all(v == len(oracle_rows) for v in exact_by.values()),
        "first_divergence": first,
        "oracle_sha256": TYPE50_ORACLE_SHA256,
    }


def reference_metrics(root: Path, evaluation: int) -> dict[str, float]:
    state_rows = read_csv(root / REFERENCE_DIR / "trajectory_state_oracle.csv")
    state = next((r for r in state_rows if int(r["evaluation_ordinal"]) == evaluation), None)
    if state is None:
        raise ValueError(f"reference state has no evaluation {evaluation}")
    ion_rows = read_csv(root / REFERENCE_DIR / "accepted_ion_populations.csv")
    helium = {
        int(r["stage"]): float(r["reference_fraction"])
        for r in ion_rows
        if int(r["reference_evaluation_ordinal"]) == evaluation and int(r["element_z"]) == 2
    }
    if set(helium) != {1, 2, 3}:
        raise ValueError("reference helium state is incomplete")
    return {
        "electron_fraction": float(state["electron_fraction_input"]),
        "charge_residual": float(state["reference_charge_residual"]),
        "hmctot": float(state["reference_hmctot"]),
        "he1_final_fraction": helium[1],
        "he2_final_fraction": helium[2],
        "he3_final_fraction": helium[3],
    }


def metric_improvements(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    reference: dict[str, float],
) -> tuple[list[dict[str, Any]], bool]:
    mapping = {
        "electron_fraction": "native_electron_fraction",
        "charge_residual": "native_charge_residual",
        "hmctot": "native_hmctot",
        "he1_final_fraction": "he1_final_fraction",
        "he2_final_fraction": "he2_final_fraction",
        "he3_final_fraction": "he3_final_fraction",
    }
    rows: list[dict[str, Any]] = []
    for metric in WHOLE_STATE_METRICS:
        key = mapping[metric]
        base = float(baseline[key])
        cand = float(candidate[key])
        ref = float(reference[metric])
        base_error = abs(base - ref)
        cand_error = abs(cand - ref)
        rows.append({
            "metric": metric,
            "reference": ref,
            "baseline": base,
            "candidate": cand,
            "delta_candidate_minus_baseline": cand - base,
            "baseline_absolute_error": base_error,
            "candidate_absolute_error": cand_error,
            "absolute_error_reduction": base_error - cand_error,
            "improved": str(cand_error < base_error).lower(),
        })
    return rows, all(row["improved"] == "true" for row in rows)


def audit(
    package_dir: Path,
    lowered_program: Path,
    constrained_baseline: Path,
    output_dir: Path,
    *,
    evaluation: int = 61,
    radiation_csv: Path | None = None,
) -> dict[str, Any]:
    if evaluation != 61:
        raise ValueError("the type-50 manifold oracle replacement is restricted to evaluation 61")
    root = package_dir.resolve()
    lowered = lowered_program.resolve()
    baseline = constrained_baseline.resolve()
    output = output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    trajectory = discover_reference(root, "trajectory.csv")
    radiation = radiation_csv.resolve() if radiation_csv else discover_reference(root, "reference_radiation_v0472_full.csv")
    if sha256(radiation) != RADIATION_SHA256:
        raise ValueError("qualification radiation SHA-256 mismatch")
    type50_dir = root / TYPE50_BUNDLE
    type50_csv = type50_dir / TYPE50_ORACLE_NAME
    if not type50_csv.is_file() or sha256(type50_csv) != TYPE50_ORACLE_SHA256:
        raise ValueError("type-50 manifold oracle is missing or modified")
    oracle50 = _oracle_rows(type50_dir, TYPE50_ORACLE_NAME)
    if len(oracle50) != 79:
        raise ValueError(f"expected 79 type-50 oracle records, found {len(oracle50)}")

    exe = root / "src/xstar_tools/xstar/cpp/xstar_cpp"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root / "src") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    run_command(["make", "-C", str(root / "src/xstar_tools/xstar/cpp"), "-j2"], cwd=root, env=env)

    candidate = output / "candidate_exact_type50_manifold"
    candidate_env = dict(env)
    candidate_env["XSTAR_QUALIFICATION_REPLACEMENT"] = "1"
    candidate_env["XSTAR_QUALIFICATION_TYPE99_RECORD1695_ORACLE"] = "1"
    candidate_env["XSTAR_QUALIFICATION_TYPE50_MANIFOLD_ORACLE"] = "1"
    if not (candidate / "native_evaluation_summary.json").is_file():
        run_command([
            str(exe), "run-fixed-evaluation",
            "--case-dir", str(lowered),
            "--trajectory-csv", str(trajectory),
            "--evaluation", str(evaluation),
            "--radiation-csv", str(radiation),
            "--diagnostics-dir", str(candidate / "diagnostics"),
            "--output-dir", str(candidate),
        ], cwd=root, env=candidate_env)

    oracle53 = load_oracle(root / "src/xstar_tools/benchmarks/v064873_type53_runtime_oracle_v0472")
    type71_dir = root / TYPE71_BUNDLE
    type99_dir = root / TYPE99_BUNDLE
    v71 = verify_type71(type71_dir)
    v99 = verify_type99(type99_dir)
    if v71["result"] != "ACCEPT" or v71["oracle_sha256"] != TYPE71_ORACLE_SHA256:
        raise ValueError("type-71 oracle verification failed")
    if v99["result"] != "ACCEPT" or v99["oracle_sha256"] != TYPE99_ORACLE_SHA256:
        raise ValueError("type-99 oracle verification failed")
    oracle71 = _oracle_rows(type71_dir, TYPE71_ORACLE_NAME)
    oracle99 = _oracle_rows(type99_dir, TYPE99_ORACLE_NAME)[0]

    constraints = {
        "baseline": {
            "type53": verify_type53_invariant(baseline, oracle53, evaluation),
            "type71": verify_type71_invariant(baseline, oracle71, evaluation),
            "type99": verify_type99_invariant(baseline, oracle99, evaluation),
        },
        "candidate": {
            "type53": verify_type53_invariant(candidate, oracle53, evaluation),
            "type71": verify_type71_invariant(candidate, oracle71, evaluation),
            "type99": verify_type99_invariant(candidate, oracle99, evaluation),
        },
    }
    baseline50 = compare_type50(baseline, oracle50, output, evaluation, "baseline")
    candidate50 = compare_type50(candidate, oracle50, output, evaluation, "candidate")
    if not candidate50["all_ieee_exact"]:
        raise RuntimeError("the coupled type-50 candidate did not apply all 79 oracle records exactly")

    baseline_metrics = state_metrics(baseline, evaluation)
    candidate_metrics = state_metrics(candidate, evaluation)
    reference = reference_metrics(root, evaluation)
    improvements, whole_state_improved = metric_improvements(baseline_metrics, candidate_metrics, reference)
    write_csv(output / "type50_manifold_fixed_state_metrics.csv", improvements, list(improvements[0]))
    deltas = metric_delta(baseline_metrics, candidate_metrics)
    isolation = element_isolation(baseline, candidate, evaluation)
    constraints_preserved = (
        constraints["candidate"]["type53"]["records"] == 31
        and constraints["candidate"]["type71"]["records"] == 31
        and constraints["candidate"]["type99"]["exact_answers"] == 6
    )
    candidate_fixed_state_result = "ACCEPT" if whole_state_improved and constraints_preserved and isolation["nonzero_h_mg_fields"] == 0 else "REJECT"

    state_row: dict[str, Any] = {"evaluation_ordinal": evaluation}
    for prefix, values in (("baseline", baseline_metrics), ("candidate", candidate_metrics)):
        for key in (
            "he1_final_fraction", "he2_final_fraction", "he3_final_fraction",
            "native_electron_fraction", "native_charge_residual", "native_hmctot",
        ):
            state_row[f"{prefix}_{key}"] = values[key]
    state_row.update(deltas)
    write_csv(output / "type50_manifold_candidate_state_delta.csv", [state_row], list(state_row))

    summary = {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT",
        "evaluation_ordinal": evaluation,
        "candidate_definition": "qualification-only simultaneous substitution of all 79 He II type-50 rows-46-54 oracle records",
        "qualification_gates": [
            "XSTAR_QUALIFICATION_REPLACEMENT=1",
            "XSTAR_QUALIFICATION_TYPE99_RECORD1695_ORACLE=1",
            "XSTAR_QUALIFICATION_TYPE50_MANIFOLD_ORACLE=1",
        ],
        "type50_runtime_oracle": {
            "records": len(oracle50),
            "oracle_sha256": TYPE50_ORACLE_SHA256,
            "capture_kind": "exact_v06472_fixed_state_type50_heii_rows46_54_evaluator_replay",
            "full_dsec_runtime_capture": False,
        },
        "type50_baseline_comparison": baseline50,
        "type50_candidate_comparison": candidate50,
        "immutable_constraints": constraints,
        "baseline": baseline_metrics,
        "candidate": candidate_metrics,
        "reference": reference,
        "candidate_deltas": deltas,
        "whole_fixed_state_metric_improvements": improvements,
        "all_whole_fixed_state_metrics_improved": whole_state_improved,
        "element_isolation": isolation,
        "candidate_fixed_state_result": candidate_fixed_state_result,
        "candidate_general_state_implementation": False,
        "type50_manifold_physics_replacement_ready": False,
        "fixed_state_parity": False,
        "production_promotion_ready": False,
        "remaining_blockers": [
            "the type-50 substitution is restricted to the evaluation-61 fixed state",
            "the type-50 oracle is an evaluator replay rather than a complete original DSEC escape-probability capture",
            "whole fixed-state parity remains blocked even if the qualification candidate improves all monitored metrics",
            "a source-faithful general-state type-50 implementation and trajectory/product verification are still required",
        ],
    }
    write_json(output / "summary.json", summary)
    return summary


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("package_dir", type=Path)
    p.add_argument("lowered_program", type=Path)
    p.add_argument("constrained_baseline", type=Path)
    p.add_argument("output_dir", type=Path)
    p.add_argument("--evaluation", type=int, default=61)
    p.add_argument("--radiation-csv", type=Path)
    p.add_argument("--output-json", type=Path)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        report = audit(
            args.package_dir,
            args.lowered_program,
            args.constrained_baseline,
            args.output_dir,
            evaluation=args.evaluation,
            radiation_csv=args.radiation_csv,
        )
        if args.output_json:
            write_json(args.output_json.resolve(), report)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"type50 manifold replacement audit failed: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
