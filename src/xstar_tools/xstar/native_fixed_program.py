"""Active-ATDB compiler for the genuine v0.6.48.7.13 native fixed-state engine.

The compiler lowers source ATDB topology plus raw formula coefficients.  It
never stores evaluated rates, populations, terminal states, trajectories, or
science products, so the resulting program cannot act as a replay cache.

v0.6.48.7.13 distinguishes three classes that older coverage reports conflated:

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

PROGRAM_ABI = 60485
QUALIFIED_XDEF_ABUNDANCES_BY_Z: dict[int, float] = {1: 1.0, 2: 0.1, 12: 3.5e-5}
# v0.6.47.2 physical_runner.py constructs the reduced ucalc rate grid with
# ncn2m=999.  Type-49 phextrap uses that reduced-grid length as its capacity
# even though phint53 subsequently integrates on the full 9999-bin live grid.
TYPE49_PHEXTRAP_MAX_POINTS = 999


def _parse_abundance_spec(text: str) -> dict[int, float]:
    result: dict[int, float] = {}
    for item in str(text).split(","):
        item = item.strip()
        if not item:
            continue
        if ":" not in item:
            raise ValueError(f"invalid abundance entry {item!r}; expected Z:value")
        z_text, value_text = item.split(":", 1)
        z = _as_int(z_text.strip(), "abundance element Z")
        value = _as_float(value_text.strip(), f"abundance Z={z}")
        if z <= 0 or value < 0.0:
            raise ValueError("element abundances require positive Z and nonnegative values")
        result[z] = value
    if not result:
        raise ValueError("at least one element abundance is required")
    return result
SIMPLE_DATA_TYPES = {1, 2, 3, 7, 8, 20}
ENGINE_RECOGNIZED_OPCODES = {1, 2, 9, 30, 38, 39, 49, 50, 51, 53, 54, 56, 57, 60, 62, 63, 68, 69, 71, 72, 73, 74, 76, 77, 86, 88, 95, 99}
# v0.6.48.7.13 completes every executable data type reached by the qualified
# H/He/Mg parent-owned traversal.  Types 1/30/38/39 are executable scalar
# ion-rate families and are serialized with matrix_enabled=0 rather than being
# mislabeled as topology metadata.
ACTIVE_LOWERER_DATA_TYPES = {1, 2, 9, 30, 38, 39, 49, 50, 51, 53, 54, 56, 57, 60, 62, 63, 68, 69, 71, 72, 73, 74, 76, 77, 86, 88, 95, 99}
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
    active_record_completion_ready: bool
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
            "abundance": _as_float(element.get("abundance", 1.0), "abundance"),
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
                "principal_n": _as_int(row.get("principal_n", 0), "principal_n"),
                "orbital_l": _as_int(row.get("orbital_l", 0), "orbital_l"),
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
            "matrix_enabled": 1 if bool(record.get("matrix_enabled", True)) else 0,
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
        "schema_version": "0.6.48.7.13",
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
    element_rows = list(csv.DictReader((root / "elements.csv").open()))
    elements = len(element_rows)
    for element in element_rows:
        abundance = _as_float(element.get("abundance", 1.0), "abundance")
        if abundance < 0.0:
            raise ValueError("element abundance must be nonnegative")
    rows = sum(1 for _ in csv.DictReader((root / "rows.csv").open()))
    record_count = 0
    opcodes: set[int] = set()
    previous_source_position = 0
    with (root / "records.csv").open() as handle:
        for record in csv.DictReader(handle):
            source_position = _as_int(record["source_position"], "source_position")
            if source_position <= 0 or source_position <= previous_source_position:
                raise ValueError("source_position must be positive and strictly increasing")
            previous_source_position = source_position
            record_count += 1
            opcodes.add(_as_int(record["opcode"], "opcode"))
    if "record_count" in manifest and int(manifest["record_count"]) != record_count:
        raise ValueError("manifest record_count does not match records.csv")
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
        "schema_version": "0.6.48.7.13",
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
        "active_record_completion_ready": not recognized and not unsupported,
        "production_promotion_ready": False,
    }


def _scan_active_records(master: Any, derived: Any, subset: Any) -> tuple[dict[tuple[int, int], int], dict[int, list[int]], list[dict[str, int]]]:
    import numpy as np

    npfi = np.asarray(derived.npfi, dtype=np.int64)
    npnxt = np.asarray(derived.npnxt, dtype=np.int64).reshape(-1)
    npar = np.asarray(derived.npar, dtype=np.int64).reshape(-1)
    ion_records = np.asarray(derived.ion_records, dtype=np.int64).reshape(-1)
    counts: dict[tuple[int, int], int] = {}
    executable_by_z: dict[int, list[int]] = {int(z): [] for z in subset.active_element_z}
    unsupported_rows: list[dict[str, int]] = []
    seen: set[int] = set()
    for ion_index in np.asarray(subset.ion_indices, dtype=np.int64).tolist():
        if ion_index <= 0 or ion_index >= npfi.shape[1] or ion_index >= ion_records.size:
            continue
        ion_record = int(ion_records[ion_index])
        if ion_record <= 0:
            continue
        z = int(derived.ion_element_z[ion_index])
        stage = int(derived.ion_stage[ion_index])
        for rate_type in range(1, npfi.shape[0]):
            rec = int(npfi[rate_type, ion_index])
            guard = 0
            # ``npnxt`` is a global same-rate chain.  It continues from the
            # current ion into later ions, so source-faithful traversal must
            # stop when the parent record changes.  Without this ownership
            # gate, the first active element consumes all downstream records
            # and later elements appear to have no executable physics.
            while 0 < rec < npnxt.size and rec < npar.size and int(npar[rec]) == ion_record:
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
                nxt = int(npnxt[rec])
                if nxt == rec:
                    raise RuntimeError(f"ATDB linked-record self-cycle at record {rec}")
                rec = nxt
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


def _level_payload(master: Any, derived: Any, ion_index: int, local_level: int) -> tuple[int, float, float, str, int, int]:
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
    ints = list(master.record_integers(rec))
    principal_n = int(ints[0]) if len(ints) > 0 else 0
    orbital_l = int(ints[2]) if len(ints) > 2 else 0
    label = master.record_chars(rec).decode("latin-1", errors="replace").strip(" \x00")
    return rec, energy, weight, label, principal_n, orbital_l


def _level_ionization_potential(master: Any, derived: Any, ion_index: int, local_level: int) -> float:
    """Return the literal level-table rlev(4) ionization-potential field."""
    import numpy as np

    npilev = np.asarray(derived.npilev, dtype=np.int64)
    if local_level <= 0 or local_level >= npilev.shape[0] or ion_index <= 0 or ion_index >= npilev.shape[1]:
        raise ValueError(f"level lookup outside npilev: ion={ion_index} local={local_level}")
    global_index = int(npilev[local_level, ion_index])
    if global_index <= 0 or global_index >= len(derived.level_record_by_global_index):
        raise ValueError(f"missing global level for ion={ion_index} local={local_level}")
    rec = int(derived.level_record_by_global_index[global_index])
    reals = list(master.record_reals(rec))
    if len(reals) < 4:
        raise ValueError(f"level record {rec} lacks rlev(4) ionization potential")
    return float(reals[3])


def _build_element_layout(master: Any, derived: Any, element_z: int, element_index: int, global_level_index_by_key: Mapping[tuple[int, int, int], int] | None = None) -> tuple[dict[str, Any], list[dict[str, Any]], Any, dict[int, Any]]:
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
        _, energy, weight, _, principal_n, orbital_l = _level_payload(master, derived, ion_index, local_level)
        stage = int(derived.ion_stage[ion_index])
        global_level_index = int((global_level_index_by_key or {}).get((int(element_z), stage, local_level), 0))
        # v0.6.48.7.30.4: every compact He II row carries a source role whose
        # resolved global ordinal is one position above the source xilevg row.
        # Correct the already-resolved ordinal directly so the shared He I/He II
        # boundary row is included without requesting the invalid local level 0.
        # He I and all other elements retain their literal resolved ordinals.
        if int(element_z) == 2 and stage == 2 and global_level_index > 0:
            global_level_index -= 1
        rows.append({
            "element_index": element_index,
            "row": int(row.compact_index),
            "superlevel": int(row.superlevel),
            "ion": int(row.ion_counter),
            "ion_charge": max(0, stage - 1),
            "initial_population": 1.0 if int(row.compact_index) == 1 else 0.0,
            "energy_ev": energy,
            "statistical_weight": weight,
            "principal_n": principal_n,
            "orbital_l": orbital_l,
            "global_level_index": global_level_index,
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




def _source_type13_table(master: Any, derived: Any, ion_index: int) -> dict[int, dict[str, Any]]:
    """Return the literal source Type-13 table keyed by its local level index.

    ``calc_rates_level_lte`` does not resolve levels through ``npilev``.  It
    walks the Type-13 linked list and writes each record into the column named
    by the record's second-to-last integer.  Replaying that exact traversal is
    required for the Milne partition row and excited-parent lookup because the
    derived global-level map can select a different alias record.
    """
    import numpy as np

    npfi = np.asarray(getattr(derived, "npfi", ()), dtype=np.int64)
    npnxt = np.asarray(getattr(derived, "npnxt", ()), dtype=np.int64).reshape(-1)
    npar = np.asarray(getattr(derived, "npar", ()), dtype=np.int64).reshape(-1)
    if npfi.ndim != 2 or 13 >= npfi.shape[0] or ion_index <= 0 or ion_index >= npfi.shape[1]:
        raise ValueError(f"missing Type-13 pointer table for ion={ion_index}")
    rec = int(npfi[13, ion_index])
    if rec <= 0 or rec >= npar.size:
        raise ValueError(f"ion={ion_index} has no Type-13 level records")
    parent = int(npar[rec])
    table: dict[int, dict[str, Any]] = {}
    guard = 0
    while rec > 0 and rec < npar.size and int(npar[rec]) == parent:
        reals = [float(v) for v in master.record_reals(rec)]
        ints = [int(v) for v in master.record_integers(rec)]
        if len(ints) < 2:
            raise ValueError(f"Type-13 record {rec} lacks a local-level integer")
        local = int(ints[-2])
        if local <= 0:
            raise ValueError(f"Type-13 record {rec} has invalid local level {local}")
        if len(reals) < 2:
            raise ValueError(f"Type-13 record {rec} lacks energy/statistical weight")
        table[local] = {
            "record": rec,
            "energy_ev": float(reals[0]),
            "statistical_weight": float(reals[1]),
            "principal_n": int(ints[0]) if ints else 0,
            "ionization_potential_ev": float(reals[3]) if len(reals) >= 4 else 0.0,
        }
        nxt = int(npnxt[rec]) if rec < npnxt.size else 0
        if nxt == rec:
            raise ValueError(f"Type-13 self-loop at record {rec}")
        rec = nxt
        guard += 1
        if guard > 100000:
            raise RuntimeError(f"Type-13 linked-list guard exceeded for ion={ion_index}")
    if not table:
        raise ValueError(f"ion={ion_index} produced an empty Type-13 table")
    return table


def _build_source_leveltemp_value_snapshots(
    master: Any, derived: Any, basis: Any
) -> tuple[
    dict[int, dict[int, dict[str, Any]]],
    dict[int, dict[int, dict[str, Any]]],
    dict[int, dict[int, dict[str, Any]]],
]:
    """Replay the two literal source ``leveltemp`` overwrite passes.

    The first result is the mutable workspace snapshot visible to each ion,
    the second records column ownership, and the third is the literal Type-13
    table for every ion.  Only columns named by Type-13 records are overwritten;
    absent columns deliberately retain an earlier ion's value.
    """
    tables: dict[int, dict[int, dict[str, Any]]] = {}
    has_literal_links = hasattr(derived, "npfi") and hasattr(derived, "npnxt")
    for block in basis.blocks:
        ion_index = int(block.ion_index)
        if has_literal_links:
            tables[ion_index] = _source_type13_table(master, derived, ion_index)
            continue
        # Compatibility path for synthetic unit fixtures predating the
        # literal Type-13 linked-list contract.  Production lowering always
        # supplies npfi/npnxt and therefore never enters this branch.
        table: dict[int, dict[str, Any]] = {}
        for local in range(1, int(block.nlev) + 1):
            _record, energy, weight, _label, _n, _l = _level_payload(
                master, derived, ion_index, local
            )
            try:
                ionpot = float(_level_ionization_potential(master, derived, ion_index, local))
            except Exception:
                ionpot = 0.0
            table[local] = {
                "record": int(_record),
                "energy_ev": float(energy),
                "statistical_weight": float(weight),
                "principal_n": int(_n),
                "ionization_potential_ev": ionpot,
            }
        tables[ion_index] = table
    workspace: dict[int, dict[str, Any]] = {}
    owners: dict[int, dict[str, Any]] = {}

    def overwrite(block: Any, sequence: int, phase: str) -> None:
        ion_index = int(block.ion_index)
        stage = int(block.ion_stage)
        for local, value in tables[ion_index].items():
            workspace[int(local)] = dict(value)
            owners[int(local)] = {
                "ion_index": ion_index,
                "ion_stage": stage,
                "write_sequence": int(sequence),
                "phase": str(phase),
                "record": int(value["record"]),
            }

    for sequence, block in enumerate(basis.blocks, start=1):
        overwrite(block, sequence, "levwkelement")

    snapshots: dict[int, dict[int, dict[str, Any]]] = {}
    owner_snapshots: dict[int, dict[int, dict[str, Any]]] = {}
    for sequence, block in enumerate(basis.blocks, start=1):
        overwrite(block, sequence, "calc_hmc_ion")
        snapshots[int(block.ion_index)] = {
            column: dict(value) for column, value in workspace.items()
        }
        owner_snapshots[int(block.ion_index)] = {
            column: dict(owner) for column, owner in owners.items()
        }
    return snapshots, owner_snapshots, tables


def _build_source_leveltemp_energy_snapshots(
    master: Any, derived: Any, basis: Any
) -> tuple[dict[int, dict[int, float]], dict[int, dict[int, dict[str, Any]]]]:
    """Compatibility view containing only source ``leveltemp`` energies."""
    snapshots, owners, _tables = _build_source_leveltemp_value_snapshots(master, derived, basis)
    energy = {
        ion_index: {
            column: float(value["energy_ev"]) for column, value in workspace.items()
        }
        for ion_index, workspace in snapshots.items()
    }
    return energy, owners

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


def _row_n(rows: Sequence[Mapping[str, Any]], one_based: int) -> int:
    return int(rows[int(one_based) - 1].get("principal_n", 0))


def _row_l(rows: Sequence[Mapping[str, Any]], one_based: int) -> int:
    return int(rows[int(one_based) - 1].get("orbital_l", 0))


def _lower_record(
    master: Any, derived: Any, rec: int, element_index: int,
    rows: Sequence[Mapping[str, Any]], basis: Any, blocks: Mapping[int, Any],
    subset: Any,
    leveltemp_energy_snapshots: Mapping[int, Mapping[int, float]] | None = None,
    leveltemp_owner_snapshots: Mapping[int, Mapping[int, Mapping[str, Any]]] | None = None,
    leveltemp_value_snapshots: Mapping[int, Mapping[int, Mapping[str, Any]]] | None = None,
    source_type13_tables: Mapping[int, Mapping[int, Mapping[str, Any]]] | None = None,
) -> dict[str, Any]:
    import numpy as np

    literal_context_supplied = (
        leveltemp_value_snapshots is not None or source_type13_tables is not None
    )
    leveltemp_energy_snapshots = leveltemp_energy_snapshots or {}
    leveltemp_owner_snapshots = leveltemp_owner_snapshots or {}
    leveltemp_value_snapshots = leveltemp_value_snapshots or {
        int(ion): {
            int(column): {
                "record": 0,
                "energy_ev": float(energy),
                "statistical_weight": 1.0,
                "ionization_potential_ev": 0.0,
            }
            for column, energy in workspace.items()
        }
        for ion, workspace in leveltemp_energy_snapshots.items()
    }
    source_type13_tables = source_type13_tables or {}
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
    matrix_enabled = True
    mass = ATOMIC_MASS_AMU.get(int(derived.ion_element_z[ion_index]), float(max(1, int(derived.ion_element_z[ion_index]) * 2)))

    if dt == 1:
        if len(raw_reals) < 2:
            raise ValueError(f"type1 record {rec} has short payload")
        payload_reals = list(raw_reals[:2])
        payload_ints = []
        matrix_enabled = False
    elif dt == 2:
        if len(raw_reals) < 4:
            raise ValueError(f"type2 record {rec} has short payload")
        lower_row = _compact_row_for_local(basis, ion_index, 1)
        upper_row = _compact_row_for_local(basis, ion_index, int(block.nlev))
        payload_reals = list(raw_reals[:4])
        payload_ints = []
        line_energy = abs(_row_energy(rows, upper_row) - _row_energy(rows, lower_row))
    elif dt == 9:
        if len(raw_reals) < 4:
            raise ValueError(f"type9 record {rec} has short payload")
        if len(raw_ints) > 1:
            id1 = int(raw_ints[0])
            id2 = int(block.nlev) + int(raw_ints[1]) - 1
            lower_row = _compact_row_for_local(basis, ion_index, id1)
            upper_row = _compact_row_for_idest(basis, block, id2)
            payload_ints = [1]
        else:
            lower_row = _compact_row_for_local(basis, ion_index, 1)
            upper_row = _compact_row_for_local(basis, ion_index, int(block.nlev))
            payload_ints = [0]
        payload_reals = list(raw_reals[:4])
        line_energy = abs(_row_energy(rows, upper_row) - _row_energy(rows, lower_row))
    elif dt == 30:
        if not raw_ints:
            raise ValueError(f"type30 record {rec} has no nmax integer")
        payload_reals = []
        payload_ints = [int(raw_ints[0])]
        matrix_enabled = False
    elif dt in {38, 39}:
        if (dt == 38 and len(raw_reals) < 4) or (dt == 39 and len(raw_reals) < 2):
            raise ValueError(f"type{dt} record {rec} has short payload")
        payload_reals = list(raw_reals)
        payload_ints = []
        matrix_enabled = False
    elif dt == 50:
        if len(raw_ints) < 2 or len(raw_reals) < 3:
            raise ValueError(f"type50 record {rec} has short payload")
        # v0.6.48.7.46.21.5: matrix endpoint orientation must follow the
        # mutable source leveltemp workspace visible to the Type-50 evaluator,
        # not the immutable compact-row energies.  The v0.6.47.2 promoted
        # path returns the packed idest1/idest2 pair and then applies the
        # source _lower_upper comparison to the live level workspace.  A few
        # Mg columns retain earlier-ion values, so compact-energy sorting puts
        # an otherwise exact decay in the opposite matrix cells.
        idest1, idest2 = int(raw_ints[0]), int(raw_ints[1])
        row1 = _compact_row_for_local(basis, ion_index, idest1)
        row2 = _compact_row_for_local(basis, ion_index, idest2)
        current_snapshot = leveltemp_value_snapshots.get(ion_index, {})
        e1 = float(current_snapshot.get(idest1, {}).get("energy_ev", _row_energy(rows, row1)))
        e2 = float(current_snapshot.get(idest2, {}).get("energy_ev", _row_energy(rows, row2)))
        if (e1 / (1.0e-24 + e2) - 1.0) < 1.0e-8:
            lower_row, upper_row = row1, row2
        else:
            lower_row, upper_row = row2, row1

        # Keep the already-qualified Type-50 scalar arithmetic unchanged.
        # Its oscillator-strength weights remain the compact-row private
        # energy ordering used by v46.9.5; this release changes only matrix
        # endpoint placement.
        scalar_lower_row, scalar_upper_row = local_pair(idest1, idest2)
        wavelength = abs(raw_reals[0])
        aij = raw_reals[2]
        gup, glo = _row_weight(rows, scalar_upper_row), _row_weight(rows, scalar_lower_row)
        oscillator = 0.0 if wavelength <= 0.0 else 1.0e-16 * aij * gup * wavelength * wavelength / (0.667274 * glo)
        # v0.6.48.7.37: retain the literal stored wavelength in addition to
        # A and the source-derived oscillator strength.  Type-50 uses the
        # stored wavelength for flin/opakab and the endpoint energy difference
        # for the population/thermal energy channels.
        payload_reals = [aij, oscillator, wavelength]
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
    elif dt == 54:
        if len(raw_ints) < 4:
            raise ValueError(f"type54 record {rec} has short integer payload")
        a, b, iq = int(raw_ints[-4]), int(raw_ints[-3]), int(raw_ints[-2])
        lower_row, upper_row = local_pair(a, b)
        ni, nf = _row_n(rows, upper_row), _row_n(rows, lower_row)
        li, lf = _row_l(rows, upper_row), _row_l(rows, lower_row)
        if not all(v >= 0 for v in (ni, nf, li, lf)) or ni <= 0 or nf <= 0 or iq <= 0:
            raise ValueError(f"type54 record {rec} missing quantum numbers")
        if ni < nf:
            ni, nf = nf, ni
        payload_reals = []
        payload_ints = [ni, nf, li, lf, iq]
        line_energy = abs(_row_energy(rows, upper_row) - _row_energy(rows, lower_row))
    elif dt == 57:
        if len(raw_ints) < 2:
            raise ValueError(f"type57 record {rec} has short integer payload")
        i57 = int(raw_ints[0])
        local = int(raw_ints[-2])
        parent_local = int(block.nlev)
        lower_row = _compact_row_for_local(basis, ion_index, local)
        upper_row = _compact_row_for_local(basis, ion_index, parent_local)
        principal_n = _row_n(rows, lower_row) or i57

        # ucalc.f90 label 57 reads both energies from the literal source-local
        # Type-13 level table before compact-row aliasing:
        #   e1  = rlev(1,idest1)
        #   eth = max(0,rlev(1,nlevp)-e1)
        # Compact rows may intentionally share an endpoint and therefore cannot
        # carry this threshold.  Serialize e1 and eth explicitly into the native
        # program.  Production lowering always has the literal Type-13 table;
        # the row-based fallback keeps pre-contract synthetic fixtures readable.
        current_table = source_type13_tables.get(ion_index)
        if not current_table:
            if hasattr(derived, "npfi") and hasattr(derived, "npnxt"):
                current_table = _source_type13_table(master, derived, ion_index)
            else:
                current_table = {}
        source_level = current_table.get(local) if current_table else None
        source_parent = current_table.get(parent_local) if current_table else None
        if source_level and source_parent:
            source_e1_ev = float(source_level["energy_ev"])
            source_parent_ev = float(source_parent["energy_ev"])
            source_lower_weight = float(source_level["statistical_weight"])
            source_parent_weight = float(source_parent["statistical_weight"])
            principal_n = int(source_level.get("principal_n", 0)) or principal_n
        elif literal_context_supplied:
            raise ValueError(
                f"type57 record {rec} lacks literal Type-13 levels "
                f"idest1={local}, nlevp={parent_local}"
            )
        else:
            source_e1_ev = _row_energy(rows, lower_row)
            source_parent_ev = _row_energy(rows, upper_row)
            source_lower_weight = _row_weight(rows, lower_row)
            source_parent_weight = _row_weight(rows, upper_row)
        source_eth_ev = max(source_parent_ev - source_e1_ev, 0.0)
        payload_reals = [
            source_e1_ev, source_eth_ev, source_lower_weight, source_parent_weight,
        ]
        # Preserve the source-local level ordinal: ucalc Type-57 applies its
        # exact zero gate to idest1 before compact-row aliasing.
        payload_ints = [i57, principal_n, local]
        line_energy = source_eth_ev
    elif dt in {60, 62}:
        minimum_reals = 3 if dt == 60 else 6
        if len(raw_ints) < 2 or len(raw_reals) < minimum_reals:
            raise ValueError(f"type{dt} record {rec} has short payload")
        lower_row, upper_row = local_pair(int(raw_ints[0]), int(raw_ints[1]))
        payload_reals = list(raw_reals)
        payload_ints = []
        line_energy = abs(_row_energy(rows, upper_row) - _row_energy(rows, lower_row))
    elif dt == 68:
        if len(raw_ints) < 3 or len(raw_reals) < 3:
            raise ValueError(f"type68 record {rec} has short payload")
        lower_row, upper_row = local_pair(int(raw_ints[0]), int(raw_ints[1]))
        payload_reals = list(raw_reals[:3])
        payload_ints = [int(raw_ints[2])]
        line_energy = abs(_row_energy(rows, upper_row) - _row_energy(rows, lower_row))
    elif dt == 63:
        if len(raw_ints) < 4:
            raise ValueError(f"type63 record {rec} has short integer payload")
        # ucalc.f90 label 63 preserves literal initial/final scalar channels,
        # while msolvelucy orders the matrix endpoints by source level energy.
        # Retain both identities: the contribution lower/upper rows follow the
        # source energy comparison and the payload carries the literal initial
        # and final rows used by the type-63 scalar evaluator.
        a, b, iq = int(raw_ints[-4]), int(raw_ints[-3]), int(raw_ints[-2])
        initial_row = _compact_row_for_local(basis, ion_index, a)
        final_row = _compact_row_for_local(basis, ion_index, b)
        initial_energy = _row_energy(rows, initial_row)
        final_energy = _row_energy(rows, final_row)
        lower_row, upper_row = initial_row, final_row
        if (initial_energy / (1.0e-24 + final_energy) - 1.0) >= 1.0e-8:
            lower_row, upper_row = final_row, initial_row
        ni, li = _row_n(rows, initial_row), _row_l(rows, initial_row)
        nf, lf = _row_n(rows, final_row), _row_l(rows, final_row)
        if ni <= 0 or nf <= 0 or li < 0 or lf < 0 or iq <= 0:
            raise ValueError(f"type63 record {rec} missing quantum numbers")
        payload_reals = []
        payload_ints = [ni, li, nf, lf, iq, initial_row, final_row]
        line_energy = abs(initial_energy - final_energy)
    elif dt in {49, 53}:
        if len(raw_ints) < 4 or len(raw_reals) < 4:
            raise ValueError(f"type{dt} record {rec} has short payload")
        id1 = int(raw_ints[-2])
        off = max(0, int(raw_ints[-4]))
        id2 = int(block.nlev) + off - 1
        lower_row = _compact_row_for_local(basis, ion_index, id1)
        upper_row = _compact_row_for_idest(basis, block, id2)

        current_table = source_type13_tables.get(ion_index)
        if not current_table:
            if hasattr(derived, "npfi") and hasattr(derived, "npnxt"):
                current_table = _source_type13_table(master, derived, ion_index)
            else:
                current_table = {}
                for local in range(1, int(block.nlev) + 1):
                    level_record, energy, weight, _label, _n, _l = _level_payload(
                        master, derived, ion_index, local
                    )
                    current_table[local] = {
                        "record": int(level_record),
                        "energy_ev": float(energy),
                        "statistical_weight": float(weight),
                        "ionization_potential_ev": float(
                            _level_ionization_potential(master, derived, ion_index, local)
                        ),
                    }
        current_snapshot = leveltemp_value_snapshots.get(ion_index, {})
        bound_level = current_table.get(id1)
        partition_level = current_snapshot.get(int(block.nlev))
        if not partition_level and not literal_context_supplied:
            partition_level = current_table.get(int(block.nlev))
        destination_leveltemp = current_snapshot.get(id2, {
            "record": 0,
            "energy_ev": float(leveltemp_energy_snapshots.get(ion_index, {}).get(id2, 0.0)),
            "statistical_weight": 0.0,
            "ionization_potential_ev": 0.0,
        })
        if not bound_level:
            raise ValueError(f"type{dt} record {rec} lacks literal Type-13 bound level {id1}")
        if not partition_level:
            raise ValueError(
                f"type{dt} record {rec} lacks source leveltemp partition column {block.nlev}"
            )

        bound_energy = float(bound_level["energy_ev"])
        bound_weight = float(bound_level["statistical_weight"])
        base_threshold_ev = float(bound_level["ionization_potential_ev"]) - bound_energy
        partition_energy_ev = float(partition_level["energy_ev"])
        partition_weight = float(partition_level["statistical_weight"])
        if not (partition_weight > 0.0):
            raise ValueError(f"type{dt} record {rec} has invalid Milne partition weight {partition_weight}")

        excited_parent_energy_ev = 0.0
        excited_parent_weight = partition_weight
        destination_weight = partition_weight
        if id2 <= int(block.nlev):
            destination_level = current_table.get(id2)
            if not destination_level:
                raise ValueError(f"type{dt} record {rec} lacks destination Type-13 level {id2}")
            destination_weight = float(destination_level["statistical_weight"])
        else:
            ordered_blocks = list(basis.blocks)
            block_position = next(
                (idx for idx, candidate in enumerate(ordered_blocks) if int(candidate.ion_index) == ion_index),
                -1,
            )
            if block_position < 0 or block_position + 1 >= len(ordered_blocks):
                raise ValueError(f"type{dt} record {rec} has no next-ion parent destination")
            destination_block = ordered_blocks[block_position + 1]
            destination_local_level = id2 - int(block.nlev) + 1
            next_table = source_type13_tables.get(int(destination_block.ion_index))
            if not next_table:
                if hasattr(derived, "npfi") and hasattr(derived, "npnxt"):
                    next_table = _source_type13_table(
                        master, derived, int(destination_block.ion_index)
                    )
                else:
                    level_record, energy, weight, _label, _n, _l = _level_payload(
                        master, derived, int(destination_block.ion_index),
                        destination_local_level,
                    )
                    next_table = {
                        destination_local_level: {
                            "record": int(level_record),
                            "energy_ev": float(energy),
                            "statistical_weight": float(weight),
                            "ionization_potential_ev": 0.0,
                        }
                    }
            excited_parent = next_table.get(destination_local_level)
            if not excited_parent:
                raise ValueError(
                    f"type{dt} record {rec} has no literal next-ion Type-13 level "
                    f"{destination_local_level}"
                )
            excited_parent_energy_ev = float(excited_parent["energy_ev"])
            excited_parent_weight = float(excited_parent["statistical_weight"])
            destination_weight = excited_parent_weight

        corrected_threshold_ev = base_threshold_ev
        if dt == 53 and id2 > int(block.nlev):
            corrected_threshold_ev += excited_parent_energy_ev
        if dt == 53:
            corrected_threshold_ev = max(0.0, corrected_threshold_ev)

        pair_payload = [
            value * 1.0e-18 if i % 2 else value
            for i, value in enumerate(raw_reals)
        ]
        if literal_context_supplied:
            # Context v2 follows the literal ucalc state: base threshold,
            # corrected threshold, bound level, Milne partition leveltemp
            # column, bound/partition/destination weights, retained leveltemp
            # destination energy, and the matched excited-parent record.
            payload_reals = pair_payload + [
                float(base_threshold_ev),
                float(corrected_threshold_ev),
                float(bound_energy),
                float(partition_energy_ev),
                float(bound_weight),
                float(partition_weight),
                float(destination_weight),
                float(destination_leveltemp["energy_ev"]),
                float(excited_parent_energy_ev),
                float(excited_parent_weight),
            ]
        else:
            # Legacy v1 compatibility for direct synthetic _lower_record tests.
            # threshold_ev = float(bound_ionization_potential) - float(bound_energy)
            # leveltemp_energy_snapshots.get(ion_index, {}).get(id2, 0.0)
            # leveltemp_energy_snapshots.get(ion_index, {}).get(id2, 0.0)
            payload_reals = pair_payload + [
                float(base_threshold_ev),
                float(bound_energy),
                float(partition_energy_ev),
                float(bound_weight),
                float(partition_weight),
                float(destination_weight),
                float(leveltemp_energy_snapshots.get(ion_index, {}).get(id2, 0.0)),
            ]
        # Type-49 canonical continuum pointer: derived.npconi2[rec]
        # Type-53 canonical continuum pointer: derived.npconi2[rec]
        continuum_index = int(derived.npconi2[rec]) if rec < len(derived.npconi2) else 0
        if continuum_index <= 0:
            # Keep the two explicit contracts visible to readiness tests.
            if dt == 49:
                raise ValueError(f"type49 record {rec} has no canonical continuum index")
            raise ValueError(f"type53 record {rec} has no canonical continuum index")
        payload_ints = [continuum_index]
        if dt == 49:
            payload_ints.append(TYPE49_PHEXTRAP_MAX_POINTS)
        line_energy = float(corrected_threshold_ev)
    elif dt == 76:
        if len(raw_ints) < 2 or len(raw_reals) < 1:
            raise ValueError(f"type76 record {rec} has short payload")
        lower_row, upper_row = local_pair(int(raw_ints[0]), int(raw_ints[1]))
        payload_reals = [max(float(raw_reals[0]), 0.0)]
        payload_ints = []
        line_energy = abs(_row_energy(rows, upper_row) - _row_energy(rows, lower_row))
    elif dt in {71, 77}:
        if len(raw_ints) < 4:
            raise ValueError(f"type{dt} record {rec} has short integer payload")
        a, b = int(raw_ints[-4]), int(raw_ints[-3])
        lower_row = _compact_row_for_local(basis, ion_index, a)
        upper_row = _compact_row_for_local(basis, ion_index, b)
        payload_reals = list(raw_reals)
        payload_ints = list(raw_ints)
        line_energy = abs(_row_energy(rows, upper_row) - _row_energy(rows, lower_row))
    elif dt == 72:
        if len(raw_ints) < 4 or len(raw_reals) < 2:
            raise ValueError(f"type72 record {rec} has short payload")
        lower_row, upper_row = local_pair(int(raw_ints[-4]), int(raw_ints[-3]))
        payload_reals = list(raw_reals)
        ground_row = _compact_row_for_local(basis, ion_index, 1)
        parent_row = _compact_row_for_local(basis, ion_index, int(block.nlev))
        payload_ints = [ground_row, parent_row]
        line_energy = abs(_row_energy(rows, upper_row) - _row_energy(rows, lower_row))
    elif dt == 73:
        if len(raw_ints) < 3 or len(raw_reals) < 7:
            raise ValueError(f"type73 record {rec} has short payload")
        lower_row, upper_row = local_pair(int(raw_ints[0]), int(raw_ints[1]))
        payload_reals = list(raw_reals[:7])
        payload_ints = [int(raw_ints[2])]
        line_energy = abs(_row_energy(rows, upper_row) - _row_energy(rows, lower_row))
    elif dt == 74:
        if len(raw_ints) < 2:
            raise ValueError(f"type74 record {rec} has short integer payload")
        lower_row = _compact_row_for_local(basis, ion_index, int(raw_ints[-2]))
        upper_row = _compact_row_for_local(basis, ion_index, int(block.nlev))
        payload_ints = []
        line_energy = abs(_row_energy(rows, upper_row) - _row_energy(rows, lower_row))
    elif dt == 86:
        if len(raw_ints) < 5 or len(raw_reals) < 2:
            raise ValueError(f"type86 record {rec} has short payload")
        id1 = int(raw_ints[-4])
        id2 = int(block.nlev) + int(raw_ints[-5]) - 1
        lower_row = _compact_row_for_local(basis, ion_index, id1)
        upper_row = _compact_row_for_idest(basis, block, id2)
        payload_reals = [float(raw_reals[1])]
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
    elif dt == 95:
        if len(raw_reals) < 6 or len(raw_ints) < 2:
            raise ValueError(f"type95 record {rec} has short payload")
        if rt == 5:
            id1 = int(raw_ints[0])
            id2 = int(block.nlev) - 1 + int(raw_ints[1]) if len(raw_ints) >= 3 else int(block.nlev)
            lower_row = _compact_row_for_local(basis, ion_index, id1)
            upper_row = _compact_row_for_idest(basis, block, id2)
        else:
            lower_row = upper_row = _compact_row_for_local(basis, ion_index, 1)
        payload_reals = list(raw_reals)
        parent_row = _compact_row_for_local(basis, ion_index, int(block.nlev))
        payload_ints = list(raw_ints) + [parent_row]
        line_energy = abs(_row_energy(rows, upper_row) - _row_energy(rows, lower_row))
    elif dt == 99:
        if len(raw_ints) < 4 or len(raw_reals) < 8:
            raise ValueError(f"type99 record {rec} has short payload")
        id1 = min(int(raw_ints[-2]), max(int(block.nlev) - 1, 1))
        id2 = int(block.nlev) + int(raw_ints[-4]) - 1
        lower_row = _compact_row_for_local(basis, ion_index, id1)
        upper_row = _compact_row_for_idest(basis, block, id2)

        # v0.6.48.7.36: Type-99 must retain the mutable source leveltemp
        # destination workspace rather than re-reading the compact alias row.
        # At an ion boundary the next-ion ground overwrites the previous-ion
        # continuum in the compact matrix, but ucalc.f90 still uses the original
        # destination energy/statistical weight when deriving ett, swrat, and the
        # final heating corrections.  Append backward-compatible metadata after
        # the literal calt99 payload: destination energy, threshold, destination g.
        _, bound_energy, _bound_weight, _bound_label, _bound_n, _bound_l = _level_payload(
            master, derived, ion_index, id1
        )
        if id2 <= int(block.nlev):
            destination_ion_index = ion_index
            destination_local_level = id2
            _, destination_energy, destination_weight, _label, _n, _l = _level_payload(
                master, derived, destination_ion_index, destination_local_level
            )
            threshold_ev = abs(bound_energy - destination_energy)
        else:
            ordered_blocks = list(basis.blocks)
            block_position = next(
                (idx for idx, candidate in enumerate(ordered_blocks) if int(candidate.ion_index) == ion_index),
                -1,
            )
            if block_position < 0 or block_position + 1 >= len(ordered_blocks):
                raise ValueError(f"type99 record {rec} has no next-ion parent destination")
            destination_block = ordered_blocks[block_position + 1]
            destination_ion_index = int(destination_block.ion_index)
            destination_local_level = id2 - int(block.nlev) + 1
            _, parent_excitation, destination_weight, _label, _n, _l = _level_payload(
                master, derived, destination_ion_index, destination_local_level
            )
            _, continuum_energy, _continuum_weight, _clabel, _cn, _cl = _level_payload(
                master, derived, ion_index, int(block.nlev)
            )
            # Historical source-contract marker retained for older readiness tests:
            # float(continuum_weight)
            threshold_ev = abs(bound_energy + parent_excitation)
            destination_energy = continuum_energy + parent_excitation

        payload_reals = list(raw_reals) + [
            float(destination_energy),
            float(threshold_ev),
            float(destination_weight),
        ]
        payload_ints = list(raw_ints)
        line_energy = float(threshold_ev)
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
        "matrix_enabled": 1 if matrix_enabled else 0,
        "reals": payload_reals,
        "ints": payload_ints,
    }


def lower_active_atdb(
    atdb_path: str | Path,
    output_dir: str | Path,
    *,
    element_z: Sequence[int] = (1, 2, 12),
    abundances_by_z: Mapping[int, float] | None = None,
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
    abundances = dict(QUALIFIED_XDEF_ABUNDANCES_BY_Z if abundances_by_z is None else abundances_by_z)
    missing_abundances = [z for z in active if z not in abundances]
    if missing_abundances:
        raise ValueError(f"missing explicit elemental abundances for Z={missing_abundances}")
    for z in active:
        abundance = _as_float(abundances[z], f"abundance Z={z}")
        if abundance < 0.0:
            raise ValueError(f"element abundance must be nonnegative for Z={z}")
        abundances[z] = abundance
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
        layouts: dict[int, tuple[
            Any, dict[int, Any], list[dict[str, Any]],
            dict[int, dict[int, float]], dict[int, dict[int, dict[str, Any]]],
            dict[int, dict[int, dict[str, Any]]], dict[int, dict[int, dict[str, Any]]],
        ]] = {}
        record_head = 0
        for element_index, z in enumerate(active):
            element, rows, basis, blocks = _build_element_layout(
                built.master, built.derived, z, element_index, subset.global_level_index_by_key
            )
            count = len(records_by_z.get(z, []))
            if count <= 0:
                raise RuntimeError(f"no lowerable executable records for active Z={z}")
            element["abundance"] = abundances[z]
            element["record_head"] = record_head
            element["record_count"] = count
            record_head += count
            element_table.append(element)
            row_table.extend(rows)
            leveltemp_value_snapshots, leveltemp_owner_snapshots, source_type13_tables = (
                _build_source_leveltemp_value_snapshots(built.master, built.derived, basis)
            )
            leveltemp_snapshots = {
                ion: {column: float(value["energy_ev"]) for column, value in workspace.items()}
                for ion, workspace in leveltemp_value_snapshots.items()
            }
            layouts[z] = (
                basis, blocks, rows, leveltemp_snapshots, leveltemp_owner_snapshots,
                leveltemp_value_snapshots, source_type13_tables,
            )

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
            "int_count", "density_scale", "line_energy_ev", "atomic_mass_amu", "matrix_enabled",
        ]
        real_offset = int_offset = global_index = 0
        native_types: set[int] = set()
        with (out / "records.csv").open("w", newline="") as records_handle, (out / "reals.txt").open("w") as reals_handle, (out / "ints.txt").open("w") as ints_handle:
            writer = csv.DictWriter(records_handle, fieldnames=record_fields, lineterminator="\n")
            writer.writeheader()
            for element_index, z in enumerate(active):
                (
                    basis, blocks, rows, leveltemp_snapshots, leveltemp_owner_snapshots,
                    leveltemp_value_snapshots, source_type13_tables,
                ) = layouts[z]
                source_records = records_by_z[z]
                for local_index, rec in enumerate(source_records):
                    lowered = _lower_record(
                        built.master, built.derived, rec, element_index, rows, basis, blocks, subset,
                        leveltemp_snapshots, leveltemp_owner_snapshots,
                        leveltemp_value_snapshots, source_type13_tables,
                    )
                    payload_reals = lowered.pop("reals")
                    payload_ints = lowered.pop("ints")
                    native_types.add(int(lowered["data_type"]))
                    # Each contribution expands to up to four matrix terms.  The
                    # ATDB raw pointer is not a source-order position (it is zero
                    # for the qualified host database), so serialize a global,
                    # strictly increasing base position with four slots per record.
                    lowered["source_position"] = 4 * (global_index + 1)
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

        program_id = f"v06487_active_atdb_{fingerprint[:16]}"
        active_record_completion_ready = not unsupported_rows
        promotion_ready = False
        manifest_lines = [
            f"program_abi={PROGRAM_ABI}", f"program_id={program_id}",
            "program_kind=active_atdb_raw_coefficients", "contains_evaluated_results=false",
            "active_atdb_lowered=true", f"active_element_z={','.join(str(z) for z in active)}",
            "element_abundances=" + ",".join(f"{z}:{abundances[z]:.17g}" for z in active),
            "electron_accounting=abundance_weighted_with_fully_ionized_stage",
            f"atdb_fingerprint_sha256={fingerprint}", f"element_count={len(element_table)}",
            f"topology_record_count={coverage['category_counts'].get('topology_metadata', 0)}",
            f"compact_row_count={len(row_table)}", f"record_count={global_index}",
            f"unsupported_record_count={len(unsupported_rows)}",
            f"partial_lowering={'true' if unsupported_rows else 'false'}",
            f"active_record_completion_ready={'true' if active_record_completion_ready else 'false'}",
            "production_promotion_ready=false",
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
            active_record_completion_ready=active_record_completion_ready,
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
    lower_p.add_argument("--abundances", default="1:1.0,2:0.1,12:3.5e-5")
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
        result = lower_active_atdb(
            args.atdb, args.output_dir, element_z=elements,
            abundances_by_z=_parse_abundance_spec(args.abundances),
            allow_partial=bool(args.allow_partial),
        )
    print(json.dumps(result.__dict__ if hasattr(result, "__dict__") else result, indent=2, default=list, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
