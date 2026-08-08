// XSTAR-SOURCE-CORRESPONDENCE-BEGIN
// Fortran: ener.f90
// Role: Construct the source logarithmic energy grid while reproducing default-REAL literal/operation
//   semantics used by ener.
// Relation: Source-exact numeric helper for the accepted energy-grid construction.
// Concordance: ARCH-001; INPUT-001
// Qualification: default-REAL policy frozen with 12.3.36 and C++ 12.3.44
// XSTAR-SOURCE-CORRESPONDENCE-END

#ifndef XSTAR_SOURCE_REAL_ENERGY_GRID_HPP
#define XSTAR_SOURCE_REAL_ENERGY_GRID_HPP

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <stdexcept>
#include <vector>

namespace xstar_source_real_energy_grid {

inline double default_real(double value) {
    return static_cast<double>(static_cast<float>(value));
}

inline double default_real_reciprocal(std::size_t denominator) {
    if (denominator == 0u) throw std::runtime_error("ener default-real reciprocal denominator is zero");
    const float one = 1.0f;
    const float denom = static_cast<float>(denominator);
    return static_cast<double>(one / denom);
}

inline std::vector<double> build(std::size_t n) {
    // Literal arithmetic-kind translation of ener.f90.  The destination
    // variables are REAL(8), but the literals 0.1, 4.e+5, 1., 1.e+6 and
    // FLOAT(...) are default REAL.  In particular, evaluate 1./FLOAT(...)
    // in binary32 before promotion to the REAL(8) exponent.
    if (n < 4u) throw std::runtime_error("ener requires at least four bins");
    const std::size_t n2 = std::max<std::size_t>(2u, n / 50u);
    const std::size_t n3 = n - n2;
    if (n3 < 2u) throw std::runtime_error("ener first segment is too small");

    std::vector<double> out(n, 0.0);
    double ebnd1 = default_real(0.1);
    double ebnd2 = default_real(4.0e5);
    const double ebnd2o = ebnd2;
    const double exponent1 = default_real_reciprocal(n3 - 1u);
    const double dele1 = std::pow(ebnd2 / ebnd1, exponent1);
    out[0] = ebnd1;
    for (std::size_t i = 1; i < n3; ++i) out[i] = out[i - 1u] * dele1;

    ebnd2 = default_real(1.0e6);
    ebnd1 = ebnd2o;
    const double exponent2 = default_real_reciprocal(n2 - 1u);
    const double dele2 = std::pow(ebnd2 / ebnd1, exponent2);
    for (std::size_t i = n3; i < n; ++i) out[i] = out[i - 1u] * dele2;
    return out;
}

}  // namespace xstar_source_real_energy_grid

#endif
