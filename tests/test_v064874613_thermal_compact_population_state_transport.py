from __future__ import annotations

import csv
import json
import struct
from pathlib import Path

import xstar_tools
from xstar_tools.xstar import thermal_compact_population_closure as compact

ROOT = Path(__file__).resolve().parents[1]


def _row(sequence: int, z: int, index: int, count: int, min_stage: int, max_stage: int) -> dict[str, object]:
    stage = max_stage if index == count else min_stage
    value = sequence * 1e-6 + z * 1e-9 + index * 1e-13
    return {
        "sequence": sequence,
        "kind": "dsec" if sequence <= 57 else "final",
        "call_index": sequence if sequence <= 57 else 0,
        "evaluation_index": sequence,
        "element_z": z,
        "abundance": "1",
        "active_min_stage": min_stage,
        "active_max_stage": max_stage,
        "compact_row": index,
        "ion": stage,
        "ion_stage": stage,
        "ion_charge": stage - 1,
        "superlevel": 1 if index == 1 else 2,
        "is_normalization_row": int(index == count),
        "final_population": format(value, ".17g"),
        "final_population_ieee_hex": struct.pack(">d", value).hex(),
    }


def _synthetic_inventory() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for sequence in range(1, 62):
        rows.extend(_row(sequence, 1, i, 33, 1, 1) for i in range(1, 34))
        rows.extend(_row(sequence, 2, i, 78, 1, 2) for i in range(1, 79))
        mg_count = 501 if sequence <= 4 else 507 if sequence <= 6 else 552
        rows.extend(_row(sequence, 12, i, mg_count, 5, 12) for i in range(1, mg_count + 1))
    return rows


def test_release_version_and_abi_are_stable() -> None:
    assert xstar_tools.__version__ == "0.6.48.7.46.19.1"
    api = (ROOT / "src/xstar_tools/xstar/cpp/xstar_api.h").read_text()
    assert "60487" in api


def test_compact_inventory_contract_is_exact() -> None:
    rows = _synthetic_inventory()
    assert len(rows) == 40149
    assert compact._validate_inventory(rows) == []
    assert sum(int(row["element_z"]) == 1 for row in rows) == 2013
    assert sum(int(row["element_z"]) == 2 for row in rows) == 4758
    assert sum(int(row["element_z"]) == 12 for row in rows) == 33378


def test_prepare_and_audit_roundtrip(tmp_path: Path) -> None:
    capture = tmp_path / "capture"
    closure = tmp_path / "closure"
    native = tmp_path / "native"
    output = tmp_path / "audit"
    capture.mkdir()
    fieldnames = [
        "sequence", "kind", "dsec_call_id", "evaluation_index", "element_z", "abundance",
        "active_min_stage", "active_max_stage", "compact_row", "ion", "ion_stage",
        "ion_charge", "superlevel", "is_normalization_row", "final_population",
    ]
    with (capture / compact.SOURCE_ROWS_NAME).open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in _synthetic_inventory():
            source = dict(row)
            source["dsec_call_id"] = source.pop("call_index")
            source.pop("final_population_ieee_hex")
            writer.writerow(source)
    report = compact.prepare(capture, closure)
    assert report["result"] == "ACCEPT"
    native.mkdir()
    rows: list[dict[str, str]] = []
    for sequence in range(1, 62):
        rows.extend(list(csv.DictReader((closure / f"sequence_{sequence:04d}_thermal_compact_populations.csv").open())))
    with (native / compact.NATIVE_AGGREGATE_NAME).open("w", newline="") as handle:
        fieldnames_native = [
            "sequence", "kind", "call_index", "evaluation_index", "element_z", "active_min_stage",
            "active_max_stage", "compact_row", "ion", "ion_stage", "ion_charge", "superlevel",
            "is_normalization_row", "thermal_population", "closure_applied",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames_native, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            row = dict(row)
            row["thermal_population"] = row["final_population"]
            row["closure_applied"] = "1"
            writer.writerow(row)
    audited = compact.audit(closure, native, output)
    assert audited["result"] == "ACCEPT"
    assert audited["population_values_exact"] == 40149
    assert audited["population_fingerprints_exact"] == 61


def test_native_transport_contract_is_present() -> None:
    cpp = (ROOT / "src/xstar_tools/xstar/cpp/fixed_state_engine.cpp").read_text()
    standalone = (ROOT / "src/xstar_tools/xstar/cpp/xstar_standalone.cpp").read_text()
    assert "XSTAR_QUALIFICATION_THERMAL_COMPACT_POPULATION_CLOSURE" in cpp
    assert "thermal_compact_population_values_for_element" in cpp
    assert "thermal_consumed_compact_population_closure" in cpp
    assert "native_thermal_compact_populations.csv" in standalone


def test_runner_and_checker_gate_compact_transport() -> None:
    runner = (ROOT / "run_v04874613_thermal_compact_population_state_transport.sh").read_text()
    checker = (ROOT / "check_v04874613_thermal_compact_population_state_transport.py").read_text()
    assert "--compact-closure" in runner
    assert "--require-compact-populations" in runner
    assert "XSTAR_QUALIFICATION_THERMAL_COMPACT_POPULATION_CLOSURE_DIR" in runner
    assert "THERMAL_COMPACT_POPULATION_VALUES_EXACT_40149" in checker
    assert "FULL_LEVEL_FIXED_STATE_PRODUCT_UNCHANGED_41968" in checker
