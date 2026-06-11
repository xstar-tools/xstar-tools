from __future__ import annotations

import csv
import json
from pathlib import Path

from xstar_tools.xstar.type53_semantics import analyze, export_reference_template, freeze_reference, main, verify_reference

FIELDS = [
    "evaluation_ordinal", "source_position", "record", "element_z", "ion_stage", "data_type",
    "lower_row", "upper_row", "density_scale", "ans1", "ans2", "ans3", "ans4", "ans5", "ans6",
    "type53_shadow_valid", "type53_shadow_ans1", "type53_shadow_ans2", "type53_shadow_ans3",
    "type53_shadow_ans4", "type53_shadow_ans5", "type53_shadow_ans6",
]


def _record(position: int, record: int) -> dict[str, object]:
    return {
        "evaluation_ordinal": 61, "source_position": position, "record": record,
        "element_z": 2, "ion_stage": 2, "data_type": 53, "lower_row": 4, "upper_row": 8,
        "density_scale": 3.0,
        "ans1": 2.0, "ans2": 1.0, "ans3": -4.0, "ans4": -5.0, "ans5": 4.0, "ans6": 5.0,
        "type53_shadow_valid": 1,
        "type53_shadow_ans1": 3.0, "type53_shadow_ans2": 1.5,
        "type53_shadow_ans3": -6.0, "type53_shadow_ans4": -7.0,
        "type53_shadow_ans5": -8.0, "type53_shadow_ans6": -9.0,
    }


def _write_records(path: Path, count: int = 31) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for index in range(count):
            writer.writerow(_record(100 + index * 4, 1000 + index))


def test_semantics_and_matrix_terms_without_runtime_oracle(tmp_path: Path) -> None:
    records = tmp_path / "diagnostics/evaluation_0061_records.csv"
    _write_records(records)
    report = analyze(tmp_path, tmp_path / "out")
    assert report["records_compared"] == 31
    assert report["matrix_terms_written"] == 31 * 2 * 4
    assert report["reference_ans_semantics_known"] is True
    assert report["shadow_source_sign_semantics_consistent"] is True
    assert report["applied_source_sign_semantics_consistent"] is False
    assert report["reference_runtime_oracle_complete"] is False
    assert report["type53_physics_replacement_ready"] is False
    terms = list(csv.DictReader((tmp_path / "out/heii_type53_matrix_terms.csv").open()))
    reverse = next(row for row in terms if row["variant"] == "shadow" and row["role"] == "reverse_diag_loss")
    assert float(reverse["cj2"]) == 24.0  # -ans5 * density
    forward = next(row for row in terms if row["variant"] == "shadow" and row["role"] == "forward_diag_loss")
    assert float(forward["cj2"]) == -27.0  # ans6 * density


def test_freeze_verify_and_exact_shadow_control(tmp_path: Path) -> None:
    records = tmp_path / "diagnostics/evaluation_0061_records.csv"
    _write_records(records)
    oracle_csv = tmp_path / "oracle.csv"
    fields = [
        "evaluation_ordinal", "source_position", "record", "element_z", "ion_stage", "data_type",
        "lower_row", "upper_row", "ans1", "ans2", "ans3", "ans4", "ans5", "ans6",
    ]
    with oracle_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for index in range(31):
            row = _record(100 + index * 4, 1000 + index)
            writer.writerow({
                "evaluation_ordinal": 61, "source_position": row["source_position"], "record": row["record"],
                "element_z": 2, "ion_stage": 2, "data_type": 53, "lower_row": 4, "upper_row": 8,
                **{f"ans{i}": row[f"type53_shadow_ans{i}"] for i in range(1, 7)},
            })
    bundle = tmp_path / "bundle"
    frozen = freeze_reference(oracle_csv, bundle, source_archive_sha256="abc")
    assert frozen["records"] == 31
    assert verify_reference(bundle)["result"] == "ACCEPT"
    report = analyze(tmp_path, tmp_path / "out", reference_oracle=bundle)
    assert report["reference_runtime_oracle_complete"] is True
    assert report["shadow_exact_to_reference"] is True
    assert report["applied_exact_to_reference"] is False
    assert report["type53_physics_replacement_ready"] is False
    assert report["matrix_terms_written"] == 31 * 3 * 4


def test_cli_removes_stale_json_on_failure(tmp_path: Path) -> None:
    stale = tmp_path / "stale.json"
    stale.write_text(json.dumps({"old": True}), encoding="utf-8")
    status = main(["analyze", str(tmp_path / "missing"), str(tmp_path / "out"), "--output-json", str(stale)])
    assert status == 2
    assert not stale.exists()


def test_reference_template_cannot_be_frozen(tmp_path: Path) -> None:
    records = tmp_path / "diagnostics/evaluation_0061_records.csv"
    _write_records(records)
    template = tmp_path / "template.csv"
    report = export_reference_template(tmp_path, template)
    assert report["records"] == 31
    assert report["runtime_values_present"] is False
    try:
        freeze_reference(template, tmp_path / "bad_bundle")
    except ValueError as exc:
        assert "finite" in str(exc)
    else:
        raise AssertionError("blank runtime template was incorrectly accepted as an oracle")


def test_exact_applied_and_shadow_enable_qualified_replacement(tmp_path: Path) -> None:
    records = tmp_path / "diagnostics/evaluation_0061_records.csv"
    _write_records(records)
    rows = list(csv.DictReader(records.open()))
    for row in rows:
        for i in range(1, 7):
            row[f"ans{i}"] = row[f"type53_shadow_ans{i}"]
    with records.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader(); writer.writerows(rows)
    oracle_csv = tmp_path / "oracle.csv"
    fields = [
        "evaluation_ordinal", "source_position", "record", "element_z", "ion_stage", "data_type",
        "lower_row", "upper_row", "ans1", "ans2", "ans3", "ans4", "ans5", "ans6",
    ]
    with oracle_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader()
        for row in rows:
            writer.writerow({
                "evaluation_ordinal": 61, "source_position": row["source_position"], "record": row["record"],
                "element_z": 2, "ion_stage": 2, "data_type": 53, "lower_row": 4, "upper_row": 8,
                **{f"ans{i}": row[f"type53_shadow_ans{i}"] for i in range(1, 7)},
            })
    bundle = tmp_path / "bundle"
    freeze_reference(oracle_csv, bundle)
    report = analyze(tmp_path, tmp_path / "out", reference_oracle=bundle)
    assert report["applied_exact_to_reference"] is True
    assert report["shadow_exact_to_reference"] is True
    assert report["applied_source_sign_semantics_consistent"] is True
    assert report["first_reference_divergence"] is None
    assert report["type53_physics_replacement_ready"] is True
    assert report["full_type53_family_promotion_ready"] is False
