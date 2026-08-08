// XSTAR-SOURCE-CORRESPONDENCE-BEGIN
// Fortran: calc_hmc_all.f90; calc_hmc_element.f90; calc_hmc_ion.f90
// Role: Source-order four-channel thermal accumulation and tagged reductions.
// Relation: Optimized storage/reduction helper constrained to reproduce the source accumulation
//   ownership/order where roundoff is observable.
// Concordance: THERM-001
// Qualification: thermal/source-order qualification 12.3.44
// XSTAR-SOURCE-CORRESPONDENCE-END

#ifndef XSTAR_SOURCE_ORDER_THERMAL_REDUCER_HPP
#define XSTAR_SOURCE_ORDER_THERMAL_REDUCER_HPP

#include <array>
#include <cmath>
#include <cstdint>
#include <stdexcept>

namespace xstar_source_order_thermal {

// The source msolvelucy/calc_hmc_all contract accumulates unweighted
// population-rate products in term order and applies elemental abundance once
// after each completed channel. Keep this small utility header-only so the
// element solver and fixed-state trajectory use the exact same arithmetic.
struct FourChannelAccumulator {
    double heating = 0.0;
    double cooling = 0.0;
    double heating2 = 0.0;
    double cooling2 = 0.0;

    void accumulate_primary(double population, double coefficient) {
        if (!std::isfinite(population) || !std::isfinite(coefficient)) {
            throw std::runtime_error("non-finite primary Thermal term");
        }
        const double product = population * coefficient;
        if (coefficient > 0.0) cooling += product;
        else heating -= product;
    }

    void accumulate_secondary(double population, double coefficient) {
        if (!std::isfinite(population) || !std::isfinite(coefficient)) {
            throw std::runtime_error("non-finite secondary Thermal term");
        }
        const double product = population * coefficient;
        if (coefficient > 0.0) cooling2 += product;
        else heating2 -= product;
    }

    void accumulate(double population, double coefficient, double coefficient2) {
        accumulate_primary(population, coefficient);
        accumulate_secondary(population, coefficient2);
    }

    std::array<double, 4> values() const {
        return {{heating, cooling, heating2, cooling2}};
    }

    std::array<double, 4> abundance_weighted(double abundance) const {
        if (!std::isfinite(abundance)) {
            throw std::runtime_error("non-finite elemental abundance");
        }
        return {{
            heating * abundance,
            cooling * abundance,
            heating2 * abundance,
            cooling2 * abundance,
        }};
    }
};

// Family attribution must share the same arithmetic tree as the element total.
// Each term is committed to the total and to exactly one tagged subtype during
// the same source-order pass. In particular, non-Type-53 is not reconstructed
// by subtracting independently rounded abundance-weighted totals.
struct TaggedFourChannelAccumulator {
    FourChannelAccumulator total;
    FourChannelAccumulator type53;
    FourChannelAccumulator non_type53;

    FourChannelAccumulator& family(bool is_type53) {
        return is_type53 ? type53 : non_type53;
    }

    void accumulate_primary(double population, double coefficient, bool is_type53) {
        total.accumulate_primary(population, coefficient);
        family(is_type53).accumulate_primary(population, coefficient);
    }

    void accumulate_secondary(double population, double coefficient, bool is_type53) {
        total.accumulate_secondary(population, coefficient);
        family(is_type53).accumulate_secondary(population, coefficient);
    }

    void accumulate(double population, double coefficient, double coefficient2, bool is_type53) {
        accumulate_primary(population, coefficient, is_type53);
        accumulate_secondary(population, coefficient2, is_type53);
    }
};

inline bool binary64_equal(double left, double right) {
    if (std::isnan(left) || std::isnan(right)) return false;
    if (left == right) return true;
    return false;
}

} // namespace xstar_source_order_thermal

#endif
