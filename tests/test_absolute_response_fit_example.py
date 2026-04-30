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
