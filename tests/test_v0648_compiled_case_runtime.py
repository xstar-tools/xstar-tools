from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess

import xstar_tools
from xstar_tools.xstar.compiled_case import (
    bundled_case_path,
    compiled_case_status,
    run_compiled_case,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_v0648_bundle_metadata() -> None:
    assert xstar_tools.__version__ == "0.6.48.4.1"
    status = compiled_case_status()
    assert status["available"] is True
    assert status["package_version"] == "0.6.48.4.1"
    assert status["evaluation_count"] == 61
    assert status["python_callback_count"] == 0
    assert status["science_file_count"] == 9


def test_v0648_callback_free_exact_science(tmp_path: Path) -> None:
    result = run_compiled_case(tmp_path)
    assert result["evaluations_native"] == 61
    assert result["python_callbacks"] == 0
    assert result["science_files_written"] == 9
    assert result["science_files_verified"] == 9
    bundle = bundled_case_path()
    for source in sorted((bundle / "science").glob("*.fits")):
        assert _sha256(source) == _sha256(tmp_path / source.name)
    assert (tmp_path / "xstar_native_trajectory.csv").is_file()
    assert (tmp_path / "xstar_native_terminals.csv").is_file()


def test_v0648_standalone_and_batch() -> None:
    package = Path(__file__).resolve().parents[1]
    cpp = package / "src" / "xstar_tools" / "xstar" / "cpp"
    case = bundled_case_path()
    for command in (
        [str(cpp / "xstar_cpp"), "production-self-test", "--case-dir", str(case)],
        [
            str(cpp / "xstar_cpp"),
            "production-batch-self-test",
            "--case-dir",
            str(case),
            "--batch",
            "4",
        ],
    ):
        completed = subprocess.run(command, cwd=cpp, text=True, capture_output=True)
        assert completed.returncode == 0, completed.stderr
        assert "RESULT=ACCEPT" in completed.stdout
        assert "python_callbacks=0" in completed.stdout
