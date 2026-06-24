"""Immutable product-oracle manifests and strict product comparison for v0.6.48.7.46.23.

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
import struct
import tarfile
from typing import Any, Iterable

RELEASE = "0.6.48.7.46.23.1"
SCHEMA = "xstar-tools-v0648746231-product-oracle-v5"
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


def inspect_fits_bytes(data: bytes, *, include_cards: bool = False) -> list[dict[str, Any]]:
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
        one = {
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
        }
        if include_cards:
            one["cards"] = cards
            one["header_values"] = header
        hdus.append(one)
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


_HEADER_COMPARE_EXCLUDED = {"CHECKSUM", "DATASUM"}


def _semantic_cards(cards: list[str]) -> list[str]:
    return [card for card in cards if card[:8].strip() not in _HEADER_COMPARE_EXCLUDED]


def _first_sequence_difference(expected: list[Any], actual: list[Any]) -> dict[str, Any] | None:
    count = max(len(expected), len(actual))
    for index in range(count):
        e = expected[index] if index < len(expected) else None
        a = actual[index] if index < len(actual) else None
        if e != a:
            return {"index": index, "expected": e, "actual": a}
    return None


def _first_column_difference(expected: list[dict[str, Any]], actual: list[dict[str, Any]]) -> dict[str, Any] | None:
    count = max(len(expected), len(actual))
    for index in range(count):
        e = expected[index] if index < len(expected) else None
        a = actual[index] if index < len(actual) else None
        if e != a:
            keys = sorted(set(e or {}) | set(a or {}))
            field = next((key for key in keys if (e or {}).get(key) != (a or {}).get(key)), None)
            return {
                "column_index": index + 1,
                "field": field,
                "expected": e,
                "actual": a,
            }
    return None


def _compare_hdus(
    expected: list[dict[str, Any]],
    actual: list[dict[str, Any]],
    expected_detailed: list[dict[str, Any]],
    actual_detailed: list[dict[str, Any]],
) -> dict[str, Any]:
    pairs = []
    count = max(len(expected), len(actual))
    for index in range(count):
        e = expected[index] if index < len(expected) else None
        a = actual[index] if index < len(actual) else None
        ed = expected_detailed[index] if index < len(expected_detailed) else None
        ad = actual_detailed[index] if index < len(actual_detailed) else None
        ekeys = (e or {}).get("structural_keys", {})
        akeys = (a or {}).get("structural_keys", {})
        ecols = (e or {}).get("columns", [])
        acols = (a or {}).get("columns", [])
        semantic_expected = _semantic_cards((ed or {}).get("cards", []))
        semantic_actual = _semantic_cards((ad or {}).get("cards", []))
        pairs.append({
            "index": index,
            "present_expected": e is not None,
            "present_actual": a is not None,
            "extension_name_expected": ekeys.get("EXTNAME", "PRIMARY"),
            "extension_name_actual": akeys.get("EXTNAME", "PRIMARY"),
            "extension_name_exact": bool(e and a and ekeys.get("EXTNAME", "PRIMARY") == akeys.get("EXTNAME", "PRIMARY")),
            "row_width_expected": ekeys.get("NAXIS1", 0),
            "row_width_actual": akeys.get("NAXIS1", 0),
            "row_width_exact": bool(e and a and ekeys.get("NAXIS1", 0) == akeys.get("NAXIS1", 0)),
            "row_count_expected": ekeys.get("NAXIS2", 0),
            "row_count_actual": akeys.get("NAXIS2", 0),
            "row_count_exact": bool(e and a and ekeys.get("NAXIS2", 0) == akeys.get("NAXIS2", 0)),
            "field_count_expected": ekeys.get("TFIELDS", 0),
            "field_count_actual": akeys.get("TFIELDS", 0),
            "field_count_exact": bool(e and a and ekeys.get("TFIELDS", 0) == akeys.get("TFIELDS", 0)),
            "columns_exact": bool(e and a and ecols == acols),
            "first_column_difference": _first_column_difference(ecols, acols),
            "structure_exact": bool(e and a and ekeys == akeys and ecols == acols),
            "header_semantic_exact": bool(e and a and semantic_expected == semantic_actual),
            "first_header_card_difference": _first_sequence_difference(semantic_expected, semantic_actual),
            "header_bytes_exact": bool(e and a and e["header_sha256"] == a["header_sha256"]),
            "header_exact": bool(e and a and semantic_expected == semantic_actual),
            "data_exact": bool(e and a and e["data_sha256"] == a["data_sha256"]),
            "hdu_exact": bool(e and a and e["hdu_sha256"] == a["hdu_sha256"]),
        })
    return {
        "hdu_count_expected": len(expected),
        "hdu_count_actual": len(actual),
        "hdu_count_exact": len(expected) == len(actual),
        "extension_order_exact": all(item["extension_name_exact"] for item in pairs),
        "row_widths_exact": all(item["row_width_exact"] for item in pairs),
        "row_counts_exact": all(item["row_count_exact"] for item in pairs),
        "field_counts_exact": all(item["field_count_exact"] for item in pairs),
        "column_metadata_exact": all(item["columns_exact"] for item in pairs),
        "all_structure_exact": all(item["structure_exact"] for item in pairs),
        "all_headers_exact": all(item["header_semantic_exact"] for item in pairs),
        "all_header_bytes_exact": all(item["header_bytes_exact"] for item in pairs),
        "all_data_exact": all(item["data_exact"] for item in pairs),
        "all_hdus_exact": all(item["hdu_exact"] for item in pairs),
        "hdus": pairs,
    }


def _oracle_payloads(oracle_dir: Path, manifest: dict[str, Any]) -> dict[str, bytes]:
    archive_path = oracle_dir / manifest["archive"]["filename"]
    result: dict[str, bytes] = {}
    with tarfile.open(archive_path, "r:gz") as archive:
        for member in _safe_members(archive):
            basename = _product_basename(member.name)
            if basename not in EXPECTED_PRODUCTS:
                continue
            stream = archive.extractfile(member)
            if stream is not None:
                result[basename] = stream.read()
    return result



_TFORM_RE = re.compile(r"^\s*(\d*)([A-Z])(?:\([^)]*\))?\s*$")
_TFORM_WIDTH = {"A": 1, "B": 1, "L": 1, "I": 2, "J": 4, "K": 8, "E": 4, "D": 8}


def _tform_layout(columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    offset = 0
    layout: list[dict[str, Any]] = []
    for index, column in enumerate(columns, start=1):
        form = str(column.get("TFORM", "") or "")
        match = _TFORM_RE.match(form)
        if not match or match.group(2) not in _TFORM_WIDTH:
            raise ValueError(f"unsupported TFORM for XSTAR_RADIAL comparison: {form!r}")
        count = int(match.group(1) or "1")
        code = match.group(2)
        width = count * _TFORM_WIDTH[code]
        layout.append({
            "column_index": index,
            "name": column.get("TTYPE"),
            "form": form,
            "count": count,
            "code": code,
            "offset": offset,
            "width": width,
        })
        offset += width
    return layout


def _decode_cell(raw: bytes, code: str, count: int) -> dict[str, Any]:
    if code == "A":
        return {
            "text": raw.decode("ascii", errors="replace"),
            "trimmed": raw.decode("ascii", errors="replace").rstrip(),
            "hex": raw.hex(),
        }
    if code == "L":
        return {"values": [chr(value) for value in raw], "hex": raw.hex()}
    formats = {"B": "B", "I": "h", "J": "i", "K": "q", "E": "f", "D": "d"}
    fmt = ">" + formats[code] * count
    values = list(struct.unpack(fmt, raw))
    result: dict[str, Any] = {"values": values, "hex": raw.hex()}
    if code in {"E", "D"}:
        unit = 4 if code == "E" else 8
        result["bit_patterns"] = [
            "0x" + raw[index * unit : (index + 1) * unit].hex()
            for index in range(count)
        ]
    return result


def _hdu_unpadded_payload(file_bytes: bytes, hdu: dict[str, Any]) -> bytes:
    start = int(hdu["offset"]) + int(hdu["header_bytes"])
    end = start + int(hdu["data_bytes_unpadded"])
    return file_bytes[start:end]


def _first_radial_cell_difference(
    expected_payload: bytes,
    actual_payload: bytes,
    expected_hdu: dict[str, Any],
    actual_hdu: dict[str, Any],
) -> dict[str, Any] | None:
    columns = expected_hdu.get("columns", [])
    if columns != actual_hdu.get("columns", []):
        return None
    layout = _tform_layout(columns)
    row_width = int(expected_hdu["structural_keys"].get("NAXIS1", 0) or 0)
    row_count = int(expected_hdu["structural_keys"].get("NAXIS2", 0) or 0)
    if row_width <= 0 or len(expected_payload) != row_width * row_count:
        return None
    if len(actual_payload) != len(expected_payload):
        return None
    for row_index in range(row_count):
        row_start = row_index * row_width
        for column in layout:
            start = row_start + int(column["offset"])
            end = start + int(column["width"])
            expected_raw = expected_payload[start:end]
            actual_raw = actual_payload[start:end]
            if expected_raw != actual_raw:
                return {
                    "row_index": row_index + 1,
                    "column_index": column["column_index"],
                    "column_name": column["name"],
                    "tform": column["form"],
                    "expected": _decode_cell(expected_raw, column["code"], column["count"]),
                    "actual": _decode_cell(actual_raw, column["code"], column["count"]),
                }
    return None


def _compare_xstar_radial_payloads(
    oracle_payloads: dict[str, bytes],
    output_dir: Path,
) -> dict[str, Any]:
    expected_set: list[dict[str, Any]] = []
    actual_set: list[dict[str, Any]] = []
    hdu_reports: list[dict[str, Any]] = []
    first_cell_difference: dict[str, Any] | None = None
    radial_products = sorted(
        name for name in FITS_PRODUCTS
        if any(
            hdu.get("structural_keys", {}).get("EXTNAME") == "XSTAR_RADIAL"
            for hdu in inspect_fits_bytes(oracle_payloads[name])
        )
    )
    for name in radial_products:
        expected_bytes = oracle_payloads[name]
        actual_path = output_dir / name
        expected_hdus = [
            hdu for hdu in inspect_fits_bytes(expected_bytes, include_cards=True)
            if hdu.get("structural_keys", {}).get("EXTNAME") == "XSTAR_RADIAL"
        ]
        actual_bytes = actual_path.read_bytes() if actual_path.is_file() else b""
        actual_hdus = [
            hdu for hdu in inspect_fits_bytes(actual_bytes, include_cards=True)
            if hdu.get("structural_keys", {}).get("EXTNAME") == "XSTAR_RADIAL"
        ] if actual_bytes else []
        for ordinal, hdu in enumerate(expected_hdus, start=1):
            expected_set.append({"file": name, "ordinal": ordinal, "hdu_index": hdu["index"]})
        for ordinal, hdu in enumerate(actual_hdus, start=1):
            actual_set.append({"file": name, "ordinal": ordinal, "hdu_index": hdu["index"]})
        count = max(len(expected_hdus), len(actual_hdus))
        for ordinal in range(count):
            expected_hdu = expected_hdus[ordinal] if ordinal < len(expected_hdus) else None
            actual_hdu = actual_hdus[ordinal] if ordinal < len(actual_hdus) else None
            expected_payload = _hdu_unpadded_payload(expected_bytes, expected_hdu) if expected_hdu else b""
            actual_payload = _hdu_unpadded_payload(actual_bytes, actual_hdu) if actual_hdu else b""
            columns_exact = bool(expected_hdu and actual_hdu and expected_hdu["columns"] == actual_hdu["columns"])
            row_counts_exact = bool(
                expected_hdu and actual_hdu
                and expected_hdu["structural_keys"].get("NAXIS2") == actual_hdu["structural_keys"].get("NAXIS2")
                and expected_hdu["structural_keys"].get("NAXIS1") == actual_hdu["structural_keys"].get("NAXIS1")
            )
            payload_exact = bool(expected_hdu and actual_hdu and expected_payload == actual_payload)
            one = {
                "file": name,
                "ordinal": ordinal + 1,
                "hdu_index_expected": expected_hdu["index"] if expected_hdu else None,
                "hdu_index_actual": actual_hdu["index"] if actual_hdu else None,
                "column_metadata_exact": columns_exact,
                "row_counts_exact": row_counts_exact,
                "payload_exact": payload_exact,
                "payload_sha256_expected": sha256_bytes(expected_payload) if expected_hdu else None,
                "payload_sha256_actual": sha256_bytes(actual_payload) if actual_hdu else None,
            }
            if (
                first_cell_difference is None
                and expected_hdu and actual_hdu and columns_exact and row_counts_exact
                and not payload_exact
            ):
                diff = _first_radial_cell_difference(
                    expected_payload, actual_payload, expected_hdu, actual_hdu)
                if diff is not None:
                    first_cell_difference = {"file": name, "ordinal": ordinal + 1, **diff}
                    one["first_cell_difference"] = diff
            hdu_reports.append(one)
    hdu_set_exact = expected_set == actual_set
    column_metadata_exact = hdu_set_exact and all(item["column_metadata_exact"] for item in hdu_reports)
    row_counts_exact = hdu_set_exact and all(item["row_counts_exact"] for item in hdu_reports)
    payload_exact = hdu_set_exact and all(item["payload_exact"] for item in hdu_reports)
    products_exact = payload_exact and len(radial_products) == 4
    return {
        "expected_hdu_set": expected_set,
        "actual_hdu_set": actual_set,
        "hdu_set_exact": hdu_set_exact,
        "column_metadata_exact": column_metadata_exact,
        "row_counts_exact": row_counts_exact,
        "payload_exact": payload_exact,
        "all_products_exact": products_exact,
        "first_cell_difference": first_cell_difference,
        "hdus": hdu_reports,
    }


def compare_output(output_dir: Path, oracle: Path, output_json: Path | None = None) -> dict[str, Any]:
    manifest, oracle_dir = _read_oracle_manifest(oracle)
    oracle_payloads = _oracle_payloads(oracle_dir, manifest)
    files_report: dict[str, Any] = {}
    actual_names = {p.name for p in output_dir.iterdir() if p.is_file()} if output_dir.is_dir() else set()
    expected_names = set(EXPECTED_PRODUCTS)
    missing = sorted(expected_names - actual_names)
    extra_product_like = sorted(
        name for name in actual_names - expected_names if name.endswith(".fits") or name == "xout_step.log"
    )
    first_header_difference: dict[str, Any] | None = None
    first_column_difference: dict[str, Any] | None = None
    parameter_hdus: list[bool] = []
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
                expected_detailed = inspect_fits_bytes(oracle_payloads[name], include_cards=True)
                actual_detailed = inspect_fits_bytes(payload, include_cards=True)
                fits_report = _compare_hdus(
                    expected["hdus"],
                    inspect_fits_bytes(payload),
                    expected_detailed,
                    actual_detailed,
                )
                report["fits"] = fits_report
                for hdu in fits_report["hdus"]:
                    if first_header_difference is None and hdu.get("first_header_card_difference"):
                        first_header_difference = {
                            "file": name,
                            "hdu_index": hdu["index"],
                            **hdu["first_header_card_difference"],
                        }
                    if first_column_difference is None and hdu.get("first_column_difference"):
                        first_column_difference = {
                            "file": name,
                            "hdu_index": hdu["index"],
                            **hdu["first_column_difference"],
                        }
                    if hdu.get("extension_name_expected") == "PARAMETERS":
                        parameter_hdus.append(bool(hdu.get("data_exact")))
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

    radial_comparison = _compare_xstar_radial_payloads(oracle_payloads, output_dir)
    fits_reports = [files_report[name].get("fits", {}) for name in FITS_PRODUCTS]
    hdu_counts_exact = all(item.get("hdu_count_exact", False) for item in fits_reports)
    extension_order_exact = all(item.get("extension_order_exact", False) for item in fits_reports)
    row_counts_exact = all(item.get("row_counts_exact", False) for item in fits_reports)
    row_widths_exact = all(item.get("row_widths_exact", False) for item in fits_reports)
    column_metadata_exact = all(item.get("column_metadata_exact", False) for item in fits_reports)
    fits_structure_exact = all(item.get("all_structure_exact", False) for item in fits_reports)
    fits_headers_exact = all(item.get("all_headers_exact", False) for item in fits_reports)
    fits_header_bytes_exact = all(item.get("all_header_bytes_exact", False) for item in fits_reports)
    fits_data_exact = all(item.get("all_data_exact", False) for item in fits_reports)
    non_radial_numeric_hdus = [
        hdu
        for name in FITS_PRODUCTS
        for hdu in files_report[name].get("fits", {}).get("hdus", [])
        if hdu.get("extension_name_expected") not in {"PRIMARY", "PARAMETERS", "XSTAR_RADIAL"}
    ]
    non_radial_numeric_exact = bool(non_radial_numeric_hdus) and all(
        hdu.get("data_exact", False) for hdu in non_radial_numeric_hdus)
    parameter_table_exact = bool(parameter_hdus) and all(parameter_hdus) and len(parameter_hdus) == 8

    in_memory_radial_state_complete = False
    radial_state_detail: dict[str, Any] = {"manifest_present": False}
    state_path = output_dir / "native_physical_run_state.json"
    if state_path.is_file():
        radial_state_detail["manifest_present"] = True
        try:
            state = json.loads(state_path.read_text())
            radial_layer = state.get("layers", {}).get("radial_zone_state", {})
            zones = state.get("radial_zones", [])
            in_memory_radial_state_complete = (
                radial_layer.get("count") == 5
                and radial_layer.get("complete") is True
                and len(zones) == 5
                and all(zone.get("python_oracle_exact") is True for zone in zones)
            )
            radial_state_detail.update({
                "count": radial_layer.get("count"),
                "complete": radial_layer.get("complete"),
                "python_oracle_exact_rows": sum(zone.get("python_oracle_exact") is True for zone in zones),
            })
        except Exception as exc:
            radial_state_detail["error"] = f"{type(exc).__name__}: {exc}"

    radial_state_complete = (
        in_memory_radial_state_complete
        and radial_comparison["all_products_exact"]
    )
    radial_state_detail["in_memory_complete"] = in_memory_radial_state_complete
    radial_state_detail["emitted_xstar_radial_exact"] = radial_comparison["all_products_exact"]

    all_byte_exact = not missing and all(files_report[name].get("byte_exact", False) for name in EXPECTED_PRODUCTS)
    report = {
        "schema": "xstar-tools-v0648746231-strict-product-comparison-v3",
        "release": RELEASE,
        "oracle_name": manifest["oracle_name"],
        "oracle_source_kind": manifest["source_kind"],
        "output_dir": str(output_dir.resolve()),
        "oracle_manifest": str((oracle_dir / "manifest.json").resolve()),
        "header_exactness_contract": {
            "semantic_cards_exact": True,
            "excluded_data_derived_cards": sorted(_HEADER_COMPARE_EXCLUDED),
            "raw_header_bytes_reported_separately": True,
        },
        "missing_products": missing,
        "extra_product_like_files": extra_product_like,
        "first_header_card_difference": first_header_difference,
        "first_column_difference": first_column_difference,
        "radial_state": radial_state_detail,
        "xstar_radial": radial_comparison,
        "files": files_report,
        "gates": {
            "TEN_PRODUCTS_PRESENT": "ACCEPT" if not missing else "REJECT",
            "FITS_HDU_COUNTS_EXACT": "ACCEPT" if hdu_counts_exact else "REJECT",
            "FITS_EXTENSION_ORDER_EXACT": "ACCEPT" if extension_order_exact else "REJECT",
            "FITS_ROW_COUNTS_EXACT": "ACCEPT" if row_counts_exact else "REJECT",
            "FITS_ROW_WIDTHS_EXACT": "ACCEPT" if row_widths_exact else "REJECT",
            "FITS_COLUMN_METADATA_EXACT": "ACCEPT" if column_metadata_exact else "REJECT",
            "FITS_HDU_STRUCTURE_EXACT": "ACCEPT" if fits_structure_exact else "REJECT",
            "FITS_HEADERS_EXACT": "ACCEPT" if fits_headers_exact else "REJECT",
            "FITS_HEADER_BYTES_EXACT": "ACCEPT" if fits_header_bytes_exact else "REJECT_ALLOWED",
            "PARAMETER_TABLE_EXACT": "ACCEPT" if parameter_table_exact else "REJECT",
            "XSTAR_RADIAL_HDU_SET_EXACT": "ACCEPT" if radial_comparison["hdu_set_exact"] else "REJECT",
            "XSTAR_RADIAL_COLUMN_METADATA_EXACT": "ACCEPT" if radial_comparison["column_metadata_exact"] else "REJECT",
            "XSTAR_RADIAL_ROW_COUNTS_EXACT": "ACCEPT" if radial_comparison["row_counts_exact"] else "REJECT",
            "XSTAR_RADIAL_PAYLOAD_EXACT": "ACCEPT" if radial_comparison["payload_exact"] else "REJECT",
            "XSTAR_RADIAL_ALL_PRODUCTS_EXACT": "ACCEPT" if radial_comparison["all_products_exact"] else "REJECT",
            "RADIAL_ZONE_STATE_COMPLETE": "ACCEPT" if radial_state_complete else "REJECT",
            "FITS_NUMERIC_ARRAYS_EXACT": "ACCEPT" if non_radial_numeric_exact else "REJECT_ALLOWED",
            "NON_RADIAL_NUMERIC_ARRAYS_EXACT": "ACCEPT" if non_radial_numeric_exact else "REJECT_ALLOWED",
            "XOUT_STEP_PARITY": "NOT_RUN",
            "XOUT_STEP_RAW_DIAGNOSTIC": "ACCEPT" if files_report["xout_step.log"].get("byte_exact") else "REJECT_DIAGNOSTIC",
            "XOUT_STEP_NORMALIZED_DIAGNOSTIC": "ACCEPT" if files_report["xout_step.log"].get("normalized_exact") else "REJECT_DIAGNOSTIC",
            "ALL_PRODUCT_FILES_BYTE_EXACT": "ACCEPT" if all_byte_exact else "REJECT_ALLOWED",
        },
        "schema_header_radial_closure": "ACCEPT" if all((
            not missing,
            hdu_counts_exact,
            extension_order_exact,
            row_counts_exact,
            row_widths_exact,
            column_metadata_exact,
            fits_headers_exact,
            parameter_table_exact,
            radial_comparison["hdu_set_exact"],
            radial_comparison["column_metadata_exact"],
            radial_comparison["row_counts_exact"],
            radial_comparison["payload_exact"],
            radial_comparison["all_products_exact"],
            radial_state_complete,
        )) else "REJECT",
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
