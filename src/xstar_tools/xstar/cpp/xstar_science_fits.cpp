#include "xstar_science_fits.hpp"

#include <stdexcept>

namespace xstar_science_fits {
namespace {
[[noreturn]] void reject_unretained_native_detail_state() {
    throw std::runtime_error(
        "native public FITS construction is unavailable: the controller does not yet retain "
        "the binary64 population-detail, line, RRC, directional-transport, continuum-channel, "
        "and profile workspaces required to construct xo01_* and xout_* without benchmark bytes");
}
} // namespace

Result write_historical_science_products(
    const std::filesystem::path&,
    const std::filesystem::path&,
    const std::vector<Snapshot>&,
    const std::vector<double>&) {
    reject_unretained_native_detail_state();
}

Result write_historical_science_products(
    const std::filesystem::path&,
    const std::filesystem::path&,
    xstar_run_state::ProductWritingState&,
    const std::vector<double>&) {
    reject_unretained_native_detail_state();
}

} // namespace xstar_science_fits
