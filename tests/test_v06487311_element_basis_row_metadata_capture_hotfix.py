from pathlib import Path
from xstar_tools.xstar.v0472_call2_helium_solve_state_capture import RELEASE, _PROBE


def test_release_and_actual_element_basis_row_schema():
    assert RELEASE == "0.6.48.7.34"
    assert "assembly.basis.ion_stage" in _PROBE
    assert "meta.ion_counter" in _PROBE
    assert "'ion_stage':stage" in _PROBE
    assert "'ion_charge':max(0,stage-1)" in _PROBE
    assert "meta.ion)" not in _PROBE
    assert "meta.ion_charge" not in _PROBE
    compile(_PROBE, "v0487311_generated_probe.py", "exec")


def test_hotfix_runner_and_readiness_files_present():
    runner = Path("run_v0487311_element_basis_row_metadata_capture_hotfix.sh").read_text()
    readiness = Path("check_v0487311_element_basis_row_metadata_readiness.py").read_text()
    assert "v0472_call2_helium_solve_state_capture" in runner
    assert "XSTAR_QUALIFICATION_SOLVE_RESPONSE=1" in runner
    assert "ELEMENT_BASIS_ROW_METADATA_CAPTURE" in readiness
    assert "physics_changed" in readiness
