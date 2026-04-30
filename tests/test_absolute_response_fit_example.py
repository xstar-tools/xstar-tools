from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_signed_triplet_response_absolute_fit_dry_run(tmp_path: Path):
    xstar_csv = tmp_path / "xstar_c5_triplet_lines.csv"
    xstar_csv.write_text(
        "index,ion,lower_level,upper_level,wavelength,emit_outward\n"
        "1,c_v,1s2.1S_0,1s1.2s1.3S_1,41.47,1.0\n"
        "2,c_v,1s2.1S_0,1s1.2p1.3P_1,40.73,0.2\n"
        "3,c_v,1s2.1S_0,1s1.2p1.1P_1,40.27,0.5\n",
        encoding="utf-8",
    )
    out = tmp_path / "signed_audit_fit"
    completed = subprocess.run([
        sys.executable,
        "examples/40_audit_signed_triplet_response.py",
        "dummy_atdb.fits",
        "--element", "C",
        "--ion-stage", "5",
        "--temperature", "1000000",
        "--electron-density", "1e8",
        "--wavelength-min", "40",
        "--wavelength-max", "42",
        "--source-levels", "2,56",
        "--xstar-lines-csv", str(xstar_csv),
        "--fit-mode", "absolute-response",
        "--out-dir", str(out),
        "--dry-run",
        "--print-summary",
    ], cwd=ROOT, check=True, capture_output=True, text=True)
    assert "absolute_response_fit status=dry_run" in completed.stdout
    summary = json.loads((out / "helike_signed_triplet_response_summary.json").read_text())
    assert summary["absolute_response_fit"]["enabled"] is True
    assert summary["absolute_response_fit"]["status"] == "dry_run"
    rows = list(csv.DictReader((out / "helike_absolute_response_fit_weights.csv").open()))
    assert rows == []



def test_absolute_response_constraint_helpers():
    import importlib.util
    spec = importlib.util.spec_from_file_location("audit40", ROOT / "examples" / "40_audit_signed_triplet_response.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)

    class Args:
        absolute_fit_reject_pure_i = True
        absolute_fit_pure_i_threshold = 0.95
        absolute_fit_max_intercombination_fraction = 0.9
        absolute_fit_max_forbidden_fraction = 1.0
        absolute_fit_max_resonance_fraction = 1.0
        absolute_fit_min_forbidden_fraction = 0.0
        absolute_fit_min_resonance_fraction = 0.0

    reasons = mod.absolute_candidate_rejection_reasons([0.0, 1.0, 0.0], Args())
    assert "pure_intercombination" in reasons
    assert "max_intercombination_fraction" in reasons

    class TargetAwareArgs(Args):
        absolute_fit_constraint_mode = "target-aware"
        absolute_fit_reject_pure_i = False
        absolute_fit_max_intercombination_fraction = 1.0
        absolute_fit_target_i_factor = 3.0
        absolute_fit_target_i_floor = 0.05
        absolute_fit_low_target_i_threshold = 0.05

    effective = mod.effective_absolute_fit_constraints(TargetAwareArgs(), [0.8077, 0.0066, 0.1857])
    assert effective["mode"] == "target-aware"
    assert effective["reject_pure_i"] is True
    assert abs(effective["max_intercombination_fraction"] - 0.05) < 1e-12
    reasons = mod.absolute_candidate_rejection_reasons([0.8, 0.06, 0.14], TargetAwareArgs(), [0.8077, 0.0066, 0.1857])
    assert "max_intercombination_fraction" in reasons

    high_i = mod.effective_absolute_fit_constraints(TargetAwareArgs(), [0.01, 0.75, 0.24])
    assert high_i["reject_pure_i"] is False
    assert high_i["max_intercombination_fraction"] == 1.0

    w = mod.parse_component_weights("auto", [0.8, 0.001, 0.199], floor=1e-3)
    assert len(w) == 3
    assert w[1] > w[0]
