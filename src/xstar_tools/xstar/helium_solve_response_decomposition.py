"""Source-ordered helium solve-response decomposition for xstar_tools v0.6.48.7.11.

This qualification workflow holds the accepted evaluation-61 helium contracts
fixed, exports the actual native helium matrix/RHS/solution in source order,
and evaluates the v0.6.47.2 reference population vector in the native system.
It ranks only remaining, unqualified scopes.  It never promotes a record or
family from residual magnitude alone.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np

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
from .helium_matrix_residual_decomposition import verify_type71_invariant, verify_type99_invariant
from .type50_manifold_replacement_audit import (
    REFERENCE_DIR,
    TYPE50_BUNDLE,
    TYPE50_ORACLE_NAME,
    TYPE50_ORACLE_SHA256,
    compare_type50,
)
from .type71_type99_replacement_audit import (
    TYPE71_BUNDLE,
    TYPE71_ORACLE_SHA256,
    TYPE99_BUNDLE,
    TYPE99_ORACLE_SHA256,
    element_isolation,
)
from .v0472_type71_runtime_capture import ORACLE_NAME as TYPE71_ORACLE_NAME, verify as verify_type71
from .v0472_type99_runtime_capture import ORACLE_NAME as TYPE99_ORACLE_NAME, verify as verify_type99

RELEASE = "0.6.48.7.11"
SCHEMA = "xstar-tools-v0648711-helium-solve-response-decomposition-v1"
REFERENCE_LEVELS = REFERENCE_DIR / "final_level_populations.csv"
KEY_FULL_ROWS = tuple(range(46, 79))
ROW_BLOCKS = (
    ("he1_rows_1_45", 1, 45),
    ("he2_low_rows_46_54", 46, 54),
    ("he2_mid_rows_55_70", 55, 70),
    ("he2_high_rows_71_77", 71, 77),
    ("continuum_normalization_row_78", 78, 78),
)


def _oracle_rows(path: Path, name: str) -> list[dict[str, str]]:
    rows = read_csv(path / name)
    if not rows:
        raise ValueError(f"empty oracle: {path / name}")
    return rows


def _diagnostic_path(run: Path, evaluation: int, suffix: str) -> Path:
    return run / "diagnostics" / f"evaluation_{evaluation:04d}_{suffix}"


def _run_fixed(
    root: Path,
    executable: Path,
    lowered: Path,
    trajectory: Path,
    radiation: Path,
    output: Path,
    evaluation: int,
    *,
    exact_type50: bool,
) -> None:
    if (output / "native_evaluation_summary.json").is_file() and _diagnostic_path(
        output, evaluation, "helium_solve_state.json"
    ).is_file():
        return
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root / "src") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["XSTAR_QUALIFICATION_REPLACEMENT"] = "1"
    env["XSTAR_QUALIFICATION_TYPE99_RECORD1695_ORACLE"] = "1"
    env["XSTAR_QUALIFICATION_SOLVE_RESPONSE"] = "1"
    if exact_type50:
        env["XSTAR_QUALIFICATION_TYPE50_MANIFOLD_ORACLE"] = "1"
    else:
        env.pop("XSTAR_QUALIFICATION_TYPE50_MANIFOLD_ORACLE", None)
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


def _matrix(run: Path, evaluation: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    rows = read_csv(_diagnostic_path(run, evaluation, "helium_solve_matrix.csv"))
    state = json.loads(_diagnostic_path(run, evaluation, "helium_solve_state.json").read_text())
    n = int(state["compact_row_count"])
    dense = np.zeros((n, n), dtype=np.float64)
    heat = np.zeros((n, n), dtype=np.float64)
    heat2 = np.zeros((n, n), dtype=np.float64)
    for row in rows:
        i = int(row["compact_row"]) - 1
        j = int(row["compact_column"]) - 1
        dense[i, j] = float(row["dense_value"])
        heat[i, j] = float(row["heating_value"])
        heat2[i, j] = float(row["heating2_value"])
    solve_rows = read_csv(_diagnostic_path(run, evaluation, "helium_solve_rows.csv"))
    rhs = np.asarray([float(r["rhs"]) for r in solve_rows], dtype=np.float64)
    return dense, heat, heat2, rhs


def _solve_rows(run: Path, evaluation: int) -> list[dict[str, str]]:
    return read_csv(_diagnostic_path(run, evaluation, "helium_solve_rows.csv"))


def _effective_system(dense: np.ndarray, normalization_index: int) -> tuple[np.ndarray, np.ndarray]:
    matrix = dense.copy()
    rhs = np.zeros(matrix.shape[0], dtype=np.float64)
    matrix[normalization_index, :] = 1.0
    rhs[normalization_index] = 1.0
    return matrix, rhs


def _pivot_sequence(matrix: np.ndarray) -> list[int]:
    work = matrix.copy()
    n = work.shape[0]
    pivots: list[int] = []
    for col in range(n):
        pivot = col + int(np.argmax(np.abs(work[col:, col])))
        pivots.append(pivot + 1)
        if pivot != col:
            work[[col, pivot], :] = work[[pivot, col], :]
        value = work[col, col]
        if value == 0.0 or not math.isfinite(float(value)):
            continue
        for row in range(col + 1, n):
            factor = work[row, col] / value
            if factor != 0.0:
                work[row, col:] -= factor * work[col, col:]
    return pivots


def _reference_populations(root: Path, evaluation: int, solve_rows: list[dict[str, str]]) -> np.ndarray:
    raw = read_csv(root / REFERENCE_LEVELS)
    mapped = [
        row
        for row in raw
        if row.get("global_population_row", "").strip()
        and int(row["reference_evaluation_ordinal"]) == evaluation
        and int(row["element_z"]) == 2
        and row.get("mapping_status") == "mapped"
    ]
    mapped.sort(key=lambda row: int(row["global_population_row"]))
    if not mapped:
        raise ValueError("reference helium level-population vector is unavailable")
    first_global = int(mapped[0]["global_population_row"])
    by_full_row = {
        int(row["global_population_row"]) - first_global + 1: float(row["reference_population"])
        for row in mapped
    }
    result = []
    for row in solve_rows:
        full = int(row["full_row"])
        if full not in by_full_row:
            raise ValueError(f"reference helium population missing for full row {full}")
        result.append(by_full_row[full])
    vector = np.asarray(result, dtype=np.float64)
    if abs(float(np.sum(vector)) - 1.0) > 5.0e-7:
        raise ValueError(f"reference helium population normalization is unexpected: {np.sum(vector)!r}")
    return vector


def _scope_keys(root: Path) -> dict[str, set[tuple[int, int]]]:
    type53 = set(load_oracle(root / "src/xstar_tools/benchmarks/v064873_type53_runtime_oracle_v0472"))
    type71 = {
        (int(row["source_position"]), int(row["record"]))
        for row in _oracle_rows(root / TYPE71_BUNDLE, TYPE71_ORACLE_NAME)
    }
    type99 = {
        (int(row["source_position"]), int(row["record"]))
        for row in _oracle_rows(root / TYPE99_BUNDLE, TYPE99_ORACLE_NAME)
    }
    type50 = {
        (int(row["source_position"]), int(row["record"]))
        for row in _oracle_rows(root / TYPE50_BUNDLE, TYPE50_ORACLE_NAME)
    }
    return {
        "exact_type53_heii": type53,
        "exact_type71_row77": type71,
        "exact_type99_record1695": type99,
        "exact_type50_rows46_54": type50,
    }


def _term_scope(row: dict[str, str], exact: dict[str, set[tuple[int, int]]]) -> str:
    key = (int(row["contribution_source_position"]), int(row["record"]))
    data_type = int(row["data_type"])
    for name, keys in exact.items():
        if key in keys:
            return name
    return f"remaining_type_{data_type}"


def _residual_rows(
    variant: str,
    solve_rows: list[dict[str, str]],
    dense: np.ndarray,
    vector: np.ndarray,
    normalization_index: int,
    vector_label: str,
) -> list[dict[str, Any]]:
    raw = dense @ vector
    effective = raw.copy()
    effective[normalization_index] = float(np.sum(vector) - 1.0)
    scale = np.sum(np.abs(dense) * np.abs(vector[np.newaxis, :]), axis=1)
    scale[normalization_index] = float(np.sum(np.abs(vector)))
    rows: list[dict[str, Any]] = []
    for index, metadata in enumerate(solve_rows):
        rows.append(
            {
                "variant": variant,
                "population_vector": vector_label,
                "compact_row": index + 1,
                "full_row": int(metadata["full_row"]),
                "ion_charge": int(metadata["ion_charge"]),
                "is_normalization_row": int(metadata["is_normalization_row"]),
                "population": float(vector[index]),
                "raw_matrix_residual": float(raw[index]),
                "effective_solver_residual": float(effective[index]),
                "row_scale": float(scale[index]),
                "relative_effective_residual": float(abs(effective[index]) / max(scale[index], 1.0e-300)),
            }
        )
    return rows


def _term_ledger(
    run: Path,
    evaluation: int,
    reference: np.ndarray,
    exact: dict[str, set[tuple[int, int]]],
) -> list[dict[str, Any]]:
    rows = read_csv(_diagnostic_path(run, evaluation, "helium_source_order_terms.csv"))
    result: list[dict[str, Any]] = []
    previous = -1
    for row in rows:
        order = int(row["source_order_index"])
        if order <= previous:
            raise ValueError("helium term stream is not strictly source ordered")
        previous = order
        col = int(row["compact_column"]) - 1
        contribution = float(row["aj1"]) * float(reference[col])
        item: dict[str, Any] = dict(row)
        item["scope"] = _term_scope(row, exact)
        item["reference_column_population"] = float(reference[col])
        item["reference_residual_contribution"] = contribution
        result.append(item)
    return result


def _aggregate_residual(
    terms: list[dict[str, Any]],
    residual_rows: list[dict[str, Any]],
    normalization_full_row: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    total_by_row = {
        int(row["full_row"]): float(row["effective_solver_residual"])
        for row in residual_rows
        if int(row["full_row"]) != normalization_full_row
    }
    by_scope_row: dict[tuple[str, int], float] = defaultdict(float)
    by_source_row: dict[tuple[str, int, int, int, int], float] = defaultdict(float)
    for term in terms:
        full_row = int(term["full_row"])
        if full_row == normalization_full_row:
            continue
        scope = str(term["scope"])
        value = float(term["reference_residual_contribution"])
        by_scope_row[(scope, full_row)] += value
        by_source_row[(scope, int(term["data_type"]), int(term["contribution_source_position"]), int(term["record"]), full_row)] += value

    scope_rows = [
        {"scope": scope, "full_row": full_row, "net_reference_residual_contribution": value}
        for (scope, full_row), value in sorted(by_scope_row.items())
    ]
    source_rows = [
        {
            "scope": scope,
            "data_type": data_type,
            "source_position": source_position,
            "record": record,
            "full_row": full_row,
            "net_reference_residual_contribution": value,
        }
        for (scope, data_type, source_position, record, full_row), value in sorted(by_source_row.items())
    ]

    base_l1 = sum(abs(value) for value in total_by_row.values())
    scopes = sorted({scope for scope, _ in by_scope_row})
    ranking: list[dict[str, Any]] = []
    for scope in scopes:
        scope_by_row = {row: by_scope_row.get((scope, row), 0.0) for row in total_by_row}
        without_l1 = sum(abs(total_by_row[row] - scope_by_row[row]) for row in total_by_row)
        values = list(scope_by_row.values())
        ranking.append(
            {
                "scope": scope,
                "qualified_exact_scope": str(scope.startswith("exact_")).lower(),
                "reference_residual_l1": base_l1,
                "residual_l1_without_scope": without_l1,
                "reference_residual_error_reduction_if_removed": base_l1 - without_l1,
                "scope_net_l1": sum(abs(value) for value in values),
                "scope_signed_sum": sum(values),
                "scope_max_abs_row_contribution": max((abs(value) for value in values), default=0.0),
            }
        )
    ranking.sort(key=lambda row: float(row["reference_residual_error_reduction_if_removed"]), reverse=True)
    return scope_rows, source_rows, ranking


def _row_blocks(residual_rows: list[dict[str, Any]], scope_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    total = {int(row["full_row"]): float(row["effective_solver_residual"]) for row in residual_rows}
    result: list[dict[str, Any]] = []
    for name, first, last in ROW_BLOCKS:
        selected = [total.get(row, 0.0) for row in range(first, last + 1)]
        result.append(
            {
                "row_block": name,
                "first_full_row": first,
                "last_full_row": last,
                "row_count": last - first + 1,
                "reference_residual_l1": sum(abs(value) for value in selected),
                "reference_residual_linf": max((abs(value) for value in selected), default=0.0),
                "reference_residual_signed_sum": sum(selected),
            }
        )
    result.sort(key=lambda row: float(row["reference_residual_l1"]), reverse=True)
    return result


def _matrix_delta_rows(
    baseline: np.ndarray,
    candidate: np.ndarray,
    baseline_heat: np.ndarray,
    candidate_heat: np.ndarray,
    baseline_heat2: np.ndarray,
    candidate_heat2: np.ndarray,
    solve_rows: list[dict[str, str]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for i, row_meta in enumerate(solve_rows):
        for j, col_meta in enumerate(solve_rows):
            delta = float(candidate[i, j] - baseline[i, j])
            delta_h = float(candidate_heat[i, j] - baseline_heat[i, j])
            delta_h2 = float(candidate_heat2[i, j] - baseline_heat2[i, j])
            if delta == 0.0 and delta_h == 0.0 and delta_h2 == 0.0:
                continue
            result.append(
                {
                    "compact_row": i + 1,
                    "compact_column": j + 1,
                    "full_row": int(row_meta["full_row"]),
                    "full_column": int(col_meta["full_row"]),
                    "baseline_dense": float(baseline[i, j]),
                    "candidate_dense": float(candidate[i, j]),
                    "delta_dense": delta,
                    "baseline_heating": float(baseline_heat[i, j]),
                    "candidate_heating": float(candidate_heat[i, j]),
                    "delta_heating": delta_h,
                    "baseline_heating2": float(baseline_heat2[i, j]),
                    "candidate_heating2": float(candidate_heat2[i, j]),
                    "delta_heating2": delta_h2,
                }
            )
    result.sort(key=lambda row: max(abs(float(row["delta_dense"])), abs(float(row["delta_heating"])), abs(float(row["delta_heating2"]))), reverse=True)
    return result


def _population_delta_rows(
    baseline_rows: list[dict[str, str]], candidate_rows: list[dict[str, str]], reference: np.ndarray
) -> list[dict[str, Any]]:
    result = []
    for index, (base, cand) in enumerate(zip(baseline_rows, candidate_rows)):
        base_value = float(base["final_population"])
        cand_value = float(cand["final_population"])
        result.append(
            {
                "compact_row": index + 1,
                "full_row": int(base["full_row"]),
                "reference_population": float(reference[index]),
                "baseline_population": base_value,
                "candidate_population": cand_value,
                "candidate_minus_baseline": cand_value - base_value,
                "baseline_minus_reference": base_value - float(reference[index]),
                "candidate_minus_reference": cand_value - float(reference[index]),
            }
        )
    result.sort(key=lambda row: abs(float(row["candidate_minus_baseline"])), reverse=True)
    return result


def _constraint_report(root: Path, run: Path, evaluation: int, oracle50: list[dict[str, str]]) -> dict[str, Any]:
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
    return {
        "type53": verify_type53_invariant(run, oracle53, evaluation),
        "type71": verify_type71_invariant(run, oracle71, evaluation),
        "type99": verify_type99_invariant(run, oracle99, evaluation),
        "type50": compare_type50(run, oracle50, run.parent / "type50_constraint_checks", evaluation, run.name),
    }


def _preliminary_comparison(baseline: Path, candidate: Path, evaluation: int) -> dict[str, Any]:
    suffix = f"evaluation_{evaluation:04d}_ion_balance.csv"
    base = read_csv(baseline / "diagnostics" / suffix)
    cand = read_csv(candidate / "diagnostics" / suffix)
    fields = (
        "evaluation_ordinal", "element_index", "element_z", "stage", "ion_charge",
        "preliminary_ionization", "preliminary_recombination", "preliminary_fraction", "active_stage",
    )
    base_he = [{key: row[key] for key in fields} for row in base if int(row["element_z"]) == 2]
    cand_he = [{key: row[key] for key in fields} for row in cand if int(row["element_z"]) == 2]
    exact = base_he == cand_he
    return {
        "helium_ion_balance_rows": len(base_he),
        "baseline_candidate_ieee_exact": exact,
        "active_stage_selection_unchanged": exact,
        "preliminary_fractions_unchanged": exact,
        "preliminary_rates_unchanged": exact,
        "final_fractions_intentionally_excluded": True,
    }


def _verify_source_order_assembly(terms: list[dict[str, Any]], dense: np.ndarray) -> dict[str, Any]:
    reconstructed = np.zeros_like(dense)
    previous = 0
    for term in terms:
        order = int(term["source_order_index"])
        if order != previous + 1:
            raise ValueError(f"source-order term sequence is not contiguous at {order}")
        previous = order
        reconstructed[int(term["compact_row"]) - 1, int(term["compact_column"]) - 1] += float(term["aj1"])
    delta = reconstructed - dense
    return {
        "terms": len(terms),
        "source_order_contiguous": True,
        "matrix_ieee_exact": bool(np.array_equal(reconstructed, dense)),
        "nonzero_matrix_differences": int(np.count_nonzero(delta)),
        "maximum_absolute_matrix_difference": float(np.max(np.abs(delta))) if delta.size else 0.0,
    }


def audit(
    package_dir: Path,
    lowered_program: Path,
    output_dir: Path,
    *,
    evaluation: int = 61,
    radiation_csv: Path | None = None,
) -> dict[str, Any]:
    if evaluation != 61:
        raise ValueError("the reference level-population decomposition is restricted to evaluation 61")
    root = package_dir.resolve()
    lowered = lowered_program.resolve()
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
        raise ValueError("type-50 manifold oracle must contain 79 records")

    executable = root / "src/xstar_tools/xstar/cpp/xstar_cpp"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root / "src") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    run_command(["make", "-C", str(root / "src/xstar_tools/xstar/cpp"), "-j2"], cwd=root, env=env)

    baseline = output / "baseline_exact_53_71_99"
    candidate = output / "candidate_exact_53_71_99_50"
    _run_fixed(root, executable, lowered, trajectory, radiation, baseline, evaluation, exact_type50=False)
    _run_fixed(root, executable, lowered, trajectory, radiation, candidate, evaluation, exact_type50=True)

    baseline_rows = _solve_rows(baseline, evaluation)
    candidate_rows = _solve_rows(candidate, evaluation)
    if [(row["compact_row"], row["full_row"]) for row in baseline_rows] != [
        (row["compact_row"], row["full_row"]) for row in candidate_rows
    ]:
        raise RuntimeError("baseline and candidate helium row mappings differ")
    normalization_index = next(i for i, row in enumerate(baseline_rows) if int(row["is_normalization_row"]) == 1)
    normalization_full_row = int(baseline_rows[normalization_index]["full_row"])
    reference = _reference_populations(root, evaluation, baseline_rows)

    bmat, bheat, bheat2, brhs = _matrix(baseline, evaluation)
    cmat, cheat, cheat2, crhs = _matrix(candidate, evaluation)
    beff, beff_rhs = _effective_system(bmat, normalization_index)
    ceff, ceff_rhs = _effective_system(cmat, normalization_index)
    bnative = np.asarray([float(row["final_population"]) for row in baseline_rows], dtype=np.float64)
    cnative = np.asarray([float(row["final_population"]) for row in candidate_rows], dtype=np.float64)

    residual_rows = []
    residual_rows.extend(_residual_rows("baseline", baseline_rows, bmat, reference, normalization_index, "v06472_reference"))
    residual_rows.extend(_residual_rows("candidate", candidate_rows, cmat, reference, normalization_index, "v06472_reference"))
    residual_rows.extend(_residual_rows("baseline", baseline_rows, bmat, bnative, normalization_index, "native_solution"))
    residual_rows.extend(_residual_rows("candidate", candidate_rows, cmat, cnative, normalization_index, "native_solution"))
    write_csv(output / "helium_reference_and_native_row_residuals.csv", residual_rows, list(residual_rows[0]))

    exact = _scope_keys(root)
    baseline_terms = _term_ledger(baseline, evaluation, reference, exact)
    candidate_terms = _term_ledger(candidate, evaluation, reference, exact)
    write_csv(output / "helium_baseline_source_order_terms.csv", baseline_terms, list(baseline_terms[0]))
    write_csv(output / "helium_candidate_source_order_terms.csv", candidate_terms, list(candidate_terms[0]))

    candidate_reference_rows = [
        row for row in residual_rows if row["variant"] == "candidate" and row["population_vector"] == "v06472_reference"
    ]
    scope_rows, source_rows, ranking = _aggregate_residual(
        candidate_terms, candidate_reference_rows, normalization_full_row
    )
    write_csv(output / "helium_reference_residual_by_scope_row.csv", scope_rows, list(scope_rows[0]))
    write_csv(output / "helium_reference_residual_by_source_position.csv", source_rows, list(source_rows[0]))
    write_csv(output / "helium_reference_residual_scope_ranking.csv", ranking, list(ranking[0]))
    blocks = _row_blocks(candidate_reference_rows, scope_rows)
    write_csv(output / "helium_reference_residual_row_blocks.csv", blocks, list(blocks[0]))

    matrix_delta = _matrix_delta_rows(bmat, cmat, bheat, cheat, bheat2, cheat2, baseline_rows)
    write_csv(output / "helium_type50_matrix_delta.csv", matrix_delta, list(matrix_delta[0]) if matrix_delta else [])
    population_delta = _population_delta_rows(baseline_rows, candidate_rows, reference)
    write_csv(output / "helium_solution_response.csv", population_delta, list(population_delta[0]))

    baseline_constraints = _constraint_report(root, baseline, evaluation, oracle50)
    candidate_constraints = _constraint_report(root, candidate, evaluation, oracle50)
    immutable_ok = (
        baseline_constraints["type53"]["applied_exact"]
        and baseline_constraints["type71"]["all_ieee_exact"]
        and baseline_constraints["type99"]["all_ieee_exact"]
        and candidate_constraints["type53"]["applied_exact"]
        and candidate_constraints["type71"]["all_ieee_exact"]
        and candidate_constraints["type99"]["all_ieee_exact"]
        and candidate_constraints["type50"]["all_ieee_exact"]
    )
    isolation = element_isolation(baseline, candidate, evaluation)
    preliminary = _preliminary_comparison(baseline, candidate, evaluation)

    dominant_scope = ranking[0] if ranking else None
    remaining = [row for row in ranking if row["qualified_exact_scope"] == "false"]
    leading = remaining[0] if remaining else None
    leading_material_fraction = (
        max(0.0, float(leading["reference_residual_error_reduction_if_removed"]))
        / max(float(leading["reference_residual_l1"]), 1.0e-300)
        if leading else 0.0
    )
    leading_material = leading is not None and leading_material_fraction >= 0.01
    dominant_block = blocks[0] if blocks else None
    baseline_assembly = _verify_source_order_assembly(baseline_terms, bmat)
    candidate_assembly = _verify_source_order_assembly(candidate_terms, cmat)
    base_ref = np.asarray([float(row["effective_solver_residual"]) for row in residual_rows if row["variant"] == "baseline" and row["population_vector"] == "v06472_reference"])
    cand_ref = np.asarray([float(row["effective_solver_residual"]) for row in candidate_reference_rows])
    bdirect = np.linalg.solve(beff, beff_rhs)
    cdirect = np.linalg.solve(ceff, ceff_rhs)

    system = {
        "baseline": {
            "condition_number_2": float(np.linalg.cond(beff)),
            "matrix_rank": int(np.linalg.matrix_rank(beff)),
            "pivot_sequence_one_based": _pivot_sequence(beff),
            "reference_residual_l1": float(np.sum(np.abs(base_ref))),
            "reference_residual_linf": float(np.max(np.abs(base_ref))),
            "direct_solution_vs_native_l1": float(np.sum(np.abs(bdirect - bnative))),
        },
        "candidate": {
            "condition_number_2": float(np.linalg.cond(ceff)),
            "matrix_rank": int(np.linalg.matrix_rank(ceff)),
            "pivot_sequence_one_based": _pivot_sequence(ceff),
            "reference_residual_l1": float(np.sum(np.abs(cand_ref))),
            "reference_residual_linf": float(np.max(np.abs(cand_ref))),
            "direct_solution_vs_native_l1": float(np.sum(np.abs(cdirect - cnative))),
        },
        "delta": {
            "dense_matrix_nonzero_entries": len(matrix_delta),
            "dense_matrix_delta_l1": float(np.sum(np.abs(cmat - bmat))),
            "dense_matrix_delta_linf": float(np.max(np.abs(cmat - bmat))),
            "rhs_ieee_exact": bool(np.array_equal(brhs, crhs)),
            "native_solution_delta_l1": float(np.sum(np.abs(cnative - bnative))),
            "native_solution_delta_linf": float(np.max(np.abs(cnative - bnative))),
            "reference_residual_l1_reduction": float(np.sum(np.abs(base_ref)) - np.sum(np.abs(cand_ref))),
        },
    }
    write_json(output / "helium_solve_linear_system_summary.json", system)

    bmetrics = state_metrics(baseline, evaluation)
    cmetrics = state_metrics(candidate, evaluation)
    result = "ACCEPT" if (
        immutable_ok
        and isolation["max_h_mg_absolute_delta"] == 0.0
        and preliminary["baseline_candidate_ieee_exact"]
        and baseline_assembly["matrix_ieee_exact"]
        and candidate_assembly["matrix_ieee_exact"]
    ) else "REJECT"
    summary: dict[str, Any] = {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": result,
        "evaluation_ordinal": evaluation,
        "qualification_only": True,
        "source_ordered_term_count": len(candidate_terms),
        "compact_helium_rows": len(candidate_rows),
        "normalization_full_row": normalization_full_row,
        "immutable_constraints": {"baseline": baseline_constraints, "candidate": candidate_constraints},
        "preliminary_and_active_stage_comparison": preliminary,
        "element_isolation": isolation,
        "baseline_state": bmetrics,
        "candidate_state": cmetrics,
        "linear_system": system,
        "reference_population_normalization": float(np.sum(reference)),
        "reference_population_normalization_error": float(np.sum(reference) - 1.0),
        "source_order_assembly": {"baseline": baseline_assembly, "candidate": candidate_assembly},
        "dominant_reference_residual_scope": dominant_scope,
        "leading_remaining_scope": leading,
        "leading_remaining_scope_material_fraction": leading_material_fraction,
        "leading_remaining_family_or_scope_identified": leading_material,
        "dominant_reference_residual_row_block": dominant_block,
        "single_record_correction_ready": False,
        "fixed_state_parity": False,
        "thermal_parity": False,
        "production_promotion_ready": False,
        "remaining_blockers": [
            "reference-population residual magnitude identifies candidate scopes but does not prove their source formulas are wrong",
            "the evaluation-61 reference level-population vector is not an all-61-state oracle",
            "the exact type-50 manifold dominates the reference-population residual, indicating that the ptmp1=1/ptmp2=0 evaluator replay is not the complete DSEC escape-probability contract",
            "no unqualified remaining family explains at least one percent of the reference residual",
            "the leading unqualified scope requires source/runtime validation before any replacement",
            "fixed-state, thermal, controller, and product parity remain blocked",
        ],
    }
    write_json(output / "summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return summary


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package_dir", type=Path)
    parser.add_argument("lowered_program", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--evaluation", type=int, default=61)
    parser.add_argument("--radiation-csv", type=Path)
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args(argv)
    summary = audit(
        args.package_dir,
        args.lowered_program,
        args.output_dir,
        evaluation=args.evaluation,
        radiation_csv=args.radiation_csv,
    )
    if args.output_json:
        write_json(args.output_json, summary)
    return 0 if summary["result"] == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
