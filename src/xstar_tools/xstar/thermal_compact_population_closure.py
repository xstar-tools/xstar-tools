"""Prepare and audit source-faithful Thermal compact-population transport.

The fixed-state product remains the accepted 688-row H/He/Mg level vector.  This
qualification closure is a distinct Thermal-only payload containing the exact
post-solve compact ``final_population`` vectors consumed by the source Thermal
calculation.  It preserves compact normalization rows and active-stage windows
without projecting them back onto the full-level product.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import struct
from collections import defaultdict
from pathlib import Path
from typing import Any

RELEASE = "0.6.48.7.46.19.1"
SCHEMA = "xstar-tools-v064874613-thermal-compact-population-closure-v1"
SOURCE_ROWS_NAME = "v0472_all61_element_solve_rows.csv"
CLOSURE_DIRNAME = "v04874613_thermal_compact_population_closure"
REPORT_NAME = "v04874613_thermal_compact_population_closure_report.json"
MANIFEST_NAME = "v04874613_thermal_compact_population_manifest.csv"
COMPARISON_NAME = "v04874613_thermal_compact_population_comparison.csv"
NATIVE_AGGREGATE_NAME = "native_all61_thermal_compact_populations.csv"

FIELDS = [
    "sequence", "kind", "call_index", "evaluation_index", "element_z", "abundance",
    "active_min_stage", "active_max_stage", "compact_row", "ion", "ion_stage",
    "ion_charge", "superlevel", "is_normalization_row", "final_population",
    "final_population_ieee_hex",
]
IDENTITY_FIELDS = [
    "sequence", "kind", "call_index", "evaluation_index", "element_z", "active_min_stage",
    "active_max_stage", "compact_row", "ion", "ion_stage", "ion_charge", "superlevel",
    "is_normalization_row",
]
EXPECTED_TOTAL = 40149
EXPECTED_BY_Z = {1: 2013, 2: 4758, 12: 33378}
EXPECTED_SEQUENCE_COUNT = 61


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _bits_hex(value: float) -> str:
    return struct.pack(">d", float(value)).hex()


def _fnv1a_binary64(values: list[float]) -> str:
    result = 1469598103934665603
    for value in values:
        for byte in struct.pack("<d", float(value)):
            result ^= byte
            result = (result * 1099511628211) & ((1 << 64) - 1)
    return f"{result:016x}"


def _source_to_closure(row: dict[str, str]) -> dict[str, Any]:
    value = float(row["final_population"])
    return {
        "sequence": int(row["sequence"]),
        "kind": row["kind"],
        "call_index": int(row.get("dsec_call_id", row.get("call_index", 0))),
        "evaluation_index": int(row["evaluation_index"]),
        "element_z": int(row["element_z"]),
        "abundance": format(float(row["abundance"]), ".17g"),
        "active_min_stage": int(row["active_min_stage"]),
        "active_max_stage": int(row["active_max_stage"]),
        "compact_row": int(row["compact_row"]),
        "ion": int(row["ion"]),
        "ion_stage": int(row["ion_stage"]),
        "ion_charge": int(row["ion_charge"]),
        "superlevel": int(row["superlevel"]),
        "is_normalization_row": int(row["is_normalization_row"]),
        "final_population": format(value, ".17g"),
        "final_population_ieee_hex": _bits_hex(value),
    }


def _validate_inventory(rows: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    if len(rows) != EXPECTED_TOTAL:
        errors.append(f"compact_population_total={len(rows)}")
    sequence_inventory = sorted({int(row["sequence"]) for row in rows})
    if sequence_inventory != list(range(1, EXPECTED_SEQUENCE_COUNT + 1)):
        errors.append(f"sequence_inventory={len(sequence_inventory)}")
    by_z: dict[int, int] = defaultdict(int)
    grouped: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        z = int(row["element_z"])
        by_z[z] += 1
        grouped[(int(row["sequence"]), z)].append(row)
        value = float(row["final_population"])
        if not math.isfinite(value) or value < 0.0:
            errors.append(f"invalid_population:{row['sequence']}:{z}:{row['compact_row']}")
        if int(row["ion"]) != int(row["ion_stage"]):
            errors.append(f"ion_stage_mismatch:{row['sequence']}:{z}:{row['compact_row']}")
        if _bits_hex(value) != str(row["final_population_ieee_hex"]).lower():
            errors.append(f"ieee_mismatch:{row['sequence']}:{z}:{row['compact_row']}")
    for z, expected in EXPECTED_BY_Z.items():
        if by_z.get(z, 0) != expected:
            errors.append(f"element_z_{z}_inventory={by_z.get(z, 0)}")
    if set(by_z) != set(EXPECTED_BY_Z):
        errors.append("unexpected_element_inventory=" + ",".join(map(str, sorted(set(by_z) - set(EXPECTED_BY_Z)))))
    for sequence in range(1, EXPECTED_SEQUENCE_COUNT + 1):
        for z in (1, 2, 12):
            subset = sorted(grouped.get((sequence, z), []), key=lambda row: int(row["compact_row"]))
            if not subset:
                errors.append(f"missing_element:{sequence}:{z}")
                continue
            compact_rows = [int(row["compact_row"]) for row in subset]
            if compact_rows != list(range(1, len(subset) + 1)):
                errors.append(f"compact_row_sequence:{sequence}:{z}")
            normalization = [int(row["is_normalization_row"]) for row in subset]
            if normalization.count(1) != 1 or normalization[-1] != 1:
                errors.append(f"normalization_row:{sequence}:{z}")
            min_stages = {int(row["active_min_stage"]) for row in subset}
            max_stages = {int(row["active_max_stage"]) for row in subset}
            if len(min_stages) != 1 or len(max_stages) != 1:
                errors.append(f"active_window:{sequence}:{z}")
    return errors


def prepare(source_capture: Path, output_dir: Path) -> dict[str, Any]:
    source_path = source_capture / SOURCE_ROWS_NAME
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    source_rows = _read_csv(source_path)
    required = {
        "sequence", "kind", "dsec_call_id", "evaluation_index", "element_z", "abundance",
        "active_min_stage", "active_max_stage", "compact_row", "ion", "ion_stage",
        "ion_charge", "superlevel", "is_normalization_row", "final_population",
    }
    missing = sorted(required - set(source_rows[0])) if source_rows else sorted(required)
    if missing:
        raise ValueError("source compact rows missing columns: " + ",".join(missing))
    rows = [_source_to_closure(row) for row in source_rows]
    rows.sort(key=lambda row: (int(row["sequence"]), int(row["element_z"]), int(row["compact_row"])))
    errors = _validate_inventory(rows)
    output_dir.mkdir(parents=True, exist_ok=True)
    for stale in output_dir.glob("sequence_*_thermal_compact_populations.csv"):
        stale.unlink()
    manifest_rows: list[dict[str, Any]] = []
    if not errors:
        for sequence in range(1, EXPECTED_SEQUENCE_COUNT + 1):
            subset = [row for row in rows if int(row["sequence"]) == sequence]
            path = output_dir / f"sequence_{sequence:04d}_thermal_compact_populations.csv"
            _write_csv(path, FIELDS, subset)
            counts = {z: sum(int(row["element_z"]) == z for row in subset) for z in (1, 2, 12)}
            values = [float(row["final_population"]) for row in subset]
            manifest_rows.append({
                "sequence": sequence,
                "kind": subset[0]["kind"],
                "call_index": subset[0]["call_index"],
                "evaluation_index": subset[0]["evaluation_index"],
                "population_count": len(values),
                "population_fingerprint": _fnv1a_binary64(values),
                "h_count": counts[1],
                "he_count": counts[2],
                "mg_count": counts[12],
                "closure_file": path.name,
            })
        _write_csv(
            output_dir / MANIFEST_NAME,
            ["sequence", "kind", "call_index", "evaluation_index", "population_count",
             "population_fingerprint", "h_count", "he_count", "mg_count", "closure_file"],
            manifest_rows,
        )
    gates = {
        "SOURCE_COMPACT_POPULATION_VALUES_40149": "ACCEPT" if len(rows) == EXPECTED_TOTAL else "REJECT",
        "SOURCE_COMPACT_H_VALUES_2013": "ACCEPT" if sum(int(r["element_z"]) == 1 for r in rows) == EXPECTED_BY_Z[1] else "REJECT",
        "SOURCE_COMPACT_HE_VALUES_4758": "ACCEPT" if sum(int(r["element_z"]) == 2 for r in rows) == EXPECTED_BY_Z[2] else "REJECT",
        "SOURCE_COMPACT_MG_VALUES_33378": "ACCEPT" if sum(int(r["element_z"]) == 12 for r in rows) == EXPECTED_BY_Z[12] else "REJECT",
        "SOURCE_COMPACT_TOPOLOGY_EXACT": "ACCEPT" if not errors else "REJECT",
        "THERMAL_COMPACT_CLOSURE_FILES_61": "ACCEPT" if len(list(output_dir.glob("sequence_*_thermal_compact_populations.csv"))) == 61 else "REJECT",
    }
    report = {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT" if all(value == "ACCEPT" for value in gates.values()) else "REJECT",
        "errors": errors,
        "source_capture": str(source_capture),
        "output_dir": str(output_dir),
        "compact_population_values": len(rows),
        "compact_population_values_by_element": {str(z): sum(int(r["element_z"]) == z for r in rows) for z in (1, 2, 12)},
        "sequences_prepared": len(manifest_rows),
        "gates": gates,
        "qualification_only": True,
        "fixed_state_product_modified": False,
        "production_promotion_ready": False,
    }
    _write_json(output_dir / REPORT_NAME, report)
    return report


def audit(closure_dir: Path, native_run: Path, output: Path) -> dict[str, Any]:
    source_rows: list[dict[str, str]] = []
    for sequence in range(1, EXPECTED_SEQUENCE_COUNT + 1):
        path = closure_dir / f"sequence_{sequence:04d}_thermal_compact_populations.csv"
        if not path.is_file():
            raise FileNotFoundError(path)
        source_rows.extend(_read_csv(path))
    native_path = native_run / NATIVE_AGGREGATE_NAME
    if not native_path.is_file():
        raise FileNotFoundError(native_path)
    native_rows = _read_csv(native_path)
    source_rows.sort(key=lambda row: (int(row["sequence"]), int(row["element_z"]), int(row["compact_row"])))
    native_rows.sort(key=lambda row: (int(row["sequence"]), int(row["element_z"]), int(row["compact_row"])))
    comparison: list[dict[str, Any]] = []
    exact = 0
    topology_exact = 0
    total = max(len(source_rows), len(native_rows))
    for index in range(total):
        source = source_rows[index] if index < len(source_rows) else {}
        native = native_rows[index] if index < len(native_rows) else {}
        identity_ok = bool(source and native) and all(str(source.get(field, "")) == str(native.get(field, "")) for field in IDENTITY_FIELDS)
        topology_exact += int(identity_ok)
        source_value = source.get("final_population", "")
        native_value = native.get("thermal_population", native.get("final_population", ""))
        try:
            value_ok = identity_ok and struct.pack(">d", float(source_value)) == struct.pack(">d", float(native_value))
        except Exception:
            value_ok = False
        exact += int(value_ok)
        comparison.append({
            "sequence": source.get("sequence", native.get("sequence", "")),
            "kind": source.get("kind", native.get("kind", "")),
            "call_index": source.get("call_index", native.get("call_index", "")),
            "evaluation_index": source.get("evaluation_index", native.get("evaluation_index", "")),
            "element_z": source.get("element_z", native.get("element_z", "")),
            "compact_row": source.get("compact_row", native.get("compact_row", "")),
            "ion": source.get("ion", native.get("ion", "")),
            "ion_charge": source.get("ion_charge", native.get("ion_charge", "")),
            "superlevel": source.get("superlevel", native.get("superlevel", "")),
            "is_normalization_row": source.get("is_normalization_row", native.get("is_normalization_row", "")),
            "source_population": source_value,
            "native_population": native_value,
            "topology_exact": int(identity_ok),
            "population_exact": int(value_ok),
        })
    _write_csv(
        output / COMPARISON_NAME,
        ["sequence", "kind", "call_index", "evaluation_index", "element_z", "compact_row", "ion",
         "ion_charge", "superlevel", "is_normalization_row", "source_population", "native_population",
         "topology_exact", "population_exact"],
        comparison,
    )
    sequence_exact = 0
    by_sequence_source: dict[int, list[dict[str, str]]] = defaultdict(list)
    by_sequence_native: dict[int, list[dict[str, str]]] = defaultdict(list)
    for row in source_rows:
        by_sequence_source[int(row["sequence"])].append(row)
    for row in native_rows:
        by_sequence_native[int(row["sequence"])].append(row)
    for sequence in range(1, EXPECTED_SEQUENCE_COUNT + 1):
        left = by_sequence_source.get(sequence, [])
        right = by_sequence_native.get(sequence, [])
        sequence_exact += int(
            len(left) == len(right)
            and _fnv1a_binary64([float(row["final_population"]) for row in left])
            == _fnv1a_binary64([float(row.get("thermal_population", row.get("final_population", "nan"))) for row in right])
        )
    gates = {
        "THERMAL_COMPACT_POPULATION_VALUES_EXACT_40149": "ACCEPT" if exact == total == EXPECTED_TOTAL else "REJECT",
        "THERMAL_COMPACT_POPULATION_TOPOLOGY_EXACT_40149": "ACCEPT" if topology_exact == total == EXPECTED_TOTAL else "REJECT",
        "ALL_61_THERMAL_COMPACT_POPULATION_FINGERPRINTS_EXACT": "ACCEPT" if sequence_exact == 61 else "REJECT",
    }
    report = {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT" if all(value == "ACCEPT" for value in gates.values()) else "REJECT",
        "gates": gates,
        "source_values": len(source_rows),
        "native_values": len(native_rows),
        "topology_values_exact": topology_exact,
        "population_values_exact": exact,
        "population_fingerprints_exact": sequence_exact,
        "qualification_only": True,
        "fixed_state_product_modified": False,
        "production_promotion_ready": False,
    }
    _write_json(output / REPORT_NAME, report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--source-capture", type=Path, required=True)
    prep.add_argument("--output-dir", type=Path, required=True)
    prep.add_argument("--output-json", type=Path)
    aud = sub.add_parser("audit")
    aud.add_argument("--closure-dir", type=Path, required=True)
    aud.add_argument("--native-run", type=Path, required=True)
    aud.add_argument("--output", type=Path, required=True)
    aud.add_argument("--output-json", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare(args.source_capture, args.output_dir)
        else:
            result = audit(args.closure_dir, args.native_run, args.output)
    except Exception as exc:
        result = {
            "schema": SCHEMA,
            "release": RELEASE,
            "result": "REJECT",
            "errors": [str(exc)],
            "qualification_only": True,
            "production_promotion_ready": False,
        }
    if getattr(args, "output_json", None):
        _write_json(args.output_json, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["result"] == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
