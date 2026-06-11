from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src/xstar_tools/xstar/cpp"
FIXTURE = ROOT / "src/xstar_tools/benchmarks/v06485_active_family_phase2_fixture"
REFERENCE = ROOT / "src/xstar_tools/benchmarks/v0648_compiled_case_helike_type69_mg11_ne1e8"


def test_preliminary_rates_feed_stage_selection_without_direct_matrix_injection() -> None:
    source = (CPP / "fixed_state_engine.cpp").read_text()
    assert "build_preliminary_ion_balance" in source
    assert "c.rate_type == 8 || c.rate_type == 6" in source
    assert "make_active_element_view" in source
    assert "const bool active_stage = original.ion_stage >= active.min_stage" in source
    assert "matrix_committed = true" in source


def test_reference_trajectory_accepts_external_radiation_csv(tmp_path: Path) -> None:
    executable = CPP / "xstar_cpp"
    if not executable.exists():
        pytest.skip("native executable has not been built")
    output = tmp_path / "trajectory"
    completed = subprocess.run(
        [
            str(executable),
            "run-fixed-trajectory",
            "--case-dir", str(FIXTURE),
            "--trajectory-csv", str(REFERENCE / "trajectory.csv"),
            "--radiation-csv", str(REFERENCE / "reference_radiation_v0472_64bin.csv"),
            "--output-dir", str(output),
        ],
        cwd=CPP,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "radiation_input=external_reference_csv" in completed.stdout
    assert "radiation_bins=64" in completed.stdout
    assert "trajectory_evaluations=61" in completed.stdout
    assert "RESULT=ACCEPT" in completed.stdout
    summary = (output / "native_trajectory_summary.json").read_text()
    assert '"radiation_input": "external_reference_csv"' in summary
    assert '"radiation_bins": 64' in summary
