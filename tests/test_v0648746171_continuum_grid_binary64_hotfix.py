from __future__ import annotations

import json
import struct
import subprocess
import sys
from pathlib import Path

import numpy as np

from xstar_tools.xstar.continuum_grid_binary64_hotfix_v048746171 import (
    canonical_epim_binary64,
)
from xstar_tools.xstar.v4617_baseline_gate_v048746171 import (
    ACCEPTED_GATES,
    EXPECTED_REJECTED_GATES,
)

ROOT = Path(__file__).resolve().parents[1]


def test_release_version() -> None:
    import xstar_tools

    assert xstar_tools.__version__ == "0.6.48.7.46.19"


def test_canonical_binary64_grid_contract() -> None:
    energy = canonical_epim_binary64()
    assert len(energy) == 999
    assert struct.pack(">d", float(energy[0])) == struct.pack(">d", 0.1)
    assert np.all(np.diff(energy) > 0.0)
    assert 9.9e5 < energy[-1] < 1.1e6


def test_binary64_grid_differs_from_historical_default_real_reconstruction() -> None:
    from xstar_tools.xstar.continuum_workspace_correction_v04874617 import source_epim

    canonical = canonical_epim_binary64()
    historical = source_epim()
    assert canonical[0] == 0.1
    assert historical[0] == float(np.float32(0.1))
    assert not np.array_equal(canonical, historical)
    assert np.max(np.abs((historical - canonical) / canonical)) > 6.0e-7


def test_cpp_uses_canonical_binary64_literals() -> None:
    source = (ROOT / "src/xstar_tools/xstar/cpp/fixed_state_engine.cpp").read_text()
    assert "double ebnd1 = 0.1;" in source
    assert "double ebnd2 = 4.0e5;" in source
    assert "ebnd2 = 1.0e6;" in source
    assert "static_cast<double>(static_cast<float>(0.1))" not in source


def test_v4617_causal_baseline_gate(tmp_path: Path) -> None:
    source = tmp_path / "checker.json"
    output = tmp_path / "baseline.json"
    gates = {name: "ACCEPT" for name in ACCEPTED_GATES}
    gates.update({name: "REJECT" for name in EXPECTED_REJECTED_GATES})
    source.write_text(
        json.dumps(
            {
                "release": "0.6.48.7.46.17",
                "result": "REJECT",
                "scientific_result": "REJECT",
                "native_computed_values_exact": 419,
                "gates": gates,
                "errors": list(EXPECTED_REJECTED_GATES),
            }
        )
    )
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "xstar_tools.xstar.v4617_baseline_gate_v048746171",
            str(source),
            "--output-json",
            str(output),
        ],
        cwd=ROOT,
        env={"PYTHONPATH": str(ROOT / "src")},
        capture_output=True,
        text=True,
    )
    assert process.returncode == 0, process.stdout + process.stderr
    assert json.loads(output.read_text())["result"] == "ACCEPT"


def test_readiness_accepts(tmp_path: Path) -> None:
    output = tmp_path / "readiness.json"
    process = subprocess.run(
        [
            sys.executable,
            str(ROOT / "check_v048746171_continuum_grid_binary64_semantics_hotfix_readiness.py"),
            "--package-dir",
            str(ROOT),
            "--output-json",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert process.returncode == 0, process.stdout + process.stderr
    assert json.loads(output.read_text())["result"] == "ACCEPT"
