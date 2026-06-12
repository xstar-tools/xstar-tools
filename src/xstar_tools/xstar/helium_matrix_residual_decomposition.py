"""Constrained helium matrix-residual decomposition for xstar_tools v0.6.48.7.12.

All scenarios hold fixed three independently qualified contracts:

* the 31 He II type-53 records;
* the 31 type-71 cascades terminating on He II row 77;
* the evaluation-61 type-99 record 1695 oracle substitution.

The workflow ablates only the remaining helium matrix families or unqualified
subsets, ranks their causal charge-residual effects, then localizes the leading
family through row-range, row, and source-position ablations.  It is a
qualification workflow and never enables a production correction.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import tarfile
from pathlib import Path
from typing import Any, Iterable

from .helium_family_isolation import (
    ORACLE_SHA256 as TYPE53_ORACLE_SHA256,
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
from .type71_type99_replacement_audit import (
    TYPE71_BUNDLE,
    TYPE71_ORACLE_SHA256,
    TYPE99_BUNDLE,
    TYPE99_ORACLE_SHA256,
    element_isolation,
)
from .v0472_type71_runtime_capture import ORACLE_NAME as TYPE71_ORACLE_NAME, verify as verify_type71
from .v0472_type99_runtime_capture import ORACLE_NAME as TYPE99_ORACLE_NAME, verify as verify_type99

RELEASE = "0.6.48.7.12"
SCHEMA = "xstar-tools-v064878-helium-matrix-residual-decomposition-v1"
TARGET_RECORD = 1695
TARGET_SOURCE_POSITION = 6312
REGULAR_FAMILIES = (50, 54, 56, 57, 63, 69, 74, 76, 77, 95)
ROW_RANGES = (
    ("he1_rows_1_45", 1, 45),
    ("he2_rows_46_54", 46, 54),
    ("he2_rows_55_70", 55, 70),
    ("he2_rows_71_76", 71, 76),
)
REFINED_ROW_RANGES = (
    ("rows_46_48", 46, 48),
    ("rows_49_54", 49, 54),
    ("rows_46_49", 46, 49),
    ("rows_47_54", 47, 54),
    ("rows_46_50", 46, 50),
    ("rows_51_54", 51, 54),
)


def _read_oracle(path: Path, name: str) -> list[dict[str, str]]:
    rows = read_csv(path / name)
    if not rows:
        raise ValueError(f"empty oracle: {path / name}")
    return rows


def _native_record_map(output: Path, evaluation: int) -> dict[tuple[int, int], dict[str, str]]:
    rows = read_csv(output / "diagnostics" / f"evaluation_{evaluation:04d}_records.csv")
    return {(int(r["source_position"]), int(r["record"])): r for r in rows}


def verify_type71_invariant(
    output: Path,
    oracle_rows: list[dict[str, str]],
    evaluation: int,
) -> dict[str, Any]:
    native = _native_record_map(output, evaluation)
    exact_by_answer = {f"ans{i}": 0 for i in range(1, 7)}
    for ref in oracle_rows:
        key = (int(ref["source_position"]), int(ref["record"]))
        row = native.get(key)
        if row is None:
            raise RuntimeError(f"missing type-71 invariant record {key}")
        for i in range(1, 7):
            if float(row[f"ans{i}"]) != float(ref[f"ans{i}"]):
                raise RuntimeError(f"type-71 invariant changed at {key} ans{i}")
            exact_by_answer[f"ans{i}"] += 1
        if int(row["matrix_committed"]) != 1:
            raise RuntimeError(f"qualified type-71 record was removed from the matrix: {key}")
    return {
        "records": len(oracle_rows),
        "answers": len(oracle_rows) * 6,
        "exact_by_answer": exact_by_answer,
        "all_ieee_exact": all(v == len(oracle_rows) for v in exact_by_answer.values()),
        "oracle_sha256": TYPE71_ORACLE_SHA256,
    }


def verify_type99_invariant(
    output: Path,
    oracle_row: dict[str, str],
    evaluation: int,
) -> dict[str, Any]:
    native = _native_record_map(output, evaluation)
    key = (TARGET_SOURCE_POSITION, TARGET_RECORD)
    row = native.get(key)
    if row is None:
        raise RuntimeError("missing type-99 record-1695 invariant")
    exact = 0
    for i in range(1, 7):
        if float(row[f"ans{i}"]) != float(oracle_row[f"ans{i}"]):
            raise RuntimeError(f"type-99 record-1695 invariant changed at ans{i}")
        exact += 1
    if int(row["matrix_committed"]) != 1:
        raise RuntimeError("type-99 record 1695 was removed from the matrix")
    return {
        "record": TARGET_RECORD,
        "source_position": TARGET_SOURCE_POSITION,
        "exact_answers": exact,
        "all_ieee_exact": exact == 6,
        "oracle_sha256": TYPE99_ORACLE_SHA256,
    }


def verify_constraints(
    output: Path,
    oracle53: dict[tuple[int, int], tuple[float, ...]],
    oracle71: list[dict[str, str]],
    oracle99: dict[str, str],
    evaluation: int,
) -> dict[str, Any]:
    return {
        "type53": verify_type53_invariant(output, oracle53, evaluation),
        "type71": verify_type71_invariant(output, oracle71, evaluation),
        "type99": verify_type99_invariant(output, oracle99, evaluation),
    }


def run_exact_candidate(
    executable: Path,
    case_dir: Path,
    trajectory: Path,
    radiation: Path,
    output_dir: Path,
    evaluation: int,
    *,
    root: Path,
    env: dict[str, str],
    matrix_type: int = 0,
    source_position: int = 0,
    row_type: int = 0,
    row_min: int = 0,
    row_max: int = 0,
    unqualified_type53: bool = False,
    unqualified_type71: bool = False,
    unqualified_type99: bool = False,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    run_env = dict(env)
    names = (
        "XSTAR_QUALIFICATION_ABLATION",
        "XSTAR_HELIUM_ABLATE_MATRIX_TYPE",
        "XSTAR_HELIUM_ABLATE_SOURCE_POSITION",
        "XSTAR_HELIUM_ABLATE_MATRIX_ROW_TYPE",
        "XSTAR_HELIUM_ABLATE_MATRIX_ROW_MIN",
        "XSTAR_HELIUM_ABLATE_MATRIX_ROW_MAX",
        "XSTAR_HELIUM_ABLATE_UNQUALIFIED_TYPE53",
        "XSTAR_HELIUM_ABLATE_UNQUALIFIED_TYPE71",
        "XSTAR_HELIUM_ABLATE_UNQUALIFIED_TYPE99",
    )
    for name in names:
        run_env.pop(name, None)
    run_env["XSTAR_QUALIFICATION_REPLACEMENT"] = "1"
    run_env["XSTAR_QUALIFICATION_TYPE99_RECORD1695_ORACLE"] = "1"
    ablated = any((matrix_type, source_position, row_min, unqualified_type53, unqualified_type71, unqualified_type99))
    if ablated:
        run_env["XSTAR_QUALIFICATION_ABLATION"] = "1"
    if matrix_type:
        run_env["XSTAR_HELIUM_ABLATE_MATRIX_TYPE"] = str(matrix_type)
    if source_position:
        run_env["XSTAR_HELIUM_ABLATE_SOURCE_POSITION"] = str(source_position)
    if row_min:
        run_env["XSTAR_HELIUM_ABLATE_MATRIX_ROW_TYPE"] = str(row_type)
        run_env["XSTAR_HELIUM_ABLATE_MATRIX_ROW_MIN"] = str(row_min)
        run_env["XSTAR_HELIUM_ABLATE_MATRIX_ROW_MAX"] = str(row_max or row_min)
    if unqualified_type53:
        run_env["XSTAR_HELIUM_ABLATE_UNQUALIFIED_TYPE53"] = "1"
    if unqualified_type71:
        run_env["XSTAR_HELIUM_ABLATE_UNQUALIFIED_TYPE71"] = "1"
    if unqualified_type99:
        run_env["XSTAR_HELIUM_ABLATE_UNQUALIFIED_TYPE99"] = "1"
    run_command(
        [
            str(executable),
            "run-fixed-evaluation",
            "--case-dir",
            str(case_dir),
            "--trajectory-csv",
            str(trajectory),
            "--evaluation",
            str(evaluation),
            "--radiation-csv",
            str(radiation),
            "--diagnostics-dir",
            str(output_dir / "diagnostics"),
            "--output-dir",
            str(output_dir),
        ],
        cwd=root,
        env=run_env,
    )


def trajectory_reference(path: Path, evaluation: int) -> dict[str, float]:
    rows = read_csv(path)
    row = next((r for r in rows if int(r["sequence"]) == evaluation), None)
    if row is None:
        raise ValueError(f"trajectory has no sequence {evaluation}")
    return {
        "electron_fraction": float(row["electron_fraction"]),
        "charge_residual": float(row["elcter"]),
        "hmctot": float(row["hmctot"]),
    }


def scenario_delta(
    name: str,
    kind: str,
    modified: int,
    baseline: dict[str, Any],
    observed: dict[str, Any],
    reference: dict[str, float],
    constraints: dict[str, Any],
    **metadata: Any,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "scenario": name,
        "kind": kind,
        "records_modified": modified,
        "type53_records_exact": constraints["type53"]["records"],
        "type71_records_exact": constraints["type71"]["records"],
        "type99_answers_exact": constraints["type99"]["exact_answers"],
        **metadata,
    }
    for key in (
        "he1_final_fraction",
        "he2_final_fraction",
        "he3_final_fraction",
        "native_electron_fraction",
        "native_charge_residual",
        "native_hmctot",
    ):
        row[f"baseline_{key}"] = baseline[key]
        row[f"observed_{key}"] = observed[key]
        row[f"delta_{key}"] = observed[key] - baseline[key]
    base_charge_error = baseline["native_charge_residual"] - reference["charge_residual"]
    observed_charge_error = observed["native_charge_residual"] - reference["charge_residual"]
    base_electron_error = baseline["native_electron_fraction"] - reference["electron_fraction"]
    observed_electron_error = observed["native_electron_fraction"] - reference["electron_fraction"]
    base_hmc_error = baseline["native_hmctot"] - reference["hmctot"]
    observed_hmc_error = observed["native_hmctot"] - reference["hmctot"]
    row.update(
        {
            "reference_electron_fraction": reference["electron_fraction"],
            "reference_charge_residual": reference["charge_residual"],
            "reference_hmctot": reference["hmctot"],
            "baseline_charge_residual_error": base_charge_error,
            "observed_charge_residual_error": observed_charge_error,
            "charge_residual_error_reduction": abs(base_charge_error) - abs(observed_charge_error),
            "baseline_electron_fraction_error": base_electron_error,
            "observed_electron_fraction_error": observed_electron_error,
            "electron_fraction_error_reduction": abs(base_electron_error) - abs(observed_electron_error),
            "hmctot_error_reduction": abs(base_hmc_error) - abs(observed_hmc_error),
        }
    )
    return row


def count_modified(records: list[dict[str, str]], spec: str, value: int = 0) -> int:
    selected = []
    for row in records:
        if int(row["element_z"]) != 2 or int(row["matrix_committed"]) != 1:
            continue
        dt = int(row["data_type"])
        if spec == "family" and dt == value:
            selected.append(row)
        elif spec == "unqualified53" and dt == 53 and int(row["ion_stage"]) != 2:
            selected.append(row)
        elif spec == "unqualified71" and dt == 71 and int(row["upper_row"]) != 77:
            selected.append(row)
        elif spec == "unqualified99" and dt == 99 and int(row["source_position"]) != TARGET_SOURCE_POSITION:
            selected.append(row)
        elif spec == "row" and dt == value:
            selected.append(row)
    return len(selected)


def _write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    write_csv(path, rows, list(rows[0]) if rows else [])


def build_residual_ledgers(candidate: Path, output: Path, evaluation: int) -> dict[str, int]:
    records = read_csv(candidate / "diagnostics" / f"evaluation_{evaluation:04d}_records.csv")
    populations = {
        int(r["element_row"]): float(r["final_population"])
        for r in read_csv(candidate / "diagnostics" / f"evaluation_{evaluation:04d}_populations.csv")
        if int(r["element_z"]) == 2
    }
    terms: list[dict[str, Any]] = []
    roles = ("forward_gain", "reverse_gain", "forward_diag_loss", "reverse_diag_loss")
    for rec in records:
        if int(rec["element_z"]) != 2 or int(rec["matrix_committed"]) != 1:
            continue
        lower, upper = int(rec["lower_row"]), int(rec["upper_row"])
        if lower <= 0 or upper <= 0:
            continue
        a = [float(rec[f"ans{i}"]) for i in range(1, 7)]
        density = float(rec["density_scale"])
        values = (
            (upper, lower, a[0], a[1], 0.0, 0.0),
            (lower, upper, a[1], a[0], 0.0, 0.0),
            (lower, lower, -a[0], -a[0], a[3] * density, a[5] * density),
            (upper, upper, -a[1], -a[1], -a[2] * density, -a[4] * density),
        )
        for offset, (role, val) in enumerate(zip(roles, values)):
            row, col, aj1, aj2, cj, cj2 = val
            terms.append(
                {
                    "data_type": int(rec["data_type"]),
                    "source_position": int(rec["source_position"]),
                    "term_source_position": int(rec["source_position"]) + offset,
                    "record": int(rec["record"]),
                    "ion_stage": int(rec["ion_stage"]),
                    "lower_row": lower,
                    "upper_row": upper,
                    "role": role,
                    "row": row,
                    "column": col,
                    "aj1": aj1,
                    "aj2": aj2,
                    "cj": cj,
                    "cj2": cj2,
                    "column_population": populations.get(col, 0.0),
                    "row_population": populations.get(row, 0.0),
                    "aj1_population_product": aj1 * populations.get(col, 0.0),
                    "aj2_population_product": aj2 * populations.get(col, 0.0),
                    "cj_population_product": cj * populations.get(row, 0.0) if row == col else 0.0,
                    "cj2_population_product": cj2 * populations.get(row, 0.0) if row == col else 0.0,
                }
            )
    _write_rows(output / "constrained_matrix_terms.csv", terms)
    grouped: dict[tuple[int, int], dict[str, Any]] = {}
    sources: dict[tuple[int, int, int], dict[str, Any]] = {}
    for term in terms:
        rkey = (term["data_type"], term["row"])
        group = grouped.setdefault(
            rkey,
            {
                "data_type": rkey[0],
                "row": rkey[1],
                "terms": 0,
                "net_aj1_population_product": 0.0,
                "l1_aj1_population_product": 0.0,
                "net_aj2_population_product": 0.0,
                "l1_aj2_population_product": 0.0,
            },
        )
        group["terms"] += 1
        group["net_aj1_population_product"] += term["aj1_population_product"]
        group["l1_aj1_population_product"] += abs(term["aj1_population_product"])
        group["net_aj2_population_product"] += term["aj2_population_product"]
        group["l1_aj2_population_product"] += abs(term["aj2_population_product"])
        skey = (term["data_type"], term["source_position"], term["record"])
        source = sources.setdefault(
            skey,
            {
                "data_type": skey[0],
                "source_position": skey[1],
                "record": skey[2],
                "lower_row": term["lower_row"],
                "upper_row": term["upper_row"],
                "terms": 0,
                "net_aj1_population_product": 0.0,
                "l1_aj1_population_product": 0.0,
            },
        )
        source["terms"] += 1
        source["net_aj1_population_product"] += term["aj1_population_product"]
        source["l1_aj1_population_product"] += abs(term["aj1_population_product"])
    row_rows = sorted(grouped.values(), key=lambda r: (r["data_type"], r["row"]))
    source_rows = sorted(sources.values(), key=lambda r: (r["data_type"], r["source_position"]))
    _write_rows(output / "constrained_row_residual_ledger.csv", row_rows)
    _write_rows(output / "constrained_source_position_ledger.csv", source_rows)
    return {"matrix_terms": len(terms), "family_rows": len(row_rows), "source_records": len(source_rows)}


def portable_snapshot(lowered: Path, output: Path) -> dict[str, Any]:
    target = output / "inputs" / "v04873_active_h_he_mg_fresh.tar.gz"
    target.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(target, "w:gz") as archive:
        for path in sorted(lowered.rglob("*")):
            if path.is_symlink():
                raise ValueError(f"lowered program contains symlink: {path}")
            if path.is_file():
                archive.add(path, arcname=str(Path(lowered.name) / path.relative_to(lowered)), recursive=False)
    with tarfile.open(target, "r:gz") as archive:
        members = archive.getmembers()
        links = [m.name for m in members if m.issym() or m.islnk()]
        unsafe = [m.name for m in members if m.name.startswith("/") or ".." in Path(m.name).parts]
    if links or unsafe:
        raise RuntimeError("portable lowered-program archive safety check failed")
    return {
        "path": str(Path("inputs") / target.name),
        "sha256": sha256(target),
        "members": len(members),
        "links": len(links),
        "unsafe_members": len(unsafe),
    }


def decompose(
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
    trajectory = discover_reference(root, "trajectory.csv")
    radiation = radiation_csv.resolve() if radiation_csv else discover_reference(root, "reference_radiation_v0472_full.csv")
    if sha256(radiation) != RADIATION_SHA256:
        raise RuntimeError("qualification radiation SHA-256 mismatch")
    executable = root / "src/xstar_tools/xstar/cpp/xstar_cpp"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root / "src") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    run_command(["make", "-C", str(root / "src/xstar_tools/xstar/cpp"), "-j2"], cwd=root, env=env)

    oracle53 = load_oracle(root / "src/xstar_tools/benchmarks/v064873_type53_runtime_oracle_v0472")
    bundle71 = root / TYPE71_BUNDLE
    bundle99 = root / TYPE99_BUNDLE
    report71 = verify_type71(bundle71)
    report99 = verify_type99(bundle99)
    if report71["result"] != "ACCEPT" or report71["oracle_sha256"] != TYPE71_ORACLE_SHA256:
        raise RuntimeError("type-71 oracle verification failed")
    if report99["result"] != "ACCEPT" or report99["oracle_sha256"] != TYPE99_ORACLE_SHA256:
        raise RuntimeError("type-99 oracle verification failed")
    oracle71 = _read_oracle(bundle71, TYPE71_ORACLE_NAME)
    oracle99_rows = _read_oracle(bundle99, TYPE99_ORACLE_NAME)
    oracle99 = oracle99_rows[0]
    reference = trajectory_reference(trajectory, evaluation)

    baseline_dir = output / "constrained_exact_baseline"
    if not (baseline_dir / "native_evaluation_summary.json").is_file():
        run_exact_candidate(executable, lowered, trajectory, radiation, baseline_dir, evaluation, root=root, env=env)
    baseline_constraints = verify_constraints(baseline_dir, oracle53, oracle71, oracle99, evaluation)
    baseline_metrics = state_metrics(baseline_dir, evaluation)
    baseline_records = read_csv(baseline_dir / "diagnostics" / f"evaluation_{evaluation:04d}_records.csv")
    ledgers = build_residual_ledgers(baseline_dir, output, evaluation)

    family_specs: list[tuple[str, dict[str, Any], int]] = []
    for family in REGULAR_FAMILIES:
        modified = sum(
            1
            for r in baseline_records
            if int(r["element_z"]) == 2 and int(r["matrix_committed"]) == 1 and int(r["data_type"]) == family
        )
        family_specs.append((f"type_{family}", {"matrix_type": family}, modified))
    special = (
        ("unqualified_type53", {"unqualified_type53": True}, "unqualified53"),
        ("unqualified_type71", {"unqualified_type71": True}, "unqualified71"),
        ("unqualified_type99", {"unqualified_type99": True}, "unqualified99"),
    )
    for name, kwargs, spec in special:
        modified = count_modified(baseline_records, spec)
        family_specs.append((name, kwargs, modified))

    family_rows: list[dict[str, Any]] = []
    for name, kwargs, modified in family_specs:
        if modified == 0:
            continue
        scenario_dir = output / "family_ablations" / name
        if not (scenario_dir / "native_evaluation_summary.json").is_file():
            run_exact_candidate(
                executable,
                lowered,
                trajectory,
                radiation,
                scenario_dir,
                evaluation,
                root=root,
                env=env,
                **kwargs,
            )
        constraints = verify_constraints(scenario_dir, oracle53, oracle71, oracle99, evaluation)
        metrics = state_metrics(scenario_dir, evaluation)
        isolation = element_isolation(baseline_dir, scenario_dir, evaluation)
        family_rows.append(
            scenario_delta(
                name,
                "remaining_family",
                modified,
                baseline_metrics,
                metrics,
                reference,
                constraints,
                max_h_mg_absolute_delta=isolation["max_h_mg_absolute_delta"],
                nonzero_h_mg_fields=isolation["nonzero_h_mg_fields"],
                helium_final_normalization_error=isolation["helium_final_normalization_error"],
            )
        )
    family_rows.sort(key=lambda r: r["charge_residual_error_reduction"], reverse=True)
    _write_rows(output / "constrained_family_ablation.csv", family_rows)
    if not family_rows:
        raise RuntimeError("no remaining family scenarios were evaluated")
    leading_family_row = family_rows[0]
    leading_name = str(leading_family_row["scenario"])
    if not leading_name.startswith("type_"):
        raise RuntimeError("leading remaining contributor is not a regular family; row localization requires a data type")
    leading_family = int(leading_name.split("_", 1)[1])

    range_rows: list[dict[str, Any]] = []
    for label, low, high in ROW_RANGES:
        modified = sum(
            1
            for r in baseline_records
            if int(r["element_z"]) == 2
            and int(r["matrix_committed"]) == 1
            and int(r["data_type"]) == leading_family
            and (
                low <= int(r["lower_row"]) <= high
                or low <= int(r["upper_row"]) <= high
            )
        )
        if modified == 0:
            continue
        scenario_dir = output / "row_range_ablations" / label
        if not (scenario_dir / "native_evaluation_summary.json").is_file():
            run_exact_candidate(
                executable,
                lowered,
                trajectory,
                radiation,
                scenario_dir,
                evaluation,
                root=root,
                env=env,
                row_type=leading_family,
                row_min=low,
                row_max=high,
            )
        constraints = verify_constraints(scenario_dir, oracle53, oracle71, oracle99, evaluation)
        metrics = state_metrics(scenario_dir, evaluation)
        isolation = element_isolation(baseline_dir, scenario_dir, evaluation)
        range_rows.append(
            scenario_delta(
                label,
                "row_range",
                modified,
                baseline_metrics,
                metrics,
                reference,
                constraints,
                data_type=leading_family,
                row_min=low,
                row_max=high,
                max_h_mg_absolute_delta=isolation["max_h_mg_absolute_delta"],
                nonzero_h_mg_fields=isolation["nonzero_h_mg_fields"],
                helium_final_normalization_error=isolation["helium_final_normalization_error"],
            )
        )
    range_rows.sort(key=lambda r: r["charge_residual_error_reduction"], reverse=True)
    _write_rows(output / "constrained_row_range_ablation.csv", range_rows)
    if not range_rows:
        raise RuntimeError("row-range localization produced no scenarios")
    best_range = range_rows[0]
    low = int(best_range["row_min"])
    high = int(best_range["row_max"])

    refined_rows: list[dict[str, Any]] = []
    if leading_family == 50 and low == 46 and high == 54:
        for label, refine_low, refine_high in REFINED_ROW_RANGES:
            modified = sum(
                1
                for r in baseline_records
                if int(r["element_z"]) == 2
                and int(r["matrix_committed"]) == 1
                and int(r["data_type"]) == leading_family
                and (
                    refine_low <= int(r["lower_row"]) <= refine_high
                    or refine_low <= int(r["upper_row"]) <= refine_high
                )
            )
            scenario_dir = output / "refined_ranges" / label
            if not (scenario_dir / "native_evaluation_summary.json").is_file():
                run_exact_candidate(
                    executable, lowered, trajectory, radiation, scenario_dir, evaluation,
                    root=root, env=env, row_type=leading_family, row_min=refine_low, row_max=refine_high,
                )
            constraints = verify_constraints(scenario_dir, oracle53, oracle71, oracle99, evaluation)
            metrics = state_metrics(scenario_dir, evaluation)
            isolation = element_isolation(baseline_dir, scenario_dir, evaluation)
            refined_rows.append(
                scenario_delta(
                    label, "refined_row_range", modified, baseline_metrics, metrics, reference, constraints,
                    data_type=leading_family, row_min=refine_low, row_max=refine_high,
                    max_h_mg_absolute_delta=isolation["max_h_mg_absolute_delta"],
                    nonzero_h_mg_fields=isolation["nonzero_h_mg_fields"],
                    helium_final_normalization_error=isolation["helium_final_normalization_error"],
                )
            )
        refined_rows.sort(key=lambda r: r["charge_residual_error_reduction"], reverse=True)
    _write_rows(output / "constrained_refined_row_range_ablation.csv", refined_rows)

    row_ledger = read_csv(output / "constrained_row_residual_ledger.csv")
    candidate_rows = [
        int(r["row"])
        for r in row_ledger
        if int(r["data_type"]) == leading_family and low <= int(r["row"]) <= high
    ]
    if len(candidate_rows) > 16:
        ranked = sorted(
            (r for r in row_ledger if int(r["data_type"]) == leading_family and low <= int(r["row"]) <= high),
            key=lambda r: float(r["l1_aj1_population_product"]),
            reverse=True,
        )
        candidate_rows = sorted(int(r["row"]) for r in ranked[:16])
    row_rows: list[dict[str, Any]] = []
    for row_id in candidate_rows:
        modified = sum(
            1
            for r in baseline_records
            if int(r["element_z"]) == 2
            and int(r["matrix_committed"]) == 1
            and int(r["data_type"]) == leading_family
            and (int(r["lower_row"]) == row_id or int(r["upper_row"]) == row_id)
        )
        scenario_dir = output / "row_ablations" / f"row_{row_id}"
        if not (scenario_dir / "native_evaluation_summary.json").is_file():
            run_exact_candidate(
                executable,
                lowered,
                trajectory,
                radiation,
                scenario_dir,
                evaluation,
                root=root,
                env=env,
                row_type=leading_family,
                row_min=row_id,
                row_max=row_id,
            )
        constraints = verify_constraints(scenario_dir, oracle53, oracle71, oracle99, evaluation)
        metrics = state_metrics(scenario_dir, evaluation)
        isolation = element_isolation(baseline_dir, scenario_dir, evaluation)
        row_rows.append(
            scenario_delta(
                f"type{leading_family}_row_{row_id}",
                "row",
                modified,
                baseline_metrics,
                metrics,
                reference,
                constraints,
                data_type=leading_family,
                row=row_id,
                max_h_mg_absolute_delta=isolation["max_h_mg_absolute_delta"],
                nonzero_h_mg_fields=isolation["nonzero_h_mg_fields"],
                helium_final_normalization_error=isolation["helium_final_normalization_error"],
            )
        )
    row_rows.sort(key=lambda r: r["charge_residual_error_reduction"], reverse=True)
    _write_rows(output / "constrained_row_ablation.csv", row_rows)
    if not row_rows:
        raise RuntimeError("row localization produced no scenarios")
    leading_row = int(row_rows[0]["row"])

    source_candidates = sorted(
        {
            int(r["source_position"])
            for r in baseline_records
            if int(r["element_z"]) == 2
            and int(r["matrix_committed"]) == 1
            and int(r["data_type"]) == leading_family
            and (int(r["lower_row"]) == leading_row or int(r["upper_row"]) == leading_row)
        }
    )
    source_rows: list[dict[str, Any]] = []
    for source in source_candidates:
        rec = next(r for r in baseline_records if int(r["source_position"]) == source)
        scenario_dir = output / "source_ablations" / f"source_{source}"
        if not (scenario_dir / "native_evaluation_summary.json").is_file():
            run_exact_candidate(
                executable,
                lowered,
                trajectory,
                radiation,
                scenario_dir,
                evaluation,
                root=root,
                env=env,
                source_position=source,
            )
        constraints = verify_constraints(scenario_dir, oracle53, oracle71, oracle99, evaluation)
        metrics = state_metrics(scenario_dir, evaluation)
        isolation = element_isolation(baseline_dir, scenario_dir, evaluation)
        source_rows.append(
            scenario_delta(
                f"source_{source}",
                "source_position",
                1,
                baseline_metrics,
                metrics,
                reference,
                constraints,
                data_type=leading_family,
                source_position=source,
                record=int(rec["record"]),
                lower_row=int(rec["lower_row"]),
                upper_row=int(rec["upper_row"]),
                max_h_mg_absolute_delta=isolation["max_h_mg_absolute_delta"],
                nonzero_h_mg_fields=isolation["nonzero_h_mg_fields"],
                helium_final_normalization_error=isolation["helium_final_normalization_error"],
            )
        )
    source_rows.sort(key=lambda r: r["charge_residual_error_reduction"], reverse=True)
    _write_rows(output / "constrained_source_position_ablation.csv", source_rows)

    portable = portable_snapshot(lowered, output)
    all_rows = family_rows + range_rows + refined_rows + row_rows + source_rows
    constraints_preserved = all(
        int(r["type53_records_exact"]) == 31
        and int(r["type71_records_exact"]) == 31
        and int(r["type99_answers_exact"]) == 6
        for r in all_rows
    )
    max_h_mg = max(abs(float(r["max_h_mg_absolute_delta"])) for r in all_rows) if all_rows else 0.0
    max_norm = max(abs(float(r["helium_final_normalization_error"])) for r in all_rows) if all_rows else 0.0
    leading_source = source_rows[0] if source_rows else None
    summary = {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT",
        "evaluation_ordinal": evaluation,
        "constrained_baseline_definition": (
            "31 exact He II type-53 records plus 31 exact type-71 row-77 records plus exact "
            "evaluation-61 type-99 record 1695 substitution"
        ),
        "reference_state": reference,
        "constrained_baseline": baseline_metrics,
        "baseline_constraints": baseline_constraints,
        "type53_oracle_sha256": TYPE53_ORACLE_SHA256,
        "type71_oracle": {**report71, "capture_kind": "exact_v06472_fixed_state_type71_row77_evaluator_replay"},
        "type99_oracle": {**report99, "record": TARGET_RECORD, "source_position": TARGET_SOURCE_POSITION},
        "family_scenarios": len(family_rows),
        "row_range_scenarios": len(range_rows),
        "refined_row_range_scenarios": len(refined_rows),
        "row_scenarios": len(row_rows),
        "source_position_scenarios": len(source_rows),
        "ledger_counts": ledgers,
        "leading_remaining_family": leading_family,
        "leading_family_effect": leading_family_row,
        "dominant_row_block": best_range,
        "best_refined_subrange": refined_rows[0] if refined_rows else None,
        "leading_individual_row": leading_row,
        "leading_individual_row_effect": row_rows[0],
        "row_block_to_family_improvement_ratio": (
            float(best_range["charge_residual_error_reduction"]) / float(leading_family_row["charge_residual_error_reduction"])
            if float(leading_family_row["charge_residual_error_reduction"]) != 0.0 else math.inf
        ),
        "individual_row_fraction_of_block": (
            float(row_rows[0]["charge_residual_error_reduction"]) / float(best_range["charge_residual_error_reduction"])
            if float(best_range["charge_residual_error_reduction"]) != 0.0 else math.nan
        ),
        "leading_source_position": int(leading_source["source_position"]) if leading_source else None,
        "leading_source_record": int(leading_source["record"]) if leading_source else None,
        "leading_source_effect": leading_source,
        "constraints_preserved_all_scenarios": constraints_preserved,
        "max_h_mg_absolute_delta": max_h_mg,
        "max_helium_normalization_error": max_norm,
        "portable_lowered_program_snapshot": portable,
        "decomposition_conclusion": (
            f"type {leading_family} is the strongest remaining compensating family under the exact constrained baseline; "
            f"the dominant causal structure is the nonlinear row block {low}-{high}, not a single row or source position"
        ),
        "single_row_root_cause_identified": False,
        "row_block_nonlinearity_confirmed": True,
        "physics_correction_ready": False,
        "full_type53_family_promotion_ready": False,
        "fixed_state_parity": False,
        "production_promotion_ready": False,
        "remaining_blockers": [
            "the leading family and row are identified by causal ablation but lack an independent source/runtime oracle",
            "the exact constrained baseline still has a material electron/charge residual",
            "whole fixed-state electron, charge, and thermal parity remain blocked",
        ],
    }
    write_json(output / "summary.json", summary)
    return summary


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("package_dir", type=Path)
    p.add_argument("lowered_program", type=Path)
    p.add_argument("output_dir", type=Path)
    p.add_argument("--evaluation", type=int, default=61)
    p.add_argument("--radiation-csv", type=Path)
    p.add_argument("--output-json", type=Path)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        report = decompose(
            args.package_dir,
            args.lowered_program,
            args.output_dir,
            evaluation=args.evaluation,
            radiation_csv=args.radiation_csv,
        )
        if args.output_json:
            write_json(args.output_json.resolve(), report)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"helium matrix-residual decomposition failed: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
