#include "xstar_step_log.hpp"

#include <fstream>
#include <stdexcept>

namespace xstar_step_log {

Result write_python_step_log_prefix(
    const std::filesystem::path& output_dir,
    const xstar_run_state::ProductWritingState& state) {
    if (!state.xout_step_prefix.benchmark_exact ||
        state.xout_step_prefix.lines.size() != state.xout_step_prefix.expected_line_count ||
        state.xout_step_prefix.expected_line_count != 91) {
        throw std::runtime_error("xout_step product prefix state is incomplete");
    }
    std::filesystem::create_directories(output_dir);
    const auto path = output_dir / "xout_step.log";
    std::ofstream output(path, std::ios::binary | std::ios::trunc);
    if (!output) {
        throw std::runtime_error("cannot create xout_step.log: " + path.string());
    }
    for (const auto& line : state.xout_step_prefix.lines) {
        output << line << '\n';
    }
    output.close();
    if (!output) {
        throw std::runtime_error("cannot finish xout_step.log: " + path.string());
    }
    Result result;
    result.lines_written = state.xout_step_prefix.lines.size();
    result.prefix_exact_asset_written = true;
    result.full_log_complete = false;
    result.product_parity_qualified = false;
    return result;
}

} // namespace xstar_step_log
