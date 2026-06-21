from __future__ import annotations

import csv
from pathlib import Path

import xstar_tools
from xstar_tools.xstar.helium_family_isolation import (
    MATRIX_FAMILIES,
    PRELIMINARY_FAMILY,
    RELEASE,
    term_rows,
)

ROOT = Path(__file__).resolve().parents[1]


def test_release_and_family_scope_are_pinned() -> None:
    assert xstar_tools.__version__ == "0.6.48.7.46.21.4"
    assert RELEASE == "0.6.48.7.13"
    assert MATRIX_FAMILIES == (50, 54, 56, 57, 63, 69, 71, 74, 76, 77, 95, 99)
    assert PRELIMINARY_FAMILY == 30


def test_matrix_ledger_expands_four_terms() -> None:
    row = {
        "evaluation_ordinal": "61", "source_position": "100", "record": "20",
        "element_z": "2", "data_type": "99", "matrix_committed": "1",
        "lower_row": "2", "upper_row": "3", "ion_stage": "2",
        "ans1": "5", "ans2": "7", "ans3": "-11", "ans4": "-13",
        "ans5": "-17", "ans6": "-19", "density_scale": "2",
    }
    terms = term_rows([row], {2: 0.25, 3: 0.75})
    assert [term["role"] for term in terms] == [
        "forward_gain", "reverse_gain", "forward_diag_loss", "reverse_diag_loss"
    ]
    assert [term["term_source_position"] for term in terms] == [100, 101, 102, 103]
    assert terms[0]["row_residual_contribution"] == 1.25
    assert terms[1]["row_residual_contribution"] == 5.25
    assert terms[2]["row_residual_contribution"] == -1.25
    assert terms[3]["row_residual_contribution"] == -5.25
    assert terms[2]["heating_matrix_contribution"] == -6.5
    assert terms[3]["heating2_matrix_contribution"] == 25.5


def test_cpp_ablation_is_explicitly_qualification_gated() -> None:
    source = (ROOT / "src/xstar_tools/xstar/cpp/fixed_state_engine.cpp").read_text()
    assert "XSTAR_QUALIFICATION_ABLATION" in source
    assert "XSTAR_HELIUM_ABLATE_MATRIX_TYPE" in source
    assert "XSTAR_HELIUM_ABLATE_PRELIMINARY_TYPE" in source
    assert "XSTAR_HELIUM_ABLATE_SOURCE_POSITION" in source
    assert "helium ablation requires XSTAR_QUALIFICATION_ABLATION=1" in source


def test_release_scripts_exist() -> None:
    assert (ROOT / "run_v04875_helium_family_isolation.sh").is_file()
    assert (ROOT / "check_v04875_helium_family_isolation.py").is_file()
