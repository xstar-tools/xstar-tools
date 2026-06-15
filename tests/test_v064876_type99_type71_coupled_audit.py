from __future__ import annotations

import csv
import json
from pathlib import Path

import xstar_tools
from xstar_tools.xstar.type99_type71_coupled_audit import (
    RELEASE,
    TARGET_RECORD,
    TARGET_SOURCE_POSITION,
    answer_sign_contract,
    matrix_terms,
    scenario_selector,
)
from xstar_tools.xstar.v0472_type99_runtime_capture import ORACLE_NAME, verify

ROOT = Path(__file__).resolve().parents[1]


def test_release_and_target_are_pinned() -> None:
    assert xstar_tools.__version__ == "0.6.48.7.36"
    assert RELEASE == "0.6.48.7.13"
    assert TARGET_RECORD == 1695
    assert TARGET_SOURCE_POSITION == 6312


def test_bundled_type99_oracle_is_complete_and_source_signed() -> None:
    bundle = ROOT / "src/xstar_tools/benchmarks/v064876_type99_record1695_runtime_oracle_v0472"
    report = verify(bundle)
    assert report["result"] == "ACCEPT"
    rows = list(csv.DictReader((bundle / ORACLE_NAME).open()))
    assert len(rows) == 1
    row = rows[0]
    assert int(row["record"]) == 1695
    assert int(row["source_position"]) == 6312
    answers = tuple(float(row[f"ans{i}"]) for i in range(1, 7))
    assert answer_sign_contract(answers)
    assert answers[0] == 104.14911901939827
    assert answers[1] == 9.817240995458149e-06
    assert answers[4] < 0.0 and answers[5] < 0.0


def test_matrix_term_mapping_preserves_source_signs() -> None:
    answers = (104.0, 2.0, -3.0, -5.0, -7.0, -11.0)
    terms = matrix_terms("reference", answers)
    assert [row["role"] for row in terms] == [
        "forward_gain", "reverse_gain", "forward_diag_loss", "reverse_diag_loss"
    ]
    assert terms[2]["cj"] == -5.0
    assert terms[2]["cj2"] == -11.0
    assert terms[3]["cj"] == 3.0
    assert terms[3]["cj2"] == 7.0


def test_type71_group_selectors_partition_the_family() -> None:
    records = []
    source = 100
    for upper, count in ((44, 15), (45, 28), (77, 31)):
        for _ in range(count):
            records.append({
                "element_index": "1", "data_type": "71", "upper_row": str(upper),
                "source_position": str(source), "matrix_enabled": "1",
            })
            source += 4
    records.extend([
        {"element_index": "1", "data_type": "99", "upper_row": "78", "source_position": "6312", "matrix_enabled": "1"},
        {"element_index": "1", "data_type": "99", "upper_row": "46", "source_position": "2784", "matrix_enabled": "1"},
        {"element_index": "1", "data_type": "99", "upper_row": "46", "source_position": "2788", "matrix_enabled": "1"},
    ])
    expected = {
        "type71_all": 74, "type71_upper44": 15, "type71_upper45": 28,
        "type71_upper77": 31, "type99_all": 3, "type99_plus_type71_all": 77,
        "type99_plus_type71_upper77": 34, "source6312_plus_type71_upper77": 32,
    }
    for name, count in expected.items():
        _, positions = scenario_selector(name, records)
        assert len(positions) == count


def test_release_scripts_exist() -> None:
    assert (ROOT / "run_v04876_type99_type71_coupled_audit.sh").is_file()
    assert (ROOT / "check_v04876_type99_type71_coupled_audit.py").is_file()
