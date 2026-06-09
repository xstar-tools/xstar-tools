"""Compiler and validator for v0.6.48.2 raw native fixed-state programs.

The program format stores topology, raw formula opcodes, and atomic coefficients.
It deliberately rejects evaluated answers, final populations, science products,
and reference trajectories so it cannot be used as a replay cache.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Iterable

PROGRAM_ABI = 60482
SUPPORTED_OPCODES = {1, 49, 50, 51, 53, 63, 69, 74, 88, 99}
FORBIDDEN_KEYS = {
    "ans1", "ans2", "ans3", "ans4", "ans5", "ans6",
    "final_population", "final_populations", "terminal_state",
    "hmctot", "elcter", "science_file", "science_files",
    "trajectory", "reference_output", "reference_outputs",
}


@dataclass(frozen=True)
class ProgramValidation:
    program_id: str
    elements: int
    rows: int
    records: int
    real_values: int
    integer_values: int
    opcodes: tuple[int, ...]


def _walk_forbidden(value: Any, path: str = "root") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in FORBIDDEN_KEYS:
                raise ValueError(f"evaluated/replay field is forbidden at {path}.{key}")
            _walk_forbidden(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _walk_forbidden(child, f"{path}[{index}]")


def _as_int(value: Any, field: str) -> int:
    try:
        return int(value)
    except Exception as exc:
        raise ValueError(f"invalid integer {field}: {value!r}") from exc


def _as_float(value: Any, field: str) -> float:
    try:
        result = float(value)
    except Exception as exc:
        raise ValueError(f"invalid float {field}: {value!r}") from exc
    if not (result == result and abs(result) != float("inf")):
        raise ValueError(f"non-finite float {field}: {value!r}")
    return result


def compile_program_spec(spec_path: str | Path, output_dir: str | Path) -> ProgramValidation:
    spec = json.loads(Path(spec_path).read_text())
    _walk_forbidden(spec)
    if _as_int(spec.get("program_abi", PROGRAM_ABI), "program_abi") != PROGRAM_ABI:
        raise ValueError(f"program_abi must be {PROGRAM_ABI}")
    program_id = str(spec.get("program_id") or "").strip()
    if not program_id:
        raise ValueError("program_id is required")
    elements = list(spec.get("elements") or [])
    records = list(spec.get("records") or [])
    if not elements or not records:
        raise ValueError("at least one element and one record are required")

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    reals: list[float] = []
    ints: list[int] = []
    element_rows: list[dict[str, Any]] = []
    element_table: list[dict[str, Any]] = []

    for element_index, element in enumerate(elements):
        rows = list(element.get("rows") or [])
        if not rows:
            raise ValueError(f"element {element_index} has no rows")
        n_rows = len(rows)
        element_records = [i for i, record in enumerate(records) if _as_int(record.get("element_index", -1), "element_index") == element_index]
        if not element_records:
            raise ValueError(f"element {element_index} has no records")
        if element_records != list(range(element_records[0], element_records[0] + len(element_records))):
            raise ValueError("records for each element must be contiguous in source order")
        element_table.append({
            "element_index": element_index,
            "element_z": _as_int(element["element_z"], "element_z"),
            "n_rows": n_rows,
            "n_superlevels": _as_int(element.get("n_superlevels", n_rows), "n_superlevels"),
            "n_ions": _as_int(element["n_ions"], "n_ions"),
            "normalization_row": _as_int(element.get("normalization_row", n_rows), "normalization_row"),
            "record_head": element_records[0],
            "record_count": len(element_records),
        })
        for row_index, row in enumerate(rows, start=1):
            element_rows.append({
                "element_index": element_index,
                "row": row_index,
                "superlevel": _as_int(row.get("superlevel", row_index), "superlevel"),
                "ion": _as_int(row["ion"], "ion"),
                "ion_charge": _as_int(row.get("ion_charge", 0), "ion_charge"),
                "initial_population": _as_float(row.get("initial_population", 0.0), "initial_population"),
                "energy_ev": _as_float(row.get("energy_ev", 0.0), "energy_ev"),
                "statistical_weight": _as_float(row.get("statistical_weight", 1.0), "statistical_weight"),
            })

    record_table: list[dict[str, Any]] = []
    opcodes: set[int] = set()
    for index, record in enumerate(records):
        opcode = _as_int(record["opcode"], "opcode")
        if opcode not in SUPPORTED_OPCODES:
            raise ValueError(f"unsupported native opcode {opcode} at record {index}")
        opcodes.add(opcode)
        element_index = _as_int(record["element_index"], "element_index")
        payload_reals = [_as_float(v, "real payload") for v in record.get("reals", [])]
        payload_ints = [_as_int(v, "integer payload") for v in record.get("ints", [])]
        real_offset = len(reals)
        int_offset = len(ints)
        reals.extend(payload_reals)
        ints.extend(payload_ints)
        next_index = record.get("next_index")
        if next_index is None:
            next_index = index + 1 if index + 1 < len(records) and _as_int(records[index + 1]["element_index"], "element_index") == element_index else -1
        record_table.append({
            "source_position": _as_int(record.get("source_position", 4 * (index + 1)), "source_position"),
            "record": _as_int(record.get("record", index + 1), "record"),
            "next_index": _as_int(next_index, "next_index"),
            "element_index": element_index,
            "opcode": opcode,
            "data_type": _as_int(record.get("data_type", opcode), "data_type"),
            "rate_type": _as_int(record.get("rate_type", 1), "rate_type"),
            "ion_index": _as_int(record.get("ion_index", 1), "ion_index"),
            "ion_stage": _as_int(record.get("ion_stage", 1), "ion_stage"),
            "lower_row": _as_int(record["lower_row"], "lower_row"),
            "upper_row": _as_int(record["upper_row"], "upper_row"),
            "real_offset": real_offset,
            "real_count": len(payload_reals),
            "int_offset": int_offset,
            "int_count": len(payload_ints),
            "density_scale": _as_float(record.get("density_scale", 1.0), "density_scale"),
            "line_energy_ev": _as_float(record.get("line_energy_ev", 0.0), "line_energy_ev"),
            "atomic_mass_amu": _as_float(record.get("atomic_mass_amu", 1.0), "atomic_mass_amu"),
        })

    (out / "manifest.txt").write_text(
        f"program_abi={PROGRAM_ABI}\n"
        f"program_id={program_id}\n"
        "program_kind=raw_atomic_coefficients\n"
        "contains_evaluated_results=false\n"
        f"element_count={len(element_table)}\n"
        f"record_count={len(record_table)}\n"
    )
    _write_csv(out / "elements.csv", element_table)
    _write_csv(out / "rows.csv", element_rows)
    _write_csv(out / "records.csv", record_table)
    (out / "reals.txt").write_text("".join(f"{value:.17g}\n" for value in reals))
    (out / "ints.txt").write_text("".join(f"{value}\n" for value in ints))
    validation = validate_program_directory(out)
    (out / "coverage.json").write_text(json.dumps({
        "schema_version": "0.6.48.2",
        "program_id": validation.program_id,
        "native_opcodes": list(validation.opcodes),
        "unsupported_opcodes": [],
        "contains_evaluated_results": False,
        "production_promotion_ready": False,
        "reason": "host ATDB and exact output-schema qualification not yet run",
    }, indent=2, sort_keys=True) + "\n")
    return validation


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"cannot write empty CSV {path.name}")
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def validate_program_directory(directory: str | Path) -> ProgramValidation:
    root = Path(directory)
    manifest = {}
    for line in (root / "manifest.txt").read_text().splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            manifest[key.strip()] = value.strip()
    if int(manifest.get("program_abi", -1)) != PROGRAM_ABI:
        raise ValueError("program ABI mismatch")
    if manifest.get("contains_evaluated_results") != "false":
        raise ValueError("program must explicitly exclude evaluated results")
    elements = list(csv.DictReader((root / "elements.csv").open()))
    rows = list(csv.DictReader((root / "rows.csv").open()))
    records = list(csv.DictReader((root / "records.csv").open()))
    reals = [line for line in (root / "reals.txt").read_text().splitlines() if line.strip()]
    ints = [line for line in (root / "ints.txt").read_text().splitlines() if line.strip()]
    opcodes = tuple(sorted({_as_int(record["opcode"], "opcode") for record in records}))
    bad = set(opcodes) - SUPPORTED_OPCODES
    if bad:
        raise ValueError(f"unsupported opcodes: {sorted(bad)}")
    return ProgramValidation(
        program_id=manifest["program_id"], elements=len(elements), rows=len(rows),
        records=len(records), real_values=len(reals), integer_values=len(ints), opcodes=opcodes,
    )


def inspect_atdb_coverage(atdb_path: str | Path, element_z: Iterable[int]) -> dict[str, Any]:
    """Scan active ATDB record headers and report native opcode coverage.

    This does not lower topology yet. It is intended to run on the qualification
    host to identify the exact remaining UCalc families before promotion.
    """
    from .atomic_database import load_atomic_database_state
    from .active_subsets import build_active_atdb_subset
    import numpy as np

    built = load_atomic_database_state(atdb_path, validate=True)
    try:
        subset = build_active_atdb_subset(built.master, built.derived, tuple(int(z) for z in element_z))
        npfi = np.asarray(built.derived.npfi, dtype=np.int64)
        npnxt = np.asarray(built.derived.npnxt, dtype=np.int64).reshape(-1)
        counts: dict[int, int] = {}
        seen: set[int] = set()
        for ion_index in np.asarray(subset.ion_indices, dtype=np.int64).tolist():
            if ion_index <= 0 or ion_index >= npfi.shape[1]:
                continue
            for rate_type in range(1, npfi.shape[0]):
                rec = int(npfi[rate_type, ion_index])
                guard = 0
                while 0 < rec < npnxt.size and rec not in seen:
                    seen.add(rec)
                    header = built.master.header(rec)
                    counts[int(header.data_type)] = counts.get(int(header.data_type), 0) + 1
                    rec = int(npnxt[rec])
                    guard += 1
                    if guard > npnxt.size:
                        raise RuntimeError("ATDB linked-record cycle")
        supported = {dt: count for dt, count in counts.items() if dt in SUPPORTED_OPCODES or dt in {2, 3, 7, 8, 20}}
        unsupported = {dt: count for dt, count in counts.items() if dt not in supported}
        return {
            "schema_version": "0.6.48.2",
            "active_element_z": list(element_z),
            "records_scanned": sum(counts.values()),
            "data_type_counts": dict(sorted(counts.items())),
            "native_supported_counts": dict(sorted(supported.items())),
            "unsupported_counts": dict(sorted(unsupported.items())),
            "production_promotion_ready": not unsupported,
        }
    finally:
        built.master.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    compile_p = sub.add_parser("compile", help="compile a raw JSON program specification")
    compile_p.add_argument("spec")
    compile_p.add_argument("output_dir")
    validate_p = sub.add_parser("validate", help="validate a raw native program directory")
    validate_p.add_argument("program_dir")
    coverage_p = sub.add_parser("coverage", help="scan active ATDB UCalc data-type coverage")
    coverage_p.add_argument("atdb")
    coverage_p.add_argument("--elements", default="1,2,12")
    coverage_p.add_argument("--output")
    args = parser.parse_args(argv)
    if args.command == "compile":
        result = compile_program_spec(args.spec, args.output_dir)
        print(json.dumps(result.__dict__, indent=2, default=list, sort_keys=True))
    elif args.command == "validate":
        result = validate_program_directory(args.program_dir)
        print(json.dumps(result.__dict__, indent=2, default=list, sort_keys=True))
    else:
        elements = tuple(int(part.strip()) for part in args.elements.split(",") if part.strip())
        result = inspect_atdb_coverage(args.atdb, elements)
        text = json.dumps(result, indent=2, sort_keys=True) + "\n"
        if args.output:
            Path(args.output).write_text(text)
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
