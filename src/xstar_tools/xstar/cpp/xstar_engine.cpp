#include "xstar_backend_common.hpp"
#include <cstdint>
#include <sstream>

extern "C" {

int xstar_engine_abi_version() {
    return 1;
}

const char* xstar_engine_backend_name() {
    return "xstar_engine_mg_ion_accumulator_skeleton_flat_cpp_v061";
}

int xstar_engine_feature_flags() {
    // bit 0: Mg-ion accumulator ABI is present as an opt-in skeleton.
    return 1;
}

int xstar_engine_probe(int element_z, int ion_index, int n_records, char* message, std::size_t message_size) {
    if (!xstar_backend::valid_count(n_records)) {
        xstar_backend::write_message(message, message_size, "invalid negative n_records");
        return xstar_backend::XSTAR_BACKEND_ERR_INVALID_ARGUMENT;
    }
    std::ostringstream out;
    out << "libxstar_engine.so skeleton available; element_z=" << element_z
        << "; ion_index=" << ion_index << "; n_records=" << n_records
        << "; Mg-ion accumulator ABI present but disabled by default";
    xstar_backend::write_message(message, message_size, out.str());
    return xstar_backend::XSTAR_BACKEND_OK;
}

int xstar_engine_eval_mg_ion_accumulator_v1(
    int element_z,
    int ion_index,
    int n_records,
    const std::int64_t* record_rate_type,
    const std::int64_t* record_data_type,
    std::int64_t* counters,
    int counters_size,
    char* message,
    std::size_t message_size
) {
    if (!xstar_backend::valid_count(n_records) || counters == nullptr || counters_size < 7) {
        xstar_backend::write_message(message, message_size, "invalid Mg-ion accumulator arguments");
        return xstar_backend::XSTAR_BACKEND_ERR_INVALID_ARGUMENT;
    }
    if (n_records > 0 && (record_rate_type == nullptr || record_data_type == nullptr)) {
        xstar_backend::write_message(message, message_size, "record arrays are required when n_records > 0");
        return xstar_backend::XSTAR_BACKEND_ERR_INVALID_ARGUMENT;
    }

    // v0.6.1 is an ABI skeleton only.  It deliberately supports no physics by
    // default, but it proves the coarse-call boundary and fallback accounting.
    std::int64_t records_seen = static_cast<std::int64_t>(n_records);
    std::int64_t cpp_supported = 0;
    std::int64_t python_fallback = records_seen;
    counters[0] = records_seen;
    counters[1] = cpp_supported;
    counters[2] = python_fallback;
    counters[3] = 0; // matrix_terms_emitted
    counters[4] = 0; // rate_terms_emitted
    counters[5] = 0; // heat_terms_emitted
    counters[6] = 0; // cool_terms_emitted

    std::ostringstream out;
    out << "Mg-ion accumulator skeleton: element_z=" << element_z
        << "; ion_index=" << ion_index
        << "; records_seen=" << records_seen
        << "; cpp_supported=0; python_fallback=" << python_fallback
        << "; no product-active C++ row generation";
    xstar_backend::write_message(message, message_size, out.str());
    return xstar_backend::XSTAR_BACKEND_OK;
}

}
