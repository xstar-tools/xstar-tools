from __future__ import annotations

import json
import subprocess
from pathlib import Path

import xstar_tools

ROOT = Path(__file__).resolve().parents[1]
FIXED = ROOT / "src/xstar_tools/xstar/cpp/fixed_state_engine.cpp"
RUNNER = ROOT / "run_v048746217_canonical_thermal_controller_parity.sh"


def test_release_version_and_abi() -> None:
    assert xstar_tools.__version__ == "0.6.48.7.46.21.8.1"
    api = (ROOT / "src/xstar_tools/xstar/cpp/xstar_api.h").read_text()
    assert "XSTAR_API_ABI_VERSION 60487u" in api


def test_type51_source_faithful_commit_is_all_element() -> None:
    text = FIXED.read_text()
    block = text.split("case XSTAR_FIXED_OPCODE_TYPE51_BT_COLLISION", 1)[1].split(
        "case XSTAR_FIXED_OPCODE_TYPE54_ANGULAR_REDIS", 1
    )[0]
    assert "XSTAR_QUALIFICATION_TYPE51_SOURCE_FAITHFUL" in block
    assert "XSTAR_QUALIFICATION_MG_TYPE51_SOURCE_FAITHFUL" in block
    assert "element.element_z == 12 &&\n                environment_flag" not in block.split("const bool source_faithful", 1)[1].split("const auto& committed", 1)[0]
    assert "source_ans2 * bt.eij_ev" in block
    assert "source_ans1 * bt.eij_ev" in block


def test_canonical_thermal_capture_occurs_after_matrix_closure() -> None:
    text = FIXED.read_text()
    closure = text.find("apply_matrix_closure_contribution_corrections(")
    append = text.rfind("canonical_thermal_builder.append_matrix_committed(contribution)")
    assert closure >= 0 and append > closure
    before_closure = text.split("if (matrix_construction_closure)", 1)[0]
    assert "canonical_thermal_builder.append_matrix_committed(contribution)" not in before_closure
    assert "contribution.ans3 = -contribution.ans2 * endpoint_energy_ev * kErgPerEv" in text
    assert "contribution.ans4 = -contribution.ans1 * endpoint_energy_ev * kErgPerEv" in text


def test_answer_diagnostics_follow_final_committed_stream() -> None:
    text = FIXED.read_text()
    sync = text.find("duplicate final committed contribution identity for diagnostics")
    append = text.rfind("canonical_thermal_builder.append_matrix_committed(contribution)")
    assert sync >= 0 and sync < append
    for field in range(1, 7):
        assert f"answers.ans{field} = committed->second->ans{field}" in text

def test_magnesium_type50_preservation_survives_post_closure_capture() -> None:
    text = FIXED.read_text()
    assert "contribution.ans3 = pre_closure_ans3" in text
    assert "contribution.ans4 = pre_closure_ans4" in text
    assert text.find("contribution.ans3 = pre_closure_ans3") < text.rfind(
        "canonical_thermal_builder.append_matrix_committed(contribution)"
    )


def test_independent_thermal_contract_fails_closed() -> None:
    text = FIXED.read_text()
    assert "independent Thermal parity requires the all-element source-faithful Type-51 contract" in text
    assert "independent Thermal parity requires post-closure He Type-50 Thermal energy reconstruction" in text
    runner = RUNNER.read_text()
    assert "XSTAR_QUALIFICATION_TYPE51_SOURCE_FAITHFUL=1" in runner
    assert "XSTAR_QUALIFICATION_HE_NON_TYPE53_TYPE50_ENERGY_REDUCTION=1" in runner
    assert "20260727-source-faithful-type51-post-closure-thermal-v6" in runner
    assert "v21.8 requires a fresh native replay" in runner


def test_v218_runner_regenerates_all_fixed_evaluations() -> None:
    replay = (ROOT / "run_v048746218_native_fixed_replay.sh").read_text()
    milestone = (ROOT / "run_v048746218_thermal_answer_path_corrections.sh").read_text()
    assert "seq -s, 1 61" in replay
    assert "XSTAR_QUALIFICATION_TYPE51_SOURCE_FAITHFUL=1" in replay
    assert "qualification_diagnostics" in replay
    assert "run_v048746218_native_fixed_replay.sh" in milestone
    assert "XSTAR_V048746217_NATIVE_EVALUATIONS_DIR" in milestone
    assert "XSTAR_V048746217_PREFLIGHT_ONLY=1" in milestone
    assert "read_resolved_dir" in milestone
    assert "20260727-resolved-baseline-path-persistence-v2" in milestone
    base_runner = RUNNER.read_text()
    assert "v048746217_baseline_v048746201.txt" in base_runner
    assert "v048746217_baseline_v0487461931.txt" in base_runner

def test_readiness_accepts(tmp_path: Path) -> None:
    output = tmp_path / "readiness.json"
    process = subprocess.run(
        [
            "python",
            str(ROOT / "check_v048746218_thermal_answer_path_correction_readiness.py"),
            "--package-dir", str(ROOT),
            "--output-json", str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert process.returncode == 0, process.stdout + process.stderr
    report = json.loads(output.read_text())
    assert report["result"] == "ACCEPT"
    assert report["module_contract"]["early_thermal_capture"] == 0
    assert report["module_contract"]["post_closure_thermal_capture"] == 1


def test_v218_preflight_uses_recursive_baseline_discovery(tmp_path: Path) -> None:
    import os

    search_root = tmp_path / "search"
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
        "result": "ACCEPT", "scientific_result": "ACCEPT",
        "systems_classified": 183, "systems_ieee_e10_acceptable": 183,
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
    env = dict(os.environ)
    env["XSTAR_V048746217_SEARCH_ROOTS"] = str(search_root)
    env["XSTAR_V048746218_PREFLIGHT_ONLY"] = "1"
    process = subprocess.run(
        [
            str(ROOT / "run_v048746218_thermal_answer_path_corrections.sh"),
            str(source_archive), str(atdb), str(base181), str(base2011), str(output), "10",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert process.returncode == 0, process.stdout + process.stderr
    assert "V048746218_PREFLIGHT=ACCEPT" in process.stdout
    assert "V048746217_PREFLIGHT=ACCEPT" in process.stdout
    assert json.loads((output / "v048746218_readiness_report.json").read_text())["result"] == "ACCEPT"
    assert (output / "v048746217_baseline_v048746201.txt").read_text().strip() == str(
        paths["v048746201_magnesium_type99_runtime_active_inventory_hotfix"].resolve()
    )
    assert (output / "v048746217_baseline_v0487461931.txt").read_text().strip() == str(
        paths["v0487461931_magnesium_type50_thermal_channel_preservation_hotfix"].resolve()
    )


def test_focused_analyzer_accepts_source_faithful_fixture(tmp_path: Path) -> None:
    import csv
    from xstar_tools.xstar import thermal_answer_path_correction_v048746218 as focused

    source = tmp_path / "source"
    native = tmp_path / "native"
    source.mkdir()
    evaluation = native / "evaluation_0001"
    diagnostics = evaluation / "qualification_diagnostics"
    diagnostics.mkdir(parents=True)

    with (source / "v0472_all61_thermal_budget.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["sequence", "h_cooling2", "he_non_type53_cooling"])
        writer.writeheader()
        writer.writerow({"sequence": 1, "h_cooling2": 2.0, "he_non_type53_cooling": 3.0})
    with (evaluation / "native_thermal_budget.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["h_cooling2", "he_non_type53_cooling"])
        writer.writeheader()
        writer.writerow({"h_cooling2": 2.0, "he_non_type53_cooling": 3.0})

    answer_fields = ["sequence", "element_z", "record", "data_type", "ans3", "ans4", "ans6"]
    source_rows = [
        {"sequence": 1, "element_z": 1, "record": record, "data_type": 51,
         "ans3": 0.0, "ans4": 0.0, "ans6": record * 1.0e-12}
        for record in focused.H_TYPE51_RECORDS
    ]
    source_rows.append({
        "sequence": 1, "element_z": 2, "record": 826, "data_type": 50,
        "ans3": -0.25, "ans4": -0.5, "ans6": 0.0,
    })
    with (source / "v0472_all61_thermal_answer_channels.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=answer_fields)
        writer.writeheader()
        writer.writerows(source_rows)
    native_fields = ["element_z", "record", "ans3", "ans4", "ans6"]
    with (diagnostics / "evaluation_0001_records.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=native_fields)
        writer.writeheader()
        for row in source_rows:
            writer.writerow({field: row[field] for field in native_fields})

    report = focused.audit(
        source, native, None, tmp_path / "differences.csv", sequences=(1,),
    )
    assert report["result"] == "ACCEPT"
    assert report["hydrogen_type51"]["source_rows"] == 23
    assert report["helium_type50"]["ans3_ans4_rejections"] == 0
    assert report["focused_rejections"] == 0
