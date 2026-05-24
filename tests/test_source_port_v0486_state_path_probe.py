from __future__ import annotations

from types import SimpleNamespace

from xstar_atomic.source_port.zone1_dsec_diagnostic import (
    extract_python_carbon_alias_boundaries,
    extract_python_carbon_stage_totals,
    extract_python_carbon_state_path,
    extract_python_hydrogen_state_path,
)
from xstar_atomic.xstar_zone1_dsec_probe import (
    zone1_extra_helper,
    zone1_insertion_snippets,
)


def _result_with_trace():
    return SimpleNamespace(
        carbon_state_path={
            "hydrogen": [
                {
                    "source": "python",
                    "phase_code": 10,
                    "phase": "calc_hmc_all_entry_hydrogen",
                    "hydrogen_ground_fraction": 0.25,
                    "hydrogen_abundance": 1.0,
                    "hydrogen_density_cm3": 8.0,
                    "neutral_h_density_cm3": 2.0,
                    "ionized_h_density_cm3": 6.0,
                }
            ],
            "levels": [
                {
                    "source": "python",
                    "phase_code": 20,
                    "phase": "calc_hmc_all_map_global_to_element_entry",
                    "outer_iteration": 0,
                    "fixed_iteration": 0,
                    "compact_index": 0,
                    "superlevel": 0,
                    "ion_counter": 0,
                    "ion_stage": 3,
                    "ion_index": 10,
                    "local_level": 1,
                    "global_index": 100,
                    "full_element_index": 1,
                    "population": 0.4,
                },
                {
                    "source": "python",
                    "phase_code": 30,
                    "phase": "calc_hmc_element_pre_msolvelucy",
                    "outer_iteration": 0,
                    "fixed_iteration": 0,
                    "compact_index": 1,
                    "superlevel": 1,
                    "ion_counter": 1,
                    "ion_stage": 3,
                    "ion_index": 0,
                    "local_level": 0,
                    "global_index": 0,
                    "full_element_index": 0,
                    "population": 0.4,
                },
                {
                    "source": "python",
                    "phase_code": 120,
                    "phase": "calc_hmc_all_global_writeback",
                    "outer_iteration": 0,
                    "fixed_iteration": 0,
                    "compact_index": 0,
                    "superlevel": 0,
                    "ion_counter": 0,
                    "ion_stage": 3,
                    "ion_index": 10,
                    "local_level": 1,
                    "global_index": 100,
                    "full_element_index": 1,
                    "population": 0.41,
                },
            ],
            "stage_totals": [
                {
                    "source": "python",
                    "phase_code": 41,
                    "phase": "msolvelucy_outer_start_xtot",
                    "outer_iteration": 1,
                    "ion_counter": 1,
                    "ion_stage": 3,
                    "population_total": 0.4,
                },
                {
                    "source": "python",
                    "phase_code": 100,
                    "phase": "calc_hmc_element_final_vector_xii",
                    "outer_iteration": 2,
                    "ion_counter": 1,
                    "ion_stage": 3,
                    "population_total": 0.41,
                },
            ],
            "aliases": [
                {
                    "source": "python",
                    "lower_ion_index": 10,
                    "lower_ion_stage": 3,
                    "lower_local_level": 5,
                    "lower_global_index": 104,
                    "lower_population": 0.2,
                    "upper_ion_index": 11,
                    "upper_ion_stage": 4,
                    "upper_local_level": 1,
                    "upper_global_index": 104,
                    "upper_population": 0.2,
                    "absolute_difference": 0.0,
                }
            ],
        },
        hydrogen_ground_fraction=0.25,
        hydrogen_abundance=1.0,
        hydrogen_density_cm3=8.0,
        neutral_h_density_cm3=2.0,
        ionized_h_density_cm3=6.0,
    )


def test_v0486_extractors_preserve_source_order_and_evaluation_identity():
    result = _result_with_trace()
    levels = extract_python_carbon_state_path(result, evaluation_index=24)
    stages = extract_python_carbon_stage_totals(result, evaluation_index=24)
    aliases = extract_python_carbon_alias_boundaries(result, evaluation_index=24)
    hydrogen = extract_python_hydrogen_state_path(result, evaluation_index=24)

    assert [row["phase_code"] for row in levels] == [20, 30, 120]
    assert [row["phase_code"] for row in stages] == [41, 100]
    assert all(row["evaluation_index"] == 24 for row in levels)
    assert all(row["evaluation_index"] == 24 for row in stages)
    assert aliases[0]["lower_global_index"] == aliases[0]["upper_global_index"]
    assert hydrogen[0]["neutral_h_density_cm3"] == 2.0
    assert hydrogen[0]["ionized_h_density_cm3"] == 6.0


def test_v0486_original_helper_and_snippets_cover_every_state_path_phase():
    helper = zone1_extra_helper()
    snippets = zone1_insertion_snippets()
    for routine in (
        "xap_zone1_hydrogen_state",
        "xap_zone1_carbon_state_path",
        "xap_zone1_carbon_stage_total",
        "xap_zone1_alias_candidate",
    ):
        assert routine in helper
    for phase in (20, 30, 40, 41, 50, 60, 70, 80, 90, 100, 110, 120):
        assert f"({phase}," in "\n".join(snippets.values())
    assert "xap_zone1_alias_reset" in snippets["calc_hmc_all_carbon_global_writeback"]


def test_v0486_hydrogen_extractor_falls_back_to_result_scalars():
    result = SimpleNamespace(
        carbon_state_path={},
        hydrogen_ground_fraction=0.75,
        hydrogen_abundance=1.0,
        hydrogen_density_cm3=4.0,
        neutral_h_density_cm3=3.0,
        ionized_h_density_cm3=1.0,
    )
    rows = extract_python_hydrogen_state_path(result, evaluation_index=3)
    assert rows == (
        {
            "evaluation_index": 3,
            "source": "python",
            "phase_code": 10,
            "phase": "calc_hmc_all_entry_hydrogen",
            "hydrogen_ground_fraction": 0.75,
            "hydrogen_abundance": 1.0,
            "hydrogen_density_cm3": 4.0,
            "neutral_h_density_cm3": 3.0,
            "ionized_h_density_cm3": 1.0,
        },
    )
