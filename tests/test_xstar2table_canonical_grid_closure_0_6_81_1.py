from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src/xstar_tools/xstar/cpp/xstar_xspec_table.cpp"
REF = ROOT / "tools/qualification/reference"


def test_canonical_energy_edge_count_is_not_inclusive_high_edge():
    text = CPP.read_text(encoding="utf-8")
    assert "slice->bin_count = high - low;" in text
    assert "slice->bin_count = high - low + 1;" not in text


def test_canonical_additive_normalization_uses_double_literal_then_float_storage():
    text = CPP.read_text(encoding="utf-8")
    assert "constexpr double kLegacyNormalization = 8.356e-7;" in text
    assert "8.356e-7f" not in text
    assert "static_cast<float>(kLegacyNormalization * delta / (luminosity_1e38 * energy))" in text


def test_real_mpi_xstar_fixture_is_pinned():
    fixture = REF / "xstar2table_mpi_grid_0_6_81_1.tar.gz"
    helper = REF / "xstar2table_mpi_grid_compare_0_6_81_1.c"
    assert fixture.is_file() and fixture.stat().st_size > 1_000_000
    assert helper.is_file()
