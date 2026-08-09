from pathlib import Path
import math

ROOT = Path(__file__).resolve().parents[1]


def test_release_version():
    assert 'version = "0.6.48.7.46.23"' in (ROOT / "pyproject.toml").read_text()
    assert '__version__ = "0.6.48.7.46.23"' in (ROOT / "src/xstar_tools/__init__.py").read_text()


def test_canonical_e7_and_zero_floor_retained():
    text = (ROOT / "src/xstar_tools/xstar/canonical_thermal_controller_parity_v048746217.py").read_text()
    assert 'format(numeric, ".7e")' in text
    assert 'abs(numeric) < 1.0e-30' in text
    assert 'format(numeric, ".10e")' in text  # diagnostic only
    assert '10 digits after decimal (.10e)' not in text


def test_controller_uses_same_e7_policy():
    text = (ROOT / "src/xstar_tools/xstar/cpp/xstar_standalone.cpp").read_text()
    assert "canonical_e7_equal" in text
    assert "kCanonicalComparisonZeroFloorV048746226" in text
    assert "canonical_e10_equal" not in text


def test_helium_type53_live_escape_binding_present():
    text = (ROOT / "src/xstar_tools/xstar/cpp/local_zone_engine.cpp").read_text()
    assert "XSTAR_QUALIFICATION_HELIUM_TYPE53_INTERVAL_SOURCE_ORDER" in text
    assert "contract_tau_in = input.continuum_tau_in[continuum_index - 1]" in text
    assert "type53_helium_live_escape_state_applied" in text
    assert "type53_integration_intervals" in text


def test_call1_residual_is_directly_bound():
    text = (ROOT / "src/xstar_tools/xstar/cpp/local_zone_engine.cpp").read_text()
    assert "output.elcter = input.charge_residual_override" in text


def test_expected_escape_ratios_are_not_roundoff_policy():
    # Representative call-3/call-4 factors from the v21.15 six-record family.
    for tau_sum, observed in [
        (7.4117e-9, math.exp(-7.4117e-9)),
        (1.50197e-8, math.exp(-1.50197e-8)),
    ]:
        assert abs(observed - (1.0 - tau_sum)) < 2e-16
        assert observed != 1.0


def test_runners_enable_correction():
    assert "XSTAR_QUALIFICATION_HELIUM_TYPE53_INTERVAL_SOURCE_ORDER=1" in (ROOT / "run_v048746226_native_fixed_replay.sh").read_text()
    assert "XSTAR_QUALIFICATION_HELIUM_TYPE53_INTERVAL_SOURCE_ORDER=1" in (ROOT / "run_v048746217_canonical_thermal_controller_parity.sh").read_text()
