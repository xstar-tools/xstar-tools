"""Audit shared immutable canonical Thermal-term ownership for v0.6.48.7.46.21.4."""
from __future__ import annotations

import argparse
import csv
import json
import struct
from collections import defaultdict
from pathlib import Path
from typing import Any

RELEASE = "0.6.48.7.46.21.4"
SCHEMA = "xstar-tools-v0648746213-canonical-thermal-term-ownership-v1"
COMPARISON_NAME = "v048746212_canonical_thermal_term_comparison.csv"


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _double_exact(left: str, right: str) -> bool:
    return struct.pack("<d", float(left)) == struct.pack("<d", float(right))


def audit(native_run: Path, output: Path) -> dict[str, Any]:
    canonical_path = native_run / "native_all61_canonical_thermal_terms.csv"
    diagonal_path = native_run / "native_all61_thermal_diagonal_ledger.csv"
    if not canonical_path.is_file() or not diagonal_path.is_file():
        missing = [str(path) for path in (canonical_path, diagonal_path) if not path.is_file()]
        raise FileNotFoundError("canonical or diagonal Thermal ledger is missing: " + ", ".join(missing))

    canonical = _read(canonical_path)
    diagonal = _read(diagonal_path)
    diagonal_by_key: dict[tuple[int, int, int], dict[str, str]] = {}
    for row in diagonal:
        key = (int(row["sequence"]), int(row["element_z"]), int(row["source_order_index"]))
        if key in diagonal_by_key:
            raise RuntimeError(f"duplicate diagonal Thermal key: {key}")
        diagonal_by_key[key] = row

    comparison: list[dict[str, Any]] = []
    per_sequence_elements: dict[int, set[int]] = defaultdict(set)
    per_group_indices: dict[tuple[int, int], list[int]] = defaultdict(list)
    per_group_fingerprints: dict[tuple[int, int], set[str]] = defaultdict(set)
    ownership_exact = 0
    insertion_captured_exact = 0
    diagonal_exact = 0

    integer_pairs = (
        ("source_position", "source_position"),
        ("record", "record"),
        ("data_type", "data_type"),
        ("rate_type", "rate_type"),
        ("ion_index", "ion_index"),
        ("ion_stage", "ion_stage"),
        ("compact_row", "compact_row"),
        ("native_compact_row", "native_compact_row"),
        ("source_compact_row", "source_compact_row"),
        ("is_normalization_row", "is_normalization_row"),
        ("source_domain_included", "source_domain_included"),
        ("type99_source_corrected", "magnesium_type99_primary_cooling_reduction_applied"),
        ("primary_source_ordered", "magnesium_primary_cooling_source_order_applied"),
        ("primary_source_order_index", "magnesium_primary_cooling_source_order_index"),
    )
    double_pairs = (
        ("cj", "cj"),
        ("cj2", "cj2"),
        ("native_cj", "native_cj"),
        ("source_cj", "source_cj"),
    )

    canonical_keys: set[tuple[int, int, int]] = set()
    for row in canonical:
        sequence = int(row["sequence"])
        element_z = int(row["element_z"])
        term_index = int(row["term_index"])
        key = (sequence, element_z, term_index)
        if key in canonical_keys:
            raise RuntimeError(f"duplicate canonical Thermal key: {key}")
        canonical_keys.add(key)
        per_sequence_elements[sequence].add(element_z)
        per_group_indices[(sequence, element_z)].append(term_index)

        fingerprint = row["ledger_fingerprint"]
        per_group_fingerprints[(sequence, element_z)].add(fingerprint)
        owned = (
            row["shared_ownership"] == "1"
            and fingerprint == row["element_consumer_fingerprint"]
            and fingerprint == row["fixed_state_consumer_fingerprint"]
        )
        ownership_exact += int(owned)
        insertion_captured = row.get("matrix_insertion_captured") == "1"
        insertion_captured_exact += int(insertion_captured)

        diag = diagonal_by_key.get(key)
        identity_exact = diag is not None
        if diag is not None:
            identity_exact = identity_exact and row["role"] == diag["role"]
            identity_exact = identity_exact and all(
                row[canonical_field] == diag[diagonal_field]
                for canonical_field, diagonal_field in integer_pairs
            )
            identity_exact = identity_exact and all(
                _double_exact(row[canonical_field], diag[diagonal_field])
                for canonical_field, diagonal_field in double_pairs
            )
        diagonal_exact += int(identity_exact)

        if not owned or not insertion_captured or not identity_exact:
            comparison.append(
                {
                    "sequence": sequence,
                    "element_z": element_z,
                    "term_index": term_index,
                    "ownership_exact": int(owned),
                    "matrix_insertion_captured": int(insertion_captured),
                    "diagonal_exact": int(identity_exact),
                    "ledger_fingerprint": fingerprint,
                }
            )

    extra_diagonal = len(set(diagonal_by_key) - canonical_keys)
    sequences_exact = sum(per_sequence_elements[sequence] == {1, 2, 12} for sequence in range(1, 62))
    fingerprint_groups_exact = sum(
        len(per_group_fingerprints[(sequence, element_z)]) == 1
        for sequence in range(1, 62)
        for element_z in (1, 2, 12)
    )
    term_indices_exact = len(per_group_indices) == 183 and all(
        sorted(values) == list(range(1, len(values) + 1))
        for values in per_group_indices.values()
    )

    gates = {
        "CANONICAL_THERMAL_LEDGER_PRESENT_ALL61": (
            "ACCEPT" if sequences_exact == 61 and len(per_group_indices) == 183 and len(canonical) > 0 else "REJECT"
        ),
        "CANONICAL_THERMAL_LEDGER_SHARED_OWNERSHIP": (
            "ACCEPT" if ownership_exact == len(canonical) else "REJECT"
        ),
        "CANONICAL_TERMS_CAPTURED_AT_MATRIX_INSERTION": (
            "ACCEPT" if insertion_captured_exact == len(canonical) else "REJECT"
        ),
        "ELEMENT_FIXED_STATE_LEDGER_FINGERPRINTS_IDENTICAL": (
            "ACCEPT" if fingerprint_groups_exact == 183 else "REJECT"
        ),
        "CANONICAL_THERMAL_TERM_INDICES_CONTIGUOUS": (
            "ACCEPT" if term_indices_exact else "REJECT"
        ),
        "CANONICAL_DIAGONAL_LEDGER_IDENTITY": (
            "ACCEPT"
            if diagonal_exact == len(canonical) == len(diagonal) and extra_diagonal == 0
            else "REJECT"
        ),
    }
    result = "ACCEPT" if all(value == "ACCEPT" for value in gates.values()) else "REJECT"

    output.mkdir(parents=True, exist_ok=True)
    fields = [
        "sequence", "element_z", "term_index", "ownership_exact",
        "matrix_insertion_captured", "diagonal_exact", "ledger_fingerprint",
    ]
    with (output / COMPARISON_NAME).open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(comparison)

    return {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": result,
        "accepted_gates": gates,
        "canonical_term_rows": len(canonical),
        "diagonal_term_rows": len(diagonal),
        "ownership_exact_rows": ownership_exact,
        "matrix_insertion_captured_rows": insertion_captured_exact,
        "diagonal_identity_exact_rows": diagonal_exact,
        "sequence_element_groups": len(per_group_indices),
        "fingerprint_groups_exact": fingerprint_groups_exact,
        "sequences_with_all_elements": sequences_exact,
        "extra_diagonal_rows": extra_diagonal,
        "first_mismatch": comparison[0] if comparison else None,
        "qualification_only": True,
        "production_promotion_ready": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--native-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = audit(args.native_run, args.output)
    except Exception as exc:
        result = {
            "schema": SCHEMA,
            "release": RELEASE,
            "result": "REJECT",
            "errors": [str(exc)],
            "qualification_only": True,
            "production_promotion_ready": False,
        }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["result"] == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
