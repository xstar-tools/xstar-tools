from __future__ import annotations

import csv
import json
import math
import subprocess
from pathlib import Path

import xstar_tools

ROOT = Path(__file__).resolve().parents[1]
FIXED = ROOT / "src/xstar_tools/xstar/cpp/fixed_state_engine.cpp"
CONTROLLER = ROOT / "run_v048746217_canonical_thermal_controller_parity.sh"
REPLAY = ROOT / "run_v048746219_native_fixed_replay.sh"
MILESTONE = ROOT / "run_v048746219_hydrogen_type6062_thermal_closure.sh"


def test_release_version_and_abi() -> None:
    assert xstar_tools.__version__ == "0.6.48.7.46.21.9"
    assert "XSTAR_API_ABI_VERSION 60487u" in (ROOT / "src/xstar_tools/xstar/cpp/xstar_api.h").read_text()


def test_type6062_source_path_matches_fortran_constants_and_order() -> None:
    text = FIXED.read_text()
    helper = text.split("double callaway_upsilon(", 1)[1].split("double type68_upsilon", 1)[0]
    block = text.split("case XSTAR_FIXED_OPCODE_TYPE60_CALLAWAY_COLLISION", 1)[1].split(
        "case XSTAR_FIXED_OPCODE_TYPE68_HELIKE_COLLISION", 1
    )[0]
    assert "XSTAR_QUALIFICATION_TYPE6062_SOURCE_FAITHFUL" in block
    assert "kLegacyBoltzmannEvPerT4 * t_xstar" in block
    assert "1.0e-16 + upper.statistical_weight" in block
    assert "1.0e-16 + lower.statistical_weight" in block
    assert "c.ans6=c.ans1*delta_ev*kErgPerEv" in block
    assert "kLegacyBoltzmannEvPerT4" in helper
    assert helper.count("std::pow(tt,static_cast<int>(k-2))") == 2


def test_sequence1_record469_ratio_is_exact_boltzmann_signature() -> None:
    source = 6.428404389666558e-11
    native = 6.4284319380718887e-11
    transition_ev = 12.08749866
    t4 = 100.0
    expected = math.exp(-transition_ev / (0.8617333262145 * t4)) / math.exp(
        -transition_ev / (0.861707 * t4)
    )
    assert math.isclose(native / source, expected, rel_tol=2.0e-15, abs_tol=0.0)


def test_independent_thermal_and_runners_enable_type6062() -> None:
    fixed = FIXED.read_text()
    assert "independent Thermal parity requires the source-faithful Type-60/62 collision contract" in fixed
    assert "XSTAR_QUALIFICATION_TYPE6062_SOURCE_FAITHFUL=1" in CONTROLLER.read_text()
    assert "XSTAR_QUALIFICATION_TYPE6062_SOURCE_FAITHFUL=1" in REPLAY.read_text()
    milestone = MILESTONE.read_text()
    assert "run_v048746219_native_fixed_replay.sh" in milestone
    assert "hydrogen_type6062_thermal_closure_v048746219" in milestone
    assert "20260727-hydrogen-type6062-source-faithful-thermal-v1" in milestone


def test_readiness_accepts(tmp_path: Path) -> None:
    output = tmp_path / "readiness.json"
    process = subprocess.run(
        [
            "python", str(ROOT / "check_v048746219_hydrogen_type6062_thermal_closure_readiness.py"),
            "--package-dir", str(ROOT), "--output-json", str(output),
        ],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert process.returncode == 0, process.stdout + process.stderr
    report = json.loads(output.read_text())
    assert report["result"] == "ACCEPT"
    assert report["module_contract"]["analyzer_dynamic_type_domain"] == 1
    assert report["module_contract"]["independent_thermal_requires_type6062"] == 1


def test_focused_analyzer_accepts_type6062_and_helium_fixture(tmp_path: Path) -> None:
    from xstar_tools.xstar import hydrogen_type6062_thermal_closure_v048746219 as focused

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
    source_rows = []
    for record in range(469, 488):
        source_rows.append({
            "sequence": 1, "element_z": 1, "record": record, "data_type": 60,
            "ans3": 0.0, "ans4": 0.0, "ans6": record * 1.0e-12,
        })
    for record in range(488, 492):
        source_rows.append({
            "sequence": 1, "element_z": 1, "record": record, "data_type": 62,
            "ans3": 0.0, "ans4": 0.0, "ans6": record * 1.0e-12,
        })
    # A Type-51 row must not be mistaken for the Hydrogen target domain.
    source_rows.append({
        "sequence": 1, "element_z": 1, "record": 900, "data_type": 51,
        "ans3": 0.0, "ans4": 0.0, "ans6": 9.0,
    })
    source_rows.append({
        "sequence": 1, "element_z": 2, "record": 826, "data_type": 50,
        "ans3": -0.25, "ans4": -0.5, "ans6": 0.0,
    })
    with (source / "v0472_all61_thermal_answer_channels.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=answer_fields)
        writer.writeheader()
        writer.writerows(source_rows)

    native_fields = ["element_z", "record", "data_type", "ans3", "ans4", "ans6"]
    with (diagnostics / "evaluation_0001_records.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=native_fields)
        writer.writeheader()
        for row in source_rows:
            writer.writerow({field: row[field] for field in native_fields})

    report = focused.audit(source, native, None, tmp_path / "differences.csv", sequences=(1,))
    assert report["result"] == "ACCEPT"
    assert report["hydrogen_type6062"]["source_rows"] == 23
    assert report["hydrogen_type6062"]["source_type_counts"] == {60: 19, 62: 4}
    assert report["hydrogen_type6062"]["ans6_rejections"] == 0
    assert report["helium_type50"]["ans3_ans4_rejections"] == 0
    assert report["focused_rejections"] == 0
