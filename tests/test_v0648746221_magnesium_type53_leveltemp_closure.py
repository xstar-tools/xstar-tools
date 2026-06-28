from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path

from xstar_tools.xstar.magnesium_type53_leveltemp_closure_v048746221 import (
    source_leveltemp_destination_energy,
)

ROOT = Path(__file__).resolve().parents[1]


def _candidates(*pairs: tuple[int, float]) -> tuple[int, tuple[float, ...]]:
    values = [0.0] * 12
    mask = 0
    for stage, value in pairs:
        values[stage - 1] = value
        mask |= 1 << (stage - 1)
    return mask, tuple(values)


def test_source_leveltemp_retains_last_active_first_pass_owner() -> None:
    mask, values = _candidates((6, 610.0), (7, 710.0), (11, 1695.53125))
    value, owner, column = source_leveltemp_destination_energy(
        ion_stage=6,
        active_min_stage=5,
        active_max_stage=12,
        destination_column=35,
        candidate_mask=mask,
        candidate_energy_ev=values,
        incoming_energy_ev=104.43699645996094,
    )
    assert column == 35
    assert owner == 6
    assert value == 610.0


def test_source_leveltemp_first_pass_owner_survives_when_second_pass_has_no_writer() -> None:
    mask, values = _candidates((11, 1695.53125), (12, 1900.0))
    value, owner, column = source_leveltemp_destination_energy(
        ion_stage=6,
        active_min_stage=5,
        active_max_stage=11,
        destination_column=35,
        candidate_mask=mask,
        candidate_energy_ev=values,
        incoming_energy_ev=104.43699645996094,
    )
    assert column == 35
    assert owner == 11
    assert value == 1695.53125


def test_source_leveltemp_second_pass_active_owner_wins() -> None:
    mask, values = _candidates((3, 325.0), (4, 425.0), (5, 525.0), (6, 625.0))
    value, owner, column = source_leveltemp_destination_energy(
        ion_stage=5,
        active_min_stage=3,
        active_max_stage=6,
        destination_column=25,
        candidate_mask=mask,
        candidate_energy_ev=values,
        incoming_energy_ev=999.0,
    )
    assert column == 25
    assert owner == 5
    assert value == 525.0


def test_source_leveltemp_unowned_column_preserves_incoming_workspace() -> None:
    value, owner, column = source_leveltemp_destination_energy(
        ion_stage=5,
        active_min_stage=5,
        active_max_stage=6,
        destination_column=50,
        candidate_mask=0,
        candidate_energy_ev=(0.0,) * 12,
        incoming_energy_ev=77.25,
    )
    assert column == 50
    assert owner == 0
    assert value == 77.25


def test_native_correction_uses_literal_candidate_payload_after_active_selection() -> None:
    text = (ROOT / "src/xstar_tools/xstar/cpp/fixed_state_engine.cpp").read_text()
    active = text.index("const ActiveElementView active =")
    correction = text.index("apply_magnesium_type53_persistent_leveltemp_v048746221(", active)
    contributions = text.index("std::vector<xstar_element_contribution_v1> contributions", active)
    assert active < correction < contributions
    assert "persistent_leveltemp_candidates_valid" in text
    assert "leveltemp_candidate_mask" in text
    assert "leveltemp_candidate_energy_ev" in text
    assert "level_count_for_stage" not in text
    assert "shadow.sumh2" in text
    assert "shadow.sumc2" in text


def test_lowerer_serializes_literal_type13_candidates() -> None:
    text = (ROOT / "src/xstar_tools/xstar/native_fixed_program.py").read_text()
    assert "TYPE53_LEVELTEMP_LAYOUT_MAGIC_V048746221 = 221" in text
    assert "source_type13_tables.get" in text
    assert "candidate_energies" in text
    assert "candidate_mask" in text
    assert "range(1, 13)" in text


def test_type57_analyzer_does_not_read_missing_source_ans1_ans2() -> None:
    text = (ROOT / "src/xstar_tools/xstar/magnesium_type57_thermal_closure_v048746220.py").read_text()
    rate_block = text.split('for field in ("ans1", "ans2"):', 1)[1].split(
        'for field in ("ans5", "ans6"):', 1
    )[0]
    assert "source[field]" not in rate_block
    assert "MAGNESIUM_TYPE57_ANS1_ANS2_NATIVE_FINITE" in text


def test_v231_readiness_accepts(tmp_path: Path) -> None:
    output = tmp_path / "readiness.json"
    completed = subprocess.run(
        [
            "python",
            str(ROOT / "check_v048746221_magnesium_type53_leveltemp_closure_readiness.py"),
            "--package-dir",
            str(ROOT),
            "--output-json",
            str(output),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    report = json.loads(output.read_text())
    assert report["result"] == "ACCEPT"
    assert report["abi"] == 60487


def test_type53_case_contract_accepts_v3_and_rejects_stale(tmp_path: Path) -> None:
    import csv
    from xstar_tools.xstar.type53_leveltemp_case_contract_v048746221 import audit_case

    case = tmp_path / "case"
    case.mkdir()
    (case / "elements.csv").write_text(
        "element_index,element_z,normalization_row\n0,12,577\n"
    )
    record_fields = [
        "source_position", "record", "next_index", "element_index", "opcode",
        "data_type", "rate_type", "ion_index", "ion_stage", "lower_row",
        "upper_row", "real_offset", "real_count", "int_offset", "int_count",
        "density_scale", "line_energy_ev", "atomic_mass_amu", "matrix_enabled",
    ]
    reals: list[float] = []
    ints: list[int] = []
    with (case / "records.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=record_fields)
        writer.writeheader()
        for index in range(876):
            real_offset = len(reals)
            int_offset = len(ints)
            # Two energy/sigma pairs plus the 22-real v3 context.  Stage 11
            # owns the requested mutable leveltemp column.
            context = [
                10.0, 10.0, 1.0, 20.0, 2.0, 1.0, 1.0, 104.0, 0.0, 1.0,
                *([0.0] * 10), 1695.53125, 0.0,
            ]
            reals.extend([1.0, 2.0, 3.0, 4.0, *context])
            ints.extend([1, 35, 1 << 10, 221])
            writer.writerow({
                "source_position": index + 1, "record": index + 1,
                "next_index": index + 1, "element_index": 0, "opcode": 53,
                "data_type": 53, "rate_type": 7, "ion_index": 11,
                "ion_stage": 11, "lower_row": 1, "upper_row": 35,
                "real_offset": real_offset, "real_count": 26,
                "int_offset": int_offset, "int_count": 4,
                "density_scale": 1.0, "line_energy_ev": 10.0,
                "atomic_mass_amu": 24.0, "matrix_enabled": 1,
            })
    (case / "reals.txt").write_text("".join(f"{value:.17g}\n" for value in reals))
    (case / "ints.txt").write_text("".join(f"{value}\n" for value in ints))
    assert audit_case(case)["result"] == "ACCEPT"

    stale = tmp_path / "stale"
    stale.mkdir()
    for name in ("elements.csv", "records.csv", "reals.txt", "ints.txt"):
        (stale / name).write_bytes((case / name).read_bytes())
    stale_ints = (stale / "ints.txt").read_text().splitlines()
    stale_ints[3] = "0"
    (stale / "ints.txt").write_text("\n".join(stale_ints) + "\n")
    report = audit_case(stale)
    assert report["result"] == "REJECT"
    assert any("layout magic" in error for error in report["errors"])
