from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def package_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_runner_rebases_stale_matrix_pointer_to_current_path(tmp_path: Path) -> None:
    runner = package_root() / "run_v04874612_all61_thermal_state_consumption_audit.sh"
    source = tmp_path / "xstar_tools-0.6.47.2.tar.gz"
    atdb = tmp_path / "atdb.fits"
    source.write_bytes(b"")
    atdb.write_bytes(b"")

    base11 = tmp_path / "v04874611_all61_fixed_state_parity"
    (base11 / "v04874611_fixed_state_closure").mkdir(parents=True)
    (base11 / "v04874611_baseline_v04874610.txt").write_text(
        "/removed/xstar_tools-0.6.48.7.46.11/v04874610_matrix_construction_closure\n"
    )

    local_base10 = tmp_path / "v04874610_matrix_construction_closure"
    (local_base10 / "v04874610_matrix_closure").mkdir(parents=True)

    report = tmp_path / "v048746111_checker_report.json"
    report.write_text(json.dumps({
        "result": "ACCEPT",
        "dense_exact_systems": 183,
        "dense_mismatch_cells": 0,
    }) + "\n")

    env = dict(os.environ, XSTAR_V04874612_BASELINE_PREFLIGHT_ONLY="1")
    completed = subprocess.run(
        [
            str(runner), str(source), str(atdb), str(base11), str(report),
            str(tmp_path / "unused-output"), "10",
        ],
        cwd=tmp_path, env=env, check=True, capture_output=True, text=True,
    )
    assert "V04874612_BASELINE_PREFLIGHT=ACCEPT" in completed.stdout
    assert f"matrix_closure_dir={local_base10 / 'v04874610_matrix_closure'}" in completed.stdout
    assert "V04874612_BASELINE_REBASE" in completed.stderr
