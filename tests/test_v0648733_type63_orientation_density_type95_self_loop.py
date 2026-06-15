from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np

from xstar_tools.xstar.call2_helium_type63_type95_stream_completion import RELEASE
from xstar_tools.xstar.native_fixed_program import _lower_record


def _lower_type63(initial: int, final: int, energies: tuple[float, float]):
    rows = [
        {"energy_ev": energies[0], "statistical_weight": 2.0, "principal_n": 3, "orbital_l": 1},
        {"energy_ev": energies[1], "statistical_weight": 4.0, "principal_n": 3, "orbital_l": 2},
    ]
    basis = SimpleNamespace(n_rows=2, role_to_row={(1, 1): 1, (1, 2): 2})
    block = SimpleNamespace(nlev=2, compact_start=1, ion_counter=1)
    derived = SimpleNamespace(
        npar=np.asarray([0, 100], dtype=np.int64),
        ion_stage=np.asarray([0, 1], dtype=np.int64),
        ion_element_z=np.asarray([0, 2], dtype=np.int64),
    )
    subset = SimpleNamespace(ion_record_to_index={100: 1})

    class Master:
        def header(self, rec: int):
            return SimpleNamespace(data_type=63, rate_type=3, raw_pointer=rec)

        def record_reals(self, rec: int):
            return []

        def record_integers(self, rec: int):
            return [initial, final, 2, 0]

    return _lower_record(Master(), derived, 1, 0, rows, basis, {1: block}, subset)


def test_release_version() -> None:
    assert RELEASE == "0.6.48.7.33"


def test_type63_lowerer_uses_source_energy_orientation_and_literal_payload() -> None:
    ascending = _lower_type63(1, 2, (10.0, 20.0))
    assert ascending["lower_row"] == 1
    assert ascending["upper_row"] == 2
    assert ascending["ints"] == [3, 1, 3, 2, 2, 1, 2]

    descending = _lower_type63(1, 2, (20.0, 10.0))
    assert descending["lower_row"] == 2
    assert descending["upper_row"] == 1
    assert descending["ints"] == [3, 1, 3, 2, 2, 1, 2]


def test_cpp_type63_density_and_type95_suppression_contract() -> None:
    text = Path("src/xstar_tools/xstar/cpp/fixed_state_engine.cpp").read_text()
    assert "record.int_count >= 7" in text
    assert "initial = &row_at(element, static_cast<int>(ints[5]))" in text
    assert "final = &row_at(element, static_cast<int>(ints[6]))" in text
    assert "c.density_scale=input.hydrogen_density_cm3" in text
    assert "source_absent_type95_self_loop" in text
    assert "original.data_type == 95" in text
    assert "original.lower_row == original.upper_row" in text
    assert "!source_absent_type95_self_loop" in text


def test_audit_and_runner_expose_completion_gates() -> None:
    audit = Path(
        "src/xstar_tools/xstar/call2_helium_type63_type95_stream_completion.py"
    ).read_text()
    runner = Path("run_v048733_type63_orientation_density_type95_self_loop.sh").read_text()
    for token in (
        "CALL2_HE_TYPE63_ENDPOINT_ORIENTATION",
        "CALL2_HE_TYPE63_CJ2_DENSITY_SCALING",
        "CALL2_HE_TYPE95_SELF_LOOP_1629_ABSENT",
        "CALL2_HE_TYPE95_SELF_LOOP_1980_ABSENT",
        "CALL2_HE_TERM_STREAM_COMPLETE",
        "CALL2_HE_RATE_FAMILY_ATTRIBUTION",
    ):
        assert token in audit
    assert "call2_helium_type63_type95_stream_completion" in runner
    assert "XSTAR_QUALIFICATION_SOLVE_RESPONSE=1" in runner
