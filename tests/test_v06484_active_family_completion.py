from __future__ import annotations

import csv
import json
from pathlib import Path
import shutil
import subprocess

from xstar_tools.xstar.native_fixed_program import (
    ACTIVE_LOWERER_DATA_TYPES,
    PROGRAM_ABI,
    _coverage_from_counts,
    _scan_active_records,
    validate_program_directory,
)

ROOT = Path(__file__).resolve().parents[1]
PROGRAM = ROOT / "src/xstar_tools/benchmarks/v06484_active_family_phase1_fixture"
CPP = ROOT / "src/xstar_tools/xstar/cpp"
PHASE1_TYPES = {54, 57, 63, 71, 77, 86, 99}


def test_coverage_promotes_phase1_families() -> None:
    counts = {(13, 6): 10, (3, 56): 20, (3, 57): 5, (3, 63): 2, (4, 71): 3, (3, 77): 4, (1, 86): 6, (1, 99): 1}
    result = _coverage_from_counts(counts, (1, 2, 12))
    assert result["topology_metadata_counts"] == {6: 10}
    assert result["active_lowerer_native_counts"] == {56: 20, 57: 5, 63: 2, 71: 3, 77: 4, 86: 6, 99: 1}
    assert result["recognized_but_not_active_lowered_counts"] == {}
    assert result["unsupported_physics_counts"] == {}
    assert result["production_promotion_ready"] is True
    assert PHASE1_TYPES <= ACTIVE_LOWERER_DATA_TYPES


def test_phase1_fixture_uses_current_abi_and_all_new_opcodes() -> None:
    validation = validate_program_directory(PROGRAM)
    assert PROGRAM_ABI == 60484
    assert validation.program_id == "v06484_active_family_phase1_fixture"
    assert validation.records == 14
    assert PHASE1_TYPES <= set(validation.opcodes)


def test_native_phase1_families_and_visited_report(tmp_path: Path) -> None:
    exe = CPP / "xstar_cpp"
    completed = subprocess.run(
        [str(exe), "run-fixed-state", "--case-dir", str(PROGRAM), "--output-dir", str(tmp_path)],
        cwd=CPP, text=True, capture_output=True, check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "records_evaluated=14" in completed.stdout
    assert "python_callbacks=0" in completed.stdout
    assert "visited_data_types=14" in completed.stdout
    with (tmp_path / "visited_records.csv").open() as handle:
        visits = {int(row["data_type"]): int(row["visits"]) for row in csv.DictReader(handle)}
    for data_type in PHASE1_TYPES:
        assert visits[data_type] == 1
    summary = json.loads((tmp_path / "native_fixed_state_summary.json").read_text())
    assert summary["schema_version"] == "0.6.48.4"
    assert summary["computed_from_raw_coefficients"] is True
    assert summary["python_callbacks"] == 0


def test_unknown_opcode_fails_closed(tmp_path: Path) -> None:
    bad = tmp_path / "bad"
    shutil.copytree(PROGRAM, bad)
    rows = list(csv.DictReader((bad / "records.csv").open()))
    rows[0]["opcode"] = "777"
    with (bad / "records.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    completed = subprocess.run(
        [str(CPP / "xstar_cpp"), "fixed-state-self-test", "--case-dir", str(bad)],
        cwd=CPP, text=True, capture_output=True, check=False,
    )
    assert completed.returncode != 0
    assert "unsupported fixed-state opcode 777" in completed.stdout + completed.stderr


def test_build_element_layout_uses_quantum_metadata(monkeypatch) -> None:
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
    monkeypatch.setattr(program, "_level_payload", lambda *args, **kwargs: (20, 0.0, 2.0, "H I", 1, 0))
    element, rows, returned_basis, blocks = program._build_element_layout(object(), Derived(), 1, 1)
    assert element["n_rows"] == 1
    assert rows[0]["row"] == 1
    assert rows[0]["principal_n"] == 1
    assert rows[0]["orbital_l"] == 0
    assert returned_basis is basis
    assert blocks[1] is block


def test_scan_active_records_stops_at_parent_ion_boundary() -> None:
    from types import SimpleNamespace
    import numpy as np

    class Master:
        @staticmethod
        def header(rec: int):
            return SimpleNamespace(rate_type=3, data_type=63, raw_pointer=rec)

    npfi = np.zeros((4, 4), dtype=np.int64)
    npfi[3, 1], npfi[3, 2], npfi[3, 3] = 10, 20, 30
    npnxt = np.zeros(40, dtype=np.int64)
    npnxt[10], npnxt[11], npnxt[20], npnxt[21], npnxt[30] = 11, 20, 21, 30, 0
    npar = np.zeros(40, dtype=np.int64)
    npar[10:12], npar[20:22], npar[30] = 100, 200, 300
    derived = SimpleNamespace(
        npfi=npfi, npnxt=npnxt, npar=npar,
        ion_records=np.asarray([0, 100, 200, 300], dtype=np.int64),
        ion_element_z=np.asarray([0, 1, 2, 12], dtype=np.int64),
        ion_stage=np.asarray([0, 1, 1, 1], dtype=np.int64),
    )
    subset = SimpleNamespace(active_element_z=(1, 2, 12), ion_indices=np.asarray([1, 2, 3], dtype=np.int64))
    counts, records_by_z, unsupported = _scan_active_records(Master(), derived, subset)
    assert counts == {(3, 63): 5}
    assert records_by_z == {1: [10, 11], 2: [20, 21], 12: [30]}
    assert unsupported == []


def test_phase1_lowerer_serializes_host_payload_shapes() -> None:
    from types import SimpleNamespace
    import numpy as np
    from xstar_tools.xstar.native_fixed_program import _lower_record

    rows = [
        {"energy_ev": 0.0, "statistical_weight": 2.0, "principal_n": 1, "orbital_l": 0},
        {"energy_ev": 10.0, "statistical_weight": 4.0, "principal_n": 2, "orbital_l": 1},
        {"energy_ev": 20.0, "statistical_weight": 6.0, "principal_n": 3, "orbital_l": 2},
        {"energy_ev": 40.0, "statistical_weight": 2.0, "principal_n": 1, "orbital_l": 0},
    ]
    basis = SimpleNamespace(
        n_rows=4,
        role_to_row={(1, 1): 1, (1, 2): 2, (1, 3): 3, (1, 4): 4},
    )
    block = SimpleNamespace(nlev=4, compact_start=1, ion_counter=1)
    derived = SimpleNamespace(
        npar=np.asarray([0, 100], dtype=np.int64),
        ion_stage=np.asarray([0, 1], dtype=np.int64),
        ion_element_z=np.asarray([0, 8], dtype=np.int64),
    )
    subset = SimpleNamespace(ion_record_to_index={100: 1})

    class Master:
        def __init__(self, data_type: int, reals: list[float], ints: list[int]):
            self.data_type = data_type
            self.reals = reals
            self.ints = ints

        def header(self, rec: int):
            return SimpleNamespace(data_type=self.data_type, rate_type=3, raw_pointer=rec)

        def record_reals(self, rec: int):
            return self.reals

        def record_integers(self, rec: int):
            return self.ints

    def lower(data_type: int, reals: list[float], ints: list[int]):
        return _lower_record(Master(data_type, reals, ints), derived, 1, 0, rows, basis, {1: block}, subset)

    type54 = lower(54, [], [1, 2, 1, 0])
    assert type54["lower_row"] == 1 and type54["upper_row"] == 2
    assert type54["ints"] == [2, 1, 1, 0, 1]

    type57 = lower(57, [], [2, 2])
    assert type57["lower_row"] == 2 and type57["upper_row"] == 4
    assert type57["ints"] == [2, 2]

    type63 = lower(63, [], [1, 2, 1, 0])
    assert type63["lower_row"] == 1 and type63["upper_row"] == 2
    assert type63["ints"] == [1, 0, 2, 1, 1]

    raw_grid = [4.0, 10.0, 4.0, 7.0, -7.0, -6.5, -6.0, -5.5, 1000.0]
    type71 = lower(71, raw_grid, [2, 2, 1, 2, 3, 0])
    type77 = lower(77, raw_grid, [2, 2, 1, 2, 3, 0])
    assert type71["lower_row"] == 1 and type71["upper_row"] == 2
    assert type77["lower_row"] == 1 and type77["upper_row"] == 2
    assert type71["reals"] == raw_grid and type77["reals"] == raw_grid

    type86 = lower(86, [0.0, 123.0], [1, 2, 0, 0, 0])
    assert type86["lower_row"] == 2 and type86["upper_row"] == 4
    assert type86["reals"] == [123.0]

    type99 = lower(99, [4.0, 10.0, 4.0, 7.0, 1e-12, 2e-12, 3e-12, 4e-12], [1, 2, 1, 0])
    assert type99["lower_row"] == 1 and type99["upper_row"] == 4
    assert type99["ints"] == [1, 2, 1, 0]
