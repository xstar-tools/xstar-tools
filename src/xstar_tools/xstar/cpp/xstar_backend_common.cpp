#include "xstar_backend_common.hpp"

extern "C" {

int xstar_backend_common_abi_version() {
    return 1;
}

const char* xstar_backend_common_backend_name() {
    return "xstar_backend_common_flat_cpp_v066";
}

int xstar_backend_common_feature_flags() {
    return 0;
}

}
