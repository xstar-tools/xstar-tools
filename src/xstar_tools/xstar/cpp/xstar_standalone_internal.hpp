// XSTAR-SOURCE-CORRESPONDENCE-BEGIN
// Fortran: No direct Fortran routine.
// Role: Standalone executable/backend-discovery utility helpers.
// Relation: Infrastructure only; no scientific operation.
// Concordance: BACKEND-001
// Qualification: ABI/productization boundary
// XSTAR-SOURCE-CORRESPONDENCE-END

#ifndef XSTAR_STANDALONE_INTERNAL_HPP
#define XSTAR_STANDALONE_INTERNAL_HPP

#include "xstar_api.h"
#include <algorithm>
#include <cstddef>
#include <cstring>
#include <filesystem>
#include <string>
#ifdef __linux__
#include <dlfcn.h>
#endif

namespace xstar_standalone {

inline void copy_text(char* destination, std::size_t capacity, const std::string& value) {
    if (destination == nullptr || capacity == 0) return;
    const std::size_t count = std::min(capacity - 1, value.size());
    std::memcpy(destination, value.data(), count);
    destination[count] = '\0';
}

inline std::string field_text(const char* value, std::size_t capacity) {
    if (value == nullptr || capacity == 0) return {};
    return std::string(value, strnlen(value, capacity));
}

inline bool valid_struct(std::uint32_t actual, std::size_t expected) {
    return actual >= expected;
}

inline std::string requested_component_backend(const xstar_config_v1& config, std::uint32_t id) {
    const char* value = nullptr;
    switch (id) {
        case XSTAR_COMPONENT_ENGINE: value = config.engine_backend; break;
        case XSTAR_COMPONENT_RATES: value = config.rates_backend; break;
        case XSTAR_COMPONENT_MATRIX: value = config.matrix_backend; break;
        case XSTAR_COMPONENT_SOLVER: value = config.solver_backend; break;
        case XSTAR_COMPONENT_EMISSIVITY: value = config.emissivity_backend; break;
        case XSTAR_COMPONENT_OPACITY: value = config.opacity_backend; break;
        case XSTAR_COMPONENT_THERMAL: value = config.thermal_backend; break;
        case XSTAR_COMPONENT_IO: value = config.backend; break;
        default: return {};
    }
    std::string result = field_text(value, XSTAR_BACKEND_NAME_SIZE);
    if (result.empty() || result == "inherit") {
        result = field_text(config.backend, XSTAR_BACKEND_NAME_SIZE);
    }
    return result;
}

inline const char* component_name(std::uint32_t id) {
    switch (id) {
        case XSTAR_COMPONENT_ENGINE: return "engine";
        case XSTAR_COMPONENT_RATES: return "rates";
        case XSTAR_COMPONENT_MATRIX: return "matrix";
        case XSTAR_COMPONENT_SOLVER: return "solver";
        case XSTAR_COMPONENT_EMISSIVITY: return "emissivity";
        case XSTAR_COMPONENT_OPACITY: return "opacity";
        case XSTAR_COMPONENT_THERMAL: return "thermal";
        case XSTAR_COMPONENT_IO: return "io";
        default: return "unknown";
    }
}

inline std::filesystem::path executable_or_library_directory(const void* symbol_address) {
#ifdef __linux__
    Dl_info info{};
    if (dladdr(symbol_address, &info) != 0 && info.dli_fname != nullptr) {
        std::error_code error;
        auto path = std::filesystem::weakly_canonical(info.dli_fname, error);
        if (!error) return path.parent_path();
        return std::filesystem::path(info.dli_fname).parent_path();
    }
#endif
    return std::filesystem::current_path();
}

} // namespace xstar_standalone

#endif
