"""Audit the canonical v0.6.47.2 binary64 continuum-grid hotfix."""
from __future__ import annotations

import argparse
import csv
import json
import math
import struct
from pathlib import Path
from typing import Any

import numpy as np

from .all61_native_replay_aggregate import CONTINUUM_WORKSPACE_LEDGER_NAME, THERMAL_LEDGER_NAME

RELEASE = "0.6.48.7.46.18.1"
SCHEMA = "xstar-tools-v0648746171-continuum-grid-binary64-hotfix-v1"
COMPONENTS = (
    "cmp1", "cmp2", "htcomp", "clcomp", "htfreef", "clbrems",
    "continuum_heating", "continuum_cooling",
    "continuum_heating2", "continuum_cooling2",
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def bits(value: float) -> bytes:
    return struct.pack(">d", float(value))


def exact(left: float, right: float) -> bool:
    return math.isfinite(left) and math.isfinite(right) and bits(left) == bits(right)


def ordered_int(value: float) -> int:
    integer = struct.unpack(">q", bits(value))[0]
    return 0x8000000000000000 - integer if integer < 0 else integer


def ulp(left: float, right: float) -> int:
    if not math.isfinite(left) or not math.isfinite(right):
        return 2**63 - 1
    return abs(ordered_int(left) - ordered_int(right))


def canonical_epim_binary64() -> np.ndarray:
    """Return the immutable v0.6.47.2 ``physical_runner.ener_grid(999)``."""
    count = 999
    tail = max(2, count // 50)
    logarithmic = count - tail
    energy = np.zeros(count, dtype=np.float64)
    energy[0] = 0.1
    ratio = (4.0e5 / 0.1) ** (1.0 / float(logarithmic - 1))
    for index in range(1, logarithmic):
        energy[index] = energy[index - 1] * ratio
    ratio2 = (1.0e6 / 4.0e5) ** (1.0 / float(tail - 1))
    for index in range(logarithmic, count):
        energy[index] = energy[index - 1] * ratio2
    return energy


def huntf(grid: np.ndarray, value: float) -> int:
    count = len(grid)
    tiny = float(np.float32(1.0e-34))
    temporary = max(value, float(grid[1]))
    index = 1
    if value < tiny or grid[0] <= tiny or grid[-1] <= tiny:
        return index
    index = int(
        (count - 1)
        * math.log(temporary / grid[0])
        / math.log(grid[-1] / grid[0])
    ) + 1
    if index < count:
        first = abs(math.log(value / (tiny + grid[index - 1])))
        second = abs(math.log(value / (tiny + grid[index])))
        if second < first:
            index += 1
    return max(1, min(count, index))


def reconstruct(
    full_epi: np.ndarray, full_bremsa: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    epim = canonical_epim_binary64()
    logarithmic = len(full_epi) - max(2, len(full_epi) // 50)
    domain = full_epi[:logarithmic]
    indices = np.asarray([huntf(domain, float(value)) for value in epim], dtype=np.int64)
    return epim, indices, full_bremsa[indices - 1]


def compare(
    source_capture: Path,
    native_run: Path,
    component_comparison: Path,
    output: Path,
) -> dict[str, Any]:
    inputs = read_csv(source_capture / "v0472_all61_input_states.csv")
    native = read_csv(native_run / CONTINUUM_WORKSPACE_LEDGER_NAME)
    thermal = read_csv(native_run / THERMAL_LEDGER_NAME)
    components = read_csv(component_comparison)

    by_sequence: dict[int, list[dict[str, str]]] = {}
    for row in native:
        by_sequence.setdefault(int(row["sequence"]), []).append(row)

    canonical = canonical_epim_binary64()
    workspace_rows: list[dict[str, Any]] = []
    epim_exact = map_exact = bremsam_exact = total = 0
    errors: list[str] = []

    for source in inputs:
        sequence = int(source["sequence"])
        call = int(source["dsec_call_id"])
        root = source_capture / "all61_input_workspaces" / f"evaluation_{sequence:04d}"
        full_epi = np.fromfile(root / f"call_{call}_radiation_energy.bin", dtype=np.float64)
        full_bremsa = np.fromfile(root / f"call_{call}_bremsa.bin", dtype=np.float64)
        epim, indices, bremsam = reconstruct(full_epi, full_bremsa)
        rows = sorted(
            by_sequence.get(sequence, []),
            key=lambda row: int(row["reduced_bin_one_based"]),
        )
        if len(rows) != 999:
            errors.append(f"sequence_{sequence:04d}:rows={len(rows)}")
            continue
        sequence_epim = sequence_map = sequence_bremsam = 0
        for index, row in enumerate(rows):
            sequence_epim += exact(float(row["epim_ev"]), float(epim[index]))
            sequence_map += int(int(row["full_bin_one_based"]) == int(indices[index]))
            sequence_bremsam += exact(float(row["bremsam"]), float(bremsam[index]))
        epim_exact += sequence_epim
        map_exact += sequence_map
        bremsam_exact += sequence_bremsam
        total += 999
        workspace_rows.append(
            {
                "sequence": sequence,
                "rows": 999,
                "epim_exact": sequence_epim,
                "bremsmap_exact": sequence_map,
                "bremsam_exact": sequence_bremsam,
                "first_index": int(indices[0]),
                "last_index": int(indices[-1]),
            }
        )

    canonical_exact = 0
    first_rows = sorted(
        by_sequence.get(1, []), key=lambda row: int(row["reduced_bin_one_based"])
    )
    if len(first_rows) == 999:
        canonical_exact = sum(
            exact(float(row["epim_ev"]), float(canonical[index]))
            for index, row in enumerate(first_rows)
        )

    component_rows: list[dict[str, Any]] = []
    summary: dict[str, dict[str, Any]] = {}
    for name in COMPONENTS:
        rows = [row for row in components if row["component"] == name]
        bit_exact = 0
        max_abs = max_rel = 0.0
        max_ulp = 0
        first_nonexact_sequence: int | None = None
        for row in rows:
            source = float(row["source_value"])
            native_value = float(row["computed_native_value"])
            difference = abs(native_value - source)
            relative = difference / max(abs(source), 1.0e-300)
            is_exact = exact(source, native_value)
            bit_exact += is_exact
            if not is_exact and first_nonexact_sequence is None:
                first_nonexact_sequence = int(row["sequence"])
            max_abs = max(max_abs, difference)
            max_rel = max(max_rel, relative)
            max_ulp = max(max_ulp, ulp(source, native_value))
        summary[name] = {
            "rows": len(rows),
            "bit_exact": bit_exact,
            "max_abs_residual": max_abs,
            "max_rel_residual": max_rel,
            "max_ulp_distance": max_ulp,
            "first_nonexact_sequence": first_nonexact_sequence,
        }
        component_rows.append({"component": name, **summary[name]})

    flags = sum(row.get("continuum_workspace_source_faithful") == "1" for row in thermal)
    counts = sum(
        row.get("continuum_epim_count") == "999"
        and row.get("continuum_bremsam_count") == "999"
        and row.get("continuum_bremsmap_count") == "999"
        for row in thermal
    )

    gates = {
        "ALL_61_CONTINUUM_WORKSPACES_RECONSTRUCTED": (
            "ACCEPT" if len(workspace_rows) == 61 and total == 60939 else "REJECT"
        ),
        "CONTINUUM_EPIM_CANONICAL_BINARY64_VALUES_EXACT_999": (
            "ACCEPT" if canonical_exact == 999 else "REJECT"
        ),
        "CONTINUUM_EPIM_BINARY64_VALUES_EXACT_60939": (
            "ACCEPT" if epim_exact == 60939 else "REJECT"
        ),
        "CONTINUUM_BREMSMAP_INDICES_EXACT_60939": (
            "ACCEPT" if map_exact == 60939 else "REJECT"
        ),
        "CONTINUUM_BREMSAM_VALUES_EXACT_60939": (
            "ACCEPT" if bremsam_exact == 60939 else "REJECT"
        ),
        "CONTINUUM_WORKSPACE_CANONICAL_V0472_61": (
            "ACCEPT" if flags == 61 and counts == 61 else "REJECT"
        ),
        "CMP1_BIT_EXACT_61": "ACCEPT" if summary["cmp1"]["bit_exact"] == 61 else "REJECT",
        "CMP2_BIT_EXACT_61": "ACCEPT" if summary["cmp2"]["bit_exact"] == 61 else "REJECT",
        "HTCOMP_BIT_EXACT_61": "ACCEPT" if summary["htcomp"]["bit_exact"] == 61 else "REJECT",
        "CLCOMP_BIT_EXACT_61": "ACCEPT" if summary["clcomp"]["bit_exact"] == 61 else "REJECT",
        "HTFREEF_BIT_EXACT_61": "ACCEPT" if summary["htfreef"]["bit_exact"] == 61 else "REJECT",
        "CLBREMS_BIT_EXACT_61": "ACCEPT" if summary["clbrems"]["bit_exact"] == 61 else "REJECT",
        "CONTINUUM_TOTAL_COMPONENTS_BIT_EXACT_244": (
            "ACCEPT"
            if sum(summary[name]["bit_exact"] for name in COMPONENTS[6:]) == 244
            else "REJECT"
        ),
        "ALL_CONTINUUM_COMPONENTS_BIT_EXACT_610": (
            "ACCEPT"
            if sum(summary[name]["bit_exact"] for name in COMPONENTS) == 610
            else "REJECT"
        ),
        "CONTINUUM_UNEXPLAINED_COMPONENT_DELTAS_ZERO": (
            "ACCEPT"
            if all(summary[name]["bit_exact"] == 61 for name in COMPONENTS)
            else "REJECT"
        ),
    }
    result = "ACCEPT" if not errors and all(value == "ACCEPT" for value in gates.values()) else "REJECT"
    report = {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": result,
        "errors": errors,
        "workspace_rows": total,
        "epim_exact": epim_exact,
        "bremsmap_exact": map_exact,
        "bremsam_exact": bremsam_exact,
        "component_summary": summary,
        "gates": gates,
        "qualification_only": True,
        "production_promotion_ready": False,
    }
    output.mkdir(parents=True, exist_ok=True)
    write_csv(
        output / "v048746171_continuum_workspace_summary.csv",
        list(workspace_rows[0]) if workspace_rows else ["sequence"],
        workspace_rows,
    )
    write_csv(
        output / "v048746171_continuum_component_summary.csv",
        list(component_rows[0]) if component_rows else ["component"],
        component_rows,
    )
    (output / "v048746171_continuum_grid_binary64_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-capture", type=Path, required=True)
    parser.add_argument("--native-run", type=Path, required=True)
    parser.add_argument("--component-comparison", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--output-json", type=Path)
    arguments = parser.parse_args(argv)
    try:
        report = compare(
            arguments.source_capture,
            arguments.native_run,
            arguments.component_comparison,
            arguments.output,
        )
    except Exception as error:  # fail closed for production qualification
        report = {
            "schema": SCHEMA,
            "release": RELEASE,
            "result": "REJECT",
            "errors": [str(error)],
            "qualification_only": True,
            "production_promotion_ready": False,
        }
    if arguments.output_json:
        arguments.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["result"] == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
