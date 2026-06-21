"""Fail-first independent compact-population parity audit for v0.6.48.7.46.21.5."""
from __future__ import annotations

import argparse
import csv
import json
import math
import struct
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

RELEASE = "0.6.48.7.46.21.5"
SCHEMA = "xstar-tools-v0648746213-independent-compact-population-parity-v1"
COMPARISON_NAME = "v048746212_compact_population_comparison.csv"
FINGERPRINT_NAME = "v048746212_compact_population_fingerprints.csv"
EXPECTED_BY_ELEMENT = {1: 2013, 2: 4758, 12: 33378}
EXPECTED_TOTAL = 40149


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _bits(value: float) -> bytes:
    return struct.pack("<d", float(value))


def _ordered_int(bits: int) -> int:
    return (~bits & 0xFFFFFFFFFFFFFFFF) if bits & (1 << 63) else bits | (1 << 63)


def _ulp_distance(left: float, right: float) -> int:
    if math.isnan(left) or math.isnan(right):
        return 2**64 - 1
    a = struct.unpack("<Q", struct.pack("<d", left))[0]
    b = struct.unpack("<Q", struct.pack("<d", right))[0]
    return abs(_ordered_int(a) - _ordered_int(b))


def _fnv1a(values: Iterable[float]) -> str:
    value = 1469598103934665603
    prime = 1099511628211
    for item in values:
        for byte in _bits(float(item)):
            value ^= byte
            value = (value * prime) & 0xFFFFFFFFFFFFFFFF
    return f"{value:016x}"


def audit(source_capture: Path, native_run: Path, output: Path) -> dict[str, Any]:
    source_path = source_capture / "v0472_all61_element_solve_rows.csv"
    native_path = native_run / "native_all61_thermal_compact_populations.csv"
    if not source_path.is_file() or not native_path.is_file():
        missing = [str(p) for p in (source_path, native_path) if not p.is_file()]
        raise FileNotFoundError("missing compact-population input: " + ", ".join(missing))

    source_rows = _rows(source_path)
    native_rows = _rows(native_path)
    source: dict[tuple[int, int, int], dict[str, str]] = {}
    for row in source_rows:
        key = (int(row["sequence"]), int(row["element_z"]), int(row["compact_row"]))
        if key in source:
            raise RuntimeError(f"duplicate source compact-population key: {key}")
        source[key] = row
    native: dict[tuple[int, int, int], dict[str, str]] = {}
    for row in native_rows:
        key = (int(row["sequence"]), int(row["element_z"]), int(row["compact_row"]))
        if key in native:
            raise RuntimeError(f"duplicate native compact-population key: {key}")
        native[key] = row

    comparison_fields = [
        "sequence", "element_z", "compact_row", "active_min_stage", "active_max_stage",
        "ion", "ion_stage", "ion_charge", "superlevel", "is_normalization_row",
        "source_population", "native_population", "binary64_exact", "ulp_distance",
        "absolute_residual", "relative_residual",
    ]
    comparison: list[dict[str, Any]] = []
    exact_by_element = defaultdict(int)
    total_by_element = defaultdict(int)
    source_streams: dict[int, list[float]] = defaultdict(list)
    native_streams: dict[int, list[float]] = defaultdict(list)
    source_element_streams: dict[tuple[int, int], list[float]] = defaultdict(list)
    native_element_streams: dict[tuple[int, int], list[float]] = defaultdict(list)
    topology_mismatches = 0
    missing_native = 0
    first_mismatch: dict[str, Any] | None = None

    topology_fields = (
        "active_min_stage", "active_max_stage", "ion", "ion_stage", "ion_charge",
        "superlevel", "is_normalization_row",
    )
    for key in sorted(source):
        sequence, element_z, compact_row = key
        src = source[key]
        nat = native.get(key)
        total_by_element[element_z] += 1
        if nat is None:
            missing_native += 1
            if first_mismatch is None:
                first_mismatch = {"sequence": sequence, "element_z": element_z, "compact_row": compact_row, "reason": "missing_native"}
            continue
        topology_ok = all(str(src[field]) == str(nat[field]) for field in topology_fields)
        if not topology_ok:
            topology_mismatches += 1
        source_value = float(src["final_population"])
        native_value = float(nat["thermal_population"])
        exact = topology_ok and _bits(source_value) == _bits(native_value)
        exact_by_element[element_z] += int(exact)
        source_streams[sequence].append(source_value)
        native_streams[sequence].append(native_value)
        source_element_streams[(sequence, element_z)].append(source_value)
        native_element_streams[(sequence, element_z)].append(native_value)
        residual = native_value - source_value
        relative = residual / source_value if source_value != 0.0 else (0.0 if residual == 0.0 else math.copysign(math.inf, residual))
        comparison.append({
            "sequence": sequence, "element_z": element_z, "compact_row": compact_row,
            **{field: src[field] for field in topology_fields},
            "source_population": format(source_value, ".17g"),
            "native_population": format(native_value, ".17g"),
            "binary64_exact": int(exact), "ulp_distance": _ulp_distance(source_value, native_value),
            "absolute_residual": format(residual, ".17g"), "relative_residual": format(relative, ".17g"),
        })
        if not exact and first_mismatch is None:
            first_mismatch = {
                "sequence": sequence, "element_z": element_z, "compact_row": compact_row,
                "source_population": source_value, "native_population": native_value,
                "ulp_distance": _ulp_distance(source_value, native_value),
                "topology_exact": topology_ok,
            }

    extra_native = len(set(native) - set(source))
    fingerprint_rows: list[dict[str, Any]] = []
    exact_sequence_fingerprints = 0
    exact_element_fingerprints = defaultdict(int)
    for sequence in range(1, 62):
        source_fp = _fnv1a(source_streams.get(sequence, ()))
        native_fp = _fnv1a(native_streams.get(sequence, ()))
        exact = source_fp == native_fp and len(source_streams.get(sequence, ())) == len(native_streams.get(sequence, ()))
        exact_sequence_fingerprints += int(exact)
        fingerprint_rows.append({
            "sequence": sequence, "element_z": 0, "population_count": len(source_streams.get(sequence, ())),
            "source_fingerprint": source_fp, "native_fingerprint": native_fp, "fingerprint_exact": int(exact),
        })
        for z in (1, 2, 12):
            sfp = _fnv1a(source_element_streams.get((sequence, z), ()))
            nfp = _fnv1a(native_element_streams.get((sequence, z), ()))
            eexact = sfp == nfp and len(source_element_streams.get((sequence, z), ())) == len(native_element_streams.get((sequence, z), ()))
            exact_element_fingerprints[z] += int(eexact)
            fingerprint_rows.append({
                "sequence": sequence, "element_z": z,
                "population_count": len(source_element_streams.get((sequence, z), ())),
                "source_fingerprint": sfp, "native_fingerprint": nfp, "fingerprint_exact": int(eexact),
            })

    output.mkdir(parents=True, exist_ok=True)
    with (output / COMPARISON_NAME).open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=comparison_fields)
        writer.writeheader(); writer.writerows(comparison)
    with (output / FINGERPRINT_NAME).open("w", newline="") as handle:
        fields = ["sequence", "element_z", "population_count", "source_fingerprint", "native_fingerprint", "fingerprint_exact"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(fingerprint_rows)

    exact_total = sum(exact_by_element.values())
    gates = {
        "H_COMPACT_POPULATIONS_EXACT": "ACCEPT" if exact_by_element[1] == EXPECTED_BY_ELEMENT[1] else "REJECT",
        "HE_COMPACT_POPULATIONS_EXACT": "ACCEPT" if exact_by_element[2] == EXPECTED_BY_ELEMENT[2] else "REJECT",
        "MG_COMPACT_POPULATIONS_EXACT": "ACCEPT" if exact_by_element[12] == EXPECTED_BY_ELEMENT[12] else "REJECT",
        "ALL_40149_COMPACT_POPULATIONS_EXACT": "ACCEPT" if exact_total == EXPECTED_TOTAL else "REJECT",
        "ALL_61_COMPACT_POPULATION_FINGERPRINTS_EXACT": "ACCEPT" if exact_sequence_fingerprints == 61 else "REJECT",
        "COMPACT_POPULATION_TOPOLOGY_EXACT": "ACCEPT" if topology_mismatches == missing_native == extra_native == 0 else "REJECT",
    }
    result = "ACCEPT" if all(value == "ACCEPT" for value in gates.values()) else "REJECT"
    report = {
        "schema": SCHEMA, "release": RELEASE, "result": result, "accepted_gates": gates,
        "compact_population_values_expected": EXPECTED_TOTAL,
        "compact_population_values_compared": len(comparison),
        "compact_population_values_exact": exact_total,
        "compact_population_values_by_element": {
            str(z): {"expected": EXPECTED_BY_ELEMENT[z], "compared": total_by_element[z], "exact": exact_by_element[z]}
            for z in (1, 2, 12)
        },
        "sequence_fingerprints_exact": exact_sequence_fingerprints,
        "element_fingerprints_exact": {str(z): exact_element_fingerprints[z] for z in (1, 2, 12)},
        "topology_mismatches": topology_mismatches, "missing_native_rows": missing_native,
        "extra_native_rows": extra_native, "first_mismatch": first_mismatch,
        "downstream_thermal_science_ready": result == "ACCEPT",
        "qualification_only": True, "production_promotion_ready": False,
    }
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-capture", type=Path, required=True)
    parser.add_argument("--native-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = audit(args.source_capture, args.native_run, args.output)
    except Exception as exc:
        result = {"schema": SCHEMA, "release": RELEASE, "result": "REJECT", "errors": [str(exc)], "qualification_only": True, "production_promotion_ready": False}
    args.output_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["result"] == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
