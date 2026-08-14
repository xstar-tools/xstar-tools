from __future__ import annotations

import importlib.util
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src/xstar_tools/xstar/cpp/xstar_standalone.cpp"
RUNNER = ROOT / "tools/qualification/run_c5_npass_multipass_host_smoke_0_6_82_27_6.py"
MAN = ROOT / "qualification/npass_0_6_82_27_6/npass_hotfix_source_scope_0_6_82_27_6.json"


def runner():
    spec = importlib.util.spec_from_file_location("npass0276_runner", RUNNER)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def source_roundtrip(value: float) -> float:
    r4 = struct.unpack("=f", struct.pack("=f", value))[0]
    return struct.unpack("=f", struct.pack("=f", float(f"{r4:.3E}")))[0]


def test_0682276_version_abis_and_narrow_scope():
    py = (ROOT / "pyproject.toml").read_text()
    mk = (ROOT / "src/xstar_tools/xstar/cpp/Makefile").read_text()
    assert any(f'version = "{v}"' in py for v in ("0.6.82.27.6", "0.6.82.27.7", "0.6.82.27.8"))
    assert any(f'PACKAGE_VERSION ?= {v}' in mk for v in ("0.6.82.27.6", "0.6.82.27.7", "0.6.82.27.8"))
    obj = json.loads(MAN.read_text())
    if 'version = "0.6.82.27.7"' in py:
        succ = json.loads((ROOT / "qualification/npass_0_6_82_27_7/npass_hotfix_source_scope_0_6_82_27_7.json").read_text())
        for rel, old_hash in obj["predecessor_sha256"].items():
            expected = obj["candidate_changed_sha256"].get(rel, old_hash)
            assert succ["predecessor_sha256"][rel] == expected, rel
    assert obj["predecessor"] == "0.6.82.27.5"
    assert obj["predecessor_sdist_sha256"] == "fb95a27edef6f7ad88dd2eaf8d5737fd6b7d78743dccc12483f1d5d2a68f2680"
    assert obj["science_revision"] == "0.6.48.12.3.45.3.3.8"
    assert (obj["c_api_abi"], obj["production_zone_abi"], obj["fixed_state_abi"]) == (60487, 6048110, 60488)
    assert obj["numerical_source_count_predecessor"] == 137
    assert obj["intentional_numerical_source_changes"] == ["src/xstar_tools/xstar/cpp/xstar_standalone.cpp"]


def test_0682276_source_savd_keyword_roundtrip_matches_fortran_diagnostic_values():
    assert source_roundtrip(1.2017343044281006) == 1.2020000219345093
    assert source_roundtrip(4.6960086822509766) == 4.696000099182129
    assert source_roundtrip(316227780608.0) == 316199993344.0


def test_0682276_cpp_quantizes_all_source_savd_scalars_and_router_owner():
    text = CPP.read_text()
    assert "double source_savd_keyword_e3_v0682276(double value)" in text
    assert 'std::snprintf(buffer, sizeof(buffer), "%.3E"' in text
    fields = (
        "out.snapshot.temperature_t4", "out.pressure_dyn_cm2", "out.radius_cm",
        "out.radial_depth_cm", "out.step_size_cm", "out.column_cm2",
        "out.electron_fraction", "out.hydrogen_density_cm3", "out.zeta",
    )
    for field in fields:
        assert f"{field} = source_savd_keyword_e3_v0682276(" in text
    assert "zone_v0682273.outer_radius_cm = saved_v0682273.step_size_cm;" in text
    assert "source SAVD FITS-E3/REAL4 per-pass detail surface" in text


def test_0682276_runner_real4_readback_gate():
    mod = runner()
    assert mod.EXPECTED_VERSION == "0.6.82.27.6"
    assert mod.SAVD_SCALAR_KEYS == ("RINNER", "ROUTER", "RDEL", "TEMPERAT", "PRESSURE", "COLUMN", "XEE", "DENSITY", "LOGXI")
    assert mod._source_real4_readback(1.202) == 1.2020000219345093
    assert mod._source_real4_readback(4.696) == 4.696000099182129


def test_0682276_runner_detects_and_accepts_scalar_keyword_readback(tmp_path):
    try:
        from astropy.io import fits
    except Exception:
        return
    mod = runner()
    def make(path: Path, *, xee: float, router: float):
        hdus = [fits.PrimaryHDU(), fits.BinTableHDU(), fits.BinTableHDU.from_columns([])]
        hdr = hdus[2].header
        vals = {"RINNER": 3.162e11, "ROUTER": router, "RDEL": 0.0,
                "TEMPERAT": 4.696, "PRESSURE": 0.03, "COLUMN": 0.0,
                "XEE": xee, "DENSITY": 1.0e8, "LOGXI": 1.0}
        for key, value in vals.items(): hdr[key] = value
        fits.HDUList(hdus).writeto(path)
    ref = tmp_path / "ref.fits"; cand = tmp_path / "cand.fits"
    make(ref, xee=1.202, router=0.0); make(cand, xee=1.20200002, router=0.0)
    assert mod.compare_savd_scalar_keywords_file(cand, ref)["accept"]
    make(cand, xee=1.2017343, router=3.162e11)
    comp = mod.compare_savd_scalar_keywords_file(cand, ref)
    assert not comp["accept"]
    assert comp["mismatches"] >= 2


def test_0682276_keeps_27_5_rrc_and_thermal_sources_frozen_by_manifest():
    obj = json.loads(MAN.read_text())
    import hashlib
    for rel in ("src/xstar_tools/xstar/cpp/local_zone_engine.cpp", "src/xstar_tools/xstar/cpp/thermal_kernels.cpp"):
        got = hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()
        assert got == obj["predecessor_sha256"][rel]
