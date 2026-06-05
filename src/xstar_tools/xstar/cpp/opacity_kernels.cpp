#include "xstar_backend_common.hpp"
#include <sstream>

extern "C" {

int xstar_opacity_abi_version() {
    return 1;
}

const char* xstar_opacity_backend_name() {
    return "xstar_opacity_skeleton_flat_cpp_v065";
}

int xstar_opacity_feature_flags() {
    return 0;
}

int xstar_opacity_probe(int n_records, char* message, std::size_t message_size) {
    if (!xstar_backend::valid_count(n_records)) {
        xstar_backend::write_message(message, message_size, "invalid negative n_records");
        return xstar_backend::XSTAR_BACKEND_ERR_INVALID_ARGUMENT;
    }
    std::ostringstream out;
    out << "libxstar_opacity.so skeleton available; n_records=" << n_records << "; no opacity physics active";
    xstar_backend::write_message(message, message_size, out.str());
    return xstar_backend::XSTAR_BACKEND_OK;
}

}
