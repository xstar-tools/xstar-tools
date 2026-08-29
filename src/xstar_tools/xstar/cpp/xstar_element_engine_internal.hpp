// Private C++ element-engine bridge.  Not part of the public C ABI.
#ifndef XSTAR_ELEMENT_ENGINE_INTERNAL_HPP
#define XSTAR_ELEMENT_ENGINE_INTERNAL_HPP

#include "xstar_element_engine.h"
#include <cstddef>
#include <cstdint>

extern "C" int xstar_element_engine_run_construction_with_trusted_thermal_ledger_v068240241(
    xstar_element_engine_context* context,
    const xstar_element_input_v1* input,
    const xstar_element_contribution_v1* contributions,
    std::size_t contribution_count,
    const xstar_canonical_thermal_term_v1* thermal_terms,
    std::size_t thermal_term_count,
    std::uint64_t authoritative_thermal_ledger_fingerprint,
    std::uint64_t* consumed_thermal_ledger_fingerprint,
    xstar_element_output_v1* output,
    char* message,
    std::size_t message_size);

#endif
