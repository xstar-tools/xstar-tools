// XSTAR-SOURCE-CORRESPONDENCE-BEGIN
// Fortran: pprint.f90
// Role: C++ interface for final/zone STEP log generation.
// Relation: Interface-only wrapper around source-mapped pprint publication.
// Concordance: STEP-001
// Qualification: STEP baseline 12.3.42/44
// XSTAR-SOURCE-CORRESPONDENCE-END

#ifndef XSTAR_STEP_LOG_HPP
#define XSTAR_STEP_LOG_HPP

#include "xstar_run_state.hpp"

#include <cstddef>
#include <filesystem>

namespace xstar_step_log {

struct Result {
    std::size_t lines_written = 0;
    bool prefix_exact_except_version = false;
    bool full_raw_exact_asset_written = false;
    bool full_log_complete = false;
    bool computed_from_native_state = false;
    bool timing_values_measured = false;
    bool product_parity_qualified = false;
};

void initialize_live_step_log_v0682331(
    const std::filesystem::path& path,
    const xstar_run_state::ProductWritingState& state,
    std::size_t source_nry,
    std::size_t output_nry);

Result write_native_step_log(
    const std::filesystem::path& output_dir,
    xstar_run_state::ProductWritingState& state);

Result write_python_step_log(
    const std::filesystem::path& output_dir,
    xstar_run_state::ProductWritingState& state);

Result write_python_step_log_prefix(
    const std::filesystem::path& output_dir,
    xstar_run_state::ProductWritingState& state);

} // namespace xstar_step_log

#endif
