#ifndef XSTAR_CANONICAL_THERMAL_TERM_HPP
#define XSTAR_CANONICAL_THERMAL_TERM_HPP

#include "source_order_thermal_reducer.hpp"
#include "xstar_element_engine.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <stdexcept>
#include <type_traits>
#include <utility>
#include <vector>

namespace xstar_canonical_thermal {

inline void fnv1a_byte(std::uint64_t& hash, std::uint8_t value) {
    constexpr std::uint64_t prime = 1099511628211ULL;
    hash ^= static_cast<std::uint64_t>(value);
    hash *= prime;
}

template <typename T>
inline void fnv1a_little_endian(std::uint64_t& hash, T value) {
    static_assert(std::is_integral<T>::value, "integral fingerprint field required");
    using U = typename std::make_unsigned<T>::type;
    const U bits = static_cast<U>(value);
    for (unsigned shift = 0; shift < sizeof(U) * 8u; shift += 8u) {
        fnv1a_byte(hash, static_cast<std::uint8_t>((bits >> shift) & static_cast<U>(0xffu)));
    }
}

inline void fnv1a_binary64(std::uint64_t& hash, double value) {
    std::uint64_t bits = 0;
    static_assert(sizeof(bits) == sizeof(value), "binary64 size mismatch");
    std::memcpy(&bits, &value, sizeof(bits));
    fnv1a_little_endian(hash, bits);
}

inline std::uint64_t fingerprint(
    const xstar_canonical_thermal_term_v1* terms,
    std::size_t count
) {
    if (count > 0 && terms == nullptr) {
        throw std::runtime_error("canonical Thermal ledger pointer is null");
    }
    std::uint64_t hash = 1469598103934665603ULL;
    fnv1a_little_endian(hash, static_cast<std::uint64_t>(count));
    for (std::size_t i = 0; i < count; ++i) {
        const auto& term = terms[i];
        fnv1a_little_endian(hash, term.source_position);
        fnv1a_little_endian(hash, term.term_index);
        fnv1a_little_endian(hash, term.record);
        fnv1a_little_endian(hash, term.primary_source_order_index);
        fnv1a_little_endian(hash, term.data_type);
        fnv1a_little_endian(hash, term.rate_type);
        fnv1a_little_endian(hash, term.ion_index);
        fnv1a_little_endian(hash, term.ion_stage);
        fnv1a_little_endian(hash, term.compact_row);
        fnv1a_little_endian(hash, term.native_compact_row);
        fnv1a_little_endian(hash, term.source_compact_row);
        fnv1a_little_endian(hash, term.role);
        fnv1a_little_endian(hash, term.flags);
        fnv1a_binary64(hash, term.cj);
        fnv1a_binary64(hash, term.cj2);
        fnv1a_binary64(hash, term.native_cj);
        fnv1a_binary64(hash, term.source_cj);
    }
    return hash;
}

inline std::uint64_t fingerprint(const std::vector<xstar_canonical_thermal_term_v1>& terms) {
    return fingerprint(terms.data(), terms.size());
}

inline void validate(
    const xstar_canonical_thermal_term_v1* terms,
    std::size_t count,
    int n_rows
) {
    if (count > 0 && terms == nullptr) {
        throw std::runtime_error("canonical Thermal ledger pointer is null");
    }
    std::int64_t previous_term_index = -1;
    for (std::size_t i = 0; i < count; ++i) {
        const auto& term = terms[i];
        if (term.term_index <= previous_term_index) {
            throw std::runtime_error("canonical Thermal ledger term_index is not strictly increasing");
        }
        previous_term_index = term.term_index;
        if (term.compact_row < 1 || term.compact_row > n_rows) {
            throw std::runtime_error("canonical Thermal ledger compact_row outside active basis");
        }
        if (term.role != XSTAR_CANONICAL_THERMAL_FORWARD_DIAG_LOSS &&
            term.role != XSTAR_CANONICAL_THERMAL_REVERSE_DIAG_LOSS) {
            throw std::runtime_error("canonical Thermal ledger role is invalid");
        }
        if (!std::isfinite(term.cj) || !std::isfinite(term.cj2) ||
            !std::isfinite(term.native_cj) || !std::isfinite(term.source_cj)) {
            throw std::runtime_error("canonical Thermal ledger contains non-finite coefficient");
        }
    }
}

struct ReductionResult {
    xstar_source_order_thermal::TaggedFourChannelAccumulator tagged;
    std::uint64_t fingerprint = 0;
    std::size_t term_count = 0;
};

inline ReductionResult reduce(
    const xstar_canonical_thermal_term_v1* terms,
    std::size_t count,
    const double* populations,
    std::size_t population_count,
    int element_z
) {
    validate(terms, count, static_cast<int>(population_count));
    if (population_count > 0 && populations == nullptr) {
        throw std::runtime_error("canonical Thermal population pointer is null");
    }
    ReductionResult result;
    result.fingerprint = fingerprint(terms, count);
    result.term_count = count;

    struct PendingPrimary {
        std::int64_t order = 0;
        std::size_t ledger_index = 0;
    };
    std::vector<PendingPrimary> pending_primary;
    pending_primary.reserve(count);

    for (std::size_t index = 0; index < count; ++index) {
        const auto& term = terms[index];
        const double population = populations[static_cast<std::size_t>(term.compact_row - 1)];
        if (!std::isfinite(population)) {
            throw std::runtime_error("canonical Thermal ledger population is non-finite");
        }
        const bool is_type53 = (term.flags & XSTAR_CANONICAL_THERMAL_TYPE53) != 0u;
        const bool defer_primary = element_z == 12 && term.cj > 0.0 &&
            term.primary_source_order_index > 0;
        if (defer_primary) {
            pending_primary.push_back({term.primary_source_order_index, index});
        } else {
            result.tagged.accumulate_primary(population, term.cj, is_type53);
        }
        result.tagged.accumulate_secondary(population, term.cj2, is_type53);
    }

    std::sort(pending_primary.begin(), pending_primary.end(), [](const auto& left, const auto& right) {
        if (left.order != right.order) return left.order < right.order;
        return left.ledger_index < right.ledger_index;
    });
    std::int64_t previous_order = 0;
    for (const auto& pending : pending_primary) {
        if (pending.order <= previous_order) {
            throw std::runtime_error("canonical Thermal primary source order is not strictly increasing");
        }
        previous_order = pending.order;
        const auto& term = terms[pending.ledger_index];
        const double population = populations[static_cast<std::size_t>(term.compact_row - 1)];
        const bool is_type53 = (term.flags & XSTAR_CANONICAL_THERMAL_TYPE53) != 0u;
        result.tagged.accumulate_primary(population, term.cj, is_type53);
    }
    return result;
}

inline ReductionResult reduce(
    const std::vector<xstar_canonical_thermal_term_v1>& terms,
    const std::vector<double>& populations,
    int element_z
) {
    return reduce(terms.data(), terms.size(), populations.data(), populations.size(), element_z);
}

} // namespace xstar_canonical_thermal

#endif
