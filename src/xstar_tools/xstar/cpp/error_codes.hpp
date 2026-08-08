// XSTAR-SOURCE-CORRESPONDENCE-BEGIN
// Fortran: No direct Fortran routine.
// Role: C++ backend error/status namespace used around translated scientific kernels.
// Relation: Infrastructure only; must not alter scientific state or Fortran-equivalent control decisions.
// Concordance: BACKEND-001
// Qualification: ABI 6048110 freeze
// XSTAR-SOURCE-CORRESPONDENCE-END

#ifndef XSTAR_BACKEND_ERROR_CODES_HPP
#define XSTAR_BACKEND_ERROR_CODES_HPP

namespace xstar_backend {
constexpr int XSTAR_BACKEND_OK = 0;
constexpr int XSTAR_BACKEND_ERR_INVALID_ARGUMENT = 1;
constexpr int XSTAR_BACKEND_ERR_BUFFER_TOO_SMALL = 2;
constexpr int XSTAR_BACKEND_ERR_UNSUPPORTED = 3;
constexpr int XSTAR_BACKEND_ERR_INTERNAL = 4;
}

#endif
