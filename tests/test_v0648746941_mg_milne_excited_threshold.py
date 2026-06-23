from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np

import xstar_tools
from xstar_tools.xstar import mg_milne_excited_threshold_attribution as audit
from xstar_tools.xstar import native_fixed_program as lowerer


def root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_release_and_api_version() -> None:
    assert xstar_tools.__version__ == "0.6.48.7.46.21.5"
    api = (root() / "src/xstar_tools/xstar/cpp/xstar_api.h").read_text()
    assert 'XSTAR_API_VERSION_STRING "0.6.48.7.46.21.5"' in api
    assert "XSTAR_API_ABI_VERSION 60487u" in api


def test_literal_type13_linked_list_overrides_alias_record() -> None:
    npfi = np.zeros((100, 4), dtype=np.int64)
    npfi[13, 1] = 1
    derived = SimpleNamespace(
        npfi=npfi,
        npnxt=np.asarray([0, 2, 0], dtype=np.int64),
        npar=np.asarray([0, 91, 91], dtype=np.int64),
    )

    class Master:
        def record_reals(self, record):
            return {1: [10.0, 2.0, 0.0, 20.0], 2: [11.0, 3.0, 0.0, 22.0]}[record]

        def record_integers(self, record):
            return {1: [0, 1, 0], 2: [0, 1, 0]}[record]

    table = lowerer._source_type13_table(Master(), derived, 1)
    assert table[1]["record"] == 2
    assert table[1]["energy_ev"] == 11.0
    assert table[1]["statistical_weight"] == 3.0
    assert table[1]["ionization_potential_ev"] == 22.0


def _synthetic_lowering(data_type: int) -> dict:
    rows = [
        {"energy_ev": 5.0, "statistical_weight": 2.0, "principal_n": 1, "orbital_l": 0},
        {"energy_ev": 20.0, "statistical_weight": 5.0, "principal_n": 0, "orbital_l": 0},
        {"energy_ev": 13.5, "statistical_weight": 4.0, "principal_n": 2, "orbital_l": 1},
    ]
    current = SimpleNamespace(ion_index=1, ion_stage=1, ion_counter=1, nlev=2, compact_start=1)
    parent = SimpleNamespace(ion_index=2, ion_stage=2, ion_counter=2, nlev=2, compact_start=2)
    basis = SimpleNamespace(n_rows=3, blocks=[current, parent], role_to_row={(1, 1): 1, (1, 2): 2})
    derived = SimpleNamespace(
        npar=np.asarray([0, 100], dtype=np.int64),
        ion_stage=np.asarray([0, 1, 2], dtype=np.int64),
        ion_element_z=np.asarray([0, 12, 12], dtype=np.int64),
        npconi2=np.asarray([0, 77], dtype=np.int64),
    )
    subset = SimpleNamespace(ion_record_to_index={100: 1})

    class Master:
        def header(self, _rec):
            return SimpleNamespace(data_type=data_type, rate_type=7, raw_pointer=1)

        def record_reals(self, _rec):
            return [0.1, 1.0, 0.2, 0.5]

        def record_integers(self, _rec):
            return [2, 0, 1, 0]

    tables = {
        1: {
            1: {"record": 11, "energy_ev": 5.0, "statistical_weight": 2.0, "ionization_potential_ev": 20.0},
            2: {"record": 12, "energy_ev": 20.0, "statistical_weight": 5.0, "ionization_potential_ev": 20.0},
        },
        2: {
            2: {"record": 22, "energy_ev": 3.0, "statistical_weight": 4.0, "ionization_potential_ev": 0.0},
        },
    }
    snapshots = {
        1: {
            1: tables[1][1],
            2: tables[1][2],
            3: {"record": 99, "energy_ev": 13.5, "statistical_weight": 7.0, "ionization_potential_ev": 0.0},
        }
    }
    return lowerer._lower_record(
        Master(), derived, 1, 2, rows, basis, {1: current, 2: parent}, subset,
        {1: {1: 5.0, 2: 20.0, 3: 13.5}},
        {1: {3: {"ion_index": 99}}},
        snapshots, tables,
    )


def test_type49_context_v2_uses_milne_partition_and_signed_threshold() -> None:
    result = _synthetic_lowering(49)
    context = result["reals"][-10:]
    assert context == [15.0, 15.0, 5.0, 20.0, 2.0, 5.0, 4.0, 13.5, 3.0, 4.0]
    assert result["ints"] == [77, 999]


def test_type53_context_v2_corrects_threshold_before_runtime() -> None:
    result = _synthetic_lowering(53)
    context = result["reals"][-10:]
    assert context[0] == 15.0
    assert context[1] == 18.0
    assert context[3] == 20.0
    assert context[5] == 5.0
    assert context[8] == 3.0
    assert context[9] == 4.0
    assert result["line_energy_ev"] == 18.0


def test_native_parses_v2_and_uses_partition_before_integration() -> None:
    cpp = (root() / "src/xstar_tools/xstar/cpp/fixed_state_engine.cpp").read_text()
    assert "kType53ContextRealsV2 = 10" in cpp
    assert "kBoundFreeContextRealsV2 = 10" in cpp
    assert "record_context.continuum_statistical_weight = r[base + 5]" in cpp
    assert "record_context.threshold_ev = r[base + 1]" in cpp
    assert "corrected_threshold_before_mapping" in cpp
    assert "XSTAR_QUALIFICATION_MG_MILNE_EXCITED_THRESHOLD" in cpp


def test_forward_reverse_and_context_gates_are_fail_closed() -> None:
    assert audit.EXPECTED == {49: 49_349, 53: 53_436}
    text = (root() / "src/xstar_tools/xstar/mg_milne_excited_threshold_attribution.py").read_text()
    for marker in (
        "MG_TYPE49_FORWARD_UNEXPLAINED_ROWS_ZERO",
        "MG_TYPE49_REVERSE_UNEXPLAINED_ROWS_ZERO",
        "MG_TYPE53_FORWARD_UNEXPLAINED_ROWS_ZERO",
        "MG_TYPE53_REVERSE_UNEXPLAINED_ROWS_ZERO",
        "MG_MILNE_PARTITION_WEIGHT_CONTEXT_EXACT",
        "MG_TYPE53_EXCITED_THRESHOLD_CONTEXT_EXACT",
        "MG_TYPE53_CORRECTED_THRESHOLD_USED_BEFORE_NBINC",
    ):
        assert marker in text


def test_type50_block_does_not_use_new_qualification_path() -> None:
    cpp = (root() / "src/xstar_tools/xstar/cpp/fixed_state_engine.cpp").read_text()
    block = cpp.split("case XSTAR_FIXED_OPCODE_TYPE50_RADIATIVE_LINE", 1)[1].split(
        "case XSTAR_FIXED_OPCODE_TYPE51_BT_COLLISION", 1
    )[0]
    assert "MG_MILNE_EXCITED_THRESHOLD" not in block
    assert "milne_partition_context_used" not in block
