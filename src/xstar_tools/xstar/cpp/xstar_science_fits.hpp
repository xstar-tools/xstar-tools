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
#include <filesystem>
#include <string>
#include <vector>

#include "xstar_run_state.hpp"

namespace xstar_science_fits {

using Snapshot = xstar_run_state::FixedEvaluationState;

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
