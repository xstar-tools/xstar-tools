from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from xstar_tools.xstar import all61_dense_matrix_causal_attribution as causal
from xstar_tools.xstar import v0472_all61_post_seed_system_capture as capture


ROOT = Path(__file__).resolve().parents[1]


def test_source_contribution_capture_executes() -> None:
    report = capture.probe_capture_behavioral_self_test()
    assert report["result"] == "ACCEPT", report
    assert report["systems"] == 3
    assert report["binary_arrays"] == 30
    assert capture.CONTRIBUTION_INT_COLUMNS == 14
    assert capture.CONTRIBUTION_REAL_COLUMNS == 16


def test_causal_attribution_classifies_orientation() -> None:
    report = causal.causal_attribution_self_test()
    assert report["result"] == "ACCEPT", report
    assert report["mismatch_cells"] > 0
    assert report["classification_counts"]["ENDPOINT_ORIENTATION_DELTA"] > 0
    assert report["data_type_counts"]["50"] > 0


def test_hydrogen_type53_qualification_correction_is_guarded() -> None:
    cpp = (ROOT / "src/xstar_tools/xstar/cpp/fixed_state_engine.cpp").read_text()
    assert "XSTAR_QUALIFICATION_HYDROGEN_TYPE53_SOURCE_FAITHFUL" in cpp
    assert "hydrogen type53 source-faithful correction requires XSTAR_QUALIFICATION_REPLACEMENT=1" in cpp
    assert "c.ans1 = source_shadow.ans1" in cpp
    assert "c.ans6 = source_shadow.ans6" in cpp


def test_native_contribution_binary_contract_is_present() -> None:
    cpp = (ROOT / "src/xstar_tools/xstar/cpp/fixed_state_engine.cpp").read_text()
    for marker in (
        "matrix_contribution_ints_path",
        "matrix_contribution_reals_path",
        "kContributionIntColumns",
        "kContributionRealColumns",
        "committed_contributions",
    ):
        assert marker in cpp


def test_release_runner_is_full_physics_workflow() -> None:
    runner = ROOT / "run_v0487469_all61_dense_matrix_causal_record_attribution.sh"
    text = runner.read_text()
    assert runner.stat().st_size > 7500
    assert "XSTAR_QUALIFICATION_HYDROGEN_TYPE53_SOURCE_FAITHFUL=1" in text
    assert "XSTAR_QUALIFICATION_SOURCE_COMPACT_BASIS_SEED=1" in text
    assert "all61_post_seed_system_decomposition" in text
    assert "all61_dense_matrix_causal_attribution" in text


def test_readiness_accepts(tmp_path: Path) -> None:
    output = tmp_path / "readiness.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "check_v04874691_indexed_causal_attribution_readiness.py"),
            "--package-dir",
            str(ROOT),
            "--output-json",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    report = json.loads(output.read_text())
    assert report["result"] == "ACCEPT", report
