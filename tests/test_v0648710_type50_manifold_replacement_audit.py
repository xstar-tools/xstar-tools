from __future__ import annotations

import csv
import hashlib
from pathlib import Path

from xstar_tools.xstar.type50_manifold_replacement_audit import (
    RELEASE,
    TYPE50_ORACLE_NAME,
    TYPE50_ORACLE_SHA256,
    TYPE50_BUNDLE,
    WHOLE_STATE_METRICS,
)

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_type50_oracle_and_static_table_are_complete() -> None:
    oracle = ROOT / TYPE50_BUNDLE / TYPE50_ORACLE_NAME
    assert digest(oracle) == TYPE50_ORACLE_SHA256
    with oracle.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 79
    assert len({(r["source_position"], r["record"]) for r in rows}) == 79
    header = (ROOT / "src/xstar_tools/xstar/cpp/type50_manifold_oracle_v048710.h").read_text()
    assert "std::array<Entry, 79>" in header
    assert header.count("Entry{") == 79
    assert TYPE50_ORACLE_SHA256 in header


def test_replacement_is_qualification_only_and_fail_closed() -> None:
    cpp = (ROOT / "src/xstar_tools/xstar/cpp/fixed_state_engine.cpp").read_text()
    assert 'environment_flag("XSTAR_QUALIFICATION_TYPE50_MANIFOLD_ORACLE")' in cpp
    assert 'environment_flag("XSTAR_QUALIFICATION_REPLACEMENT")' in cpp
    assert "restricted to the evaluation-61 fixed state" in cpp
    assert "type50 manifold oracle identity mismatch" in cpp


def test_release_and_whole_state_gate() -> None:
    assert RELEASE == "0.6.48.7.12"
    assert WHOLE_STATE_METRICS == (
        "electron_fraction",
        "charge_residual",
        "he1_final_fraction",
        "he2_final_fraction",
        "he3_final_fraction",
        "hmctot",
    )
