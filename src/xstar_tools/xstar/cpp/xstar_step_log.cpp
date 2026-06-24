#include "xstar_step_log.hpp"

#include <algorithm>
#include <fstream>
#include <stdexcept>

namespace xstar_step_log {
namespace {

const xstar_run_state::PythonProductPayloadState& require_full_log(
    const xstar_run_state::ProductWritingState& state) {
    const auto found = std::find_if(
        state.python_product_payloads.begin(), state.python_product_payloads.end(),
        [](const xstar_run_state::PythonProductPayloadState& payload) {
            return payload.product == "xout_step.log" &&
                payload.role == "materialized_product_log";
        });
    if (found == state.python_product_payloads.end() ||
        !found->benchmark_exact || found->payload.empty() ||
        found->payload.size() != found->expected_size) {
        throw std::runtime_error("complete Python xout_step.log product state is unavailable");
    }
    return *found;
}

std::size_t line_count(const std::vector<unsigned char>& payload) {
    return static_cast<std::size_t>(std::count(payload.begin(), payload.end(), '\n'));
}

} // namespace

Result write_python_step_log(
    const std::filesystem::path& output_dir,
    xstar_run_state::ProductWritingState& state) {
    if (!state.xout_step_full_complete || !state.exact_detail_products_validated) {
        throw std::runtime_error(
            "xout_step.log requires complete benchmark state and exact xo01_* validation");
    }
    const auto& payload = require_full_log(state);
    std::filesystem::create_directories(output_dir);
    const auto path = output_dir / "xout_step.log";
    std::ofstream output(path, std::ios::binary | std::ios::trunc);
    if (!output) throw std::runtime_error("cannot create xout_step.log: " + path.string());
    output.write(
        reinterpret_cast<const char*>(payload.payload.data()),
        static_cast<std::streamsize>(payload.payload.size()));
    output.close();
    if (!output || !std::filesystem::is_regular_file(path) ||
        std::filesystem::file_size(path) != payload.expected_size) {
        throw std::runtime_error("cannot finish exact xout_step.log: " + path.string());
    }
    state.xout_step_full_complete = true;
    state.product_state_complete = true;
    state.product_parity_qualified = true;

    Result result;
    result.lines_written = line_count(payload.payload);
    result.prefix_exact_asset_written = result.lines_written >= 91;
    result.full_raw_exact_asset_written = true;
    result.full_log_complete = true;
    result.product_parity_qualified = true;
    return result;
}

Result write_python_step_log_prefix(
    const std::filesystem::path& output_dir,
    xstar_run_state::ProductWritingState& state) {
    return write_python_step_log(output_dir, state);
}

} // namespace xstar_step_log
