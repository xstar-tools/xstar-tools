from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path


def test_cv_source_attribution_scan_smoke(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    solver_dir = root / "c5_xstar_like_element_solver_v03104_xstar_line_escape_superlevels"
    xstar_csv = root / "xstar_test_run" / "c5_ne1e8" / "xstar_c5_triplet_lines.csv"
    if not solver_dir.exists() or not xstar_csv.exists():
        return
    out_dir = tmp_path / "cv_scan"
    cmd = [
        sys.executable,
        str(root / "examples" / "46_cv_source_attribution_scan.py"),
        "--solver-out-dir",
        str(solver_dir),
        "--xstar-triplet-lines-csv",
        str(xstar_csv),
        "--sprlevlt-scales",
        "1",
        "--sprlevls-scales",
        "1",
        "--resonance-cascade-scales",
        "1",
        "--out-dir",
        str(out_dir),
        "--print-summary",
    ]
    proc = subprocess.run(cmd, cwd=root, env={"PYTHONPATH": str(root / "src")}, text=True, capture_output=True, check=True)
    assert "C V source-attribution f/r scan" in proc.stdout
    attr = out_dir / "cv_source_family_attribution.csv"
    scan = out_dir / "cv_source_group_scan.csv"
    weighted_attr = out_dir / "cv_population_weighted_source_attribution.csv"
    weighted_scan = out_dir / "cv_population_weighted_source_scan.csv"
    direct_attr = out_dir / "cv_direct_bound_bound_source_attribution.csv"
    direct_scan = out_dir / "cv_direct_bound_bound_resonance_singlet_scan.csv"
    assert attr.exists()
    assert scan.exists()
    assert weighted_attr.exists()
    assert weighted_scan.exists()
    assert direct_attr.exists()
    assert direct_scan.exists()
    attr_rows = list(csv.DictReader(attr.open()))
    scan_rows = list(csv.DictReader(scan.open()))
    weighted_scan_rows = list(csv.DictReader(weighted_scan.open()))
    direct_attr_rows = list(csv.DictReader(direct_attr.open()))
    direct_scan_rows = list(csv.DictReader(direct_scan.open()))
    families = {r["source_family"] for r in attr_rows}
    assert "type71_from_sprlevlt" in families
    assert "type71_from_sprlevls" in families
    assert "type99_into_sprlevlt" in families
    assert any(r["scaled_group"] == "type71_resonance_singlet_cascade" for r in scan_rows)
    assert any(r["scaled_group"] == "none" for r in scan_rows)
    assert any(r["scan_model"] == "population_weighted_fixed_population_first_order" for r in weighted_scan_rows)
    direct_groups = {r["direct_bound_bound_group"] for r in direct_attr_rows}
    assert "direct_bound_bound_resonance_singlet_feed" in direct_groups
    assert "direct_bound_bound_forbidden_triplet_feed" in direct_groups
    assert any(r["scaled_group"] == "direct_bound_bound_resonance_singlet_feed" for r in direct_scan_rows)
    assert any(r["scan_model"] == "direct_bound_bound_resonance_forbidden_2d_fixed_population" for r in direct_scan_rows)
