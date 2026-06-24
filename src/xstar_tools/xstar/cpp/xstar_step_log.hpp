#ifndef XSTAR_STEP_LOG_HPP
#define XSTAR_STEP_LOG_HPP

#include "xstar_run_state.hpp"

#include <cstddef>
#include <filesystem>

namespace xstar_step_log {

struct Result {
    std::size_t lines_written = 0;
    bool prefix_exact_asset_written = false;
    bool full_raw_exact_asset_written = false;
    bool full_log_complete = false;
    bool product_parity_qualified = false;
};

Result write_python_step_log(
    const std::filesystem::path& output_dir,
    xstar_run_state::ProductWritingState& state);

// Compatibility entrypoint retained for inherited callers; v24 writes the
// complete Python product log rather than only the 91-line prefix.
Result write_python_step_log_prefix(
    const std::filesystem::path& output_dir,
    xstar_run_state::ProductWritingState& state);

} // namespace xstar_step_log

#endif
