"""Synthetic, metadata-only validation tests; never count as host science evidence."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import struct
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/qualification/run_cross_platform_closure_host_0_6_91_4.py"
SPEC = importlib.util.spec_from_file_location("cross_platform_06914", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def binary(host: str, *, wrong: bool = False) -> bytes:
    if host.startswith("linux-"):
        b = bytearray(64)
        b[:4] = b"\x7fELF"
        b[4:6] = b"\x02\x01"
        struct.pack_into("<H", b, 18, 62 if host.endswith("x86_64") else 183)
        if wrong:struct.pack_into("<H", b, 18, 0)
        return bytes(b)
    if host.startswith("macos-"):
        b = bytearray(64)
        b[:4] = b"\xcf\xfa\xed\xfe"
        struct.pack_into("<I", b, 4, 0x0100000C if host.endswith("arm64") else 0x01000007)
        if wrong:struct.pack_into("<I", b, 4, 0x00000003)
        return bytes(b)
    b = bytearray(512)
    b[:2] = b"MZ"
    struct.pack_into("<I", b, 0x3c, 0x80)
    b[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<H", b, 0x84, 0 if wrong else 0x8664)
    return bytes(b)


def fake_wheel(tmp_path: Path, host: str, policy: dict, *,
               altered: str | None = None, wrong_arch: bool = False) -> Path:
    system, machine, profile, tag, _, _ = mod.HOSTS[host]
    version = policy["package_version"]
    name = f"xstar_tools-{version}-cp313-cp313-{tag}.whl"
    dest = tmp_path / name
    provenance = {
        **policy, "platform_system": system, "platform_machine": machine,
        "native_profile": profile, "native_built": True,
        "mpi_included": False, "atomic_database_bundled": False,
        "artifacts": list(mod.native_artifacts(host)),
    }
    if altered:
        provenance[altered] = "unauthorized"
    vendor = ".dylibs" if host.startswith("macos-") else "xstar_tools.libs"
    cfitsio_ext = "dylib" if host.startswith("macos-") else "dll" if host.startswith("windows-") else "so.10"
    files = {
        **{f"xstar_tools/xstar/cpp/{a}": binary(host, wrong=wrong_arch)
           for a in mod.native_artifacts(host)},
        f"{vendor}/libcfitsio.test.{cfitsio_ext}": binary(host),
        "xstar_tools/xstar/cpp/native_build.json": json.dumps(provenance).encode(),
        f"xstar_tools-{version}.dist-info/WHEEL": (
            "Wheel-Version: 1.0\nRoot-Is-Purelib: false\n"
            f"Tag: cp313-cp313-{tag}\n"
        ).encode(),
        f"xstar_tools-{version}.dist-info/METADATA": (
            f"Name: xstar-tools\nVersion: {version}\n"
        ).encode(),
    }
    with zipfile.ZipFile(dest, "w") as z:
        for member, data in files.items():
            z.writestr(member, data)
    return dest


@pytest.mark.parametrize("host", sorted(mod.HOSTS))
def test_expected_wheel_synthetic(host, tmp_path):
    policy = {**mod.policy_for(ROOT), "package_version": "0.7.42"}
    wheel = fake_wheel(tmp_path, host, policy)
    row = mod.validate_wheel(wheel, host, policy)
    assert row["native_artifact_count"] == 18
    assert row["python_tag"] == "cp313"


@pytest.mark.parametrize("host", sorted(mod.HOSTS))
def test_wrong_machine_rejected(host, tmp_path):
    policy = mod.policy_for(ROOT)
    wheel = fake_wheel(tmp_path, host, policy, wrong_arch=True)
    with pytest.raises(mod.QualificationError, match="architecture"):
        mod.validate_wheel(wheel, host, policy)


def test_science_revision_forgery_rejected(tmp_path):
    policy = mod.policy_for(ROOT)
    wheel = fake_wheel(tmp_path, "linux-aarch64", policy, altered="science_revision")
    with pytest.raises(mod.QualificationError, match="science_revision"):
        mod.validate_wheel(wheel, "linux-aarch64", policy)


def test_workflow_has_five_hosts_and_no_publishing():
    workflow = (ROOT / ".github/workflows/cross-platform-closure.yml").read_text()
    for host in mod.HOSTS:
        assert host in workflow
    assert "gh-action-pypi-publish" not in workflow
    assert "cibuildwheel@" in workflow
    assert "run_cross_platform_closure_host_0_6_91_4.py" in workflow

AGG_SCRIPT = ROOT / "tools/qualification/aggregate_cross_platform_closure_0_6_91_4.py"
AGG_SPEC = importlib.util.spec_from_file_location("aggregate_cross_platform_06914", AGG_SCRIPT)
assert AGG_SPEC is not None and AGG_SPEC.loader is not None
aggregate = importlib.util.module_from_spec(AGG_SPEC)
AGG_SPEC.loader.exec_module(aggregate)


def generate_reports(directory: Path) -> None:
    policy = mod.policy_for(ROOT)
    for host in mod.HOSTS:
        target = directory / f"cross-platform-06914-{host}-evidence"
        target.mkdir()
        (target / "result.json").write_text(json.dumps({
            **policy, "host": host, "host_result": "ACCEPT",
            "wheel": {"python_tag": "cp313", "native_artifact_count": 18,
                      "filename": f"xstar_tools-{policy['package_version']}-cp313-cp313-fake.whl",
                      "sha256": "c" * 64},
        }))


def test_aggregate_requires_all_five_reports(tmp_path):
    generate_reports(tmp_path)
    result = aggregate.check_reports(ROOT, tmp_path)
    assert result["host_result"] == "ACCEPT"
    assert set(result["accepted_hosts"]) == set(mod.HOSTS)
    (tmp_path / "cross-platform-06914-macos-arm64-evidence" / "result.json").unlink()
    with pytest.raises(ValueError, match="missing native host"):
        aggregate.check_reports(ROOT, tmp_path)


def test_aggregate_rejects_false_science_revision(tmp_path):
    generate_reports(tmp_path)
    path = tmp_path / "cross-platform-06914-windows-amd64-evidence" / "result.json"
    data = json.loads(path.read_text())
    data["science_revision"] = "unqualified-science"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="metadata mismatch"):
        aggregate.check_reports(ROOT, tmp_path)
