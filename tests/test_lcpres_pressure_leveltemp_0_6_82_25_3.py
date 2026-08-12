from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_production_runner_carries_source_leveltemp_across_dsec_and_zones():
    source = (ROOT / "src/xstar_tools/xstar/physical_runner.py").read_text()
    assert "leveltemp_workspace=None if prior is None else prior.leveltemp_workspace" in source
    assert "leveltemp_owner_by_column={} if prior is None else prior.leveltemp_owner_by_column" in source
    assert "reset_leveltemp_each_calc_hmc_all=False" in source


def test_dsec_commit_supports_persistent_source_leveltemp():
    source = (ROOT / "src/xstar_tools/xstar/dsec.py").read_text()
    assert "if not self.reset_leveltemp_each_calc_hmc_all:" in source
    assert "self.leveltemp_workspace = result.leveltemp_workspace" in source
    assert "self.last_leveltemp_workspace = result.leveltemp_workspace" in source


def test_emissivity_and_heatt_preserve_one_source_wide_leveltemp_chain():
    emisab = (ROOT / "src/xstar_tools/xstar/emissivity.py").read_text()
    emis = (ROOT / "src/xstar_tools/xstar/emergent_emissivity.py").read_text()
    radial = (ROOT / "src/xstar_tools/xstar/radial_transfer.py").read_text()
    assert "next_context.initial_leveltemp_workspace = result.leveltemp_workspace" in emisab
    assert "runtime.leveltemp_workspace = result.leveltemp_workspace" in emisab
    assert "runtime.leveltemp_workspace = result.leveltemp_workspace" in emis
    assert "runtime.leveltemp_workspace = result.leveltemp_workspace" in radial


def test_25_3_runner_is_backend_aware_and_version_locked():
    source = (ROOT / "tools/qualification/run_c5_lcpres_pressure_host_smoke_0_6_82_25_3.py").read_text()
    assert "--backend" in source
    assert "choices=('cpp','python')" in source
    assert 'EXPECTED_VERSION="0.6.82.25.3"' in source
    assert "C5_LCPRES_PRESSURE_0682253_" in source
