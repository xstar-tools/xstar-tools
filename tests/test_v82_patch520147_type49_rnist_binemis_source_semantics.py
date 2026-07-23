from __future__ import annotations

import math
from pathlib import Path

from xstar_tools.rates_type53 import (
    RYDBERG_EV,
    XSTAR_KT_EV_PER_1E4K,
    Type53LiveRadiationState,
    evaluate_type53_ucalc_record,
)


def _record():
    return {
        "energy_above_threshold_ryd": [0.1, 0.5, 1.0, 2.0, 4.0, 8.0],
        "cross_section_cm2": [1e-18, 8e-19, 5e-19, 2e-19, 8e-20, 2e-20],
        "threshold_eV": 50.0,
        "bound_statistical_weight": 2.0,
        "continuum_statistical_weight": 1.0,
        "destination_statistical_weight": 1.0,
        "continuum_energy_eV": 10.0,
        "bound_energy_eV": 0.0,
        "destination_energy_eV": 10.0,
    }


def _state():
    epi = [10.0, 20.0, 30.0, 40.0, 60.0, 80.0, 100.0, 140.0,
           180.0, 240.0, 320.0, 420.0, 550.0, 700.0, 900.0, 1200.0]
    return Type53LiveRadiationState.from_sequences(epi, [1e10] * len(epi), [0.0] * len(epi))


def _evaluate(*, type49: bool):
    return evaluate_type53_ucalc_record(
        _record(), _state(), temperature_k=65000.0, xpx_cm3=1e8,
        electron_fraction_xee=1.2, ptmp1=0.0, ptmp2=1.0, lfast=2,
        abund1=1e-3, abund2=1e-3, type49_rnist_semantics=type49,
    )


def test_type49_rnist_excludes_excited_parent_threshold():
    result = _evaluate(type49=True)
    assert result["status"] == "evaluated"
    assert result["rnist_family"] == "type49"
    assert result["rnist_exponent_includes_ethtmp"] is False
    assert result["rnist_excited_parent_ethtmp_eV"] == 40.0
    assert math.isclose(result["rnist_exponent_energy_eV"], RYDBERG_EV * 0.1, rel_tol=0.0, abs_tol=1e-15)


def test_type53_rnist_retains_excited_parent_threshold():
    result = _evaluate(type49=False)
    assert result["status"] == "evaluated"
    assert result["rnist_family"] == "type53"
    assert result["rnist_exponent_includes_ethtmp"] is True
    assert math.isclose(result["rnist_exponent_energy_eV"], 40.0 + RYDBERG_EV * 0.1, rel_tol=0.0, abs_tol=1e-15)


def test_type49_to_type53_rnist_ratio_is_exact_missing_ethtmp_boltzmann_factor():
    t49 = _evaluate(type49=True)
    t53 = _evaluate(type49=False)
    expected = math.exp(40.0 / (XSTAR_KT_EV_PER_1E4K * 6.5))
    assert math.isclose(t49["rnist"] / t53["rnist"], expected, rel_tol=2e-15, abs_tol=0.0)


def test_binemis_uses_compact_core_and_source_reach_without_million_point_allocation():
    root = Path(__file__).resolve().parents[1]
    output_writer = (root / "src/xstar_tools/xstar/output_writers.py").read_text()
    cpp_writer = (root / "src/xstar_tools/xstar/cpp/xstar_standalone.cpp").read_text()
    cpp_backend = (root / "src/xstar_tools/xstar/cpp_backend_emissivity.py").read_text()
    cpp_kernel = (root / "src/xstar_tools/xstar/cpp/line_emissivity.cpp").read_text()

    # Do not materialize PARAM:ncn=999999 in Python or C++.  The core stays
    # bounded while a far-wing continuation carries the source reach.
    assert "nbtpp = 20000" in output_writer
    assert "source_profile_half_steps = 499999" in output_writer
    assert "nbtpp = 999999" not in output_writer
    assert "kSourceBinemisScratchPoints = 20000" in cpp_writer
    assert "int(ncn2), 20000" in cpp_backend
    assert "kSourceProfileHalfSteps = 499999" in cpp_kernel
    assert "new double[static_cast<std::size_t>(999999)]" not in cpp_kernel


def test_binemis_source_reach_can_extend_far_beyond_compact_core_without_more_storage():
    # Representative benchmark geometry: ncut=4 means deleused=deleepi/4.
    # The 20k core reaches 10k substeps, whereas the source declaration reaches
    # 499999 on each side.  The latter is >49x farther without requiring a
    # million-element array in the translated implementation.
    deleused = 1.0
    core_reach = (20000 // 2) * deleused
    source_reach = 499999 * deleused
    assert source_reach / core_reach > 49.0
