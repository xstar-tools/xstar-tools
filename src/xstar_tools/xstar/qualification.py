"""Qualification infrastructure for the all-C++ XSTAR promotion program.

This module deliberately does not make a production claim.  It freezes and
verifies the v0.6.47.2 reference bundle, emits immutable source-order maps for
lowered native programs, and compares text, CSV, JSON, FITS, and binary
products under explicit comparison policies.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import struct
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

REFERENCE_SCHEMA = "xstar-tools-v06486-reference-v1"
MAP_SCHEMA = "xstar-tools-v06486-source-order-map-v1"
COMPARISON_SCHEMA = "xstar-tools-v06486-comparison-v1"
VOLATILE_FITS_KEYS = {"CHECKSUM", "DATASUM", "DATE", "DATE-OBS"}
SCIENCE_PRODUCT_FILES = {
    "xout_step.log", "xout_abund1.fits", "xout_cont1.fits", "xout_spect1.fits",
    "xout_lines1.fits", "xout_rrc1.fits", "xo01_detail.fits", "xo01_detal2.fits",
    "xo01_detal3.fits", "xo01_detal4.fits",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative_files(root: Path) -> list[Path]:
    return sorted(
        p.relative_to(root)
        for p in root.rglob("*")
        if p.is_file() and p.name not in {"reference_manifest.json", "SHA256SUMS"}
    )


def create_reference_manifest(
    root: Path,
    *,
    source_release: str = "0.6.47.2",
    source_archive_sha256: str = "",
) -> dict[str, Any]:
    files = []
    for relative in _relative_files(root):
        path = root / relative
        files.append(
            {
                "path": relative.as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return {
        "schema": REFERENCE_SCHEMA,
        "immutable": True,
        "source_release": source_release,
        "source_archive_sha256": source_archive_sha256,
        "reference_case": "helike_type69_mg11_ne1e8",
        "file_count": len(files),
        "files": files,
        "production_promotion_ready": False,
    }


def write_reference_manifest(root: Path, source_archive_sha256: str = "") -> dict[str, Any]:
    manifest = create_reference_manifest(root, source_archive_sha256=source_archive_sha256)
    (root / "reference_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    sums = "".join(f'{item["sha256"]}  {item["path"]}\n' for item in manifest["files"])
    (root / "SHA256SUMS").write_text(sums, encoding="utf-8")
    return manifest


def verify_reference_bundle(root: Path) -> dict[str, Any]:
    manifest_path = root / "reference_manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"missing reference manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    if manifest.get("schema") != REFERENCE_SCHEMA:
        errors.append(f"unexpected schema {manifest.get('schema')!r}")
    if manifest.get("immutable") is not True:
        errors.append("reference bundle is not marked immutable")
    expected_paths = {item["path"] for item in manifest.get("files", [])}
    actual_paths = {p.as_posix() for p in _relative_files(root)}
    missing = sorted(expected_paths - actual_paths)
    unexpected = sorted(actual_paths - expected_paths)
    if missing:
        errors.append("missing files: " + ", ".join(missing))
    if unexpected:
        errors.append("unexpected files: " + ", ".join(unexpected))
    verified = 0
    for item in manifest.get("files", []):
        path = root / item["path"]
        if not path.is_file():
            continue
        size = path.stat().st_size
        digest = sha256_file(path)
        if size != item["size_bytes"]:
            errors.append(f"size mismatch: {item['path']}")
        if digest != item["sha256"]:
            errors.append(f"hash mismatch: {item['path']}")
        if size == item["size_bytes"] and digest == item["sha256"]:
            verified += 1
    return {
        "schema": REFERENCE_SCHEMA,
        "bundle": str(root),
        "files_expected": len(manifest.get("files", [])),
        "files_verified": verified,
        "errors": errors,
        "result": "ACCEPT" if not errors else "REJECT",
        "production_promotion_ready": False,
    }


def _read_csv(path: Path) -> tuple[list[str], list[list[str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError(f"empty CSV: {path}") from exc
        return header, [row for row in reader]


def build_source_order_maps(program_dir: Path, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    element_header, element_rows = _read_csv(program_dir / "elements.csv")
    row_header, row_rows = _read_csv(program_dir / "rows.csv")
    record_header, record_rows = _read_csv(program_dir / "records.csv")

    def to_dicts(header: list[str], data: list[list[str]], name: str) -> list[dict[str, str]]:
        result: list[dict[str, str]] = []
        for index, row in enumerate(data, 2):
            if len(row) != len(header):
                raise ValueError(f"{name} row {index} has {len(row)} columns; expected {len(header)}")
            result.append(dict(zip(header, row)))
        return result

    elements = to_dicts(element_header, element_rows, "elements.csv")
    rows = to_dicts(row_header, row_rows, "rows.csv")
    records = to_dicts(record_header, record_rows, "records.csv")

    # Dense native order and strict source order are both part of the contract.
    source_positions = [int(record["source_position"]) for record in records]
    if source_positions != sorted(source_positions) or len(set(source_positions)) != len(source_positions):
        raise ValueError("records.csv source_position is not strictly increasing")
    element_indices = [int(element["element_index"]) for element in elements]
    if element_indices != list(range(len(elements))):
        raise ValueError("elements.csv element_index is not dense")

    traversal_ordinal: dict[int, int] = {}
    records_by_element: dict[int, list[int]] = {index: [] for index in element_indices}
    for native_index, record in enumerate(records):
        records_by_element[int(record["element_index"])].append(native_index)
    for element in elements:
        element_index = int(element["element_index"])
        current = int(element["record_head"])
        declared = int(float(element["record_count"]))
        seen: set[int] = set()
        ordinal = 0
        while current >= 0:
            if current in seen:
                raise ValueError(f"linked record cycle for element {element_index}")
            if current >= len(records):
                raise ValueError(f"linked record index outside records.csv for element {element_index}")
            seen.add(current)
            record = records[current]
            if int(record["element_index"]) != element_index:
                raise ValueError(f"linked traversal crosses element boundary for element {element_index}")
            traversal_ordinal[current] = ordinal
            ordinal += 1
            current = int(record["next_index"])
        if ordinal != declared:
            raise ValueError(
                f"linked record count {ordinal} differs from declared {declared} for element {element_index}"
            )

    element_map = output_dir / "elements_source_order.csv"
    with element_map.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = [
            "source_element_ordinal",
            "element_index",
            "element_z",
            "abundance",
            "n_rows",
            "n_superlevels",
            "n_ions",
            "normalization_row",
            "record_head",
            "record_count",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for ordinal, element in enumerate(elements, 1):
            writer.writerow(
                {
                    "source_element_ordinal": ordinal,
                    **{key: element.get(key, "") for key in fieldnames[1:]},
                }
            )

    row_map = output_dir / "rows_source_order.csv"
    global_row = 0
    with row_map.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = [
            "global_population_row",
            "element_index",
            "element_z",
            "element_row",
            "superlevel",
            "ion",
            "ion_charge",
            "initial_population",
            "energy_ev",
            "statistical_weight",
            "principal_n",
            "orbital_l",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        z_by_element = {int(e["element_index"]): e["element_z"] for e in elements}
        last_row_by_element: dict[int, int] = {}
        for row in rows:
            element_index = int(row["element_index"])
            element_row = int(row["row"])
            expected = last_row_by_element.get(element_index, 0) + 1
            if element_row != expected:
                raise ValueError(f"rows.csv is not dense for element {element_index}")
            last_row_by_element[element_index] = element_row
            global_row += 1
            writer.writerow(
                {
                    "global_population_row": global_row,
                    "element_index": element_index,
                    "element_z": z_by_element[element_index],
                    "element_row": element_row,
                    "superlevel": row["superlevel"],
                    "ion": row["ion"],
                    "ion_charge": row["ion_charge"],
                    "initial_population": row["initial_population"],
                    "energy_ev": row["energy_ev"],
                    "statistical_weight": row["statistical_weight"],
                    "principal_n": row.get("principal_n", ""),
                    "orbital_l": row.get("orbital_l", ""),
                }
            )

    record_map = output_dir / "records_source_order.csv"
    with record_map.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = [
            "source_record_ordinal",
            "source_position",
            "native_record_index",
            "linked_traversal_ordinal",
            "record",
            "next_index",
            "element_index",
            "element_z",
            "opcode",
            "data_type",
            "rate_type",
            "ion_index",
            "ion_stage",
            "lower_row",
            "upper_row",
            "real_offset",
            "real_count",
            "int_offset",
            "int_count",
            "density_scale",
            "line_energy_ev",
            "atomic_mass_amu",
            "matrix_enabled",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        z_by_element = {int(e["element_index"]): e["element_z"] for e in elements}
        for native_index, record in enumerate(records):
            element_index = int(record["element_index"])
            writer.writerow(
                {
                    "source_record_ordinal": native_index + 1,
                    "source_position": record["source_position"],
                    "native_record_index": native_index,
                    "linked_traversal_ordinal": traversal_ordinal[native_index],
                    "record": record["record"],
                    "next_index": record["next_index"],
                    "element_index": element_index,
                    "element_z": z_by_element[element_index],
                    **{
                        key: record.get(key, "")
                        for key in fieldnames[8:]
                    },
                }
            )

    input_files = ["manifest.txt", "elements.csv", "rows.csv", "records.csv", "reals.txt", "ints.txt"]
    output_files = [element_map, row_map, record_map]
    manifest = {
        "schema": MAP_SCHEMA,
        "program_directory": str(program_dir.resolve()),
        "program_id": _read_manifest_value(program_dir / "manifest.txt", "program_id"),
        "source_order_strict": True,
        "element_count": len(elements),
        "row_count": len(rows),
        "record_count": len(records),
        "inputs": [
            {
                "path": name,
                "size_bytes": (program_dir / name).stat().st_size,
                "sha256": sha256_file(program_dir / name),
            }
            for name in input_files
        ],
        "outputs": [
            {
                "path": path.name,
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in output_files
        ],
        "production_promotion_ready": False,
    }
    (output_dir / "source_order_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def _read_manifest_value(path: Path, key: str) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(key + "="):
            return line.split("=", 1)[1]
    return ""


def _float_bits(value: float) -> bytes:
    return struct.pack(">d", float(value))


def _parse_float(text: str) -> float | None:
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


@dataclass
class Difference:
    path: str
    category: str
    location: str
    reference: str
    candidate: str
    absolute_delta: float | None = None
    relative_delta: float | None = None


def _compare_csv(
    reference: Path,
    candidate: Path,
    *,
    mode: str,
    rtol: float,
    atol: float,
    max_differences: int,
) -> list[Difference]:
    rh, rr = _read_csv(reference)
    ch, cr = _read_csv(candidate)
    differences: list[Difference] = []
    if rh != ch:
        differences.append(Difference(reference.name, "csv_header", "header", repr(rh), repr(ch)))
        return differences
    if len(rr) != len(cr):
        differences.append(
            Difference(reference.name, "csv_row_count", "rows", str(len(rr)), str(len(cr)))
        )
    for row_index, (rrow, crow) in enumerate(zip(rr, cr), 2):
        if len(rrow) != len(crow):
            differences.append(
                Difference(reference.name, "csv_width", f"row {row_index}", str(len(rrow)), str(len(crow)))
            )
            if len(differences) >= max_differences:
                return differences
            continue
        for column_index, (rv, cv) in enumerate(zip(rrow, crow)):
            if rv == cv:
                continue
            rf, cf = _parse_float(rv), _parse_float(cv)
            equal = False
            absolute_delta = relative_delta = None
            if rf is not None and cf is not None:
                if math.isnan(rf) and math.isnan(cf):
                    equal = True
                elif mode == "ieee":
                    equal = _float_bits(rf) == _float_bits(cf)
                elif mode == "source-rounded":
                    equal = format(rf, ".7g") == format(cf, ".7g")
                elif mode == "diagnostic":
                    equal = math.isclose(rf, cf, rel_tol=rtol, abs_tol=atol)
                if math.isfinite(rf) and math.isfinite(cf):
                    absolute_delta = abs(cf - rf)
                    relative_delta = absolute_delta / max(abs(rf), atol, 1.0e-300)
            if not equal:
                differences.append(
                    Difference(
                        reference.name,
                        "csv_value",
                        f"row {row_index}, column {column_index + 1} ({rh[column_index]})",
                        rv,
                        cv,
                        absolute_delta,
                        relative_delta,
                    )
                )
                if len(differences) >= max_differences:
                    return differences
    return differences


def _canonical_header(header: Any, *, ignore_volatile: bool) -> list[tuple[str, str, str]]:
    cards: list[tuple[str, str, str]] = []
    for card in header.cards:
        if ignore_volatile and card.keyword in VOLATILE_FITS_KEYS:
            continue
        cards.append((card.keyword, repr(card.value), card.comment or ""))
    return cards


def _compare_fits(
    reference: Path,
    candidate: Path,
    *,
    mode: str,
    rtol: float,
    atol: float,
    max_differences: int,
) -> list[Difference]:
    try:
        import numpy as np
        from astropy.io import fits
    except Exception as exc:  # pragma: no cover - environment dependent
        return [Difference(reference.name, "fits_dependency", "import", "astropy/numpy", str(exc))]

    differences: list[Difference] = []
    with fits.open(reference, memmap=False) as ref_hdul, fits.open(candidate, memmap=False) as can_hdul:
        if len(ref_hdul) != len(can_hdul):
            differences.append(
                Difference(reference.name, "fits_hdu_count", "HDU count", str(len(ref_hdul)), str(len(can_hdul)))
            )
        for hdu_index, (rhdu, chdu) in enumerate(zip(ref_hdul, can_hdul)):
            ignore_volatile = mode != "byte"
            rh = _canonical_header(rhdu.header, ignore_volatile=ignore_volatile)
            ch = _canonical_header(chdu.header, ignore_volatile=ignore_volatile)
            if rh != ch:
                differences.append(
                    Difference(reference.name, "fits_header", f"HDU {hdu_index}", repr(rh[:20]), repr(ch[:20]))
                )
                if len(differences) >= max_differences:
                    return differences
            rdata, cdata = rhdu.data, chdu.data
            if rdata is None or cdata is None:
                if (rdata is None) != (cdata is None):
                    differences.append(
                        Difference(reference.name, "fits_data_presence", f"HDU {hdu_index}", str(rdata is not None), str(cdata is not None))
                    )
                continue
            if rdata.shape != cdata.shape or rdata.dtype.names != cdata.dtype.names:
                differences.append(
                    Difference(reference.name, "fits_shape_dtype", f"HDU {hdu_index}", f"{rdata.shape}/{rdata.dtype}", f"{cdata.shape}/{cdata.dtype}")
                )
                continue
            names = rdata.dtype.names or ("__array__",)
            for name in names:
                ra = np.asarray(rdata if name == "__array__" else rdata[name])
                ca = np.asarray(cdata if name == "__array__" else cdata[name])
                if ra.dtype.kind in "f":
                    if mode == "ieee":
                        equal_mask = ra.view(np.uint8).reshape(ra.shape + (-1,)) == ca.view(np.uint8).reshape(ca.shape + (-1,))
                        equal = bool(np.all(equal_mask))
                    elif mode == "source-rounded":
                        equal = bool(np.all(np.vectorize(lambda x, y: format(float(x), ".7g") == format(float(y), ".7g"))(ra, ca)))
                    else:
                        equal = bool(np.allclose(ra, ca, rtol=rtol, atol=atol, equal_nan=True))
                else:
                    equal = bool(np.array_equal(ra, ca))
                if not equal:
                    index = tuple(int(x) for x in np.argwhere(ra != ca)[0]) if ra.shape else ()
                    rv = ra[index] if index else ra.item()
                    cv = ca[index] if index else ca.item()
                    delta = None
                    relative = None
                    try:
                        delta = abs(float(cv) - float(rv))
                        relative = delta / max(abs(float(rv)), atol, 1.0e-300)
                    except Exception:
                        pass
                    differences.append(
                        Difference(reference.name, "fits_value", f"HDU {hdu_index}, field {name}, index {index}", repr(rv), repr(cv), delta, relative)
                    )
                    if len(differences) >= max_differences:
                        return differences
    return differences


def compare_directories(
    reference_dir: Path,
    candidate_dir: Path,
    *,
    mode: str = "ieee",
    rtol: float = 0.0,
    atol: float = 0.0,
    max_differences: int = 100,
    profile: str = "all",
) -> dict[str, Any]:
    reference_files = {p.relative_to(reference_dir).as_posix(): p for p in reference_dir.rglob("*") if p.is_file()}
    candidate_files = {p.relative_to(candidate_dir).as_posix(): p for p in candidate_dir.rglob("*") if p.is_file()}
    if profile == "science-products":
        reference_files = {name: path for name, path in reference_files.items() if name in SCIENCE_PRODUCT_FILES}
        candidate_files = {name: path for name, path in candidate_files.items() if name in SCIENCE_PRODUCT_FILES}
    elif profile != "all":
        raise ValueError(f"unsupported comparison profile: {profile}")
    differences: list[Difference] = []
    missing = sorted(set(reference_files) - set(candidate_files))
    unexpected = sorted(set(candidate_files) - set(reference_files))
    for path in missing:
        differences.append(Difference(path, "missing", "file", "present", "missing"))
    for path in unexpected:
        differences.append(Difference(path, "unexpected", "file", "absent", "present"))

    compared = 0
    exact_files = 0
    for relative in sorted(set(reference_files) & set(candidate_files)):
        reference = reference_files[relative]
        candidate = candidate_files[relative]
        compared += 1
        if sha256_file(reference) == sha256_file(candidate):
            exact_files += 1
            continue
        if mode == "byte":
            differences.append(
                Difference(relative, "byte_hash", "file", sha256_file(reference), sha256_file(candidate))
            )
        elif reference.suffix.lower() == ".csv":
            differences.extend(
                _compare_csv(reference, candidate, mode=mode, rtol=rtol, atol=atol, max_differences=max_differences - len(differences))
            )
        elif reference.suffix.lower() in {".fits", ".fit", ".fts"}:
            differences.extend(
                _compare_fits(reference, candidate, mode=mode, rtol=rtol, atol=atol, max_differences=max_differences - len(differences))
            )
        elif reference.suffix.lower() == ".json":
            try:
                rj = json.loads(reference.read_text(encoding="utf-8"))
                cj = json.loads(candidate.read_text(encoding="utf-8"))
                if rj != cj:
                    differences.append(Difference(relative, "json_value", "document", repr(rj), repr(cj)))
            except Exception:
                differences.append(Difference(relative, "text", "file", reference.read_text(errors="replace"), candidate.read_text(errors="replace")))
        else:
            rt = reference.read_text(errors="replace").splitlines()
            ct = candidate.read_text(errors="replace").splitlines()
            for line_number, (rv, cv) in enumerate(zip(rt, ct), 1):
                if rv != cv:
                    differences.append(Difference(relative, "text_line", f"line {line_number}", rv, cv))
                    if len(differences) >= max_differences:
                        break
            if len(rt) != len(ct) and len(differences) < max_differences:
                differences.append(Difference(relative, "text_line_count", "lines", str(len(rt)), str(len(ct))))
        if len(differences) >= max_differences:
            break

    result = {
        "schema": COMPARISON_SCHEMA,
        "mode": mode,
        "profile": profile,
        "reference_directory": str(reference_dir),
        "candidate_directory": str(candidate_dir),
        "files_compared": compared,
        "files_byte_exact": exact_files,
        "missing_files": missing,
        "unexpected_files": unexpected,
        "difference_count_reported": len(differences),
        "differences": [asdict(item) for item in differences],
        "result": "ACCEPT" if not differences else "REJECT",
        "production_promotion_ready": False,
    }
    return result


def _write_json(data: dict[str, Any], path: str | None) -> None:
    text = json.dumps(data, indent=2, sort_keys=True) + "\n"
    if path:
        Path(path).write_text(text, encoding="utf-8")
    print(text, end="")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    freeze = sub.add_parser("freeze-reference", help="write immutable hashes for a prepared reference directory")
    freeze.add_argument("bundle_dir", type=Path)
    freeze.add_argument("--source-archive-sha256", default="")
    freeze.add_argument("--output-json")

    verify = sub.add_parser("verify-reference", help="verify the immutable reference manifest")
    verify.add_argument("bundle_dir", type=Path)
    verify.add_argument("--output-json")

    maps = sub.add_parser("build-source-order-maps", help="emit source-order element, row, and record maps")
    maps.add_argument("program_dir", type=Path)
    maps.add_argument("output_dir", type=Path)
    maps.add_argument("--output-json")

    compare = sub.add_parser("compare", help="strictly compare a candidate product directory with a reference")
    compare.add_argument("reference_dir", type=Path)
    compare.add_argument("candidate_dir", type=Path)
    compare.add_argument("--mode", choices=["byte", "ieee", "source-rounded", "diagnostic"], default="ieee")
    compare.add_argument("--profile", choices=["all", "science-products"], default="all")
    compare.add_argument("--rtol", type=float, default=0.0)
    compare.add_argument("--atol", type=float, default=0.0)
    compare.add_argument("--max-differences", type=int, default=100)
    compare.add_argument("--output-json")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "freeze-reference":
        result = write_reference_manifest(args.bundle_dir, args.source_archive_sha256)
        result = {**result, "result": "ACCEPT"}
    elif args.command == "verify-reference":
        result = verify_reference_bundle(args.bundle_dir)
    elif args.command == "build-source-order-maps":
        result = build_source_order_maps(args.program_dir, args.output_dir)
        result = {**result, "result": "ACCEPT"}
    elif args.command == "compare":
        result = compare_directories(
            args.reference_dir,
            args.candidate_dir,
            mode=args.mode,
            rtol=args.rtol,
            atol=args.atol,
            max_differences=args.max_differences,
            profile=args.profile,
        )
    else:  # pragma: no cover
        raise AssertionError(args.command)
    _write_json(result, getattr(args, "output_json", None))
    return 0 if result.get("result") == "ACCEPT" else 1


if __name__ == "__main__":
    raise SystemExit(main())
