from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path

import xstar_tools

ROOT = Path(__file__).resolve().parents[1]
FIXED = ROOT / "src/xstar_tools/xstar/cpp/fixed_state_engine.cpp"
LOWERER = ROOT / "src/xstar_tools/xstar/native_fixed_program.py"
UCALC = ROOT / "src/xstar_tools/xstar/ucalc.py"
CONSTANTS = ROOT / "src/xstar_tools/xstar/constants.def"
CONTROLLER = ROOT / "run_v048746217_canonical_thermal_controller_parity.sh"
REPLAY = ROOT / "run_v048746220_native_fixed_replay.sh"
MILESTONE = ROOT / "run_v048746220_magnesium_type57_thermal_closure.sh"


def test_release_version_and_abi() -> None:
    assert xstar_tools.__version__ == "0.6.48.7.46.21.10"
    assert "XSTAR_API_ABI_VERSION 60487u" in (ROOT / "src/xstar_tools/xstar/cpp/xstar_api.h").read_text()


def test_benchmark_constants_are_named_and_centralized() -> None:
    constants = CONSTANTS.read_text()
    assert "kLegacyBoltzmannEvPerT4, 0.861707" in constants
    assert "kCollisionRateCoefficientPerSqrtT4, 8.626e-8" in constants
    assert "kModernErgPerEv, 1.602176634e-12" in constants
    fixed = FIXED.read_text()
    block = fixed.split("case XSTAR_FIXED_OPCODE_TYPE60_CALLAWAY_COLLISION", 1)[1].split(
        "case XSTAR_FIXED_OPCODE_TYPE68_HELIKE_COLLISION", 1
    )[0]
    assert "kLegacyBoltzmannEvPerT4 * t_xstar" in block
    assert "kCollisionRateCoefficientPerSqrtT4 * ups" in block
    assert block.count("xstar_constants::kModernErgPerEv") == 2
    ucalc = UCALC.read_text()
    assert "ERG_PER_EV = LEGACY_COLLISION_ERG_PER_EV" in ucalc
    assert "XSTAR_SOURCE_ERG_PER_EV = MODERN_ERG_PER_EV" in ucalc


def test_type57_serializes_literal_source_threshold_and_uses_legacy_energy() -> None:
    lowerer = LOWERER.read_text().split("elif dt == 57:", 1)[1].split("elif dt in {60, 62}:", 1)[0]
    assert 'current_table = source_type13_tables.get(ion_index)' in lowerer
    assert 'source_e1_ev, source_eth_ev, source_lower_weight, source_parent_weight' in lowerer
    assert 'line_energy = source_eth_ev' in lowerer
    fixed = FIXED.read_text()
    block = fixed.split("case XSTAR_FIXED_OPCODE_TYPE57_COLLISIONAL_IONIZATION", 1)[1].split(
        "case XSTAR_FIXED_OPCODE_TYPE56_TABULATED_COLLISION", 1
    )[0]
    assert "XSTAR_QUALIFICATION_TYPE57_SOURCE_ENERGY" in block
    assert "source-faithful type57 requires literal e1/eth/g1/g2 payload" in block
    assert "xstar_constants::kLegacyCollisionErgPerEv" in block
    assert "independent Thermal parity requires source-local Type-57 energy transport" in fixed


def test_runners_enable_fresh_type57_replay() -> None:
    assert "XSTAR_QUALIFICATION_TYPE57_SOURCE_ENERGY=1" in CONTROLLER.read_text()
    assert "XSTAR_QUALIFICATION_TYPE57_SOURCE_ENERGY=1" in REPLAY.read_text()
    milestone = MILESTONE.read_text()
    assert "run_v048746220_native_fixed_replay.sh" in milestone
    assert "magnesium_type57_thermal_closure_v048746220" in milestone
    assert "20260727-magnesium-type57-source-local-thermal-v1" in milestone


def test_readiness_accepts(tmp_path: Path) -> None:
    output = tmp_path / "readiness.json"
    process = subprocess.run(
        [
            "python", str(ROOT / "check_v048746220_magnesium_type57_thermal_closure_readiness.py"),
            "--package-dir", str(ROOT), "--output-json", str(output),
        ],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert process.returncode == 0, process.stdout + process.stderr
    report = json.loads(output.read_text())
    assert report["result"] == "ACCEPT"
    assert report["module_contract"]["type57_literal_source_payload"] == 1
    assert report["module_contract"]["type6062_named_modern_ergsev"] == 2


def test_focused_analyzer_accepts_type57_and_prior_domains(tmp_path: Path) -> None:
    from xstar_tools.xstar import magnesium_type57_thermal_closure_v048746220 as focused

    source = tmp_path / "source"
    native = tmp_path / "native"
    source.mkdir()
    evaluation = native / "evaluation_0001"
    diagnostics = evaluation / "qualification_diagnostics"
    diagnostics.mkdir(parents=True)

    budget_fields = ["sequence", "h_cooling2", "he_non_type53_cooling", "mg_heating2", "mg_cooling2"]
    with (source / "v0472_all61_thermal_budget.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=budget_fields)
        writer.writeheader()
        writer.writerow({
            "sequence": 1, "h_cooling2": 2.0, "he_non_type53_cooling": 3.0,
            "mg_heating2": 4.0, "mg_cooling2": 5.0,
        })
    with (evaluation / "native_thermal_budget.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=budget_fields[1:])
        writer.writeheader()
        writer.writerow({
            "h_cooling2": 2.0, "he_non_type53_cooling": 3.0,
            "mg_heating2": 4.0, "mg_cooling2": 5.0,
        })

    answer_fields = ["sequence", "element_z", "record", "data_type", "ans1", "ans2", "ans3", "ans4", "ans5", "ans6"]
    source_rows: list[dict[str, object]] = []
    for record in range(469, 488):
        source_rows.append({
            "sequence": 1, "element_z": 1, "record": record, "data_type": 60,
            "ans1": 1.0, "ans2": 2.0, "ans3": 0.0, "ans4": 0.0,
            "ans5": 3.0, "ans6": 4.0,
        })
    for record in range(488, 492):
        source_rows.append({
            "sequence": 1, "element_z": 1, "record": record, "data_type": 62,
            "ans1": 1.0, "ans2": 2.0, "ans3": 0.0, "ans4": 0.0,
            "ans5": 3.0, "ans6": 4.0,
        })
    source_rows.append({
        "sequence": 1, "element_z": 2, "record": 826, "data_type": 50,
        "ans1": 0.0, "ans2": 0.0, "ans3": -0.25, "ans4": -0.5,
        "ans5": 0.0, "ans6": 0.0,
    })
    for offset in range(368):
        source_rows.append({
            "sequence": 1, "element_z": 12, "record": 40000 + offset, "data_type": 57,
            "ans1": 1.0e-8 + offset * 1.0e-14,
            "ans2": 2.0e-16 + offset * 1.0e-22,
            "ans3": 0.0, "ans4": 0.0,
            "ans5": -(2.0e-16 + offset * 1.0e-22) * 10.0,
            "ans6": -(1.0e-8 + offset * 1.0e-14) * 10.0,
        })
    with (source / "v0472_all61_thermal_answer_channels.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=answer_fields)
        writer.writeheader()
        writer.writerows(source_rows)

    native_fields = ["element_z", "record", "data_type", "line_energy_ev", "ans1", "ans2", "ans3", "ans4", "ans5", "ans6"]
    with (diagnostics / "evaluation_0001_records.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=native_fields)
        writer.writeheader()
        for row in source_rows:
            native_row = {field: row.get(field, 0.0) for field in native_fields}
            native_row["line_energy_ev"] = 10.0 if int(row["data_type"]) == 57 else 1.0
            writer.writerow(native_row)

    report = focused.audit(source, native, None, None, tmp_path / "differences.csv", sequences=(1,))
    assert report["result"] == "ACCEPT"
    assert report["magnesium_type57"]["source_rows"] == 368
    assert report["magnesium_type57"]["ans1_ans2_rejections"] == 0
    assert report["magnesium_type57"]["ans5_ans6_rejections"] == 0
    assert report["v21_9_regression"]["result"] == "ACCEPT"
