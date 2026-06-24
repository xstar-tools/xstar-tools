#include "xstar_step_log.hpp"

#include <stdexcept>

namespace xstar_step_log {
namespace {
[[noreturn]] void reject_unretained_native_product_state() {
    throw std::runtime_error(
        "native xout_step.log construction is unavailable: the complete ProductWritingState "
        "is not retained independently of benchmark FITS/log payloads");
}
} // namespace

Result write_python_step_log(
    const std::filesystem::path&,
    xstar_run_state::ProductWritingState&) {
    reject_unretained_native_product_state();
}

Result write_python_step_log_prefix(
    const std::filesystem::path&,
    xstar_run_state::ProductWritingState&) {
    reject_unretained_native_product_state();
}

} // namespace xstar_step_log
