from __future__ import annotations

from pathlib import Path

from xstar_tools.xstar import all61_post_seed_system_decomposition as decomposition


def _rows() -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    source: list[dict[str, str]] = []
    native: list[dict[str, str]] = []
    for row, (ion, charge, superlevel, seed) in enumerate(
        ((5, 4, 101, 0.2), (5, 4, 101, 0.3), (6, 5, 205, 0.5)), start=1
    ):
        source.append({
            "sequence": "1", "element_z": "12", "compact_row": str(row),
            "active_min_stage": "5", "active_max_stage": "12",
            "ion": str(ion), "ion_charge": str(charge),
            "superlevel": str(superlevel), "is_normalization_row": "0",
            "transformed_initial_population": repr(seed),
        })
        native.append({
            "evaluation_ordinal": "1", "element_z": "12", "compact_row": str(row),
            "active_min_stage": "5", "active_max_stage": "12",
            "ion": str(ion), "ion_charge": str(charge),
            "superlevel": str(1 if row < 3 else 2), "is_normalization_row": "0",
            "initial_population": repr(seed),
        })
    return source, native


def test_source_basis_seed_oracle_is_present() -> None:
    root = Path(__file__).resolve().parents[1]
    cpp = (root / "src/xstar_tools/xstar/cpp/fixed_state_engine.cpp").read_text()
    for marker in (
        "XSTAR_QUALIFICATION_SOURCE_COMPACT_BASIS_SEED",
        "XSTAR_QUALIFICATION_SOURCE_SOLVE_ROWS_CSV",
        "XSTAR_QUALIFICATION_SOURCE_SEQUENCE",
        "load_source_compact_oracle",
        "make_source_compact_element_view",
        "constexpr double critf = 1.0e-7",
        "preserve_initial_seed",
    ):
        assert marker in cpp


def test_basis_comparator_canonicalizes_superlevel_labels() -> None:
    source, native = _rows()
    exact, counts = decomposition._basis_seed_exact(source, native)
    assert exact
    assert counts["basis_exact"] == 3
    assert counts["seed_exact"] == 3


def test_basis_comparator_rejects_charge_and_seed_changes() -> None:
    source, native = _rows()
    native[1]["ion_charge"] = "99"
    assert not decomposition._basis_seed_exact(source, native)[0]
    source, native = _rows()
    native[2]["initial_population"] = "0.5000000000000001"
    assert not decomposition._basis_seed_exact(source, native)[0]


def test_release_runner_is_full_workflow() -> None:
    root = Path(__file__).resolve().parents[1]
    runner = root / "run_v0487468_all61_post_seed_system_decomposition.sh"
    text = runner.read_text()
    assert runner.stat().st_size > 6000
    assert "v0472_all61_post_seed_system_capture capture" in text
    assert "XSTAR_QUALIFICATION_SOURCE_COMPACT_BASIS_SEED=1" in text
    assert "all61_post_seed_system_decomposition" in text
