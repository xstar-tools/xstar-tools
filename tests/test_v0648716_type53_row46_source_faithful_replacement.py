from pathlib import Path

import xstar_tools
from xstar_tools.xstar.type53_row46_dsec_runtime_contract_audit import BUNDLE
from xstar_tools.xstar.type53_row46_source_faithful_replacement_audit import (
    RELEASE,
    SCHEMA,
    TARGET_ANSWERS,
    TARGET_RECORDS,
    TARGET_TERMS,
    verify_oracle,
)


def root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_release_version() -> None:
    assert xstar_tools.__version__ == "0.6.48.7.43"
    assert RELEASE == "0.6.48.7.21.4"
    assert SCHEMA.endswith("source-faithful-replacement-audit-v1")


def test_frozen_oracle_inventory() -> None:
    result = verify_oracle(root() / BUNDLE)
    assert result["result"] == "ACCEPT"
    assert result["records"] == TARGET_RECORDS == 44
    assert result["answers"] == TARGET_ANSWERS == 264
    assert result["matrix_terms"] == TARGET_TERMS == 176


def test_cpp_oracle_header_has_complete_manifold() -> None:
    text = (root() / "src/xstar_tools/xstar/cpp/type53_row46_dsec_runtime_oracle_v048716.h").read_text()
    assert "std::array<Entry, 44>" in text
    assert text.count("Entry{") == 44


def test_cpp_gate_and_live_branch_are_present() -> None:
    text = (root() / "src/xstar_tools/xstar/cpp/fixed_state_engine.cpp").read_text()
    assert "XSTAR_QUALIFICATION_TYPE53_ROW46_COUPLED_REPLACEMENT" in text
    assert "captured_state_anchor" in text
    assert "contract_ptmp1" in text and "contract_ptmp2" in text
    assert "reorder_type53_row46_coupled_contributions" in text


def test_checker_blocks_general_state_promotion() -> None:
    text = (root() / "check_v048716_type53_row46_source_faithful_replacement_audit.py").read_text()
    assert "ARBITRARY_STATE_CONTRACT_INTERFACE=ACCEPT" in text
    assert "ARBITRARY_STATE_PARITY=BLOCKED" in text
    assert "PRODUCTION_PROMOTION=BLOCKED" in text
