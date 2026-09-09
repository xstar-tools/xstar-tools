from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def test_current_source_concordance_gate_accepts() -> None:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools/qualification/check_source_concordance.py")],
        cwd=ROOT, text=True, capture_output=True, check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "SOURCE_CONCORDANCE_RESULT=ACCEPT" in proc.stdout


def test_concordance_no_longer_depends_on_retired_overlay_manifests() -> None:
    data = json.loads((ROOT / "qualification/source_concordance.json").read_text())
    policy = json.dumps(data.get("pinned_source_policy", {}), sort_keys=True)
    assert "cpp_source_comment_overlay.json" not in policy
    assert "python_source_comment_overlay.json" not in policy
    assert data["pinned_source_policy"]["science_hash_manifest"] == "qualification/parity_freeze_current_source_hashes.json"
