"""Immutable product-oracle manifests and strict product comparison for v0.6.48.7.46.22.

The module intentionally has no Astropy dependency.  It parses FITS block
boundaries directly so qualification hosts can freeze and compare products
with only the Python standard library.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import tarfile
from typing import Any, Iterable

RELEASE = "0.6.48.7.46.22"
SCHEMA = "xstar-tools-v064874622-product-oracle-v1"
EXPECTED_PRODUCTS = (
    "xo01_detail.fits",
    "xo01_detal2.fits",
    "xo01_detal3.fits",
    "xo01_detal4.fits",
    "xout_abund1.fits",
    "xout_cont1.fits",
    "xout_lines1.fits",
    "xout_rrc1.fits",
    "xout_spect1.fits",
    "xout_step.log",
)
FITS_PRODUCTS = tuple(name for name in EXPECTED_PRODUCTS if name.endswith(".fits"))
BLOCK = 2880
CARD = 80


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_card_value(card: str) -> Any:
    if len(card) < 10 or card[8] != "=":
        return None
    raw = card[10:]
    in_quote = False
    value_chars: list[str] = []
    i = 0
    while i < len(raw):
        ch = raw[i]
        if ch == "'":
            if in_quote and i + 1 < len(raw) and raw[i + 1] == "'":
                value_chars.extend(["'", "'"])
                i += 2
                continue
            in_quote = not in_quote
        if ch == "/" and not in_quote:
            break
        value_chars.append(ch)
        i += 1
    value = "".join(value_chars).strip()
    if not value:
        return ""
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1].replace("''", "'").rstrip()
    if value == "T":
        return True
    if value == "F":
        return False
    normalized = value.replace("D", "E")
    try:
        if any(ch in normalized for ch in ".Ee"):
            return float(normalized)
        return int(normalized)
    except ValueError:
        return value


def _header_at(data: bytes, offset: int) -> tuple[dict[str, Any], list[str], int]:
    cards: list[str] = []
    cursor = offset
    found_end = False
    while cursor + BLOCK <= len(data):
        block = data[cursor : cursor + BLOCK]
        for start in range(0, BLOCK, CARD):
            card = block[start : start + CARD].decode("ascii", errors="replace")
            cards.append(card)
            if card.startswith("END"):
                found_end = True
                break
        cursor += BLOCK
        if found_end:
            break
    if not found_end:
        raise ValueError(f"FITS header at offset {offset} has no END card")
    values: dict[str, Any] = {}
    for card in cards:
        key = card[:8].strip()
        if key and key not in {"COMMENT", "HISTORY", "END"} and key not in values:
            values[key] = _parse_card_value(card)
    return values, cards, cursor - offset


def _hdu_data_size(header: dict[str, Any]) -> int:
    xtension = str(header.get("XTENSION", "PRIMARY") or "PRIMARY").strip().upper()
    naxis = int(header.get("NAXIS", 0) or 0)
    pcount = int(header.get("PCOUNT", 0) or 0)
    gcount = int(header.get("GCOUNT", 1) or 1)
    if xtension in {"BINTABLE", "TABLE", "A3DTABLE"}:
        return int(header.get("NAXIS1", 0) or 0) * int(header.get("NAXIS2", 0) or 0) + pcount
    if naxis <= 0:
        return 0
    pixels = 1
    for axis in range(1, naxis + 1):
        pixels *= max(0, int(header.get(f"NAXIS{axis}", 0) or 0))
    bitpix = abs(int(header.get("BITPIX", 8) or 8))
    return (pixels * bitpix // 8 + pcount) * gcount


def inspect_fits_bytes(data: bytes) -> list[dict[str, Any]]:
    hdus: list[dict[str, Any]] = []
    offset = 0
    index = 0
    while offset < len(data):
        if data[offset:] == b"" or not data[offset:].strip(b"\0 "):
            break
        header, cards, header_size = _header_at(data, offset)
        data_size = _hdu_data_size(header)
        padded_data_size = int(math.ceil(data_size / BLOCK) * BLOCK) if data_size else 0
        data_start = offset + header_size
        end = data_start + padded_data_size
        if end > len(data):
            raise ValueError(f"FITS HDU {index} extends beyond file")
        header_bytes = data[offset:data_start]
        data_bytes = data[data_start:end]
        structural_keys = {
            key: header[key]
            for key in (
                "SIMPLE", "XTENSION", "BITPIX", "NAXIS", "NAXIS1", "NAXIS2",
                "PCOUNT", "GCOUNT", "TFIELDS", "EXTNAME", "EXTVER",
            )
            if key in header
        }
        columns = []
        fields = int(header.get("TFIELDS", 0) or 0)
        for col in range(1, fields + 1):
            columns.append({
                key: header.get(f"{key}{col}")
                for key in ("TTYPE", "TFORM", "TUNIT", "TDISP", "TNULL", "TZERO", "TSCAL")
                if f"{key}{col}" in header
            })
        hdus.append({
            "index": index,
            "offset": offset,
            "header_bytes": header_size,
            "data_bytes_unpadded": data_size,
            "data_bytes_padded": padded_data_size,
            "card_count": len(cards),
            "structural_keys": structural_keys,
            "columns": columns,
            "header_sha256": sha256_bytes(header_bytes),
            "data_sha256": sha256_bytes(data_bytes),
            "hdu_sha256": sha256_bytes(data[offset:end]),
        })
        offset = end
        index += 1
    if offset != len(data) and data[offset:].strip(b"\0 "):
        raise ValueError(f"unparsed FITS bytes remain at offset {offset}")
    return hdus


_RUNTIME_LINE = re.compile(r"(?i)(elapsed|runtime|total\s+time|cpu\s+time|wall\s+time|writer\s+time)")
_FLOAT_WITH_UNIT = re.compile(r"(?<![A-Za-z0-9_.])[-+]?\d+(?:\.\d+)?(?:[Ee][-+]?\d+)?\s*(?:s|sec|secs|seconds|minutes|min)\b", re.I)
_ABS_PATH = re.compile(r"(?<![A-Za-z0-9_.-])/(?:[^\s'\"]+/)+[^\s'\"]+")
_ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}(?:[T ][0-9:.+-Z]+)?\b")
_VERSION_LINE = re.compile(r"(?i)(xstar_tools\s+version\s*)\S+")


def normalize_log_text(text: str) -> str:
    """Normalize only non-scientific provenance and runtime fields.

    Scientific numbers, row order, identifiers, and section labels are retained.
    """
    normalized: list[str] = []
    for source_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = source_line.rstrip()
        line = _ABS_PATH.sub("<PATH>", line)
        line = _ISO_DATE.sub("<DATE>", line)
        line = _VERSION_LINE.sub(r"\1<VERSION>", line)
        if _RUNTIME_LINE.search(line):
            line = _FLOAT_WITH_UNIT.sub("<RUNTIME>", line)
            line = re.sub(r"(?<=[=:])\s*[-+]?\d+(?:\.\d+)?(?:[Ee][-+]?\d+)?", " <RUNTIME>", line)
        normalized.append(line)
    while normalized and normalized[-1] == "":
        normalized.pop()
    return "\n".join(normalized) + "\n"


def _safe_members(archive: tarfile.TarFile) -> Iterable[tarfile.TarInfo]:
    for member in archive.getmembers():
        path = Path(member.name)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"unsafe archive member: {member.name}")
        if member.isfile():
            yield member


def _product_basename(name: str) -> str:
    return Path(name).name


def freeze_bundle(archive_path: Path, output_dir: Path, oracle_name: str, source_kind: str) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    files: dict[str, dict[str, Any]] = {}
    raw_log: bytes | None = None
    with tarfile.open(archive_path, "r:gz") as archive:
        for member in _safe_members(archive):
            basename = _product_basename(member.name)
            if basename not in EXPECTED_PRODUCTS:
                continue
            extracted = archive.extractfile(member)
            if extracted is None:
                raise ValueError(f"cannot read archive member: {member.name}")
            payload = extracted.read()
            entry: dict[str, Any] = {
                "archive_member": member.name,
                "size": len(payload),
                "sha256": sha256_bytes(payload),
            }
            if basename.endswith(".fits"):
                entry["hdus"] = inspect_fits_bytes(payload)
            else:
                raw_log = payload
                text = payload.decode("utf-8", errors="replace")
                normalized = normalize_log_text(text)
                entry["line_count"] = len(text.splitlines())
                entry["normalized_sha256"] = sha256_bytes(normalized.encode("utf-8"))
            files[basename] = entry
    missing = [name for name in EXPECTED_PRODUCTS if name not in files]
    if missing:
        raise ValueError(f"oracle archive is missing products: {missing}")
    if raw_log is None:
        raise ValueError("oracle archive is missing xout_step.log")
    copied_archive = output_dir / "bundle.tar.gz"
    shutil.copyfile(archive_path, copied_archive)
    raw_log_path = output_dir / "xout_step.raw.log"
    normalized_log_path = output_dir / "xout_step.normalized.log"
    raw_log_path.write_bytes(raw_log)
    normalized_log_path.write_text(
        normalize_log_text(raw_log.decode("utf-8", errors="replace")), encoding="utf-8"
    )
    manifest = {
        "schema": SCHEMA,
        "release": RELEASE,
        "oracle_name": oracle_name,
        "source_kind": source_kind,
        "product_parity_claimed": False,
        "archive": {
            "filename": "bundle.tar.gz",
            "size": copied_archive.stat().st_size,
            "sha256": sha256_file(copied_archive),
        },
        "expected_products": list(EXPECTED_PRODUCTS),
        "files": files,
        "log_references": {
            "raw": raw_log_path.name,
            "normalized": normalized_log_path.name,
            "normalization_contract": "paths, dates, version labels, and runtime-only fields only",
        },
        "result": "ACCEPT",
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    (output_dir / "SHA256SUMS").write_text(
        f"{manifest['archive']['sha256']}  bundle.tar.gz\n"
        f"{sha256_file(output_dir / 'manifest.json')}  manifest.json\n"
        f"{sha256_file(raw_log_path)}  {raw_log_path.name}\n"
        f"{sha256_file(normalized_log_path)}  {normalized_log_path.name}\n"
    )
    return manifest


def _read_oracle_manifest(path: Path) -> tuple[dict[str, Any], Path]:
    manifest_path = path / "manifest.json" if path.is_dir() else path
    return json.loads(manifest_path.read_text()), manifest_path.parent


def _compare_hdus(expected: list[dict[str, Any]], actual: list[dict[str, Any]]) -> dict[str, Any]:
    pairs = []
    count = max(len(expected), len(actual))
    for index in range(count):
        e = expected[index] if index < len(expected) else None
        a = actual[index] if index < len(actual) else None
        pairs.append({
            "index": index,
            "present_expected": e is not None,
            "present_actual": a is not None,
            "structure_exact": bool(e and a and e["structural_keys"] == a["structural_keys"] and e["columns"] == a["columns"]),
            "header_exact": bool(e and a and e["header_sha256"] == a["header_sha256"]),
            "data_exact": bool(e and a and e["data_sha256"] == a["data_sha256"]),
            "hdu_exact": bool(e and a and e["hdu_sha256"] == a["hdu_sha256"]),
        })
    return {
        "hdu_count_expected": len(expected),
        "hdu_count_actual": len(actual),
        "hdu_count_exact": len(expected) == len(actual),
        "all_structure_exact": all(item["structure_exact"] for item in pairs),
        "all_headers_exact": all(item["header_exact"] for item in pairs),
        "all_data_exact": all(item["data_exact"] for item in pairs),
        "all_hdus_exact": all(item["hdu_exact"] for item in pairs),
        "hdus": pairs,
    }


def compare_output(output_dir: Path, oracle: Path, output_json: Path | None = None) -> dict[str, Any]:
    manifest, oracle_dir = _read_oracle_manifest(oracle)
    files_report: dict[str, Any] = {}
    actual_names = {p.name for p in output_dir.iterdir() if p.is_file()} if output_dir.is_dir() else set()
    expected_names = set(EXPECTED_PRODUCTS)
    missing = sorted(expected_names - actual_names)
    extra_product_like = sorted(
        name for name in actual_names - expected_names if name.endswith(".fits") or name == "xout_step.log"
    )
    for name in EXPECTED_PRODUCTS:
        expected = manifest["files"][name]
        path = output_dir / name
        if not path.is_file():
            files_report[name] = {"present": False, "result": "MISSING"}
            continue
        payload = path.read_bytes()
        report: dict[str, Any] = {
            "present": True,
            "size_expected": expected["size"],
            "size_actual": len(payload),
            "sha256_expected": expected["sha256"],
            "sha256_actual": sha256_bytes(payload),
        }
        report["byte_exact"] = report["sha256_expected"] == report["sha256_actual"]
        if name.endswith(".fits"):
            try:
                report["fits"] = _compare_hdus(expected["hdus"], inspect_fits_bytes(payload))
                report["result"] = "ACCEPT" if report["byte_exact"] else "REJECT"
            except Exception as exc:  # comparator must report rather than crash
                report["fits_error"] = f"{type(exc).__name__}: {exc}"
                report["result"] = "REJECT"
        else:
            text = payload.decode("utf-8", errors="replace")
            normalized = normalize_log_text(text)
            report["line_count_expected"] = expected.get("line_count")
            report["line_count_actual"] = len(text.splitlines())
            report["normalized_sha256_expected"] = expected["normalized_sha256"]
            report["normalized_sha256_actual"] = sha256_bytes(normalized.encode("utf-8"))
            report["normalized_exact"] = report["normalized_sha256_expected"] == report["normalized_sha256_actual"]
            report["result"] = "ACCEPT" if report["byte_exact"] else "REJECT"
        files_report[name] = report
    fits_structure_exact = all(
        files_report[name].get("fits", {}).get("all_structure_exact", False)
        for name in FITS_PRODUCTS
    )
    fits_headers_exact = all(
        files_report[name].get("fits", {}).get("all_headers_exact", False)
        for name in FITS_PRODUCTS
    )
    fits_data_exact = all(
        files_report[name].get("fits", {}).get("all_data_exact", False)
        for name in FITS_PRODUCTS
    )
    all_byte_exact = not missing and all(files_report[name].get("byte_exact", False) for name in EXPECTED_PRODUCTS)
    report = {
        "schema": "xstar-tools-v064874622-strict-product-comparison-v1",
        "release": RELEASE,
        "oracle_name": manifest["oracle_name"],
        "oracle_source_kind": manifest["source_kind"],
        "output_dir": str(output_dir.resolve()),
        "oracle_manifest": str((oracle_dir / "manifest.json").resolve()),
        "missing_products": missing,
        "extra_product_like_files": extra_product_like,
        "files": files_report,
        "gates": {
            "TEN_PRODUCTS_PRESENT": "ACCEPT" if not missing else "REJECT",
            "FITS_HDU_STRUCTURE_EXACT": "ACCEPT" if fits_structure_exact else "REJECT",
            "FITS_HEADERS_EXACT": "ACCEPT" if fits_headers_exact else "REJECT",
            "FITS_NUMERIC_AND_TABLE_BYTES_EXACT": "ACCEPT" if fits_data_exact else "REJECT",
            "XOUT_STEP_RAW_EXACT": "ACCEPT" if files_report["xout_step.log"].get("byte_exact") else "REJECT",
            "XOUT_STEP_NORMALIZED_EXACT": "ACCEPT" if files_report["xout_step.log"].get("normalized_exact") else "REJECT",
            "ALL_PRODUCT_FILES_BYTE_EXACT": "ACCEPT" if all_byte_exact else "REJECT",
        },
        "product_level_parity": "ACCEPT" if all_byte_exact else "REJECT",
        "production_promotion_ready": False,
        "result": "ACCEPT" if all_byte_exact else "REJECT",
    }
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def bundled_oracle_root(name: str = "python_physical_run") -> Path:
    return Path(__file__).resolve().parents[1] / "benchmarks" / "v064874622_product_oracles" / name


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    freeze = sub.add_parser("freeze")
    freeze.add_argument("--archive", required=True, type=Path)
    freeze.add_argument("--output-dir", required=True, type=Path)
    freeze.add_argument("--oracle-name", required=True)
    freeze.add_argument("--source-kind", required=True, choices=("python", "fortran"))
    compare = sub.add_parser("compare")
    compare.add_argument("--output-dir", required=True, type=Path)
    compare.add_argument("--oracle", type=Path)
    compare.add_argument("--oracle-name", default="python_physical_run")
    compare.add_argument("--output-json", type=Path)
    normalize = sub.add_parser("normalize-log")
    normalize.add_argument("input", type=Path)
    normalize.add_argument("output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "freeze":
        result = freeze_bundle(args.archive, args.output_dir, args.oracle_name, args.source_kind)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.command == "compare":
        oracle = args.oracle or bundled_oracle_root(args.oracle_name)
        result = compare_output(args.output_dir, oracle, args.output_json)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["result"] == "ACCEPT" else 2
    if args.command == "normalize-log":
        args.output.write_text(normalize_log_text(args.input.read_text(errors="replace")), encoding="utf-8")
        return 0
    return 64


if __name__ == "__main__":
    raise SystemExit(main())
