"""Verify that the production ARM64 release gate follows package metadata.

Synthetic ELF/ZIP fixtures only; these are not science or host-build evidence.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import struct
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/release/validate_linux_arm64_wheels.py"
SPEC = importlib.util.spec_from_file_location("arm64_release_wheel_validator", SCRIPT)
assert SPEC and SPEC.loader
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


def fake_elf(machine: int = 183) -> bytes:
    data = bytearray(64)
    data[:4] = b"\x7fELF"
    data[4] = 2
    data[5] = 1
    struct.pack_into("<H", data, 18, machine)
    return bytes(data)


def fake_wheel(tmp_path: Path, *, policy: dict, corrupt_field: str | None = None,
               corrupt_value=None, machine: int = 183) -> Path:
    ver = policy["package_version"]
    tag = "cp313"
    whl = tmp_path / f"xstar_tools-{ver}-{tag}-{tag}-manylinux_2_28_aarch64.whl"
    native = {
        "package_version": ver,
        "science_revision": policy["science_revision"],
        "platform_system": "Linux",
        "platform_machine": "aarch64",
        "native_profile": "pypi-linux",
        "native_built": True,
        "mpi_included": False,
        "atomic_database_bundled": False,
        "artifacts": list(validator.ARTIFACTS),
        **policy["abis"],
    }
    if corrupt_field:
        native[corrupt_field] = corrupt_value
    members = {
        **{validator.ROOT_REL + a: fake_elf(machine) for a in validator.ARTIFACTS},
        "xstar_tools.libs/libcfitsio-future.so.10": fake_elf(),
        validator.ROOT_REL + "native_build.json": json.dumps(native).encode(),
        f"xstar_tools-{ver}.dist-info/WHEEL": (
            f"Wheel-Version: 1.0\nRoot-Is-Purelib: false\n"
            f"Tag: {tag}-{tag}-manylinux_2_28_aarch64\n"
        ).encode(),
        f"xstar_tools-{ver}.dist-info/METADATA": (
            f"Name: xstar-tools\nVersion: {ver}\n"
        ).encode(),
    }
    with zipfile.ZipFile(whl, "w") as z:
        for path, payload in members.items():
            z.writestr(path, payload)
    return whl


def test_policy_follows_checkout_metadata(tmp_path):
    (tmp_path / "qualification").mkdir()
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "0.6.99.100"\n')
    (tmp_path / "qualification/parity_freeze.json").write_text(json.dumps({
        "science_revision": "0.6.90.5.5",
        "abis": {"c_api": 60487, "production_zone": 6048110},
    }))
    policy = validator.release_policy(tmp_path)
    assert policy["package_version"] == "0.6.99.100"
    assert policy["science_revision"] == "0.6.90.5.5"
    assert policy["abis"]["c_api_abi"] == 60487


def test_future_version_wheel_is_valid(tmp_path):
    policy = {**validator.release_policy(ROOT), "package_version": "0.6.99.100"}
    whl = fake_wheel(tmp_path, policy=policy)
    result = validator.validate_wheel(whl, policy=policy)
    assert result["python_tag"] == "cp313"
    assert result["science_revision"] == "0.6.90.5.5"


def test_wrong_version_is_rejected(tmp_path):
    policy = validator.release_policy(ROOT)
    whl = fake_wheel(tmp_path, policy=policy)
    changed = {**policy, "package_version": "0.6.99.100"}
    with pytest.raises(validator.GateError, match="version/CPython ABI"):
        validator.validate_wheel(whl, policy=changed)


@pytest.mark.parametrize("field,value", [
    ("science_revision", "unqualified-revision"),
    ("c_api_abi", 12345),
    ("production_zone_abi", 12345),
    ("native_built", False),
])
def test_provenance_tampering_is_rejected(tmp_path, field, value):
    policy = validator.release_policy(ROOT)
    whl = fake_wheel(tmp_path, policy=policy, corrupt_field=field, corrupt_value=value)
    with pytest.raises(validator.GateError, match=field):
        validator.validate_wheel(whl, policy=policy)


def test_wrong_architecture_is_rejected(tmp_path):
    policy = validator.release_policy(ROOT)
    whl = fake_wheel(tmp_path, policy=policy, machine=62)
    with pytest.raises(validator.GateError, match="ELF64 AArch64"):
        validator.validate_wheel(whl, policy=policy)


def test_release_workflow_no_historical_qualifier():
    workflow = (ROOT / ".github/workflows/pypi-release.yml").read_text()
    assert "tools/release/validate_linux_arm64_wheels.py" in workflow
    assert "run_linux_arm64_packaging_host_0_6_91_3.py" not in workflow
    assert "linux_arm64_packaging_06913_release_evidence" not in workflow


def _minimal_release_tree(tmp_path: Path) -> Path:
    """Create a release preflight tree without historical milestone workflows."""
    import shutil

    for rel in (
        "pyproject.toml",
        "qualification/parity_freeze.json",
        ".github/workflows/pypi-release.yml",
        "tools/packaging/build_manylinux_cfitsio.sh",
    ):
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, target)
    # Deliberately DO NOT install linux-arm64-packaging.yml.
    return tmp_path


def test_release_preflight_does_not_require_historical_workflow(tmp_path, monkeypatch):
    from types import SimpleNamespace

    root = _minimal_release_tree(tmp_path)
    assert not (root / ".github/workflows/linux-arm64-packaging.yml").exists()
    monkeypatch.setattr(validator.subprocess, "run", lambda *a, **kw:
                        SimpleNamespace(returncode=0, stdout="", stderr=""))
    result = validator.check_preflight(root)
    assert result["packaging_contract"] == "ACCEPT"
    assert result["source_version"] == validator.release_policy(ROOT)["package_version"]


@pytest.mark.parametrize("missing", [
    "runs-on: ubuntu-24.04-arm",
    "CIBW_ARCHS_LINUX: aarch64",
    "pypa/cibuildwheel@",
    "tools/release/validate_linux_arm64_wheels.py",
])
def test_release_preflight_rejects_missing_real_arm64_gate(tmp_path, monkeypatch, missing):
    from types import SimpleNamespace

    root = _minimal_release_tree(tmp_path)
    path = root / ".github/workflows/pypi-release.yml"
    content = path.read_text()
    start = content.index("  linux-arm64:\n")
    end = content.index("  macos-arm64:\n", start)
    arm64_job = content[start:end]
    assert missing in arm64_job
    path.write_text(content[:start] + arm64_job.replace(
        missing, "removed-qualification-contract", 1
    ) + content[end:])
    monkeypatch.setattr(validator.subprocess, "run", lambda *a, **kw:
                        SimpleNamespace(returncode=0, stdout="", stderr=""))
    with pytest.raises(validator.GateError, match="PyPI release ARM64 job"):
        validator.check_preflight(root)


def test_manifest_does_not_require_milestone_specific_workflow():
    manifest = (ROOT / "MANIFEST.in").read_text()
    assert "recursive-include .github/workflows *.yml" in manifest
    assert "include .github/workflows/linux-arm64-packaging.yml" not in manifest
