from __future__ import annotations
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import types

import pytest

from xstar_tools.execution import (
    advanced_execution_provenance, infer_public_mode, resolve_mode, execution_provenance, run_xstar,
    SCIENCE_REVISION, ZONE_ABI_VERSION, package_version,
)


def test_public_mode_mapping_matches_frozen_aliases():
    pure = resolve_mode("pure-python")
    assert (pure.controller, pure.zone_backend, pure.global_backend, pure.solver_backend) == ("python", "python", "python", "python")
    assert {pure.rates_backend, pure.matrix_backend, pure.emissivity_backend, pure.opacity_backend, pure.thermal_backend, pure.engine_backend} == {"python"}

    accelerated = resolve_mode("zone-python")
    assert (accelerated.controller, accelerated.zone_backend, accelerated.global_backend, accelerated.solver_backend) == ("python", "python", "cpp", "cpp")
    assert {accelerated.rates_backend, accelerated.matrix_backend, accelerated.emissivity_backend, accelerated.opacity_backend, accelerated.thermal_backend, accelerated.engine_backend} == {"cpp"}

    assert resolve_mode("zone-cpp").zone_backend == "cpp-zone"
    assert resolve_mode("zone-all").zone_backend == "cpp-all"
    assert resolve_mode("xstar-cpp").standalone is True


def test_legacy_alias_inference():
    assert infer_public_mode(zone_backend="python", backend="python", solver_backend="python") == "pure-python"
    assert infer_public_mode(zone_backend="python", backend="cpp", solver_backend="cpp") == "zone-python"
    assert infer_public_mode(zone_backend="cpp-zone", backend="cpp", solver_backend="cpp") == "zone-cpp"
    assert infer_public_mode(zone_backend="cpp-all", backend="cpp", solver_backend="cpp") == "zone-all"
    assert infer_public_mode(zone_backend="python", backend="cpp", solver_backend="python") == "advanced"


def test_advanced_alias_provenance_has_same_observability_contract(tmp_path, monkeypatch):
    atdb = tmp_path / "atdb.fits"; atdb.write_bytes(b"atdb")
    coheat = tmp_path / "coheat.dat"; coheat.write_bytes(b"coheat")
    monkeypatch.setattr("xstar_tools.execution._api_library_identity", lambda: {"available": False, "version": None, "abi": None})
    monkeypatch.setattr("xstar_tools.execution.native_executable_info", lambda: {"available": False, "version": None})
    prov = advanced_execution_provenance(
        atdb_path=atdb, coheat_path=coheat, mapping={"backend": "cpp", "solver_backend": "python"}
    )
    for key in ("requested_mode", "actual_mode", "package_version", "science_revision", "c_api_abi", "zone_abi", "cpp", "cpu", "fallback_events", "atomic_data"):
        assert key in prov
    assert prov["requested_mode"] == prov["actual_mode"] == "advanced"
    assert prov["cpp"]["used"] is True


def test_provenance_has_required_fields_and_hashes(tmp_path, monkeypatch):
    atdb = tmp_path / "atdb.fits"; atdb.write_bytes(b"atdb")
    coheat = tmp_path / "coheat.dat"; coheat.write_bytes(b"coheat")
    monkeypatch.setattr("xstar_tools.execution.cpp_identity_for_mode", lambda mode: {"used": False})
    prov = execution_provenance(requested_mode="pure-python", atdb_path=atdb, coheat_path=coheat)
    for key in ("requested_mode", "actual_mode", "package_version", "science_revision", "c_api_abi", "zone_abi", "cpp", "cpu", "fallback_events", "atomic_data"):
        assert key in prov
    assert prov["science_revision"] == SCIENCE_REVISION
    assert prov["zone_abi"] == ZONE_ABI_VERSION
    assert len(prov["atomic_data"]["atdb_sha256"]) == 64
    assert len(prov["atomic_data"]["coheat_sha256"]) == 64


@dataclass
class FakeResult:
    seen: dict
    def as_dict(self):
        return {"ready": True, "output_dir": "/tmp/out", "provenance": {
            "atdb_path": "/tmp/atdb.fits",
            "solver_backend": {"requested": self.seen["solver"], "active": self.seen["solver"]},
            "rates_backend": {"requested": self.seen["rates"], "active": self.seen["rates"]},
            "matrix_backend": {"requested": self.seen["matrix"], "active": self.seen["matrix"]},
            "emissivity_backend": {"requested": self.seen["emissivity"], "active": self.seen["emissivity"]},
            "opacity_backend": {"requested": self.seen["opacity"], "active": self.seen["opacity"]},
            "thermal_backend": {"requested": self.seen["thermal"], "active": self.seen["thermal"]},
            "engine_backend": {"requested": self.seen["engine"], "active": self.seen["engine"]},
        }}


def test_run_public_python_modes_force_exact_backend_environment(monkeypatch):
    import xstar_tools.execution as ex
    monkeypatch.setattr(ex, "cpp_identity_for_mode", lambda mode: {"used": mode != "pure-python"})
    monkeypatch.setattr(ex, "atomic_data_identity", lambda *a, **k: {})
    seen_calls = []
    def fake(source, **kwargs):
        seen = {
            "global": os.environ["XSTAR_ATOMIC_BACKEND"],
            "solver": os.environ["XSTAR_ATOMIC_SOLVER_BACKEND"],
            "rates": os.environ["XSTAR_ATOMIC_RATES_BACKEND"],
            "matrix": os.environ["XSTAR_ATOMIC_MATRIX_BACKEND"],
            "emissivity": os.environ["XSTAR_ATOMIC_EMISSIVITY_BACKEND"],
            "opacity": os.environ["XSTAR_ATOMIC_OPACITY_BACKEND"],
            "thermal": os.environ["XSTAR_ATOMIC_THERMAL_BACKEND"],
            "engine": os.environ["XSTAR_ATOMIC_ENGINE_BACKEND"],
        }
        seen_calls.append(seen)
        return FakeResult(seen)
    fake_module = types.ModuleType("xstar_tools.xstar.physical_runner")
    fake_module.run_xstar_python_script = fake
    fake_module.run_xstar_python_command = fake
    monkeypatch.setitem(sys.modules, "xstar_tools.xstar.physical_runner", fake_module)
    run_xstar(mode="pure-python", run_script="run_xstar.sh", output_dir="out")
    assert set(seen_calls[-1].values()) == {"python"}
    run_xstar(mode="zone-python", run_script="run_xstar.sh", output_dir="out")
    assert set(seen_calls[-1].values()) == {"cpp"}


def test_run_zone_cpp_and_zone_all_select_frozen_internal_names(monkeypatch):
    import xstar_tools.xstar.cpp_backend_production_zone as pz
    import xstar_tools.execution as ex
    calls = []
    def fake(**kwargs):
        calls.append(kwargs["mode"])
        return {"ready": True, "provenance": {"zone_backend": {"requested": kwargs["mode"], "active": kwargs["mode"]}}}
    monkeypatch.setattr(pz, "run_shared_production_zone_backend", fake)
    monkeypatch.setattr(ex, "cpp_identity_for_mode", lambda mode: {"used": True})
    monkeypatch.setattr(ex, "atomic_data_identity", lambda *a, **k: {})
    run_xstar(mode="zone-cpp", run_script="run_xstar.sh", output_dir="out")
    run_xstar(mode="zone-all", run_script="run_xstar.sh", output_dir="out")
    assert calls == ["cpp-zone", "cpp-all"]


def test_native_mode_selects_run_production(monkeypatch, tmp_path):
    import xstar_tools.execution as ex
    exe = tmp_path / "xstar-cpp"; exe.write_text("", encoding="utf-8"); exe.chmod(0o755)
    atdb = tmp_path / "atdb.fits"; atdb.write_bytes(b"a")
    coheat = tmp_path / "coheat.dat"; coheat.write_bytes(b"c")
    monkeypatch.setattr(ex, "native_executable_path", lambda: exe)
    monkeypatch.setattr(ex, "native_executable_info", lambda: {"available": True, "path": str(exe), "version": SCIENCE_REVISION})
    monkeypatch.setattr(ex, "_native_payload_from_command", lambda *a, **k: {"atomic_database": str(atdb), "coheat_file": str(coheat)})
    calls = []
    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")
    monkeypatch.setattr(ex.subprocess, "run", fake_run)
    result = run_xstar(mode="xstar-cpp", command="xstar cfrac=1", atdb_path=atdb, coheat_path=coheat, output_dir=tmp_path / "out")
    assert result.ready
    assert calls[0][1] == "run-production"



def test_xstar_cpp_native_frontend_accepts_xstar_style_tokens_without_python(tmp_path):
    compiler = shutil.which("g++")
    if compiler is None:
        pytest.skip("g++ is required for the native frontend characterization")
    root = Path(__file__).resolve().parents[1]
    source = root / "src/xstar_tools/xstar/native/xstar_cpp_frontend.cpp"
    frontend = tmp_path / "xstar-cpp"
    proc = subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Wpedantic", "-O0", f'-DXSTAR_TOOLS_PACKAGE_VERSION="{package_version()}"', "-o", str(frontend), str(source), "-lstdc++fs"], text=True, capture_output=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "warning:" not in (proc.stdout + proc.stderr)

    capture = tmp_path / "argv.txt"
    sibling = tmp_path / "xstar_cpp"
    sibling.write_text('#!/bin/sh\nprintf "%s\n" "$@" > "$XSTAR_FRONTEND_CAPTURE"\n', encoding="utf-8")
    sibling.chmod(0o755)
    parameters = tmp_path / "parameters.json"
    atdb = tmp_path / "atdb.fits"; atdb.write_bytes(b"atomic-data")
    coheat = tmp_path / "coheat.dat"; coheat.write_bytes(b"coheat-data")
    env = dict(os.environ, XSTAR_FRONTEND_CAPTURE=str(capture))
    proc = subprocess.run([
        str(frontend), "run-xstar", "--atomic-db", str(atdb), "--coheat", str(coheat),
        "--output-dir", str(tmp_path / "out"), "--parameters-out", str(parameters),
        "cfrac=1", "column=1.23456789E+22", "spectrum=pow", "modelname=test_model",
    ], text=True, capture_output=True, env=env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert capture.read_text().splitlines()[:2] == ["run-production", "--parameters"]
    payload = json.loads(parameters.read_text())
    assert payload["column"] == "1.23456789E+22"
    assert payload["atomic_database"] == str(atdb)
    assert payload["coheat_file"] == str(coheat)
    native_prov = json.loads((tmp_path / "out/xstar_execution_provenance.json").read_text())
    assert native_prov["requested_mode"] == native_prov["actual_mode"] == "xstar-cpp"
    assert native_prov["package_version"] == package_version()
    assert native_prov["science_revision"] == SCIENCE_REVISION
    assert native_prov["c_api_abi"] > 0 and native_prov["zone_abi"] == ZONE_ABI_VERSION
    import hashlib
    assert native_prov["atomic_data"]["atdb_sha256"] == hashlib.sha256(b"atomic-data").hexdigest()
    assert native_prov["atomic_data"]["coheat_sha256"] == hashlib.sha256(b"coheat-data").hexdigest()



def test_xstar_cpp_makefile_links_filesystem_compatibility_library():
    root = Path(__file__).resolve().parents[1]
    makefile = (root / "src/xstar_tools/xstar/cpp/Makefile").read_text(encoding="utf-8")
    public_rule = makefile.split("$(PUBLIC_EXECUTABLE_TARGET):", 1)[1].split("\n\n", 1)[0]
    assert "$(FILESYSTEM_LIBS)" in public_rule
    assert "$(STDCXXFS_LIBS)" not in public_rule
    assert "XSTAR_TOOLS_PACKAGE_VERSION" in public_rule
    assert "PACKAGE_VERSION ?=" in makefile


def test_stable_mode_rejects_simultaneous_advanced_backend_flags():
    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ, PYTHONPATH=str(root / "src"))
    proc = subprocess.run([
        sys.executable, "-m", "xstar_tools.source_port_physical_runner_cli",
        "--mode", "pure-python", "--backend", "cpp", "--command", "xstar cfrac=1", "--atdb", "missing-atdb.fits", "--output-dir", "out",
    ], cwd=root, text=True, capture_output=True, env=env)
    assert proc.returncode == 2
    assert "cannot be combined with advanced backend flags" in proc.stderr


def test_backends_capability_api_exposes_all_public_modes():
    from xstar_tools import backends
    available = backends.available()
    assert tuple(available) == ("pure-python", "zone-python", "zone-cpp", "zone-all", "xstar-cpp")
    assert available["pure-python"] is True
    described = backends.describe()
    from xstar_tools.execution import package_version
    assert described["package_version"] == package_version()
    assert described["science_revision"] == SCIENCE_REVISION
    assert described["zone_abi"] == ZONE_ABI_VERSION
    assert set(described["modes"]) == set(available)


def test_unified_cli_backends_and_doctor_json():
    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ, PYTHONPATH=str(root / "src"))
    backends = subprocess.run([sys.executable, "-m", "xstar_tools.cli.main", "backends", "--json"], cwd=root, text=True, capture_output=True, env=env)
    assert backends.returncode == 0, backends.stdout + backends.stderr
    data = json.loads(backends.stdout)
    assert set(data["modes"]) == {"pure-python", "zone-python", "zone-cpp", "zone-all", "xstar-cpp"}
    doctor = subprocess.run([sys.executable, "-m", "xstar_tools.cli.main", "doctor", "--require", "pure-python", "--json"], cwd=root, text=True, capture_output=True, env=env)
    assert doctor.returncode == 0, doctor.stdout + doctor.stderr
    doctor_data = json.loads(doctor.stdout)["doctor"]
    assert doctor_data["required_mode"] == "pure-python"
    assert doctor_data["mode_ready"] is True
    assert doctor_data["ready"] is True

def test_public_contract_checker_passes():
    root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(["python", str(root / "tools/qualification/check_public_execution_modes.py")], cwd=root, text=True, capture_output=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "PUBLIC_EXECUTION_MODES_RESULT=ACCEPT" in proc.stdout
