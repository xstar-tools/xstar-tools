from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from xstar_tools import BackendMode, XStarConfig, XStarData, XStarProducts, XStarResult, run_xstar
from xstar_tools.config import read_xstar_parameter_file
from xstar_tools.execution import PublicRunResult, SCIENCE_REVISION, ZONE_ABI_VERSION


def _data_dir(tmp_path: Path) -> Path:
    data = tmp_path / "data"
    data.mkdir()
    # Lightweight structural FITS header sufficient for the public locator.
    atdb = data / "atdb.fits"
    atdb.write_bytes(b"SIMPLE  =                    T".ljust(2880, b" "))
    (data / "coheat.dat").write_text("test coheat\n", encoding="utf-8")
    return data


def _fake_legacy(monkeypatch, seen: list[dict]):
    import xstar_tools.execution as ex

    def fake(**kwargs):
        seen.append(dict(kwargs))
        out = Path(kwargs["output_dir"])
        (out / "xout_step.log").write_text("step\n", encoding="utf-8")
        (out / "xout_abund1.fits").write_bytes(b"fits")
        return PublicRunResult(True, kwargs["mode"], {
            "ready": True,
            "returncode": 0,
            "output_dir": str(out),
            "timings": {"total_seconds": 1.25},
            "provenance": {"execution": {
                "requested_mode": kwargs["mode"],
                "actual_mode": kwargs["mode"],
                "package_version": "test",
                "science_revision": SCIENCE_REVISION,
                "zone_abi": ZONE_ABI_VERSION,
                "fallback_events": [],
            }},
        })

    monkeypatch.setattr(ex, "_run_xstar_legacy", fake)


def test_top_level_public_objects_are_importable():
    from xstar_tools import XStarConfig as C, XStarResult as R, XStarProducts as P, XStarData as D
    assert (C, R, P, D) == (XStarConfig, XStarResult, XStarProducts, XStarData)


def test_par_file_round_trip_preserves_literal_values(tmp_path):
    par = tmp_path / "xstar.par"
    par.write_text(
        'column,r,h,1.23456789E+22,,,column\n'
        'density,r,h,1e8,,,density\n'
        'spectrum,s,h,pow,,,spectrum\n'
        'lwrite,b,h,yes,,,lwrite\n',
        encoding="utf-8",
    )
    cfg = XStarConfig.from_par_file(par, data_dir=tmp_path, output_dir=tmp_path / "out")
    mapping = cfg.parameter_mapping()
    assert mapping["column"] == "1.23456789E+22"
    assert mapping["lwrite"] == "yes"
    exported = cfg.to_par_file(tmp_path / "canonical.par")
    reread = read_xstar_parameter_file(exported)
    assert reread == mapping
    assert exported.read_text().splitlines() == sorted(exported.read_text().splitlines())


def test_mapping_and_fortran_directory_sources(tmp_path):
    mapping_cfg = XStarConfig.from_mapping(
        {"density": "1e8", "spectrum": "pow"}, data_dir=tmp_path, output_dir=tmp_path / "m"
    )
    assert mapping_cfg.source_kind == "mapping"
    assert "density=1e8" in mapping_cfg.to_xstar_command()

    run_dir = tmp_path / "fortran"
    run_dir.mkdir()
    (run_dir / "run_xstar.sh").write_text("#!/bin/sh\nxstar density=1e8 spectrum=pow\n", encoding="utf-8")
    fortran_cfg = XStarConfig.from_fortran_run_directory(
        run_dir, data_dir=tmp_path, output_dir=tmp_path / "f"
    )
    assert fortran_cfg.source_kind == "fortran-run-directory"
    assert fortran_cfg.source_run_script() == (run_dir / "run_xstar.sh").resolve()
    assert fortran_cfg.parameter_mapping()["density"] == "1e8"


def test_data_locator_validates_required_local_data_without_download(tmp_path, monkeypatch):
    data_dir = _data_dir(tmp_path)
    data = XStarData.from_directory(data_dir)
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("download attempted")))
    report = data.validate()
    assert report.valid
    identity = data.identity()
    assert identity["atdb_sha256"] == hashlib.sha256((data_dir / "atdb.fits").read_bytes()).hexdigest()
    assert identity["coheat_sha256"] == hashlib.sha256((data_dir / "coheat.dat").read_bytes()).hexdigest()
    assert len(identity["constants_sha256"]) == 64


def test_invalid_data_fails_before_execution(tmp_path, monkeypatch):
    called = False
    import xstar_tools.execution as ex
    def fail(**kwargs):
        nonlocal called
        called = True
        raise AssertionError("execution should not start")
    monkeypatch.setattr(ex, "_run_xstar_legacy", fail)
    cfg = XStarConfig.from_mapping({"density": 1e8}, data_dir=tmp_path / "missing", output_dir=tmp_path / "out")
    with pytest.raises(FileNotFoundError):
        run_xstar(cfg)
    assert called is False


def test_invalid_backend_combination_fails_at_config_creation(tmp_path):
    with pytest.raises(ValueError, match="advanced backend overrides"):
        XStarConfig.from_mapping(
            {"density": 1e8}, data_dir=tmp_path, output_dir=tmp_path / "out",
            mode=BackendMode.ZONE_CPP, advanced_backend_overrides={"rates_backend": "python"},
        )
    with pytest.raises(ValueError, match="unknown advanced backend"):
        XStarConfig.from_mapping(
            {"density": 1e8}, data_dir=tmp_path, output_dir=tmp_path / "out",
            advanced_backend_overrides={"mystery_backend": "cpp"},
        )


def test_product_paths_are_deterministic(tmp_path):
    out = tmp_path / "same"
    one = XStarProducts(out)
    two = XStarProducts(out)
    assert one.as_dict() == two.as_dict()
    assert one.step_log == out.resolve() / "xout_step.log"
    assert len(one.expected_fits) == 9


def test_config_run_returns_typed_result_and_complete_provenance(tmp_path, monkeypatch):
    data_dir = _data_dir(tmp_path)
    seen: list[dict] = []
    _fake_legacy(monkeypatch, seen)
    cfg = XStarConfig.from_mapping(
        {"density": "1e8", "spectrum": "pow"}, data_dir=data_dir,
        output_dir=tmp_path / "run", mode=BackendMode.ZONE_PYTHON, progress=False,
    )
    result = run_xstar(cfg)
    assert isinstance(result, XStarResult)
    assert result.success and result.return_code == 0 and result.status == "success"
    assert result.products.abundances in result.produced_fits
    assert result.step_log.is_file()
    execution = result.provenance["execution"]
    for key in ("requested_mode", "actual_mode", "package_version", "science_revision", "zone_abi", "public_api", "input_source_kind", "threads", "reproducible"):
        assert key in execution
    assert result.provenance["data"]["atdb_sha256"]
    assert seen[0]["mode"] == "zone-python"


def test_public_config_delegates_to_frozen_mode_mapping(tmp_path, monkeypatch):
    data_dir = _data_dir(tmp_path)
    seen: list[dict] = []
    _fake_legacy(monkeypatch, seen)
    cfg = XStarConfig.from_mapping(
        {"density": "1e8"}, data_dir=data_dir, output_dir=tmp_path / "run",
        mode="zone-python", progress=False,
    )
    run_xstar(cfg)
    mapping = seen[-1]["_mapping_override"]
    assert mapping.public_mode == "zone-python"
    assert mapping.controller == "python"
    assert {mapping.global_backend, mapping.solver_backend, mapping.rates_backend, mapping.matrix_backend, mapping.emissivity_backend, mapping.opacity_backend, mapping.thermal_backend, mapping.engine_backend} == {"cpp"}


def test_advanced_overrides_are_explicit_and_report_advanced(tmp_path, monkeypatch):
    data_dir = _data_dir(tmp_path)
    seen: list[dict] = []
    _fake_legacy(monkeypatch, seen)
    cfg = XStarConfig.from_mapping(
        {"density": "1e8"}, data_dir=data_dir, output_dir=tmp_path / "run",
        mode="zone-python", progress=False,
        advanced_backend_overrides={"matrix_backend": "python"},
    )
    result = run_xstar(cfg)
    assert seen[-1]["_mapping_override"].matrix_backend == "python"
    assert result.provenance["execution"]["actual_mode"] == "advanced"


def test_output_directory_policy_and_repeated_runs_are_deterministic(tmp_path, monkeypatch):
    data_dir = _data_dir(tmp_path)
    seen: list[dict] = []
    _fake_legacy(monkeypatch, seen)
    out = tmp_path / "run"
    out.mkdir()
    (out / "stale.txt").write_text("stale", encoding="utf-8")
    strict = XStarConfig.from_mapping({"density": 1e8}, data_dir=data_dir, output_dir=out, progress=False)
    with pytest.raises(FileExistsError):
        run_xstar(strict)
    cfg = XStarConfig.from_mapping({"density": 1e8}, data_dir=data_dir, output_dir=out, progress=False, overwrite=True)
    first = run_xstar(cfg)
    assert not (out / "stale.txt").exists()
    marker = out / "old-extra.txt"; marker.write_text("old", encoding="utf-8")
    second = run_xstar(cfg)
    assert not marker.exists()
    assert first.products.as_dict() == second.products.as_dict()
    assert len(seen) == 2


def test_environment_does_not_leak_between_runs(tmp_path, monkeypatch):
    data_dir = _data_dir(tmp_path)
    seen: list[dict] = []
    import xstar_tools.execution as ex
    original_omp = os.environ.get("OMP_NUM_THREADS")
    original_repro = os.environ.get("XSTAR_TOOLS_REPRODUCIBLE")
    def fake(**kwargs):
        seen.append({"omp": os.environ.get("OMP_NUM_THREADS"), "repro": os.environ.get("XSTAR_TOOLS_REPRODUCIBLE")})
        return PublicRunResult(True, kwargs["mode"], {"ready": True, "returncode": 0, "provenance": {"execution": {"requested_mode": kwargs["mode"], "actual_mode": kwargs["mode"], "fallback_events": []}}})
    monkeypatch.setattr(ex, "_run_xstar_legacy", fake)
    cfg1 = XStarConfig.from_mapping({"density": 1}, data_dir=data_dir, output_dir=tmp_path / "r1", threads=3, reproducible=True, progress=False)
    cfg2 = XStarConfig.from_mapping({"density": 1}, data_dir=data_dir, output_dir=tmp_path / "r2", threads=1, reproducible=False, progress=False)
    run_xstar(cfg1); run_xstar(cfg2)
    assert seen == [{"omp": "3", "repro": "1"}, {"omp": "1", "repro": "0"}]
    assert os.environ.get("OMP_NUM_THREADS") == original_omp
    assert os.environ.get("XSTAR_TOOLS_REPRODUCIBLE") == original_repro


def test_legacy_keyword_api_remains_compatible(monkeypatch):
    import xstar_tools.execution as ex
    monkeypatch.setattr(ex, "_run_xstar_legacy", lambda **kwargs: PublicRunResult(True, kwargs["mode"], {"ready": True}))
    result = run_xstar(mode="pure-python", command="xstar density=1", output_dir="out")
    assert isinstance(result, PublicRunResult)
