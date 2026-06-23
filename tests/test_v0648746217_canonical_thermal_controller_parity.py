from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from xstar_tools.xstar import canonical_thermal_controller_parity_v048746217 as parity

ROOT = Path(__file__).resolve().parents[1]


def test_canonical_e10_preserves_v216_semantics() -> None:
    assert parity.canonical_e10(2.1624460966087834e-15) == "2.1624460966e-15"
    assert parity.canonical_e10(2.1624460966087830e-15) == "2.1624460966e-15"


def test_numeric_roundoff_is_accepted_but_recorded() -> None:
    recorder = parity.Recorder()
    assert recorder.numeric(
        "committed_temperature", 2, "evaluation=2", "temperature",
        2.8591353411150710e-09, 2.8591353411150713e-09,
    )
    assert len(recorder.accepted_roundoff) == 1
    assert len(recorder.rejections) == 0
    assert recorder.accepted_roundoff[0]["classification"] == "E10_ACCEPTED_ROUNDOFF"


def test_visible_e10_difference_is_rejected() -> None:
    recorder = parity.Recorder()
    assert not recorder.numeric(
        "thermal_budget", 1, "kind=dsec;call=1;evaluation=1", "h_cooling2",
        6.034766640150065e-09, 6.0347716572508278e-09,
    )
    assert len(recorder.rejections) == 1
    assert recorder.rejections[0]["classification"] == "NUMERIC_REJECT"
    assert recorder.rejections[0]["source_e10"] != recorder.rejections[0]["native_e10"]


def test_structural_fields_remain_exact() -> None:
    recorder = parity.Recorder()
    assert recorder.exact("controller_structure", 1, "call=1", "evaluation", 1, 1)
    assert not recorder.exact("controller_termination", 1, "call=1", "reason", "tolerance", "maximum_evaluations")
    assert len(recorder.rejections) == 1
    assert recorder.rejections[0]["classification"] == "STRUCTURAL_REJECT"


def test_gate_reporting_cleanup_and_readiness() -> None:
    checker = (ROOT / "check_v048746217_canonical_thermal_controller_parity.py").read_text()
    assert "PRODUCT_LEVEL_PARITY" in checker
    assert "PRODUCTION_PROMOTION_STATUS" in checker
    assert "PRODUCTION_PROMOTION_BLOCKED=ACCEPT" not in checker
    process = subprocess.run(
        [
            sys.executable,
            str(ROOT / "check_v048746217_canonical_thermal_controller_parity_readiness.py"),
            "--package-dir", str(ROOT),
            "--output-json", str(ROOT / "v048746217_test_readiness_report.json"),
        ],
        capture_output=True,
        text=True,
    )
    assert process.returncode == 0, process.stdout + process.stderr
    assert json.loads(process.stdout)["result"] == "ACCEPT"


def test_checker_accepts_zero_rejection_contract(tmp_path: Path) -> None:
    checker_module = __import__(
        "check_v048746217_canonical_thermal_controller_parity",
        fromlist=["check"],
    )
    audit_dir = tmp_path / "audit"
    audit_dir.mkdir()
    audit = {
        "gates": {name: "ACCEPT" for name in checker_module.REQUIRED_GATES},
        "scientific_result": "ACCEPT",
        "accepted_roundoff_differences": 3,
        "rejected_differences": 0,
        "first_rejection": None,
    }
    baseline = {
        "result": "ACCEPT", "scientific_result": "ACCEPT",
        "systems_classified": 183, "systems_ieee_e10_acceptable": 183,
        "rejected_differences": 0,
    }
    source = {"result": "ACCEPT", "evaluations": 61}
    (audit_dir / "v048746217_thermal_controller_report.json").write_text(json.dumps(audit))
    baseline_path = tmp_path / "baseline.json"
    source_path = tmp_path / "source.json"
    baseline_path.write_text(json.dumps(baseline))
    source_path.write_text(json.dumps(source))
    result = checker_module.check(audit_dir, baseline_path, source_path)
    assert result["result"] == "ACCEPT"
    assert result["product_level_parity"] == "NOT_RUN"
    assert result["production_promotion_status"] == "BLOCKED_PENDING_PRODUCT_PARITY"


def test_runner_autodiscovers_baselines_and_omits_scalar_oracles(tmp_path: Path) -> None:
    runner = ROOT / "run_v048746217_canonical_thermal_controller_parity.sh"
    text = runner.read_text()
    assert "find_baseline_dir()" in text
    assert "resolve_named_dir()" in text
    assert '--mg-primary-budget-csv "$MG_BUDGET"' not in text
    assert '--call1-thermal-budget-csv "$MG_BUDGET"' not in text

    search_root = tmp_path / "search"
    search_root.mkdir()
    names = [
        "v048746216_all_sequence_ieee_e10_trajectory_parity",
        "v0487461721_continuum_preservation_gate_vocabulary_hotfix",
        "v048746172_continuum_freef_pow_semantics_hotfix",
        "v04874613_thermal_compact_population_state_transport",
        "v04874612_all61_thermal_state_consumption",
        "v04874610_matrix_closure",
        "v048746201_magnesium_type99_runtime_active_inventory_hotfix",
        "v0487461931_magnesium_type50_thermal_channel_preservation_hotfix",
    ]
    paths = {name: search_root / f"container_{name}" / name for name in names}
    for path in paths.values():
        path.mkdir(parents=True)

    (paths[names[0]] / "v048746216_checker_report.json").write_text(json.dumps({
        "result": "ACCEPT",
        "scientific_result": "ACCEPT",
        "systems_classified": 183,
        "systems_ieee_e10_acceptable": 183,
        "rejected_differences": 0,
    }))
    case = paths["v04874613_thermal_compact_population_state_transport"] / "native_case_all61"
    case.mkdir()
    (case / "records.csv").write_text("data_type\n")

    source_archive = tmp_path / "source.tar.gz"
    atdb = tmp_path / "atdb.fits"
    source_archive.write_bytes(b"")
    atdb.write_bytes(b"")
    base181 = tmp_path / "base181"
    base2011 = tmp_path / "base2011"
    base181.mkdir()
    base2011.mkdir()
    output = tmp_path / "out"

    env = dict(__import__("os").environ)
    env["XSTAR_V048746217_SEARCH_ROOTS"] = str(search_root)
    env["XSTAR_V048746217_PREFLIGHT_ONLY"] = "1"
    process = subprocess.run(
        [
            str(runner), str(source_archive), str(atdb), str(base181), str(base2011),
            str(output), "10",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert process.returncode == 0, process.stdout + process.stderr
    assert "V048746217_PREFLIGHT=ACCEPT" in process.stdout
    for name in names:
        assert str(paths[name].resolve()) in process.stderr


def test_full_controller_binds_source_sequence_per_evaluation(tmp_path: Path) -> None:
    cpp = ROOT / "src/xstar_tools/xstar/cpp"
    program = ROOT / "src/xstar_tools/benchmarks/v06485_active_family_phase2_fixture"
    trajectory = ROOT / "src/xstar_tools/benchmarks/v0648_compiled_case_helike_type69_mg11_ne1e8/trajectory.csv"
    output = tmp_path / "controller"
    diagnostics = tmp_path / "diagnostics"
    process = subprocess.run(
        [
            str(cpp / "xstar_cpp"), "run-fixed-dsec",
            "--case-dir", str(program),
            "--trajectory-csv", str(trajectory),
            "--diagnostics-dir", str(diagnostics),
            "--skip-fits",
            "--output-dir", str(output),
        ],
        cwd=cpp,
        capture_output=True,
        text=True,
    )
    # The development fixture is not expected to satisfy the 61-state science
    # reference, so return code 20 is a valid completed diagnostic run.
    assert process.returncode in {0, 20}, process.stdout + process.stderr
    combined = process.stdout + process.stderr
    assert "missing environment integer: XSTAR_QUALIFICATION_SOURCE_SEQUENCE" not in combined
    rows = list(__import__("csv").DictReader((output / "native_dsec_trajectory.csv").open()))
    assert len(rows) == 61
    by_identity = {
        (row["kind"], int(row["call_index"]), int(row["evaluation_index"])): int(row["sequence"])
        for row in rows
    }
    assert by_identity[("dsec", 1, 1)] == 1
    assert by_identity[("dsec", 2, 1)] == 22
    assert by_identity[("dsec", 3, 1)] == 23
    assert by_identity[("dsec", 4, 1)] == 41
    assert by_identity[("final", 1, 22)] == 58
    assert by_identity[("final", 2, 2)] == 59
    assert by_identity[("final", 3, 19)] == 60
    assert by_identity[("final", 4, 18)] == 61
    assert sorted(int(row["sequence"]) for row in rows) == list(range(1, 62))
    assert (diagnostics / "evaluation_0001_state.json").is_file()
    assert (diagnostics / "evaluation_0061_state.json").is_file()
