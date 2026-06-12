"""Exact v0.6.47.2 fixed-state type-99 replay for record 1695.

The replay executes the untouched ``xstar_tools==0.6.47.2`` source-faithful
``SourceFaithfulUCalc`` type-99 branch in an isolated subprocess.  It uses the
packed active-ATDB payload, evaluation-61 state, ion-local level context, and
frozen 9,999-bin radiation field.  The result is an independent single-record
fixed-state evaluator oracle, not a full DSEC-controller runtime capture.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any, Mapping

RELEASE = "0.6.48.7.6"
SCHEMA = "xstar-tools-v064876-v0472-type99-record1695-runtime-capture-v1"
ORACLE_SCHEMA = "xstar-tools-v064876-type99-record1695-runtime-oracle-v1"
SOURCE_VERSION = "0.6.47.2"
SOURCE_ARCHIVE_SHA256 = "85ff0184bd95daf046fd28923837239c5192f8d309b0716556d1d804b0453060"
UCALC_RELATIVE = Path("src/xstar_tools/xstar/ucalc.py")
SOLVER_RELATIVE = Path("src/xstar_tools/xstar_element_solver.py")
UCALC_SHA256 = "54479ba156e1be784ce669d97ef97183af781531f9b0b39313d8c965fed51b8b"
SOLVER_SHA256 = "6852eae4709032449c6addcf18f2bab31052ba4fa0564b5e06bac6832f470851"
RADIATION_SHA256 = "8cd5771924724d5aa8fcf5af8c533f5b5ca9887e24a94ac2d7b4557c0ff7b108"
TARGET_RECORD = 1695
TARGET_SOURCE_POSITION = 6312
ORACLE_NAME = "type99_record1695_runtime_oracle.csv"
ORACLE_FIELDS = [
    "evaluation_ordinal", "source_position", "record", "element_z", "ion_stage", "data_type",
    "lower_row", "upper_row", "idest1", "idest2", "ans1", "ans2", "ans3", "ans4", "ans5", "ans6",
    "threshold_ev", "temperature_k", "hydrogen_density_cm3", "electron_fraction_xee", "electron_density_cm3",
    "radiation_bins", "payload_sha256", "source_archive_sha256", "source_ucalc_sha256", "source_solver_sha256",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def safe_extract(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with tarfile.open(archive, "r:gz") as handle:
        for member in handle.getmembers():
            target = (root / member.name).resolve()
            if root != target and root not in target.parents:
                raise ValueError(f"unsafe source-archive member: {member.name}")
            if member.issym() or member.islnk():
                raise ValueError(f"source archive links are not accepted: {member.name}")
        try:
            handle.extractall(root, filter="fully_trusted")
        except TypeError:
            handle.extractall(root)


def source_root(extracted: Path) -> Path:
    roots = [path.parent for path in extracted.glob("*/pyproject.toml")]
    if len(roots) != 1:
        raise ValueError(f"expected one source root, found {len(roots)}")
    root = roots[0].resolve()
    text = (root / "pyproject.toml").read_text(encoding="utf-8")
    if f'version = "{SOURCE_VERSION}"' not in text:
        raise ValueError("source archive is not xstar_tools 0.6.47.2")
    if sha256(root / UCALC_RELATIVE) != UCALC_SHA256:
        raise ValueError("v0.6.47.2 ucalc.py SHA-256 mismatch")
    if sha256(root / SOLVER_RELATIVE) != SOLVER_SHA256:
        raise ValueError("v0.6.47.2 xstar_element_solver.py SHA-256 mismatch")
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
from xstar_tools.rates_type53 import Type53LiveRadiationState
from xstar_tools.xstar.ucalc import UCalcContext,UCalcLevel,UCalcLevelTable,UCalcRecord,SourceFaithfulUCalc
if str(getattr(xstar_tools,"__version__",""))!="0.6.47.2":
    raise RuntimeError("wrong xstar_tools source version")
root=pathlib.Path(cfg["lowered_program"])
reals=[float(x) for x in (root/"reals.txt").read_text().splitlines()]
ints=[int(x) for x in (root/"ints.txt").read_text().splitlines()]
with (root/"records.csv").open(newline="",encoding="utf-8") as h:
    recs={int(r["record"]):dict(r) for r in csv.DictReader(h)}
rec=recs[1695]
if int(rec["source_position"])!=6312 or int(rec["data_type"])!=99:
    raise RuntimeError("record 1695 identity mismatch")
ro,rc=int(rec["real_offset"]),int(rec["real_count"])
io,ic=int(rec["int_offset"]),int(rec["int_count"])
record=UCalcRecord(record=1695,data_type=99,rate_type=int(rec["rate_type"]),continuation=0,
    reals=tuple(reals[ro:ro+rc]),integers=tuple(ints[io:io+ic]))
with (root/"rows.csv").open(newline="",encoding="utf-8") as h:
    ion_rows=[dict(r) for r in csv.DictReader(h) if int(r["element_index"])==1 and int(r["ion"])==2]
ion_rows.sort(key=lambda r:int(r["row"]))
if len(ion_rows)!=33 or int(ion_rows[0]["row"])!=46 or int(ion_rows[-1]["row"])!=78:
    raise RuntimeError("unexpected He II ion-local row topology")
levels=UCalcLevelTable(nlev=len(ion_rows))
for local,row in enumerate(ion_rows,start=1):
    levels.levels[local]=UCalcLevel(index=local,energy_ev=float(row["energy_ev"]),
        statistical_weight=float(row["statistical_weight"]),principal_n=int(row["principal_n"]),
        orbital_l=int(row["orbital_l"]))
energy=[]; incident=[]
with pathlib.Path(cfg["radiation_csv"]).open(newline="",encoding="utf-8") as h:
    reader=csv.DictReader(h)
    if not {"energy","incident"}.issubset(reader.fieldnames or []):
        raise RuntimeError("radiation CSV missing energy/incident")
    for row in reader:
        energy.append(float(row["energy"])); incident.append(float(row["incident"]))
if len(energy)!=9999:
    raise RuntimeError(f"expected 9999 radiation bins, got {len(energy)}")
radiation=Type53LiveRadiationState.from_sequences(energy,incident,[0.0]*len(energy),metadata={
    "type53_grid_policy":"full_high_resolution_epi_bremsa_for_side_effects",
    "type53_grid_source":"frozen_v06472_full_radiation_csv",
})
ctx=UCalcContext(temperature_k=float(cfg["temperature_k"]),hydrogen_density_cm3=float(cfg["hydrogen_density_cm3"]),
    electron_fraction_xee=float(cfg["electron_fraction_xee"]),nlev=len(ion_rows),levels=levels,radiation=radiation,
    ptmp1=1.0,ptmp2=0.0,lfast=2)
result=SourceFaithfulUCalc().evaluate(record,ctx,strict=True)
if str(result.status.value)!="evaluated":
    raise RuntimeError(f"source evaluator status={result.status}")
answers=[float(result.ans1),float(result.ans2),float(result.ans3),float(result.ans4),float(result.ans5),float(result.ans6)]
if any(not math.isfinite(x) for x in answers):
    raise RuntimeError("source evaluator returned non-finite answer")
digest=hashlib.sha256()
for value in record.reals:
    digest.update(float(value).hex().encode("ascii")); digest.update(b"\n")
row={
    "evaluation_ordinal":int(cfg["evaluation_ordinal"]),"source_position":6312,"record":1695,
    "element_z":2,"ion_stage":2,"data_type":99,"lower_row":77,"upper_row":78,
    "idest1":int(result.idest1),"idest2":int(result.idest2),
    **{f"ans{i+1}":answers[i] for i in range(6)},
    "threshold_ev":float(rec["line_energy_ev"]),"temperature_k":float(cfg["temperature_k"]),
    "hydrogen_density_cm3":float(cfg["hydrogen_density_cm3"]),"electron_fraction_xee":float(cfg["electron_fraction_xee"]),
    "electron_density_cm3":float(cfg["hydrogen_density_cm3"])*float(cfg["electron_fraction_xee"]),
    "radiation_bins":len(energy),"payload_sha256":digest.hexdigest(),
    "source_archive_sha256":cfg["source_archive_sha256"],"source_ucalc_sha256":cfg["source_ucalc_sha256"],
    "source_solver_sha256":cfg["source_solver_sha256"],
}
out.parent.mkdir(parents=True,exist_ok=True)
with out.open("w",newline="",encoding="utf-8") as h:
    w=csv.DictWriter(h,fieldnames=cfg["fields"]); w.writeheader(); w.writerow(row)
pathlib.Path(sys.argv[3]).write_text(json.dumps({
    "schema":cfg["schema"],"release":cfg["release"],"result":"ACCEPT",
    "capture_kind":"exact_v06472_fixed_state_type99_record1695_evaluator_replay",
    "full_dsec_runtime_capture":False,"records":1,"record":1695,"source_position":6312,
    "source_package_version":"0.6.47.2","answers":{f"ans{i+1}":answers[i] for i in range(6)},
    "idest1":int(result.idest1),"idest2":int(result.idest2),
    "diagnostics":result.diagnostics,"production_promotion_ready":False,
},indent=2,sort_keys=True,default=str)+"\n",encoding="utf-8")
'''


def capture(source_archive: Path, lowered_program: Path, audit_output: Path, radiation_csv: Path, output_dir: Path, *, evaluation: int = 61) -> dict[str, Any]:
    source_archive = source_archive.resolve(); lowered_program = lowered_program.resolve(); audit_output = audit_output.resolve()
    radiation_csv = radiation_csv.resolve(); output_dir = output_dir.resolve(); output_dir.mkdir(parents=True, exist_ok=True)
    if sha256(source_archive) != SOURCE_ARCHIVE_SHA256:
        raise ValueError("v0.6.47.2 source archive SHA-256 mismatch")
    if sha256(radiation_csv) != RADIATION_SHA256:
        raise ValueError("radiation CSV SHA-256 mismatch")
    state_file = state_path(audit_output, evaluation)
    state = json.loads(state_file.read_text(encoding="utf-8"))
    cfg = {
        "schema": SCHEMA, "release": RELEASE, "evaluation_ordinal": evaluation,
        "lowered_program": str(lowered_program), "radiation_csv": str(radiation_csv),
        "temperature_k": float(state["temperature_k"]),
        "hydrogen_density_cm3": float(state["hydrogen_density_cm3"]),
        "electron_fraction_xee": float(state.get("electron_fraction_input", state.get("electron_fraction_xee"))),
        "source_archive_sha256": SOURCE_ARCHIVE_SHA256, "source_ucalc_sha256": UCALC_SHA256,
        "source_solver_sha256": SOLVER_SHA256, "fields": ORACLE_FIELDS,
    }
    with tempfile.TemporaryDirectory(prefix="v064876-type99-") as td:
        temp = Path(td)
        extracted = temp / "source"; safe_extract(source_archive, extracted); root = source_root(extracted)
        cfg_path = temp / "config.json"; write_json(cfg_path, cfg)
        csv_path = output_dir / ORACLE_NAME; report_path = output_dir / "capture_report.json"
        env = dict(os.environ); env["PYTHONPATH"] = str(root / "src")
        result = subprocess.run([sys.executable, "-c", _REPLAY, str(cfg_path), str(csv_path), str(report_path)],
            cwd=temp, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if result.returncode:
            raise RuntimeError("v0.6.47.2 type-99 replay failed:\n" + result.stdout)
    provenance = {
        "schema": SCHEMA, "release": RELEASE, "capture_kind": "exact_v06472_fixed_state_type99_record1695_evaluator_replay",
        "full_dsec_runtime_capture": False, "source_archive_sha256": SOURCE_ARCHIVE_SHA256,
        "source_ucalc_sha256": UCALC_SHA256, "source_solver_sha256": SOLVER_SHA256,
        "radiation_sha256": RADIATION_SHA256, "state_json_sha256": sha256(state_file),
        "lowered_program_manifest_sha256": sha256(lowered_program / "manifest.txt"),
        "record": TARGET_RECORD, "source_position": TARGET_SOURCE_POSITION,
        "oracle_csv_sha256": sha256(output_dir / ORACLE_NAME), "production_promotion_ready": False,
    }
    write_json(output_dir / "capture_provenance.json", provenance)
    files = {}
    for name in (ORACLE_NAME, "capture_report.json", "capture_provenance.json"):
        path = output_dir / name; files[name] = {"sha256": sha256(path), "size_bytes": path.stat().st_size}
    manifest = {
        "schema": ORACLE_SCHEMA, "release": RELEASE, "result": "ACCEPT", "immutable": True,
        "records": 1, "record": TARGET_RECORD, "source_position": TARGET_SOURCE_POSITION,
        "capture_kind": provenance["capture_kind"], "files": files, "production_promotion_ready": False,
    }
    write_json(output_dir / "reference_manifest.json", manifest)
    return verify(output_dir)


def verify(bundle: Path) -> dict[str, Any]:
    bundle = bundle.resolve(); errors: list[str] = []
    manifest_path = bundle / "reference_manifest.json"
    if not manifest_path.is_file():
        errors.append("missing reference_manifest.json")
        manifest: dict[str, Any] = {}
    else:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for name, meta in manifest.get("files", {}).items():
        path = bundle / name
        if not path.is_file(): errors.append(f"missing {name}")
        elif sha256(path) != meta.get("sha256"): errors.append(f"SHA-256 mismatch for {name}")
    csv_path = bundle / ORACLE_NAME
    rows: list[dict[str, str]] = []
    if csv_path.is_file():
        with csv_path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle); rows = list(reader)
            missing = sorted(set(ORACLE_FIELDS).difference(reader.fieldnames or []))
            if missing: errors.append("missing oracle fields: " + ", ".join(missing))
        if len(rows) != 1: errors.append(f"expected one oracle row, found {len(rows)}")
        elif int(rows[0].get("record", 0)) != TARGET_RECORD or int(rows[0].get("source_position", 0)) != TARGET_SOURCE_POSITION:
            errors.append("oracle record identity mismatch")
        else:
            for i in range(1, 7):
                try: value = float(rows[0][f"ans{i}"])
                except Exception: value = math.nan
                if not math.isfinite(value): errors.append(f"ans{i} is non-finite")
    return {
        "schema": ORACLE_SCHEMA, "release": RELEASE, "result": "ACCEPT" if not errors else "REJECT",
        "bundle_directory": str(bundle), "records": len(rows), "errors": errors,
        "oracle_sha256": sha256(csv_path) if csv_path.is_file() else None,
        "production_promotion_ready": False,
    }


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__); sub = p.add_subparsers(dest="command", required=True)
    c = sub.add_parser("capture-and-freeze"); c.add_argument("source_archive", type=Path); c.add_argument("lowered_program", type=Path)
    c.add_argument("audit_output", type=Path); c.add_argument("radiation_csv", type=Path); c.add_argument("output_dir", type=Path)
    c.add_argument("--evaluation", type=int, default=61); c.add_argument("--output-json", type=Path)
    v = sub.add_parser("verify"); v.add_argument("bundle", type=Path); v.add_argument("--output-json", type=Path)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "capture-and-freeze":
            report = capture(args.source_archive, args.lowered_program, args.audit_output, args.radiation_csv, args.output_dir, evaluation=args.evaluation)
        else: report = verify(args.bundle)
        if args.output_json: write_json(args.output_json, report)
        print(json.dumps(report, indent=2, sort_keys=True)); return 0 if report["result"] == "ACCEPT" else 2
    except Exception as exc:
        print(f"v0.6.47.2 type-99 runtime capture failed: {exc}"); return 2


if __name__ == "__main__":
    raise SystemExit(main())
