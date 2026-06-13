"""Audit the v0.6.48.7.21.3 type-53 DSEC runtime-state ABI extension.

The audit verifies the appended ABI fields, then—when an independent original-
DSEC evaluation-60 capture is available—runs the native coupled type-53 path
with the captured ``epi/bremsa`` and continuum optical-depth workspaces and
compares all 44 records and 176 committed terms.
"""
from __future__ import annotations

import argparse
import ctypes
import csv
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

from .helium_family_isolation import read_csv, run_command, write_json
from .helium_solve_response_decomposition import _diagnostic_path
from .type53_row46_dsec_runtime_contract_audit import (
    _candidate_records,
    _candidate_terms,
    _compare_records,
    _compare_terms,
)
from .type53_runtime_state_independent_capture import (
    RADIATION_NAME,
    RECORDS_NAME,
    TARGET_EVALUATION,
    TARGET_RECORDS,
    TARGET_TERMS,
    TAU_NAME,
    TERMS_NAME,
    verify as verify_capture,
)

csv.field_size_limit(sys.maxsize)

RELEASE = "0.6.48.7.21.3"
SCHEMA = "xstar-tools-v0648719-type53-rnist-covering-correction-audit-v1"
ABI_VERSION = 60487
PROGRAM_ABI_VERSION = 60485


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n")


def _build(root: Path) -> Path:
    cpp = root / "src/xstar_tools/xstar/cpp"
    run_command(["make", "-C", str(cpp), "-j2"], cwd=root, env=dict(os.environ))
    executable = cpp / "xstar_cpp"
    if not executable.is_file():
        raise FileNotFoundError(executable)
    return executable


def abi_readiness(root: Path) -> dict[str, Any]:
    executable = _build(root)
    lib = root / "src/xstar_tools/xstar/cpp/libxstar_fixed_state.so"
    handle = ctypes.CDLL(str(lib))
    handle.xstar_fixed_state_engine_abi_version.restype = ctypes.c_uint32
    abi = int(handle.xstar_fixed_state_engine_abi_version())
    header = (root / "src/xstar_tools/xstar/cpp/xstar_fixed_state_engine.h").read_text()
    required_fields = (
        "dsec_radiation_energy_ev",
        "dsec_bremsa",
        "dsec_radiation_bin_count",
        "continuum_tau_in",
        "continuum_tau_out",
        "continuum_tau_count",
        "runtime_state_flags",
        "dsec_covering_fraction",
    )
    missing = [field for field in required_fields if field not in header]
    help_text = subprocess.run(
        [str(executable)], cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    ).stdout
    cli_ready = ("--dsec-radiation-csv" in help_text and "--continuum-tau-csv" in help_text
                 and "--dsec-covering-fraction" in help_text)
    result = "ACCEPT" if abi == ABI_VERSION and not missing and cli_ready else "REJECT"
    return {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": result,
        "abi_version": abi,
        "program_abi_version": PROGRAM_ABI_VERSION,
        "appended_fields": list(required_fields),
        "missing_fields": missing,
        "standalone_workspace_cli": cli_ready,
        "dsec_radiation_workspace": "ACCEPT" if "dsec_bremsa" not in missing and cli_ready else "REJECT",
        "continuum_optical_depth_workspace": "ACCEPT" if "continuum_tau_in" not in missing and cli_ready else "REJECT",
        "independent_state_capture": "RUN_REQUIRED",
        "independent_state_parity": "BLOCKED",
        "arbitrary_state_promotion": "BLOCKED",
        "production_promotion_ready": False,
    }


def _run_native(
    root: Path,
    executable: Path,
    case_dir: Path,
    capture_dir: Path,
    output: Path,
    evaluation: int,
) -> None:
    trajectory = root / "src/xstar_tools/benchmarks/v06486_qualification_reference_v0472/trajectory.csv"
    radiation = root / "src/xstar_tools/benchmarks/v06486_qualification_reference_v0472/reference_radiation_v0472_full.csv"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root / "src") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["XSTAR_QUALIFICATION_REPLACEMENT"] = "1"
    env["XSTAR_QUALIFICATION_TYPE53_ROW46_COUPLED_REPLACEMENT"] = "1"
    env["XSTAR_QUALIFICATION_SOLVE_RESPONSE"] = "1"
    captured_records = read_csv(capture_dir / RECORDS_NAME)
    covering_values = {float(row["covering_fraction"]) for row in captured_records}
    temperature_values = {float(row["temperature_k"]) for row in captured_records}
    if len(covering_values) != 1:
        raise ValueError(f"independent capture must have one DSEC covering fraction, got {sorted(covering_values)}")
    if len(temperature_values) != 1:
        raise ValueError(f"independent capture must have one DSEC temperature, got {sorted(temperature_values)}")
    dsec_covering_fraction = next(iter(covering_values))
    dsec_temperature_k = next(iter(temperature_values))
    run_command(
        [
            str(executable),
            "run-fixed-evaluation",
            "--case-dir", str(case_dir.resolve()),
            "--trajectory-csv", str(trajectory),
            "--evaluation", str(evaluation),
            "--radiation-csv", str(radiation),
            "--dsec-radiation-csv", str((capture_dir / RADIATION_NAME).resolve()),
            "--continuum-tau-csv", str((capture_dir / TAU_NAME).resolve()),
            "--dsec-covering-fraction", format(dsec_covering_fraction, ".17g"),
            "--temperature-k", format(dsec_temperature_k, ".17g"),
            "--diagnostics-dir", str((output / "diagnostics").resolve()),
            "--output-dir", str(output.resolve()),
        ],
        cwd=root,
        env=env,
    )


def audit(
    root: Path,
    case_dir: Path,
    capture_dir: Path,
    output_dir: Path,
    *,
    evaluation: int = TARGET_EVALUATION,
) -> dict[str, Any]:
    root = root.resolve()
    case_dir = case_dir.resolve()
    capture_dir = capture_dir.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    readiness = abi_readiness(root)
    capture = verify_capture(capture_dir)
    if readiness["result"] != "ACCEPT" or capture["result"] != "ACCEPT":
        result = {
            "schema": SCHEMA,
            "release": RELEASE,
            "result": "REJECT",
            "abi_readiness": readiness,
            "capture_verification": capture,
            "independent_state_parity": False,
            "arbitrary_state_promotion_ready": False,
            "production_promotion_ready": False,
        }
        _write(output_dir / "type53_runtime_state_abi_audit_summary.json", result)
        return result

    executable = root / "src/xstar_tools/xstar/cpp/xstar_cpp"
    native = output_dir / "native_independent_state"
    _run_native(root, executable, case_dir, capture_dir, native, evaluation)

    oracle_records = read_csv(capture_dir / RECORDS_NAME)
    oracle_terms = read_csv(capture_dir / TERMS_NAME)
    candidate_records = _candidate_records(native, evaluation)
    candidate_terms = _candidate_terms(native, evaluation)
    record_comparison = _compare_records(oracle_records, candidate_records, output_dir)
    term_comparison, _ = _compare_terms(oracle_terms, candidate_terms, output_dir)

    selected_records = [
        row for row in candidate_records
        if int(row.get("element_z") or 0) == 2
        and int(row.get("data_type") or 0) == 53
        and int(row.get("type53_row46_contract") or 0) == 1
    ]
    workspace_used = sum(int(row.get("type53_runtime_state_abi_used") or 0) == 1 for row in selected_records)
    source_valid = sum(int(row.get("type53_shadow_valid") or 0) == 1 for row in selected_records)
    radiation_counts = {int(row.get("type53_dsec_radiation_bin_count") or 0) for row in selected_records}
    tau_counts = {int(row.get("type53_continuum_tau_count") or 0) for row in selected_records}
    summary_path = native / "native_evaluation_summary.json"
    native_summary = json.loads(summary_path.read_text()) if summary_path.is_file() else {}
    status_abi = bool(native_summary.get("dsec_runtime_state_abi"))

    parity = (
        record_comparison["all_records_ieee_exact"]
        and term_comparison["all_terms_ieee_exact"]
        and term_comparison["absolute_source_order_fully_exact"]
        and workspace_used == TARGET_RECORDS
        and source_valid == TARGET_RECORDS
        and status_abi
    )
    result = {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT",
        "qualification_only": True,
        "abi_readiness": readiness,
        "capture_verification": capture,
        "evaluation_ordinal": evaluation,
        "runtime_state_correction": {
            "continuum_energy_semantics": "destination continuum energy, not zero",
            "dsec_covering_fraction": next(iter({float(row["covering_fraction"]) for row in oracle_records})),
            "dsec_temperature_k": next(iter({float(row["temperature_k"]) for row in oracle_records})),
            "rounded_trajectory_temperature_not_reused": True,
            "generic_covering_fraction_not_reused": True,
            "rnist_exponent_correction": "remove spurious exp(-min(threshold, continuum_energy)/kT) suppression",
        },
        "runtime_state_workspace": {
            "native_status_flag": status_abi,
            "records": len(selected_records),
            "workspace_used_records": workspace_used,
            "source_shadow_valid_records": source_valid,
            "dsec_radiation_bin_counts": sorted(radiation_counts),
            "continuum_tau_counts": sorted(tau_counts),
        },
        "record_comparison": record_comparison,
        "term_comparison": term_comparison,
        "independent_state_parity": parity,
        "arbitrary_state_promotion_ready": parity,
        "remaining_blockers": [] if parity else [
            "independent-state answers, thermal terms, or source-order positions are not yet exact",
            "arbitrary-state promotion requires exact independent original-DSEC parity",
        ],
        "production_promotion_ready": False,
    }
    _write(output_dir / "type53_runtime_state_abi_audit_summary.json", result)
    return result


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    ready = sub.add_parser("readiness")
    ready.add_argument("package_dir", type=Path)
    ready.add_argument("--output-json", type=Path)
    run = sub.add_parser("audit")
    run.add_argument("package_dir", type=Path)
    run.add_argument("case_dir", type=Path)
    run.add_argument("capture_dir", type=Path)
    run.add_argument("output_dir", type=Path)
    run.add_argument("--evaluation", type=int, default=TARGET_EVALUATION)
    run.add_argument("--output-json", type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "readiness":
            result = abi_readiness(args.package_dir.resolve())
        else:
            result = audit(
                args.package_dir,
                args.case_dir,
                args.capture_dir,
                args.output_dir,
                evaluation=args.evaluation,
            )
        if args.output_json:
            write_json(args.output_json, result)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["result"] == "ACCEPT" else 2
    except Exception as exc:
        result = {
            "schema": SCHEMA,
            "release": RELEASE,
            "result": "REJECT",
            "errors": [str(exc)],
            "independent_state_parity": False,
            "arbitrary_state_promotion_ready": False,
            "production_promotion_ready": False,
        }
        if getattr(args, "output_json", None):
            write_json(args.output_json, result)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
