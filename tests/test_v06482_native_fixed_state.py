from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from xstar_tools.xstar.native_fixed_program import (
    compile_program_spec,
    validate_program_directory,
)


ROOT = Path(__file__).resolve().parents[1]
PROGRAM = ROOT / "src/xstar_tools/benchmarks/v06482_native_fixed_state_synthetic"
CPP = ROOT / "src/xstar_tools/xstar/cpp"


def test_raw_program_is_not_replay() -> None:
    result = validate_program_directory(PROGRAM)
    assert result.program_id == "v06482_native_fixed_state_synthetic"
    assert result.records == 5
    assert set(result.opcodes) == {1, 50, 53, 69, 74}
    assert "contains_evaluated_results=false" in (PROGRAM / "manifest.txt").read_text()


def test_compiler_rejects_evaluated_answers(tmp_path: Path) -> None:
    spec = {
        "program_id": "bad",
        "elements": [{"element_z": 1, "n_ions": 1, "rows": [{"ion": 1}]}],
        "records": [{
            "element_index": 0, "opcode": 1, "data_type": 3,
            "lower_row": 1, "upper_row": 1, "reals": [1.0, 2.0],
            "ans1": 123.0,
        }],
    }
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(spec))
    with pytest.raises(ValueError, match="forbidden"):
        compile_program_spec(path, tmp_path / "out")


def test_cpp_native_state_is_state_dependent_and_callback_free() -> None:
    executable = CPP / "xstar_cpp"
    if not executable.exists():
        pytest.skip("native executable has not been built")
    completed = subprocess.run(
        [str(executable), "fixed-state-self-test", "--case-dir", str(PROGRAM)],
        cwd=CPP, text=True, capture_output=True, check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "python_callbacks=0" in completed.stdout
    assert "state_dependent=true" in completed.stdout
    assert "RESULT=ACCEPT" in completed.stdout


def test_cpp_generates_computed_log_and_fits(tmp_path: Path) -> None:
    executable = CPP / "xstar_cpp"
    if not executable.exists():
        pytest.skip("native executable has not been built")
    completed = subprocess.run(
        [str(executable), "run-fixed-state", "--case-dir", str(PROGRAM), "--output-dir", str(tmp_path)],
        cwd=CPP, text=True, capture_output=True, check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    log = (tmp_path / "xout_step.log").read_text()
    assert "computed_from_raw_coefficients=true" in log
    assert "python_callbacks=0" in log
    from astropy.io import fits
    with fits.open(tmp_path / "xout_native_state.fits") as hdul:
        assert [hdu.name for hdu in hdul] == ["PRIMARY", "NATIVE_STATE", "NATIVE_SPECTRUM"]
        assert len(hdul[2].data) == 64
