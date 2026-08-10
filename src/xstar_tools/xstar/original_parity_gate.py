#!/usr/bin/env python3
"""Original-XSTAR parity gate for the Mg XI ne=1e8 benchmark products."""
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
def fits_signature(path: Path) -> list[dict[str, Any]]:
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
            row["tforms"] = [h.get(f"TFORM{i}", "") for i in range(1, tf + 1)]
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
def relerr(a: float, b: float) -> float:
    denom = max(abs(a), 1.0e-300)
    return abs(b - a) / denom


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the main operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: Diagnostic/qualification helper; observes qualified runtime state and has no independent paper equation.
# XSTAR-FUNCTION-COMMENT-END
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--original-dir", required=True)
    ap.add_argument("--python-dir", required=True)
    ap.add_argument("--out-json")
    ap.add_argument("--mg-rtol", type=float, default=2.0e-2)
    ap.add_argument("--option22-rtol", type=float, default=2.0e-2)
    ap.add_argument("--require-fits-structure", action="store_true", default=True)
    args = ap.parse_args(argv)
    orig = Path(args.original_dir)
    py = Path(args.python_dir)
    report: dict[str, Any] = {"original_dir": str(orig), "python_dir": str(py), "files": {}, "step": {}, "ready": True}

    for name in PRODUCTS:
        o = orig / name
        p = py / name
        rec: dict[str, Any] = {"exists_original": o.exists(), "exists_python": p.exists()}
        if o.exists() and p.exists():
            rec.update({
                "original_size": o.stat().st_size,
                "python_size": p.stat().st_size,
                "size_match": o.stat().st_size == p.stat().st_size,
                "hash_match": sha256(o) == sha256(p),
            })
            if name.endswith(".fits"):
                osig = fits_signature(o)
                psig = fits_signature(p)
                rec["fits_structure_match"] = osig == psig
                rec["original_fits_signature"] = osig
                rec["python_fits_signature"] = psig
        else:
            report["ready"] = False
        report["files"][name] = rec

    if (orig / "xout_step.log").exists() and (py / "xout_step.log").exists():
        om = extract_step_metrics(orig / "xout_step.log")
        pm = extract_step_metrics(py / "xout_step.log")
        step: dict[str, Any] = {"original": om, "python": pm, "checks": {}}
        if om.get("summary_rows") and pm.get("summary_rows"):
            o0 = om["summary_rows"][0]
            p0 = pm["summary_rows"][0]
            step["checks"]["summary_first_hc_fwd_absdiff"] = abs(float(o0["hc_fwd"]) - float(p0["hc_fwd"]))
            step["checks"]["summary_first_last_column_match"] = int(o0["last_column"]) == int(p0["last_column"])
        mg_checks = {}
        for ion, oval in sorted(om.get("option27_mg", {}).items()):
            if ion in pm.get("option27_mg", {}):
                perr = relerr(float(oval), float(pm["option27_mg"][ion]))
                mg_checks[ion] = {"original": oval, "python": pm["option27_mg"][ion], "relerr": perr, "pass": perr <= args.mg_rtol}
        step["checks"]["option27_mg"] = mg_checks
        opt22_checks = {}
        for key, oval in sorted(om.get("option22", {}).items()):
            if key in pm.get("option22", {}):
                perr = relerr(float(oval), float(pm["option22"][key]))
                opt22_checks[key] = {"original": oval, "python": pm["option22"][key], "relerr": perr, "pass": perr <= args.option22_rtol}
        step["checks"]["option22"] = opt22_checks
        report["step"] = step
    else:
        report["ready"] = False

    # Gate conditions.
    for rec in report["files"].values():
        if not rec.get("exists_original") or not rec.get("exists_python"):
            report["ready"] = False
        if rec.get("exists_original") and rec.get("exists_python") and rec.get("fits_structure_match") is False:
            report["ready"] = False
    for val in report.get("step", {}).get("checks", {}).get("option27_mg", {}).values():
        if not val.get("pass"):
            report["ready"] = False
    for val in report.get("step", {}).get("checks", {}).get("option22", {}).values():
        if not val.get("pass"):
            report["ready"] = False
    if report.get("step", {}).get("checks", {}).get("summary_first_last_column_match") is False:
        report["ready"] = False

    if args.out_json:
        Path(args.out_json).write_text(json.dumps(report, indent=2, sort_keys=True))
    print(json.dumps({"ready": report["ready"], "python_dir": str(py), "original_dir": str(orig)}, indent=2))
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
