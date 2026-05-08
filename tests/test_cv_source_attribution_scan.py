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
    assert attr.exists()
    assert scan.exists()
    attr_rows = list(csv.DictReader(attr.open()))
    scan_rows = list(csv.DictReader(scan.open()))
    families = {r["source_family"] for r in attr_rows}
    assert "type71_from_sprlevlt" in families
    assert "type71_from_sprlevls" in families
    assert "type99_into_sprlevlt" in families
    assert any(r["scaled_group"] == "type71_resonance_singlet_cascade" for r in scan_rows)
    assert any(r["scaled_group"] == "none" for r in scan_rows)
