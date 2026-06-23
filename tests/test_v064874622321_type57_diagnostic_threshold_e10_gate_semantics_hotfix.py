from __future__ import annotations

import csv
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_type57_threshold_gate_uses_e10_and_distinct_valid_domains(tmp_path, monkeypatch):
    from xstar_tools.xstar import type57_diagnostic_threshold_e10_gate_semantics_hotfix_v04874622321 as focused

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
    native_rows = []
    source_rows = []
    for index in range(368):
        record = 40000 + index
        threshold = 1.0 + index / 1000.0
        diagnostic = math.nextafter(threshold, math.inf)
        assert threshold.hex() != diagnostic.hex()
        assert format(threshold, ".10e") == format(diagnostic, ".10e")
        case_rows.append({
            "element_index": 0,
            "data_type": 57,
            "record": record,
            "line_energy_ev": format(threshold, ".17g"),
        })
        native_rows.append({
            "element_z": 12,
            "data_type": 57,
            "record": record,
            "line_energy_ev": format(diagnostic, ".17g"),
        })
        if index < 342:
            source_rows.append({
                "sequence": 1,
                "element_z": 12,
                "data_type": 57,
                "record": record,
                "ans5": "1.0" if index < 3 else "0.0",
                "ans6": "0.0",
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
    gates = report["required_gates"]
    assert gates["MAGNESIUM_TYPE57_THRESHOLD_SOURCE_DOMAIN_EXACT"] == "ACCEPT"
    assert gates["MAGNESIUM_TYPE57_THRESHOLD_NATIVE_INVENTORY_EXACT"] == "ACCEPT"
    assert gates["MAGNESIUM_TYPE57_DIAGNOSTIC_THRESHOLD_IEEE_E10"] == "ACCEPT"
    assert gates["MAGNESIUM_TYPE57_ACTIVE_SOURCE_THRESHOLDS_POSITIVE"] == "ACCEPT"
    assert "MAGNESIUM_TYPE57_DIAGNOSTIC_THRESHOLD_BIT_EXACT" not in gates
    transport = report["magnesium_type57_threshold_transport"]
    assert transport["source_rows"] == 342
    assert transport["native_rows"] == 368
    assert transport["diagnostic_threshold_e10_mismatches"] == 0
    assert transport["bit_different_e10_equal"] == 368
    assert transport["nonpositive_active_threshold_rows"] == 0


def test_type57_threshold_e10_gate_rejects_visible_e10_difference(tmp_path, monkeypatch):
    from xstar_tools.xstar import type57_diagnostic_threshold_e10_gate_semantics_hotfix_v04874622321 as focused

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
        lambda *args, **kwargs: {"result": "ACCEPT", "required_gates": prior},
    )
    source = tmp_path / "source"
    case = tmp_path / "case"
    evaluations = tmp_path / "evaluations"
    _write_csv(case / "elements.csv", ["element_index", "element_z"], [
        {"element_index": 0, "element_z": 12},
    ])
    case_rows = []
    native_rows = []
    source_rows = []
    for index in range(368):
        record = 50000 + index
        threshold = 1.0 + index / 1000.0
        diagnostic = threshold + (1.0e-5 if index == 0 else 0.0)
        case_rows.append({"element_index": 0, "data_type": 57, "record": record, "line_energy_ev": threshold})
        native_rows.append({"element_z": 12, "data_type": 57, "record": record, "line_energy_ev": diagnostic})
        if index < 342:
            source_rows.append({"sequence": 1, "element_z": 12, "data_type": 57, "record": record, "ans5": 0.0, "ans6": 0.0})
    _write_csv(case / "records.csv", ["element_index", "data_type", "record", "line_energy_ev"], case_rows)
    _write_csv(source / "v0472_all61_thermal_answer_channels.csv", ["sequence", "element_z", "data_type", "record", "ans5", "ans6"], source_rows)
    _write_csv(evaluations / "evaluation_0001" / "qualification_diagnostics" / "evaluation_0001_records.csv", ["element_z", "data_type", "record", "line_energy_ev"], native_rows)
    report = focused.audit(source, evaluations, case, None, None, None, tmp_path / "differences.csv", (1,))
    assert report["required_gates"]["MAGNESIUM_TYPE57_DIAGNOSTIC_THRESHOLD_IEEE_E10"] == "REJECT"
    assert report["magnesium_type57_threshold_transport"]["diagnostic_threshold_e10_mismatches"] == 1


def test_hotfix_runner_uses_fresh_replay_and_e10_analyzer():
    text = (ROOT / "run_v04874622321_type57_diagnostic_threshold_e10_gate_semantics_hotfix.sh").read_text()
    assert ".v04874622321_run_lock" in text
    assert ".native_case_v04874622321.$$.tmp" in text
    assert "run_v04874622321_native_fixed_replay.sh" in text
    assert "type57_diagnostic_threshold_e10_gate_semantics_hotfix_v04874622321" in text
