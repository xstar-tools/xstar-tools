#include "xstar_backend_common.hpp"
#include <sstream>

extern "C" {

int xstar_thermal_abi_version() {
    return 1;
}

const char* xstar_thermal_backend_name() {
    return "xstar_thermal_skeleton_flat_cpp_v065";
}

int xstar_thermal_feature_flags() {
    return 0;
}

int xstar_thermal_probe(int n_elements, int n_zones, char* message, std::size_t message_size) {
    if (!xstar_backend::valid_count(n_elements) || !xstar_backend::valid_count(n_zones)) {
        xstar_backend::write_message(message, message_size, "invalid negative element/zone count");
        return xstar_backend::XSTAR_BACKEND_ERR_INVALID_ARGUMENT;
    }
    std::ostringstream out;
    out << "libxstar_thermal.so skeleton available; n_elements=" << n_elements
        << "; n_zones=" << n_zones << "; no thermal physics active";
    xstar_backend::write_message(message, message_size, out.str());
    return xstar_backend::XSTAR_BACKEND_OK;
}

}
