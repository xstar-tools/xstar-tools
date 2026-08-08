from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

from xstar_tools.xstar.qualification import (
    build_source_order_maps,
    compare_directories,
    verify_reference_bundle,
)


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "tests/fixtures/historical/v06486_qualification_reference_v0472"
FIXTURE = ROOT / "tests/fixtures/historical/v06485_active_family_phase2_fixture"
BENCH = ROOT / "tests/fixtures/historical/v0648_compiled_case_helike_type69_mg11_ne1e8"
CPP = ROOT / "src/xstar_tools/xstar/cpp"


def test_immutable_v06472_reference_bundle_verifies() -> None:
    result = verify_reference_bundle(REFERENCE)
    assert result["result"] == "ACCEPT"
    assert result["files_verified"] == result["files_expected"] == 17
    manifest = json.loads((REFERENCE / "reference_manifest.json").read_text())
    assert manifest["immutable"] is True
    assert manifest["source_release"] == "0.6.47.2"
    assert manifest["production_promotion_ready"] is False


def test_source_order_maps_are_dense_and_hashed(tmp_path: Path) -> None:
    result = build_source_order_maps(FIXTURE, tmp_path)
    assert result["source_order_strict"] is True
    assert result["record_count"] == 27
    assert result["row_count"] == 4
    assert result["element_count"] == 1
    assert len(result["outputs"]) == 3
    assert (tmp_path / "source_order_manifest.json").is_file()


def test_strict_comparator_controls(tmp_path: Path) -> None:
    same = compare_directories(REFERENCE, REFERENCE, mode="ieee")
    assert same["result"] == "ACCEPT"
    candidate = tmp_path / "candidate"
    shutil.copytree(REFERENCE, candidate)
    with (candidate / "xout_step.log").open("a", encoding="utf-8") as handle:
        handle.write("negative control\n")
    changed = compare_directories(REFERENCE, candidate, mode="ieee")
    assert changed["result"] == "REJECT"
    assert changed["difference_count_reported"] > 0


def test_native_61_evaluation_family_diagnostics(tmp_path: Path) -> None:
    subprocess.run(["make", "-C", str(CPP), "-j2"], check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    output = tmp_path / "trajectory"
    diagnostics = tmp_path / "diagnostics"
    completed = subprocess.run(
        [
            str(CPP / "xstar_cpp"),
            "run-fixed-trajectory",
            "--case-dir", str(FIXTURE),
            "--trajectory-csv", str(BENCH / "trajectory.csv"),
            "--radiation-csv", str(BENCH / "reference_radiation_v0472_64bin.csv"),
            "--output-dir", str(output),
            "--diagnostics-dir", str(diagnostics),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    assert "trajectory_evaluations=61" in completed.stdout
    assert "python_callbacks=0" in completed.stdout
    assert len(list(diagnostics.glob("evaluation_*_state.json"))) == 61
    assert len(list(diagnostics.glob("evaluation_*_records.csv"))) == 61
    assert sum(1 for _ in (diagnostics / "evaluation_0061_records.csv").open()) == 28
