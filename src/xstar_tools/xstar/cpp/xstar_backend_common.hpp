#ifndef XSTAR_BACKEND_COMMON_HPP
#define XSTAR_BACKEND_COMMON_HPP

#include <cstddef>
#include <cstring>
#include <string>
#include "error_codes.hpp"
#include "compact_arrays.hpp"

namespace xstar_backend {

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

inline MgIonAccumulatorCounters empty_counters() {
    MgIonAccumulatorCounters counters{};
    counters.records_seen = 0;
    counters.cpp_supported = 0;
    counters.python_fallback = 0;
    counters.matrix_terms_emitted = 0;
    counters.rate_terms_emitted = 0;
    counters.heat_terms_emitted = 0;
    counters.cool_terms_emitted = 0;
    return counters;
}

inline bool valid_count(int n) {
    return n >= 0;
}

} // namespace xstar_backend

#endif
