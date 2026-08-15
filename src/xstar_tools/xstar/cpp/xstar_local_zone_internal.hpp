// Internal C++ publication bridge.  This is not part of the public C ABI.
#ifndef XSTAR_LOCAL_ZONE_INTERNAL_HPP
#define XSTAR_LOCAL_ZONE_INTERNAL_HPP

#include "xstar_local_zone_engine.h"
#include <array>
#include <map>
#include <vector>

namespace xstar_local_zone_internal {

struct PublicationStateV0682292 {
    std::map<int, std::vector<double>> ionization_rates;
    std::map<int, std::vector<double>> recombination_rates;
    std::map<int, std::array<double,4>> element_thermal;
    double free_free_heating = 0.0;
    double brems_cooling = 0.0;
};

void capture_publication_state_v0682292(
    const xstar_fixed_state_context* context,
    PublicationStateV0682292& out);

} // namespace xstar_local_zone_internal

#endif
