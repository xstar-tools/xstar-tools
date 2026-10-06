#!/usr/bin/env python3
"""Validate the accepted Mn/Type-49 science-refreeze record and source contract."""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECORD = ROOT / "qualification" / "mn_type49_science_refreeze_0_6_90_5_8.json"
SCIENCE = "0.6.90.5.5"
PACKAGE = "0.6.90.5.8"


def reject(message: str) -> None:
    raise SystemExit(f"MN_TYPE49_SCIENCE_REFREEZE_REJECT: {message}")


def main() -> int:
    data = json.loads(RECORD.read_text(encoding="utf-8"))
    if data.get("schema") != "xstar-tools-mn-type49-science-refreeze-v1":
        reject("schema mismatch")
    if data.get("package_version") != PACKAGE:
        reject("package version mismatch")
    if data.get("science_revision") != SCIENCE:
        reject("science revision mismatch")
    if data.get("canonical_authority") != "FORTRAN XSTAR 2.59g":
        reject("canonical authority mismatch")
    if data.get("decision") != "ACCEPT":
        reject("qualification decision is not ACCEPT")

    limit = float(data["acceptance_policy"]["public_material_normalized_l1_max"])
    r = data["results"]
    if not r["step"].get("formatted_rows_exact") or r["step"].get("ntotit") != [12, 6, 6]:
        reject("STEP/ntotit trajectory mismatch")

    checks = {
        "spect emitted inward": r["xout_spect1"]["emit_inward_normalized_l1"],
        "spect emitted outward": r["xout_spect1"]["emit_outward_normalized_l1"],
        "cont emitted inward": r["xout_cont1"]["emit_inward_normalized_l1"],
        "cont emitted outward": r["xout_cont1"]["emit_outward_normalized_l1"],
        "rrc emitted inward": r["xout_rrc1"]["emit_inward_normalized_l1"],
        "rrc emitted outward": r["xout_rrc1"]["emit_outward_normalized_l1"],
        "common-line emitted inward": r["xout_lines1"]["common_emit_inward_normalized_l1"],
        "common-line emitted outward": r["xout_lines1"]["common_emit_outward_normalized_l1"],
        "total heating": r["xout_abund1"]["total_heating_normalized_l1"],
        "total cooling": r["xout_abund1"]["total_cooling_normalized_l1"],
        "Mn heating": r["xout_abund1"]["manganese_heating_normalized_l1"],
        "Mn cooling": r["xout_abund1"]["manganese_cooling_normalized_l1"],
        "Mn ionic fractions": r["xout_abund1"]["manganese_max_ionic_fraction_normalized_l1"],
    }
    for label, value in checks.items():
        if float(value) >= limit:
            reject(f"{label} exceeds normalized-L1 limit: {value} >= {limit}")

    if r["xout_lines1"].get("common_line_indices") != 599:
        reject("common-line inventory changed")
    if r["xout_rrc1"].get("rows_cpp") != r["xout_rrc1"].get("rows_fortran"):
        reject("RRC row count mismatch")

    atdb = (ROOT / "src/xstar_tools/xstar/cpp/xstar_atdb_runtime.cpp").read_text(encoding="utf-8")
    engine = (ROOT / "src/xstar_tools/xstar/cpp/local_zone_engine.cpp").read_text(encoding="utf-8")
    header = (ROOT / "src/xstar_tools/xstar/cpp/xstar_local_zone_engine.h").read_text(encoding="utf-8")
    if "source_type49_skip" not in atdb or "h.nreal<=0" not in atdb:
        reject("Type-49 source early-exit lowering is absent")
    if "XSTAR_FIXED_OPCODE_SOURCE_SKIPPED" not in engine or "XSTAR_FIXED_OPCODE_SOURCE_SKIPPED = 201" not in header:
        reject("source-skipped execution opcode is absent")

    print(f"MN_TYPE49_SCIENCE_REFREEZE_PACKAGE={PACKAGE}")
    print(f"MN_TYPE49_SCIENCE_REFREEZE_SCIENCE_REVISION={SCIENCE}")
    print("MN_TYPE49_SCIENCE_REFREEZE_STEP=EXACT")
    print("MN_TYPE49_SCIENCE_REFREEZE_PUBLIC_MATERIAL=ACCEPT")
    print("MN_TYPE49_SCIENCE_REFREEZE_MN=ACCEPT")
    print("MN_TYPE49_SCIENCE_REFREEZE_RESULT=ACCEPT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
