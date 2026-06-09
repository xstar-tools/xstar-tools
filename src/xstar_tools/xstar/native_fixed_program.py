"""Active-ATDB compiler for the genuine v0.6.48.3.1 native fixed-state engine.

The compiler lowers source ATDB topology plus raw formula coefficients.  It
never stores evaluated rates, populations, terminal states, trajectories, or
science products, so the resulting program cannot act as a replay cache.

v0.6.48.3.1 distinguishes three classes that older coverage reports conflated:

* topology metadata (rate type 13; usually data type 6 or 83),
* executable families accepted by the active lowerer,
* executable families that remain unsupported and therefore block promotion.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

PROGRAM_ABI = 60483
SIMPLE_DATA_TYPES = {1, 2, 3, 7, 8, 20}
ENGINE_RECOGNIZED_OPCODES = {1, 49, 50, 51, 53, 56, 63, 69, 74, 88, 99}
# Families whose raw ATDB representation is lowered by this release.  The
# engine still recognizes 63/99 for synthetic/development programs, but the
# active lowerer refuses them until their exact host payload transforms are
# qualified.
ACTIVE_LOWERER_DATA_TYPES = {49, 50, 51, 53, 56, 69, 74, 88}
TOPOLOGY_RATE_TYPES = {11, 12, 13}
FORBIDDEN_KEYS = {
    "ans1", "ans2", "ans3", "ans4", "ans5", "ans6",
    "final_population", "final_populations", "terminal_state",
    "hmctot", "elcter", "science_file", "science_files",
    "trajectory", "reference_output", "reference_outputs",
}
ATOMIC_MASS_AMU = {1: 1.00794, 2: 4.002602, 12: 24.305}


@dataclass(frozen=True)
class ProgramValidation:
    program_id: str
    elements: int
    rows: int
    records: int
    real_values: int
    integer_values: int
    opcodes: tuple[int, ...]


@dataclass(frozen=True)
class ActiveLoweringResult:
    output_dir: str
    program_id: str
    active_element_z: tuple[int, ...]
    elements: int
    compact_rows: int
    topology_records: int
    executable_records: int
    unsupported_records: int
    native_data_types: tuple[int, ...]
    unsupported_data_types: tuple[int, ...]
    production_promotion_ready: bool
    atdb_fingerprint_sha256: str


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


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"cannot write empty CSV {path.name}")
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def compile_program_spec(spec_path: str | Path, output_dir: str | Path) -> ProgramValidation:
    """Compile a small JSON development fixture into the raw program format."""
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
        element_records = [i for i, record in enumerate(records) if _as_int(record.get("element_index", -1), "element_index") == element_index]
        if not element_records:
            raise ValueError(f"element {element_index} has no records")
        if element_records != list(range(element_records[0], element_records[0] + len(element_records))):
            raise ValueError("records for each element must be contiguous in source order")
        element_table.append({
            "element_index": element_index,
            "element_z": _as_int(element["element_z"], "element_z"),
            "n_rows": len(rows),
            "n_superlevels": _as_int(element.get("n_superlevels", len(rows)), "n_superlevels"),
            "n_ions": _as_int(element["n_ions"], "n_ions"),
            "normalization_row": _as_int(element.get("normalization_row", len(rows)), "normalization_row"),
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
        if opcode not in ENGINE_RECOGNIZED_OPCODES:
            raise ValueError(f"unsupported native opcode {opcode} at record {index}")
        opcodes.add(opcode)
        element_index = _as_int(record["element_index"], "element_index")
        payload_reals = [_as_float(v, "real payload") for v in record.get("reals", [])]
        payload_ints = [_as_int(v, "integer payload") for v in record.get("ints", [])]
        real_offset, int_offset = len(reals), len(ints)
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
        f"program_abi={PROGRAM_ABI}\nprogram_id={program_id}\n"
        "program_kind=raw_atomic_coefficients\ncontains_evaluated_results=false\n"
        "active_atdb_lowered=false\n"
        f"element_count={len(element_table)}\nrecord_count={len(record_table)}\n"
    )
    _write_csv(out / "elements.csv", element_table)
    _write_csv(out / "rows.csv", element_rows)
    _write_csv(out / "records.csv", record_table)
    (out / "reals.txt").write_text("".join(f"{value:.17g}\n" for value in reals))
    (out / "ints.txt").write_text("".join(f"{value}\n" for value in ints))
    validation = validate_program_directory(out)
    (out / "coverage.json").write_text(json.dumps({
        "schema_version": "0.6.48.3.1",
        "program_id": validation.program_id,
        "native_opcodes": list(validation.opcodes),
        "unsupported_opcodes": [],
        "contains_evaluated_results": False,
        "active_atdb_lowered": False,
        "production_promotion_ready": False,
        "reason": "development fixture, not a host ATDB lowering",
    }, indent=2, sort_keys=True) + "\n")
    return validation


def _manifest(directory: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in (directory / "manifest.txt").read_text().splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            result[key.strip()] = value.strip()
    return result


def validate_program_directory(directory: str | Path) -> ProgramValidation:
    root = Path(directory)
    manifest = _manifest(root)
    if int(manifest.get("program_abi", -1)) != PROGRAM_ABI:
        raise ValueError("program ABI mismatch")
    if manifest.get("contains_evaluated_results") != "false":
        raise ValueError("program must explicitly exclude evaluated results")
    elements = sum(1 for _ in csv.DictReader((root / "elements.csv").open()))
    rows = sum(1 for _ in csv.DictReader((root / "rows.csv").open()))
    record_count = 0
    opcodes: set[int] = set()
    with (root / "records.csv").open() as handle:
        for record in csv.DictReader(handle):
            record_count += 1
            opcodes.add(_as_int(record["opcode"], "opcode"))
    bad = opcodes - ENGINE_RECOGNIZED_OPCODES
    if bad:
        raise ValueError(f"unsupported opcodes: {sorted(bad)}")
    real_values = sum(1 for line in (root / "reals.txt").open() if line.strip())
    integer_values = sum(1 for line in (root / "ints.txt").open() if line.strip())
    return ProgramValidation(
        program_id=manifest["program_id"], elements=elements, rows=rows,
        records=record_count, real_values=real_values, integer_values=integer_values,
        opcodes=tuple(sorted(opcodes)),
    )


def _classify_record(rate_type: int, data_type: int) -> str:
    if rate_type in TOPOLOGY_RATE_TYPES:
        return "topology_metadata"
    if data_type in ACTIVE_LOWERER_DATA_TYPES:
        return "native_executable"
    if data_type in ENGINE_RECOGNIZED_OPCODES or data_type in SIMPLE_DATA_TYPES:
        return "recognized_but_not_active_lowered"
    return "unsupported_physics"


def _coverage_from_counts(counts: Mapping[tuple[int, int], int], active_elements: Sequence[int]) -> dict[str, Any]:
    data_type_counts: dict[int, int] = {}
    category_counts: dict[str, int] = {}
    native: dict[int, int] = {}
    metadata: dict[int, int] = {}
    recognized: dict[int, int] = {}
    unsupported: dict[int, int] = {}
    for (rate_type, data_type), count in counts.items():
        data_type_counts[data_type] = data_type_counts.get(data_type, 0) + count
        category = _classify_record(rate_type, data_type)
        category_counts[category] = category_counts.get(category, 0) + count
        target = {
            "native_executable": native,
            "topology_metadata": metadata,
            "recognized_but_not_active_lowered": recognized,
            "unsupported_physics": unsupported,
        }[category]
        target[data_type] = target.get(data_type, 0) + count
    total = sum(data_type_counts.values())
    covered = category_counts.get("native_executable", 0) + category_counts.get("topology_metadata", 0)
    return {
        "schema_version": "0.6.48.3.1",
        "active_element_z": list(active_elements),
        "records_scanned": total,
        "data_type_counts": dict(sorted(data_type_counts.items())),
        "topology_metadata_counts": dict(sorted(metadata.items())),
        "active_lowerer_native_counts": dict(sorted(native.items())),
        "recognized_but_not_active_lowered_counts": dict(sorted(recognized.items())),
        "unsupported_physics_counts": dict(sorted(unsupported.items())),
        "category_counts": dict(sorted(category_counts.items())),
        "nominal_record_coverage_fraction": (covered / total if total else 0.0),
        "nominal_record_coverage_percent": (100.0 * covered / total if total else 0.0),
        "production_promotion_ready": not recognized and not unsupported,
    }


def _scan_active_records(master: Any, derived: Any, subset: Any) -> tuple[dict[tuple[int, int], int], dict[int, list[int]], list[dict[str, int]]]:
    import numpy as np

    npfi = np.asarray(derived.npfi, dtype=np.int64)
    npnxt = np.asarray(derived.npnxt, dtype=np.int64).reshape(-1)
    counts: dict[tuple[int, int], int] = {}
    executable_by_z: dict[int, list[int]] = {int(z): [] for z in subset.active_element_z}
    unsupported_rows: list[dict[str, int]] = []
    seen: set[int] = set()
    for ion_index in np.asarray(subset.ion_indices, dtype=np.int64).tolist():
        if ion_index <= 0 or ion_index >= npfi.shape[1]:
            continue
        z = int(derived.ion_element_z[ion_index])
        stage = int(derived.ion_stage[ion_index])
        for rate_type in range(1, npfi.shape[0]):
            rec = int(npfi[rate_type, ion_index])
            guard = 0
            while 0 < rec < npnxt.size:
                if rec in seen:
                    break
                seen.add(rec)
                header = master.header(rec)
                key = (int(header.rate_type), int(header.data_type))
                counts[key] = counts.get(key, 0) + 1
                category = _classify_record(*key)
                if category == "native_executable":
                    executable_by_z.setdefault(z, []).append(rec)
                elif category not in {"topology_metadata"}:
                    unsupported_rows.append({
                        "record": rec, "element_z": z, "ion_index": int(ion_index),
                        "ion_stage": stage, "rate_type": int(header.rate_type),
                        "data_type": int(header.data_type),
                        "category": category,
                    })
                rec = int(npnxt[rec])
                guard += 1
                if guard > npnxt.size:
                    raise RuntimeError("ATDB linked-record cycle")
    for records in executable_by_z.values():
        records.sort()
    return counts, executable_by_z, unsupported_rows


def inspect_atdb_coverage(atdb_path: str | Path, element_z: Iterable[int]) -> dict[str, Any]:
    from .atomic_database import load_atomic_database_state
    from .active_subsets import build_active_atdb_subset

    elements = tuple(sorted({int(z) for z in element_z if int(z) > 0}))
    built = load_atomic_database_state(atdb_path, validate=True)
    try:
        subset = build_active_atdb_subset(built.master, built.derived, elements)
        counts, _, _ = _scan_active_records(built.master, built.derived, subset)
        return _coverage_from_counts(counts, elements)
    finally:
        built.master.close()


def _atdb_fingerprint(master: Any, active_elements: Sequence[int]) -> tuple[str, dict[str, Any]]:
    stat = Path(master.path).stat()
    payload = {
        "path_name": Path(master.path).name,
        "file_size": int(stat.st_size),
        "file_mtime_ns": int(stat.st_mtime_ns),
        "creation_date": str(master.creation_date),
        "creator": str(master.creator),
        "n_records": int(master.np2),
        "n_reals": int(master.np1r),
        "n_integers": int(master.np1i),
        "n_chars": int(master.np1k),
        "active_element_z": list(active_elements),
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return digest, payload


def _level_payload(master: Any, derived: Any, ion_index: int, local_level: int) -> tuple[int, float, float, str]:
    import numpy as np

    npilev = np.asarray(derived.npilev, dtype=np.int64)
    if local_level <= 0 or local_level >= npilev.shape[0] or ion_index <= 0 or ion_index >= npilev.shape[1]:
        raise ValueError(f"level lookup outside npilev: ion={ion_index} local={local_level}")
    global_index = int(npilev[local_level, ion_index])
    if global_index <= 0 or global_index >= len(derived.level_record_by_global_index):
        raise ValueError(f"missing global level for ion={ion_index} local={local_level}")
    rec = int(derived.level_record_by_global_index[global_index])
    reals = list(master.record_reals(rec))
    energy = float(reals[0]) if reals else 0.0
    weight = float(reals[1]) if len(reals) > 1 and float(reals[1]) > 0.0 else 1.0
    label = master.record_chars(rec).decode("latin-1", errors="replace").strip(" \x00")
    return rec, energy, weight, label


def _build_element_layout(master: Any, derived: Any, element_z: int, element_index: int) -> tuple[dict[str, Any], list[dict[str, Any]], Any, dict[int, Any]]:
    from .element_equilibrium import build_element_compact_basis

    ions = [
        (int(i), int(derived.ion_stage[i]))
        for i in range(1, int(derived.n_ions) + 1)
        if int(derived.ion_element_z[i]) == int(element_z)
    ]
    if not ions:
        raise ValueError(f"no active ion topology for Z={element_z}")
    basis = build_element_compact_basis(
        master, derived, element_z=int(element_z),
        min_ion_stage=min(stage for _, stage in ions),
        max_ion_stage=max(stage for _, stage in ions),
    )
    blocks = {int(block.ion_index): block for block in basis.blocks}
    rows: list[dict[str, Any]] = []
    for row in basis.rows:
        if not row.roles:
            raise ValueError(f"compact row {row.compact_index} has no source role")
        role = row.roles[-1]
        ion_index = int(role["ion_index"])
        local_level = int(role["local_level"])
        _, energy, weight, _ = _level_payload(master, derived, ion_index, local_level)
        stage = int(derived.ion_stage[ion_index])
        rows.append({
            "element_index": element_index,
            "row": int(row.compact_index),
            "superlevel": int(row.superlevel),
            "ion": int(row.ion_counter),
            "ion_charge": max(0, stage - 1),
            "initial_population": 1.0 if int(row.compact_index) == 1 else 0.0,
            "energy_ev": energy,
            "statistical_weight": weight,
        })
    element = {
        "element_index": element_index,
        "element_z": int(element_z),
        "n_rows": int(basis.n_rows),
        "n_superlevels": int(basis.n_superlevels),
        "n_ions": int(basis.n_ions),
        "normalization_row": int(basis.normalization_row),
        "record_head": 0,
        "record_count": 0,
    }
    return element, rows, basis, blocks


def _compact_row_for_local(basis: Any, ion_index: int, local_level: int) -> int:
    key = (int(ion_index), int(local_level))
    if key not in basis.role_to_row:
        raise ValueError(f"ATDB endpoint has no compact row: ion={ion_index} local={local_level}")
    return int(basis.role_to_row[key])


def _compact_row_for_idest(basis: Any, block: Any, idest: int) -> int:
    row = int(block.compact_start) + int(idest) - 1
    if row < 1 or row > int(basis.n_rows):
        raise ValueError(f"destination {idest} outside compact element basis")
    return row


def _row_energy(rows: Sequence[Mapping[str, Any]], one_based: int) -> float:
    return float(rows[int(one_based) - 1]["energy_ev"])


def _row_weight(rows: Sequence[Mapping[str, Any]], one_based: int) -> float:
    return max(float(rows[int(one_based) - 1]["statistical_weight"]), 1.0e-300)


def _lower_record(master: Any, derived: Any, rec: int, element_index: int, rows: Sequence[Mapping[str, Any]], basis: Any, blocks: Mapping[int, Any], subset: Any) -> dict[str, Any]:
    import numpy as np

    header = master.header(rec)
    dt, rt = int(header.data_type), int(header.rate_type)
    if dt not in ACTIVE_LOWERER_DATA_TYPES:
        raise ValueError(f"data type {dt} is not active-lowerer supported")
    raw_reals = [float(v) for v in np.asarray(master.record_reals(rec), dtype=np.float64).reshape(-1)]
    raw_ints = [int(v) for v in np.asarray(master.record_integers(rec), dtype=np.int64).reshape(-1)]
    ion_rec = int(derived.npar[rec]) if 0 < rec < len(derived.npar) else 0
    ion_index = int(subset.ion_record_to_index.get(ion_rec, 0))
    if ion_index <= 0 or ion_index not in blocks:
        raise ValueError(f"record {rec} has no active parent ion")
    block = blocks[ion_index]
    stage = int(derived.ion_stage[ion_index])

    def local_pair(a: int, b: int) -> tuple[int, int]:
        ra = _compact_row_for_local(basis, ion_index, a)
        rb = _compact_row_for_local(basis, ion_index, b)
        return (ra, rb) if _row_energy(rows, ra) <= _row_energy(rows, rb) else (rb, ra)

    payload_reals = list(raw_reals)
    payload_ints = list(raw_ints)
    lower_row = upper_row = 0
    line_energy = 0.0
    mass = ATOMIC_MASS_AMU.get(int(derived.ion_element_z[ion_index]), float(max(1, int(derived.ion_element_z[ion_index]) * 2)))

    if dt == 50:
        if len(raw_ints) < 2 or len(raw_reals) < 3:
            raise ValueError(f"type50 record {rec} has short payload")
        lower_row, upper_row = local_pair(int(raw_ints[0]), int(raw_ints[1]))
        wavelength = abs(raw_reals[0])
        aij = raw_reals[2]
        gup, glo = _row_weight(rows, upper_row), _row_weight(rows, lower_row)
        oscillator = 0.0 if wavelength <= 0.0 else 1.0e-16 * aij * gup * wavelength * wavelength / (0.667274 * glo)
        payload_reals = [aij, oscillator]
        payload_ints = []
        line_energy = abs(_row_energy(rows, upper_row) - _row_energy(rows, lower_row))
    elif dt in {51, 56, 69}:
        if len(raw_ints) < 2:
            raise ValueError(f"type{dt} record {rec} has short integer payload")
        if dt == 51:
            if len(raw_ints) < 3:
                raise ValueError(f"type51 record {rec} has short integer payload")
            a, b = int(raw_ints[2]), int(raw_ints[1])
            payload_ints = [int(raw_ints[0])]
        else:
            a, b = int(raw_ints[0]), int(raw_ints[1])
            payload_ints = []
        lower_row, upper_row = local_pair(a, b)
        line_energy = abs(_row_energy(rows, upper_row) - _row_energy(rows, lower_row))
    elif dt in {49, 53}:
        if len(raw_ints) < 4 or len(raw_reals) < 4:
            raise ValueError(f"type{dt} record {rec} has short payload")
        id1 = int(raw_ints[-2])
        off = max(0, int(raw_ints[-4]))
        id2 = int(block.nlev) + off - 1
        lower_row = _compact_row_for_local(basis, ion_index, id1)
        upper_row = _compact_row_for_idest(basis, block, id2)
        payload_reals = [value * 1.0e-18 if i % 2 else value for i, value in enumerate(raw_reals)]
        payload_ints = []
        line_energy = abs(_row_energy(rows, upper_row) - _row_energy(rows, lower_row))
    elif dt == 74:
        if len(raw_ints) < 2:
            raise ValueError(f"type74 record {rec} has short integer payload")
        lower_row = _compact_row_for_local(basis, ion_index, int(raw_ints[-2]))
        upper_row = _compact_row_for_local(basis, ion_index, int(block.nlev))
        payload_ints = []
        line_energy = abs(_row_energy(rows, upper_row) - _row_energy(rows, lower_row))
    elif dt == 88:
        if len(raw_ints) < 2 or len(raw_reals) < 4:
            raise ValueError(f"type88 record {rec} has short payload")
        lower_row = _compact_row_for_local(basis, ion_index, int(raw_ints[-2]))
        upper_row = _compact_row_for_local(basis, ion_index, int(block.nlev))
        payload_reals = [value * 1.0e-18 if i % 2 else value for i, value in enumerate(raw_reals)]
        payload_ints = []
        line_energy = abs(_row_energy(rows, upper_row) - _row_energy(rows, lower_row))
    else:  # pragma: no cover - guarded above
        raise ValueError(f"unhandled active-lowerer type {dt}")

    return {
        "source_position": int(header.raw_pointer),
        "record": int(rec),
        "element_index": int(element_index),
        "opcode": int(dt),
        "data_type": int(dt),
        "rate_type": int(rt),
        "ion_index": int(block.ion_counter),
        "ion_stage": int(stage),
        "lower_row": int(lower_row),
        "upper_row": int(upper_row),
        "density_scale": 1.0,
        "line_energy_ev": float(line_energy),
        "atomic_mass_amu": float(mass),
        "reals": payload_reals,
        "ints": payload_ints,
    }


def lower_active_atdb(
    atdb_path: str | Path,
    output_dir: str | Path,
    *,
    element_z: Sequence[int] = (1, 2, 12),
    allow_partial: bool = False,
) -> ActiveLoweringResult:
    """Lower active H/He/Mg topology and supported raw records into a C++ program.

    Strict mode is the production-oriented default and refuses to create a
    runnable program while any active executable family is unsupported.
    ``allow_partial=True`` creates a development program plus an explicit
    unsupported-record ledger; its manifest remains promotion-blocked.
    """
    from .active_subsets import build_active_atdb_subset
    from .atomic_database import load_atomic_database_state

    active = tuple(sorted({int(z) for z in element_z if int(z) > 0}))
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    built = load_atomic_database_state(atdb_path, validate=True)
    try:
        subset = build_active_atdb_subset(built.master, built.derived, active)
        counts, records_by_z, unsupported_rows = _scan_active_records(built.master, built.derived, subset)
        coverage = _coverage_from_counts(counts, active)
        fingerprint, fingerprint_payload = _atdb_fingerprint(built.master, active)
        coverage["atdb_fingerprint"] = fingerprint_payload
        coverage["atdb_fingerprint_sha256"] = fingerprint
        (out / "coverage.json").write_text(json.dumps(coverage, indent=2, sort_keys=True) + "\n")
        if unsupported_rows:
            _write_csv(out / "unsupported_records.csv", unsupported_rows)
        else:
            (out / "unsupported_records.csv").write_text("record,element_z,ion_index,ion_stage,rate_type,data_type,category\n")
        if unsupported_rows and not allow_partial:
            by_type: dict[int, int] = {}
            for row in unsupported_rows:
                by_type[int(row["data_type"])] = by_type.get(int(row["data_type"]), 0) + 1
            raise RuntimeError(
                "active ATDB contains unsupported executable families; "
                f"rerun with --allow-partial for development: {dict(sorted(by_type.items()))}"
            )

        element_table: list[dict[str, Any]] = []
        row_table: list[dict[str, Any]] = []
        layouts: dict[int, tuple[Any, dict[int, Any], list[dict[str, Any]]]] = {}
        record_head = 0
        for element_index, z in enumerate(active):
            element, rows, basis, blocks = _build_element_layout(built.master, built.derived, z, element_index)
            count = len(records_by_z.get(z, []))
            if count <= 0:
                raise RuntimeError(f"no lowerable executable records for active Z={z}")
            element["record_head"] = record_head
            element["record_count"] = count
            record_head += count
            element_table.append(element)
            row_table.extend(rows)
            layouts[z] = (basis, blocks, rows)

        _write_csv(out / "elements.csv", element_table)
        _write_csv(out / "rows.csv", row_table)
        topology_rows = []
        for row in row_table:
            topology_rows.append({
                "element_index": row["element_index"], "compact_row": row["row"],
                "superlevel": row["superlevel"], "ion_counter": row["ion"],
                "ion_charge": row["ion_charge"], "energy_ev": row["energy_ev"],
                "statistical_weight": row["statistical_weight"],
            })
        _write_csv(out / "topology_rows.csv", topology_rows)

        record_fields = [
            "source_position", "record", "next_index", "element_index", "opcode", "data_type", "rate_type",
            "ion_index", "ion_stage", "lower_row", "upper_row", "real_offset", "real_count", "int_offset",
            "int_count", "density_scale", "line_energy_ev", "atomic_mass_amu",
        ]
        real_offset = int_offset = global_index = 0
        native_types: set[int] = set()
        with (out / "records.csv").open("w", newline="") as records_handle, (out / "reals.txt").open("w") as reals_handle, (out / "ints.txt").open("w") as ints_handle:
            writer = csv.DictWriter(records_handle, fieldnames=record_fields, lineterminator="\n")
            writer.writeheader()
            for element_index, z in enumerate(active):
                basis, blocks, rows = layouts[z]
                source_records = records_by_z[z]
                for local_index, rec in enumerate(source_records):
                    lowered = _lower_record(built.master, built.derived, rec, element_index, rows, basis, blocks, subset)
                    payload_reals = lowered.pop("reals")
                    payload_ints = lowered.pop("ints")
                    native_types.add(int(lowered["data_type"]))
                    lowered["next_index"] = global_index + 1 if local_index + 1 < len(source_records) else -1
                    lowered["real_offset"] = real_offset
                    lowered["real_count"] = len(payload_reals)
                    lowered["int_offset"] = int_offset
                    lowered["int_count"] = len(payload_ints)
                    writer.writerow(lowered)
                    for value in payload_reals:
                        reals_handle.write(f"{float(value):.17g}\n")
                    for value in payload_ints:
                        ints_handle.write(f"{int(value)}\n")
                    real_offset += len(payload_reals)
                    int_offset += len(payload_ints)
                    global_index += 1

        program_id = f"v06483_active_atdb_{fingerprint[:16]}"
        promotion_ready = not unsupported_rows
        manifest_lines = [
            f"program_abi={PROGRAM_ABI}", f"program_id={program_id}",
            "program_kind=active_atdb_raw_coefficients", "contains_evaluated_results=false",
            "active_atdb_lowered=true", f"active_element_z={','.join(str(z) for z in active)}",
            f"atdb_fingerprint_sha256={fingerprint}", f"element_count={len(element_table)}",
            f"topology_record_count={coverage['category_counts'].get('topology_metadata', 0)}",
            f"compact_row_count={len(row_table)}", f"record_count={global_index}",
            f"unsupported_record_count={len(unsupported_rows)}",
            f"partial_lowering={'true' if unsupported_rows else 'false'}",
            f"production_promotion_ready={'true' if promotion_ready else 'false'}",
        ]
        (out / "manifest.txt").write_text("\n".join(manifest_lines) + "\n")
        validation = validate_program_directory(out)
        if validation.records != global_index:
            raise RuntimeError("lowered record count failed validation")
        summary = ActiveLoweringResult(
            output_dir=str(out), program_id=program_id, active_element_z=active,
            elements=len(element_table), compact_rows=len(row_table),
            topology_records=int(coverage["category_counts"].get("topology_metadata", 0)),
            executable_records=global_index, unsupported_records=len(unsupported_rows),
            native_data_types=tuple(sorted(native_types)),
            unsupported_data_types=tuple(sorted({int(row["data_type"]) for row in unsupported_rows})),
            production_promotion_ready=promotion_ready,
            atdb_fingerprint_sha256=fingerprint,
        )
        (out / "lowering_summary.json").write_text(json.dumps(summary.__dict__, indent=2, sort_keys=True, default=list) + "\n")
        return summary
    finally:
        built.master.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    compile_p = sub.add_parser("compile", help="compile a small raw JSON program specification")
    compile_p.add_argument("spec")
    compile_p.add_argument("output_dir")
    validate_p = sub.add_parser("validate", help="validate a raw native program directory")
    validate_p.add_argument("program_dir")
    coverage_p = sub.add_parser("coverage", help="scan active ATDB metadata and executable-family coverage")
    coverage_p.add_argument("atdb")
    coverage_p.add_argument("--elements", default="1,2,12")
    coverage_p.add_argument("--output")
    lower_p = sub.add_parser("lower-atdb", help="lower active ATDB topology and supported raw coefficients")
    lower_p.add_argument("atdb")
    lower_p.add_argument("output_dir")
    lower_p.add_argument("--elements", default="1,2,12")
    lower_p.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "compile":
        result: Any = compile_program_spec(args.spec, args.output_dir)
    elif args.command == "validate":
        result = validate_program_directory(args.program_dir)
    else:
        elements = tuple(int(part.strip()) for part in args.elements.split(",") if part.strip())
        if args.command == "coverage":
            result = inspect_atdb_coverage(args.atdb, elements)
            text = json.dumps(result, indent=2, sort_keys=True, default=list) + "\n"
            if args.output:
                Path(args.output).write_text(text)
            print(text, end="")
            return 0
        result = lower_active_atdb(args.atdb, args.output_dir, element_z=elements, allow_partial=bool(args.allow_partial))
    print(json.dumps(result.__dict__ if hasattr(result, "__dict__") else result, indent=2, default=list, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
