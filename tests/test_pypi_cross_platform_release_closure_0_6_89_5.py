from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.6.89.5"


def load_bundle_module():
    path = ROOT / "tools/qualification/check_pypi_cross_platform_release_bundle_0_6_89_5.py"
    spec = importlib.util.spec_from_file_location("release_bundle_06895", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_authoritative_version_and_license():
    text = (ROOT / "pyproject.toml").read_text()
    assert f'version = "{VERSION}"' in text
    assert 'license = "GPL-3.0"' in text


def test_source_qualification_accepts():
    proc = subprocess.run(
        [sys.executable, "tools/qualification/check_pypi_cross_platform_release_closure_0_6_89_5.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "PYPI_CROSS_PLATFORM_RELEASE_CLOSURE_06895_RESULT=ACCEPT" in proc.stdout


def test_expected_wheel_count_is_24():
    mod = load_bundle_module()
    assert len(mod.expected_wheel_names()) == 24


def test_expected_platform_counts_are_6_12_6():
    names = load_bundle_module().expected_wheel_names()
    assert sum("manylinux_2_28_x86_64" in n for n in names) == 6
    assert sum("macosx_11_0_" in n for n in names) == 12
    assert sum("win_amd64" in n for n in names) == 6


def test_release_workflow_uses_native_hosted_runners():
    text = (ROOT / ".github/workflows/pypi-cross-platform-release.yml").read_text()
    assert "ubuntu-latest" in text
    assert "macos-15" in text
    assert "macos-15-intel" in text
    assert "windows-latest" in text


def test_release_workflow_does_not_publish_automatically():
    text = (ROOT / ".github/workflows/pypi-cross-platform-release.yml").read_text()
    assert "gh-action-pypi-publish" not in text
    assert "twine upload" not in text


def test_release_smokes_all_target_06895():
    for platform in ("linux", "macos", "windows"):
        text = (ROOT / f"tools/packaging/pypi_cross_platform_release_{platform}_smoke_0_6_89_5.py").read_text()
        assert VERSION in text
        assert "0.6.48.12.3.45.3.3.8" in text


def test_bundle_checker_accepts_synthetic_25_file_release(tmp_path):
    mod = load_bundle_module()
    release = tmp_path / "release-dist"
    release.mkdir()
    license_text = (ROOT / "LICENSE").read_text()
    for name in sorted(mod.expected_wheel_names()):
        system, profile = mod.expected_profile(name)
        dist = f"xstar_tools-{VERSION}.dist-info"
        native = {
            "package_version": VERSION,
            "native_built": True,
            "platform_system": system,
            "native_profile": profile,
            "c_api_abi": 60487,
            "production_zone_abi": 6048110,
            "mpi_included": False,
            "atomic_database_bundled": False,
        }
        with zipfile.ZipFile(release / name, "w") as zf:
            zf.writestr(f"{dist}/METADATA", f"Metadata-Version: 2.4\nName: xstar-tools\nVersion: {VERSION}\nLicense-Expression: GPL-3.0\n")
            zf.writestr(f"{dist}/licenses/LICENSE", license_text)
            zf.writestr("xstar_tools/xstar/cpp/native_build.json", json.dumps(native))
    root = f"xstar_tools-{VERSION}"
    sdist = release / f"xstar_tools-{VERSION}.tar.gz"
    import io
    with tarfile.open(sdist, "w:gz") as tf:
        for rel, data in {
            "pyproject.toml": f'[project]\nname="xstar-tools"\nversion = "{VERSION}"\nlicense = "GPL-3.0"\n'.encode(),
            "LICENSE": license_text.encode(),
        }.items():
            info = tarfile.TarInfo(f"{root}/{rel}")
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools/qualification/check_pypi_cross_platform_release_bundle_0_6_89_5.py"), "--release-dir", str(release)],
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "PYPI_CROSS_PLATFORM_RELEASE_CLOSURE_06895_BUNDLE_RESULT=ACCEPT" in proc.stdout
