from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_parity_freeze_metadata_contract():
    freeze = json.loads((ROOT / "qualification" / "parity_freeze.json").read_text())
    assert freeze["accepted_python_science_revision"] == "0.6.48.12.3.45.3.3.8"
    assert freeze["rejected_experiment"] == "0.6.48.12.3.45.3.3.9"
    assert freeze["frozen_cpp_revision"] == "0.6.48.12.3.44"
    assert freeze["production_zone_abi"] == 6048110
    assert freeze["thresholds"]["material_normalized_l1_max_exclusive"] == 0.01
    assert freeze["accepted_c5"]["routine_rerun"] is False
    assert {x["model"] for x in freeze["accepted_structural_exceptions"]} == {
        "helike_type69/ca19_xi2_ne1",
        "helike_type69/o7_ne1e10",
    }


def test_parity_freeze_artifacts_exist():
    assert (ROOT / "PARITY_FREEZE.md").is_file()
    assert (ROOT / "qualification" / "parity_freeze_science_hashes.json").is_file()
    assert (ROOT / "tools" / "qualification" / "check_parity_freeze.py").is_file()
    assert (ROOT / ".github" / "workflows" / "parity-freeze.yml").is_file()


def test_frozen_evidence_is_stable_and_versioned_tools_are_archived():
    freeze = json.loads((ROOT / "qualification" / "parity_freeze.json").read_text())
    refs = freeze["reference_hashes"]
    assert refs["frozen_cpp44_production_manifest_path"] == "qualification/frozen/cpp44/production_source_hashes_44.json"
    assert refs["option15_comparator_path"] == "qualification/frozen/option15/compare_step_log_science.py"
    assert refs["option23_comparator_path"] == "qualification/frozen/option23/compare_step_log_science.py"
    assert refs["option23_selftest_path"] == "qualification/frozen/option23/selftest_option23_comparator.py"
    for key in (
        "frozen_cpp44_production_manifest_path",
        "option15_comparator_path",
        "option23_comparator_path",
        "option23_selftest_path",
    ):
        assert (ROOT / refs[key]).is_file()
    active = ROOT / "tools" / "qualification"
    assert not [p for p in active.glob("v064*") if p.is_dir()]


def test_productization_entry_version_is_0651():
    freeze = json.loads((ROOT / "qualification" / "parity_freeze.json").read_text())
    assert freeze["productization_entry_version"] == "0.6.51"
    assert freeze["qualification_history"]["active_version_specific_directories"] == 0


def test_benchmark_reference_cleanup_is_enforced():
    benchmark_root = ROOT / "src" / "xstar_tools" / "benchmarks"
    assert sorted(p.name for p in benchmark_root.iterdir() if p.is_dir()) == [
        "v06486_qualification_reference_v0472",
        "v0648724_call1_thermal_leaf_reference",
    ]
    assert sorted(
        p.name
        for p in (benchmark_root / "v06486_qualification_reference_v0472").iterdir()
        if p.is_file()
    ) == ["reference_radiation_v0472_full.csv", "trajectory.csv"]
    assert not (benchmark_root / "v0648_compiled_case_helike_type69_mg11_ne1e8").exists()
    for obsolete in ("acceptance.py", "matrix.py", "smoke.py"):
        assert not (benchmark_root / obsolete).exists()
    freeze = json.loads((ROOT / "qualification" / "parity_freeze.json").read_text())
    assert freeze["benchmark_reference_cleanup"]["deprecated_compiled_case_bundled"] is False
    assert freeze["benchmark_reference_cleanup"]["unreferenced_benchmark_directories_archived"] == 13
