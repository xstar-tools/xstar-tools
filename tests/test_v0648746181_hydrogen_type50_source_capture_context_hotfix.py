from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import xstar_tools
from xstar_tools.xstar import v0472_all61_hydrogen_type50_escape_capture as capture

ROOT = Path(__file__).resolve().parents[1]


def _blocks() -> tuple[str, str]:
    source = capture._PROBE
    start = source.index("    def escape_factors(record, rate_type, derived, context):")
    middle = source.index("    def evaluate_record_number", start)
    end = source.index("    eq._escape_factors", middle)
    return source[start:middle], source[middle:end]


def test_release_and_context_filter_contract() -> None:
    assert xstar_tools.__version__ == "0.6.48.7.46.20.1"
    escape_block, result_block = _blocks()
    assert "if int(rate_type) == 4:" in escape_block
    assert 'extras.get("element_z"' not in escape_block
    assert 'data_type", -1)) == 50' in result_block
    assert 'extras.get("element_z"' in result_block


def test_invalid_partial_capture_is_rebuilt() -> None:
    runner = (ROOT / "run_v04874618_hydrogen_type50_cooling.sh").read_text()
    assert "V04874618_SOURCE_CAPTURE_INVALID_RECAPTURE=1" in runner
    assert "XSTAR_V04874618_SOURCE_CAPTURE_REUSE_STRICT" in runner
    assert 'rm -rf "$SOURCE_CAPTURE"' in runner


def test_hotfix_readiness_accepts(tmp_path: Path) -> None:
    output = tmp_path / "readiness.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "check_v048746181_hydrogen_type50_source_capture_context_hotfix_readiness.py"),
            "--package-dir",
            str(ROOT),
            "--output-json",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    report = json.loads(output.read_text())
    assert report["result"] == "ACCEPT"
    assert report["module_contract"]["escape_capture_all_rate4"] == 1
    assert report["module_contract"]["escape_capture_wrong_element_filter_removed"] == 0


def test_hotfix_checker_accepts_synthetic_v4618_result(tmp_path: Path) -> None:
    output = tmp_path / "audit"
    output.mkdir()
    prior_gates = {
        "HYDROGEN_COOLING_ALL61_EXACT": "ACCEPT",
        "HYDROGEN_TYPE50_ANSWERS_EXACT_8113": "ACCEPT",
        "NATIVE_COMPUTED_THERMAL_VALUES_EXACT_1066": "ACCEPT",
        "ALL_CONTINUUM_COMPONENTS_BIT_EXACT_610_PRESERVED": "ACCEPT",
        "V06487_FIXED_STATE_PARITY_PRESERVED": "ACCEPT",
        "DENSE_EXACT_SYSTEMS_183_PRESERVED": "ACCEPT",
        "DENSE_MISMATCH_CELLS_ZERO_PRESERVED": "ACCEPT",
        "PRODUCTION_PROMOTION_BLOCKED": "ACCEPT",
    }
    (output / "v04874618_checker_report.json").write_text(
        json.dumps(
            {
                "result": "ACCEPT",
                "scientific_result": "ACCEPT",
                "gates": prior_gates,
                "native_computed_values_exact": 1066,
                "native_computed_values_total": 2440,
                "independent_native_thermal_parity": "NOT_ACCEPTED",
                "production_promotion_ready": False,
            }
        )
    )
    (output / "v04874618_source_capture_verification.json").write_text(
        json.dumps(
            {
                "result": "ACCEPT",
                "evaluations": 61,
                "hydrogen_type50_escape_rows": 8113,
                "line_index_map_rows": 133,
                "thermal_capture_result": "ACCEPT",
                "production_promotion_ready": False,
            }
        )
    )
    (output / "v048746181_readiness_report.json").write_text(json.dumps({"result": "ACCEPT"}))
    report_path = output / "v048746181_checker_report.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "check_v048746181_hydrogen_type50_source_capture_context_hotfix.py"),
            "--audit-output",
            str(output),
            "--output-json",
            str(report_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert json.loads(report_path.read_text())["result"] == "ACCEPT"
