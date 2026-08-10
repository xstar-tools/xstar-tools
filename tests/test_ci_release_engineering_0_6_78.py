from __future__ import annotations

import csv
import json
from pathlib import Path
import subprocess
import sys

from xstar_tools.benchmarks.public_suite import DEFAULT_PYTHON_CASES
from tools.ci.report_benchmark_results import build_report, classify_case

ROOT = Path(__file__).resolve().parents[1]


def test_milestone10_checker_accepts_current_tree():
    proc = subprocess.run(
        [sys.executable, "tools/qualification/check_ci_release_engineering_0_6_78.py"],
        cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    assert proc.returncode == 0, proc.stdout
    assert "CI_RELEASE_ENGINEERING_0678_RESULT=ACCEPT" in proc.stdout


def test_default_science_smoke_excludes_frozen_c5():
    assert DEFAULT_PYTHON_CASES == (
        "helike_type69/o7_ne1e10",
        "helike_type69/mg11_ne1e8",
        "helike_type69/ca19_xi2_ne1",
    )
    assert all("/c5_" not in case for case in DEFAULT_PYTHON_CASES)
    tier1 = (ROOT / ".github/workflows/ci-tier1-science-smoke.yml").read_text()
    assert "Optional frozen C5 diagnostic smoke" in tier1
    assert "github.event_name == 'workflow_dispatch' && inputs.include_c5" in tier1


def test_regime_report_groups_by_physics_and_backend(tmp_path: Path):
    run_manifest = tmp_path / "run_manifest.csv"
    rows = [
        {"case": "helike_type69/o7_ne1e10", "mode": "zone-cpp", "wall_seconds": "10", "accept": "True"},
        {"case": "helike_type69/mg11_ne1e8", "mode": "zone-cpp", "wall_seconds": "20", "accept": "True"},
        {"case": "helike_type69/ca19_xi2p5_ne1", "mode": "xstar-cpp", "wall_seconds": "30", "accept": "True"},
    ]
    with run_manifest.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    model = tmp_path / "models.csv"
    mrows = [
        {"mode": row["mode"], "case": row["case"], "science_gate": "True", "max_surface_nl1": "0.001"}
        for row in rows
    ]
    with model.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(mrows[0]))
        writer.writeheader(); writer.writerows(mrows)
    detailed, grouped = build_report(run_manifest, model)
    assert len(detailed) == 3
    assert len(grouped) == 3
    assert classify_case("helike_type69/ca19_xi2p5_ne1") == {
        "element": "Ca",
        "density_exponent": 0,
        "density_regime": "low-ne<=1e4",
        "ionization_log10_xi": 2.5,
        "ionization_regime": "mid-xi",
    }
    assert {row["backend"] for row in grouped} == {"zone-cpp", "xstar-cpp"}


def test_tier0_has_no_all62_or_science_benchmark_launch():
    text = (ROOT / ".github/workflows/ci-tier0.yml").read_text()
    assert "qualify benchmark" not in text
    assert "all62" not in text.lower()
    assert "check_parity_freeze.py" in text
    assert "make -C src/xstar_tools/xstar/cpp -j2" in text


def test_performance_is_a_separate_report_only_gate():
    workflow = (ROOT / ".github/workflows/performance.yml").read_text()
    script = (ROOT / "tools/ci/performance_report.py").read_text()
    assert "xstar-perf" in workflow
    assert "performance_report.py" in workflow
    assert '"science_gate": "separate"' in script
    assert '"performance_gate": "report-only"' in script


def test_milestone10_manifest_freezes_science_and_abis():
    doc = json.loads((ROOT / "qualification/ci_release_engineering_0_6_78.json").read_text())
    assert doc["product_version"] == "0.6.78"
    assert doc["science_revision"] == "0.6.48.12.3.45.3.3.8"
    assert doc["c_api_abi"] == 60487
    assert doc["production_zone_abi"] == 6048110
    assert doc["all62_on_every_pr"] is False
    assert doc["default_c5_smoke"] is False
