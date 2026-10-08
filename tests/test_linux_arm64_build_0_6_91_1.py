"""0.6.91.1 infrastructure-only tests; not ARM64 host science evidence."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "tools/qualification/run_linux_arm64_build_host_0_6_91_1.py"
SPEC = importlib.util.spec_from_file_location("linux_arm64_build_06911", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
arm = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(arm)


def test_arm64_native_host_only(monkeypatch, tmp_path):
    monkeypatch.setattr(arm.platform, "system", lambda: "Linux")
    monkeypatch.setattr(arm.platform, "machine", lambda: "x86_64")
    with pytest.raises(arm.GateError, match="native Linux aarch64"):
        arm.native_requirements(tmp_path, tmp_path)


def test_frozen_science_hash_rejects_tamper(tmp_path):
    original = b"accepted-scientific-source\n"
    rel = "src/xstar_tools/xstar/cpp/local_zone_engine.cpp"
    source = tmp_path / rel
    source.parent.mkdir(parents=True)
    source.write_bytes(original)
    manifest = tmp_path / "qualification/parity_freeze_current_source_hashes.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({
        "science_revision": "0.6.90.5.5",
        "files": {rel: {"sha256": hashlib.sha256(original).hexdigest()}},
    }))
    assert arm.source_hashes(tmp_path)[rel] == hashlib.sha256(original).hexdigest()
    source.write_bytes(original + b"unexpected-change")
    with pytest.raises(arm.GateError, match="frozen source mismatch"):
        arm.source_hashes(tmp_path)


def test_elf_inspection_rejects_non_arm_artifact(monkeypatch, tmp_path):
    (tmp_path / "libxstar_solver.so").write_bytes(b"not a valid AArch64 ELF")
    def fake_run(cmd, cwd, logfile, *, timeout=240):
        return "Class: ELF64\nMachine: Advanced Micro Devices X86-64\n"
    monkeypatch.setattr(arm, "run_command", fake_run)
    with pytest.raises(arm.GateError, match="wrong ELF class/machine"):
        arm.inspect_elf(tmp_path, tmp_path)


def test_result_records_only_host_accept_from_native_build():
    source = SCRIPT.read_text()
    assert 'report["host_result"] = "NOT_RUN"' in source
    assert 'report["host_result"] = "ACCEPT"' in source
    assert "source_hashes(copy)" in source
    assert "V068240_NATIVE=0" in source
    assert "V068240_LTO=0" in source
    assert "V068240_PGO_MODE=off" in source
