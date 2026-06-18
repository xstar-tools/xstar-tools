from __future__ import annotations
from pathlib import Path
import xstar_tools
from xstar_tools.xstar import type53_semantics

ROOT = Path(__file__).resolve().parents[1]


def test_release_and_type53_ieee_contract_are_pinned() -> None:
    assert xstar_tools.__version__ == "0.6.48.7.46.12"
    assert type53_semantics.RELEASE == "0.6.48.7.13"
    source = (ROOT / "src/xstar_tools/xstar/cpp/fixed_state_engine.cpp").read_text()
    assert "constexpr double kType53RydEv = 13.605692;" in source
    assert "std::max(-60.0, std::min(60.0, x))" in source
    assert "element.element_z == 2" in source
    assert "record_context.valid || record.ion_stage == 2" in source


def test_qualification_scripts_are_path_hardened() -> None:
    runner = (ROOT / "run_v04874_type53_ieee_application.sh").read_text()
    checker = (ROOT / "check_v04874_type53_ieee_application.py").read_text()
    assert "v06486_qualification_reference_v0472" in runner
    assert "v0648_compiled_case_helike_type69_mg11_ne1e8" in runner
    assert "RADIATION_SHA" in checker
    assert '"--audit-output"' in checker
