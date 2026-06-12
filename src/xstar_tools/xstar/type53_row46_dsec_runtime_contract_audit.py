"""Qualification-only original-DSEC type-53 row-46 coupled runtime-contract audit.

The audit freezes the 44-record, 176-term type-53 manifold that contributes to
compact helium row 46 during the actual v0.6.47.2 evaluation-61 DSEC solve.  It
compares the complete runtime answers and committed terms with the current
native fixed-state implementation, preserves original source order, and
substitutes the whole aliased manifold as one unit to measure the reference-
population residual and solve response.  It does not promote any single record
or an arbitrary-state production implementation.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import struct
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from .helium_family_isolation import (
    RADIATION_SHA256,
    discover_reference,
    read_csv,
    run_command,
    sha256,
    write_csv,
    write_json,
)
from .helium_solve_response_decomposition import (
    _diagnostic_path,
    _effective_system,
    _matrix,
    _reference_populations,
    _residual_rows,
    _solve_rows,
    _verify_source_order_assembly,
)
from .type50_dsec_coupled_replacement_audit import _run as _run_type50_dsec_candidate

csv.field_size_limit(sys.maxsize)

RELEASE = "0.6.48.7.15"
SCHEMA = "xstar-tools-v0648715-type53-row46-dsec-runtime-contract-audit-v1"
ORACLE_SCHEMA = "xstar-tools-v0648715-type53-row46-dsec-runtime-oracle-v1"
BUNDLE = Path("src/xstar_tools/benchmarks/v0648715_type53_row46_dsec_runtime_oracle_v0472")
RECORDS_NAME = "type53_row46_dsec_runtime_records.csv"
TERMS_NAME = "type53_row46_dsec_runtime_matrix_terms.csv"
CONTRIBUTION_NAME = "type53_row46_dsec_contribution.csv"
MANIFEST_NAME = "reference_manifest.json"
TARGET_EVALUATION = 61
TARGET_FULL_ROW = 46
TARGET_RECORDS = 44
TARGET_ANSWERS = 264
TARGET_TERMS = 176
TARGET_DATA_TYPE = 53
TARGET_RATE_TYPE = 7
ROLE_MAP = {
    "forward_gain": "forward_offdiag",
    "reverse_gain": "reverse_offdiag",
    "forward_diag_loss": "forward_diag_loss",
    "reverse_diag_loss": "reverse_diag_loss",
}
EXPECTED_RECORD_SHA256 = "055f8e7e4fab15933048537d7779d20e48684f73b07c7541124b5e48b6596e65"
EXPECTED_TERMS_SHA256 = "bca0488eee0e88c847de1789c6c1fc0705489d8c39f5ba0b91688796ecaad15a"
EXPECTED_CONTRIBUTION_SHA256 = "28b3492939a3932775c7a35e916f898b04f8b4363e0caa544a1f30631e8726aa"
PARENT_RECORD_SHA256 = "0a3182194ed63f90bebc4dd362ac29b421abf368232e4a937477dc5f6741f545"
PARENT_TERMS_SHA256 = "c62995b305bcb3191a20ac2a9f73f4dbaef890221aaeaa16ea28959592dc2849"
PARENT_TRACE_SHA256 = "46ad8a73302ea68381829f4568c6907b3c618e0a4449e3337f692a5dd6121257"


def _bits(value: str | float) -> bytes:
    return struct.pack(">d", float(value))


def _isfinite(value: str | float) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _load_manifest(bundle: Path) -> dict[str, Any]:
    manifest_path = bundle / MANIFEST_NAME
    if not manifest_path.is_file():
        raise FileNotFoundError(f"missing type-53 row-46 manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != ORACLE_SCHEMA:
        raise ValueError(f"unexpected type-53 row-46 oracle schema: {manifest.get('schema')!r}")
    return manifest


def verify_oracle(bundle: Path) -> dict[str, Any]:
    bundle = bundle.resolve()
    manifest = _load_manifest(bundle)
    errors: list[str] = []
    files = {
        "records": bundle / RECORDS_NAME,
        "matrix_terms": bundle / TERMS_NAME,
        "contribution": bundle / CONTRIBUTION_NAME,
    }
    for name, path in files.items():
        if not path.is_file():
            errors.append(f"missing oracle file: {name}")
    if errors:
        return {
            "schema": ORACLE_SCHEMA,
            "release": RELEASE,
            "result": "REJECT",
            "errors": errors,
            "qualification_only": True,
            "production_promotion_ready": False,
        }

    hashes = {name: sha256(path) for name, path in files.items()}
    expected_hashes = {
        "records": EXPECTED_RECORD_SHA256,
        "matrix_terms": EXPECTED_TERMS_SHA256,
        "contribution": EXPECTED_CONTRIBUTION_SHA256,
    }
    for name, expected in expected_hashes.items():
        if hashes[name] != expected:
            errors.append(f"{name} SHA-256 mismatch")
        if manifest.get(f"{name}_sha256") != expected:
            errors.append(f"manifest {name} SHA-256 mismatch")

    records = read_csv(files["records"])
    terms = read_csv(files["matrix_terms"])
    contribution = read_csv(files["contribution"])
    if len(records) != TARGET_RECORDS:
        errors.append(f"expected {TARGET_RECORDS} records, found {len(records)}")
    if len(terms) != TARGET_TERMS:
        errors.append(f"expected {TARGET_TERMS} terms, found {len(terms)}")
    if len(contribution) != 78:
        errors.append(f"expected 78 contribution columns, found {len(contribution)}")

    record_keys: list[tuple[int, int]] = []
    for row in records:
        key = (int(row["source_position"]), int(row["record"]))
        record_keys.append(key)
        if int(row["global_evaluation_ordinal"]) != TARGET_EVALUATION:
            errors.append(f"record {key} is not evaluation 61")
        if int(row["data_type"]) != TARGET_DATA_TYPE or int(row["rate_type"]) != TARGET_RATE_TYPE:
            errors.append(f"record {key} is not type-53/rate-type-7")
        if int(row.get("matrix_term_count") or 0) != 4 or str(row.get("matrix_committed", "")).lower() != "true":
            errors.append(f"record {key} does not have four committed terms")
        for field in (
            "tau_in", "tau_out", "ptmp1", "ptmp2", "ptmp_sum",
            "flinabs_ptmp1", "covering_fraction", "temperature_k",
            "hydrogen_density_cm3", "electron_fraction_xee",
            "ans1", "ans2", "ans3", "ans4", "ans5", "ans6",
            "initial_lower_population", "initial_upper_population",
            "lte_lower_population", "lte_upper_population",
            "final_lower_population", "final_upper_population",
        ):
            if row.get(field, "") != "" and not _isfinite(row[field]):
                errors.append(f"record {key} has non-finite {field}")
        for field in ("diagnostics_json", "population_dependency_json"):
            try:
                parsed = json.loads(row.get(field) or "{}")
                if not isinstance(parsed, dict):
                    raise ValueError("not an object")
            except Exception as exc:
                errors.append(f"record {key} has invalid {field}: {exc}")
    if len(set(record_keys)) != TARGET_RECORDS:
        errors.append("record identities are not unique")

    terms_by_record: Counter[tuple[int, int]] = Counter()
    term_keys: list[tuple[int, int, str]] = []
    valid_roles = set(ROLE_MAP.values())
    for row in terms:
        key2 = (int(row["source_position"]), int(row["record"]))
        key3 = (key2[0], key2[1], str(row["role"]))
        term_keys.append(key3)
        terms_by_record[key2] += 1
        if key2 not in set(record_keys):
            errors.append(f"term {key3} has no captured record")
        if int(row["global_evaluation_ordinal"]) != TARGET_EVALUATION:
            errors.append(f"term {key3} is not evaluation 61")
        if int(row["data_type"]) != TARGET_DATA_TYPE or int(row["rate_type"]) != TARGET_RATE_TYPE:
            errors.append(f"term {key3} is not type-53/rate-type-7")
        if row["role"] not in valid_roles:
            errors.append(f"term {key3} has invalid role")
        # The coupled record contract includes all four committed terms.
        # Only some terms touch row 46 directly; the opposite diagonal term
        # remains part of the source-faithful manifold and must be retained.
        for field in ("aj1", "aj2", "cj", "cj2"):
            if not _isfinite(row[field]):
                errors.append(f"term {key3} has non-finite {field}")
    if len(set(term_keys)) != TARGET_TERMS:
        errors.append("term identities are not unique")
    bad_counts = [key for key, count in terms_by_record.items() if count != 4]
    if bad_counts:
        errors.append(f"records without four terms: {bad_counts[:5]}")

    reconstructed = np.zeros(78, dtype=np.float64)
    for row in sorted(terms, key=lambda item: int(item["source_order_index"])):
        if int(row["row"]) == TARGET_FULL_ROW:
            reconstructed[int(row["column"]) - 1] += float(row["aj1"])
    expected = np.asarray([float(row["dense_contribution"]) for row in contribution], dtype=np.float64)
    exact_columns = sum(_bits(a) == _bits(b) for a, b in zip(reconstructed, expected))
    if exact_columns != 78:
        errors.append(f"source-order contribution reconstruction exact in only {exact_columns}/78 columns")

    for field, expected_value in (
        ("records", TARGET_RECORDS),
        ("answers", TARGET_ANSWERS),
        ("matrix_terms", TARGET_TERMS),
        ("data_type", TARGET_DATA_TYPE),
        ("rate_type", TARGET_RATE_TYPE),
        ("target_evaluation_ordinal", TARGET_EVALUATION),
        ("target_full_row", TARGET_FULL_ROW),
    ):
        if int(manifest.get(field, -1)) != expected_value:
            errors.append(f"manifest {field} mismatch")
    if manifest.get("parent_row46_record_oracle_sha256") != PARENT_RECORD_SHA256:
        errors.append("parent row-46 record hash mismatch")
    if manifest.get("parent_row46_matrix_terms_sha256") != PARENT_TERMS_SHA256:
        errors.append("parent row-46 term hash mismatch")
    if manifest.get("parent_trace_sha256") != PARENT_TRACE_SHA256:
        errors.append("parent DSEC trace hash mismatch")

    return {
        "schema": ORACLE_SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT" if not errors else "REJECT",
        "errors": errors,
        "records": len(records),
        "answers": len(records) * 6,
        "matrix_terms": len(terms),
        "source_order_contribution_exact_columns": exact_columns,
        "records_sha256": hashes["records"],
        "matrix_terms_sha256": hashes["matrix_terms"],
        "contribution_sha256": hashes["contribution"],
        "parent_row46_record_oracle_sha256": PARENT_RECORD_SHA256,
        "parent_row46_matrix_terms_sha256": PARENT_TERMS_SHA256,
        "parent_trace_sha256": PARENT_TRACE_SHA256,
        "qualification_only": True,
        "production_promotion_ready": False,
    }


def _candidate_records(run: Path, evaluation: int) -> list[dict[str, str]]:
    return read_csv(_diagnostic_path(run, evaluation, "records.csv"))


def _candidate_terms(run: Path, evaluation: int) -> list[dict[str, str]]:
    return read_csv(_diagnostic_path(run, evaluation, "helium_source_order_terms.csv"))


def _term_key(row: dict[str, str]) -> tuple[int, int, str]:
    return (
        int(row["contribution_source_position"]),
        int(row["record"]),
        ROLE_MAP[str(row["role"])],
    )


def _compare_records(
    oracle: list[dict[str, str]],
    candidate_rows: list[dict[str, str]],
    output: Path,
) -> dict[str, Any]:
    actual = {
        (int(row["source_position"]), int(row["record"])): row
        for row in candidate_rows
    }
    rows: list[dict[str, Any]] = []
    exact_by_answer = {f"ans{i}": 0 for i in range(1, 7)}
    l1_by_answer = {f"ans{i}": 0.0 for i in range(1, 7)}
    linf_by_answer = {f"ans{i}": 0.0 for i in range(1, 7)}
    for source in oracle:
        key = (int(source["source_position"]), int(source["record"]))
        candidate = actual.get(key)
        if candidate is None:
            raise ValueError(f"native candidate is missing type-53 row-46 record {key}")
        row: dict[str, Any] = {
            "source_position": key[0],
            "record": key[1],
            "element_z": int(source["element_z"]),
            "ion_stage": int(source["ion_stage"]),
            "lower_row": int(source["lower_row"]),
            "upper_row": int(source["upper_row"]),
            "compact_lower_row": int(source["compact_lower_row"]),
            "compact_upper_row": int(source["compact_upper_row"]),
            "escape_kind": source["escape_kind"],
            "escape_index": int(source["escape_index"] or 0),
            "tau_in": float(source["tau_in"]),
            "tau_out": float(source["tau_out"]),
            "ptmp1": float(source["ptmp1"]),
            "ptmp2": float(source["ptmp2"]),
            "flinabs_ptmp1": float(source["flinabs_ptmp1"]),
            "covering_fraction": float(source["covering_fraction"]),
            "initial_lower_population": float(source["initial_lower_population"] or 0.0),
            "initial_upper_population": float(source["initial_upper_population"] or 0.0),
            "final_lower_population": float(source["final_lower_population"] or 0.0),
            "final_upper_population": float(source["final_upper_population"] or 0.0),
            "provenance_branch": source["provenance_branch"],
            "provenance_implementation": source["provenance_implementation"],
        }
        all_exact = True
        for i in range(1, 7):
            field = f"ans{i}"
            oracle_value = float(source[field])
            native_value = float(candidate[field])
            delta = native_value - oracle_value
            exact = _bits(oracle_value) == _bits(native_value)
            exact_by_answer[field] += int(exact)
            l1_by_answer[field] += abs(delta)
            linf_by_answer[field] = max(linf_by_answer[field], abs(delta))
            all_exact = all_exact and exact
            row[f"dsec_{field}"] = oracle_value
            row[f"native_{field}"] = native_value
            row[f"delta_{field}"] = delta
            row[f"{field}_ieee_exact"] = exact
        row["all_answers_ieee_exact"] = all_exact
        rows.append(row)
    write_csv(output / "type53_row46_dsec_record_comparison.csv", rows, list(rows[0]))
    exact_records = sum(int(row["all_answers_ieee_exact"]) for row in rows)
    return {
        "records": len(rows),
        "answers": len(rows) * 6,
        "records_all_answers_ieee_exact": exact_records,
        "all_records_ieee_exact": exact_records == len(rows),
        "exact_by_answer": exact_by_answer,
        "answer_delta_l1": l1_by_answer,
        "answer_delta_linf": linf_by_answer,
    }


def _compare_terms(
    oracle: list[dict[str, str]],
    candidate_rows: list[dict[str, str]],
    output: Path,
) -> tuple[dict[str, Any], dict[tuple[int, int, str], dict[str, str]]]:
    actual = {_term_key(row): row for row in candidate_rows}
    oracle_by_key: dict[tuple[int, int, str], dict[str, str]] = {}
    captured_sequence: list[tuple[int, int, str]] = []
    rows: list[dict[str, Any]] = []
    exact_terms = 0
    exact_scalar_counts = {field: 0 for field in ("aj1", "aj2", "cj", "cj2")}
    scalar_l1 = {field: 0.0 for field in ("aj1", "aj2", "cj", "cj2")}
    scalar_linf = {field: 0.0 for field in ("aj1", "aj2", "cj", "cj2")}
    absolute_order_exact = 0
    for source in sorted(oracle, key=lambda row: int(row["source_order_index"])):
        key = (int(source["source_position"]), int(source["record"]), source["role"])
        oracle_by_key[key] = source
        captured_sequence.append(key)
        candidate = actual.get(key)
        if candidate is None:
            raise ValueError(f"native candidate is missing type-53 row-46 term {key}")
        native_order = int(candidate["source_order_index"])
        dsec_order = int(source["source_order_index"])
        row: dict[str, Any] = {
            "source_position": key[0],
            "record": key[1],
            "role": key[2],
            "row": int(source["row"]),
            "column": int(source["column"]),
            "dsec_source_order_index": dsec_order,
            "native_source_order_index": native_order,
            "source_order_index_delta": native_order - dsec_order,
            "absolute_source_order_index_exact": native_order == dsec_order,
        }
        absolute_order_exact += int(row["absolute_source_order_index_exact"])
        all_exact = True
        for field in ("aj1", "aj2", "cj", "cj2"):
            oracle_value = float(source[field])
            native_value = float(candidate[field])
            delta = native_value - oracle_value
            exact = _bits(oracle_value) == _bits(native_value)
            exact_scalar_counts[field] += int(exact)
            scalar_l1[field] += abs(delta)
            scalar_linf[field] = max(scalar_linf[field], abs(delta))
            all_exact = all_exact and exact
            row[f"dsec_{field}"] = oracle_value
            row[f"native_{field}"] = native_value
            row[f"delta_{field}"] = delta
            row[f"{field}_ieee_exact"] = exact
        row["term_ieee_exact"] = all_exact
        exact_terms += int(all_exact)
        rows.append(row)
    write_csv(output / "type53_row46_dsec_term_comparison.csv", rows, list(rows[0]))

    candidate_sequence = [
        _term_key(row)
        for row in sorted(candidate_rows, key=lambda row: int(row["source_order_index"]))
        if _term_key(row) in oracle_by_key
    ]
    relative_order_exact = candidate_sequence == captured_sequence
    return (
        {
            "terms": len(rows),
            "exact_terms": exact_terms,
            "all_terms_ieee_exact": exact_terms == len(rows),
            "exact_scalar_counts": exact_scalar_counts,
            "scalar_delta_l1": scalar_l1,
            "scalar_delta_linf": scalar_linf,
            "absolute_source_order_indices_exact": absolute_order_exact,
            "absolute_source_order_fully_exact": absolute_order_exact == len(rows),
            "relative_source_order_exact": relative_order_exact,
            "source_order_index_delta_min": min((int(row["source_order_index_delta"]) for row in rows), default=0),
            "source_order_index_delta_max": max((int(row["source_order_index_delta"]) for row in rows), default=0),
        },
        oracle_by_key,
    )


def _contribution_comparison(
    oracle_terms: list[dict[str, str]],
    candidate_terms: list[dict[str, str]],
    contribution_rows: list[dict[str, str]],
    output: Path,
) -> dict[str, Any]:
    oracle = np.zeros(78, dtype=np.float64)
    native = np.zeros(78, dtype=np.float64)
    keys = {
        (int(row["source_position"]), int(row["record"]), str(row["role"]))
        for row in oracle_terms
    }
    for row in sorted(oracle_terms, key=lambda item: int(item["source_order_index"])):
        if int(row["row"]) == TARGET_FULL_ROW:
            oracle[int(row["column"]) - 1] += float(row["aj1"])
    for row in sorted(candidate_terms, key=lambda item: int(item["source_order_index"])):
        if _term_key(row) in keys and int(row["compact_row"]) == TARGET_FULL_ROW:
            native[int(row["compact_column"]) - 1] += float(row["aj1"])
    frozen = np.asarray([float(row["dense_contribution"]) for row in contribution_rows], dtype=np.float64)
    rows: list[dict[str, Any]] = []
    frozen_exact = 0
    for index in range(78):
        exact = _bits(oracle[index]) == _bits(frozen[index])
        frozen_exact += int(exact)
        rows.append({
            "compact_column": index + 1,
            "frozen_dsec_contribution": frozen[index],
            "reconstructed_dsec_contribution": oracle[index],
            "native_contribution": native[index],
            "native_minus_dsec": native[index] - oracle[index],
            "frozen_reconstruction_ieee_exact": exact,
        })
    write_csv(output / "type53_row46_contribution_comparison.csv", rows, list(rows[0]))
    return {
        "columns": 78,
        "frozen_reconstruction_exact_columns": frozen_exact,
        "frozen_reconstruction_ieee_exact": frozen_exact == 78,
        "native_dsec_delta_l1": float(np.sum(np.abs(native - oracle))),
        "native_dsec_delta_linf": float(np.max(np.abs(native - oracle))),
        "native_nonzero_delta_columns": int(np.count_nonzero(native - oracle)),
    }


def _substitute_manifold(
    dense: np.ndarray,
    heat: np.ndarray,
    heat2: np.ndarray,
    candidate_terms: list[dict[str, str]],
    oracle_by_key: dict[tuple[int, int, str], dict[str, str]],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    out_dense = dense.copy()
    out_heat = heat.copy()
    out_heat2 = heat2.copy()
    replaced = 0
    for candidate in candidate_terms:
        key = _term_key(candidate)
        source = oracle_by_key.get(key)
        if source is None:
            continue
        row = int(candidate["compact_row"]) - 1
        column = int(candidate["compact_column"]) - 1
        out_dense[row, column] += float(source["aj1"]) - float(candidate["aj1"])
        out_heat[row, column] += float(source["cj"]) - float(candidate["cj"])
        out_heat2[row, column] += float(source["cj2"]) - float(candidate["cj2"])
        replaced += 1
    return out_dense, out_heat, out_heat2, replaced


def _residual_metrics(
    dense: np.ndarray,
    vector: np.ndarray,
    normalization_index: int,
) -> tuple[float, float, np.ndarray]:
    residual = (dense @ vector).astype(np.float64, copy=True)
    residual[normalization_index] = float(np.sum(vector) - 1.0)
    return float(np.sum(np.abs(residual))), float(np.max(np.abs(residual))), residual


def _solve_metrics(
    dense: np.ndarray,
    normalization_index: int,
) -> tuple[np.ndarray, dict[str, Any]]:
    matrix, rhs = _effective_system(dense, normalization_index)
    rank = int(np.linalg.matrix_rank(matrix))
    condition = float(np.linalg.cond(matrix))
    try:
        solution = np.linalg.solve(matrix, rhs)
        method = "solve"
    except np.linalg.LinAlgError:
        solution = np.linalg.lstsq(matrix, rhs, rcond=None)[0]
        method = "lstsq"
    return solution, {
        "matrix_rank": rank,
        "condition_number_2": condition,
        "solution_method": method,
        "normalization_error": abs(float(np.sum(solution)) - 1.0),
    }


def _population_rows(
    solve_rows: list[dict[str, str]],
    native: np.ndarray,
    substituted: np.ndarray,
    reference: np.ndarray,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(solve_rows):
        rows.append({
            "compact_row": int(row["compact_row"]),
            "full_row": int(row["full_row"]),
            "is_normalization_row": int(row["is_normalization_row"]),
            "native_solution": float(native[index]),
            "type53_dsec_substituted_solution": float(substituted[index]),
            "reference_population": float(reference[index]),
            "substituted_minus_native": float(substituted[index] - native[index]),
            "native_absolute_reference_error": abs(float(native[index] - reference[index])),
            "substituted_absolute_reference_error": abs(float(substituted[index] - reference[index])),
        })
    return rows


def audit(
    package_dir: Path,
    lowered_program: Path,
    output_dir: Path,
    *,
    evaluation: int = TARGET_EVALUATION,
    oracle_dir: Path | None = None,
    radiation_csv: Path | None = None,
) -> dict[str, Any]:
    if evaluation != TARGET_EVALUATION:
        raise ValueError("type-53 row-46 runtime-contract audit is restricted to evaluation 61")
    root = package_dir.resolve()
    lowered = lowered_program.resolve()
    output = output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    bundle = oracle_dir.resolve() if oracle_dir else (root / BUNDLE).resolve()

    oracle_verification = verify_oracle(bundle)
    if oracle_verification["result"] != "ACCEPT":
        raise ValueError(f"type-53 row-46 oracle rejected: {oracle_verification['errors']}")
    oracle_records = read_csv(bundle / RECORDS_NAME)
    oracle_terms = read_csv(bundle / TERMS_NAME)
    contribution_rows = read_csv(bundle / CONTRIBUTION_NAME)

    trajectory = discover_reference(root, "trajectory.csv")
    radiation = radiation_csv.resolve() if radiation_csv else discover_reference(root, "reference_radiation_v0472_full.csv")
    if sha256(radiation) != RADIATION_SHA256:
        raise ValueError("qualification radiation hash mismatch")
    executable = root / "src/xstar_tools/xstar/cpp/xstar_cpp"
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(root / "src")
    run_command(["make", "-C", str(root / "src/xstar_tools/xstar/cpp"), "-j2"], cwd=root, env=environment)

    candidate = output / "candidate_exact_53_71_99_actual_dsec_type50"
    _run_type50_dsec_candidate(root, executable, lowered, trajectory, radiation, candidate, evaluation, True)

    candidate_records = _candidate_records(candidate, evaluation)
    candidate_terms = _candidate_terms(candidate, evaluation)
    record_comparison = _compare_records(oracle_records, candidate_records, output)
    term_comparison, oracle_by_key = _compare_terms(oracle_terms, candidate_terms, output)
    contribution_comparison = _contribution_comparison(oracle_terms, candidate_terms, contribution_rows, output)

    solve_rows = _solve_rows(candidate, evaluation)
    dense, heat, heat2, rhs = _matrix(candidate, evaluation)
    normalization_index = next(index for index, row in enumerate(solve_rows) if int(row["is_normalization_row"]) == 1)
    reference = _reference_populations(root, evaluation, solve_rows)
    native_solution = np.asarray([float(row["final_population"]) for row in solve_rows], dtype=np.float64)

    candidate_l1, candidate_linf, candidate_residual = _residual_metrics(dense, reference, normalization_index)
    substituted_dense, substituted_heat, substituted_heat2, replaced = _substitute_manifold(
        dense, heat, heat2, candidate_terms, oracle_by_key
    )
    substituted_l1, substituted_linf, substituted_residual = _residual_metrics(
        substituted_dense, reference, normalization_index
    )
    reduction = candidate_l1 - substituted_l1
    fraction = reduction / max(candidate_l1, 1.0e-300)
    row46_before = float(candidate_residual[TARGET_FULL_ROW - 1])
    row46_after = float(substituted_residual[TARGET_FULL_ROW - 1])

    residual_rows = _residual_rows(
        "original_dsec_type53_row46_manifold",
        solve_rows,
        substituted_dense,
        reference,
        normalization_index,
        "v0472_reference",
    )
    write_csv(output / "type53_row46_reference_residual_rows.csv", residual_rows, list(residual_rows[0]))

    substituted_solution, substituted_solve_metrics = _solve_metrics(substituted_dense, normalization_index)
    native_effective, _ = _effective_system(dense, normalization_index)
    native_solve_metrics = {
        "matrix_rank": int(np.linalg.matrix_rank(native_effective)),
        "condition_number_2": float(np.linalg.cond(native_effective)),
        "normalization_error": abs(float(np.sum(native_solution)) - 1.0),
    }
    population_rows = _population_rows(solve_rows, native_solution, substituted_solution, reference)
    write_csv(output / "type53_row46_solution_response.csv", population_rows, list(population_rows[0]))

    selected_keys = set(oracle_by_key)
    source_terms = [
        {
            **row,
            "source_order_index": int(row["source_order_index"]),
            "compact_row": int(row["compact_row"]),
            "compact_column": int(row["compact_column"]),
            "aj1": float(row["aj1"]),
        }
        for row in candidate_terms
    ]
    native_assembly = _verify_source_order_assembly(source_terms, dense)
    substituted_terms: list[dict[str, Any]] = []
    for row in source_terms:
        updated = dict(row)
        source = oracle_by_key.get(_term_key(row))
        if source is not None:
            updated["aj1"] = float(source["aj1"])
        substituted_terms.append(updated)
    substituted_assembly = _verify_source_order_assembly(substituted_terms, substituted_dense)

    runtime_summary = {
        "records": TARGET_RECORDS,
        "tau_in_nonzero_records": sum(abs(float(row["tau_in"])) > 0.0 for row in oracle_records),
        "tau_out_nonzero_records": sum(abs(float(row["tau_out"])) > 0.0 for row in oracle_records),
        "ptmp1_zero_records": sum(float(row["ptmp1"]) == 0.0 for row in oracle_records),
        "ptmp2_unity_records": sum(float(row["ptmp2"]) == 1.0 for row in oracle_records),
        "ptmp2_attenuated_records": sum(float(row["ptmp2"]) < 1.0 for row in oracle_records),
        "covering_fraction_unity_records": sum(float(row["covering_fraction"]) == 1.0 for row in oracle_records),
        "population_dependency_records": sum(bool(json.loads(row["population_dependency_json"])) for row in oracle_records),
        "provenance_branches": sorted({row["provenance_branch"] for row in oracle_records}),
        "provenance_implementations": sorted({row["provenance_implementation"] for row in oracle_records}),
    }

    materially_reduced = fraction >= 0.95 and abs(row46_after) < abs(row46_before) * 1.0e-3
    audit_complete = (
        oracle_verification["result"] == "ACCEPT"
        and record_comparison["records"] == TARGET_RECORDS
        and term_comparison["terms"] == TARGET_TERMS
        and contribution_comparison["frozen_reconstruction_ieee_exact"]
        and replaced == TARGET_TERMS
        and materially_reduced
        and native_assembly["matrix_ieee_exact"]
        and math.isfinite(substituted_solve_metrics["condition_number_2"])
    )

    summary: dict[str, Any] = {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT" if audit_complete else "REJECT",
        "evaluation_ordinal": evaluation,
        "qualification_only": True,
        "oracle_verification": oracle_verification,
        "runtime_contract": runtime_summary,
        "record_comparison": record_comparison,
        "term_comparison": term_comparison,
        "source_order_contribution": contribution_comparison,
        "source_order_assembly": {
            "native_candidate": native_assembly,
            "offline_original_dsec_type53": substituted_assembly,
        },
        "coupled_residual_response": {
            "candidate_reference_residual_l1": candidate_l1,
            "candidate_reference_residual_linf": candidate_linf,
            "type53_dsec_substituted_reference_residual_l1": substituted_l1,
            "type53_dsec_substituted_reference_residual_linf": substituted_linf,
            "absolute_l1_reduction": reduction,
            "fraction_l1_reduced": fraction,
            "row46_residual_before": row46_before,
            "row46_residual_after": row46_after,
            "row46_absolute_reduction": abs(row46_before) - abs(row46_after),
            "terms_replaced": replaced,
            "materially_reduced": materially_reduced,
        },
        "solve_response": {
            "native": native_solve_metrics,
            "type53_dsec_substituted": substituted_solve_metrics,
            "solution_delta_l1": float(np.sum(np.abs(substituted_solution - native_solution))),
            "solution_delta_linf": float(np.max(np.abs(substituted_solution - native_solution))),
            "native_reference_error_l1": float(np.sum(np.abs(native_solution - reference))),
            "substituted_reference_error_l1": float(np.sum(np.abs(substituted_solution - reference))),
            "rhs_unchanged": True,
        },
        "native_answer_parity": record_comparison["all_records_ieee_exact"],
        "native_matrix_term_parity": term_comparison["all_terms_ieee_exact"],
        "native_relative_source_order_parity": term_comparison["relative_source_order_exact"],
        "native_absolute_source_order_parity": term_comparison["absolute_source_order_fully_exact"],
        "type53_row46_general_state_promotion_ready": False,
        "single_record_correction_ready": False,
        "fixed_state_parity": False,
        "thermal_parity": False,
        "production_promotion_ready": False,
        "remaining_blockers": [
            "the original-DSEC type-53 contract is frozen only at evaluation 61",
            "native type-53 answers and matrix terms do not yet reproduce the 44-record runtime contract",
            "native relative and absolute source order differ from the original DSEC stream",
            "the arbitrary-state type-53 escape, radiation, and population-dependent law is not yet promoted",
            "fixed-state, thermal, controller, and product parity remain blocked",
        ],
    }
    write_json(output / "summary.json", summary)
    write_json(output / "type53_row46_runtime_contract_summary.json", {
        "oracle_verification": oracle_verification,
        "runtime_contract": runtime_summary,
        "record_comparison": record_comparison,
        "term_comparison": term_comparison,
    })
    write_json(output / "type53_row46_coupled_response_summary.json", {
        "source_order_contribution": contribution_comparison,
        "coupled_residual_response": summary["coupled_residual_response"],
        "solve_response": summary["solve_response"],
    })
    print(json.dumps(summary, indent=2, sort_keys=True))
    return summary


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command")

    verify_parser = subparsers.add_parser("verify", help="verify the frozen type-53 row-46 oracle")
    verify_parser.add_argument("oracle_dir", type=Path)
    verify_parser.add_argument("--output-json", type=Path)

    audit_parser = subparsers.add_parser("audit", help="run the coupled runtime-contract audit")
    audit_parser.add_argument("package_dir", type=Path)
    audit_parser.add_argument("lowered_program", type=Path)
    audit_parser.add_argument("output_dir", type=Path)
    audit_parser.add_argument("--evaluation", type=int, default=TARGET_EVALUATION)
    audit_parser.add_argument("--oracle-dir", type=Path)
    audit_parser.add_argument("--radiation-csv", type=Path)
    audit_parser.add_argument("--output-json", type=Path)

    args = parser.parse_args(list(argv) if argv is not None else None)
    command = args.command or "audit"
    try:
        if command == "verify":
            result = verify_oracle(args.oracle_dir)
        else:
            result = audit(
                args.package_dir,
                args.lowered_program,
                args.output_dir,
                evaluation=args.evaluation,
                oracle_dir=args.oracle_dir,
                radiation_csv=args.radiation_csv,
            )
    except Exception as exc:
        print(f"type-53 row-46 DSEC runtime-contract audit failed: {exc}")
        return 2
    if getattr(args, "output_json", None):
        write_json(args.output_json, result)
    return 0 if result["result"] == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
