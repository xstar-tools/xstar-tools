from __future__ import annotations

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools/qualification/check_broad_multi_element_closure_0_6_82_5.py"
RUNNER = ROOT / "tools/qualification/run_multi_element_host_smoke_0_6_82_5.py"


def test_06825_checker_accepts():
    proc = subprocess.run([sys.executable, str(CHECKER)], cwd=ROOT, text=True, capture_output=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "BROAD_MULTI_ELEMENT_CLOSURE_06825_RESULT=ACCEPT" in proc.stdout


def test_06825_type85_and_dsec_contracts_are_present():
    local = (ROOT / "src/xstar_tools/xstar/cpp/local_zone_engine.cpp").read_text(encoding="utf-8")
    standalone = (ROOT / "src/xstar_tools/xstar/cpp/xstar_standalone.cpp").read_text(encoding="utf-8")
    atdb = (ROOT / "src/xstar_tools/xstar/cpp/xstar_atdb_runtime.cpp").read_text(encoding="utf-8")
    t85 = local[local.index("else if(dt==85)"):local.index("if (dt != 64 && dt != 85)")]
    assert "c.ans4=-ph.ans[2]" in t85
    assert "c.ans6=-ph.ans[4]" in t85
    a85 = atdb[atdb.index("case 85:"):atdb.index("case 89:", atdb.index("case 85:"))]
    assert "else energy_order_pair(id1,1)" in a85
    assert 'snapshot.kind == "dsec"' in standalone
    assert "XSTAR_FIXED_RUNTIME_STATE_DSEC_HMC_ONLY" in standalone


def test_06825_ntotit_and_step_rows_are_physical_source_owned():
    state = (ROOT / "src/xstar_tools/xstar/cpp/xstar_run_state.hpp").read_text(encoding="utf-8")
    standalone = (ROOT / "src/xstar_tools/xstar/cpp/xstar_standalone.cpp").read_text(encoding="utf-8")
    step = (ROOT / "src/xstar_tools/xstar/cpp/xstar_step_log.cpp").read_text(encoding="utf-8")
    assert "std::size_t dsec_ntotit = 0" in state
    assert "std::max(stats.ntotit, 0)" in standalone
    assert "zone.dsec_ntotit = dsec_ntotit" in standalone
    assert "const std::size_t output_rows = rows.size();" in step
    assert "physical_radial_boundaries_retained" in step
    assert "state.radial_zones[i].dsec_ntotit" in step
    assert "std::max<std::size_t>(state.radial_zones.size(),rows.size())" not in step


def test_06825_host_runner_is_version_locked():
    text = RUNNER.read_text(encoding="utf-8")
    assert 'EXPECTED_VERSION = "0.6.82.5"' in text
    assert "MULTI_ELEMENT_HOST_SMOKE_06825_SCIENCE_RESULT=" in text
    assert "MULTI_ELEMENT_HOST_SMOKE_06825_PERFORMANCE_RESULT=" in text
