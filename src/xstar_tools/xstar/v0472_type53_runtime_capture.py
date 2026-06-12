"""Exact v0.6.47.2 type-53 fixed-state evaluator replay for v0.6.48.7.5.

This module executes the untouched ``xstar_tools==0.6.47.2``
``evaluate_type53_ucalc_record`` implementation in an isolated subprocess.  It
replays the 31 He II type-53 records at the frozen evaluation-61 state using
packed coefficients from the lowered ATDB program and the frozen 9,999-bin
radiation field.  The resulting ans1--ans6 values may be frozen as an immutable
runtime oracle.  This is a fixed-state evaluator replay, not a complete DSEC
controller rerun.
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
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any, Mapping

from .he_bound_free_audit import _resolve_records_csv
from .type53_semantics import ANS_NAMES, ORACLE_FIELDS, freeze_reference, verify_reference

RELEASE = "0.6.48.7.5"
SCHEMA = "xstar-tools-v064873-v0472-type53-runtime-capture-v1"
SOURCE_VERSION = "0.6.47.2"
SOURCE_ARCHIVE_SHA256 = "85ff0184bd95daf046fd28923837239c5192f8d309b0716556d1d804b0453060"
SOURCE_MODULE_RELATIVE = Path("src/xstar_tools/rates_type53.py")
CAPTURE_FIELDS = ORACLE_FIELDS + [
    "temperature_k", "hydrogen_density_cm3", "electron_fraction_xee",
    "electron_density_cm3", "radiation_bins", "threshold_eV",
    "bound_energy_eV", "destination_energy_eV", "bound_statistical_weight",
    "destination_statistical_weight", "rnist", "sumr", "sumi", "sumh",
    "sumh2", "sumc", "sumc2", "nb1_1based", "klmax_1based",
    "payload_sha256", "source_package_version", "source_module_sha256",
]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _safe_extract(archive: Path, destination: Path) -> None:
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as handle:
        for member in handle.getmembers():
            target = (destination / member.name).resolve()
            if destination != target and destination not in target.parents:
                raise ValueError(f"unsafe source-archive member: {member.name}")
            if member.issym() or member.islnk():
                raise ValueError(f"links are not accepted in source archive: {member.name}")
        try:
            handle.extractall(destination, filter="fully_trusted")
        except TypeError:  # Python < 3.12
            handle.extractall(destination)


def _find_source_root(extracted: Path) -> Path:
    candidates = [path.parent for path in extracted.glob("*/pyproject.toml")]
    if len(candidates) != 1:
        raise ValueError(f"expected one extracted source root, found {len(candidates)}")
    root = candidates[0].resolve()
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    if f'version = "{SOURCE_VERSION}"' not in pyproject:
        raise ValueError("source archive is not xstar_tools 0.6.47.2")
    return root


def _state_path(audit_output: Path, evaluation: int) -> Path:
    candidates = (
        audit_output / "diagnostics" / f"evaluation_{evaluation:04d}_state.json",
        audit_output / f"evaluation_{evaluation:04d}_state.json",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(f"cannot find evaluation-{evaluation} state JSON under {audit_output}")


def _program_inputs(lowered_program: Path) -> dict[str, Any]:
    required = ("manifest.txt", "rows.csv", "records.csv", "reals.txt")
    result: dict[str, Any] = {}
    for name in required:
        path = lowered_program / name
        if not path.is_file():
            raise FileNotFoundError(f"lowered program is missing {name}")
        result[name] = {"sha256": _sha256(path), "size_bytes": path.stat().st_size}
    manifest = (lowered_program / "manifest.txt").read_text(encoding="utf-8")
    if "active_atdb_lowered=true" not in manifest:
        raise ValueError("lowered program is not an active-ATDB program")
    if "active_element_z=1,2,12" not in manifest:
        raise ValueError("lowered program does not contain the H/He/Mg qualification scope")
    return result


def _template_identity(audit_output: Path, evaluation: int) -> tuple[Path, list[dict[str, int]]]:
    records_csv = _resolve_records_csv(audit_output, evaluation)
    with records_csv.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        needed = {"evaluation_ordinal", "source_position", "record", "element_z", "ion_stage", "data_type", "lower_row", "upper_row"}
        missing = sorted(needed.difference(reader.fieldnames or []))
        if missing:
            raise ValueError("audit records are missing fields: " + ", ".join(missing))
        rows = [
            {
                "evaluation_ordinal": int(row["evaluation_ordinal"]),
                "source_position": int(row["source_position"]),
                "record": int(row["record"]),
                "element_z": int(row["element_z"]),
                "ion_stage": int(row["ion_stage"]),
                "data_type": int(row["data_type"]),
                "lower_row": int(row["lower_row"]),
                "upper_row": int(row["upper_row"]),
            }
            for row in reader
            if int(row["evaluation_ordinal"]) == evaluation
            and int(row["element_z"]) == 2
            and int(row["ion_stage"]) == 2
            and int(row["data_type"]) == 53
        ]
    rows.sort(key=lambda row: (row["source_position"], row["record"]))
    if len(rows) != 31 or len({(row["source_position"], row["record"]) for row in rows}) != 31:
        raise ValueError("audit must contain exactly 31 unique evaluation-61 He II type-53 records")
    return records_csv.resolve(), rows


_REPLAY_SCRIPT = r'''
from __future__ import annotations
import csv, hashlib, json, math, pathlib, sys

cfg = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
out_csv = pathlib.Path(sys.argv[2])
out_report = pathlib.Path(sys.argv[3])

import xstar_tools
from xstar_tools.rates_type53 import Type53LiveRadiationState, evaluate_type53_ucalc_record

version = str(getattr(xstar_tools, "__version__", ""))
if version != "0.6.47.2":
    raise RuntimeError(f"imported xstar_tools {version!r}, expected 0.6.47.2")

root = pathlib.Path(cfg["lowered_program"])
reals = [float(value) for value in (root / "reals.txt").read_text(encoding="utf-8").splitlines()]
with (root / "records.csv").open(newline="", encoding="utf-8") as handle:
    program_records = {int(row["record"]): dict(row) for row in csv.DictReader(handle)}
with (root / "rows.csv").open(newline="", encoding="utf-8") as handle:
    levels = {(int(row["element_index"]), int(row["row"])): dict(row) for row in csv.DictReader(handle)}

energy = []
incident = []
with pathlib.Path(cfg["radiation_csv"]).open(newline="", encoding="utf-8") as handle:
    reader = csv.DictReader(handle)
    if not {"energy", "incident"}.issubset(reader.fieldnames or []):
        raise RuntimeError("radiation CSV must contain energy and incident columns")
    for row in reader:
        energy.append(float(row["energy"]))
        incident.append(float(row["incident"]))
if len(energy) != int(cfg["radiation_bins"]):
    raise RuntimeError(f"radiation bin count mismatch: {len(energy)}")

radiation = Type53LiveRadiationState.from_sequences(
    energy,
    incident,
    [0.0] * len(energy),
    metadata={
        "type53_grid_policy": "full_high_resolution_epi_bremsa_for_side_effects",
        "type53_grid_source": "frozen_v06472_full_radiation_csv",
        "type53_full_grid_points": len(energy),
        "type53_reduced_grid_points": 0,
    },
)

def sha_values(values):
    digest = hashlib.sha256()
    for value in values:
        digest.update(float(value).hex().encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()

rows = []
for identity in cfg["records"]:
    record_number = int(identity["record"])
    rec = program_records[record_number]
    if int(rec["source_position"]) != int(identity["source_position"]):
        raise RuntimeError(f"source-position mismatch for record {record_number}")
    element_index = int(rec["element_index"])
    lower_index = int(rec["lower_row"])
    upper_index = int(rec["upper_row"])
    if lower_index != int(identity["lower_row"]) or upper_index != int(identity["upper_row"]):
        raise RuntimeError(f"row mapping mismatch for record {record_number}")
    lower = levels[(element_index, lower_index)]
    upper = levels[(element_index, upper_index)]
    offset = int(rec["real_offset"])
    count = int(rec["real_count"])
    payload = reals[offset:offset + count]
    if len(payload) != count or count < 4 or count % 2:
        raise RuntimeError(f"invalid type-53 payload for record {record_number}")
    decoded = {
        "energy_above_threshold_ryd": payload[0::2],
        "cross_section_cm2": payload[1::2],
        "threshold_eV": float(rec["line_energy_ev"]),
        "bound_statistical_weight": float(lower["statistical_weight"]),
        "continuum_statistical_weight": float(upper["statistical_weight"]),
        "destination_statistical_weight": float(upper["statistical_weight"]),
        "continuum_energy_eV": float(upper["energy_ev"]),
        "bound_energy_eV": float(lower["energy_ev"]),
        "destination_energy_eV": float(upper["energy_ev"]),
    }
    result = evaluate_type53_ucalc_record(
        decoded,
        radiation,
        temperature_k=float(cfg["temperature_k"]),
        xpx_cm3=float(cfg["hydrogen_density_cm3"]),
        electron_fraction_xee=float(cfg["electron_fraction_xee"]),
        ptmp1=1.0,
        ptmp2=0.0,
        lfast=2,
        abund1=0.0,
        abund2=0.0,
    )
    if result.get("status") != "evaluated":
        raise RuntimeError(f"record {record_number} returned {result.get('status')}")
    diag = dict(result.get("phint53_diagnostics", {}))
    row = {
        **identity,
        "ans1": float(result["ans1_photoionization_s^-1"]),
        "ans2": float(result["ans2_milne_recombination_s^-1"]),
        "ans3": float(result["ans3_cooling_signed_erg_s^-1"]),
        "ans4": float(result["ans4_heating_signed_erg_s^-1"]),
        "ans5": float(result["ans5_electron_pov_cooling_signed_erg_s^-1"]),
        "ans6": float(result["ans6_electron_pov_heating_signed_erg_s^-1"]),
        "temperature_k": float(cfg["temperature_k"]),
        "hydrogen_density_cm3": float(cfg["hydrogen_density_cm3"]),
        "electron_fraction_xee": float(cfg["electron_fraction_xee"]),
        "electron_density_cm3": float(cfg["hydrogen_density_cm3"]) * float(cfg["electron_fraction_xee"]),
        "radiation_bins": len(energy),
        "threshold_eV": float(rec["line_energy_ev"]),
        "bound_energy_eV": float(lower["energy_ev"]),
        "destination_energy_eV": float(upper["energy_ev"]),
        "bound_statistical_weight": float(lower["statistical_weight"]),
        "destination_statistical_weight": float(upper["statistical_weight"]),
        "rnist": float(result.get("rnist", math.nan)),
        "sumr": float(result.get("sumr", math.nan)),
        "sumi": float(result.get("sumi", math.nan)),
        "sumh": float(result.get("sumh", math.nan)),
        "sumh2": float(result.get("sumh2", math.nan)),
        "sumc": float(result.get("sumc", math.nan)),
        "sumc2": float(result.get("sumc2", math.nan)),
        "nb1_1based": int(diag.get("nb1_1based", 0)),
        "klmax_1based": int(diag.get("klmax_1based", 0)),
        "payload_sha256": sha_values(payload),
        "source_package_version": version,
        "source_module_sha256": cfg["source_module_sha256"],
    }
    if any(not math.isfinite(float(row[f"ans{i}"])) for i in range(1, 7)):
        raise RuntimeError(f"record {record_number} returned non-finite answers")
    rows.append(row)

fields = cfg["capture_fields"]
out_csv.parent.mkdir(parents=True, exist_ok=True)
with out_csv.open("w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)

report = {
    "schema": cfg["schema"],
    "release": cfg["release"],
    "result": "ACCEPT",
    "capture_kind": "exact_v06472_fixed_state_evaluator_replay",
    "full_dsec_runtime_capture": False,
    "source_package_version": version,
    "source_archive_sha256": cfg["source_archive_sha256"],
    "source_module_sha256": cfg["source_module_sha256"],
    "evaluation_ordinal": int(cfg["evaluation_ordinal"]),
    "records": len(rows),
    "temperature_k": float(cfg["temperature_k"]),
    "hydrogen_density_cm3": float(cfg["hydrogen_density_cm3"]),
    "electron_fraction_xee": float(cfg["electron_fraction_xee"]),
    "radiation_bins": len(energy),
    "output_csv": str(out_csv.resolve()),
    "production_promotion_ready": False,
}
out_report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
'''


def validate_capture(capture_csv: Path, *, audit_output: Path | None = None, evaluation: int = 61) -> dict[str, Any]:
    capture_csv = capture_csv.resolve()
    errors: list[str] = []
    with capture_csv.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = sorted(set(CAPTURE_FIELDS).difference(reader.fieldnames or []))
        if missing:
            errors.append("missing fields: " + ", ".join(missing))
        rows = list(reader)
    if len(rows) != 31:
        errors.append(f"expected 31 rows, observed {len(rows)}")
    keys = [(int(row.get("source_position", 0)), int(row.get("record", 0))) for row in rows]
    if len(set(keys)) != len(keys):
        errors.append("duplicate source-position/record keys")
    if any(int(row.get("evaluation_ordinal", 0)) != evaluation for row in rows):
        errors.append("capture contains an unexpected evaluation ordinal")
    for line, row in enumerate(rows, start=2):
        if row.get("source_package_version") != SOURCE_VERSION:
            errors.append(f"line {line}: unexpected source package version")
        for name in ANS_NAMES:
            try:
                value = float(row.get(name, ""))
            except ValueError:
                value = math.nan
            if not math.isfinite(value):
                errors.append(f"line {line}: {name} is non-finite")
    if audit_output is not None:
        _, expected = _template_identity(audit_output.resolve(), evaluation)
        expected_keys = [(row["source_position"], row["record"]) for row in expected]
        if keys != expected_keys:
            errors.append("capture identity/order does not match the audit records")
    return {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT" if not errors else "REJECT",
        "capture_csv": str(capture_csv),
        "records": len(rows),
        "errors": errors,
        "sha256": _sha256(capture_csv),
        "production_promotion_ready": False,
    }


def capture_runtime(
    source_archive: Path,
    lowered_program: Path,
    audit_output: Path,
    radiation_csv: Path,
    output_csv: Path,
    *,
    evaluation: int = 61,
    output_json: Path | None = None,
) -> dict[str, Any]:
    source_archive = source_archive.resolve()
    lowered_program = lowered_program.resolve()
    audit_output = audit_output.resolve()
    radiation_csv = radiation_csv.resolve()
    output_csv = output_csv.resolve()
    output_json = (output_json or output_csv.with_suffix(".capture.json")).resolve()

    observed_source_sha = _sha256(source_archive)
    if observed_source_sha != SOURCE_ARCHIVE_SHA256:
        raise ValueError(f"v0.6.47.2 source archive SHA-256 mismatch: {observed_source_sha}")
    if not radiation_csv.is_file():
        raise FileNotFoundError(radiation_csv)
    program_inputs = _program_inputs(lowered_program)
    records_csv, identities = _template_identity(audit_output, evaluation)
    state_file = _state_path(audit_output, evaluation)
    state = json.loads(state_file.read_text(encoding="utf-8"))
    if int(state.get("evaluation_ordinal", 0)) != evaluation:
        raise ValueError("state JSON evaluation ordinal mismatch")
    if int(state.get("radiation_bin_count", 0)) != 9999:
        raise ValueError("capture requires the full 9,999-bin evaluation state")

    with tempfile.TemporaryDirectory(prefix="v064873-v0472-") as temp_name:
        temp = Path(temp_name)
        extracted = temp / "source"
        _safe_extract(source_archive, extracted)
        source_root = _find_source_root(extracted)
        source_module = source_root / SOURCE_MODULE_RELATIVE
        source_module_sha = _sha256(source_module)
        config = {
            "schema": SCHEMA,
            "release": RELEASE,
            "source_archive_sha256": observed_source_sha,
            "source_module_sha256": source_module_sha,
            "lowered_program": str(lowered_program),
            "radiation_csv": str(radiation_csv),
            "radiation_bins": int(state["radiation_bin_count"]),
            "evaluation_ordinal": evaluation,
            "temperature_k": float(state["temperature_k"]),
            "hydrogen_density_cm3": float(state["hydrogen_density_cm3"]),
            "electron_fraction_xee": float(state["electron_fraction_input"]),
            "records": identities,
            "capture_fields": CAPTURE_FIELDS,
        }
        config_path = temp / "capture_config.json"
        _write_json(config_path, config)
        replay_path = temp / "replay.py"
        replay_path.write_text(_REPLAY_SCRIPT, encoding="utf-8")
        raw_report = temp / "replay_report.json"
        env = dict(os.environ)
        env["PYTHONPATH"] = str(source_root / "src")
        subprocess.run(
            [sys.executable, str(replay_path), str(config_path), str(output_csv), str(raw_report)],
            check=True,
            cwd=str(source_root),
            env=env,
        )
        replay_report = json.loads(raw_report.read_text(encoding="utf-8"))

    validation = validate_capture(output_csv, audit_output=audit_output, evaluation=evaluation)
    if validation["result"] != "ACCEPT":
        raise ValueError("captured runtime oracle failed validation: " + "; ".join(validation["errors"]))
    report = {
        **replay_report,
        "output_json": str(output_json),
        "capture_csv_sha256": _sha256(output_csv),
        "capture_csv_size_bytes": output_csv.stat().st_size,
        "source_archive": str(source_archive),
        "source_archive_sha256": observed_source_sha,
        "source_records_csv": str(records_csv),
        "source_records_csv_sha256": _sha256(records_csv),
        "state_json": str(state_file),
        "state_json_sha256": _sha256(state_file),
        "radiation_csv": str(radiation_csv),
        "radiation_csv_sha256": _sha256(radiation_csv),
        "lowered_program": str(lowered_program),
        "lowered_program_inputs": program_inputs,
        "source_runtime_values_present": True,
        "oracle_freeze_ready": True,
        "fixed_state_parity": False,
        "production_promotion_ready": False,
    }
    _write_json(output_json, report)
    return report


def capture_and_freeze(
    source_archive: Path,
    lowered_program: Path,
    audit_output: Path,
    radiation_csv: Path,
    bundle_dir: Path,
    *,
    evaluation: int = 61,
) -> dict[str, Any]:
    bundle_dir = bundle_dir.resolve()
    work_dir = bundle_dir.parent / (bundle_dir.name + ".capture-work")
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True)
    capture_csv = work_dir / "type53_runtime_capture.csv"
    capture_json = work_dir / "capture_report.json"
    capture = capture_runtime(
        source_archive, lowered_program, audit_output, radiation_csv, capture_csv,
        evaluation=evaluation, output_json=capture_json,
    )
    frozen = freeze_reference(capture_csv, bundle_dir, source_archive_sha256=SOURCE_ARCHIVE_SHA256)
    portable_capture = {
        "schema": capture["schema"],
        "release": capture["release"],
        "result": capture["result"],
        "capture_kind": capture["capture_kind"],
        "full_dsec_runtime_capture": False,
        "source_package_version": capture["source_package_version"],
        "source_archive_sha256": capture["source_archive_sha256"],
        "source_module_sha256": capture["source_module_sha256"],
        "evaluation_ordinal": capture["evaluation_ordinal"],
        "records": capture["records"],
        "temperature_k": capture["temperature_k"],
        "hydrogen_density_cm3": capture["hydrogen_density_cm3"],
        "electron_fraction_xee": capture["electron_fraction_xee"],
        "radiation_bins": capture["radiation_bins"],
        "capture_csv_sha256": capture["capture_csv_sha256"],
        "capture_csv_size_bytes": capture["capture_csv_size_bytes"],
        "source_records_csv_sha256": capture["source_records_csv_sha256"],
        "state_json_sha256": capture["state_json_sha256"],
        "radiation_csv_sha256": capture["radiation_csv_sha256"],
        "lowered_program_inputs": capture["lowered_program_inputs"],
        "source_runtime_values_present": True,
        "oracle_freeze_ready": True,
        "production_promotion_ready": False,
    }
    _write_json(bundle_dir / "capture_provenance.json", portable_capture)
    shutil.copy2(capture_csv, bundle_dir / "type53_runtime_capture_full.csv")
    manifest_path = bundle_dir / "reference_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for name in ("capture_provenance.json", "type53_runtime_capture_full.csv"):
        path = bundle_dir / name
        manifest.setdefault("files", {})[name] = {"sha256": _sha256(path), "size_bytes": path.stat().st_size}
    manifest["capture_kind"] = capture["capture_kind"]
    manifest["full_dsec_runtime_capture"] = False
    manifest["source_module_sha256"] = capture["source_module_sha256"]
    manifest["lowered_program_inputs"] = capture["lowered_program_inputs"]
    manifest["state_json_sha256"] = capture["state_json_sha256"]
    manifest["radiation_csv_sha256"] = capture["radiation_csv_sha256"]
    manifest["release"] = RELEASE
    _write_json(manifest_path, manifest)
    verification = verify_reference(bundle_dir)
    if verification["result"] != "ACCEPT":
        raise ValueError("frozen runtime oracle failed verification")
    shutil.rmtree(work_dir)
    return {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT",
        "bundle_directory": str(bundle_dir),
        "records": 31,
        "capture": capture,
        "freeze": frozen,
        "verification": verification,
        "runtime_oracle_available": True,
        "full_dsec_runtime_capture": False,
        "fixed_state_parity": False,
        "production_promotion_ready": False,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("capture")
    p.add_argument("source_archive", type=Path)
    p.add_argument("lowered_program", type=Path)
    p.add_argument("audit_output", type=Path)
    p.add_argument("radiation_csv", type=Path)
    p.add_argument("output_csv", type=Path)
    p.add_argument("--evaluation", type=int, default=61)
    p.add_argument("--output-json", type=Path)
    p = sub.add_parser("capture-and-freeze")
    p.add_argument("source_archive", type=Path)
    p.add_argument("lowered_program", type=Path)
    p.add_argument("audit_output", type=Path)
    p.add_argument("radiation_csv", type=Path)
    p.add_argument("bundle_dir", type=Path)
    p.add_argument("--evaluation", type=int, default=61)
    p.add_argument("--output-json", type=Path)
    p = sub.add_parser("validate")
    p.add_argument("capture_csv", type=Path)
    p.add_argument("--audit-output", type=Path)
    p.add_argument("--evaluation", type=int, default=61)
    p.add_argument("--output-json", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    output_json = getattr(args, "output_json", None)
    try:
        if args.command == "capture":
            result = capture_runtime(
                args.source_archive, args.lowered_program, args.audit_output,
                args.radiation_csv, args.output_csv, evaluation=args.evaluation,
                output_json=output_json,
            )
            output = (output_json or args.output_csv.with_suffix(".capture.json")).resolve()
        elif args.command == "capture-and-freeze":
            result = capture_and_freeze(
                args.source_archive, args.lowered_program, args.audit_output,
                args.radiation_csv, args.bundle_dir, evaluation=args.evaluation,
            )
            output = (output_json or args.bundle_dir.resolve() / "capture_and_freeze_report.json").resolve()
            _write_json(output, result)
        else:
            result = validate_capture(args.capture_csv, audit_output=args.audit_output, evaluation=args.evaluation)
            output = (output_json or args.capture_csv.with_suffix(".validate.json")).resolve()
            _write_json(output, result)
        printable = dict(result)
        printable["output_json"] = str(output)
        print(json.dumps(printable, indent=2, sort_keys=True))
        return 0 if result.get("result") == "ACCEPT" else 1
    except Exception as exc:
        if output_json and output_json.resolve().exists():
            output_json.resolve().unlink()
        print(f"v0.6.47.2 type-53 runtime capture failed: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
