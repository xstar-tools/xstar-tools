from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]


def test_version_and_plan():
    pyproject = (ROOT / "pyproject.toml").read_text()
    makefile = (ROOT / "src/xstar_tools/xstar/cpp/Makefile").read_text()
    assert 'version = "0.6.82.30.7"' in pyproject
    assert "PACKAGE_VERSION ?= 0.6.82.30.7" in makefile
    plan = json.loads((ROOT / "qualification/npass1_ownership_0_6_82_30_7/npass1_ownership_0_6_82_30_7.json").read_text())
    assert plan["targets"]["savd_scalar_mismatches"] == 0
    assert plan["targets"]["raw_rrc_hdu3_rows"] == "346/346"
    assert plan["targets"]["rrc_identity_209_hdu3"] is True


def test_single_pass_uses_source_savd_detail_surface():
    cpp = (ROOT / "src/xstar_tools/xstar/cpp/xstar_standalone.cpp").read_text()
    assert "const bool source_savd_detail_enabled_v0682307" in cpp
    assert "params.lwrite > 0 || effective_npass_v068227 > 1u" in cpp
    assert cpp.count("if (source_savd_detail_enabled_v0682307)") == 3
    assert "source SAVD FITS-E3/REAL4 per-pass detail surface" in cpp


def test_detail_writer_accepts_saved_single_pass_surface():
    fits = (ROOT / "src/xstar_tools/xstar/cpp/xstar_science_fits.cpp").read_text()
    assert "state.multipass_detail_radial_zones.size() >= static_cast<std::size_t>(npass)" in fits
    assert "source SAVD owns the detail stream whenever" in fits
    runner = (ROOT / "tools/qualification/run_npass1_ownership_host_smoke_0_6_82_30_7.py").read_text()
    assert 'CASE = "npass1"' in runner
    assert 'choices=("prepare", "cpp", "compare", "cpp-compare")' in runner
    assert "npass3" not in runner
    assert "npass5" not in runner
