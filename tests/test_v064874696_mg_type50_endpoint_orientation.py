from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np

import xstar_tools
from xstar_tools.xstar import native_fixed_program as lowerer


def root() -> Path:
    return Path(__file__).resolve().parents[1]


def _lower(snapshot_e1: float, snapshot_e2: float) -> dict:
    rows = [
        {"energy_ev": 10.0, "statistical_weight": 2.0, "principal_n": 1, "orbital_l": 0},
        {"energy_ev": 30.0, "statistical_weight": 4.0, "principal_n": 2, "orbital_l": 1},
    ]
    block = SimpleNamespace(nlev=2, compact_start=1, ion_counter=1)
    basis = SimpleNamespace(n_rows=2, role_to_row={(1, 1): 1, (1, 2): 2})
    derived = SimpleNamespace(
        npar=np.asarray([0, 100], dtype=np.int64),
        ion_stage=np.asarray([0, 3], dtype=np.int64),
        ion_element_z=np.asarray([0, 12], dtype=np.int64),
    )
    subset = SimpleNamespace(ion_record_to_index={100: 1})

    class Master:
        def header(self, _rec):
            return SimpleNamespace(data_type=50, rate_type=4, raw_pointer=1)
        def record_reals(self, _rec):
            return [12.5, 0.0, 3.0e8]
        def record_integers(self, _rec):
            return [1, 2]

    snapshots = {1: {
        1: {"energy_ev": snapshot_e1, "statistical_weight": 7.0},
        2: {"energy_ev": snapshot_e2, "statistical_weight": 9.0},
    }}
    return lowerer._lower_record(
        Master(), derived, 1, 2, rows, basis, {1: block}, subset,
        leveltemp_value_snapshots=snapshots,
    )


def test_release_and_api_version() -> None:
    assert xstar_tools.__version__ == "0.6.48.7.46.21"
    api = (root() / "src/xstar_tools/xstar/cpp/xstar_api.h").read_text()
    assert 'XSTAR_API_VERSION_STRING "0.6.48.7.46.21"' in api
    assert "XSTAR_API_ABI_VERSION 60487u" in api


def test_type50_matrix_orientation_uses_mutable_leveltemp_snapshot() -> None:
    result = _lower(40.0, 5.0)
    assert result["lower_row"] == 2
    assert result["upper_row"] == 1
    assert result["line_energy_ev"] == 20.0


def test_type50_scalar_payload_remains_compact_energy_ordered() -> None:
    result = _lower(40.0, 5.0)
    wavelength = 12.5
    aij = 3.0e8
    expected = 1.0e-16 * aij * 4.0 * wavelength * wavelength / (0.667274 * 2.0)
    assert result["reals"] == [aij, expected, wavelength]


def test_type50_normal_snapshot_keeps_existing_orientation() -> None:
    result = _lower(10.0, 30.0)
    assert result["lower_row"] == 1
    assert result["upper_row"] == 2


def test_type50_lowerer_contract_is_explicit() -> None:
    text = (root() / "src/xstar_tools/xstar/native_fixed_program.py").read_text()
    block = text.split("elif dt == 50:", 1)[1].split("elif dt in {51, 56, 69}:", 1)[0]
    assert "leveltemp_value_snapshots" in block
    assert "source _lower_upper" in block
    assert "scalar_lower_row, scalar_upper_row = local_pair" in block
