from __future__ import annotations

import csv
import json
from pathlib import Path
import subprocess

from xstar_tools.xstar.native_fixed_program import (
    PROGRAM_ABI,
    _coverage_from_counts,
    validate_program_directory,
)

ROOT = Path(__file__).resolve().parents[1]
PROGRAM = ROOT / "src/xstar_tools/benchmarks/v06483_active_atdb_lowerer_fixture"
CPP = ROOT / "src/xstar_tools/xstar/cpp"


def test_coverage_separates_metadata_native_and_blockers() -> None:
    result = _coverage_from_counts({(13, 6): 10, (3, 56): 20, (3, 57): 5, (3, 63): 2}, (1, 2, 12))
    assert result["topology_metadata_counts"] == {6: 10}
    assert result["active_lowerer_native_counts"] == {56: 20}
    assert result["unsupported_physics_counts"] == {57: 5}
    assert result["recognized_but_not_active_lowered_counts"] == {63: 2}
    assert result["nominal_record_coverage_percent"] == 100.0 * 30 / 37
    assert result["production_promotion_ready"] is False


def test_fixture_uses_type56_and_current_abi() -> None:
    validation = validate_program_directory(PROGRAM)
    assert PROGRAM_ABI == 60483
    assert validation.program_id == "v06483_active_atdb_lowerer_fixture"
    assert validation.records == 6
    assert 56 in validation.opcodes


def test_native_type56_and_visited_report(tmp_path: Path) -> None:
    exe = CPP / "xstar_cpp"
    completed = subprocess.run(
        [str(exe), "run-fixed-state", "--case-dir", str(PROGRAM), "--output-dir", str(tmp_path)],
        cwd=CPP, text=True, capture_output=True, check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "type56_records_evaluated=1" in completed.stdout
    assert "python_callbacks=0" in completed.stdout
    assert "visited_record_report_generated=true" in completed.stdout
    with (tmp_path / "visited_records.csv").open() as handle:
        visits = {int(row["data_type"]): int(row["visits"]) for row in csv.DictReader(handle)}
    assert visits[56] == 1
    summary = json.loads((tmp_path / "native_fixed_state_summary.json").read_text())
    assert summary["schema_version"] == "0.6.48.3.1"
    assert summary["type56_records_evaluated"] == 1
    assert summary["computed_from_raw_coefficients"] is True


def test_unknown_opcode_fails_closed(tmp_path: Path) -> None:
    import shutil
    bad = tmp_path / "bad"
    shutil.copytree(PROGRAM, bad)
    rows = list(csv.DictReader((bad / "records.csv").open()))
    rows[0]["opcode"] = "777"
    with (bad / "records.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    exe = CPP / "xstar_cpp"
    completed = subprocess.run(
        [str(exe), "fixed-state-self-test", "--case-dir", str(bad)],
        cwd=CPP, text=True, capture_output=True, check=False,
    )
    assert completed.returncode != 0
    assert "unsupported fixed-state opcode 777" in (completed.stdout + completed.stderr)


def test_build_element_layout_uses_compact_index(monkeypatch) -> None:
    from xstar_tools.xstar import element_equilibrium as equilibrium
    from xstar_tools.xstar import native_fixed_program as program

    block = equilibrium.ElementIonBlock(
        ion_index=1, ion_record=10, element_z=1, ion_stage=1, nlev=1,
        compact_start=1, compact_stop=1, first_level_record=20, ion_counter=1,
    )
    basis = equilibrium.ElementCompactBasis(
        element_z=1, min_ion_stage=1, max_ion_stage=1, blocks=[block],
        rows=[equilibrium.ElementBasisRow(
            compact_index=1, superlevel=1, ion_counter=1,
            roles=[{"ion_index": 1, "local_level": 1}],
        )],
        n_rows=1, n_superlevels=1, n_ions=1, normalization_row=1,
        role_to_row={(1, 1): 1}, ion_stage_by_counter={1: 1},
    )

    class Derived:
        n_ions = 1
        ion_element_z = [0, 1]
        ion_stage = [0, 1]

    monkeypatch.setattr(equilibrium, "build_element_compact_basis", lambda *args, **kwargs: basis)
    monkeypatch.setattr(program, "_level_payload", lambda *args, **kwargs: (20, 0.0, 2.0, "H I"))

    element, rows, returned_basis, blocks = program._build_element_layout(object(), Derived(), 1, 1)
    assert element["n_rows"] == 1
    assert rows[0]["row"] == 1
    assert rows[0]["initial_population"] == 1.0
    assert returned_basis is basis
    assert blocks[1] is block
