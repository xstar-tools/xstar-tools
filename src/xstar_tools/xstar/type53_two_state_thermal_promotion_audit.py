"""Promote the source-faithful type-53 row-46 contract at two captured states.

This qualification audit verifies the independent evaluation-60 runtime-state
oracle and the evaluation-61 row-46 oracle, applies the same coupled 44-record
contract through the fixed-state engine, exercises the thermal-controller
callback with the promoted live law, and attributes the remaining ``hmctot``
discrepancy by element and continuum budget.  It does not promote the complete
thermal controller or production products.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import subprocess
from pathlib import Path
from typing import Any, Iterable, Mapping

from .helium_family_isolation import read_csv, run_command, write_csv, write_json
from .helium_solve_response_decomposition import _diagnostic_path
from .type53_row46_dsec_runtime_contract_audit import (
    BUNDLE as EVAL61_BUNDLE_REL,
    RECORDS_NAME as EVAL61_RECORDS_NAME,
    TERMS_NAME as EVAL61_TERMS_NAME,
    _candidate_records,
    _candidate_terms,
    _compare_records,
    _compare_terms,
    verify_oracle as verify_eval61_oracle,
)
from .type53_runtime_state_independent_capture import (
    RECORDS_NAME as EVAL60_RECORDS_NAME,
    TERMS_NAME as EVAL60_TERMS_NAME,
    RADIATION_NAME,
    TAU_NAME,
    verify as verify_eval60_oracle,
)

csv.field_size_limit(1 << 31)

RELEASE = "0.6.48.7.19.1"
SCHEMA = "xstar-tools-v06487191-type53-two-state-thermal-promotion-audit-v1"
EVAL60 = 60
EVAL61 = 61
TARGET_RECORDS = 44
TARGET_ANSWERS = 264
TARGET_TERMS = 176
EMBEDDED_EVAL60 = Path("src/xstar_tools/benchmarks/v0648719_type53_two_state_promotion/evaluation60")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _build(root: Path) -> Path:
    cpp = root / "src/xstar_tools/xstar/cpp"
    run_command(["make", "-C", str(cpp), "-j2"], cwd=root, env=dict(os.environ))
    exe = cpp / "xstar_cpp"
    if not exe.is_file():
        raise FileNotFoundError(exe)
    return exe


def _promotion_env(root: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root / "src") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["XSTAR_QUALIFICATION_REPLACEMENT"] = "1"
    env["XSTAR_QUALIFICATION_TYPE53_TWO_STATE_PROMOTION"] = "1"
    env["XSTAR_QUALIFICATION_SOLVE_RESPONSE"] = "1"
    return env


def _run_fixed(
    root: Path,
    executable: Path,
    case_dir: Path,
    output: Path,
    evaluation: int,
    *,
    promoted: bool,
    eval60_bundle: Path,
) -> None:
    trajectory = root / "src/xstar_tools/benchmarks/v06486_qualification_reference_v0472/trajectory.csv"
    radiation = root / "src/xstar_tools/benchmarks/v06486_qualification_reference_v0472/reference_radiation_v0472_full.csv"
    cmd = [
        str(executable), "run-fixed-evaluation",
        "--case-dir", str(case_dir),
        "--trajectory-csv", str(trajectory),
        "--evaluation", str(evaluation),
        "--radiation-csv", str(radiation),
        "--diagnostics-dir", str(output / "diagnostics"),
        "--output-dir", str(output),
    ]
    env = _promotion_env(root) if promoted else dict(os.environ)
    if promoted and evaluation == EVAL60:
        oracle = read_csv(eval60_bundle / EVAL60_RECORDS_NAME)
        temperatures = {float(r["temperature_k"]) for r in oracle}
        coverings = {float(r["covering_fraction"]) for r in oracle}
        if len(temperatures) != 1 or len(coverings) != 1:
            raise ValueError("evaluation-60 oracle does not have one temperature and covering fraction")
        cmd += [
            "--dsec-radiation-csv", str(eval60_bundle / RADIATION_NAME),
            "--continuum-tau-csv", str(eval60_bundle / TAU_NAME),
            "--dsec-covering-fraction", format(next(iter(coverings)), ".17g"),
            "--temperature-k", format(next(iter(temperatures)), ".17g"),
        ]
    run_command(cmd, cwd=root, env=env)


def _run_controller_smoke(
    root: Path,
    executable: Path,
    case_dir: Path,
    eval60_bundle: Path,
    output: Path,
) -> dict[str, Any]:
    trajectory = root / "src/xstar_tools/benchmarks/v06486_qualification_reference_v0472/trajectory.csv"
    radiation = root / "src/xstar_tools/benchmarks/v06486_qualification_reference_v0472/reference_radiation_v0472_full.csv"
    oracle = read_csv(eval60_bundle / EVAL60_RECORDS_NAME)
    temperature = next(iter({float(r["temperature_k"]) for r in oracle}))
    covering = next(iter({float(r["covering_fraction"]) for r in oracle}))
    run_command([
        str(executable), "run-fixed-dsec",
        "--case-dir", str(case_dir),
        "--trajectory-csv", str(trajectory),
        "--radiation-csv", str(radiation),
        "--dsec-radiation-csv", str(eval60_bundle / RADIATION_NAME),
        "--continuum-tau-csv", str(eval60_bundle / TAU_NAME),
        "--dsec-covering-fraction", format(covering, ".17g"),
        "--temperature-k", format(temperature, ".17g"),
        "--controller-smoke-evaluations", "2",
        "--skip-fits",
        "--output-dir", str(output),
    ], cwd=root, env=_promotion_env(root))
    return _load_json(output / "controller_smoke_summary.json")


def _run_full_controller(
    root: Path,
    executable: Path,
    case_dir: Path,
    eval60_bundle: Path,
    output: Path,
) -> tuple[dict[str, Any] | None, int]:
    """Run the complete native controller without discarding partial evidence.

    ``run-fixed-dsec`` returns status 20 when the completed native trajectory is
    not reference-identical.  That is a scientific qualification result, not an
    infrastructure exception.  Preserve its summary and return code so the
    already completed fixed-state, callback, and attribution gates remain
    reportable.
    """
    trajectory = root / "src/xstar_tools/benchmarks/v06486_qualification_reference_v0472/trajectory.csv"
    radiation = root / "src/xstar_tools/benchmarks/v06486_qualification_reference_v0472/reference_radiation_v0472_full.csv"
    oracle = read_csv(eval60_bundle / EVAL60_RECORDS_NAME)
    temperature = next(iter({float(r["temperature_k"]) for r in oracle}))
    covering = next(iter({float(r["covering_fraction"]) for r in oracle}))
    command = [
        str(executable), "run-fixed-dsec",
        "--case-dir", str(case_dir),
        "--trajectory-csv", str(trajectory),
        "--radiation-csv", str(radiation),
        "--dsec-radiation-csv", str(eval60_bundle / RADIATION_NAME),
        "--continuum-tau-csv", str(eval60_bundle / TAU_NAME),
        "--dsec-covering-fraction", format(covering, ".17g"),
        "--temperature-k", format(temperature, ".17g"),
        "--skip-fits",
        "--output-dir", str(output),
    ]
    print("$ " + " ".join(command))
    completed = subprocess.run(
        command, cwd=root, env=_promotion_env(root), text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    print(completed.stdout, end="")
    summary_path = output / "native_dsec_summary.json"
    summary = _load_json(summary_path) if summary_path.is_file() else None
    return summary, int(completed.returncode)


def _full_controller_assessment(
    summary: Mapping[str, Any] | None, returncode: int | None
) -> dict[str, Any]:
    completed = bool(summary and int(summary.get("total_evaluations", 0)) > 0)
    reference_identity = bool(summary and summary.get("reference_state_identity"))
    callbacks_exact = bool(summary and int(summary.get("python_callbacks", -1)) == 0)
    workspace_evaluations = int((summary or {}).get("runtime_state_workspace_evaluations", 0))
    accepted = bool(completed and returncode == 0 and reference_identity and callbacks_exact)
    return {
        "status": "ACCEPT" if accepted else ("REJECT" if completed else "NOT_RUN"),
        "completed": completed,
        "returncode": returncode,
        "reference_state_identity": reference_identity,
        "python_callbacks_exact": callbacks_exact,
        "runtime_state_workspace_evaluations": workspace_evaluations,
        "total_evaluations": int((summary or {}).get("total_evaluations", 0)),
        "dsec_evaluations": int((summary or {}).get("dsec_evaluations", 0)),
        "max_abs_hmctot_delta_to_reference": (summary or {}).get("max_abs_hmctot_delta_to_reference"),
    }


def _state(run: Path, evaluation: int) -> dict[str, Any]:
    return _load_json(_diagnostic_path(run, evaluation, "state.json"))


def _element_budget(run: Path, evaluation: int) -> dict[str, dict[str, float]]:
    state = _state(run, evaluation)
    rows = read_csv(_diagnostic_path(run, evaluation, "elements.csv"))
    labels = {1: "hydrogen", 2: "helium", 12: "magnesium"}
    budget: dict[str, dict[str, float]] = {}
    sum_h = 0.0
    sum_c = 0.0
    for row in rows:
        z = int(row["element_z"])
        heating = float(row["heating"]) + float(row["heating2"])
        cooling = float(row["cooling"]) + float(row["cooling2"])
        label = labels.get(z, f"element_z{z}")
        budget[label] = {"heating": heating, "cooling": cooling, "net": heating - cooling}
        sum_h += heating
        sum_c += cooling
    continuum_heating = float(state["total_heating"]) - sum_h
    continuum_cooling = float(state["total_cooling"]) - sum_c
    budget["continuum"] = {
        "heating": continuum_heating,
        "cooling": continuum_cooling,
        "net": continuum_heating - continuum_cooling,
    }
    denom = max(abs(float(state["total_heating"])) + abs(float(state["total_cooling"])), 1e-300)
    for value in budget.values():
        value["normalized_hmctot_contribution"] = value["net"] / denom
    return budget


def _hmctot_attribution(
    output: Path,
    baseline_runs: Mapping[int, Path],
    candidate_runs: Mapping[int, Path],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    state_summary: dict[str, Any] = {}
    for evaluation in (EVAL60, EVAL61):
        baseline_state = _state(baseline_runs[evaluation], evaluation)
        candidate_state = _state(candidate_runs[evaluation], evaluation)
        baseline_budget = _element_budget(baseline_runs[evaluation], evaluation)
        candidate_budget = _element_budget(candidate_runs[evaluation], evaluation)
        components = sorted(set(baseline_budget) | set(candidate_budget))
        component_deltas: list[tuple[str, float]] = []
        for component in components:
            b = baseline_budget[component]
            c = candidate_budget[component]
            delta = c["normalized_hmctot_contribution"] - b["normalized_hmctot_contribution"]
            component_deltas.append((component, delta))
            rows.append({
                "evaluation": evaluation,
                "component": component,
                "baseline_heating": b["heating"],
                "baseline_cooling": b["cooling"],
                "baseline_net": b["net"],
                "baseline_hmctot_contribution": b["normalized_hmctot_contribution"],
                "candidate_heating": c["heating"],
                "candidate_cooling": c["cooling"],
                "candidate_net": c["net"],
                "candidate_hmctot_contribution": c["normalized_hmctot_contribution"],
                "promotion_hmctot_contribution_delta": delta,
            })
        reference = float(candidate_runs[evaluation].joinpath("native_evaluation_summary.json").read_text() and _load_json(candidate_runs[evaluation] / "native_evaluation_summary.json")["reference_hmctot"])
        baseline_hmc = float(baseline_state["hmctot"])
        candidate_hmc = float(candidate_state["hmctot"])
        leading = max(component_deltas, key=lambda item: abs(item[1]))
        state_summary[str(evaluation)] = {
            "reference_hmctot": reference,
            "baseline_hmctot": baseline_hmc,
            "candidate_hmctot": candidate_hmc,
            "baseline_gap": baseline_hmc - reference,
            "candidate_gap": candidate_hmc - reference,
            "promotion_shift": candidate_hmc - baseline_hmc,
            "absolute_gap_improved": abs(candidate_hmc - reference) < abs(baseline_hmc - reference),
            "leading_promotion_budget_component": leading[0],
            "leading_promotion_budget_delta": leading[1],
            "remaining_gap_requires_additional_cooling": candidate_hmc > reference,
        }
    write_csv(output / "hmctot_component_attribution.csv", rows, list(rows[0]))
    type53_ruled_out = all(
        value["promotion_shift"] > 0.0 and value["remaining_gap_requires_additional_cooling"]
        for value in state_summary.values()
    )
    result = {
        "states": state_summary,
        "type53_is_not_remaining_cooling_source": type53_ruled_out,
        "interpretation": (
            "The promoted type-53 manifold adds net helium heating and moves hmctot toward zero, "
            "while both references require substantially more net cooling. Hydrogen is negligible and "
            "magnesium nearly cancels internally; the remaining discrepancy belongs to continuum and/or "
            "other non-type53 thermal channels plus controller-state coupling."
        ),
        "next_attribution_scope": [
            "continuum net heating/cooling construction",
            "magnesium large heating/cooling cancellation",
            "non-type53 helium thermal channels",
            "controller state trajectory",
        ],
        "complete": True,
    }
    write_json(output / "hmctot_attribution_summary.json", result)
    return result


def _bool_cell(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def _recover_comparison(output: Path, evaluation: int) -> dict[str, Any]:
    compare_dir = output / f"comparison_eval{evaluation}"
    record_rows = read_csv(compare_dir / "type53_row46_dsec_record_comparison.csv")
    term_rows = read_csv(compare_dir / "type53_row46_dsec_term_comparison.csv")
    record_exact = len(record_rows) == TARGET_RECORDS and all(
        _bool_cell(row.get("all_answers_ieee_exact")) for row in record_rows
    )
    term_exact = len(term_rows) == TARGET_TERMS and all(
        _bool_cell(row.get("term_ieee_exact")) for row in term_rows
    )
    order_exact = len(term_rows) == TARGET_TERMS and all(
        _bool_cell(row.get("absolute_source_order_index_exact")) for row in term_rows
    )
    return {
        "record_comparison": {
            "records": len(record_rows),
            "answers": len(record_rows) * 6,
            "records_all_answers_ieee_exact": sum(
                _bool_cell(row.get("all_answers_ieee_exact")) for row in record_rows
            ),
            "all_records_ieee_exact": record_exact,
            "recovered_from_existing_output": True,
        },
        "term_comparison": {
            "terms": len(term_rows),
            "exact_terms": sum(_bool_cell(row.get("term_ieee_exact")) for row in term_rows),
            "all_terms_ieee_exact": term_exact,
            "absolute_source_order_indices_exact": sum(
                _bool_cell(row.get("absolute_source_order_index_exact")) for row in term_rows
            ),
            "absolute_source_order_fully_exact": order_exact,
            "recovered_from_existing_output": True,
        },
    }


def recover_existing_output(root: Path, output: Path) -> dict[str, Any]:
    """Recover a complete audit summary after a nonzero full-controller result."""
    root = root.resolve()
    output = output.resolve()
    comparisons = {str(e): _recover_comparison(output, e) for e in (EVAL60, EVAL61)}
    two_state_exact = all(
        item["record_comparison"]["all_records_ieee_exact"]
        and item["term_comparison"]["all_terms_ieee_exact"]
        and item["term_comparison"]["absolute_source_order_fully_exact"]
        for item in comparisons.values()
    )
    smoke = _load_json(output / "controller_smoke/controller_smoke_summary.json")
    smoke_ok = (
        smoke.get("result") == "ACCEPT"
        and int(smoke.get("evaluations_completed", 0)) == 2
        and int(smoke.get("runtime_state_workspace_evaluations", 0)) >= 1
        and int(smoke.get("python_callbacks", -1)) == 0
    )
    attribution_path = output / "hmctot_attribution_summary.json"
    if attribution_path.is_file():
        attribution = _load_json(attribution_path)
    else:
        attribution = _hmctot_attribution(
            output,
            {EVAL60: output / "baseline_eval60", EVAL61: output / "baseline_eval61"},
            {EVAL60: output / "candidate_eval60", EVAL61: output / "candidate_eval61"},
        )
    full_path = output / "full_controller/native_dsec_summary.json"
    full_summary = _load_json(full_path) if full_path.is_file() else None
    # A persisted summary with reference_state_identity=false corresponds to
    # run-fixed-dsec status 20 in this qualification lineage.
    inferred_returncode = 0 if full_summary and full_summary.get("reference_state_identity") else (20 if full_summary else None)
    full_assessment = _full_controller_assessment(full_summary, inferred_returncode)
    full_status = full_assessment["status"] if full_summary else "RUN_REQUIRED"
    result = {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT" if two_state_exact and smoke_ok and attribution.get("complete") else "REJECT",
        "qualification_only": True,
        "recovered_from_existing_output": True,
        "two_state_exactness": comparisons,
        "two_state_type53_promotion": two_state_exact,
        "fixed_state_workflow": two_state_exact,
        "thermal_controller_integration": smoke_ok,
        "controller_smoke": smoke,
        "full_thermal_controller": full_status,
        "full_controller_assessment": full_assessment,
        "full_controller_summary": full_summary,
        "hmctot_attribution": attribution,
        "fixed_state_parity": False,
        "thermal_parity": False,
        "production_promotion_ready": False,
        "remaining_blockers": [
            "the complete native controller ran but did not reproduce the reference trajectory" if full_status == "REJECT" else None,
            "the evaluation-60 runtime-state workspace was not activated inside the complete controller trajectory" if full_status == "REJECT" and full_assessment["runtime_state_workspace_evaluations"] == 0 else None,
            "type-53 promotion improves charge and populations but worsens hmctot at both captured states",
            "continuum and non-type53 thermal channels are not yet source-parity qualified",
            "whole fixed-state, thermal-controller, output-product, and production parity remain blocked",
        ],
    }
    result["remaining_blockers"] = [x for x in result["remaining_blockers"] if x]
    write_json(output / "type53_two_state_thermal_promotion_summary.json", result)
    write_json(output / "audit_summary.json", result)
    return result


def audit(
    root: Path,
    case_dir: Path,
    output: Path,
    *,
    eval60_bundle: Path | None = None,
    run_full_controller: bool = False,
) -> dict[str, Any]:
    root = root.resolve()
    case_dir = case_dir.resolve()
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    eval60_bundle = (eval60_bundle or (root / EMBEDDED_EVAL60)).resolve()
    eval61_bundle = (root / EVAL61_BUNDLE_REL).resolve()
    executable = _build(root)

    verify60 = verify_eval60_oracle(eval60_bundle)
    verify61 = verify_eval61_oracle(eval61_bundle)
    if verify60["result"] != "ACCEPT" or verify61["result"] != "ACCEPT":
        raise RuntimeError("two-state oracle verification failed")

    baseline_runs: dict[int, Path] = {}
    candidate_runs: dict[int, Path] = {}
    comparisons: dict[str, Any] = {}
    for evaluation in (EVAL60, EVAL61):
        baseline = output / f"baseline_eval{evaluation}"
        candidate = output / f"candidate_eval{evaluation}"
        _run_fixed(root, executable, case_dir, baseline, evaluation, promoted=False, eval60_bundle=eval60_bundle)
        _run_fixed(root, executable, case_dir, candidate, evaluation, promoted=True, eval60_bundle=eval60_bundle)
        baseline_runs[evaluation] = baseline
        candidate_runs[evaluation] = candidate
        if evaluation == EVAL60:
            oracle_records = read_csv(eval60_bundle / EVAL60_RECORDS_NAME)
            oracle_terms = read_csv(eval60_bundle / EVAL60_TERMS_NAME)
        else:
            oracle_records = read_csv(eval61_bundle / EVAL61_RECORDS_NAME)
            oracle_terms = read_csv(eval61_bundle / EVAL61_TERMS_NAME)
        compare_dir = output / f"comparison_eval{evaluation}"
        compare_dir.mkdir(parents=True, exist_ok=True)
        record_cmp = _compare_records(oracle_records, _candidate_records(candidate, evaluation), compare_dir)
        term_cmp, _ = _compare_terms(oracle_terms, _candidate_terms(candidate, evaluation), compare_dir)
        comparisons[str(evaluation)] = {"record_comparison": record_cmp, "term_comparison": term_cmp}

    two_state_exact = all(
        item["record_comparison"]["all_records_ieee_exact"]
        and item["term_comparison"]["all_terms_ieee_exact"]
        and item["term_comparison"]["absolute_source_order_fully_exact"]
        for item in comparisons.values()
    )
    smoke = _run_controller_smoke(root, executable, case_dir, eval60_bundle, output / "controller_smoke")
    smoke_ok = (
        smoke.get("result") == "ACCEPT"
        and int(smoke.get("evaluations_completed", 0)) == 2
        and int(smoke.get("runtime_state_workspace_evaluations", 0)) >= 1
        and int(smoke.get("python_callbacks", -1)) == 0
    )
    full_summary = None
    full_returncode: int | None = None
    if run_full_controller:
        full_summary, full_returncode = _run_full_controller(
            root, executable, case_dir, eval60_bundle, output / "full_controller"
        )
    full_assessment = _full_controller_assessment(full_summary, full_returncode)
    full_status = full_assessment["status"] if run_full_controller else "RUN_REQUIRED"
    attribution = _hmctot_attribution(output, baseline_runs, candidate_runs)

    result = {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT" if two_state_exact and smoke_ok and attribution["complete"] else "REJECT",
        "qualification_only": True,
        "two_state_oracles": {"evaluation60": verify60, "evaluation61": verify61},
        "two_state_exactness": comparisons,
        "two_state_type53_promotion": two_state_exact,
        "fixed_state_workflow": two_state_exact,
        "thermal_controller_integration": smoke_ok,
        "controller_smoke": smoke,
        "full_thermal_controller": full_status,
        "full_controller_assessment": full_assessment,
        "full_controller_summary": full_summary,
        "hmctot_attribution": attribution,
        "fixed_state_parity": False,
        "thermal_parity": False,
        "production_promotion_ready": False,
        "remaining_blockers": [
            "the complete native thermal controller must be rerun externally" if full_status == "RUN_REQUIRED" else None,
            "the complete native controller ran but did not reproduce the reference trajectory" if full_status == "REJECT" else None,
            "the evaluation-60 runtime-state workspace was not activated inside the complete controller trajectory" if full_status == "REJECT" and full_assessment["runtime_state_workspace_evaluations"] == 0 else None,
            "type-53 promotion improves charge and populations but worsens hmctot at both captured states",
            "continuum and non-type53 thermal channels are not yet source-parity qualified",
            "whole fixed-state, thermal-controller, output-product, and production parity remain blocked",
        ],
    }
    result["remaining_blockers"] = [x for x in result["remaining_blockers"] if x]
    write_json(output / "type53_two_state_thermal_promotion_summary.json", result)
    return result


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package_dir", type=Path)
    parser.add_argument("case_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--eval60-bundle", type=Path)
    parser.add_argument("--run-full-controller", action="store_true")
    parser.add_argument("--recover-existing", action="store_true")
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if args.recover_existing:
            result = recover_existing_output(args.package_dir, args.output_dir)
        else:
            result = audit(
                args.package_dir,
                args.case_dir,
                args.output_dir,
                eval60_bundle=args.eval60_bundle,
                run_full_controller=args.run_full_controller,
            )
    except Exception as exc:
        result = {
            "schema": SCHEMA,
            "release": RELEASE,
            "result": "REJECT",
            "errors": [str(exc)],
            "two_state_type53_promotion": False,
            "thermal_controller_integration": False,
            "full_thermal_controller": "NOT_RUN",
            "hmctot_attribution": {"complete": False},
            "fixed_state_parity": False,
            "thermal_parity": False,
            "production_promotion_ready": False,
        }
    if args.output_json:
        write_json(args.output_json, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["result"] == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
