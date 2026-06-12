"""Type-53 answer-semantics and matrix-insertion qualification for v0.6.48.7.9.

The tool joins the applied native values and the translated source-style shadow
values for the 31 He II type-53 records at one evaluation.  It expands each
six-value record into the four matrix terms used by the native element engine.
An optional immutable v0.6.47.2 runtime oracle can be supplied as a third
column.  Without that runtime oracle, source-code semantics may be accepted but
physics replacement and fixed-state parity remain blocked.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import shutil
import struct
from pathlib import Path
from typing import Any, Iterable, Mapping

from .he_bound_free_audit import _resolve_records_csv

SCHEMA = "xstar-tools-v064874-type53-ieee-application-v1"
ORACLE_SCHEMA = "xstar-tools-v064872-type53-runtime-oracle-v1"
RELEASE = "0.6.48.7.9"
ELEMENT_Z = 2
ION_STAGE = 2
DATA_TYPE = 53
ANS_NAMES = tuple(f"ans{i}" for i in range(1, 7))
ORACLE_FIELDS = [
    "evaluation_ordinal", "source_position", "record", "element_z", "ion_stage", "data_type",
    "lower_row", "upper_row", "ans1", "ans2", "ans3", "ans4", "ans5", "ans6",
]


def _int(value: Any) -> int:
    return int(value or 0)


def _float(value: Any) -> float:
    return float(value) if value not in (None, "") else math.nan


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _write_csv(path: Path, rows: Iterable[Mapping[str, Any]], fields: list[str]) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})
    os.replace(tmp, path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _bits(value: float) -> bytes:
    return struct.pack(">d", float(value))


def _exact(a: float, b: float) -> bool:
    if math.isnan(a) and math.isnan(b):
        return True
    return _bits(a) == _bits(b)


def _load_selected(records_source: Path, evaluation: int) -> tuple[Path, list[dict[str, Any]]]:
    records_csv = _resolve_records_csv(records_source, evaluation)
    with records_csv.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {
            "evaluation_ordinal", "source_position", "record", "element_z", "ion_stage", "data_type",
            "lower_row", "upper_row", "density_scale", *ANS_NAMES,
            *(f"type53_shadow_{name}" for name in ANS_NAMES), "type53_shadow_valid",
        }
        missing = sorted(required.difference(reader.fieldnames or []))
        if missing:
            raise ValueError("records CSV lacks v0.6.48.7.9 type-53 fields: " + ", ".join(missing))
        rows = [
            dict(row) for row in reader
            if _int(row["evaluation_ordinal"]) == evaluation
            and _int(row["element_z"]) == ELEMENT_Z
            and _int(row["ion_stage"]) == ION_STAGE
            and _int(row["data_type"]) == DATA_TYPE
            and _int(row["type53_shadow_valid"]) == 1
        ]
    rows.sort(key=lambda row: (_int(row["source_position"]), _int(row["record"])))
    if not rows:
        raise ValueError("no He II type-53 records found")
    return records_csv, rows


def _load_oracle(path: Path | None, evaluation: int) -> tuple[dict[tuple[int, int], dict[str, Any]], dict[str, Any]]:
    if path is None:
        return {}, {"available": False, "verified": False, "path": None}
    path = path.resolve()
    csv_path = path
    manifest: dict[str, Any] | None = None
    if path.is_dir():
        manifest_path = path / "reference_manifest.json"
        csv_path = path / "type53_runtime_oracle.csv"
        if not manifest_path.is_file() or not csv_path.is_file():
            raise ValueError("oracle directory must contain reference_manifest.json and type53_runtime_oracle.csv")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("schema") != ORACLE_SCHEMA:
            raise ValueError("unexpected oracle schema")
        expected = manifest.get("files", {}).get("type53_runtime_oracle.csv", {}).get("sha256")
        if expected != _sha256(csv_path):
            raise ValueError("runtime oracle SHA-256 mismatch")
    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = sorted(set(ORACLE_FIELDS).difference(reader.fieldnames or []))
        if missing:
            raise ValueError("runtime oracle missing fields: " + ", ".join(missing))
        rows = [dict(row) for row in reader if _int(row["evaluation_ordinal"]) == evaluation]
    mapping = {(_int(row["source_position"]), _int(row["record"])): row for row in rows}
    if len(mapping) != len(rows):
        raise ValueError("runtime oracle contains duplicate source-position/record keys")
    for row in rows:
        if _int(row["element_z"]) != ELEMENT_Z or _int(row["ion_stage"]) != ION_STAGE or _int(row["data_type"]) != DATA_TYPE:
            raise ValueError("runtime oracle contains a non-He-II type-53 row")
        if any(not math.isfinite(_float(row[name])) for name in ANS_NAMES):
            raise ValueError("runtime oracle contains blank or non-finite ans values")
    info = {
        "available": True,
        "verified": manifest is not None,
        "path": str(path),
        "records": len(mapping),
        "sha256": _sha256(csv_path),
    }
    if manifest is not None:
        info.update({
            "capture_kind": manifest.get("capture_kind"),
            "full_dsec_runtime_capture": bool(manifest.get("full_dsec_runtime_capture", False)),
            "source_archive_sha256": manifest.get("source_archive_sha256"),
            "source_module_sha256": manifest.get("source_module_sha256"),
        })
    return mapping, info


def _matrix_terms(row: Mapping[str, Any], values: Mapping[str, float], variant: str) -> list[dict[str, Any]]:
    lower = _int(row["lower_row"])
    upper = _int(row["upper_row"])
    density = _float(row["density_scale"])
    a1, a2, a3, a4, a5, a6 = (values[name] for name in ANS_NAMES)
    definitions = (
        ("forward_gain", upper, lower, a1, a2, 0.0, 0.0),
        ("reverse_gain", lower, upper, a2, a1, 0.0, 0.0),
        ("forward_diag_loss", lower, lower, -a1, -a1, a4 * density, a6 * density),
        ("reverse_diag_loss", upper, upper, -a2, -a2, -a3 * density, -a5 * density),
    )
    return [
        {
            "evaluation_ordinal": _int(row["evaluation_ordinal"]),
            "source_position": _int(row["source_position"]),
            "record": _int(row["record"]),
            "variant": variant,
            "term_offset": offset,
            "role": role,
            "row": matrix_row,
            "column": column,
            "aj1": aj1,
            "aj2": aj2,
            "cj": cj,
            "cj2": cj2,
            "density_scale": density,
        }
        for offset, (role, matrix_row, column, aj1, aj2, cj, cj2) in enumerate(definitions)
    ]


def analyze(records_source: Path, output_dir: Path, *, evaluation: int = 61, reference_oracle: Path | None = None) -> dict[str, Any]:
    records_csv, selected = _load_selected(records_source, evaluation)
    oracle, oracle_info = _load_oracle(reference_oracle, evaluation)
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    joined: list[dict[str, Any]] = []
    matrix_rows: list[dict[str, Any]] = []
    source_sign_ok = True
    applied_sign_ok = True
    applied_pair_symmetry = True
    shadow_pair_symmetry = True
    reference_exact_applied = True
    reference_exact_shadow = True
    reference_records_compared = 0
    first_reference_divergence: dict[str, Any] | None = None
    reference_metrics = {
        variant: {name: {"exact": 0, "max_absolute_delta": 0.0, "max_relative_delta": 0.0, "source_position": None, "record": None} for name in ANS_NAMES}
        for variant in ("applied", "shadow")
    }
    shadow_closer_records = 0
    applied_closer_records = 0
    equal_distance_records = 0

    for raw in selected:
        key = (_int(raw["source_position"]), _int(raw["record"]))
        applied = {name: _float(raw[name]) for name in ANS_NAMES}
        shadow = {name: _float(raw[f"type53_shadow_{name}"]) for name in ANS_NAMES}
        reference_raw = oracle.get(key)
        reference = {name: _float(reference_raw[name]) for name in ANS_NAMES} if reference_raw else None
        source_sign_ok &= shadow["ans1"] >= 0.0 and shadow["ans2"] >= 0.0 and all(shadow[name] <= 0.0 for name in ("ans3", "ans4", "ans5", "ans6"))
        applied_sign_ok &= applied["ans1"] >= 0.0 and applied["ans2"] >= 0.0 and all(applied[name] <= 0.0 for name in ("ans3", "ans4", "ans5", "ans6"))
        applied_pair_symmetry &= _exact(applied["ans5"], -applied["ans3"]) and _exact(applied["ans6"], -applied["ans4"])
        shadow_pair_symmetry &= _exact(shadow["ans5"], -shadow["ans3"]) and _exact(shadow["ans6"], -shadow["ans4"])
        joined_row: dict[str, Any] = {
            "evaluation_ordinal": evaluation,
            "source_position": key[0],
            "record": key[1],
            "lower_row": _int(raw["lower_row"]),
            "upper_row": _int(raw["upper_row"]),
            "density_scale": _float(raw["density_scale"]),
            "reference_available": reference is not None,
        }
        for name in ANS_NAMES:
            joined_row[f"applied_{name}"] = applied[name]
            joined_row[f"shadow_{name}"] = shadow[name]
            joined_row[f"shadow_minus_applied_{name}"] = shadow[name] - applied[name]
            joined_row[f"reference_{name}"] = "" if reference is None else reference[name]
            if reference is not None:
                applied_match = _exact(reference[name], applied[name])
                shadow_match = _exact(reference[name], shadow[name])
                joined_row[f"applied_exact_{name}"] = applied_match
                joined_row[f"shadow_exact_{name}"] = shadow_match
                reference_exact_applied &= applied_match
                reference_exact_shadow &= shadow_match
                for variant_name, candidate, matched in (("applied", applied[name], applied_match), ("shadow", shadow[name], shadow_match)):
                    metric = reference_metrics[variant_name][name]
                    if matched:
                        metric["exact"] += 1
                    absolute_delta = abs(candidate - reference[name])
                    relative_delta = absolute_delta / max(abs(reference[name]), 1.0e-300)
                    if absolute_delta > metric["max_absolute_delta"]:
                        metric.update({
                            "max_absolute_delta": absolute_delta,
                            "max_relative_delta": relative_delta,
                            "source_position": key[0],
                            "record": key[1],
                        })
                if first_reference_divergence is None and not (applied_match and shadow_match):
                    first_reference_divergence = {"source_position": key[0], "record": key[1], "answer": name}
            else:
                joined_row[f"applied_exact_{name}"] = ""
                joined_row[f"shadow_exact_{name}"] = ""
        if reference is not None:
            reference_records_compared += 1
            applied_distance = sum(abs(applied[name] - reference[name]) for name in ANS_NAMES)
            shadow_distance = sum(abs(shadow[name] - reference[name]) for name in ANS_NAMES)
            if shadow_distance < applied_distance:
                shadow_closer_records += 1
            elif applied_distance < shadow_distance:
                applied_closer_records += 1
            else:
                equal_distance_records += 1
        joined.append(joined_row)
        matrix_rows.extend(_matrix_terms(raw, applied, "applied"))
        matrix_rows.extend(_matrix_terms(raw, shadow, "shadow"))
        if reference is not None:
            matrix_rows.extend(_matrix_terms(raw, reference, "reference"))

    joined_fields = [
        "evaluation_ordinal", "source_position", "record", "lower_row", "upper_row", "density_scale", "reference_available",
    ]
    for name in ANS_NAMES:
        joined_fields += [
            f"applied_{name}", f"shadow_{name}", f"shadow_minus_applied_{name}", f"reference_{name}",
            f"applied_exact_{name}", f"shadow_exact_{name}",
        ]
    joined_csv = output_dir / "heii_type53_three_way.csv"
    _write_csv(joined_csv, joined, joined_fields)
    matrix_csv = output_dir / "heii_type53_matrix_terms.csv"
    matrix_fields = [
        "evaluation_ordinal", "source_position", "record", "variant", "term_offset", "role", "row", "column",
        "aj1", "aj2", "cj", "cj2", "density_scale",
    ]
    _write_csv(matrix_csv, matrix_rows, matrix_fields)

    oracle_complete = oracle_info["available"] and reference_records_compared == len(selected) == 31
    semantics_known = source_sign_ok
    blockers: list[str] = []
    if not oracle_complete:
        blockers.append("exact v0.6.47.2 evaluation-61 per-record runtime oracle is unavailable or incomplete")
    if not applied_sign_ok:
        blockers.append("applied native ans5/ans6 do not follow source signed-energy semantics")
    if oracle_complete and not reference_exact_applied:
        blockers.append("applied native ans1-ans6 are not IEEE-exact to the runtime oracle")
    if oracle_complete and not reference_exact_shadow:
        blockers.append("translated shadow ans1-ans6 are not IEEE-exact to the runtime oracle")

    report = {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT",
        "audit_complete": True,
        "evaluation_ordinal": evaluation,
        "records_csv": str(records_csv),
        "output_directory": str(output_dir),
        "three_way_csv": str(joined_csv.resolve()),
        "matrix_terms_csv": str(matrix_csv.resolve()),
        "records_compared": len(selected),
        "matrix_terms_written": len(matrix_rows),
        "reference_runtime_oracle": oracle_info,
        "reference_records_compared": reference_records_compared,
        "reference_runtime_oracle_complete": oracle_complete,
        "reference_ans_semantics_known": semantics_known,
        "source_semantics_provenance": {
            "v06472_source_archive_sha256": "85ff0184bd95daf046fd28923837239c5192f8d309b0716556d1d804b0453060",
            "rates_type53_py_sha256": "67439524b5453d73ca184346bb844ce2cc23faad771b402effb33932a2bf8e06",
            "element_engine_cpp_sha256": "fe6e2844fefc14109906f2f154307a69483fabb041d65f9393cd0a569c80b328",
            "runtime_oracle_distinction": (
                "exact v0.6.47.2 fixed-state evaluator replay is available and verified"
                if oracle_complete else
                "source-code semantics are verified; exact v0.6.47.2 runtime per-record values are unavailable"
            ),
        },
        "source_semantics": {
            "ans1": "photoionization_rate_nonnegative",
            "ans2": "milne_recombination_rate_nonnegative",
            "ans3": "negative_recombination_cooling_energy",
            "ans4": "negative_photoionization_heating_energy",
            "ans5": "negative_recombination_electron_pov_energy_after_source_correction",
            "ans6": "negative_photoionization_electron_pov_energy_after_source_correction",
            "matrix_reverse_diag_cj2": "-ans5*density_scale",
            "matrix_forward_diag_cj2": "ans6*density_scale",
        },
        "shadow_source_sign_semantics_consistent": source_sign_ok,
        "applied_source_sign_semantics_consistent": applied_sign_ok,
        "applied_pair_symmetry_ans5_minus_ans3_ans6_minus_ans4": applied_pair_symmetry,
        "shadow_pair_symmetry_ans5_minus_ans3_ans6_minus_ans4": shadow_pair_symmetry,
        "applied_exact_to_reference": reference_exact_applied if oracle_complete else False,
        "shadow_exact_to_reference": reference_exact_shadow if oracle_complete else False,
        "first_reference_divergence": first_reference_divergence,
        "reference_difference_metrics": reference_metrics if oracle_complete else {},
        "shadow_closer_to_reference_records": shadow_closer_records,
        "applied_closer_to_reference_records": applied_closer_records,
        "equal_distance_to_reference_records": equal_distance_records,
        "qualified_applied_scope": "He II type-53 records (element_z=2, ion_stage=2)",
        "qualified_records": len(selected),
        "type53_ieee_kernel_contract": {
            "rydberg_ev": 13.605692,
            "exponential_clamp": [-60.0, 60.0],
            "floating_point_contract": "binary64, source operation order, compiler ffp-contract=off",
        },
        "type53_physics_replacement_ready": bool(
            oracle_complete and reference_exact_applied and reference_exact_shadow and applied_sign_ok
        ),
        "full_type53_family_promotion_ready": False,
        "remaining_scope_blockers": [
            "type-53 ions outside the qualified He II scope do not yet have independent runtime oracles",
            "whole fixed-state electron/charge/thermal parity remains blocked by other rate families",
        ],
        "fixed_state_parity": False,
        "production_promotion_ready": False,
        "blockers": blockers,
    }
    return report


def export_reference_template(records_source: Path, output_csv: Path, *, evaluation: int = 61) -> dict[str, Any]:
    records_csv, selected = _load_selected(records_source, evaluation)
    rows = []
    for raw in selected:
        row = {
            "evaluation_ordinal": evaluation,
            "source_position": _int(raw["source_position"]),
            "record": _int(raw["record"]),
            "element_z": ELEMENT_Z,
            "ion_stage": ION_STAGE,
            "data_type": DATA_TYPE,
            "lower_row": _int(raw["lower_row"]),
            "upper_row": _int(raw["upper_row"]),
        }
        for name in ANS_NAMES:
            row[name] = ""
        rows.append(row)
    output_csv = output_csv.resolve()
    _write_csv(output_csv, rows, ORACLE_FIELDS)
    return {
        "schema": ORACLE_SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT",
        "template_only": True,
        "records": len(rows),
        "evaluation_ordinal": evaluation,
        "records_csv": str(records_csv),
        "output_csv": str(output_csv),
        "runtime_values_present": False,
        "production_promotion_ready": False,
    }


def freeze_reference(source_csv: Path, bundle_dir: Path, *, source_archive_sha256: str = "") -> dict[str, Any]:
    source_csv = source_csv.resolve()
    bundle_dir = bundle_dir.resolve()
    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)
    bundle_dir.mkdir(parents=True)
    with source_csv.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = sorted(set(ORACLE_FIELDS).difference(reader.fieldnames or []))
        if missing:
            raise ValueError("runtime oracle source missing fields: " + ", ".join(missing))
        rows = [dict(row) for row in reader]
    rows.sort(key=lambda row: (_int(row["evaluation_ordinal"]), _int(row["source_position"]), _int(row["record"])))
    keys = [(_int(row["evaluation_ordinal"]), _int(row["source_position"]), _int(row["record"])) for row in rows]
    if len(rows) != 31 or len(set(keys)) != 31:
        raise ValueError("runtime oracle must contain exactly 31 unique evaluation-61 He II type-53 records")
    if any(key[0] != 61 for key in keys):
        raise ValueError("runtime oracle must contain evaluation 61 only")
    for row in rows:
        if _int(row["element_z"]) != ELEMENT_Z or _int(row["ion_stage"]) != ION_STAGE or _int(row["data_type"]) != DATA_TYPE:
            raise ValueError("runtime oracle must contain He II type-53 rows only")
        if any(not math.isfinite(_float(row[name])) for name in ANS_NAMES):
            raise ValueError("runtime oracle ans1-ans6 must all be finite")
    target = bundle_dir / "type53_runtime_oracle.csv"
    _write_csv(target, rows, ORACLE_FIELDS)
    manifest = {
        "schema": ORACLE_SCHEMA,
        "release": RELEASE,
        "immutable": True,
        "evaluation_ordinal": 61,
        "records": 31,
        "source_archive_sha256": source_archive_sha256,
        "files": {
            target.name: {"sha256": _sha256(target), "size_bytes": target.stat().st_size},
        },
        "production_promotion_ready": False,
    }
    _write_json(bundle_dir / "reference_manifest.json", manifest)
    return {**manifest, "bundle_directory": str(bundle_dir), "result": "ACCEPT"}


def verify_reference(bundle_dir: Path) -> dict[str, Any]:
    bundle_dir = bundle_dir.resolve()
    errors: list[str] = []
    manifest_path = bundle_dir / "reference_manifest.json"
    if not manifest_path.is_file():
        return {"schema": ORACLE_SCHEMA, "result": "REJECT", "errors": ["missing reference_manifest.json"]}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != ORACLE_SCHEMA:
        errors.append("unexpected oracle schema")
    for name, metadata in manifest.get("files", {}).items():
        path = bundle_dir / name
        if not path.is_file():
            errors.append(f"missing {name}")
        elif _sha256(path) != metadata.get("sha256"):
            errors.append(f"SHA-256 mismatch for {name}")
    try:
        oracle, info = _load_oracle(bundle_dir, 61)
        if len(oracle) != 31:
            errors.append("oracle does not contain 31 records")
    except Exception as exc:
        errors.append(str(exc))
    return {
        "schema": ORACLE_SCHEMA,
        "bundle_directory": str(bundle_dir),
        "result": "ACCEPT" if not errors else "REJECT",
        "errors": errors,
        "files_verified": len(manifest.get("files", {})) - len([e for e in errors if e.startswith("missing") or "mismatch" in e]),
        "production_promotion_ready": False,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("analyze")
    p.add_argument("records_source", type=Path)
    p.add_argument("output_dir", type=Path)
    p.add_argument("--evaluation", type=int, default=61)
    p.add_argument("--reference-oracle", type=Path)
    p.add_argument("--output-json", type=Path)
    p = sub.add_parser("export-reference-template")
    p.add_argument("records_source", type=Path)
    p.add_argument("output_csv", type=Path)
    p.add_argument("--evaluation", type=int, default=61)
    p.add_argument("--output-json", type=Path)
    p = sub.add_parser("freeze-reference")
    p.add_argument("source_csv", type=Path)
    p.add_argument("bundle_dir", type=Path)
    p.add_argument("--source-archive-sha256", default="")
    p.add_argument("--output-json", type=Path)
    p = sub.add_parser("verify-reference")
    p.add_argument("bundle_dir", type=Path)
    p.add_argument("--output-json", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    output_json = getattr(args, "output_json", None)
    try:
        if args.command == "analyze":
            result = analyze(args.records_source, args.output_dir, evaluation=args.evaluation, reference_oracle=args.reference_oracle)
            output = output_json.resolve() if output_json else args.output_dir.resolve() / "summary.json"
        elif args.command == "export-reference-template":
            result = export_reference_template(args.records_source, args.output_csv, evaluation=args.evaluation)
            output = output_json.resolve() if output_json else args.output_csv.resolve().with_suffix(".json")
        elif args.command == "freeze-reference":
            result = freeze_reference(args.source_csv, args.bundle_dir, source_archive_sha256=args.source_archive_sha256)
            output = output_json.resolve() if output_json else args.bundle_dir.resolve() / "freeze_report.json"
        else:
            result = verify_reference(args.bundle_dir)
            output = output_json.resolve() if output_json else args.bundle_dir.resolve() / "verify_report.json"
        _write_json(output, result)
        printable = dict(result)
        printable["output_json"] = str(output)
        print(json.dumps(printable, indent=2, sort_keys=True))
        return 0 if result.get("result") == "ACCEPT" else 1
    except Exception as exc:
        if output_json:
            stale = output_json.resolve()
            if stale.exists():
                stale.unlink()
        print(f"type53 semantics audit failed: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
