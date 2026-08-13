from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _runner():
    path = ROOT / "tools/qualification/run_c5_radexp_density_host_smoke_0_6_82_26_3.py"
    spec = importlib.util.spec_from_file_location("radexp0263_runner", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_missing_density_fortran_is_recorded_as_legacy_unsafe_continue(tmp_path):
    runner = _runner()
    log = tmp_path / "fortran.log"
    log.write_text("****** -36.00 -10.00 Inf 1.00 ****** 6.00\n final print: 1\n")
    result = runner.classify_failure_result("fortran", "table_missing", runner.FAIL_CASES["table_missing"], log, 0)
    assert result["classification"] == "LEGACY_UNSAFE_CONTINUE"
    assert result["accept"] is True


def test_missing_density_cpp_and_python_remain_safe_rejects(tmp_path):
    runner = _runner()
    for backend, rc in (("cpp", 20), ("python", 1)):
        log = tmp_path / f"{backend}.log"
        log.write_text("missing density file: /tmp/density.dat\n")
        result = runner.classify_failure_result(backend, "table_missing", runner.FAIL_CASES["table_missing"], log, rc)
        assert result["classification"] == "SAFE_REJECT"
        assert result["accept"] is True


def test_radius_error_is_source_concordant_even_when_fortran_stop_returns_zero(tmp_path):
    runner = _runner()
    for backend, rc in (("fortran", 0), ("cpp", 20), ("python", 1)):
        log = tmp_path / f"{backend}.log"
        log.write_text("STOP radius error\n" if backend == "fortran" else "radius error\n")
        result = runner.classify_failure_result(backend, "table_nonmonotonic", runner.FAIL_CASES["table_nonmonotonic"], log, rc)
        assert result["classification"] == "radius error"
        assert result["accept"] is True


def test_all_0262_numerical_sources_are_frozen_by_sha256():
    manifest = json.loads((ROOT / "qualification/radexp_density_0_6_82_26_3/radexp_density_robustness_policy_0_6_82_26_3.json").read_text())
    hashes = manifest["numerical_source_sha256_from_0_6_82_26_2"]
    assert len(hashes) >= 130
    pyproject = (ROOT / "pyproject.toml").read_text()
    successor = 'version = "0.6.82.27"' in pyproject
    declared = set()
    chain = {}
    if successor:
        npass = json.loads((ROOT / "qualification/npass_0_6_82_27/npass_source_scope_0_6_82_27.json").read_text())
        declared = set(npass["intentional_numerical_source_changes"])
        chain = npass["predecessor_sha256"]
    for rel, expected in hashes.items():
        path = ROOT / rel
        current = hashlib.sha256(path.read_bytes()).hexdigest()
        if successor and rel in declared:
            # The .26.3 freeze is not rewritten; .27 must prove its predecessor
            # hash is exactly the frozen .26.3/.26.2 byte before changing it.
            assert chain[rel] == expected, rel
            assert current != expected, rel
        else:
            assert current == expected, rel
