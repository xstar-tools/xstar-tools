"""v0.6.48.7.34 Type-56 IEEE and common-xpx qualification audit."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

from .constants import (
    COLLISION_RATE_COEFFICIENT_PER_SQRT_K,
    SOURCE_COLLISION_BOLTZMANN_EV_PER_K,
)

RELEASE = "0.6.48.7.34"
SCHEMA = "xstar-tools-v0648734-type56-ieee-common-xpx-v1"
SUMMARY = "call2_helium_solve_state_rate_matrix_decomposition_summary.json"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def as_int(row: dict[str, str], key: str, default: int = 0) -> int:
    try:
        return int(float(row.get(key, default)))
    except (TypeError, ValueError):
        return default


def as_float(row: dict[str, str], key: str, default: float = math.nan) -> float:
    try:
        return float(row.get(key, default))
    except (TypeError, ValueError):
        return default


def exact(a: float, b: float) -> bool:
    return math.isfinite(a) and math.isfinite(b) and a == b


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-capture", type=Path, required=True)
    parser.add_argument("--native-replay", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    summary_path = args.output / SUMMARY
    base = json.loads(summary_path.read_text())
    gates = dict(base.get("gates", {}))

    source_rows = read_csv(
        args.source_capture / "v0472_call2_eval1_he_type56_records.csv"
    )
    native_rows = read_csv(
        args.native_replay / "diagnostics/evaluation_0022_records.csv"
    )
    native_terms = read_csv(
        args.native_replay / "diagnostics/evaluation_0022_helium_source_order_terms.csv"
    )
    term_comparison = read_csv(args.output / "call2_he_metadata_keyed_term_comparison.csv")
    state = json.loads(
        (args.native_replay / "diagnostics/evaluation_0022_state.json").read_text()
    )

    source_by_record = {
        as_int(row, "record"): row for row in source_rows if as_int(row, "data_type") == 56
    }
    native_by_record = {
        as_int(row, "record"): row
        for row in native_rows
        if as_int(row, "element_z") == 2
        and as_int(row, "data_type") == 56
        and as_int(row, "matrix_committed") == 1
    }

    comparisons: list[dict[str, Any]] = []
    for record in sorted(set(source_by_record) | set(native_by_record)):
        source = source_by_record.get(record, {})
        native = native_by_record.get(record, {})
        row: dict[str, Any] = {
            "record": record,
            "source_present": bool(source),
            "native_present": bool(native),
            "source_temperature_K": as_float(source, "temperature_K"),
            "native_temperature_K": float(state.get("temperature_k", math.nan)),
        }
        pairs = (
            ("upsilon", "upsilon", "type56_upsilon"),
            ("ans1", "ans1", "ans1"),
            ("ans2", "ans2", "ans2"),
            ("ans5", "ans5", "ans5"),
            ("ans6", "ans6", "ans6"),
        )
        for label, source_key, native_key in pairs:
            sv = as_float(source, source_key)
            nv = as_float(native, native_key)
            row[f"source_{label}"] = sv
            row[f"native_{label}"] = nv
            row[f"{label}_exact"] = exact(sv, nv)
            row[f"{label}_abs_delta"] = abs(nv - sv) if math.isfinite(sv) and math.isfinite(nv) else math.inf
        comparisons.append(row)
    write_csv(args.output / "call2_he_type56_record_comparison.csv", comparisons)

    hydrogen_density = float(state.get("hydrogen_density_cm3", math.nan))
    xpx_rows: list[dict[str, Any]] = []
    for term in native_terms:
        scale = as_float(term, "density_scale")
        xpx_rows.append(
            {
                "source_order_index": as_int(term, "source_order_index"),
                "record": as_int(term, "record"),
                "data_type": as_int(term, "data_type"),
                "role": term.get("role", ""),
                "density_scale": scale,
                "hydrogen_density_cm3": hydrogen_density,
                "common_xpx_exact": exact(scale, hydrogen_density),
            }
        )
    write_csv(args.output / "call2_he_common_xpx_scaling.csv", xpx_rows)

    type56_terms = [row for row in term_comparison if as_int(row, "data_type") == 56]
    type56_terms_exact = bool(type56_terms) and all(
        str(row.get(f"{name}_exact", "")).lower() == "true"
        for row in type56_terms
        for name in ("aj1", "aj2", "cj", "cj2")
    )
    source_records_complete = len(source_by_record) == 411
    native_records_complete = len(native_by_record) == 411
    record_sets_exact = source_by_record.keys() == native_by_record.keys()

    def field_exact(name: str) -> bool:
        return bool(comparisons) and all(bool(row.get(f"{name}_exact")) for row in comparisons)

    common_xpx_exact = len(xpx_rows) == 5232 and all(row["common_xpx_exact"] for row in xpx_rows)
    type53_not_double = bool([r for r in xpx_rows if r["data_type"] == 53]) and all(
        row["common_xpx_exact"] for row in xpx_rows if row["data_type"] == 53
    )
    type63_not_double = bool([r for r in xpx_rows if r["data_type"] == 63]) and all(
        row["common_xpx_exact"] for row in xpx_rows if row["data_type"] == 63
    )

    gates.update(
        {
            "CALL2_HE_TYPE56_SOURCE_RECORD_CAPTURE": "ACCEPT" if source_records_complete else "REJECT",
            "CALL2_HE_TYPE56_NATIVE_RECORD_CAPTURE": "ACCEPT" if native_records_complete else "REJECT",
            "CALL2_HE_TYPE56_RECORD_IDENTITY": "ACCEPT" if record_sets_exact else "REJECT",
            "CALL2_HE_TYPE56_UPSILON_EXACT": "ACCEPT" if field_exact("upsilon") else "REJECT",
            "CALL2_HE_TYPE56_ANS1_EXACT": "ACCEPT" if field_exact("ans1") else "REJECT",
            "CALL2_HE_TYPE56_ANS2_EXACT": "ACCEPT" if field_exact("ans2") else "REJECT",
            "CALL2_HE_TYPE56_ANS5_EXACT": "ACCEPT" if field_exact("ans5") else "REJECT",
            "CALL2_HE_TYPE56_ANS6_EXACT": "ACCEPT" if field_exact("ans6") else "REJECT",
            "CALL2_HE_TYPE56_THERMAL_COEFFICIENTS_EXACT": "ACCEPT" if type56_terms_exact else "REJECT",
            "CALL2_HE_TYPE56_RATE_MATRIX": "ACCEPT" if type56_terms_exact else "REJECT",
            "CALL2_HE_COMMON_XPX_MATRIX_SCALING": "ACCEPT" if common_xpx_exact else "REJECT",
            "CALL2_HE_TYPE53_NOT_DOUBLE_SCALED": "ACCEPT" if type53_not_double else "REJECT",
            "CALL2_HE_TYPE63_NOT_DOUBLE_SCALED": "ACCEPT" if type63_not_double else "REJECT",
        }
    )

    inherited = all(
        gates.get(name) == "ACCEPT"
        for name in (
            "CALL2_HE_COMPACT_SEED_MAPPING",
            "CALL2_HE_TRANSFORMED_INITIAL_STATE",
            "CALL2_HE_RHS_CONSTRUCTION",
            "CALL2_HE_TERM_STREAM_COMPLETE",
            "CALL2_HE_TYPE63_ENDPOINT_ORIENTATION",
            "CALL2_HE_TYPE95_SELF_LOOP_1629_ABSENT",
            "CALL2_HE_TYPE95_SELF_LOOP_1980_ABSENT",
        )
    )
    targeted = all(
        gates.get(name) == "ACCEPT"
        for name in (
            "CALL2_HE_TYPE56_SOURCE_RECORD_CAPTURE",
            "CALL2_HE_TYPE56_NATIVE_RECORD_CAPTURE",
            "CALL2_HE_TYPE56_RECORD_IDENTITY",
            "CALL2_HE_TYPE56_UPSILON_EXACT",
            "CALL2_HE_TYPE56_ANS1_EXACT",
            "CALL2_HE_TYPE56_ANS2_EXACT",
            "CALL2_HE_TYPE56_ANS5_EXACT",
            "CALL2_HE_TYPE56_ANS6_EXACT",
            "CALL2_HE_TYPE56_THERMAL_COEFFICIENTS_EXACT",
            "CALL2_HE_COMMON_XPX_MATRIX_SCALING",
            "CALL2_HE_TYPE53_NOT_DOUBLE_SCALED",
            "CALL2_HE_TYPE63_NOT_DOUBLE_SCALED",
        )
    )

    report = dict(base)
    report.update(
        {
            "schema": SCHEMA,
            "release": RELEASE,
            "result": "ACCEPT" if inherited and targeted else "REJECT",
            "source_type56_records": len(source_by_record),
            "native_type56_records": len(native_by_record),
            "type56_record_exact": sum(
                all(bool(row.get(f"{name}_exact")) for name in ("upsilon", "ans1", "ans2", "ans5", "ans6"))
                for row in comparisons
            ),
            "type56_terms": len(type56_terms),
            "type56_exact_terms": sum(
                all(str(row.get(f"{name}_exact", "")).lower() == "true" for name in ("aj1", "aj2", "cj", "cj2"))
                for row in type56_terms
            ),
            "common_xpx_exact_terms": sum(row["common_xpx_exact"] for row in xpx_rows),
            "common_xpx_term_count": len(xpx_rows),
            "source_collision_boltzmann_ev_per_k": SOURCE_COLLISION_BOLTZMANN_EV_PER_K,
            "type56_collision_rate_coefficient_per_sqrt_k": COLLISION_RATE_COEFFICIENT_PER_SQRT_K,
            "type56_expression_order": "sqrt(T), shared source collision coefficient, Python q_rates_from_upsilon",
            "physics_change_scope": "Type-56 IEEE coefficient restoration and source-general cj/cj2 xpx insertion scaling",
            "physics_changed": True,
            "qualification_only": True,
            "production_promotion_ready": False,
            "gates": gates,
        }
    )
    summary_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["result"] == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
