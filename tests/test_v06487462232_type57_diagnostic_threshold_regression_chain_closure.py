from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXED = ROOT / "src/xstar_tools/xstar/cpp/fixed_state_engine.cpp"


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_evaluated_record_exports_serialized_metadata_before_opcode_switch():
    text = FIXED.read_text()
    function = text.split("EvaluatedRecord evaluate_record(", 1)[1]
    prefix = function.split("switch (record.opcode)", 1)[0]
    assert "out.line_energy_ev = record.line_energy_ev;" in prefix
    assert "out.atomic_mass_amu = record.atomic_mass_amu;" in prefix
    assert "out.natural_width_ev = record.natural_width_ev;" in prefix


def test_historical_analyzer_release_identities_are_immutable():
    base = ROOT / "src/xstar_tools/xstar"
    expected = {
        "magnesium_type57_thermal_closure_v048746220.py": "0.6.48.7.46.21.10",
        "magnesium_type53_leveltemp_closure_v048746221.py": "0.6.48.7.46.21.11",
        "magnesium_type49_leveltemp_closure_v048746222.py": "0.6.48.7.46.21.12",
        "magnesium_type99_leveltemp_closure_v048746223.py": "0.6.48.7.46.21.13",
    }
    for filename, release in expected.items():
        assert f'RELEASE = "{release}"' in (base / filename).read_text()


def test_threshold_audit_closes_named_regression_chain(tmp_path, monkeypatch):
    from xstar_tools.xstar import type57_diagnostic_threshold_regression_chain_closure_v0487462232 as focused

    prior = {
        "V21_11_TYPE53_TYPE57_AND_V21_9_REGRESSION": "ACCEPT",
        "V21_12_TYPE49_REGRESSION": "ACCEPT",
        "V21_13_TYPE99_AND_PRIOR_REGRESSION": "ACCEPT",
        "MAGNESIUM_TYPE68_SOURCE_DOMAIN_EXACT": "ACCEPT",
        "MAGNESIUM_TYPE68_NATIVE_INVENTORY_EXACT": "ACCEPT",
        "MAGNESIUM_TYPE68_ANS5_ANS6_IEEE_E10": "ACCEPT",
        "MAGNESIUM_COOLING2_ALL_SELECTED_IEEE_E10": "ACCEPT",
    }
    monkeypatch.setattr(
        focused.v2231,
        "audit",
        lambda *args, **kwargs: {
            "result": "ACCEPT",
            "required_gates": prior,
            "residual_family_attribution": {"result": "ACCEPT", "families": {}},
            "canonical": {"result": "REJECT"},
        },
    )

    source = tmp_path / "source"
    case = tmp_path / "case"
    evaluations = tmp_path / "evaluations"
    _write_csv(case / "elements.csv", ["element_index", "element_z"], [
        {"element_index": 0, "element_z": 12},
    ])
    case_rows = []
    source_rows = []
    native_rows = []
    for index in range(368):
        record = 40000 + index
        threshold = 1.0 + index / 1000.0
        case_rows.append({
            "element_index": 0,
            "data_type": 57,
            "record": record,
            "line_energy_ev": format(threshold, ".17g"),
        })
        source_rows.append({
            "sequence": 1,
            "element_z": 12,
            "data_type": 57,
            "record": record,
            "ans5": "1.0" if index == 0 else "0.0",
            "ans6": "0.0",
        })
        native_rows.append({
            "element_z": 12,
            "data_type": 57,
            "record": record,
            "line_energy_ev": format(threshold, ".17g"),
        })
    _write_csv(
        case / "records.csv",
        ["element_index", "data_type", "record", "line_energy_ev"],
        case_rows,
    )
    _write_csv(
        source / "v0472_all61_thermal_answer_channels.csv",
        ["sequence", "element_z", "data_type", "record", "ans5", "ans6"],
        source_rows,
    )
    _write_csv(
        evaluations / "evaluation_0001" / "qualification_diagnostics" / "evaluation_0001_records.csv",
        ["element_z", "data_type", "record", "line_energy_ev"],
        native_rows,
    )

    report = focused.audit(
        source,
        evaluations,
        case,
        None,
        None,
        None,
        tmp_path / "differences.csv",
        (1,),
    )
    assert report["result"] == "ACCEPT"
    assert all(value == "ACCEPT" for value in report["required_gates"].values())
    transport = report["magnesium_type57_threshold_transport"]
    assert transport["serialized_records"] == 368
    assert transport["diagnostic_threshold_mismatches"] == 0
    assert transport["nonpositive_active_threshold_rows"] == 0


def test_runner_requires_fresh_replay_and_new_analyzer():
    text = (ROOT / "run_v0487462232_type57_diagnostic_threshold_regression_chain_closure.sh").read_text()
    assert ".v0487462232_run_lock" in text
    assert ".native_case_v0487462232.$$.tmp" in text
    assert "run_v0487462232_native_fixed_replay.sh" in text
    assert "type57_diagnostic_threshold_regression_chain_closure_v0487462232" in text
