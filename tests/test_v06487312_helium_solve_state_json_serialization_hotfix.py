from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from xstar_tools.xstar.v0472_call2_helium_solve_state_capture import RELEASE, _PROBE


def test_generated_probe_writes_valid_json_newline_and_validates():
    assert RELEASE == "0.6.48.7.39"
    assert "state_path.write_text(json.dumps(_HE_SOLVE_STATE,indent=2,sort_keys=True)+'\\n')" in _PROBE
    assert "+'\\\\n'" not in _PROBE
    assert "json.loads(state_path.read_text())" in _PROBE
    compile(_PROBE, "v0487312_generated_probe.py", "exec")


def test_missing_summary_checker_returns_structured_rejection(tmp_path: Path):
    audit = tmp_path / "audit"
    audit.mkdir()
    output = tmp_path / "report.json"
    checker = Path("check_v0487312_helium_solve_state_json_serialization_hotfix.py")
    completed = subprocess.run(
        [
            sys.executable,
            str(checker),
            "--audit-output",
            str(audit),
            "--output-json",
            str(output),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 2
    report = json.loads(output.read_text())
    assert report["result"] == "REJECT"
    assert report["gates"]["CALL2_HE_SOLVE_STATE_DECOMPOSITION"] == "NOT_RUN_MISSING_SUMMARY"
    assert "missing summary:" in report["errors"][0]
    assert "FileNotFoundError" not in completed.stderr


def test_new_runner_uses_unchanged_physical_decomposition():
    text = Path("run_v0487312_helium_solve_state_json_serialization_hotfix.sh").read_text()
    assert "v0472_call2_helium_solve_state_capture" in text
    assert "XSTAR_QUALIFICATION_SOLVE_RESPONSE=1" in text
    assert "call2_helium_solve_state_rate_matrix_decomposition" in text
