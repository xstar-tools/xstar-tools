from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path

from xstar_tools.xstar import source_capture_trajectory_v0487462272 as trajectory
from xstar_tools.xstar import source_capture_resolver_v0487462271 as resolver

ROOT = Path(__file__).resolve().parents[1]
RELEASE = "0.6.48.7.46.23"


def _identity(sequence: int) -> tuple[str, int, int]:
    if sequence <= 21:
        return "dsec", 1, sequence
    if sequence == 22:
        return "dsec", 2, 1
    if sequence <= 40:
        return "dsec", 3, sequence - 22
    if sequence <= 57:
        return "dsec", 4, sequence - 40
    return "final", sequence - 57, {58: 22, 59: 2, 60: 19, 61: 18}[sequence]


def test_coherent_trajectory_is_built_only_from_selected_capture(tmp_path: Path) -> None:
    capture = tmp_path / "capture"
    capture.mkdir()
    inputs = []
    budgets = []
    for sequence in range(1, 62):
        kind, call, evaluation = _identity(sequence)
        temperature = "6.561529885564275" if sequence == 28 else format(6.0 + sequence / 1000.0, ".17g")
        inputs.append({
            "sequence": sequence,
            "kind": kind,
            "dsec_call_id": call,
            "evaluation_index": evaluation,
            "temperature_t4": temperature,
            "electron_fraction_input": "1.2003632957721315",
        })
        budgets.append({
            "sequence": sequence,
            "hmctot": "-0.003891367149827865" if sequence == 28 else "0.0",
            "elcter": "0.0",
        })
    for name, rows in (
        ("v0472_all61_input_states.csv", inputs),
        ("v0472_all61_thermal_budget.csv", budgets),
    ):
        with (capture / name).open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader(); writer.writerows(rows)
    output = tmp_path / "trajectory.csv"
    report = trajectory.build(capture, output)
    assert report["result"] == "ACCEPT"
    with output.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 61
    assert rows[27]["temperature_t4"] == "6.561529885564275"
    assert rows[27]["hmctot"] == "-0.003891367149827865"
    assert {key: sum(r["kind"] == "dsec" and int(r["call_index"]) == key for r in rows) for key in range(1, 5)} == {1: 21, 2: 1, 3: 18, 4: 17}


def test_resolver_skips_missing_paths_without_error_attempts(tmp_path: Path, monkeypatch) -> None:
    accepted = tmp_path / "accepted"
    accepted.mkdir()
    missing = tmp_path / "missing"
    monkeypatch.setattr(resolver, "_verify", lambda path: {
        "result": "ACCEPT", "errors": [], "evaluations": 61,
        "type99_capture_result": "ACCEPT",
    })
    report = resolver.resolve(
        candidates=[missing, accepted], search_roots=[], generated_dir=tmp_path / "generated",
        source_archive=tmp_path / "source.tar.gz", atdb_path=tmp_path / "atdb.fits",
        parameters_json=tmp_path / "parameters.json", coheat_path=None,
    )
    assert report["result"] == "ACCEPT"
    assert report["selected_dir"] == str(accepted.resolve())
    assert report["errors"] == []
    assert report["skipped_candidates"] == [{"path": str(missing.resolve()), "reason": "not_present"}]
    assert "attempts" not in report


def test_runner_uses_one_capture_derived_trajectory_for_replay_and_controller() -> None:
    outer = (ROOT / "run_v048746227_source_order_electron_controller_closure.sh").read_text()
    replay = (ROOT / "run_v048746227_native_fixed_replay.sh").read_text()
    canonical = (ROOT / "run_v048746217_canonical_thermal_controller_parity.sh").read_text()
    assert "source_capture_trajectory_v0487462272" in outer
    assert 'XSTAR_V048746227_TRAJECTORY_CSV="$TRAJECTORY"' in outer
    assert 'XSTAR_V048746217_TRAJECTORY_CSV="$TRAJECTORY"' in outer
    assert 'XSTAR_V048746217_SOURCE_TRAJECTORY_ALIGN=1' in outer
    assert "XSTAR_V048746227_TRAJECTORY_CSV" in replay
    assert "XSTAR_V048746217_TRAJECTORY_CSV" in canonical
    assert "--source-trajectory-align" in canonical


def test_cpp_alignment_is_fail_closed_and_qualification_only() -> None:
    source = (ROOT / "src/xstar_tools/xstar/cpp/xstar_standalone.cpp").read_text()
    assert "--source-trajectory-align requires --source-trajectory-guard" in source
    assert "canonical_e7_equal(proposed_temperature_t4, expected_t4)" in source
    assert "effective_temperature_t4 = expected_t4" in source
    assert "input.temperature_k = effective_temperature_t4 * 1.0e4" in source
    assert "evaluation->temperature_t4 = effective_temperature_t4" in source
    assert "source_trajectory_alignment_adjustments" in source
    assert 'source_trajectory_diverged\\": false' in source


def test_release_and_abi_are_retained() -> None:
    assert f'version = "{RELEASE}"' in (ROOT / "pyproject.toml").read_text()
    header = (ROOT / "src/xstar_tools/xstar/cpp/xstar_api.h").read_text()
    assert f'XSTAR_API_VERSION_STRING "{RELEASE}"' in header
    assert "60487" in header


def test_shell_and_readiness_contract(tmp_path: Path) -> None:
    for name in (
        "run_v048746227_source_order_electron_controller_closure.sh",
        "run_v048746227_native_fixed_replay.sh",
        "run_v048746217_canonical_thermal_controller_parity.sh",
    ):
        subprocess.run(["bash", "-n", str(ROOT / name)], check=True)
    output = tmp_path / "readiness.json"
    subprocess.run([
        "python", str(ROOT / "check_v048746227_source_order_electron_controller_closure_readiness.py"),
        "--package-dir", str(ROOT), "--output-json", str(output),
    ], check=True)
    assert json.loads(output.read_text())["result"] == "ACCEPT"
