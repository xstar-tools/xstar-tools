from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools" / "qualification" / "check_cpp_unused_function_cleanup_0_6_77.py"
MANIFEST = ROOT / "qualification" / "cpp_unused_function_cleanup_0_6_77.json"


def test_cpp_unused_function_cleanup_0677_gate_accepts() -> None:
    proc = subprocess.run([sys.executable, str(CHECKER)], cwd=ROOT, text=True, capture_output=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "CPP_UNUSED_FUNCTION_CLEANUP_0677_RESULT=ACCEPT" in proc.stdout
    assert "CPP_UNUSED_FUNCTION_CLEANUP_0677_WARNING_COUNT=0" in proc.stdout


def test_cpp_unused_function_cleanup_0677_exact_annotation_set() -> None:
    data = json.loads(MANIFEST.read_text())
    assert data["product_version"] == "0.6.77"
    assert data["base_version"] == "0.6.76"
    assert data["science_change"] is False
    assert data["annotated_function_count"] == 12
    names = {name for values in data["annotated_functions"].values() for name in values}
    assert len(names) == 12
    assert {"resolve_standalone_atomic_database", "load_native_ion_row_minima", "csv_double"} <= names


def test_cpp_unused_function_cleanup_0677_does_not_suppress_warnings() -> None:
    makefile = (ROOT / "src/xstar_tools/xstar/cpp/Makefile").read_text()
    assert "-Wno-" not in makefile
    for flag in ("-Wall", "-Wextra", "-Wpedantic"):
        assert flag in makefile
