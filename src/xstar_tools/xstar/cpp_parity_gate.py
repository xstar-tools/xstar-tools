#!/usr/bin/env python3
"""Python-reference vs C++-candidate parity gate for Mg XI ne=1e8 products.

This gate intentionally uses the Python xstar_tools run as the reference.  The
Python port is not bit-for-bit original Fortran XSTAR, but it is the current
source-faithful physics baseline for enabling C++ accelerators.  No C++ path
should become default unless this gate passes against the Python baseline.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

PRODUCTS = [
    "xout_step.log",
    "xout_abund1.fits",
    "xout_cont1.fits",
    "xout_lines1.fits",
    "xout_rrc1.fits",
    "xout_spect1.fits",
    "xo01_detail.fits",
    "xo01_detal2.fits",
    "xo01_detal3.fits",
    "xo01_detal4.fits",
]
FITS_PRODUCTS = [p for p in PRODUCTS if p.endswith(".fits")]
MG_RE = re.compile(r"^\s*(\d+)\s+(mg_[ivx]+)\s+([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?)")
SUMMARY_RE = re.compile(r"^\s*([+-]?\d+\.\d+)\s+([+-]?\d+\.\d+)\s+([+-]?\d+\.\d+)\s+([+-]?\d+\.\d+)\s+([+-]?\d+\.\d+)\s+([+-]?\d+\.\d+)\s+([+-]?\d+\.\d+)\s+([+-]?\d+\.\d+)\s+([+-]?\d+\.\d+)\s+([+-]?\d+\.\d+)\s+([+-]?\d+\.\d+)\s+(\d+)\s*$")
KV_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_()/-]*)=\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?)")


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the sha256 operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: Diagnostic/qualification helper; observes qualified runtime state and has no independent paper equation.
# XSTAR-FUNCTION-COMMENT-END
def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the fits headers operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: Diagnostic/qualification helper; observes qualified runtime state and has no independent paper equation.
# XSTAR-FUNCTION-COMMENT-END
def fits_headers(path: Path) -> list[dict[str, str]]:
    data = path.read_bytes()
    pos = 0
    headers: list[dict[str, str]] = []
    while pos < len(data):
        cards: list[str] = []
        header_start = pos
        while pos + 80 <= len(data):
            card = data[pos:pos + 80].decode("ascii", "replace")
            cards.append(card)
            pos += 80
            if card.startswith("END"):
                break
        if not cards:
            break
        pos = header_start + ((pos - header_start + 2879) // 2880) * 2880
        h: dict[str, str] = {}
        for card in cards:
            key = card[:8].strip()
            if not key or card[8:10] != "= ":
                continue
            h[key] = card[10:80].split("/", 1)[0].strip().strip("'").strip()
        headers.append(h)
        bitpix = int(h.get("BITPIX", "8") or "8")
        naxis = int(h.get("NAXIS", "0") or "0")
        size = 0
        if naxis > 0:
            size = abs(bitpix) // 8
            for axis in range(1, naxis + 1):
                size *= int(h.get(f"NAXIS{axis}", "0") or "0")
            size += int(h.get("PCOUNT", "0") or "0")
            size *= int(h.get("GCOUNT", "1") or "1")
        pos += ((size + 2879) // 2880) * 2880
    return headers


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the fits signature operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: Diagnostic/qualification helper; observes qualified runtime state and has no independent paper equation.
# XSTAR-FUNCTION-COMMENT-END
def fits_signature(path: Path, *, canonical_tforms: bool = False) -> list[dict[str, Any]]:
    sig = []
    for h in fits_headers(path):
        row = {
            "xtension": h.get("XTENSION", "PRIMARY"),
            "naxis1": int(h.get("NAXIS1", "0") or "0"),
            "naxis2": int(h.get("NAXIS2", "0") or "0"),
            "tfields": int(h.get("TFIELDS", "0") or "0"),
        }
        tf = row["tfields"]
        if tf:
            tforms = [h.get(f"TFORM{i}", "") for i in range(1, tf + 1)]
            if canonical_tforms:
                tforms = [t[1:] if len(t) > 1 and t.startswith("1") and t[1] in "IJEDABC" else t for t in tforms]
            row["tforms"] = tforms
            row["tbcols"] = [h.get(f"TBCOL{i}", "") for i in range(1, tf + 1)]
        sig.append(row)
    return sig


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the extract step metrics operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: Diagnostic/qualification helper; observes qualified runtime state and has no independent paper equation.
# XSTAR-FUNCTION-COMMENT-END
def extract_step_metrics(path: Path) -> dict[str, Any]:
    text = path.read_text(errors="replace")
    lines = text.splitlines()
    metrics: dict[str, Any] = {"summary_rows": [], "option22": {}, "option27_mg": {}}
    for line in lines:
        m = SUMMARY_RE.match(line)
        if m:
            values = [float(m.group(i)) for i in range(1, 12)]
            metrics["summary_rows"].append({
                "log_r": values[0], "delr_r": values[1], "log_N": values[2],
                "log_xi": values[3], "x_e": values[4], "log_n": values[5],
                "log_t": values[6], "hc_fwd": values[7], "hc_rev": values[8],
                "log_tau_fwd": values[9], "log_tau_rev": values[10],
                "last_column": int(m.group(12)),
            })
    for i, line in enumerate(lines):
        if "print option:22" in line:
            block = "\n".join(lines[i:i + 8])
            metrics["option22"] = {k: float(v) for k, v in KV_RE.findall(block)}
            break
    in27 = False
    for line in lines:
        if "print option:27" in line:
            in27 = True
            continue
        if in27:
            m = MG_RE.match(line)
            if m:
                metrics["option27_mg"][m.group(2)] = float(m.group(3))
            elif "print option:" in line and metrics["option27_mg"]:
                break
    return metrics


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the relerr operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: Diagnostic/qualification helper; observes qualified runtime state and has no independent paper equation.
# XSTAR-FUNCTION-COMMENT-END
def relerr(ref: float, cand: float) -> float:
    denom = max(abs(ref), 1.0e-300)
    return abs(cand - ref) / denom


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Check scalar map for this module while preserving the surrounding source/runtime invariants.
# Reference context: Diagnostic/qualification helper; observes qualified runtime state and has no independent paper equation.
# XSTAR-FUNCTION-COMMENT-END
def check_scalar_map(ref: dict[str, float], cand: dict[str, float], rtol: float, atol: float = 0.0) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, rval in sorted(ref.items()):
        if key not in cand:
            out[key] = {"reference": rval, "candidate": None, "relerr": math.inf, "absdiff": math.inf, "pass": False}
            continue
        cval = float(cand[key])
        adiff = abs(float(rval) - cval)
        err = relerr(float(rval), cval)
        out[key] = {"reference": rval, "candidate": cval, "relerr": err, "absdiff": adiff, "pass": (adiff <= atol or err <= rtol)}
    return out


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the main operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: Diagnostic/qualification helper; observes qualified runtime state and has no independent paper equation.
# XSTAR-FUNCTION-COMMENT-END
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reference-dir", required=True, help="Python-reference product directory")
    ap.add_argument("--candidate-dir", required=True, help="C++ candidate product directory")
    ap.add_argument("--out-json")
    ap.add_argument("--mg-rtol", type=float, default=1.0e-6)
    ap.add_argument("--option22-rtol", type=float, default=1.0e-6)
    ap.add_argument("--summary-hc-atol", type=float, default=1.0e-2)
    ap.add_argument("--require-fits-structure", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--require-fits-size", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--require-fits-hash", action=argparse.BooleanOptionalAction, default=False)
    ap.add_argument("--canonical-tforms", action=argparse.BooleanOptionalAction, default=True)
    args = ap.parse_args(argv)
    ref = Path(args.reference_dir)
    cand = Path(args.candidate_dir)
    report: dict[str, Any] = {
        "reference_dir": str(ref),
        "candidate_dir": str(cand),
        "ready": True,
        "policy": "C++ candidate must match the Python-reference xstar_tools products before becoming default.",
        "files": {},
        "step": {},
    }

    for name in PRODUCTS:
        r = ref / name
        c = cand / name
        rec: dict[str, Any] = {"exists_reference": r.exists(), "exists_candidate": c.exists()}
        if r.exists() and c.exists():
            rec.update({
                "reference_size": r.stat().st_size,
                "candidate_size": c.stat().st_size,
                "size_match": r.stat().st_size == c.stat().st_size,
                "hash_match": sha256(r) == sha256(c),
            })
            if name.endswith(".fits"):
                rsig = fits_signature(r, canonical_tforms=args.canonical_tforms)
                csig = fits_signature(c, canonical_tforms=args.canonical_tforms)
                rec["fits_structure_match"] = rsig == csig
                rec["reference_fits_signature"] = rsig
                rec["candidate_fits_signature"] = csig
        else:
            report["ready"] = False
        report["files"][name] = rec

    if (ref / "xout_step.log").exists() and (cand / "xout_step.log").exists():
        rm = extract_step_metrics(ref / "xout_step.log")
        cm = extract_step_metrics(cand / "xout_step.log")
        step: dict[str, Any] = {"reference": rm, "candidate": cm, "checks": {}}
        summary_checks = []
        for idx, (rr, cr) in enumerate(zip(rm.get("summary_rows", []), cm.get("summary_rows", []))):
            row = {
                "row": idx,
                "hc_fwd_absdiff": abs(float(rr["hc_fwd"]) - float(cr["hc_fwd"])),
                "hc_rev_absdiff": abs(float(rr["hc_rev"]) - float(cr["hc_rev"])),
                "last_column_reference": int(rr["last_column"]),
                "last_column_candidate": int(cr["last_column"]),
            }
            row["pass"] = (
                row["hc_fwd_absdiff"] <= args.summary_hc_atol
                and row["hc_rev_absdiff"] <= args.summary_hc_atol
                and row["last_column_reference"] == row["last_column_candidate"]
            )
            summary_checks.append(row)
        step["checks"]["summary_rows"] = summary_checks
        step["checks"]["option27_mg"] = check_scalar_map(rm.get("option27_mg", {}), cm.get("option27_mg", {}), args.mg_rtol)
        step["checks"]["option22"] = check_scalar_map(rm.get("option22", {}), cm.get("option22", {}), args.option22_rtol)
        report["step"] = step
    else:
        report["ready"] = False

    for rec in report["files"].values():
        if not rec.get("exists_reference") or not rec.get("exists_candidate"):
            report["ready"] = False
        if args.require_fits_size and rec.get("size_match") is False:
            report["ready"] = False
        if args.require_fits_hash and rec.get("hash_match") is False:
            report["ready"] = False
        if args.require_fits_structure and rec.get("fits_structure_match") is False:
            report["ready"] = False
    for row in report.get("step", {}).get("checks", {}).get("summary_rows", []):
        if not row.get("pass"):
            report["ready"] = False
    for group in ("option27_mg", "option22"):
        for val in report.get("step", {}).get("checks", {}).get(group, {}).values():
            if not val.get("pass"):
                report["ready"] = False

    if args.out_json:
        Path(args.out_json).write_text(json.dumps(report, indent=2, sort_keys=True))
    print(json.dumps({"ready": report["ready"], "reference_dir": str(ref), "candidate_dir": str(cand)}, indent=2))
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
