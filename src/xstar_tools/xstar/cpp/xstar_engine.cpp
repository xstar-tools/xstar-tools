#include "xstar_backend_common.hpp"
#include "compact_arrays.hpp"
#include <cstdint>
#include <sstream>
#include <algorithm>
#include <cmath>
#include <chrono>

namespace {

bool is_supported_mg_record(long long rate_type, long long data_type) {
    if (rate_type == 7 && (data_type == 49 || data_type == 53)) {
        return true;
    }
    // Type 50/51 are not product-active in v0.6.8, but the coarse ABI can
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
    // Product-active row generation remains off in v0.6.8.
    counters[MG_ACC_MATRIX_TERMS_EMITTED] = 0;
    counters[MG_ACC_RATE_TERMS_EMITTED] = 0;
    counters[MG_ACC_HEAT_TERMS_EMITTED] = 0;
    counters[MG_ACC_COOL_TERMS_EMITTED] = 0;

    std::ostringstream out;
    out << "Mg-ion accumulator v0.6.8 coarse ABI: element_z=" << element_z
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
    return 3;
}

const char* xstar_engine_backend_name() {
    return "xstar_engine_mg_rate_payload_batched_orchestration_shadow_v029";
}

int xstar_engine_feature_flags() {
    // bit 0: Mg-ion accumulator ABI present.
    // bit 1: coarse record traversal/classification implemented.
    // bit 2: compact packet counters implemented.
    // bit 3: evaluation-level Mg rate-payload orchestration shadow.
    return 1 | 2 | 4 | 8;
}

int xstar_engine_probe(int element_z, int ion_index, int n_records, char* message, std::size_t message_size) {
    if (!xstar_backend::valid_count(n_records)) {
        xstar_backend::write_message(message, message_size, "invalid negative n_records");
        return xstar_backend::XSTAR_BACKEND_ERR_INVALID_ARGUMENT;
    }
    std::ostringstream out;
    out << "libxstar_engine.so v0.6.29 Mg-ion accumulator and rate-payload orchestration shadow ABI available; element_z=" << element_z
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
// the v0.6.8 coarse ABI without product-active row generation.
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

extern "C" int xstar_engine_eval_mg_rate_payload_shadow_v1(
    int n_records,
    const std::int64_t* meta_i64,
    int meta_stride,
    const double* rates_f64,
    int rates_stride,
    int max_terms,
    std::int64_t* out_i64,
    int out_i64_stride,
    double* out_f64,
    int out_f64_stride,
    double* timing_f64,
    int timing_size,
    std::int64_t* stats,
    int stats_size,
    char* message,
    std::size_t message_size
) {
    using namespace xstar_backend;
    if (!valid_count(n_records) || meta_stride < 12 || rates_stride < 7 ||
        out_i64_stride < 16 || out_f64_stride < 4 || max_terms < 0 ||
        timing_f64 == nullptr || timing_size < 3 || stats == nullptr || stats_size < 16) {
        write_message(message, message_size, "invalid rate-payload shadow arguments");
        return XSTAR_BACKEND_ERR_INVALID_ARGUMENT;
    }
    if (n_records > 0 && (meta_i64 == nullptr || rates_f64 == nullptr || out_i64 == nullptr || out_f64 == nullptr)) {
        write_message(message, message_size, "null rate-payload shadow array");
        return XSTAR_BACKEND_ERR_INVALID_ARGUMENT;
    }
    for (int i = 0; i < stats_size; ++i) stats[i] = 0;
    for (int i = 0; i < timing_size; ++i) timing_f64[i] = 0.0;
    using clock_t = std::chrono::steady_clock;
    const auto total_t0 = clock_t::now();
    int emitted = 0;
    for (int k = 0; k < n_records; ++k) {
        const auto eval_t0 = clock_t::now();
        const std::int64_t* m = meta_i64 + static_cast<std::int64_t>(k) * meta_stride;
        const double* r = rates_f64 + static_cast<std::int64_t>(k) * rates_stride;
        const long long record = m[0], rate_type = m[1], data_type = m[2];
        const long long ion_index = m[3], ion_stage = m[4], compact_start = m[5];
        const long long basis_n_rows = m[6], idest1 = m[7], idest2 = m[8];
        const long long lower_endpoint = m[9], upper_endpoint = m[10], term_start = m[11];
        stats[0] += 1;
        bool family = (rate_type == 4 && data_type == 50) ||
                      (rate_type == 3 && data_type == 51) ||
                      (rate_type == 3 && data_type == 63) ||
                      (rate_type == 42 && data_type == 88);
        if (!family) { stats[4] += 1; timing_f64[0] += std::chrono::duration<double>(clock_t::now() - eval_t0).count(); continue; }
        if (rate_type == 4 && data_type == 50) stats[8] += 1;
        if (rate_type == 3 && data_type == 51) stats[9] += 1;
        if (rate_type == 3 && data_type == 63) stats[10] += 1;
        if (rate_type == 42 && data_type == 88) stats[11] += 1;
        bool finite = true;
        for (int j = 0; j < 7; ++j) finite = finite && std::isfinite(r[j]);
        if (!finite || record <= 0 || basis_n_rows <= 0 || compact_start <= 0 ||
            idest1 <= 0 || idest2 <= 0 || lower_endpoint <= 0 || upper_endpoint <= 0) {
            stats[5] += 1;
            timing_f64[0] += std::chrono::duration<double>(clock_t::now() - eval_t0).count();
            continue;
        }
        timing_f64[0] += std::chrono::duration<double>(clock_t::now() - eval_t0).count();
        if (emitted + 4 > max_terms) { stats[6] += 1; break; }
        const auto terms_t0 = clock_t::now();
        const double ans1 = r[0], ans2 = r[1], ans3 = r[2], ans4 = r[3], ans5 = r[4], ans6 = r[5];
        const double xpx = r[6];
        long long raw_lower = compact_start + lower_endpoint - 1;
        long long raw_upper = compact_start + upper_endpoint - 1;
        long long row_lower = std::min(basis_n_rows, raw_lower);
        long long row_upper = std::min(basis_n_rows, raw_upper);
        const long long rows[4] = {row_upper, row_lower, row_lower, row_upper};
        const long long cols[4] = {row_lower, row_upper, row_lower, row_upper};
        const long long raw_rows[4] = {raw_upper, raw_lower, raw_lower, raw_upper};
        const long long raw_cols[4] = {raw_lower, raw_upper, raw_lower, raw_upper};
        const long long roles[4] = {1, 2, 3, 4};
        const double vals[4][4] = {
            {ans1, ans2, 0.0, 0.0},
            {ans2, ans1, 0.0, 0.0},
            {-ans1, -ans1, ans4 * xpx, ans6 * xpx},
            {-ans2, -ans2, -ans3 * xpx, -ans5 * xpx},
        };
        for (int q = 0; q < 4; ++q) {
            std::int64_t* oi = out_i64 + static_cast<std::int64_t>(emitted) * out_i64_stride;
            double* of = out_f64 + static_cast<std::int64_t>(emitted) * out_f64_stride;
            oi[0] = term_start + q; oi[1] = record; oi[2] = data_type; oi[3] = rate_type;
            oi[4] = ion_index; oi[5] = ion_stage; oi[6] = roles[q]; oi[7] = rows[q]; oi[8] = cols[q];
            oi[9] = idest1; oi[10] = idest2; oi[11] = lower_endpoint; oi[12] = upper_endpoint;
            oi[13] = raw_rows[q]; oi[14] = raw_cols[q]; oi[15] = (raw_rows[q] != rows[q] || raw_cols[q] != cols[q]) ? 1 : 0;
            of[0] = vals[q][0]; of[1] = vals[q][1]; of[2] = vals[q][2]; of[3] = vals[q][3];
            ++emitted;
        }
        stats[1] += 1;
        timing_f64[1] += std::chrono::duration<double>(clock_t::now() - terms_t0).count();
    }
    timing_f64[2] = std::chrono::duration<double>(clock_t::now() - total_t0).count();
    stats[2] = emitted;
    stats[3] = emitted / 4;
    stats[7] = (stats[5] == 0 && stats[6] == 0) ? 1 : 0;
    std::ostringstream out;
    out << "rate-payload batched orchestration shadow: records=" << n_records
        << "; supported=" << stats[1] << "; terms=" << emitted
        << "; invalid=" << stats[5] << "; overflow=" << stats[6];
    write_message(message, message_size, out.str());
    return XSTAR_BACKEND_OK;
}
