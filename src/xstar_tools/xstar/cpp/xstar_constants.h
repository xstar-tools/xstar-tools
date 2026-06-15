#pragma once

namespace xstar_constants {
#define XSTAR_CONSTANT(name, value) inline constexpr double name = value;
#include "../constants.def"
#undef XSTAR_CONSTANT
}  // namespace xstar_constants
