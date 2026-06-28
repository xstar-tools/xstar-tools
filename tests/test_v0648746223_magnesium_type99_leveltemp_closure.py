from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path

from xstar_tools.xstar.magnesium_type99_leveltemp_closure_v048746223 import (
    resolve_type99_context,
    source_leveltemp_value,
)
from xstar_tools.xstar.type99_leveltemp_case_contract_v048746223 import audit_case

ROOT = Path(__file__).resolve().parents[1]
ANALYZER = ROOT / "src/xstar_tools/xstar/magnesium_type99_leveltemp_closure_v048746223.py"


def _candidates(*pairs: tuple[int, float, float]):
    energies = [0.0] * 12
    weights = [0.0] * 12
    mask = 0
    for stage, energy, weight in pairs:
        energies[stage - 1] = energy
        weights[stage - 1] = weight
        mask |= 1 << (stage - 1)
    return mask, tuple(energies), tuple(weights)


def test_type99_active_second_pass_context():
    mask, energies, weights = _candidates(
        (5, 100.0, 2.0), (11, 1695.53125, 4.0), (12, 1884.255959375, 6.0)
    )
    energy, weight, owner = source_leveltemp_value(
        ion_stage=11,
        active_min_stage=5,
        active_max_stage=12,
        column=35,
        candidate_mask=mask,
        candidate_energy_ev=energies,
        candidate_statistical_weight=weights,
        incoming_energy_ev=77.0,
        incoming_statistical_weight=1.0,
    )
    assert (energy, weight, owner) == (1695.53125, 4.0, 11)


def test_type99_first_pass_owner_before_current_writer():
    mask, energies, weights = _candidates((11, 1695.0, 4.0), (12, 1884.0, 6.0))
    energy, weight, owner = source_leveltemp_value(
        ion_stage=6,
        active_min_stage=5,
        active_max_stage=12,
        column=35,
        candidate_mask=mask,
        candidate_energy_ev=energies,
        candidate_statistical_weight=weights,
        incoming_energy_ev=77.0,
        incoming_statistical_weight=1.0,
    )
    assert (energy, weight, owner) == (1884.0, 6.0, 12)


def test_type99_resolved_threshold_and_weight_ratio():
    bmask, be, bw = _candidates((11, 10.0, 2.0), (12, 20.0, 4.0))
    pmask, pe, pw = _candidates((11, 11.0, 2.0), (12, 21.0, 4.0))
    context = {
        "bound_column": 30,
        "parent_column": 46,
        "destination_column": 46,
        "bound_mask": bmask,
        "parent_mask": pmask,
        "destination_mask": pmask,
        "excited_parent_mode": 0,
        "incoming_bound": (1.0, 1.0),
        "incoming_parent": (2.0, 1.0),
        "incoming_destination": (2.0, 1.0),
        "excited_parent": (0.0, 0.0),
        "bound_energy": be,
        "bound_weight": bw,
        "parent_energy": pe,
        "parent_weight": pw,
        "destination_energy": pe,
        "destination_weight": pw,
    }
    resolved = resolve_type99_context(
        context, ion_stage=11, active_min_stage=5, active_max_stage=12
    )
    assert resolved["bound_energy_ev"] == 10.0
    assert resolved["parent_energy_ev"] == 11.0
    assert resolved["threshold_ev"] == 1.0
    assert resolved["swrat"] == 1.0


def _write_case(case: Path) -> None:
    case.mkdir()
    (case / "elements.csv").write_text(
        "element_index,element_z,normalization_row\n0,12,577\n"
    )
    fields = [
        "source_position", "record", "next_index", "element_index", "opcode",
        "data_type", "rate_type", "ion_index", "ion_stage", "lower_row", "upper_row",
        "real_offset", "real_count", "int_offset", "int_count", "density_scale",
        "line_energy_ev", "atomic_mass_amu", "matrix_enabled",
    ]
    reals: list[float] = []
    ints: list[int] = []
    with (case / "records.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for index in range(13):
            real_offset = len(reals)
            int_offset = len(ints)
            # nden=1, ntem=2, nxs=2 -> core real count 9.
            core = [8.0, 4.0, 5.0, 1.0, 2.0, 1.0, 1.0, 2.0, 1.0]
            compatibility = [11.0, 1.0, 2.0]
            incoming_and_excited = [10.0, 2.0, 11.0, 2.0, 11.0, 2.0, 0.0, 0.0]
            bound_energy = [0.0] * 12
            bound_weight = [0.0] * 12
            parent_energy = [0.0] * 12
            parent_weight = [0.0] * 12
            destination_energy = [0.0] * 12
            destination_weight = [0.0] * 12
            bound_energy[10], bound_weight[10] = 10.0, 2.0
            parent_energy[10], parent_weight[10] = 11.0, 2.0
            destination_energy[10], destination_weight[10] = 11.0, 2.0
            context = (
                compatibility + incoming_and_excited + bound_energy + bound_weight +
                parent_energy + parent_weight + destination_energy + destination_weight
            )
            assert len(context) == 83
            reals.extend(core + context)
            ints.extend([1, 2, 2, 30, 46, 46, 1 << 10, 1 << 10, 1 << 10, 0, 223])
            writer.writerow({
                "source_position": index + 1,
                "record": index + 1,
                "next_index": index + 1 if index < 12 else -1,
                "element_index": 0,
                "opcode": 99,
                "data_type": 99,
                "rate_type": 7,
                "ion_index": 11,
                "ion_stage": 11,
                "lower_row": 1,
                "upper_row": 2,
                "real_offset": real_offset,
                "real_count": len(core) + len(context),
                "int_offset": int_offset,
                "int_count": 11,
                "density_scale": 1.0,
                "line_energy_ev": 1.0,
                "atomic_mass_amu": 24.305,
                "matrix_enabled": 1,
            })
    (case / "reals.txt").write_text("".join(f"{value:.17g}\n" for value in reals))
    (case / "ints.txt").write_text("".join(f"{value}\n" for value in ints))


def test_type99_case_contract_accepts_and_rejects_stale(tmp_path: Path):
    case = tmp_path / "case"
    _write_case(case)
    assert audit_case(case)["result"] == "ACCEPT"
    values = (case / "ints.txt").read_text().splitlines()
    values[10] = "0"
    (case / "ints.txt").write_text("\n".join(values) + "\n")
    assert audit_case(case)["result"] == "REJECT"


def test_v2312_self_import_recursion_is_fixed():
    text = (ROOT / "src/xstar_tools/xstar/magnesium_type49_leveltemp_closure_v048746222.py").read_text()
    assert "from . import magnesium_type53_leveltemp_closure_v048746221 as v231" in text
    assert "from . import magnesium_type49_leveltemp_closure_v048746222 as v231" not in text


def test_type99_native_reevaluation_runs_after_active_selection_and_reuses_kernel():
    text = (ROOT / "src/xstar_tools/xstar/cpp/fixed_state_engine.cpp").read_text()
    active = text.index("const ActiveElementView active =")
    apply_call = text.index("apply_magnesium_type99_persistent_leveltemp_v048746223(", active)
    contributions = text.index("std::vector<xstar_element_contribution_v1> contributions", active)
    definition = text.index("void apply_magnesium_type99_persistent_leveltemp_v048746223(")
    end = text.index("PreliminaryIonBalance build_preliminary_ion_balance", definition)
    assert active < apply_call < contributions
    assert "evaluate_type99_source_faithful(" in text[definition:end]
    assert "build_type99_reduced_radiation(" in text
    assert "mg_cooling2" not in text[definition:end]


def test_type99_lowerer_serializes_energy_weight_context():
    text = (ROOT / "src/xstar_tools/xstar/native_fixed_program.py").read_text()
    assert "TYPE99_LEVELTEMP_LAYOUT_MAGIC_V048746223 = 223" in text
    for token in (
        "bound_candidate_energy", "bound_candidate_weight",
        "parent_candidate_energy", "parent_candidate_weight",
        "destination_candidate_energy", "destination_candidate_weight",
    ):
        assert token in text


def test_readiness_accepts(tmp_path: Path):
    output = tmp_path / "readiness.json"
    completed = subprocess.run(
        [
            "python", str(ROOT / "check_v048746223_magnesium_type99_leveltemp_closure_readiness.py"),
            "--package-dir", str(ROOT), "--output-json", str(output),
        ],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    report = json.loads(output.read_text())
    assert report["result"] == "ACCEPT"
    assert report["abi"] == 60487
    assert report["grid_path_changed"] is False
    assert report["aggregate_magnesium_cooling_override_added"] is False


def test_focused_analyzer_does_not_require_uncaptured_source_ans12() -> None:
    text = ANALYZER.read_text()
    assert 'NOT_CAPTURED_IN_SOURCE_ANSWER_CHANNELS' in text
    assert 'source[field]' in text  # ans3-ans6 comparison remains dynamic
    ans12_block = 'for field in ("ans1", "ans2")'
    assert ans12_block not in text
