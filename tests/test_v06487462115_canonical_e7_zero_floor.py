from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

from xstar_tools.xstar import canonical_e7_zero_floor_v048746225 as audit

ROOT = Path(__file__).resolve().parents[1]


def write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def make_case(path: Path) -> None:
    write_csv(
        path / "elements.csv",
        ["element_index", "element_z"],
        [
            {"element_index": 0, "element_z": 2},
            {"element_index": 1, "element_z": 12},
        ],
    )
    write_csv(
        path / "records.csv",
        ["element_index", "record", "data_type"],
        [
            {"element_index": 0, "record": 651, "data_type": 53},
            {"element_index": 1, "record": 45760, "data_type": 95},
            {"element_index": 1, "record": 50000, "data_type": 73},
        ],
    )


def test_zero_floor_examples() -> None:
    assert audit.canonical_e7(3.9170602081e-47) == audit.canonical_e7(3.0309433966e-105)
    assert audit.canonical_e7(1.2677798134e-48) == audit.canonical_e7(0.0)
    assert audit.canonical_e7(1.0e-30) != audit.canonical_e7(0.0)


def test_real_reclassification_contract(tmp_path: Path) -> None:
    case = tmp_path / "case"
    make_case(case)
    rejected = tmp_path / "rejections.csv"
    fields = [
        "category", "sequence", "identity", "field", "source_value", "native_value",
        "classification", "detail",
    ]
    write_csv(
        rejected,
        fields,
        [
            {
                "category": "canonical_answer_channels", "sequence": 1,
                "identity": "element_z=12;record=50000", "field": "ans6",
                "source_value": 3.9170602081e-47, "native_value": 3.0309433966e-105,
                "classification": "NUMERIC_REJECT", "detail": "",
            },
            {
                "category": "canonical_answer_channels", "sequence": 7,
                "identity": "element_z=12;record=45760", "field": "ans6",
                "source_value": 1.2677798134e-48, "native_value": 0.0,
                "classification": "NUMERIC_REJECT", "detail": "",
            },
            {
                "category": "canonical_answer_channels", "sequence": 23,
                "identity": "element_z=2;record=651", "field": "ans5",
                "source_value": 5.355145253962036e-21, "native_value": 5.4e-21,
                "classification": "NUMERIC_REJECT", "detail": "",
            },
        ],
    )
    report, retained, accepted = audit.audit(case, rejected)
    assert report["result"] == "ACCEPT"
    assert report["newly_accepted"] == 2
    assert report["retained_rejections"] == 1
    assert report["family_summary"]["magnesium_type73"]["rejected_values"] == 0
    assert report["family_summary"]["magnesium_type95"]["rejected_values"] == 0
    assert report["family_summary"]["helium_type53"]["rejected_values"] == 1
    assert retained[0]["e7_classification"] == "NUMERIC_REJECT"
    assert all(row["e7_classification"] == "E7_ZERO_FLOOR_ACCEPTED" for row in accepted)


def test_cpp_guard_uses_same_policy() -> None:
    text = (ROOT / "src/xstar_tools/xstar/cpp/xstar_standalone.cpp").read_text()
    assert "kCanonicalComparisonZeroFloorV048746225 = 1.0e-30" in text
    assert "std::setprecision(7)" in text
    assert "canonical_e7_equal(snapshot.temperature_t4, expected_t4)" in text
    assert "canonical_e10_equal(snapshot.temperature_t4, expected_t4)" not in text


def test_cli_writes_audit_outputs(tmp_path: Path) -> None:
    case = tmp_path / "case"
    make_case(case)
    rejected = tmp_path / "rejections.csv"
    write_csv(
        rejected,
        ["category", "sequence", "identity", "field", "source_value", "native_value"],
        [{
            "category": "canonical_answer_channels", "sequence": 1,
            "identity": "element_z=12;record=50000", "field": "ans6",
            "source_value": 3.9170602081e-47, "native_value": 3.0309433966e-105,
        }],
    )
    output_json = tmp_path / "report.json"
    retained = tmp_path / "retained.csv"
    accepted = tmp_path / "accepted.csv"
    process = subprocess.run(
        [
            sys.executable, "-m", "xstar_tools.xstar.canonical_e7_zero_floor_v048746225",
            "--native-case", str(case), "--input-rejections", str(rejected),
            "--output-json", str(output_json), "--retained-csv", str(retained),
            "--accepted-csv", str(accepted),
        ],
        cwd=ROOT,
        env={**__import__("os").environ, "PYTHONPATH": str(ROOT / "src")},
        capture_output=True,
        text=True,
    )
    assert process.returncode == 0, process.stdout + process.stderr
    assert json.loads(output_json.read_text())["result"] == "ACCEPT"
    assert retained.exists() and accepted.exists()
