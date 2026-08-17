// Internal C++ publication bridge.  This is not part of the public C ABI.
#ifndef XSTAR_LOCAL_ZONE_INTERNAL_HPP
#define XSTAR_LOCAL_ZONE_INTERNAL_HPP

#include "xstar_local_zone_engine.h"
#include <array>
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

} // namespace xstar_local_zone_internal

#endif
