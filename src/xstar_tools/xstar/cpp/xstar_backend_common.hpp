// XSTAR-SOURCE-CORRESPONDENCE-BEGIN
// Fortran: No direct Fortran routine; supports calc_hmc/calc_emis-equivalent backend kernels.
// Role: Shared compact-packet/error helpers for native backend modules.
// Relation: C++ infrastructure/storage only.
// Concordance: BACKEND-001
// Qualification: ABI 6048110 freeze
// XSTAR-SOURCE-CORRESPONDENCE-END

#ifndef XSTAR_BACKEND_COMMON_HPP
#define XSTAR_BACKEND_COMMON_HPP

#include <cstddef>
#include <cstring>
#include <string>
#include "error_codes.hpp"
#include "compact_arrays.hpp"

namespace xstar_backend {

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Implement write message as a small shared native helper used by the standalone/backend orchestration layer.
// Reference context: Implementation helper; no independent scientific formula.
// XSTAR-FUNCTION-COMMENT-END
inline void write_message(char* message, std::size_t message_size, const std::string& text) {
    if (message == nullptr || message_size == 0) {
        return;
    }
    std::size_t n = text.size();
    if (n + 1 > message_size) {
        n = message_size - 1;
    }
    std::memcpy(message, text.data(), n);
    message[n] = '\0';
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Implement empty counters as a small shared native helper used by the standalone/backend orchestration layer.
// Reference context: Implementation helper; no independent scientific formula.
// XSTAR-FUNCTION-COMMENT-END

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Implement valid count as a small shared native helper used by the standalone/backend orchestration layer.
// Reference context: Implementation helper; no independent scientific formula.
// XSTAR-FUNCTION-COMMENT-END
inline bool valid_count(int n) {
    return n >= 0;
}

} // namespace xstar_backend

#endif
