// XSTAR-SOURCE-CORRESPONDENCE-BEGIN
// Fortran: fstepr*.f90; writespectra*.f90
// Role: C++ publication API for source-equivalent scientific FITS products.
// Relation: Interface-only wrapper for the native publication owner.
// Concordance: DETAIL-001; FINAL-001
// Qualification: C++ FITS baseline 12.3.44
// XSTAR-SOURCE-CORRESPONDENCE-END

#ifndef XSTAR_SCIENCE_FITS_HPP
#define XSTAR_SCIENCE_FITS_HPP

#include <array>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <string>
#include <vector>

#include "xstar_run_state.hpp"

namespace xstar_science_fits {

using Snapshot = xstar_run_state::FixedEvaluationState;

struct IncrementalDetailResultV068233 {
    double detail_population_seconds = 0.0;
    double detail_line_seconds = 0.0;
    double detail_line_identity_seconds = 0.0;
    double detail_line_cpu_staging_seconds = 0.0;
    double detail_line_fits_write_seconds = 0.0;
    double detail_line_checksum_seconds = 0.0;
    // 0.6.82.35.2: detailed-line staging localization; observation only.
    double detail_line_diagnostic_seconds = 0.0;
    double detail_line_source_rows_seconds = 0.0;
    double detail_line_activity_shadow_seconds = 0.0;
    double detail_line_native_map_seconds = 0.0;
    std::uint64_t detail_line_zones = 0u;
    std::uint64_t detail_line_diagnostic_records_loaded = 0u;
    std::uint64_t detail_line_type50_records_considered = 0u;
    std::uint64_t detail_line_direct_index_hits = 0u;
    std::uint64_t detail_line_fallback_resolutions = 0u;
    std::uint64_t detail_line_fallback_identity_comparisons = 0u;
    std::uint64_t detail_line_source_identities_scanned = 0u;
    std::uint64_t detail_line_source_rows_retained = 0u;
    double detail_rrc_seconds = 0.0;
    double detail_rrc_cpu_staging_seconds = 0.0;
    double detail_rrc_fits_write_seconds = 0.0;
    double detail_rrc_checksum_seconds = 0.0;
    double detail_spectrum_seconds = 0.0;
    std::uint64_t zone_publication_scratch_bytes = 0u;
    std::uint64_t detail_rows = 0u;
    std::uint64_t detal2_rows = 0u;
    std::uint64_t detal3_rows = 0u;
    std::vector<xstar_run_state::IncrementalDetal2TerminalPatchStateV0682332>
        detal2_terminal_patches_v0682332;
};

IncrementalDetailResultV068233 append_incremental_detail_zone_v068233(
    const std::filesystem::path& output_dir,
    const xstar_run_state::ProductWritingState& one_zone_state,
    std::size_t pass_index);

std::uint64_t finalize_incremental_detal2_terminal_gate_v0682332(
    const std::filesystem::path& output_dir,
    const xstar_run_state::ProductWritingState& final_state);

struct Result {
    std::size_t files_written = 0;
    bool schema_complete = false;
    bool computed_from_native_state = false;
    bool continuum_and_spectrum_paths_separate = false;
    bool physical_equivalence_qualified = false;
    bool detail_products_byte_exact = false;
    bool public_products_byte_exact = false;
    bool all_fits_products_byte_exact = false;
    bool benchmark_archive_materialized = false;
    bool generalized_product_reduction_qualified = false;
    double detail_population_seconds = 0.0;
    double detail_line_seconds = 0.0;
    double detail_line_identity_seconds = 0.0;
    double detail_line_cpu_staging_seconds = 0.0;
    double detail_line_fits_write_seconds = 0.0;
    double detail_line_checksum_seconds = 0.0;
    // 0.6.82.35.2: detailed-line staging localization; observation only.
    double detail_line_diagnostic_seconds = 0.0;
    double detail_line_source_rows_seconds = 0.0;
    double detail_line_activity_shadow_seconds = 0.0;
    double detail_line_native_map_seconds = 0.0;
    std::uint64_t detail_line_zones = 0u;
    std::uint64_t detail_line_diagnostic_records_loaded = 0u;
    std::uint64_t detail_line_type50_records_considered = 0u;
    std::uint64_t detail_line_direct_index_hits = 0u;
    std::uint64_t detail_line_fallback_resolutions = 0u;
    std::uint64_t detail_line_fallback_identity_comparisons = 0u;
    std::uint64_t detail_line_source_identities_scanned = 0u;
    std::uint64_t detail_line_source_rows_retained = 0u;
    double detail_rrc_seconds = 0.0;
    double detail_rrc_cpu_staging_seconds = 0.0;
    double detail_rrc_fits_write_seconds = 0.0;
    double detail_rrc_checksum_seconds = 0.0;
    double detail_spectrum_seconds = 0.0;
    double public_lines_seconds = 0.0;
    double public_rrc_seconds = 0.0;
    double public_cont_seconds = 0.0;
    double public_spect_seconds = 0.0;
    bool public_lines_retained_fast_path = false;
    std::vector<std::string> filenames;
};

Result write_historical_science_products(
    const std::filesystem::path& program_dir,
    const std::filesystem::path& output_dir,
    const std::vector<Snapshot>& radial_snapshots,
    const std::vector<double>& native_energy_ev);

Result write_historical_science_products(
    const std::filesystem::path& program_dir,
    const std::filesystem::path& output_dir,
    xstar_run_state::ProductWritingState& product_state,
    const std::vector<double>& native_energy_ev);

bool abundance_product_enabled();

void write_native_abundance_product(
    const std::filesystem::path& program_dir,
    const std::filesystem::path& output_dir,
    xstar_run_state::ProductWritingState& product_state);

} // namespace xstar_science_fits

#endif
