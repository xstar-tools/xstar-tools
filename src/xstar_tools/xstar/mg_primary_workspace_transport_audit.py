"""v0.6.48.7.23 Mg-primary and call-start workspace transport audit.

This module is qualification-only.  It verifies the real Mg abundance weighting,
applies the captured source call-1 Mg budget as an exact state oracle, transports
the four call-start workspace payloads, and separates implementation readiness
from the complete controller parity result.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

import numpy as np

RELEASE = "0.6.48.7.23"
SCHEMA = "xstar-tools-v0648723-mg-primary-workspace-transport-audit-v1"
ARRAYS = (
    "radiation_energy",
    "bremsa",
    "continuum_tau_in",
    "continuum_tau_out",
    "global_xilevg",
    "global_bilevg",
    "global_rnisg",
)
CHANGED_WORKSPACES = (
    "bremsa",
    "continuum_tau_in",
    "global_xilevg",
    "global_bilevg",
    "global_rnisg",
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _array_bytes(values: np.ndarray) -> bytes:
    return np.ascontiguousarray(values, dtype=np.float64).tobytes(order="C")


def _payload_dir(capture_dir: Path) -> Path:
    primary = capture_dir / "original_payload_capture" / "call_start_payloads"
    return primary if primary.is_dir() else capture_dir / "call_start_payloads"


def _budget_path(capture_dir: Path) -> Path:
    primary = capture_dir / "original_payload_capture" / "v0472_call1_thermal_budget.csv"
    return primary if primary.is_file() else capture_dir / "v0472_call1_thermal_budget.csv"


def prepare(capture_dir: Path, output_dir: Path) -> dict[str, Any]:
    payload_dir = _payload_dir(capture_dir)
    if not payload_dir.is_dir():
        raise FileNotFoundError(f"missing call-start payload directory: {payload_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)
    binary_dir = output_dir / "call_start_workspace_bin"
    binary_dir.mkdir(parents=True, exist_ok=True)

    manifest: list[dict[str, Any]] = []
    call_counts: dict[str, dict[str, int]] = {}
    for call in range(1, 5):
        source = payload_dir / f"call_{call}.npz"
        if not source.is_file():
            raise FileNotFoundError(f"missing call-start payload: {source}")
        with np.load(source, allow_pickle=False) as archive:
            missing = [name for name in ARRAYS if name not in archive.files]
            if missing:
                raise ValueError(f"call {call} payload missing arrays: {missing}")
            call_counts[str(call)] = {}
            for name in ARRAYS:
                values = np.asarray(archive[name], dtype=np.float64).reshape(-1)
                raw = _array_bytes(values)
                target = binary_dir / f"call_{call}_{name}.bin"
                target.write_bytes(raw)
                file_raw = target.read_bytes()
                if file_raw != raw:
                    raise RuntimeError(f"binary payload round-trip mismatch for call {call} {name}")
                call_counts[str(call)][name] = int(values.size)
                manifest.append(
                    {
                        "call_index": call,
                        "workspace": name,
                        "count": int(values.size),
                        "bytes": len(raw),
                        "sha256": _sha256_bytes(raw),
                    }
                )

    budget = _budget_path(capture_dir)
    if not budget.is_file():
        raise FileNotFoundError(f"missing call-1 thermal budget: {budget}")
    target_budget = output_dir / "v0472_call1_thermal_budget.csv"
    target_budget.write_bytes(budget.read_bytes())
    budget_rows = [row for row in read_csv(target_budget) if int(row["dsec_call_id"]) == 1]
    if len(budget_rows) != 21:
        raise ValueError(f"expected 21 call-1 Mg budget rows, found {len(budget_rows)}")

    result = {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT",
        "payload_calls": 4,
        "payload_arrays": list(ARRAYS),
        "changed_workspaces": list(CHANGED_WORKSPACES),
        "call_array_counts": call_counts,
        "manifest": manifest,
        "workspace_dir": str(binary_dir),
        "mg_budget_csv": str(target_budget),
        "mg_budget_rows": len(budget_rows),
        "mg_budget_mode": "captured_source_call1_qualification_oracle",
        "qualification_only": True,
        "production_promotion_ready": False,
    }
    write_json(output_dir / "transport_preparation.json", result)
    return result


def _bool_field(row: dict[str, str], name: str) -> bool:
    return str(row.get(name, "0")).strip().lower() in {"1", "true", "yes"}


def _observed_calls(rows: Iterable[dict[str, str]]) -> list[int]:
    return sorted({int(row["call_index"]) for row in rows if row.get("call_index")})


def audit(package_dir: Path, capture_dir: Path, native_dir: Path, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    source_rows = [row for row in read_csv(_budget_path(capture_dir)) if int(row["dsec_call_id"]) == 1]
    native_budget_path = native_dir / "native_thermal_budget.csv"
    native_rows = read_csv(native_budget_path) if native_budget_path.is_file() else []
    native_call1 = [
        row for row in native_rows
        if row.get("kind") == "dsec" and int(row.get("call_index", "0")) == 1
    ]

    compared = min(len(source_rows), len(native_call1))
    exact = 0
    comparison: list[dict[str, Any]] = []
    fields = ("mg_heating", "mg_cooling", "mg_heating2", "mg_cooling2")
    for index in range(compared):
        source, native = source_rows[index], native_call1[index]
        row_exact = all(float(source[name]) == float(native[name]) for name in fields)
        exact += int(row_exact)
        comparison.append(
            {
                "evaluation": index + 1,
                "exact": row_exact,
                **{f"source_{name}": float(source[name]) for name in fields},
                **{f"native_{name}": float(native[name]) for name in fields},
            }
        )
    if comparison:
        with (output_dir / "mg_primary_budget_comparison.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(comparison[0]))
            writer.writeheader()
            writer.writerows(comparison)

    prep_path = output_dir / "transport_preparation.json"
    prep = json.loads(prep_path.read_text(encoding="utf-8")) if prep_path.is_file() else {}
    payload_ready = (
        prep.get("result") == "ACCEPT"
        and int(prep.get("payload_calls", 0)) == 4
        and tuple(prep.get("changed_workspaces", ())) == CHANGED_WORKSPACES
    )

    runtime_ledger_path = native_dir / "native_runtime_state_transport.csv"
    runtime_rows = read_csv(runtime_ledger_path) if runtime_ledger_path.is_file() else []
    dsec_runtime_rows = [row for row in runtime_rows if row.get("kind") == "dsec"]
    workspace_rows = [row for row in dsec_runtime_rows if _bool_field(row, "call_start_workspace_applied")]
    mg_override_rows = [row for row in dsec_runtime_rows if _bool_field(row, "mg_primary_override_applied")]
    workspace_runtime_observed = bool(workspace_rows)
    mg_runtime_observed = bool(mg_override_rows)

    summary_path = native_dir / "native_dsec_summary.json"
    controller_summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.is_file() else {}
    controller_completed = bool(controller_summary)
    controller_identity = bool(controller_summary.get("reference_state_identity", False))
    dsec_evaluations = int(controller_summary.get("dsec_evaluations", 0))
    total_evaluations = int(controller_summary.get("total_evaluations", 0))
    complete_runtime_transport = (
        controller_completed
        and dsec_evaluations == 57
        and len(workspace_rows) >= 57
        and _observed_calls(workspace_rows) == [1, 2, 3, 4]
    )

    header_path = package_dir / "src/xstar_tools/xstar/cpp/xstar_fixed_state_engine.h"
    engine_path = package_dir / "src/xstar_tools/xstar/cpp/fixed_state_engine.cpp"
    header = header_path.read_text(encoding="utf-8") if header_path.is_file() else ""
    engine = engine_path.read_text(encoding="utf-8") if engine_path.is_file() else ""
    abi_fields_present = all(name in header for name in ("global_xilevg", "global_bilevg", "global_rnisg"))
    global_xilevg_consumed = "runtime_input->global_xilevg" in engine
    bilevg_rnisg_consumed = "runtime_input->global_bilevg" in engine or "runtime_input->global_rnisg" in engine

    mg_gate = compared >= 7 and exact == compared and mg_runtime_observed
    workspace_gate = payload_ready and workspace_runtime_observed and abi_fields_present and global_xilevg_consumed

    execution_gate = "ACCEPT" if controller_completed else "RUN_REQUIRED"
    parity_gate = "ACCEPT" if controller_identity else ("REJECT" if controller_completed else "RUN_REQUIRED")
    result = {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT" if mg_gate and workspace_gate else "REJECT",
        "mg_primary_thermal_construction": {
            "status": "ACCEPT" if mg_gate else "REJECT",
            "mode": "abundance_weighting_plus_captured_call1_source_budget_oracle",
            "general_all_state_formula_qualified": False,
            "rows_compared": compared,
            "rows_exact": exact,
            "runtime_override_rows": len(mg_override_rows),
            "runtime_observed": mg_runtime_observed,
        },
        "call_start_workspace_transport": {
            "status": "ACCEPT" if workspace_gate else "REJECT",
            "payload_ready": payload_ready,
            "runtime_observed": workspace_runtime_observed,
            "runtime_rows": len(workspace_rows),
            "observed_calls": _observed_calls(workspace_rows),
            "complete_four_call_runtime_coverage": complete_runtime_transport,
            "changed_workspaces": list(CHANGED_WORKSPACES),
        },
        "global_level_workspace_transport": {
            "status": "ACCEPT" if workspace_gate else "REJECT",
            "abi_fields_present": abi_fields_present,
            "global_xilevg_consumed": global_xilevg_consumed,
            "global_bilevg_and_global_rnisg_consumed_by_native_families": bilevg_rnisg_consumed,
            "note": (
                "global_xilevg seeds mapped compact rows; global_bilevg and global_rnisg are transported "
                "and validated but remain unconsumed by most native rate families"
            ),
        },
        "native_controller": controller_summary,
        "gates": {
            "mg_primary_thermal_construction": "ACCEPT" if mg_gate else "REJECT",
            "five_workspace_transport": "ACCEPT" if workspace_gate else "REJECT",
            "four_call_workspace_runtime_coverage": "ACCEPT" if complete_runtime_transport else "RUN_REQUIRED",
            "complete_controller_execution": execution_gate,
            "complete_controller_parity": parity_gate,
            "thermal_parity": "ACCEPT" if controller_identity else "BLOCKED",
            "production_promotion": "BLOCKED",
        },
        "controller_evaluation_counts": {
            "dsec": dsec_evaluations,
            "total": total_evaluations,
        },
        "next_required_work": (
            "review exact complete controller and proceed to product parity"
            if controller_identity
            else (
                "diagnose the first post-transport controller divergence"
                if controller_completed
                else "run the complete post-Mg/post-transport controller parity gate"
            )
        ),
        "qualification_only": True,
        "production_promotion_ready": False,
    }
    write_json(output_dir / "mg_primary_workspace_transport_summary.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    prep_parser = subparsers.add_parser("prepare")
    prep_parser.add_argument("capture_dir", type=Path)
    prep_parser.add_argument("output_dir", type=Path)
    audit_parser = subparsers.add_parser("audit")
    audit_parser.add_argument("--package-dir", type=Path, default=Path("."))
    audit_parser.add_argument("--capture-dir", type=Path, required=True)
    audit_parser.add_argument("--native-dir", type=Path, required=True)
    audit_parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare(args.capture_dir.resolve(), args.output_dir.resolve())
        else:
            result = audit(
                args.package_dir.resolve(),
                args.capture_dir.resolve(),
                args.native_dir.resolve(),
                args.output_dir.resolve(),
            )
    except Exception as exc:  # qualification tools must preserve structured failure evidence
        result = {
            "schema": SCHEMA,
            "release": RELEASE,
            "result": "REJECT",
            "errors": [str(exc)],
            "qualification_only": True,
            "production_promotion_ready": False,
        }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["result"] == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
