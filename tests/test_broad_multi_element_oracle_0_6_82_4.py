from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools/qualification/check_broad_multi_element_oracle_0_6_82_4.py"
RUNNER = ROOT / "tools/qualification/run_multi_element_host_smoke_0_6_82_4.py"


def test_broad_multi_element_oracle_checker_accepts():
    env = os.environ.copy()
    source = Path("/mnt/data/xstar_fortran_src/xstar")
    if source.is_dir():
        env["XSTAR_SOURCE_ROOT"] = str(source)
    proc = subprocess.run([sys.executable, str(CHECKER)], cwd=ROOT, env=env, text=True, capture_output=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "BROAD_MULTI_ELEMENT_ORACLE_06824_RESULT=ACCEPT" in proc.stdout


def test_host_runner_is_version_locked_and_fortran_gated():
    text = RUNNER.read_text(encoding="utf-8")
    assert 'EXPECTED_VERSION = "0.6.82.4"' in text
    assert "STEP_REFERENCE" in text
    assert "MATERIAL_LIMIT = 0.01" in text
    assert "DEFAULT_PERFORMANCE_RATIO_LIMIT = 1.25" in text
    assert "MULTI_ELEMENT_HOST_SMOKE_06824_SCIENCE_RESULT=" in text
    assert "MULTI_ELEMENT_HOST_SMOKE_06824_PERFORMANCE_RESULT=" in text


def test_type85_endpoint_and_dsec_hot_path_are_source_shaped():
    atdb = (ROOT / "src/xstar_tools/xstar/cpp/xstar_atdb_runtime.cpp").read_text(encoding="utf-8")
    local = (ROOT / "src/xstar_tools/xstar/cpp/local_zone_engine.cpp").read_text(encoding="utf-8")
    standalone = (ROOT / "src/xstar_tools/xstar/cpp/xstar_standalone.cpp").read_text(encoding="utf-8")
    section = atdb[atdb.index("case 85:"):atdb.index("case 89:", atdb.index("case 85:"))]
    assert "else energy_order_pair(id1,1)" in section
    assert "if (!dsec_hmc_only_v06824 && !spectral.empty()" in local
    assert "XSTAR_FIXED_RUNTIME_STATE_DSEC_HMC_ONLY" in standalone
