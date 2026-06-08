from __future__ import annotations

from xstar_tools.xstar.performance import summarize_rate_payload_four_family_product
from xstar_tools.xstar.ucalc import (
    SourceFaithfulUCalc,
    UCalcContext,
    UCalcLevel,
    UCalcLevelTable,
    _source_faithful_level_threshold,
)


def test_type88_packet_threshold_uses_exact_level_threshold_semantics() -> None:
    levels = UCalcLevelTable(
        levels={
            1: UCalcLevel(index=1, energy_ev=12.0, ionization_potential_ev=100.0),
            2: UCalcLevel(index=2, energy_ev=15.0, continuum_energy_ev=90.0),
            3: UCalcLevel(index=3, energy_ev=20.0),
            4: UCalcLevel(index=4, energy_ev=120.0),
        },
        nlev=4,
    )
    assert _source_faithful_level_threshold(levels, 1, 4) == 88.0
    assert _source_faithful_level_threshold(levels, 2, 4) == 75.0
    assert _source_faithful_level_threshold(levels, 3, 4) == 100.0

    dispatcher = SourceFaithfulUCalc()
    context = UCalcContext(temperature_k=1.0e6, nlev=4, levels=levels)
    assert dispatcher._level_threshold(context, 1) == 88.0
    assert dispatcher._level_threshold(context, 2) == 75.0
    assert dispatcher._level_threshold(context, 3) == 100.0


def test_v06401_summary_preserves_hotfix_and_mismatch_provenance() -> None:
    mismatch = {
        "evaluation_index": 7,
        "record": 40380,
        "family": "42:88",
        "field": "ans1",
        "accepted_value": 1.25,
        "candidate_value": 1.5,
        "packet_threshold_eV": 88.0,
        "accepted_threshold_eV": 88.0,
    }
    evaluation = {
        "schema_version": "0.6.40.1",
        "accepted_gate": True,
        "product_candidate": True,
        "product_promoted": False,
        "seed_elision_differential": False,
        "active": False,
        "live_matrix_commit": False,
        "whole_evaluation_fallback": True,
        "python_seed_path_retained": False,
        "verification_enabled": True,
        "full_reverse_verification": True,
        "order_preserving_commit": False,
        "status": "FALLBACK_ACCEPTED_PATH",
        "native_scalar_mismatches": 1,
        "native_scalar_mismatch_fields_by_family": {
            "4:50": {}, "3:63": {}, "42:88": {"ans1": 1}
        },
        "first_native_scalar_mismatch": mismatch,
        "fallback_provenance": mismatch,
    }
    summary = summarize_rate_payload_four_family_product(
        {"mg_rate_payload_four_family_product_evaluations": [evaluation]}
    )
    assert summary["schema_version"] == "0.6.40.1"
    assert summary["status"] == "FALLBACK"
    assert summary["native_scalar_mismatch_fields_by_family"]["42:88"] == {
        "ans1": 1
    }
    assert summary["first_native_scalar_mismatches"] == [mismatch]
    assert summary["fallback_provenance_samples"] == [mismatch]


def test_v06401_candidate_success_status() -> None:
    evaluation = {
        "schema_version": "0.6.40.1",
        "accepted_gate": True,
        "product_candidate": True,
        "product_promoted": False,
        "seed_elision_differential": False,
        "active": True,
        "live_matrix_commit": True,
        "whole_evaluation_fallback": True,
        "python_seed_path_retained": False,
        "verification_enabled": True,
        "full_reverse_verification": True,
        "order_preserving_commit": False,
        "status": "TYPE88_THRESHOLD_HOTFIX_CANDIDATE_EXACT",
    }
    summary = summarize_rate_payload_four_family_product(
        {"mg_rate_payload_four_family_product_evaluations": [evaluation]}
    )
    assert summary["status"] == "TYPE88_THRESHOLD_HOTFIX_CANDIDATE_EXACT"
    assert summary["product_activations"] == 1
