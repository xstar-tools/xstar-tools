from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAPTURE = ROOT / "src/xstar_tools/xstar/v0472_all61_independent_thermal_capture_v048746211.py"


def test_capture_hooks_matrix_commit_not_all_ucalc_calls() -> None:
    source = CAPTURE.read_text()
    assert "def _v048746211_install_answer_commit_hook" in source
    assert "original_terms_for_result = eq._matrix_terms_for_result" in source
    assert "eq._matrix_terms_for_result = matrix_terms_for_result" in source
    assert "original_evaluate = SourceFaithfulUCalc.evaluate_record_number" not in source


def test_capture_records_actual_source_position_and_final_answers() -> None:
    source = CAPTURE.read_text()
    assert '"source_position": int(term_start)' in source
    for field in ("ans3", "ans4", "ans5", "ans6"):
        assert f'"{field}": float(getattr(result, "{field}", 0.0))' in source
    assert "terms = original_terms_for_result(" in source
    assert source.index("terms = original_terms_for_result(") < source.index('sink = _STATE.setdefault("v048746211_answer_channels", {})')


def test_record47_preliminary_context_failure_is_documented_as_excluded() -> None:
    source = CAPTURE.read_text()
    assert "Preliminary ion-balance calls may evaluate the same atomic record" in source
    assert "H record 47 in sequence 1" in source
    assert "non-unique committed Thermal answer context" in source


def test_v21_scientific_implementation_is_preserved() -> None:
    cpp = ROOT / "src/xstar_tools/xstar/cpp"
    fixed = (cpp / "fixed_state_engine.cpp").read_text()
    element = (cpp / "element_engine.cpp").read_text()
    assert '#include "source_order_thermal_reducer.hpp"' in fixed
    assert '#include "source_order_thermal_reducer.hpp"' in element
    assert "output.elcter = input.electron_fraction_xee - computed_electron_fraction" in fixed
    assert "last_source_scalar_override_used" in fixed


def test_hotfix_readiness_accepts(tmp_path: Path) -> None:
    report = tmp_path / "readiness.json"
    subprocess.run(
        [
            "python",
            str(ROOT / "check_v048746211_independent_thermal_parity_readiness.py"),
            "--package-dir",
            str(ROOT),
            "--output-json",
            str(report),
        ],
        check=True,
    )
    result = json.loads(report.read_text())
    assert result["result"] == "ACCEPT"
    contract = result["module_contract"]
    assert contract["source_answer_matrix_commit_hook"] >= 1
    assert contract["source_answer_raw_ucalc_hook"] == 0


def test_hotfix_runner_usage_and_revision() -> None:
    runner = ROOT / "run_v048746211_independent_thermal_parity.sh"
    completed = subprocess.run([str(runner)], cwd=ROOT, capture_output=True, text=True)
    assert completed.returncode == 64
    source = runner.read_text()
    assert "20260726-independent-thermal-answer-commit-context-v2" in source
    assert "v0472_all61_independent_thermal_capture_v048746211" in source
