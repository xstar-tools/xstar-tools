from __future__ import annotations

from pathlib import Path
import unittest

import numpy as np

from xstar_tools.xstar.cpp_backend_rates import apply_linopac_profile_cpp, rates_backend_status
from xstar_tools.xstar.emergent_emissivity import (
    _source_linopac_center_profile,
    _source_linopac_seed_profiles,
    _source_linopac_into_opakc,
)
from xstar_tools.xstar.performance import summarize_rate_payload_four_family_product


def test_voigt_far_wing_cpp_profile_is_binary64_exact() -> None:
    status = rates_backend_status()
    if not status.cpp_available:
        raise unittest.SkipTest(f"optional C++ rates backend is not built: {status.cpp_import_error}")
    assert "source_real_v3" in str(status.cpp_backend_name)
    epi = np.geomspace(0.1, 1.0e5, 9999).astype(np.float64)
    cases = (
        (1.0e-8, 1000.0, 35.0, 180.0, 24.305, 1.0e-2),
        (1.0e-5, 1352.0, 0.0, 6.5, 24.305, 1.0e-3),
        (1.0e-8, 1000.0, 35.0, 180.0, 24.305, 0.0),
    )
    for optpp, energy, vturb, temperature, mass, natural_width in cases:
        python_opacity = np.zeros_like(epi)
        cpp_opacity = np.zeros_like(epi)
        python_emissivity = np.zeros((2, epi.size), dtype=np.float64)
        cpp_emissivity = np.zeros_like(python_emissivity)
        python_diag = _source_linopac_into_opakc(
            optpp=optpp, rcem1=0.0, rcem2=0.0, line_energy_eV=energy,
            vturb_km_s=vturb, temperature_1e4K=temperature,
            atomic_mass_amu=mass, natural_width_eV=natural_width,
            epi=epi, opakc=python_opacity, rccemis=python_emissivity,
            ncn2=epi.size,
        )
        cpp_diag, _, _ = apply_linopac_profile_cpp(
            optpp=optpp, rcem1=0.0, rcem2=0.0, line_energy_eV=energy,
            vturb_km_s=vturb, temperature_1e4K=temperature,
            atomic_mass_amu=mass, natural_width_eV=natural_width,
            seed_profiles=_source_linopac_seed_profiles(
                line_energy_eV=energy, vturb_km_s=vturb,
                temperature_1e4K=temperature, atomic_mass_amu=mass,
                natural_width_eV=natural_width, epi=epi, ncn2=epi.size,
            ),
            epi=epi, opakc=cpp_opacity, rccemis=cpp_emissivity,
            ncn2=epi.size,
        )
        assert python_diag["updated_bins"] == cpp_diag["updated_bins"]
        assert np.array_equal(python_opacity, cpp_opacity)
        assert np.array_equal(python_emissivity, cpp_emissivity)


def test_v0641_summary_reports_qualified_promotion() -> None:
    evaluation = {
        "schema_version": "0.6.41", "accepted_gate": True,
        "product_candidate": False, "product_promoted": True,
        "seed_elision_differential": False, "active": True,
        "live_matrix_commit": True, "whole_evaluation_fallback": True,
        "python_seed_path_retained": False, "verification_enabled": False,
        "full_reverse_verification": False, "order_preserving_commit": True,
        "order_preserving_commit_verified": True,
        "status": "FOUR_FAMILY_PRODUCT_PROMOTED_EXACT",
        "qualification_candidate_version": "0.6.40.3",
        "qualification_evaluations": 61,
        "qualification_type50_opakab_records": 146286,
        "qualification_science_products_exact": True,
    }
    summary = summarize_rate_payload_four_family_product(
        {"mg_rate_payload_four_family_product_evaluations": [evaluation]}
    )
    assert summary["status"] == "FOUR_FAMILY_PRODUCT_PROMOTED_EXACT"
    assert summary["product_activations"] == 1
    assert summary["qualification_candidate_version"] == "0.6.40.3"
    assert summary["qualification_science_products_exact"] is True


def test_v0641_runner_enables_exact_products_without_oracle() -> None:
    root = Path(__file__).parents[1]
    runner = (root / "run_v041_xstar_tools_four_family_product_promoted.sh").read_text()
    assert "XSTAR_ATOMIC_RATE_PAYLOAD_FOUR_FAMILY_PRODUCT_PROMOTED=1" in runner
    assert "XSTAR_ATOMIC_RATE_PAYLOAD_FOUR_FAMILY_VERIFY_OLD=0" in runner
    assert "XSTAR_ATOMIC_EMISSIVITY_UPSTREAM_TYPE4_PRODUCT_CPP=1" in runner
    source = (root / "src/xstar_tools/xstar/cpp/rate_kernels.cpp").read_text()
    assert "v2*v2*v2" in source
