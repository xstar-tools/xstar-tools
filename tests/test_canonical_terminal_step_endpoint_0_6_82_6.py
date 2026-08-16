from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools/qualification/check_canonical_terminal_step_endpoint_0_6_82_6.py"
RUNNER = ROOT / "tools/qualification/run_c5_terminal_step_host_smoke_0_6_82_6.py"
REFERENCE = ROOT / "qualification/c5_terminal_step_0_6_82_6/reference_step_rows.json"


def test_06826_checker_accepts():
    proc = subprocess.run([sys.executable, str(CHECKER)], cwd=ROOT, text=True, capture_output=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "CANONICAL_TERMINAL_STEP_06826_RESULT=ACCEPT" in proc.stdout


def test_06826_source_owns_postloop_endpoint_as_physical_step_row():
    standalone = (ROOT / "src/xstar_tools/xstar/cpp/xstar_standalone.cpp").read_text(encoding="utf-8")
    step = (ROOT / "src/xstar_tools/xstar/cpp/xstar_step_log.cpp").read_text(encoding="utf-8")
    assert "const std::size_t radial_event_count = finals.size() + 1u;" in standalone
    assert "whole.physical_radial_boundaries_expected = radial_event_count;" in standalone
    assert "whole.physical_radial_boundaries_retained = whole.radial_zones.size();" in standalone
    assert "qualification_free_native_terminal_posttransport" in standalone
    assert "Canonical xstar.f90 executes `pprint(9,...)` once more after the" in standalone
    assert "print_xstar_style_live_zone(" in standalone
    assert "complete physical pprint(9) trajectory" in step
    assert "const std::size_t output_rows = rows.size();" in step


def test_06826_zero_thickness_final_evaluation_stays_outside_radial_zones():
    standalone = (ROOT / "src/xstar_tools/xstar/cpp/xstar_standalone.cpp").read_text(encoding="utf-8")
    post = standalone.index("qualification_free_native_terminal_posttransport")
    zero = standalone.index("final_zero_thickness_started_v064890", post)
    assert post < zero
    zero_block = standalone[zero: zero + 12000]
    assert "legacy_pprint.final_zero_thickness_evaluation_present" in zero_block
    assert "append_zone(" not in zero_block


def test_06826_c5_reference_contains_terminal_column_endpoint():
    doc = json.loads(REFERENCE.read_text(encoding="utf-8"))
    expected_counts = {
        "c5_ne1": 5,
        "c5_ne1e4": 5,
        "c5_ne1e8": 5,
        "c5_ne1e10": 7,
        "c5_ne1e12": 6,
    }
    assert set(doc["models"]) == set(expected_counts)
    for model, count in expected_counts.items():
        rows = doc["models"][model]["rows"]
        assert len(rows) == count
        assert rows[-1][2] == 20.0  # log(N)
        assert rows[-1][-1] == rows[-2][-1]  # no new DSEC call at post-loop pprint(9)


def test_06826_host_runner_is_version_locked():
    text = RUNNER.read_text(encoding="utf-8")
    assert 'EXPECTED_VERSION = "0.6.82.6"' in text
    assert "C5_TERMINAL_STEP_06826_RESULT=ACCEPT" in text
    assert "LOW_XI_THERMAL_STATUS=OPEN_SEPARATE_INVESTIGATION" in text
