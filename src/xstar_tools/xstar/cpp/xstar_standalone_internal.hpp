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
#include "xstar_dynamic_library.hpp"
#include <algorithm>
#include <cstddef>
#include <cstring>
#include <filesystem>
#include <string>

namespace xstar_standalone {

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Implement copy text as a small shared native helper used by the standalone/backend orchestration layer.
// Reference context: Implementation helper; no independent scientific formula.
// XSTAR-FUNCTION-COMMENT-END
inline void copy_text(char* destination, std::size_t capacity, const std::string& value) {
    if (destination == nullptr || capacity == 0) return;
    const std::size_t count = std::min(capacity - 1, value.size());
    std::memcpy(destination, value.data(), count);
    destination[count] = '\0';
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Implement field text as a small shared native helper used by the standalone/backend orchestration layer.
// Reference context: Implementation helper; no independent scientific formula.
// XSTAR-FUNCTION-COMMENT-END
inline std::string field_text(const char* value, std::size_t capacity) {
    if (value == nullptr || capacity == 0) return {};
    return std::string(value, strnlen(value, capacity));
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Implement valid struct as a small shared native helper used by the standalone/backend orchestration layer.
// Reference context: Implementation helper; no independent scientific formula.
// XSTAR-FUNCTION-COMMENT-END
inline bool valid_struct(std::uint32_t actual, std::size_t expected) {
    return actual >= expected;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Implement requested component backend as a small shared native helper used by the standalone/backend orchestration layer.
// Reference context: Implementation helper; no independent scientific formula.
// XSTAR-FUNCTION-COMMENT-END
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

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Implement component name as a small shared native helper used by the standalone/backend orchestration layer.
// Reference context: Implementation helper; no independent scientific formula.
// XSTAR-FUNCTION-COMMENT-END
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

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Implement executable or library directory as a small shared native helper used by the standalone/backend orchestration layer.
// Reference context: Implementation helper; no independent scientific formula.
// XSTAR-FUNCTION-COMMENT-END
inline std::filesystem::path executable_or_library_directory(const void* symbol_address) {
    return xstar_platform::module_directory(symbol_address);
}

} // namespace xstar_standalone

#endif
