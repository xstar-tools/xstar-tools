"""Capture an independent original-DSEC type-53 runtime-state contract.

The capture executes the untouched, hash-verified v0.6.47.2 Python DSEC path
at evaluation 60.  It freezes the complete 44-record type-53 row-46 aliased
manifold together with the full source ``epi/bremsa`` radiation workspace and
the dense inward/outward continuum optical-depth arrays used by that call.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
import struct
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

from . import v0472_dsec_row46_runtime_capture as parent

csv.field_size_limit(sys.maxsize)

RELEASE = "0.6.48.7.19.1"
SCHEMA = "xstar-tools-v0648717-type53-independent-runtime-state-capture-v1"
BUNDLE_SCHEMA = "xstar-tools-v0648717-type53-independent-runtime-state-oracle-v1"
TARGET_EVALUATION = 60
TARGET_DATA_TYPE = 53
TARGET_RATE_TYPE = 7
TARGET_RECORDS = 44
TARGET_ANSWERS = TARGET_RECORDS * 6
TARGET_TERMS = TARGET_RECORDS * 4

RECORDS_NAME = "type53_independent_state_runtime_records.csv"
TERMS_NAME = "type53_independent_state_runtime_matrix_terms.csv"
RADIATION_NAME = "dsec_radiation_workspace.csv"
TAU_NAME = "dsec_continuum_tau_workspace.csv"
TRACE_NAME = parent.TRACE_NAME
REPORT_NAME = "independent_state_capture_report.json"
MANIFEST_NAME = "independent_state_manifest.json"
VERIFY_NAME = "independent_state_verification.json"


def _bits(value: str | float) -> bytes:
    return struct.pack(">d", float(value))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        raise ValueError(f"cannot write empty CSV: {path.name}")
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def freeze_from_parent(bundle: Path) -> dict[str, Any]:
    source_records = _read_csv(bundle / parent.RECORDS_NAME)
    source_terms = _read_csv(bundle / parent.TERMS_NAME)
    records = [
        row for row in source_records
        if int(row["global_evaluation_ordinal"]) == TARGET_EVALUATION
        and int(row["data_type"]) == TARGET_DATA_TYPE
        and int(row["rate_type"]) == TARGET_RATE_TYPE
    ]
    selected = {(int(row["source_position"]), int(row["record"])) for row in records}
    terms = [
        row for row in source_terms
        if int(row["global_evaluation_ordinal"]) == TARGET_EVALUATION
        and int(row["data_type"]) == TARGET_DATA_TYPE
        and int(row["rate_type"]) == TARGET_RATE_TYPE
        and (int(row["source_position"]), int(row["record"])) in selected
    ]
    records.sort(key=lambda row: int(row["source_position"]))
    terms.sort(key=lambda row: int(row["source_order_index"]))
    _write_csv(bundle / RECORDS_NAME, records)
    _write_csv(bundle / TERMS_NAME, terms)
    parent_report = json.loads((bundle / parent.REPORT_NAME).read_text())
    report = {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT",
        "capture_kind": "actual_v06472_dsec_type53_row46_independent_runtime_state_capture",
        "actual_dsec_runtime_capture": True,
        "target_evaluation_ordinal": TARGET_EVALUATION,
        "target_full_row": 46,
        "records": len(records),
        "answers": len(records) * 6,
        "matrix_terms": len(terms),
        "dsec_evaluations_observed": int(parent_report.get("dsec_evaluations_observed", 0)),
        "dsec_radiation_bins": int(parent_report.get("dsec_radiation_bins", 0)),
        "continuum_tau_count": int(parent_report.get("continuum_tau_count", 0)),
        "parent_capture_report": parent.REPORT_NAME,
        "qualification_only": True,
        "production_promotion_ready": False,
    }
    _write_json(bundle / REPORT_NAME, report)
    result = verify(bundle)
    _write_json(bundle / VERIFY_NAME, result)
    files = {}
    for name in (RECORDS_NAME, TERMS_NAME, RADIATION_NAME, TAU_NAME, TRACE_NAME, REPORT_NAME):
        path = bundle / name
        if path.is_file():
            files[name] = {"sha256": _sha256(path), "size_bytes": path.stat().st_size}
    _write_json(bundle / MANIFEST_NAME, {**result, "immutable": result["result"] == "ACCEPT", "files": files})
    return result


def verify(bundle: Path) -> dict[str, Any]:
    errors: list[str] = []
    required = (RECORDS_NAME, TERMS_NAME, RADIATION_NAME, TAU_NAME, TRACE_NAME, REPORT_NAME)
    for name in required:
        if not (bundle / name).is_file():
            errors.append(f"missing:{name}")
    if errors:
        return {
            "schema": BUNDLE_SCHEMA,
            "release": RELEASE,
            "result": "REJECT",
            "errors": errors,
            "qualification_only": True,
            "production_promotion_ready": False,
        }
    records = _read_csv(bundle / RECORDS_NAME)
    terms = _read_csv(bundle / TERMS_NAME)
    radiation = _read_csv(bundle / RADIATION_NAME)
    tau = _read_csv(bundle / TAU_NAME)
    trace = _read_csv(bundle / TRACE_NAME)
    report = json.loads((bundle / REPORT_NAME).read_text())

    if len(records) != TARGET_RECORDS:
        errors.append(f"records={len(records)}")
    if len(terms) != TARGET_TERMS:
        errors.append(f"matrix_terms={len(terms)}")
    if len({(int(r["source_position"]), int(r["record"])) for r in records}) != len(records):
        errors.append("record_identity_not_unique")
    if any(int(r["global_evaluation_ordinal"]) != TARGET_EVALUATION for r in records):
        errors.append("record_evaluation_mismatch")
    if any(int(r["data_type"]) != TARGET_DATA_TYPE or int(r["rate_type"]) != TARGET_RATE_TYPE for r in records):
        errors.append("record_family_mismatch")
    for row in records:
        for field in (
            "tau_in", "tau_out", "ptmp1", "ptmp2", "covering_fraction",
            "temperature_k", "hydrogen_density_cm3", "electron_fraction_xee",
            "ans1", "ans2", "ans3", "ans4", "ans5", "ans6",
        ):
            try:
                value = float(row[field])
            except Exception:
                errors.append(f"non_numeric:{row.get('record')}:{field}")
                break
            if not math.isfinite(value):
                errors.append(f"non_finite:{row.get('record')}:{field}")
                break

    term_counts = Counter((int(r["source_position"]), int(r["record"])) for r in terms)
    if len(term_counts) != TARGET_RECORDS or set(term_counts.values()) != {4}:
        errors.append("four_term_inventory_mismatch")
    order = [int(r["source_order_index"]) for r in terms]
    if order != sorted(order) or len(order) != len(set(order)):
        errors.append("source_order_not_strict")
    if any(int(r["global_evaluation_ordinal"]) != TARGET_EVALUATION for r in terms):
        errors.append("term_evaluation_mismatch")

    rad_indices = [int(r["grid_index"]) for r in radiation]
    energies = [float(r["energy_ev"]) for r in radiation]
    bremsa = [float(r["bremsa"]) for r in radiation]
    if len(radiation) < 3:
        errors.append(f"radiation_bins={len(radiation)}")
    if rad_indices != list(range(1, len(radiation) + 1)):
        errors.append("radiation_indices_not_dense")
    if any(not math.isfinite(v) for v in energies + bremsa):
        errors.append("radiation_non_finite")
    if any(b <= a for a, b in zip(energies, energies[1:])):
        errors.append("radiation_energy_not_strictly_increasing")

    tau_indices = [int(r["continuum_index"]) for r in tau]
    if tau_indices != list(range(1, len(tau) + 1)):
        errors.append("continuum_tau_indices_not_dense")
    tau_by_index = {int(r["continuum_index"]): r for r in tau}
    if any(not math.isfinite(float(r[f])) for r in tau for f in ("tau_in", "tau_out")):
        errors.append("continuum_tau_non_finite")
    max_escape = max((int(r.get("escape_index") or 0) for r in records), default=0)
    if max_escape > len(tau):
        errors.append(f"continuum_tau_short:{len(tau)}<{max_escape}")
    tau_exact = 0
    for row in records:
        index = int(row.get("escape_index") or 0)
        workspace = tau_by_index.get(index)
        if workspace and _bits(row["tau_in"]) == _bits(workspace["tau_in"]) and _bits(row["tau_out"]) == _bits(workspace["tau_out"]):
            tau_exact += 1
    if tau_exact != len(records):
        errors.append(f"record_tau_workspace_exact={tau_exact}/{len(records)}")

    if not bool(report.get("actual_dsec_runtime_capture")):
        errors.append("not_actual_dsec_capture")
    if int(report.get("target_evaluation_ordinal", -1)) != TARGET_EVALUATION:
        errors.append("report_evaluation_mismatch")
    if len(trace) < TARGET_EVALUATION:
        errors.append("insufficient_dsec_trace")

    hashes = {name: _sha256(bundle / name) for name in required}
    return {
        "schema": BUNDLE_SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT" if not errors else "REJECT",
        "capture_kind": report.get("capture_kind"),
        "actual_dsec_runtime_capture": bool(report.get("actual_dsec_runtime_capture")),
        "target_evaluation_ordinal": TARGET_EVALUATION,
        "records": len(records),
        "answers": len(records) * 6,
        "matrix_terms": len(terms),
        "dsec_radiation_bins": len(radiation),
        "continuum_tau_count": len(tau),
        "record_tau_workspace_ieee_exact": tau_exact,
        "maximum_continuum_index_used": max_escape,
        "dsec_evaluations_observed": len(trace),
        "record_oracle_sha256": hashes[RECORDS_NAME],
        "matrix_terms_sha256": hashes[TERMS_NAME],
        "dsec_radiation_sha256": hashes[RADIATION_NAME],
        "continuum_tau_sha256": hashes[TAU_NAME],
        "trace_sha256": hashes[TRACE_NAME],
        "errors": errors,
        "qualification_only": True,
        "production_promotion_ready": False,
    }


def run_capture(
    source_archive: Path,
    lowered_program: Path,
    atdb_path: Path,
    output_dir: Path,
    *,
    parameters_json: Path,
    coheat_path: Path | None = None,
) -> dict[str, Any]:
    parent.run_capture(
        source_archive,
        lowered_program,
        atdb_path,
        output_dir,
        parameters_json=parameters_json,
        coheat_path=coheat_path,
        target_evaluation=TARGET_EVALUATION,
    )
    return freeze_from_parent(output_dir)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("source_archive", type=Path)
    run.add_argument("lowered_program", type=Path)
    run.add_argument("atdb_path", type=Path)
    run.add_argument("output_dir", type=Path)
    run.add_argument("--parameters-json", type=Path, required=True)
    run.add_argument("--coheat-path", type=Path)
    check = sub.add_parser("verify")
    check.add_argument("bundle", type=Path)
    check.add_argument("--output-json", type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "run":
            result = run_capture(
                args.source_archive,
                args.lowered_program,
                args.atdb_path,
                args.output_dir,
                parameters_json=args.parameters_json,
                coheat_path=args.coheat_path,
            )
        else:
            result = verify(args.bundle)
        if getattr(args, "output_json", None):
            _write_json(args.output_json, result)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["result"] == "ACCEPT" else 2
    except Exception as exc:
        result = {
            "schema": BUNDLE_SCHEMA,
            "release": RELEASE,
            "result": "REJECT",
            "errors": [str(exc)],
            "qualification_only": True,
            "production_promotion_ready": False,
        }
        if getattr(args, "output_json", None):
            _write_json(args.output_json, result)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
