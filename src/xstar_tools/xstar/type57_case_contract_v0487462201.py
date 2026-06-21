"""Validate that a lowered native case carries the v21.10 Type-57 literal payload."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

RELEASE = "0.6.48.7.46.21.11"
SCHEMA = "xstar-tools-v06487462201-type57-fresh-lowered-case-contract-v1"


def _read_numbers(path: Path, cast: type[float] | type[int]) -> list[float] | list[int]:
    values: list[float] | list[int] = []
    for line_number, raw in enumerate(path.read_text().splitlines(), start=1):
        text = raw.strip()
        if not text:
            continue
        try:
            values.append(cast(text))
        except ValueError as exc:
            raise ValueError(f"invalid numeric value in {path.name}:{line_number}: {text!r}") from exc
    return values


def validate_case(case_dir: Path) -> dict[str, Any]:
    root = case_dir.resolve()
    required = [root / "records.csv", root / "reals.txt", root / "ints.txt", root / "elements.csv"]
    errors = [f"missing:{path.name}" for path in required if not path.is_file()]
    if errors:
        return {
            "schema": SCHEMA, "release": RELEASE, "result": "REJECT",
            "case_dir": str(root), "errors": errors,
            "type57_records": 0, "magnesium_type57_records": 0,
            "production_promotion_ready": False, "qualification_only": True,
        }

    reals = [float(v) for v in _read_numbers(root / "reals.txt", float)]
    ints = [int(v) for v in _read_numbers(root / "ints.txt", int)]
    with (root / "elements.csv").open(newline="") as handle:
        element_z = {int(row["element_index"]): int(row["element_z"]) for row in csv.DictReader(handle)}
    with (root / "records.csv").open(newline="") as handle:
        records = list(csv.DictReader(handle))

    type57 = [row for row in records if int(row["data_type"]) == 57]
    magnesium = 0
    valid = 0
    real_counts: set[int] = set()
    int_counts: set[int] = set()
    for row in type57:
        record = int(row["record"])
        z = element_z.get(int(row["element_index"]), -1)
        magnesium += int(z == 12)
        ro = int(row["real_offset"])
        rc = int(row["real_count"])
        io = int(row["int_offset"])
        ic = int(row["int_count"])
        real_counts.add(rc)
        int_counts.add(ic)
        if rc < 4 or ic < 3:
            errors.append(f"record:{record}:short-payload:real_count={rc}:int_count={ic}")
            continue
        if ro < 0 or ro + rc > len(reals) or io < 0 or io + ic > len(ints):
            errors.append(f"record:{record}:payload-out-of-range")
            continue
        e1, eth, g1, g2 = reals[ro : ro + 4]
        local = ints[io + 2]
        line_energy = float(row["line_energy_ev"])
        if not all(math.isfinite(value) for value in (e1, eth, g1, g2, line_energy)):
            errors.append(f"record:{record}:nonfinite-payload")
            continue
        if eth < 0.0 or g1 <= 0.0 or g2 <= 0.0 or local <= 0:
            errors.append(
                f"record:{record}:invalid-payload:e1={e1}:eth={eth}:g1={g1}:g2={g2}:local={local}"
            )
            continue
        if format(line_energy, ".17g") != format(eth, ".17g"):
            errors.append(f"record:{record}:line-energy-not-source-threshold:{line_energy}!={eth}")
            continue
        valid += 1

    if not type57:
        errors.append("no-type57-records")
    if magnesium != 368:
        errors.append(f"magnesium-type57-inventory:{magnesium}:expected:368")
    result = "ACCEPT" if not errors and valid == len(type57) else "REJECT"
    return {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": result,
        "case_dir": str(root),
        "errors": errors,
        "type57_records": len(type57),
        "valid_type57_records": valid,
        "magnesium_type57_records": magnesium,
        "real_count_values": sorted(real_counts),
        "int_count_values": sorted(int_counts),
        "real_payload_values": len(reals),
        "integer_payload_values": len(ints),
        "qualification_only": True,
        "production_promotion_ready": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-dir", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = validate_case(args.case_dir)
    except Exception as exc:  # fail closed with a machine-readable report
        report = {
            "schema": SCHEMA, "release": RELEASE, "result": "REJECT",
            "case_dir": str(args.case_dir.resolve()), "errors": [str(exc)],
            "type57_records": 0, "magnesium_type57_records": 0,
            "qualification_only": True, "production_promotion_ready": False,
        }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["result"] == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
