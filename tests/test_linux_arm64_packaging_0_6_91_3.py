"""Guard the 0.6.91.3 *packaging* contract with synthetic ZIP/ELF fixtures.

These synthetic fixtures are deliberately NEVER astronomical reference outputs
or evidence of any real ARM64 host build.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import struct
import zipfile

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "tools/qualification/run_linux_arm64_packaging_host_0_6_91_3.py"
SPEC = importlib.util.spec_from_file_location("linux_arm64_packaging_06913", SCRIPT)
assert SPEC and SPEC.loader
pkg = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pkg)
ROOT = SCRIPT.parents[2]


def fake_elf(machine: int = 183, elf_class: int = 2) -> bytes:
    buf = bytearray(64)
    buf[:4] = b"\x7fELF"
    buf[4] = elf_class
    buf[5] = 1  # Little-endian
    struct.pack_into("<H", buf, 18, machine)
    return bytes(buf)


def make_fake_wheel(tmp_path: Path, *, tag: str = "cp313", machine: int = 183,
                    omit: str | None = None, field: str | None = None,
                    value=None, include_atdb: bool = False) -> Path:
    filename = f"xstar_tools-0.6.91.3-{tag}-{tag}-manylinux_2_28_aarch64.whl"
    dest = tmp_path / filename
    native = {
        "package_version": pkg.PACKAGE_VERSION,
        "science_revision": pkg.SCIENCE_REVISION,
        "c_api_abi": 60487,
        "production_zone_abi": 6048110,
        "platform_system": "Linux",
        "platform_machine": "aarch64",
        "native_profile": "pypi-linux",
        "native_built": True,
        "mpi_included": False,
        "atomic_database_bundled": False,
        "artifacts": list(pkg.ARTIFACTS),
    }
    if field is not None:
        native[field] = value
    files = {
        **{pkg.ROOT_REL + a: fake_elf(machine) for a in pkg.ARTIFACTS},
        "xstar_tools.libs/libcfitsio-qualifier.so.10": fake_elf(),
        pkg.ROOT_REL + "native_build.json": json.dumps(native).encode(),
        "xstar_tools-0.6.91.3.dist-info/WHEEL": (
            f"Wheel-Version: 1.0\nGenerator: synthetic-test\nRoot-Is-Purelib: false\n"
            f"Tag: {tag}-{tag}-manylinux_2_28_aarch64\n"
        ).encode(),
        "xstar_tools-0.6.91.3.dist-info/METADATA": b"Name: xstar-tools\nVersion: 0.6.91.3\n",
    }
    if include_atdb:
        files["xstar_tools/data/atdb.fits"] = b"synthetic not scientific data"
    if omit:
        files.pop(omit)
    with zipfile.ZipFile(dest, "w") as z:
        for path, data in files.items():
            z.writestr(path, data)
    return dest


def test_no_scientific_source_is_rebaselined():
    from hashlib import sha256
    data = json.loads((ROOT / "qualification/parity_freeze_current_source_hashes.json").read_text())
    assert len(data["files"]) == 51
    assert all(sha256((ROOT / path).read_bytes()).hexdigest() == rec["sha256"]
               for path, rec in data["files"].items())


def test_release_wheel_policy_configuration_remains_pinned():
    import tomllib
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert config["project"]["version"] == pkg.PACKAGE_VERSION
    cibw = config["tool"]["cibuildwheel"]
    assert cibw["linux"]["manylinux-x86_64-image"] == "manylinux_2_28"
    assert cibw["linux"]["manylinux-aarch64-image"] == "manylinux_2_28"
    assert cibw["linux"]["environment"]["XSTAR_TOOLS_NATIVE_PROFILE"] == "pypi-linux"
    assert "auditwheel repair" in cibw["linux"]["repair-wheel-command"]


def test_repaired_wheel_contract_accepts_fixtures(tmp_path):
    for python in ("cp311", "cp313"):
        path = make_fake_wheel(tmp_path, tag=python)
        result = pkg.validate_wheel(path)
        assert result["python_tag"] == python
        assert result["native_artifacts"] == 18
        assert result["science_revision"] == pkg.SCIENCE_REVISION


@pytest.mark.parametrize("field,value,pattern", [
    ("science_revision", "changed-science", "science_revision"),
    ("c_api_abi", 1234, "c_api_abi"),
    ("native_profile", "full", "native_profile"),
    ("mpi_included", True, "mpi_included"),
    ("native_built", False, "native_built"),
])
def test_wheel_provenance_tampering_rejected(tmp_path, field, value, pattern):
    path = make_fake_wheel(tmp_path, field=field, value=value)
    with pytest.raises(pkg.GateError, match=pattern):
        pkg.validate_wheel(path)


def test_wrong_elf_architecture_rejected(tmp_path):
    path = make_fake_wheel(tmp_path, machine=62)  # x86-64, not AArch64
    with pytest.raises(pkg.GateError, match="ELF64 AArch64"):
        pkg.validate_wheel(path)


def test_missing_native_object_rejected(tmp_path):
    path = make_fake_wheel(tmp_path, omit=pkg.ROOT_REL + "libxstar_api.so")
    with pytest.raises(pkg.GateError, match="missing native artifact"):
        pkg.validate_wheel(path)


def test_missing_vendored_cfitsio_rejected(tmp_path):
    path = make_fake_wheel(tmp_path, omit="xstar_tools.libs/libcfitsio-qualifier.so.10")
    with pytest.raises(pkg.GateError, match="wheel-local CFITSIO"):
        pkg.validate_wheel(path)


def test_packaged_atomic_database_rejected(tmp_path):
    path = make_fake_wheel(tmp_path, include_atdb=True)
    with pytest.raises(pkg.GateError, match="atomic database"):
        pkg.validate_wheel(path)


def test_bad_manylinux_tag_rejected(tmp_path):
    path = make_fake_wheel(tmp_path)
    path.rename(tmp_path / path.name.replace("manylinux_2_28_aarch64", "linux_aarch64"))
    with pytest.raises(pkg.GateError, match="manylinux_2_28_aarch64"):
        pkg.validate_wheel(tmp_path / "xstar_tools-0.6.91.3-cp313-cp313-linux_aarch64.whl")


def test_host_accept_cannot_be_claimed_from_preflight_only():
    script = SCRIPT.read_text()
    assert 'report: dict[str, object] = {"milestone": PACKAGE_VERSION, "host_result": "NOT_RUN"}' in script
    assert "native Linux ARM64 wheel qualification requires" in script
    assert "if not args.preflight_only:" in script
