from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load_parameter_contract():
    path = ROOT / "src/xstar_tools/xstar/parameter_contract.py"
    spec = importlib.util.spec_from_file_location("parameter_contract_068229", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod

PC = _load_parameter_contract()


def _required_products(lwrite: int, lprint: int, npass: int):
    all_names = (
        "xo01_detail.fits", "xo01_detal2.fits", "xo01_detal3.fits", "xo01_detal4.fits",
        "xout_abund1.fits", "xout_spect1.fits", "xout_lines1.fits", "xout_cont1.fits",
        "xout_rrc1.fits", "xout_step.log",
    )
    required=["xout_step.log"]
    if lwrite >= -1: required.append("xout_spect1.fits")
    if lwrite >= 0: required.extend(("xout_lines1.fits","xout_cont1.fits","xout_rrc1.fits"))
    if lprint >= 0: required.append("xout_abund1.fits")
    if lwrite > 0 or npass > 1: required.extend(all_names[:4])
    return tuple(n for n in all_names if n in required)


def _sequence(lprint: int):
    nl=(22,11,1,23,24,16,27,15,19,5,14,21,7,10,26,0,4,6,18,29,30,28)
    if lprint < 0: return (22,)
    n={0:2,1:10,2:15,3:18}.get(lprint,21)
    return nl[:n]


def test_lwrite_source_supported_envelope():
    assert [PC.coerce_and_validate_parameter("lwrite", v) for v in (-1,0,1)] == [-1,0,1]
    with pytest.raises(ValueError): PC.coerce_and_validate_parameter("lwrite", -2)
    with pytest.raises(ValueError): PC.coerce_and_validate_parameter("lwrite", 2)


def test_lprint_stock_xpi_envelope():
    assert [PC.coerce_and_validate_parameter("lprint", v) for v in range(-1,7)] == list(range(-1,7))
    with pytest.raises(ValueError): PC.coerce_and_validate_parameter("lprint", -2)
    with pytest.raises(ValueError): PC.coerce_and_validate_parameter("lprint", 7)


def test_lstep_and_metadata_roles():
    assert PC.coerce_and_validate_parameter("lstep", -123) == -123
    assert PC.coerce_and_validate_parameter("lstep", 12345) == 12345
    with pytest.raises(ValueError): PC.coerce_and_validate_parameter("lstep", 1.5)
    assert PC.PARAMETER_RULES["lstep"].classification == "output-control"
    for name in ("modelname","mode","loopcontrol"):
        assert PC.PARAMETER_RULES[name].classification == "metadata/interface"


def test_source_required_product_inventory():
    assert _required_products(-1,-1,1) == ("xout_spect1.fits","xout_step.log")
    assert _required_products(-1,0,1) == ("xout_abund1.fits","xout_spect1.fits","xout_step.log")
    assert _required_products(0,0,1) == ("xout_abund1.fits","xout_spect1.fits","xout_lines1.fits","xout_cont1.fits","xout_rrc1.fits","xout_step.log")
    assert _required_products(1,0,1) == ("xo01_detail.fits","xo01_detal2.fits","xo01_detal3.fits","xo01_detal4.fits","xout_abund1.fits","xout_spect1.fits","xout_lines1.fits","xout_cont1.fits","xout_rrc1.fits","xout_step.log")
    names=_required_products(-1,-1,3)
    assert "xout_lines1.fits" not in names and "xout_abund1.fits" not in names
    assert all(n in names for n in ("xo01_detail.fits","xo01_detal2.fits","xo01_detal3.fits","xo01_detal4.fits"))


@pytest.mark.parametrize("lprint, expected", [
    (-1,(22,)), (0,(22,11)),
    (1,(22,11,1,23,24,16,27,15,19,5)),
    (2,(22,11,1,23,24,16,27,15,19,5,14,21,7,10,26)),
    (3,(22,11,1,23,24,16,27,15,19,5,14,21,7,10,26,0,4,6)),
    (4,(22,11,1,23,24,16,27,15,19,5,14,21,7,10,26,0,4,6,18,29,30)),
    (5,(22,11,1,23,24,16,27,15,19,5,14,21,7,10,26,0,4,6,18,29,30)),
    (6,(22,11,1,23,24,16,27,15,19,5,14,21,7,10,26,0,4,6,18,29,30)),
])
def test_lprint_source_dispatch(lprint, expected):
    assert _sequence(lprint) == expected
    src=(ROOT/"src/xstar_tools/xstar/pprint_legacy.py").read_text()
    # Production helper contains the same nlnprnt thresholds and literal NLPRNT tuple.
    assert "def _final_pprint_option_sequence" in src
    assert "n = 21" in src
    assert "22, 11, 1, 23, 24, 16, 27, 15, 19, 5, 14, 21, 7, 10, 26, 0, 4, 6, 18, 29, 30, 28" in src


def test_python_and_cpp_publication_contract_present():
    runner=(ROOT/"src/xstar_tools/xstar/physical_runner.py").read_text()
    pprint=(ROOT/"src/xstar_tools/xstar/pprint_legacy.py").read_text()
    header=(ROOT/"src/xstar_tools/xstar/cpp/xstar_parameter_contract.hpp").read_text()
    standalone=(ROOT/"src/xstar_tools/xstar/cpp/xstar_standalone.cpp").read_text()
    fits=(ROOT/"src/xstar_tools/xstar/cpp/xstar_science_fits.cpp").read_text()
    step=(ROOT/"src/xstar_tools/xstar/cpp/xstar_step_log.cpp").read_text()
    assert 'def _required_products_for_controls(*, lwrite: int, lprint: int, npass: int)' in runner
    assert 'if requested_lpri >= 0:' in pprint
    assert '{"lwrite", ParameterKind::Integer, "0", true, -1.0, true, 1.0}' in header
    assert 'spectral_count = lwrite >= 0 ? 4u : (lwrite >= -1 ? 1u : 0u)' in standalone
    assert 'lprint >= 0 && xstar_science_fits::abundance_product_enabled()' in standalone
    assert 'if (lwrite >= 0)' in fits and 'if (lwrite >= -1)' in fits
    assert 'if (lprint >= 0) out << "\\n print option:11\\n";' in step
    assert all(x in step for x in ('if (lprint >= 2)','if (lprint >= 3)','if (lprint >= 4)'))


def test_no_output_controls_in_core_rate_solver_science():
    needles=("lwrite","lprint","lstep","loopcontrol","modelname")
    files=("ucalc.py","element_equilibrium.py","local_zone.py","thermal_balance.py")
    for name in files:
        text=(ROOT/"src/xstar_tools/xstar"/name).read_text().lower()
        # Ignore documentation/comments only by demanding no executable access pattern.
        for needle in needles:
            assert f'get("{needle}")' not in text
            assert f"['{needle}']" not in text
            assert f'["{needle}"]' not in text


def test_contract_documented():
    text=(ROOT/"output_control_0_6_82_29.md").read_text()
    for phrase in ("lwrite=-1","lprint=-1..6","lstep","modelname","loopcontrol","mode"):
        assert phrase in text
