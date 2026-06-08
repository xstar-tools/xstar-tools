from __future__ import annotations

import math
import unittest

import numpy as np

from xstar_tools.xstar.cpp_backend_extra import (
    backend_status,
    eval_mg_rate_payload_native_scalar_shadow_cpp,
)
from xstar_tools.xstar.performance import summarize_rate_payload_four_family_product


def test_native_type50_opakab_is_binary64_source_exact() -> None:
    status = backend_status("engine")
    if not status.cpp_available:
        raise unittest.SkipTest(f"optional C++ engine is not built: {status.cpp_import_error}")
    assert status.cpp_abi_version == 9
    assert int(status.cpp_feature_flags or 0) & 512

    row = {
        "record": 1, "rate_type": 4, "data_type": 50,
        "ion_index": 1, "ion_stage": 1, "idest1": 2, "idest2": 1,
        "raw_payload_f64": (), "type50_wavelength_A": 9.16875,
        "type50_aij_s_inv": 1.23e13, "type50_upper_g": 3.0,
        "type50_lower_g": 1.0, "type50_ptmp1": 0.8,
        "type50_ptmp2": 0.1, "type50_cfrac": 1.0,
        "type50_bremsa_nb1": 0.0, "type50_hydrogen_density_cm3": 1.0e8,
        "type50_endpoint_energy_eV": 1352.2, "temperature_k": 1.8e6,
        "turbulent_velocity_km_s": 35.0, "type50_atomic_mass_amu": 24.305,
    }
    results, _, stats = eval_mg_rate_payload_native_scalar_shadow_cpp(
        [row], epi_eV=np.asarray([1.0, 2.0, 3.0]), bremsa=np.zeros(3)
    )
    flin = (
        1.0e-16 * row["type50_aij_s_inv"] * row["type50_upper_g"]
        * row["type50_wavelength_A"] * row["type50_wavelength_A"]
        / (0.667274 * row["type50_lower_g"])
    )
    t_1e4 = row["temperature_k"] / 1.0e4
    vtherm = math.sqrt(
        (row["turbulent_velocity_km_s"] * 1.0e5) ** 2
        + (1.29e6 / math.sqrt(max(row["type50_atomic_mass_amu"] / t_1e4, 1.0e-48))) ** 2
    )
    expected = 0.02655 * flin * row["type50_wavelength_A"] * 1.0e-8 / vtherm
    assert results[0]["opakab"] == expected
    assert int(stats["family_4_50"]) == 1


def test_v0640_candidate_summary_preserves_decisive_contract() -> None:
    evaluation = {
        "schema_version": "0.6.40", "accepted_gate": True,
        "product_candidate": True, "product_promoted": False,
        "seed_elision_differential": False, "active": True,
        "live_matrix_commit": True, "whole_evaluation_fallback": True,
        "python_seed_path_retained": False, "verification_enabled": True,
        "full_reverse_verification": True, "order_preserving_commit": False,
        "status": "TYPE50_OPAKAB_STATE_RESTORATION_CANDIDATE_EXACT",
        "family_record_counts": {"4:50": 2, "3:51": 1, "3:63": 1, "42:88": 1},
        "fast_path_record_counts": {"4:50": 2, "3:63": 1, "42:88": 1},
        "type50_opakab_records_expected": 2,
        "type50_opakab_records_compared": 2,
        "type50_opakab_mismatches": 0,
        "native_scalar_mismatches": 0, "row_mismatches": 0,
        "result_state_records_compared": 4, "result_state_mismatches": 0,
        "ordered_stream_exact": True, "all_matrix_checkpoints_exact": True,
        "solver_input_checkpoint_exact": True,
    }
    summary = summarize_rate_payload_four_family_product(
        {"mg_rate_payload_four_family_product_evaluations": [evaluation]}
    )
    assert summary["status"] == "TYPE50_OPAKAB_STATE_RESTORATION_CANDIDATE_EXACT"
    assert summary["product_activations"] == 1
    assert summary["type50_opakab_records_expected"] == 2
    assert summary["type50_opakab_records_compared"] == 2
    assert summary["type50_opakab_mismatches"] == 0
    assert summary["native_scalar_mismatches"] == 0
    assert summary["row_mismatches"] == 0
    assert summary["result_state_mismatches"] == 0
    assert summary["all_matrix_checkpoints_exact"] is True
    assert summary["solver_input_checkpoint_exact"] is True
