from __future__ import annotations

import csv
import json
from pathlib import Path

from xstar_tools.xstar.he_bound_free_audit import audit, main


FIELDS = [
    "evaluation_ordinal", "source_position", "record", "element_z", "ion_stage", "data_type",
    "lower_row", "upper_row", "ans1", "ans2", "ans3", "ans4", "ans5", "ans6",
    "type53_shadow_valid", "type53_shadow_ans1", "type53_shadow_ans2",
    "type53_shadow_ans3", "type53_shadow_ans4", "type53_shadow_ans5", "type53_shadow_ans6",
    "type53_shadow_threshold_ev", "type53_shadow_rnist", "type53_shadow_nb1_one_based",
    "type53_shadow_klmax_one_based",
]


def _row(source_position: int, record: int, applied: float, shadow: float) -> dict[str, object]:
    row: dict[str, object] = {
        "evaluation_ordinal": 61,
        "source_position": source_position,
        "record": record,
        "element_z": 2,
        "ion_stage": 2,
        "data_type": 53,
        "lower_row": 1,
        "upper_row": 2,
        "type53_shadow_valid": 1,
        "type53_shadow_threshold_ev": 54.4,
        "type53_shadow_rnist": 1.0,
        "type53_shadow_nb1_one_based": 10,
        "type53_shadow_klmax_one_based": 20,
    }
    for index in range(1, 7):
        row[f"ans{index}"] = applied * index
        row[f"type53_shadow_ans{index}"] = shadow * index
    return row


def test_audit_reports_source_order_and_totals(tmp_path: Path) -> None:
    diagnostics = tmp_path / "diagnostics"
    diagnostics.mkdir()
    records = diagnostics / "evaluation_0061_records.csv"
    with records.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerow(_row(20, 2, 2.0, 5.0))
        writer.writerow(_row(10, 1, 1.0, 3.0))
    (diagnostics / "evaluation_0061_state.json").write_text(json.dumps({
        "computed_electron_fraction": 1.2,
        "charge_residual": 0.01,
        "record_diagnostic_count": 2,
        "element_diagnostic_count": 3,
    }), encoding="utf-8")

    report = audit(tmp_path, tmp_path / "audit", evaluation=61)
    assert report["records_compared"] == 2
    assert report["first_divergent_source_position"] == 10
    assert report["first_divergent_record"] == 1
    assert report["totals"]["ans1"]["applied"] == 3.0
    assert report["totals"]["ans1"]["shadow"] == 8.0
    assert report["source_shadow_applied_to_physics"] is False
    assert report["native_electron_fraction"] == 1.2
    rows = list(csv.DictReader((tmp_path / "audit/heii_type53_source_order_audit.csv").open()))
    assert [int(row["source_position"]) for row in rows] == [10, 20]


def test_cli_removes_stale_json_on_failure(tmp_path: Path) -> None:
    report = tmp_path / "stale.json"
    report.write_text("stale", encoding="utf-8")
    status = main(["audit", str(tmp_path / "missing"), str(tmp_path / "out"), "--output-json", str(report)])
    assert status == 2
    assert not report.exists()
