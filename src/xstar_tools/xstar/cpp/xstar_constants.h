// XSTAR-SOURCE-CORRESPONDENCE-BEGIN
// Fortran: constants.f90; selected literal semantics in rread1.f90/trnfrc.f90 and scientific routines
// Role: C++ constants required by source-equivalent kernels, including legacy/source-rounded values when
//   observable.
// Relation: Source-exact or qualification-pinned constants; do not normalize legacy values without science
//   requalification.
// Concordance: INPUT-001; THERM-001; RADIAL-001
// Qualification: default-REAL/radius repair 12.3.36; C++ 12.3.44
// XSTAR-SOURCE-CORRESPONDENCE-END

#pragma once

namespace xstar_constants {
#define XSTAR_CONSTANT(name, value) inline constexpr double name = value;
#include "../constants.def"
#undef XSTAR_CONSTANT
}  // namespace xstar_constants
