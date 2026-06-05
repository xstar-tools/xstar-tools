#include "xstar_backend_common.hpp"
#include "compact_arrays.hpp"
#include <cstdint>
#include <sstream>

namespace {

bool is_supported_mg_record(long long rate_type, long long data_type) {
    if (rate_type == 7 && (data_type == 49 || data_type == 53)) {
        return true;
    }
    // Type 50/51 are not product-active in v0.6.5, but the coarse ABI can
    // identify their topology and count them as C++-supported classification
    // work.  Matrix/rate row generation remains disabled until a later parity
    // package owns the full row application boundary.
    if (data_type == 50 || data_type == 51) {
        return true;
    }
    return false;
}

void zero_counters(std::int64_t* counters, int counters_size) {
    if (counters == nullptr || counters_size <= 0) return;
    for (int i = 0; i < counters_size; ++i) counters[i] = 0;
}

int eval_mg_ion_accumulator_impl(
    int element_z,
    int ion_index,
    int ion_stage,
    int n_levels,
    int n_parent_levels,
    int n_records,
    const std::int64_t* record_number,
    const std::int64_t* record_rate_type,
    const std::int64_t* record_data_type,
    const std::int64_t* record_source_index,
    std::int64_t* counters,
    int counters_size,
    char* message,
    std::size_t message_size
) {
    using namespace xstar_backend;
    if (!valid_count(n_records) || counters == nullptr || counters_size < MG_ACC_COUNTER_COUNT) {
        write_message(message, message_size, "invalid Mg-ion accumulator arguments");
        return XSTAR_BACKEND_ERR_INVALID_ARGUMENT;
    }
    if (n_records > 0 && (record_rate_type == nullptr || record_data_type == nullptr)) {
        write_message(message, message_size, "record rate/data arrays are required when n_records > 0");
        return XSTAR_BACKEND_ERR_INVALID_ARGUMENT;
    }
    zero_counters(counters, counters_size);

    std::int64_t cpp_supported = 0;
    std::int64_t python_fallback = 0;
    std::int64_t unsupported_rate = 0;
    std::int64_t unsupported_data = 0;
    std::int64_t previous_source_index = -9223372036854775807LL;
    std::int64_t source_order_records = 0;

    for (int i = 0; i < n_records; ++i) {
        const std::int64_t rt = record_rate_type[i];
        const std::int64_t dt = record_data_type[i];
        counters[MG_ACC_RECORDS_SEEN] += 1;
        if (record_source_index != nullptr) {
            const std::int64_t src = record_source_index[i];
            if (i == 0 || src >= previous_source_index) {
                source_order_records += 1;
            }
            previous_source_index = src;
        } else if (record_number != nullptr) {
            const std::int64_t src = record_number[i];
            if (i == 0 || src >= previous_source_index) {
                source_order_records += 1;
            }
            previous_source_index = src;
        }
        if (rt == 7) counters[MG_ACC_RATE_TYPE7_RECORDS] += 1;
        if (dt == 49) counters[MG_ACC_TYPE49_RECORDS] += 1;
        if (dt == 53) counters[MG_ACC_TYPE53_RECORDS] += 1;
        if (dt == 50) counters[MG_ACC_TYPE50_RECORDS] += 1;
        if (dt == 51) counters[MG_ACC_TYPE51_RECORDS] += 1;

        if (element_z == 12 && is_supported_mg_record(rt, dt)) {
            cpp_supported += 1;
            if (rt == 7 && dt == 49) counters[MG_ACC_TYPE49_SUPPORTED] += 1;
            if (rt == 7 && dt == 53) counters[MG_ACC_TYPE53_SUPPORTED] += 1;
            if (dt == 50) counters[MG_ACC_TYPE50_TOPOLOGY_SUPPORTED] += 1;
            if (dt == 51) counters[MG_ACC_TYPE51_TOPOLOGY_SUPPORTED] += 1;
        } else {
            python_fallback += 1;
            if (rt != 7 && dt != 50 && dt != 51) unsupported_rate += 1;
            else unsupported_data += 1;
        }
    }

    counters[MG_ACC_CPP_SUPPORTED] = cpp_supported;
    counters[MG_ACC_PYTHON_FALLBACK] = python_fallback;
    counters[MG_ACC_UNSUPPORTED_RATE_TYPE_RECORDS] = unsupported_rate;
    counters[MG_ACC_UNSUPPORTED_DATA_TYPE_RECORDS] = unsupported_data;
    counters[MG_ACC_SOURCE_ORDER_RECORDS] = source_order_records;
    counters[MG_ACC_PRODUCT_ACTIVE] = 0;
    // Product-active row generation remains off in v0.6.5.
    counters[MG_ACC_MATRIX_TERMS_EMITTED] = 0;
    counters[MG_ACC_RATE_TERMS_EMITTED] = 0;
    counters[MG_ACC_HEAT_TERMS_EMITTED] = 0;
    counters[MG_ACC_COOL_TERMS_EMITTED] = 0;

    std::ostringstream out;
    out << "Mg-ion accumulator v0.6.5 coarse ABI: element_z=" << element_z
        << "; ion_index=" << ion_index
        << "; ion_stage=" << ion_stage
        << "; n_levels=" << n_levels
        << "; n_parent_levels=" << n_parent_levels
        << "; records_seen=" << counters[MG_ACC_RECORDS_SEEN]
        << "; cpp_supported=" << cpp_supported
        << "; python_fallback=" << python_fallback
        << "; product_active=0";
    write_message(message, message_size, out.str());
    return XSTAR_BACKEND_OK;
}

} // namespace

extern "C" {

int xstar_engine_abi_version() {
    return 2;
}

const char* xstar_engine_backend_name() {
    return "xstar_engine_mg_ion_accumulator_coarse_abi_flat_cpp_v065";
}

int xstar_engine_feature_flags() {
    // bit 0: Mg-ion accumulator ABI present.
    // bit 1: coarse record traversal/classification implemented.
    // bit 2: compact packet counters implemented.
    return 1 | 2 | 4;
}

int xstar_engine_probe(int element_z, int ion_index, int n_records, char* message, std::size_t message_size) {
    if (!xstar_backend::valid_count(n_records)) {
        xstar_backend::write_message(message, message_size, "invalid negative n_records");
        return xstar_backend::XSTAR_BACKEND_ERR_INVALID_ARGUMENT;
    }
    std::ostringstream out;
    out << "libxstar_engine.so v0.6.5 coarse Mg-ion accumulator ABI available; element_z=" << element_z
        << "; ion_index=" << ion_index << "; n_records=" << n_records
        << "; product-active matrix/rate emission disabled";
    xstar_backend::write_message(message, message_size, out.str());
    return xstar_backend::XSTAR_BACKEND_OK;
}

int xstar_matrix_eval_mg_ion_accumulator_v1(
    int element_z,
    int ion_index,
    int ion_stage,
    int n_levels,
    int n_parent_levels,
    int n_records,
    const std::int64_t* record_number,
    const std::int64_t* record_rate_type,
    const std::int64_t* record_data_type,
    const std::int64_t* record_source_index,
    std::int64_t* counters,
    int counters_size,
    char* message,
    std::size_t message_size
) {
    return eval_mg_ion_accumulator_impl(
        element_z, ion_index, ion_stage, n_levels, n_parent_levels, n_records,
        record_number, record_rate_type, record_data_type, record_source_index,
        counters, counters_size, message, message_size);
}

// Backward-compatible v0.6.1 symbol.  It maps the shorter skeleton call onto
// the v0.6.5 coarse ABI without product-active row generation.
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
    return eval_mg_ion_accumulator_impl(
        element_z, ion_index, 0, 0, 0, n_records,
        nullptr, record_rate_type, record_data_type, nullptr,
        counters, counters_size, message, message_size);
}

}
