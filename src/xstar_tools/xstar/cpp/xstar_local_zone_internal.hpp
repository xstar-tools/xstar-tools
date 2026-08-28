// Internal C++ publication bridge.  This is not part of the public C ABI.
#ifndef XSTAR_LOCAL_ZONE_INTERNAL_HPP
#define XSTAR_LOCAL_ZONE_INTERNAL_HPP

#include "xstar_local_zone_engine.h"
#include <array>
#include <cstddef>
#include <cstdint>
#include <map>
#include <tuple>
#include <vector>

namespace xstar_local_zone_internal {

struct PublicationStateV0682292 {
    std::map<int, std::vector<double>> ionization_rates;
    std::map<int, std::vector<double>> recombination_rates;
    std::map<int, std::array<double,4>> element_thermal;
    // 0.6.82.29.3.1: private publication surface for literal pprint(7).
    // Key is {atomic_number, ion_stage, local_level}.
    std::map<std::tuple<int,int,int>, double> level_gamma;
    std::map<std::tuple<int,int,int>, double> level_alpha;
    std::map<std::tuple<int,int,int>, std::int64_t> level_igammamax;
    std::map<std::tuple<int,int,int>, std::int64_t> level_ialphamax;
    // 0.6.82.29.3.3.1: publication-only literal pprint(4) flinel owner.
    // calc_emis_all retains caller-owned calc_emisab flinel and adds selected
    // calc_emis line contributions; production transport state remains unchanged.
    std::vector<double> option4_flinel;
    double free_free_heating = 0.0;
    double brems_cooling = 0.0;
};

void capture_publication_state_v0682292(
    const xstar_fixed_state_context* context,
    PublicationStateV0682292& out);

// 0.6.82.31: private performance-only fixed-state/controller attribution.
// This deliberately stays outside the public C ABI so the accepted 6048110 /
// 60488 interfaces remain frozen. Every field is observational only.
struct PerformanceFoundationV068231 {
    std::uint64_t fixed_calls = 0u;
    double record_preparation_seconds = 0.0;
    double preliminary_cache_seconds = 0.0;
    double evaluated_record_seconds = 0.0;
    double contribution_list_seconds = 0.0;
    double element_input_seconds = 0.0;
    double matrix_workspace_seconds = 0.0;
    double retained_array_seconds = 0.0;
    double spectral_workspace_seconds = 0.0;
    double level_population_scratch_seconds = 0.0;
    double bound_free_workspace_seconds = 0.0;
    std::uint64_t preliminary_cache_capacity_growths = 0u;
    std::uint64_t preliminary_cache_capacity_reuses = 0u;
    std::uint64_t evaluated_capacity_growths = 0u;
    std::uint64_t evaluated_capacity_reuses = 0u;
    std::uint64_t contribution_capacity_growths = 0u;
    std::uint64_t contribution_capacity_reuses = 0u;
    // 0.6.82.40.2.14 contribution-list hot-path qualification.
    std::uint64_t contribution_hotpath_optimized_calls_v068240214 = 0u;
    std::uint64_t contribution_hotpath_historical_calls_v068240214 = 0u;
    std::uint64_t contribution_geometric_growths_v068240214 = 0u;
    std::uint64_t contribution_temporary_copies_elided_v068240214 = 0u;
    std::uint64_t contribution_diagnostic_maps_elided_v068240214 = 0u;
    std::uint64_t contribution_direct_thermal_build_calls_v068240214 = 0u;
    std::uint64_t contribution_thermal_term_capacity_growths_v068240214 = 0u;
    std::uint64_t contribution_thermal_term_capacity_reuses_v068240214 = 0u;
    // 0.6.82.40.2.15 traversal-orchestration hot-path qualification.
    std::uint64_t traversal_hotpath_optimized_calls_v068240215 = 0u;
    std::uint64_t traversal_hotpath_historical_calls_v068240215 = 0u;
    std::uint64_t option10_postpass_records_considered_v068240215 = 0u;
    std::uint64_t option10_postpass_records_elided_v068240215 = 0u;
    std::uint64_t option10_endpoint_cache_hits_v068240215 = 0u;
    std::uint64_t errc_postpass_records_considered_v068240215 = 0u;
    std::uint64_t errc_postpass_records_elided_v068240215 = 0u;
    std::uint64_t postpass_index_capacity_growths_v068240215 = 0u;
    std::uint64_t postpass_index_capacity_reuses_v068240215 = 0u;
    double option10_ownership_seconds_v068240215 = 0.0;
    double errc_ownership_seconds_v068240215 = 0.0;
    std::uint64_t element_buffer_reuses = 0u;
    std::uint64_t leveltemp_backup_reuses = 0u;
    std::uint64_t reduced_continuum_geometry_builds = 0u;
    std::uint64_t reduced_continuum_geometry_reuses = 0u;
    std::uint64_t reduced_continuum_live_updates = 0u;
    std::uint64_t spectral_workspace_reuses = 0u;
    std::uint64_t persistent_reserved_bytes = 0u;
    std::uint64_t persistent_peak_reserved_bytes = 0u;
    // 0.6.82.35.2: capacity-only ownership breakdown for the persistent
    // fixed-state scratch. These categories are observational and sum to the
    // same lower-bound capacity accounting as persistent_reserved_bytes.
    std::uint64_t persistent_record_cache_bytes = 0u;
    std::uint64_t persistent_contribution_bytes = 0u;
    std::uint64_t persistent_population_bytes = 0u;
    std::uint64_t persistent_spectral_bytes = 0u;
    std::uint64_t persistent_element_solver_bytes = 0u;
    std::uint64_t persistent_continuum_bytes = 0u;
    // 0.6.82.35.1: observation-only element/matrix work counters.
    std::uint64_t element_solve_calls = 0u;
    std::uint64_t matrix_rows_sum = 0u;
    std::uint64_t matrix_rows_max = 0u;
    std::uint64_t matrix_terms_sum = 0u;
    std::uint64_t matrix_terms_max = 0u;
    std::uint64_t matrix_superlevels_sum = 0u;
    std::uint64_t matrix_superlevels_max = 0u;
    std::uint64_t population_outer_iterations = 0u;
    std::uint64_t population_fixed_iterations = 0u;
    // 0.6.82.36.4: observation-only count used to qualify whether the
    // remaining dense n*n matrix can later become rescue-on-demand.
    std::uint64_t dense_rescue_count_v0682364 = 0u;
    // 0.6.82.36.11: accepted-boundary record-product ownership telemetry.
    // All values are observational lower-bound capacity accounting and do not
    // participate in scientific or publication decisions.
    std::uint64_t rich_record_count_peak_v06823611 = 0u;
    std::uint64_t compact_record_count_peak_v06823611 = 0u;
    std::uint64_t rich_record_inline_capacity_bytes_peak_v06823611 = 0u;
    std::uint64_t compact_record_inline_capacity_bytes_peak_v06823611 = 0u;
    std::uint64_t legacy_rich_inline_equivalent_bytes_peak_v06823611 = 0u;
    std::uint64_t legacy_rich_getter_copy_equivalent_bytes_peak_v06823611 = 0u;
    std::uint64_t compact_sort_index_upper_bound_bytes_peak_v06823611 = 0u;
    std::uint64_t rich_bound_free_sidecar_count_peak_v06823611 = 0u;
    std::uint64_t rich_bound_free_sidecar_bytes_peak_v06823611 = 0u;
    std::uint64_t rich_generic_bound_free_dynamic_capacity_bytes_peak_v06823611 = 0u;
    std::uint64_t evaluated_record_inline_capacity_bytes_peak_v06823611 = 0u;
    std::uint64_t evaluated_bound_free_sidecar_count_peak_v06823611 = 0u;
    std::uint64_t evaluated_bound_free_sidecar_bytes_peak_v06823611 = 0u;
    std::uint64_t evaluated_generic_bound_free_dynamic_capacity_bytes_peak_v06823611 = 0u;
    std::uint64_t element_diagnostic_inline_capacity_bytes_peak_v06823611 = 0u;
    std::uint64_t element_diagnostic_nested_capacity_bytes_peak_v06823611 = 0u;
    std::uint64_t thermal_diagonal_capacity_bytes_peak_v06823611 = 0u;
    std::uint64_t last_source_workspace_capacity_bytes_peak_v06823611 = 0u;
    std::uint64_t compact_record_release_bytes_peak_v06823611 = 0u;
    // 0.6.82.36.12: nested-owner attribution that was invisible to the
    // capacity-only persistent scratch counters in .36.11.
    std::uint64_t preliminary_bound_free_sidecar_count_peak_v06823612 = 0u;
    std::uint64_t preliminary_bound_free_sidecar_bytes_peak_v06823612 = 0u;
    std::uint64_t revisit_record_count_peak_v06823612 = 0u;
    std::uint64_t revisit_record_inline_bytes_peak_v06823612 = 0u;
    std::uint64_t revisit_bound_free_sidecar_count_peak_v06823612 = 0u;
    std::uint64_t revisit_bound_free_sidecar_bytes_peak_v06823612 = 0u;
    std::uint64_t thermal_diagonal_rows_elided_peak_v06823612 = 0u;
    std::uint64_t thermal_diagonal_bytes_elided_peak_v06823612 = 0u;
    // 0.6.82.36.13: compact prepared Type49/53 geometry-cache ownership.
    std::uint64_t bf_reduced_sgbar_capacity_bytes_current_v06823613 = 0u;
    std::uint64_t bf_reduced_sgbar_capacity_bytes_peak_v06823613 = 0u;
    std::uint64_t bf_reduced_sgbar_dense_equivalent_bytes_peak_v06823613 = 0u;
    std::uint64_t bf_full_sgbar_capacity_bytes_current_v06823613 = 0u;
    std::uint64_t bf_full_sgbar_capacity_bytes_peak_v06823613 = 0u;
    std::uint64_t bf_full_sgbar_dense_equivalent_bytes_peak_v06823613 = 0u;
    std::uint64_t bf_sgbar_compacted_geometry_count_v06823613 = 0u;
    std::uint64_t bf_sgbar_compact_values_current_v06823613 = 0u;
    std::uint64_t bf_sgbar_dense_values_current_v06823613 = 0u;
    // 0.6.82.36.14: compact retained Type-49/53 revisit ownership.
    std::uint64_t revisit_compact_count_peak_v06823614 = 0u;
    std::uint64_t revisit_compact_inline_bytes_peak_v06823614 = 0u;
    std::uint64_t revisit_legacy_rich_equivalent_bytes_peak_v06823614 = 0u;
    std::uint64_t revisit_bytes_elided_peak_v06823614 = 0u;
    // 0.6.82.36.15: hot EvaluatedRecord representation and production-only
    // telemetry-overhead elision.  These remain observation-only counters.
    std::uint64_t evaluated_record_bytes_v06823615 = 0u;
    std::uint64_t evaluated_record_legacy_bytes_v06823615 = 0u;
    std::uint64_t evaluated_record_bytes_elided_v06823615 = 0u;
    std::uint64_t preliminary_scan_records_elided_v06823615 = 0u;
    std::uint64_t evaluated_scan_records_elided_v06823615 = 0u;
    std::uint64_t incremental_memory_telemetry_calls_v06823615 = 0u;
    std::uint64_t deep_memory_telemetry_calls_v06823615 = 0u;
    // 0.6.82.37: phase-1 compiled execution-plan telemetry.  These fields
    // measure the flat source-order index representation and direct-selection
    // traffic only; they do not participate in scientific decisions.
    std::uint64_t execution_plan_records_v068237 = 0u;
    std::uint64_t execution_plan_elements_v068237 = 0u;
    std::uint64_t execution_plan_index_bytes_v068237 = 0u;
    std::uint64_t execution_plan_preliminary_entries_v068237 = 0u;
    std::uint64_t direct_selection_records_v068237 = 0u;
    std::uint64_t identity_map_entries_elided_v068237 = 0u;
    // 0.6.82.37.1: sparse Type-49/53 execution slice.
    std::uint64_t bound_free_execution_records_v0682371 = 0u;
    std::uint64_t bound_free_slot_map_bytes_v0682371 = 0u;
    std::uint64_t bound_free_sparse_cache_bytes_v0682371 = 0u;
    std::uint64_t bound_free_dense_cache_equivalent_bytes_v0682371 = 0u;
    std::uint64_t bound_free_cache_bytes_elided_v0682371 = 0u;
    std::uint64_t bound_free_predecoded_context_bytes_v0682371 = 0u;
    std::uint64_t bound_free_predecoded_context_hits_v0682371 = 0u;
    // 0.6.82.37.2: accepted-boundary transient ownership compaction.
    std::uint64_t compact_element_diagnostic_count_peak_v0682372 = 0u;
    std::uint64_t consumed_evaluated_records_cleared_peak_v0682372 = 0u;
    std::uint64_t consumed_preliminary_records_cleared_peak_v0682372 = 0u;
    std::uint64_t deferred_rrc_count_peak_v0682372 = 0u;
    std::uint64_t deferred_rrc_inline_bytes_peak_v0682372 = 0u;
    std::uint64_t deferred_rrc_sample_bytes_peak_v0682372 = 0u;
    std::uint64_t deferred_rrc_duplicate_sample_bytes_elided_peak_v0682372 = 0u;
    std::uint64_t deferred_rrc_evaluated_inline_bytes_elided_peak_v0682372 = 0u;
    std::uint64_t deferred_rrc_bound_free_payload_bytes_elided_peak_v0682372 = 0u;
    // 0.6.82.37.3 emission-view replay telemetry.
    std::uint64_t deferred_rrc_temp_curve_builds_elided_peak_v0682373 = 0u;
    std::uint64_t deferred_rrc_temp_curve_sample_bytes_elided_peak_v0682373 = 0u;
    std::uint64_t deferred_rrc_opacity_source_pairs_peak_v0682373 = 0u;
    std::uint64_t deferred_rrc_emission_source_pairs_peak_v0682373 = 0u;
    // 0.6.82.37.4: mutually exclusive Type-49/53 shadow-family compaction.
    std::uint64_t bound_free_sidecar_bytes_v0682374 = 0u;
    std::uint64_t bound_free_sidecar_legacy_bytes_v0682374 = 0u;
    std::uint64_t bound_free_sidecar_bytes_elided_per_sidecar_v0682374 = 0u;
    std::uint64_t bound_free_sidecar_peak_bytes_elided_v0682374 = 0u;
    // 0.6.82.37.5: final .37 execution-representation pass.  The canonical
    // source record remains the cold identity/publication owner while the
    // evaluator consumes a compact direct-indexed hot execution header.
    std::uint64_t program_record_count_v0682375 = 0u;
    std::uint64_t program_record_cold_bytes_v0682375 = 0u;
    std::uint64_t program_record_hot_bytes_v0682375 = 0u;
    std::uint64_t program_record_legacy_bytes_v0682375 = 0u;
    std::uint64_t program_record_total_bytes_v0682375 = 0u;
    std::uint64_t program_record_bytes_elided_per_record_v0682375 = 0u;
    std::uint64_t program_record_bytes_elided_total_v0682375 = 0u;
    // 0.6.82.38.1: accepted-boundary spectral lookup compaction.  These are
    // observation-only counters for replacing repeated full ProgramRecord hash
    // rebuilds and Type-49 linear contribution scans with the persistent dense
    // record-index lookup populated in source order.
    std::uint64_t spectral_record_index_bytes_peak_v0682381 = 0u;
    std::uint64_t spectral_record_index_populated_peak_v0682381 = 0u;
    std::uint64_t spectral_direct_record_lookups_v0682381 = 0u;
    std::uint64_t spectral_direct_contribution_lookups_v0682381 = 0u;
    std::uint64_t spectral_program_hash_rebuilds_elided_v0682381 = 0u;
    std::uint64_t spectral_type49_linear_scans_elided_v0682381 = 0u;
    // 0.6.82.39: first retained-state/lifetime tranche.  Accepted-boundary
    // native production discards matrix-only EvaluatedRecord ownership as soon
    // as the canonical contribution/product rows have been captured.  The
    // phase RSS fields are observation-only /proc samples used to locate the
    // remaining fixed-state high-water without changing public ABIs.
    std::uint64_t postsolve_compaction_calls_v068239 = 0u;
    std::uint64_t postsolve_records_before_peak_v068239 = 0u;
    std::uint64_t postsolve_records_retained_peak_v068239 = 0u;
    std::uint64_t postsolve_records_discarded_total_v068239 = 0u;
    std::uint64_t postsolve_bound_free_sidecars_released_total_v068239 = 0u;
    std::uint64_t postsolve_bound_free_sidecar_bytes_released_total_v068239 = 0u;
    std::uint64_t postsolve_dead_inline_bytes_peak_v068239 = 0u;
    // 0.6.82.39.1 reachability audit: distinguish the ordinary production
    // physics profile from an explicit rich-forensic request.
    std::uint64_t postsolve_production_reachable_calls_v0682391 = 0u;
    std::uint64_t postsolve_generic_replacement_bypass_calls_v0682391 = 0u;
    std::uint64_t postsolve_explicit_forensic_blocks_v0682391 = 0u;
    std::uint64_t fixed_phase_rss_samples_v068239 = 0u;
    std::uint64_t fixed_phase_rss_peak_bytes_v068239 = 0u;
    std::uint64_t fixed_phase_rss_peak_phase_v068239 = 0u;
    std::uint64_t fixed_phase_rss_after_pass2_peak_v068239 = 0u;
    std::uint64_t fixed_phase_rss_after_contribution_peak_v068239 = 0u;
    std::uint64_t fixed_phase_rss_after_buffers_peak_v068239 = 0u;
    std::uint64_t fixed_phase_rss_after_solve_peak_v068239 = 0u;
    std::uint64_t fixed_phase_rss_after_mapback_peak_v068239 = 0u;
    // 0.6.82.39.2: actual capacity lifetime transfer/release.  These fields
    // are observation-only and quantify storage ownership removed from later
    // accepted-boundary phases; no scientific arithmetic depends on them.
    std::uint64_t phase_capacity_release_calls_v0682392 = 0u;
    std::uint64_t traversal_capacity_released_peak_bytes_v0682392 = 0u;
    std::uint64_t traversal_capacity_released_total_bytes_v0682392 = 0u;
    std::uint64_t spectral_owner_transfer_calls_v0682392 = 0u;
    std::uint64_t spectral_duplicate_capacity_released_peak_bytes_v0682392 = 0u;
    std::uint64_t spectral_duplicate_capacity_released_total_bytes_v0682392 = 0u;
    std::uint64_t spectral_capacity_transferred_peak_bytes_v0682392 = 0u;
    std::uint64_t post_spectral_capacity_release_calls_v0682392 = 0u;
    std::uint64_t post_spectral_capacity_released_peak_bytes_v0682392 = 0u;
    std::uint64_t post_spectral_capacity_released_total_bytes_v0682392 = 0u;
    std::uint64_t rss_before_traversal_release_peak_v0682392 = 0u;
    std::uint64_t rss_after_traversal_release_peak_v0682392 = 0u;
    std::uint64_t rss_traversal_release_reduction_peak_v0682392 = 0u;
    std::uint64_t rss_before_spectral_transfer_peak_v0682392 = 0u;
    std::uint64_t rss_after_spectral_transfer_peak_v0682392 = 0u;
    std::uint64_t rss_spectral_transfer_reduction_peak_v0682392 = 0u;
    std::uint64_t rss_before_post_spectral_release_peak_v0682392 = 0u;
    std::uint64_t rss_after_post_spectral_release_peak_v0682392 = 0u;
    std::uint64_t rss_post_spectral_release_reduction_peak_v0682392 = 0u;
    // 0.6.82.40.2.2: observation-only ATDB activation census.  The full
    // catalog is not an expectation: counters are emitted only for labels
    // actually evaluated by the canonical/C++ paths.  0..110 matches the
    // diagnostic FORTRAN array and safely contains the current native labels.
    std::array<std::uint64_t, 111> evaluated_records_by_type{};
    std::array<std::uint64_t, 111> evaluated_records_by_rate_type_v06824022{};
    std::array<std::array<std::uint64_t, 111>, 111> evaluated_records_by_type_rate_v06824022{};
    std::array<std::uint64_t, 111> ans1_nonzero_by_type_v06824022{};
    std::array<std::uint64_t, 111> ans2_nonzero_by_type_v06824022{};
    std::array<double, 111> ans1_abs_sum_by_type_v06824022{};
    std::array<double, 111> ans2_abs_sum_by_type_v06824022{};
    std::array<std::uint64_t, 111> matrix_records_by_type_v06824022{};
    std::array<std::uint64_t, 111> spectral_records_by_type_v06824022{};
    std::array<std::uint64_t, 111> bound_free_records_by_type_v06824022{};
    std::array<std::uint64_t, 111> real_payload_values_by_type_v06824022{};
    std::array<std::uint64_t, 111> int_payload_values_by_type_v06824022{};

    // 0.6.82.40.2.5: narrow low-ionization family diagnostics.  Family
    // indices are: 1=53/59/74/99 bound-free/recombination,
    // 2=51/56/63/77 electron-collision, 3=2/9 charge exchange, and
    // 4=Type-50 control.  EVAL_SECONDS reuses the pre-existing per-record
    // rate timer and therefore adds no new clock read in the hot evaluator.
    std::array<double, 5> ion_family_eval_seconds_v06824025{};
    std::array<std::uint64_t, 5> ion_family_eval_calls_v06824025{};
    std::array<std::uint64_t, 5> ion_family_first_rss_before_v06824025{};
    std::array<std::uint64_t, 5> ion_family_first_rss_after_v06824025{};
    std::array<std::uint64_t, 5> ion_family_first_record_index_v06824025{};
    std::array<std::uint64_t, 111> ion_unique_records_touched_by_type_v06824025{};
    std::array<std::uint64_t, 111> ion_unique_real_payload_bytes_by_type_v06824025{};
    std::array<std::uint64_t, 111> ion_unique_int_payload_bytes_by_type_v06824025{};
    std::array<std::uint64_t, 111> ion_unique_hot_record_bytes_by_type_v06824025{};
    std::array<std::uint64_t, 111> ion_unique_cold_record_bytes_by_type_v06824025{};
    std::array<std::uint64_t, 111> ion_unique_payload_page_bytes_by_type_v06824025{};
    std::array<std::uint64_t, 111> ion_unique_resident_payload_page_bytes_by_type_v06824025{};
    std::array<std::uint64_t, 111> ion_prepared_cache_bytes_by_type_v06824025{};

    // 0.6.82.40.2.6: production Type-53 legacy-prepass elision.  The
    // source-faithful Type-53 evaluator is the committed native-production
    // owner whenever a lowered record context is valid.  Count the generic
    // legacy pair loop only for explicit forensic/fallback execution.
    std::uint64_t type53_legacy_prepass_executed_calls_v06824026 = 0u;
    std::uint64_t type53_legacy_prepass_elided_calls_v06824026 = 0u;
    std::uint64_t type53_legacy_pair_interpolations_executed_v06824026 = 0u;
    std::uint64_t type53_legacy_pair_interpolations_elided_v06824026 = 0u;

    // 0.6.82.40.2.27: same-binary Type-53 static-kernel qualification.
    // These counters are private diagnostics and add no ABI surface or clock.
    std::uint64_t type53_static_historical_calls_v068240227 = 0u;
    std::uint64_t type53_static_optimized_calls_v068240227 = 0u;
    std::uint64_t type53_static_fallback_calls_v068240227 = 0u;
    std::uint64_t type53_static_fixed_contexts_v068240227 = 0u;
    std::uint64_t type53_static_geometry_builds_v068240227 = 0u;
    std::uint64_t type53_static_bbnurj_values_prepared_v068240227 = 0u;
};

// 0.6.82.40.2.8: narrow live-owner view used only by the fixed/controller
// diagnostic sweep.  These are current capacity lower bounds, not allocator
// ownership claims, and never participate in scientific decisions.
struct FixedLiveOwnerMemoryV06824028 {
    std::uint64_t persistent_scratch_bytes = 0u;
    std::uint64_t persistent_record_cache_bytes = 0u;
    std::uint64_t persistent_contribution_bytes = 0u;
    std::uint64_t persistent_population_bytes = 0u;
    std::uint64_t persistent_spectral_bytes = 0u;
    std::uint64_t persistent_element_solver_bytes = 0u;
    std::uint64_t persistent_continuum_bytes = 0u;
    std::uint64_t last_source_workspace_capacity_bytes = 0u;
    std::uint64_t compact_record_capacity_bytes = 0u;
    std::uint64_t rich_record_capacity_bytes = 0u;
    std::uint64_t prepared_bound_free_capacity_bytes = 0u;
    std::uint64_t execution_plan_capacity_bytes = 0u;
    std::uint64_t retained_state_capacity_bytes = 0u;
};

void capture_fixed_live_owner_memory_v06824028(
    const xstar_fixed_state_context* context,
    FixedLiveOwnerMemoryV06824028& out);

void capture_performance_foundation_v068231(
    const xstar_fixed_state_context* context,
    PerformanceFoundationV068231& out);

// 0.6.82.36.11: once the standalone has copied the compact production record
// products into its accepted-boundary snapshot, no native fixed-state consumer
// needs that retained vector. Release its capacity before later publication
// staging so accepted-boundary ownership cannot overlap unnecessarily.
std::uint64_t release_compact_record_products_v06823611(
    xstar_fixed_state_context* context);

} // namespace xstar_local_zone_internal

#endif
