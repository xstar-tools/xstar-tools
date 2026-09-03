from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_build_support():
    spec = importlib.util.spec_from_file_location("xstar_tools_build_support_test_068921", ROOT / "build_support.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_source_checker_accepts() -> None:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools/qualification/check_pypi_native_wheel_linux_preflight_dependency_closure_0_6_89_2_1.py")],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "PYPI_NATIVE_WHEEL_LINUX_PREFLIGHT_DEPENDENCY_CLOSURE_068921_RESULT=ACCEPT" in proc.stdout


def test_pypi_profile_removes_only_python_embedding_plugin() -> None:
    support = load_build_support()
    full = set(support._native_artifacts("Linux", profile="full"))
    pypi = set(support._native_artifacts("Linux", profile="pypi-linux"))
    assert full - pypi == {"libxstar_backend_python.so"}
    assert not (pypi - full)
    assert {
        "libxstar_api.so",
        "libxstar_production_zone.so",
        "xstar-cpp",
        "xstar-xspec-initable",
        "xstar-xspec-table",
        "xstar-xspec",
    } <= pypi


def test_pypi_profile_is_linux_only() -> None:
    support = load_build_support()
    with pytest.raises(RuntimeError):
        support._native_artifacts("Darwin", profile="pypi-linux")
    with pytest.raises(RuntimeError):
        support._native_artifacts("Windows", profile="pypi-linux")


def test_pinned_bremsstrahlung_science_smoke() -> None:
    from xstar_tools.xstar.bremsstrahlung import bremem

    result = bremem(
        [10.0, 100.0, 1000.0],
        [9.0, 8.0, 7.0],
        [1.0e-8, 2.0e-8, 3.0e-8],
        temperature_k=1.0e6,
        hydrogen_density_cm3=1.0e8,
        electron_fraction_xee=1.2,
    )
    assert tuple(float(x) for x in result.brcems_after) == pytest.approx(
        (185.2554089800474, 65.18940067478347, 0.001897745194931447),
        rel=1.0e-14,
        abs=0.0,
    )
    assert tuple(float(x) for x in result.opakc_after_cm_inv) == (
        1.0e-8,
        2.0e-8,
        3.0e-8,
    )


def _write_synthetic_repaired_wheel(wheel: Path) -> None:
    cpp = "xstar_tools/xstar/cpp/"
    dist = "xstar_tools-0.6.89.2.1.dist-info/"
    required = [
        "libxstar_solver.so",
        "libxstar_rates.so",
        "libxstar_matrix.so",
        "libxstar_emissivity.so",
        "libxstar_opacity.so",
        "libxstar_thermal.so",
        "libxstar_engine.so",
        "libxstar_local_zone.so",
        "libxstar_final_recompute.so",
        "libxstar_production_zone.so",
        "libxstar_xspec_table.so",
        "libxstar_api.so",
        "libxstar_backend_cpp.so",
        "xstar_cpp",
        "xstar-cpp",
        "xstar-xspec-initable",
        "xstar-xspec-table",
        "xstar-xspec",
    ]
    metadata = {
        "schema": "xstar-tools-native-build-v2",
        "package_version": "0.6.89.2.1",
        "science_revision": "0.6.48.12.3.45.3.3.8",
        "c_api_abi": 60487,
        "production_zone_abi": 6048110,
        "policy": "required",
        "platform_system": "Linux",
        "platform_machine": "x86_64",
        "platform_key": "linux",
        "native_profile": "pypi-linux",
        "native_built": True,
        "artifacts": required,
        "mpi_included": False,
        "atomic_database_bundled": False,
    }
    wheel_text = (
        "Wheel-Version: 1.0\n"
        "Generator: auditwheel\n"
        "Root-Is-Purelib: false\n"
        "Tag: cp313-cp313-manylinux_2_27_x86_64\n"
        "Tag: cp313-cp313-manylinux_2_28_x86_64\n"
    )
    entry_points = (
        "[console_scripts]\n"
        "xstar-cpp = xstar_tools.cli.xstar_cpp:main\n"
        "xstar-xspec-initable = xstar_tools.cli.native_exec:main_xstar_xspec_initable\n"
        "xstar-xspec-table = xstar_tools.cli.native_exec:main_xstar_xspec_table\n"
        "xstar-xspec = xstar_tools.cli.native_exec:main_xstar_xspec\n"
    )
    with zipfile.ZipFile(wheel, "w") as zf:
        zf.writestr(cpp + "native_build.json", json.dumps(metadata))
        for name in required:
            zf.writestr(cpp + name, b"synthetic")
        zf.writestr("xstar_tools.libs/libcfitsio-abc123.so.10", b"synthetic")
        zf.writestr(dist + "WHEEL", wheel_text)
        zf.writestr(dist + "entry_points.txt", entry_points)


def test_artifact_checker_accepts_auditwheel_multi_policy_tag(tmp_path: Path) -> None:
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    wheel = wheelhouse / (
        "xstar_tools-0.6.89.2.1-cp313-cp313-"
        "manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl"
    )
    _write_synthetic_repaired_wheel(wheel)
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools/qualification/check_pypi_native_wheel_linux_artifacts_0_6_89_2_1.py"),
            "--wheelhouse",
            str(wheelhouse),
            "--selector",
            "cp313-manylinux_x86_64",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "PYPI_NATIVE_WHEEL_LINUX_PREFLIGHT_DEPENDENCY_CLOSURE_068921_ARTIFACT_WHEEL_METADATA_MANYLINUX=ACCEPT" in proc.stdout
    assert "PYPI_NATIVE_WHEEL_LINUX_PREFLIGHT_DEPENDENCY_CLOSURE_068921_ARTIFACT_RESULT=ACCEPT" in proc.stdout


def test_workflow_installs_build_backend_requirements_before_source_checker() -> None:
    workflow = (ROOT / ".github/workflows/pypi-native-wheel-linux.yml").read_text(encoding="utf-8")
    install = 'python -m pip install --upgrade "setuptools>=77" wheel'
    checker = "check_pypi_native_wheel_linux_preflight_dependency_closure_0_6_89_2_1.py"
    assert install in workflow
    assert checker in workflow
    assert workflow.index(install) < workflow.index(checker)


def test_build_support_and_native_runtime_match_06892() -> None:
    import hashlib
    def normalized(path: Path) -> str:
        data = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        return hashlib.sha256(data).hexdigest()
    assert normalized(ROOT / "build_support.py") == "4886ffc24bd0742436012321da14fd94ef69de67642deb69eaaf191c75dde720"
    assert normalized(ROOT / "src/xstar_tools/native_runtime.py") == "c764699e128f7c0c457124001d26ddafa587859a7e737c417d2b117998ea3bd1"


def test_missing_setuptools_is_controlled_reject_not_traceback() -> None:
    proc = subprocess.run(
        [sys.executable, "-S", str(ROOT / "tools/qualification/check_pypi_native_wheel_linux_preflight_dependency_closure_0_6_89_2_1.py")],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode != 0
    assert "PYPI_NATIVE_WHEEL_LINUX_PREFLIGHT_DEPENDENCY_CLOSURE_068921_SETUPTOOLS_AVAILABLE=REJECT" in proc.stdout
    assert "Traceback" not in proc.stdout + proc.stderr
