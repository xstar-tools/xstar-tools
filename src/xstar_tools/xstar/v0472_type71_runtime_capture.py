"""Capture a 31-record v0.6.47.2 type-71 row-77 evaluator oracle.

The capture executes the untouched ``xstar_tools==0.6.47.2``
``evaluate_type71_ucalc_record`` implementation in an isolated subprocess.
For these non-resonant cascade records the source matrix contract has
``ptmp1 + ptmp2 == 1``; the replay uses ``ptmp1=1`` and ``ptmp2=0`` and records
that assumption explicitly.  The artifact is an evaluation-61 fixed-state
oracle, not a full DSEC runtime capture.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any, Mapping

RELEASE = "0.6.48.7.9"
SCHEMA = "xstar-tools-v064877-v0472-type71-row77-runtime-capture-v1"
ORACLE_SCHEMA = "xstar-tools-v064877-type71-row77-runtime-oracle-v1"
SOURCE_VERSION = "0.6.47.2"
SOURCE_ARCHIVE_SHA256 = "85ff0184bd95daf046fd28923837239c5192f8d309b0716556d1d804b0453060"
SOURCE_MODULE_RELATIVE = Path("src/xstar_tools/rates_type71.py")
SOURCE_MODULE_SHA256 = "da83eed661cec06596f66c7ab1785875c508a5356309175d890d30977a4520cf"
TARGET_EVALUATION = 61
TARGET_COUNT = 31
ORACLE_NAME = "type71_row77_runtime_oracle.csv"
ORACLE_FIELDS = [
    "evaluation_ordinal", "source_position", "record", "element_z", "ion_stage", "data_type",
    "lower_row", "upper_row", "idest1", "idest2", "ans1", "ans2", "ans3", "ans4", "ans5", "ans6",
    "aij_s_inv", "wavelength_a", "log10_aij", "ptmp1", "ptmp2", "ptmp_sum",
    "temperature_k", "hydrogen_density_cm3", "electron_fraction_xee", "electron_density_argument_cm3",
    "payload_sha256", "source_archive_sha256", "source_module_sha256",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def safe_extract(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with tarfile.open(archive, "r:gz") as tf:
        for member in tf.getmembers():
            target = (root / member.name).resolve()
            if root != target and root not in target.parents:
                raise ValueError(f"unsafe source archive member: {member.name}")
            if member.issym() or member.islnk():
                raise ValueError(f"source archive links are not accepted: {member.name}")
        try:
            tf.extractall(root, filter="fully_trusted")
        except TypeError:
            tf.extractall(root)


def source_root(extracted: Path) -> Path:
    roots = [p.parent for p in extracted.glob("*/pyproject.toml")]
    if len(roots) != 1:
        raise ValueError(f"expected one source root, found {len(roots)}")
    root = roots[0].resolve()
    if f'version = "{SOURCE_VERSION}"' not in (root / "pyproject.toml").read_text(encoding="utf-8"):
        raise ValueError("source archive is not xstar_tools 0.6.47.2")
    if sha256(root / SOURCE_MODULE_RELATIVE) != SOURCE_MODULE_SHA256:
        raise ValueError("v0.6.47.2 rates_type71.py SHA-256 mismatch")
    return root


def state_path(audit_output: Path, evaluation: int) -> Path:
    for candidate in (
        audit_output / "diagnostics" / f"evaluation_{evaluation:04d}_state.json",
        audit_output / f"evaluation_{evaluation:04d}_state.json",
    ):
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(f"cannot find evaluation-{evaluation} state JSON under {audit_output}")


_REPLAY = r'''
from __future__ import annotations
import csv, hashlib, json, math, pathlib, sys
cfg=json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
out=pathlib.Path(sys.argv[2])
import xstar_tools
from xstar_tools.rates_type71 import evaluate_type71_ucalc_record
if str(getattr(xstar_tools,"__version__",""))!="0.6.47.2":
    raise RuntimeError("wrong xstar_tools source version")
root=pathlib.Path(cfg["lowered_program"])
reals=[float(x) for x in (root/"reals.txt").read_text().splitlines()]
ints=[int(x) for x in (root/"ints.txt").read_text().splitlines()]
with (root/"records.csv").open(newline="",encoding="utf-8") as h:
    recs=[dict(r) for r in csv.DictReader(h)]
with (root/"rows.csv").open(newline="",encoding="utf-8") as h:
    rows={(int(r["element_index"]),int(r["row"])):dict(r) for r in csv.DictReader(h)}
target=[r for r in recs if int(r["element_index"])==1 and int(r["ion_stage"])==2 and int(r["data_type"])==71 and int(r["upper_row"])==77]
target.sort(key=lambda r:int(r["source_position"]))
if len(target)!=31:
    raise RuntimeError(f"expected 31 type71 row77 records, got {len(target)}")
out.parent.mkdir(parents=True,exist_ok=True)
with out.open("w",newline="",encoding="utf-8") as h:
    w=csv.DictWriter(h,fieldnames=cfg["fields"]); w.writeheader()
    for rec in target:
        ro,rc=int(rec["real_offset"]),int(rec["real_count"])
        io,ic=int(rec["int_offset"]),int(rec["int_count"])
        payload_reals=reals[ro:ro+rc]; payload_ints=ints[io:io+ic]
        lower=rows[(1,int(rec["lower_row"]))]; upper=rows[(1,int(rec["upper_row"]))]
        ev=evaluate_type71_ucalc_record(
            {"reals":payload_reals,"ints":payload_ints},
            temperature_k=float(cfg["temperature_k"]),
            electron_density_cm3=float(cfg["hydrogen_density_cm3"]),
            ptmp1=1.0,ptmp2=0.0,
            endpoint1_energy_ev=float(lower["energy_ev"]),
            endpoint2_energy_ev=float(upper["energy_ev"]),
        )
        answers=[ev["ans1_upward_s^-1"],ev["ans2_downward_s^-1"],ev["ans3_cooling_signed_erg_s^-1"],ev["ans4_heating_signed_erg_s^-1"],0.0,0.0]
        if ev.get("status")!="evaluated" or any(x is None or not math.isfinite(float(x)) for x in answers):
            raise RuntimeError(f"type71 evaluator failed for record {rec['record']}: {ev}")
        digest=hashlib.sha256()
        for value in payload_reals:
            digest.update(float(value).hex().encode("ascii")); digest.update(b"\n")
        for value in payload_ints:
            digest.update(str(int(value)).encode("ascii")); digest.update(b"\n")
        row={
            "evaluation_ordinal":int(cfg["evaluation_ordinal"]),"source_position":int(rec["source_position"]),
            "record":int(rec["record"]),"element_z":2,"ion_stage":2,"data_type":71,
            "lower_row":int(rec["lower_row"]),"upper_row":77,
            "idest1":int(payload_ints[-2]) if len(payload_ints)>=2 else int(rec["lower_row"]),
            "idest2":int(payload_ints[-1]) if len(payload_ints)>=1 else 77,
            **{f"ans{i+1}":float(answers[i]) for i in range(6)},
            "aij_s_inv":float(ev["aij_s^-1"]),"wavelength_a":float(ev["wavelength_A"]),
            "log10_aij":float(ev["log10_aij"]),"ptmp1":1.0,"ptmp2":0.0,"ptmp_sum":1.0,
            "temperature_k":float(cfg["temperature_k"]),"hydrogen_density_cm3":float(cfg["hydrogen_density_cm3"]),
            "electron_fraction_xee":float(cfg["electron_fraction_xee"]),
            "electron_density_argument_cm3":float(cfg["hydrogen_density_cm3"]),
            "payload_sha256":digest.hexdigest(),"source_archive_sha256":cfg["source_archive_sha256"],
            "source_module_sha256":cfg["source_module_sha256"],
        }
        w.writerow(row)
pathlib.Path(sys.argv[3]).write_text(json.dumps({
    "schema":cfg["schema"],"release":cfg["release"],"result":"ACCEPT",
    "capture_kind":"exact_v06472_fixed_state_type71_row77_evaluator_replay",
    "full_dsec_runtime_capture":False,"records":len(target),"evaluation_ordinal":int(cfg["evaluation_ordinal"]),
    "escape_probability_contract":"ptmp1=1, ptmp2=0 for the source matrix-rate cascade amplitude",
    "source_package_version":"0.6.47.2","production_promotion_ready":False,
},indent=2,sort_keys=True)+"\n",encoding="utf-8")
'''


def capture(source_archive: Path, lowered_program: Path, audit_output: Path, output_dir: Path, *, evaluation: int = TARGET_EVALUATION) -> dict[str, Any]:
    source_archive = source_archive.resolve(); lowered_program = lowered_program.resolve(); audit_output = audit_output.resolve(); output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if sha256(source_archive) != SOURCE_ARCHIVE_SHA256:
        raise ValueError("v0.6.47.2 source archive SHA-256 mismatch")
    state_file = state_path(audit_output, evaluation)
    state = json.loads(state_file.read_text(encoding="utf-8"))
    cfg = {
        "schema": SCHEMA, "release": RELEASE, "fields": ORACLE_FIELDS, "evaluation_ordinal": evaluation,
        "lowered_program": str(lowered_program), "temperature_k": float(state["temperature_k"]),
        "hydrogen_density_cm3": float(state["hydrogen_density_cm3"]),
        "electron_fraction_xee": float(state.get("electron_fraction_xee", state.get("electron_fraction_input"))),
        "source_archive_sha256": SOURCE_ARCHIVE_SHA256, "source_module_sha256": SOURCE_MODULE_SHA256,
    }
    with tempfile.TemporaryDirectory(prefix="v064877-type71-") as td:
        work = Path(td); extracted = work / "source"; safe_extract(source_archive, extracted); root = source_root(extracted)
        cfg_path = work / "config.json"; cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
        report_path = output_dir / "capture_report.json"; oracle_path = output_dir / ORACLE_NAME
        env = dict(os.environ); env["PYTHONPATH"] = str(root / "src")
        cp = subprocess.run([sys.executable, "-c", _REPLAY, str(cfg_path), str(oracle_path), str(report_path)], env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if cp.returncode:
            raise RuntimeError(f"v0.6.47.2 type71 runtime capture failed: {cp.stdout}")
    return json.loads((output_dir / "capture_report.json").read_text(encoding="utf-8"))


def freeze(capture_dir: Path, bundle_dir: Path) -> dict[str, Any]:
    capture_dir = capture_dir.resolve(); bundle_dir = bundle_dir.resolve(); bundle_dir.mkdir(parents=True, exist_ok=True)
    oracle_src = capture_dir / ORACLE_NAME
    rows = list(csv.DictReader(oracle_src.open(newline="", encoding="utf-8")))
    if len(rows) != TARGET_COUNT:
        raise ValueError(f"expected {TARGET_COUNT} oracle records, got {len(rows)}")
    oracle_dst = bundle_dir / ORACLE_NAME; oracle_dst.write_bytes(oracle_src.read_bytes())
    report = json.loads((capture_dir / "capture_report.json").read_text(encoding="utf-8"))
    provenance = {
        "schema": SCHEMA, "release": RELEASE, "result": "ACCEPT", "capture_kind": report["capture_kind"],
        "full_dsec_runtime_capture": False, "records": TARGET_COUNT, "evaluation_ordinal": TARGET_EVALUATION,
        "source_archive_sha256": SOURCE_ARCHIVE_SHA256, "source_module_sha256": SOURCE_MODULE_SHA256,
        "escape_probability_contract": report["escape_probability_contract"], "production_promotion_ready": False,
    }
    write_json(bundle_dir / "capture_provenance.json", provenance)
    files = {name: {"sha256": sha256(bundle_dir / name), "size_bytes": (bundle_dir / name).stat().st_size} for name in (ORACLE_NAME, "capture_provenance.json")}
    manifest = {
        "schema": ORACLE_SCHEMA, "release": RELEASE, "result": "ACCEPT", "immutable": True,
        "capture_kind": report["capture_kind"], "full_dsec_runtime_capture": False, "records": TARGET_COUNT,
        "evaluation_ordinal": TARGET_EVALUATION, "files": files, "source_archive_sha256": SOURCE_ARCHIVE_SHA256,
        "production_promotion_ready": False,
    }
    write_json(bundle_dir / "reference_manifest.json", manifest)
    return {"schema": ORACLE_SCHEMA, "release": RELEASE, "result": "ACCEPT", "records": TARGET_COUNT,
            "bundle_directory": str(bundle_dir), "oracle_sha256": sha256(oracle_dst), "files_verified": 3,
            "production_promotion_ready": False}


def verify(bundle_dir: Path) -> dict[str, Any]:
    bundle_dir = bundle_dir.resolve(); errors: list[str] = []
    manifest_path = bundle_dir / "reference_manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for name, meta in manifest.get("files", {}).items():
        path = bundle_dir / name
        if not path.is_file(): errors.append(f"missing {name}")
        elif sha256(path) != meta.get("sha256"): errors.append(f"SHA-256 mismatch: {name}")
    rows = list(csv.DictReader((bundle_dir / ORACLE_NAME).open(newline="", encoding="utf-8"))) if (bundle_dir / ORACLE_NAME).is_file() else []
    if len(rows) != TARGET_COUNT: errors.append(f"expected {TARGET_COUNT} records, got {len(rows)}")
    for row in rows:
        for i in range(1, 7):
            try: float(row[f"ans{i}"])
            except Exception: errors.append(f"invalid ans{i} for record {row.get('record')}")
    return {"schema": ORACLE_SCHEMA, "release": RELEASE, "result": "ACCEPT" if not errors else "REJECT",
            "bundle_directory": str(bundle_dir), "records": len(rows), "errors": errors,
            "files_verified": 3 if not errors else 0,
            "oracle_sha256": sha256(bundle_dir / ORACLE_NAME) if (bundle_dir / ORACLE_NAME).is_file() else None,
            "production_promotion_ready": False}


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__); sub = p.add_subparsers(dest="command", required=True)
    c = sub.add_parser("capture-and-freeze"); c.add_argument("source_archive", type=Path); c.add_argument("lowered_program", type=Path); c.add_argument("audit_output", type=Path); c.add_argument("bundle_dir", type=Path); c.add_argument("--evaluation", type=int, default=61); c.add_argument("--output-json", type=Path)
    v = sub.add_parser("verify"); v.add_argument("bundle_dir", type=Path); v.add_argument("--output-json", type=Path)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "capture-and-freeze":
            with tempfile.TemporaryDirectory(prefix="v064877-type71-capture-") as td:
                capture(args.source_archive, args.lowered_program, args.audit_output, Path(td), evaluation=args.evaluation)
                report = freeze(Path(td), args.bundle_dir)
                verification = verify(args.bundle_dir); report["verification"] = verification
        else:
            report = verify(args.bundle_dir)
        if getattr(args, "output_json", None): write_json(args.output_json.resolve(), report)
        print(json.dumps(report, indent=2, sort_keys=True)); return 0 if report["result"] == "ACCEPT" else 2
    except Exception as exc:
        print(f"v0.6.47.2 type71 runtime capture failed: {exc}"); return 2


if __name__ == "__main__":
    raise SystemExit(main())
