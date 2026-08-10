// XSTAR-SOURCE-CORRESPONDENCE-BEGIN
// Fortran: levwkelement.f90; levwk.f90; calc_hmc_ion.f90
// Role: Compact C++ storage/views for the source one-based level/rate topology consumed during element and
//   ion solves.
// Relation: Storage transformation only; indices/endpoints must reproduce the Fortran compact basis and
//   clamping semantics.
// Concordance: LEVEL-001; MATRIX-001
// Qualification: matrix repair 12.3.25; C++ baseline 12.3.44
// XSTAR-SOURCE-CORRESPONDENCE-END

#ifndef XSTAR_BACKEND_COMPACT_ARRAYS_HPP
#define XSTAR_BACKEND_COMPACT_ARRAYS_HPP

#include <cstddef>
#include <cstdint>

namespace xstar_backend {

struct CompactI64Array {
    const std::int64_t* data;
    std::size_t size;
};

struct CompactF64Array {
    const double* data;
    std::size_t size;
};

struct MutableI64Array {
    std::int64_t* data;
    std::size_t size;
};

struct MutableF64Array {
    double* data;
    std::size_t size;
};




} // namespace xstar_backend

#endif
