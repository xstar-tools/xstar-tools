from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def test_compact_parity_freeze_gate_accepts() -> None:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools/qualification/check_parity_freeze.py")],
        cwd=ROOT, text=True, capture_output=True, check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "PARITY_FREEZE_RESULT=ACCEPT" in proc.stdout


def test_cleanup_preserves_frozen_science_revision_and_abis() -> None:
    data = json.loads((ROOT / "qualification/parity_freeze.json").read_text())
    assert data["schema"] == "xstar-tools-parity-freeze-v2"
    assert data["science_revision"] == "0.6.48.12.3.45.3.3.8"
    assert data["abis"] == {
        "c_api": 60487,
        "production_zone": 6048110,
        "fixed_state_program": 60486,
        "fixed_state_engine": 60488,
        "xspec_table": 1,
    }


def test_current_science_source_hash_manifest_is_predecessor_snapshot() -> None:
    data = json.loads((ROOT / "qualification/parity_freeze_current_source_hashes.json").read_text())
    assert data["captured_from_distribution"] == "0.6.90.2"
    assert data["science_revision"] == "0.6.48.12.3.45.3.3.8"
    assert len(data["files"]) >= 50
