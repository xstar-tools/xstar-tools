"""Qualification-only source-faithful type-53 row-46 coupled replacement audit.

This release applies the complete 44-record, 176-term original-DSEC type-53
row-46 aliased manifold as one qualification unit.  At the captured
v0.6.47.2 evaluation-61 state, the immutable oracle is the exact answer and
matrix-term anchor.  The same C++ path also exposes a live non-anchor evaluator
for radiation, escape, population-dependent and thermal channels, but arbitrary-
state parity remains blocked because the fixed-state ABI does not yet carry the
complete original DSEC radiation/optical-depth workspace.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import struct
import sys
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from .helium_family_isolation import (
    RADIATION_SHA256,
    discover_reference,
    read_csv,
    run_command,
    sha256,
    state_metrics,
    write_csv,
    write_json,
)
from .helium_solve_response_decomposition import (
    _diagnostic_path,
    _effective_system,
    _matrix,
    _preliminary_comparison,
    _reference_populations,
    _residual_rows,
    _solve_rows,
    _verify_source_order_assembly,
)
from .type50_dsec_coupled_replacement_audit import _run as _run_type50_dsec_candidate
from .type50_manifold_replacement_audit import metric_improvements, reference_metrics
from .type53_row46_dsec_runtime_contract_audit import (
    BUNDLE,
    CONTRIBUTION_NAME,
    RECORDS_NAME,
    TERMS_NAME,
    ROLE_MAP,
    TARGET_ANSWERS,
    TARGET_DATA_TYPE,
    TARGET_EVALUATION,
    TARGET_FULL_ROW,
    TARGET_RECORDS,
    TARGET_TERMS,
    _candidate_records,
    _candidate_terms,
    _compare_records,
    _compare_terms,
    _contribution_comparison,
    _residual_metrics,
    verify_oracle,
)
from .type71_type99_replacement_audit import element_isolation

csv.field_size_limit(sys.maxsize)

RELEASE = "0.6.48.7.21.2"
SCHEMA = "xstar-tools-v0648716-type53-row46-source-faithful-replacement-audit-v1"
NONANCHOR_EVALUATION = 60


def _bits(value: str | float) -> bytes:
    return struct.pack(">d", float(value))


def _run_candidate(
    root: Path,
    executable: Path,
    lowered: Path,
    trajectory: Path,
    radiation: Path,
    output: Path,
    evaluation: int,
    *,
    captured_constraints: bool,
) -> None:
    if (output / "native_evaluation_summary.json").is_file() and _diagnostic_path(
        output, evaluation, "helium_solve_state.json"
    ).is_file():
        return
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root / "src") + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    env["XSTAR_QUALIFICATION_REPLACEMENT"] = "1"
    env["XSTAR_QUALIFICATION_TYPE53_ROW46_COUPLED_REPLACEMENT"] = "1"
    env["XSTAR_QUALIFICATION_SOLVE_RESPONSE"] = "1"
    env.pop("XSTAR_QUALIFICATION_TYPE50_MANIFOLD_ORACLE", None)
    if captured_constraints:
        env["XSTAR_QUALIFICATION_TYPE99_RECORD1695_ORACLE"] = "1"
        env["XSTAR_QUALIFICATION_TYPE50_DSEC_RUNTIME_ORACLE"] = "1"
    else:
        env.pop("XSTAR_QUALIFICATION_TYPE99_RECORD1695_ORACLE", None)
        env.pop("XSTAR_QUALIFICATION_TYPE50_DSEC_RUNTIME_ORACLE", None)
    run_command(
        [
            str(executable),
            "run-fixed-evaluation",
            "--case-dir",
            str(lowered),
            "--trajectory-csv",
            str(trajectory),
            "--evaluation",
            str(evaluation),
            "--radiation-csv",
            str(radiation),
            "--diagnostics-dir",
            str(output / "diagnostics"),
            "--output-dir",
            str(output),
        ],
        cwd=root,
        env=env,
    )


def _term_key(row: dict[str, str]) -> tuple[int, int, str]:
    return (
        int(row["contribution_source_position"]),
        int(row["record"]),
        ROLE_MAP[str(row["role"])],
    )


def _target_keys(oracle_records: list[dict[str, str]]) -> set[tuple[int, int]]:
    return {(int(row["source_position"]), int(row["record"])) for row in oracle_records}


def _isolation(
    baseline_records: list[dict[str, str]],
    candidate_records: list[dict[str, str]],
    baseline_terms: list[dict[str, str]],
    candidate_terms: list[dict[str, str]],
    selected_records: set[tuple[int, int]],
) -> dict[str, Any]:
    base_records = {
        (int(row["source_position"]), int(row["record"])): row for row in baseline_records
    }
    cand_records = {
        (int(row["source_position"]), int(row["record"])): row for row in candidate_records
    }
    compared_records = 0
    exact_record_scalars = 0
    nonexact_record_scalars = 0
    for key, source in base_records.items():
        if key in selected_records:
            continue
        target = cand_records.get(key)
        if target is None:
            raise ValueError(f"candidate is missing non-target record {key}")
        compared_records += 1
        for i in range(1, 7):
            if _bits(source[f"ans{i}"]) == _bits(target[f"ans{i}"]):
                exact_record_scalars += 1
            else:
                nonexact_record_scalars += 1

    def term_map(rows: list[dict[str, str]]) -> dict[tuple[int, int, str], dict[str, str]]:
        return {_term_key(row): row for row in rows}

    base_terms = term_map(baseline_terms)
    cand_terms = term_map(candidate_terms)
    compared_terms = 0
    exact_term_scalars = 0
    nonexact_term_scalars = 0
    for key, source in base_terms.items():
        if key[:2] in selected_records:
            continue
        target = cand_terms.get(key)
        if target is None:
            raise ValueError(f"candidate is missing non-target term {key}")
        compared_terms += 1
        for field in ("aj1", "aj2", "cj", "cj2"):
            if _bits(source[field]) == _bits(target[field]):
                exact_term_scalars += 1
            else:
                nonexact_term_scalars += 1
    return {
        "non_target_records_compared": compared_records,
        "non_target_record_scalars_exact": exact_record_scalars,
        "non_target_record_scalars_nonexact": nonexact_record_scalars,
        "non_target_terms_compared": compared_terms,
        "non_target_term_scalars_exact": exact_term_scalars,
        "non_target_term_scalars_nonexact": nonexact_term_scalars,
        "all_non_target_record_answers_ieee_exact": nonexact_record_scalars == 0,
        "all_non_target_term_scalars_ieee_exact": nonexact_term_scalars == 0,
    }


def _source_order_assembly(terms: list[dict[str, str]], dense: np.ndarray) -> dict[str, Any]:
    ledger = [
        {
            **row,
            "source_order_index": int(row["source_order_index"]),
            "compact_row": int(row["compact_row"]),
            "compact_column": int(row["compact_column"]),
            "aj1": float(row["aj1"]),
        }
        for row in terms
    ]
    return _verify_source_order_assembly(ledger, dense)


def _matrix_metrics(dense: np.ndarray, normalization_index: int) -> dict[str, Any]:
    effective, _ = _effective_system(dense, normalization_index)
    return {
        "matrix_rank": int(np.linalg.matrix_rank(effective)),
        "condition_number_2": float(np.linalg.cond(effective)),
    }


def _nonanchor_validation(
    run: Path,
    evaluation: int,
    oracle_terms: list[dict[str, str]],
) -> dict[str, Any]:
    records = read_csv(_diagnostic_path(run, evaluation, "records.csv"))
    selected = [
        row
        for row in records
        if int(row["element_z"]) == 2
        and int(row["data_type"]) == TARGET_DATA_TYPE
        and int(row.get("type53_row46_contract") or 0) == 1
    ]
    finite_records = sum(
        all(math.isfinite(float(row[f"ans{i}"])) for i in range(1, 7))
        and all(
            math.isfinite(float(row[field]))
            for field in ("type53_tau_in", "type53_tau_out", "type53_ptmp1", "type53_ptmp2")
        )
        for row in selected
    )
    terms = _candidate_terms(run, evaluation)
    oracle_order = {
        (int(row["source_position"]), int(row["record"]), str(row["role"])):
        int(row["source_order_index"])
        for row in oracle_terms
    }
    selected_terms = [row for row in terms if _term_key(row) in oracle_order]
    exact_positions = sum(
        int(row["source_order_index"]) == oracle_order[_term_key(row)] for row in selected_terms
    )
    return {
        "evaluation_ordinal": evaluation,
        "records": len(selected),
        "captured_state_anchor_records": sum(
            int(row.get("type53_captured_state_anchor") or 0) for row in selected
        ),
        "source_shadow_valid_records": sum(
            int(row.get("type53_shadow_valid") or 0) for row in selected
        ),
        "finite_runtime_contract_records": finite_records,
        "terms": len(selected_terms),
        "absolute_source_order_positions_exact": exact_positions,
        "live_branch_executed": (
            len(selected) == TARGET_RECORDS
            and finite_records == TARGET_RECORDS
            and sum(int(row.get("type53_captured_state_anchor") or 0) for row in selected) == 0
            and len(selected_terms) == TARGET_TERMS
            and exact_positions == TARGET_TERMS
        ),
        "parity_qualified": False,
    }


def audit(
    package_dir: Path,
    lowered_program: Path,
    output_dir: Path,
    *,
    evaluation: int = TARGET_EVALUATION,
    radiation_csv: Path | None = None,
) -> dict[str, Any]:
    if evaluation != TARGET_EVALUATION:
        raise ValueError("type-53 row-46 replacement audit is restricted to evaluation 61")
    root = package_dir.resolve()
    lowered = lowered_program.resolve()
    output = output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    bundle = (root / BUNDLE).resolve()

    oracle_verification = verify_oracle(bundle)
    if oracle_verification["result"] != "ACCEPT":
        raise ValueError(f"type-53 row-46 oracle rejected: {oracle_verification['errors']}")
    oracle_records = read_csv(bundle / RECORDS_NAME)
    oracle_terms = read_csv(bundle / TERMS_NAME)
    contribution_rows = read_csv(bundle / CONTRIBUTION_NAME)
    selected_records = _target_keys(oracle_records)

    trajectory = discover_reference(root, "trajectory.csv")
    radiation = radiation_csv.resolve() if radiation_csv else discover_reference(
        root, "reference_radiation_v0472_full.csv"
    )
    if sha256(radiation) != RADIATION_SHA256:
        raise ValueError("qualification radiation hash mismatch")
    executable = root / "src/xstar_tools/xstar/cpp/xstar_cpp"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root / "src")
    run_command(["make", "-C", str(root / "src/xstar_tools/xstar/cpp"), "-j2"], cwd=root, env=env)

    baseline = output / "baseline_exact_53_71_99_actual_dsec_type50"
    candidate = output / "candidate_type53_row46_source_faithful"
    nonanchor = output / "nonanchor_type53_row46_live_law"
    _run_type50_dsec_candidate(root, executable, lowered, trajectory, radiation, baseline, evaluation, True)
    _run_candidate(
        root, executable, lowered, trajectory, radiation, candidate, evaluation,
        captured_constraints=True,
    )
    _run_candidate(
        root, executable, lowered, trajectory, radiation, nonanchor, NONANCHOR_EVALUATION,
        captured_constraints=False,
    )

    baseline_records = _candidate_records(baseline, evaluation)
    candidate_records = _candidate_records(candidate, evaluation)
    baseline_terms = _candidate_terms(baseline, evaluation)
    candidate_terms = _candidate_terms(candidate, evaluation)

    record_exactness = _compare_records(oracle_records, candidate_records, output)
    term_exactness, _ = _compare_terms(oracle_terms, candidate_terms, output)
    contribution_exactness = _contribution_comparison(
        oracle_terms, candidate_terms, contribution_rows, output
    )
    isolation = _isolation(
        baseline_records, candidate_records, baseline_terms, candidate_terms, selected_records
    )

    baseline_rows = _solve_rows(baseline, evaluation)
    candidate_rows = _solve_rows(candidate, evaluation)
    baseline_dense, baseline_heat, baseline_heat2, baseline_rhs = _matrix(baseline, evaluation)
    candidate_dense, candidate_heat, candidate_heat2, candidate_rhs = _matrix(candidate, evaluation)
    normalization_index = next(
        index for index, row in enumerate(candidate_rows) if int(row["is_normalization_row"]) == 1
    )
    reference = _reference_populations(root, evaluation, candidate_rows)
    baseline_solution = np.asarray(
        [float(row["final_population"]) for row in baseline_rows], dtype=np.float64
    )
    candidate_solution = np.asarray(
        [float(row["final_population"]) for row in candidate_rows], dtype=np.float64
    )

    baseline_l1, baseline_linf, baseline_residual = _residual_metrics(
        baseline_dense, reference, normalization_index
    )
    candidate_l1, candidate_linf, candidate_residual = _residual_metrics(
        candidate_dense, reference, normalization_index
    )
    reduction = baseline_l1 - candidate_l1
    fraction = reduction / max(baseline_l1, 1.0e-300)
    row46_before = float(baseline_residual[TARGET_FULL_ROW - 1])
    row46_after = float(candidate_residual[TARGET_FULL_ROW - 1])
    residual_rows = _residual_rows(
        "source_faithful_type53_row46_candidate",
        candidate_rows,
        candidate_dense,
        reference,
        normalization_index,
        "v0472_reference",
    )
    write_csv(
        output / "type53_row46_candidate_reference_residual_rows.csv",
        residual_rows,
        list(residual_rows[0]),
    )

    population_rows: list[dict[str, Any]] = []
    for index, row in enumerate(candidate_rows):
        population_rows.append({
            "compact_row": int(row["compact_row"]),
            "full_row": int(row["full_row"]),
            "is_normalization_row": int(row["is_normalization_row"]),
            "baseline_solution": float(baseline_solution[index]),
            "candidate_solution": float(candidate_solution[index]),
            "reference_population": float(reference[index]),
            "candidate_minus_baseline": float(candidate_solution[index] - baseline_solution[index]),
            "baseline_absolute_reference_error": abs(float(baseline_solution[index] - reference[index])),
            "candidate_absolute_reference_error": abs(float(candidate_solution[index] - reference[index])),
        })
    write_csv(
        output / "type53_row46_candidate_solution_response.csv",
        population_rows,
        list(population_rows[0]),
    )

    element_scope = element_isolation(baseline, candidate, evaluation)
    preliminary = _preliminary_comparison(baseline, candidate, evaluation)
    baseline_state = state_metrics(baseline, evaluation)
    candidate_state = state_metrics(candidate, evaluation)
    reference_state = reference_metrics(root, evaluation)
    improvements, all_metrics_improved = metric_improvements(
        baseline_state, candidate_state, reference_state
    )
    write_csv(
        output / "type53_row46_fixed_state_metric_improvements.csv",
        improvements,
        list(improvements[0]),
    )

    baseline_assembly = _source_order_assembly(baseline_terms, baseline_dense)
    candidate_assembly = _source_order_assembly(candidate_terms, candidate_dense)
    baseline_matrix_metrics = _matrix_metrics(baseline_dense, normalization_index)
    candidate_matrix_metrics = _matrix_metrics(candidate_dense, normalization_index)
    nonanchor_validation = _nonanchor_validation(nonanchor, NONANCHOR_EVALUATION, oracle_terms)

    candidate_solve_state = json.loads(
        _diagnostic_path(candidate, evaluation, "helium_solve_state.json").read_text(encoding="utf-8")
    )
    captured_contract_rows = [
        row
        for row in candidate_records
        if int(row["element_z"]) == 2
        and int(row["data_type"]) == TARGET_DATA_TYPE
        and int(row.get("type53_row46_contract") or 0) == 1
    ]
    contract_diagnostics = {
        "records": len(captured_contract_rows),
        "captured_state_anchor_records": sum(
            int(row.get("type53_captured_state_anchor") or 0) for row in captured_contract_rows
        ),
        "source_shadow_valid_records": sum(
            int(row.get("type53_shadow_valid") or 0) for row in captured_contract_rows
        ),
        "gate_recorded_in_solve_state": candidate_solve_state.get(
            "type53_row46_coupled_replacement"
        ) is True,
    }

    answers_exact = record_exactness["all_records_ieee_exact"]
    terms_exact = term_exactness["all_terms_ieee_exact"]
    thermal_exact = (
        term_exactness["exact_scalar_counts"]["cj"] == TARGET_TERMS
        and term_exactness["exact_scalar_counts"]["cj2"] == TARGET_TERMS
    )
    order_exact = (
        term_exactness["relative_source_order_exact"]
        and term_exactness["absolute_source_order_fully_exact"]
    )
    materially_reduced = (
        fraction >= 0.95
        and abs(row46_after) < abs(row46_before) * 1.0e-3
        and float(np.sum(np.abs(candidate_solution - reference)))
        < float(np.sum(np.abs(baseline_solution - reference))) * 1.0e-3
    )
    captured_contract_exact = (
        contract_diagnostics["records"] == TARGET_RECORDS
        and contract_diagnostics["captured_state_anchor_records"] == TARGET_RECORDS
        and contract_diagnostics["source_shadow_valid_records"] == TARGET_RECORDS
        and contract_diagnostics["gate_recorded_in_solve_state"]
    )
    accepted = all((
        oracle_verification["result"] == "ACCEPT",
        answers_exact,
        terms_exact,
        thermal_exact,
        order_exact,
        contribution_exactness["native_dsec_delta_l1"] == 0.0,
        contribution_exactness["native_nonzero_delta_columns"] == 0,
        isolation["all_non_target_record_answers_ieee_exact"],
        isolation["all_non_target_term_scalars_ieee_exact"],
        element_scope["max_h_mg_absolute_delta"] == 0.0,
        element_scope["helium_final_normalization_error"] == 0.0,
        len(candidate_rows) == 78,
        baseline_assembly["matrix_ieee_exact"],
        candidate_assembly["matrix_ieee_exact"],
        np.array_equal(baseline_rhs, candidate_rhs),
        materially_reduced,
        captured_contract_exact,
        nonanchor_validation["live_branch_executed"],
    ))

    summary: dict[str, Any] = {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT" if accepted else "REJECT",
        "evaluation_ordinal": evaluation,
        "qualification_only": True,
        "oracle_verification": oracle_verification,
        "manifold_inventory": {
            "records": TARGET_RECORDS,
            "answers": TARGET_ANSWERS,
            "matrix_terms": TARGET_TERMS,
            "data_type": TARGET_DATA_TYPE,
            "target_full_row": TARGET_FULL_ROW,
        },
        "candidate_answer_exactness": record_exactness,
        "candidate_matrix_term_exactness": term_exactness,
        "candidate_thermal_channel_exactness": {
            "cj_exact": term_exactness["exact_scalar_counts"]["cj"],
            "cj2_exact": term_exactness["exact_scalar_counts"]["cj2"],
            "all_thermal_channels_ieee_exact": thermal_exact,
        },
        "candidate_source_order_contract": {
            "relative_source_order_exact": term_exactness["relative_source_order_exact"],
            "absolute_source_order_exact": term_exactness["absolute_source_order_fully_exact"],
            "source_contribution": contribution_exactness,
            "full_matrix_source_assembly": candidate_assembly,
        },
        "captured_state_contract_diagnostics": contract_diagnostics,
        "arbitrary_state_interface": nonanchor_validation,
        "non_target_isolation": isolation,
        "element_isolation": element_scope,
        "preliminary_and_active_stage_response": {
            **preliminary,
            "interpretation": "expected coupled response: type-53 contributes to preliminary helium ion balance before the detailed solve",
        },
        "source_order_assembly": {
            "baseline": baseline_assembly,
            "candidate": candidate_assembly,
        },
        "linear_system": {
            "baseline": {
                **baseline_matrix_metrics,
                "reference_residual_l1": baseline_l1,
                "reference_residual_linf": baseline_linf,
            },
            "candidate": {
                **candidate_matrix_metrics,
                "reference_residual_l1": candidate_l1,
                "reference_residual_linf": candidate_linf,
            },
            "delta": {
                "reference_residual_l1_reduction": reduction,
                "reference_residual_fraction_reduced": fraction,
                "row46_residual_before": row46_before,
                "row46_residual_after": row46_after,
                "row46_absolute_reduction": abs(row46_before) - abs(row46_after),
                "dense_matrix_nonzero_entries": int(np.count_nonzero(candidate_dense - baseline_dense)),
                "dense_matrix_delta_l1": float(np.sum(np.abs(candidate_dense - baseline_dense))),
                "dense_matrix_delta_linf": float(np.max(np.abs(candidate_dense - baseline_dense))),
                "heating_matrix_delta_l1": float(np.sum(np.abs(candidate_heat - baseline_heat))),
                "heating2_matrix_delta_l1": float(np.sum(np.abs(candidate_heat2 - baseline_heat2))),
                "rhs_ieee_exact": bool(np.array_equal(baseline_rhs, candidate_rhs)),
                "materially_reduced": materially_reduced,
            },
        },
        "solve_response": {
            "baseline_reference_error_l1": float(np.sum(np.abs(baseline_solution - reference))),
            "candidate_reference_error_l1": float(np.sum(np.abs(candidate_solution - reference))),
            "solution_delta_l1": float(np.sum(np.abs(candidate_solution - baseline_solution))),
            "solution_delta_linf": float(np.max(np.abs(candidate_solution - baseline_solution))),
            "baseline_normalization_error": abs(float(np.sum(baseline_solution)) - 1.0),
            "candidate_normalization_error": abs(float(np.sum(candidate_solution)) - 1.0),
        },
        "baseline_state": baseline_state,
        "candidate_state": candidate_state,
        "reference_state": reference_state,
        "whole_fixed_state_metric_improvements": improvements,
        "all_whole_fixed_state_metrics_improved": all_metrics_improved,
        "captured_state_replacement_exact": answers_exact and terms_exact and thermal_exact and order_exact,
        "arbitrary_state_contract_interface_ready": nonanchor_validation["live_branch_executed"],
        "arbitrary_state_parity_validated": False,
        "type53_general_state_promotion_ready": False,
        "fixed_state_parity": False,
        "thermal_parity": False,
        "production_promotion_ready": False,
        "remaining_blockers": [
            "the exact original-DSEC type-53 oracle is frozen only at evaluation 61",
            "the non-anchor live law has no original-DSEC arbitrary-state parity oracle",
            "the fixed-state ABI does not carry the complete original DSEC bremsa and continuum optical-depth arrays",
            "whole fixed-state parity remains incomplete",
            "thermal, controller, output-product, and production parity remain blocked",
        ],
    }
    write_json(output / "summary.json", summary)
    write_json(output / "type53_row46_replacement_exactness.json", {
        "oracle_verification": oracle_verification,
        "answer_exactness": record_exactness,
        "matrix_term_exactness": term_exactness,
        "thermal_channel_exactness": summary["candidate_thermal_channel_exactness"],
        "source_order_contract": summary["candidate_source_order_contract"],
    })
    write_json(output / "type53_row46_replacement_response.json", {
        "linear_system": summary["linear_system"],
        "solve_response": summary["solve_response"],
        "baseline_state": baseline_state,
        "candidate_state": candidate_state,
        "reference_state": reference_state,
    })
    print(json.dumps(summary, indent=2, sort_keys=True))
    return summary


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package_dir", type=Path)
    parser.add_argument("lowered_program", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--evaluation", type=int, default=TARGET_EVALUATION)
    parser.add_argument("--radiation-csv", type=Path)
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        result = audit(
            args.package_dir,
            args.lowered_program,
            args.output_dir,
            evaluation=args.evaluation,
            radiation_csv=args.radiation_csv,
        )
    except Exception as exc:
        print(f"type-53 row-46 source-faithful replacement audit failed: {exc}")
        return 2
    if args.output_json:
        write_json(args.output_json, result)
    return 0 if result["result"] == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
