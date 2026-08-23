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
    std::array<std::uint64_t, 103> evaluated_records_by_type{};
};

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
