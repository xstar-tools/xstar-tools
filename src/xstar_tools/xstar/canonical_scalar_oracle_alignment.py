"""Canonical fixed-state/Thermal scalar-oracle alignment for v0.6.48.7.46.17.

The accepted v46.11 fixed-state closure and the current v46.12 source Thermal
capture were produced by separate source-capture runs.  Level and ion
populations must remain bit-exact against v46.11, while the two controller
scalars are rebased onto the current source capture so the fixed-state and
Thermal closures consume one canonical binary64 oracle.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
import struct
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

RELEASE = "0.6.48.7.46.17"
SCHEMA = "xstar-tools-v06487461211-canonical-fixed-thermal-scalar-oracle-v1"
REPORT_NAME = "v048746121_canonical_scalar_oracle_alignment_report.json"
COMPARISON_NAME = "v048746121_scalar_oracle_comparison.csv"
ALIGNED_DIRNAME = "v048746121_canonical_fixed_state_thermal_closure"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, fieldnames: list[str], rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _bits(value: float) -> int:
    return struct.unpack(">Q", struct.pack(">d", float(value)))[0]


def _bits_hex(value: float) -> str:
    return f"0x{_bits(value):016x}"


def _ordered_bits(value: float) -> int:
    bits = _bits(value)
    if bits & 0x8000000000000000:
        return (~bits) & 0xFFFFFFFFFFFFFFFF
    return bits | 0x8000000000000000


def _ulp_distance(left: float, right: float) -> int:
    if math.isnan(left) or math.isnan(right):
        return 2**64 - 1
    return abs(_ordered_bits(left) - _ordered_bits(right))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _scalar_map(path: Path) -> dict[str, dict[str, str]]:
    rows = _read_csv(path)
    result = {row["field"]: row for row in rows}
    required = {"computed_electron_fraction", "charge_residual"}
    if set(result) != required or len(rows) != 2:
        raise ValueError(f"{path}: expected exactly {sorted(required)}")
    return result


def prepare(
    baseline_closure: Path,
    source_capture: Path,
    thermal_closure: Path,
    output_dir: Path,
    output_json: Path | None = None,
) -> dict[str, Any]:
    fixed_rows_path = source_capture / "v0472_all61_fixed_state_rows.csv"
    level_rows_path = source_capture / "v0472_all61_level_populations.csv"
    ion_rows_path = source_capture / "v0472_all61_ion_populations.csv"
    thermal_rows_path = source_capture / "v0472_all61_thermal_budget.csv"
    for path in (fixed_rows_path, level_rows_path, ion_rows_path, thermal_rows_path):
        if not path.is_file():
            raise FileNotFoundError(path)

    fixed_rows = {int(row["sequence"]): row for row in _read_csv(fixed_rows_path)}
    thermal_rows = {int(row["sequence"]): row for row in _read_csv(thermal_rows_path)}
    output_dir.mkdir(parents=True, exist_ok=True)
    for stale in output_dir.glob("sequence_*.csv"):
        stale.unlink()
    comparison_rows: list[dict[str, Any]] = []
    errors: list[str] = []
    level_exact = 0
    ion_exact = 0
    level_total = 0
    ion_total = 0
    scalar_exact = 0
    scalar_total = 0
    fixed_thermal_charge_exact = 0
    changed_sequences: set[int] = set()
    copied_files = 0
    max_scalar_ulp = 0

    expected_sequences = set(range(1, 62))
    if set(fixed_rows) != expected_sequences:
        errors.append(f"fixed_sequence_inventory={len(fixed_rows)}")
    if set(thermal_rows) != expected_sequences:
        errors.append(f"thermal_sequence_inventory={len(thermal_rows)}")

    for sequence in range(1, 62):
        baseline_levels_path = baseline_closure / f"sequence_{sequence:04d}_levels.csv"
        baseline_ions_path = baseline_closure / f"sequence_{sequence:04d}_ions.csv"
        baseline_scalars_path = baseline_closure / f"sequence_{sequence:04d}_scalars.csv"
        thermal_sequence_path = thermal_closure / f"sequence_{sequence:04d}_thermal.csv"
        required_paths = (baseline_levels_path, baseline_ions_path, baseline_scalars_path, thermal_sequence_path)
        missing_paths = [path for path in required_paths if not path.is_file()]
        if missing_paths:
            errors.extend(f"missing:{path}" for path in missing_paths)
            continue

        baseline_levels = _read_csv(baseline_levels_path)
        baseline_ions = _read_csv(baseline_ions_path)
        if len(baseline_levels) != 688:
            errors.append(f"sequence_{sequence:04d}:baseline_level_inventory:{len(baseline_levels)}")
        else:
            level_total += len(baseline_levels)
        if len(baseline_ions) != 18:
            errors.append(f"sequence_{sequence:04d}:baseline_ion_inventory:{len(baseline_ions)}")
        else:
            ion_total += len(baseline_ions)

        # Immutable level/ion files are copied byte-for-byte from the accepted
        # v46.11 closure. The hash identity is the preservation contract; only
        # the scalar files are allowed to change in this release.
        for source_path in (baseline_levels_path, baseline_ions_path):
            destination = output_dir / source_path.name
            shutil.copyfile(source_path, destination)
            if _sha256(source_path) != _sha256(destination):
                errors.append(f"copy_hash_mismatch:{source_path.name}")
            else:
                if source_path.name.endswith("_levels.csv"):
                    level_exact += len(baseline_levels)
                else:
                    ion_exact += len(baseline_ions)
            copied_files += 1

        baseline_scalars = _scalar_map(baseline_scalars_path)
        fixed = fixed_rows[sequence]
        thermal = thermal_rows[sequence]
        thermal_file_rows = _read_csv(thermal_sequence_path)
        if len(thermal_file_rows) != 1:
            errors.append(f"sequence_{sequence:04d}:thermal_closure_row_count={len(thermal_file_rows)}")
            continue
        thermal_file = thermal_file_rows[0]
        identity = (
            int(fixed["sequence"]), fixed["kind"], int(fixed["dsec_call_id"]), int(fixed["evaluation_index"])
        )
        thermal_identity = (
            int(thermal["sequence"]), thermal["kind"], int(thermal["call_index"]), int(thermal["evaluation_index"])
        )
        if identity != thermal_identity:
            errors.append(f"sequence_{sequence:04d}:identity:{identity}!={thermal_identity}")

        canonical_values = {
            "computed_electron_fraction": float(fixed["computed_electron_fraction"]),
            "charge_residual": float(fixed["charge_residual"]),
        }
        thermal_elcter = float(thermal["elcter"])
        thermal_file_elcter = float(thermal_file["elcter"])
        charge_exact = (
            _bits(canonical_values["charge_residual"]) == _bits(thermal_elcter) == _bits(thermal_file_elcter)
        )
        fixed_thermal_charge_exact += int(charge_exact)
        if not charge_exact:
            errors.append(f"sequence_{sequence:04d}:fixed_thermal_charge_not_exact")

        aligned_scalar_rows = []
        for field in ("computed_electron_fraction", "charge_residual"):
            baseline_value = float(baseline_scalars[field]["source_value"])
            canonical_value = canonical_values[field]
            exact = _bits(baseline_value) == _bits(canonical_value)
            scalar_exact += int(exact)
            scalar_total += 1
            ulp = _ulp_distance(baseline_value, canonical_value)
            max_scalar_ulp = max(max_scalar_ulp, ulp)
            if not exact:
                changed_sequences.add(sequence)
            comparison_rows.append({
                "sequence": sequence,
                "kind": fixed["kind"],
                "call_index": fixed["dsec_call_id"],
                "evaluation_index": fixed["evaluation_index"],
                "field": field,
                "baseline_source_value": format(baseline_value, ".17g"),
                "canonical_source_value": format(canonical_value, ".17g"),
                "baseline_bits": _bits_hex(baseline_value),
                "canonical_bits": _bits_hex(canonical_value),
                "exact": int(exact),
                "ulp_distance": ulp,
                "thermal_value": format(thermal_elcter, ".17g") if field == "charge_residual" else "",
                "thermal_bits": _bits_hex(thermal_elcter) if field == "charge_residual" else "",
                "fixed_thermal_exact": int(charge_exact) if field == "charge_residual" else "",
            })
            aligned_scalar_rows.append({
                "field": field,
                "source_value": format(canonical_value, ".17g"),
                "native_baseline": baseline_scalars[field]["native_baseline"],
            })
        _write_csv(
            output_dir / f"sequence_{sequence:04d}_scalars.csv",
            ["field", "source_value", "native_baseline"],
            aligned_scalar_rows,
        )
        copied_files += 1

    comparison_path = output_dir.parent / COMPARISON_NAME
    _write_csv(
        comparison_path,
        [
            "sequence", "kind", "call_index", "evaluation_index", "field",
            "baseline_source_value", "canonical_source_value", "baseline_bits", "canonical_bits",
            "exact", "ulp_distance", "thermal_value", "thermal_bits", "fixed_thermal_exact",
        ],
        comparison_rows,
    )

    gates = {
        "ACCEPTED_V4611_LEVEL_POPULATIONS_PRESERVED_41968": "ACCEPT" if level_exact == level_total == 41968 else "REJECT",
        "ACCEPTED_V4611_ION_POPULATIONS_PRESERVED_1098": "ACCEPT" if ion_exact == ion_total == 1098 else "REJECT",
        "SOURCE_FIXED_THERMAL_CHARGE_BITS_EXACT_61": "ACCEPT" if fixed_thermal_charge_exact == 61 else "REJECT",
        "CANONICAL_SCALAR_FIELDS_WRITTEN_122": "ACCEPT" if scalar_total == 122 else "REJECT",
        "CANONICAL_CLOSURE_FILES_WRITTEN_183": "ACCEPT" if copied_files == 183 and len(list(output_dir.glob("sequence_*.csv"))) == 183 else "REJECT",
        "SCALAR_DRIFT_EXPLICITLY_ATTRIBUTED": "ACCEPT" if len(comparison_rows) == 122 else "REJECT",
        "NO_ALIGNMENT_ERRORS": "ACCEPT" if not errors else "REJECT",
    }
    result = "ACCEPT" if all(value == "ACCEPT" for value in gates.values()) else "REJECT"
    report = {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": result,
        "baseline_fixed_state_closure": str(baseline_closure),
        "source_capture": str(source_capture),
        "thermal_component_closure": str(thermal_closure),
        "canonical_closure": str(output_dir),
        "comparison_csv": str(comparison_path),
        "sequences": 61,
        "level_values_exact": level_exact,
        "level_values_total": level_total,
        "ion_values_exact": ion_exact,
        "ion_values_total": ion_total,
        "scalar_values_unchanged": scalar_exact,
        "scalar_values_total": scalar_total,
        "scalar_values_rebased": scalar_total - scalar_exact,
        "scalar_sequences_rebased": len(changed_sequences),
        "first_rebased_sequence": min(changed_sequences) if changed_sequences else None,
        "max_scalar_ulp_distance": max_scalar_ulp,
        "fixed_thermal_charge_exact": fixed_thermal_charge_exact,
        "gates": gates,
        "errors": errors,
        "qualification_only": True,
        "native_replay_replayed": False,
        "production_promotion_ready": False,
    }
    report_path = output_json or output_dir.parent / REPORT_NAME
    _write_json(report_path, report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-fixed-state-closure", type=Path, required=True)
    parser.add_argument("--source-capture", type=Path, required=True)
    parser.add_argument("--thermal-closure", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args(argv)
    try:
        report = prepare(
            args.baseline_fixed_state_closure,
            args.source_capture,
            args.thermal_closure,
            args.output_dir,
            args.output_json,
        )
    except Exception as exc:
        report = {
            "schema": SCHEMA,
            "release": RELEASE,
            "result": "REJECT",
            "errors": [str(exc)],
            "qualification_only": True,
            "production_promotion_ready": False,
        }
        if args.output_json:
            _write_json(args.output_json, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("result") == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
