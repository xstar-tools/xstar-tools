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
    current_027 = 'version = "0.6.82.27"' in pyproject
    current_0271 = 'version = "0.6.82.27.1"' in pyproject
    current_0272 = 'version = "0.6.82.27.2"' in pyproject or 'version = "0.6.82.27.3"' in pyproject or 'version = "0.6.82.27.4"' in pyproject or 'version = "0.6.82.27.5"' in pyproject
    current_0273 = 'version = "0.6.82.27.3"' in pyproject or 'version = "0.6.82.27.4"' in pyproject or 'version = "0.6.82.27.5"' in pyproject
    current_0274 = 'version = "0.6.82.27.4"' in pyproject or 'version = "0.6.82.27.5"' in pyproject
    current_0275 = 'version = "0.6.82.27.5"' in pyproject
    npass = None
    hotfix = None
    hotfix2 = None
    hotfix3 = None
    hotfix4 = None
    hotfix5 = None
    if current_027 or current_0271 or current_0272:
        npass = json.loads((ROOT / "qualification/npass_0_6_82_27/npass_source_scope_0_6_82_27.json").read_text())
    if current_0271 or current_0272:
        hotfix = json.loads((ROOT / "qualification/npass_0_6_82_27_1/npass_hotfix_source_scope_0_6_82_27_1.json").read_text())
    if current_0272:
        hotfix2 = json.loads((ROOT / "qualification/npass_0_6_82_27_2/npass_hotfix_source_scope_0_6_82_27_2.json").read_text())
    if current_0273:
        hotfix3 = json.loads((ROOT / "qualification/npass_0_6_82_27_3/npass_hotfix_source_scope_0_6_82_27_3.json").read_text())
    if current_0274:
        hotfix4 = json.loads((ROOT / "qualification/npass_0_6_82_27_4/npass_hotfix_source_scope_0_6_82_27_4.json").read_text())
    if current_0275:
        hotfix5 = json.loads((ROOT / "qualification/npass_0_6_82_27_5/npass_hotfix_source_scope_0_6_82_27_5.json").read_text())
    for rel, expected_0263 in hashes.items():
        current = hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()
        if npass is None:
            assert current == expected_0263, rel
            continue
        declared_027 = set(npass["intentional_numerical_source_changes"])
        if rel in declared_027:
            assert npass["predecessor_sha256"][rel] == expected_0263, rel
            expected_027 = npass["candidate_changed_sha256"][rel]
        else:
            assert npass["predecessor_sha256"][rel] == expected_0263, rel
            expected_027 = expected_0263
        if hotfix is None:
            assert current == expected_027, rel
            continue
        assert hotfix["predecessor_sha256"][rel] == expected_027, rel
        expected_0271 = hotfix["candidate_changed_sha256"].get(rel, expected_027)
        if hotfix2 is None:
            assert current == expected_0271, rel
            continue
        assert hotfix2["predecessor_sha256"][rel] == expected_0271, rel
        expected_0272 = hotfix2["candidate_changed_sha256"].get(rel, expected_0271)
        if hotfix3 is None:
            assert current == expected_0272, rel
            continue
        assert hotfix3["predecessor_sha256"][rel] == expected_0272, rel
        expected_0273 = hotfix3["candidate_changed_sha256"].get(rel, expected_0272)
        if hotfix4 is None:
            assert current == expected_0273, rel
            continue
        assert hotfix4["predecessor_sha256"][rel] == expected_0273, rel
        expected_0274 = hotfix4["candidate_changed_sha256"].get(rel, expected_0273)
        if hotfix5 is None:
            assert current == expected_0274, rel
            continue
        assert hotfix5["predecessor_sha256"][rel] == expected_0274, rel
        expected_0275 = hotfix5["candidate_changed_sha256"].get(rel, expected_0274)
        assert current == expected_0275, rel

