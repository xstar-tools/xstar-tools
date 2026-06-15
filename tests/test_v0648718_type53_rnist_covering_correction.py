from pathlib import Path


def test_type53_uses_destination_continuum_energy() -> None:
    root = Path(__file__).resolve().parents[1]
    text = (root / "src/xstar_tools/xstar/cpp/fixed_state_engine.cpp").read_text()
    assert "record_context->continuum_energy_ev" in text
    assert "record_context->leveltemp_destination_energy_ev" in text
    assert "row46_contract ? 0.0 : upper.energy_ev" not in text


def test_dsec_covering_fraction_is_first_class_abi_state() -> None:
    root = Path(__file__).resolve().parents[1]
    header = (root / "src/xstar_tools/xstar/cpp/xstar_fixed_state_engine.h").read_text()
    standalone = (root / "src/xstar_tools/xstar/cpp/xstar_standalone.cpp").read_text()
    assert "XSTAR_FIXED_STATE_ENGINE_ABI_VERSION 60487u" in header
    assert "dsec_covering_fraction" in header
    assert "XSTAR_FIXED_RUNTIME_STATE_DSEC_COVERING_FRACTION" in header
    assert "--dsec-covering-fraction" in standalone
    assert "--temperature-k" in standalone
