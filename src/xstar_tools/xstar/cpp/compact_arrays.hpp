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

struct MgIonCompactPacketView {
    int element_z;
    int ion_index;
    int ion_stage;
    int n_levels;
    int n_parent_levels;
    CompactI64Array record_number;
    CompactI64Array record_rate_type;
    CompactI64Array record_data_type;
    CompactI64Array record_source_index;
    CompactI64Array payload_i64_offsets;
    CompactI64Array payload_f64_offsets;
    CompactI64Array destination_level_1;
    CompactI64Array destination_level_2;
    CompactF64Array level_energy_ev;
    CompactF64Array level_weight;
};

struct MgIonAccumulatorCounters {
    std::int64_t records_seen;
    std::int64_t cpp_supported;
    std::int64_t python_fallback;
    std::int64_t matrix_terms_emitted;
    std::int64_t rate_terms_emitted;
    std::int64_t heat_terms_emitted;
    std::int64_t cool_terms_emitted;
    std::int64_t rate_type7_records;
    std::int64_t type49_records;
    std::int64_t type53_records;
    std::int64_t type50_records;
    std::int64_t type51_records;
    std::int64_t type49_supported;
    std::int64_t type53_supported;
    std::int64_t type50_topology_supported;
    std::int64_t type51_topology_supported;
    std::int64_t unsupported_rate_type_records;
    std::int64_t unsupported_data_type_records;
    std::int64_t source_order_records;
    std::int64_t product_active;
};

enum MgIonAccumulatorCounterIndex {
    MG_ACC_RECORDS_SEEN = 0,
    MG_ACC_CPP_SUPPORTED = 1,
    MG_ACC_PYTHON_FALLBACK = 2,
    MG_ACC_MATRIX_TERMS_EMITTED = 3,
    MG_ACC_RATE_TERMS_EMITTED = 4,
    MG_ACC_HEAT_TERMS_EMITTED = 5,
    MG_ACC_COOL_TERMS_EMITTED = 6,
    MG_ACC_RATE_TYPE7_RECORDS = 7,
    MG_ACC_TYPE49_RECORDS = 8,
    MG_ACC_TYPE53_RECORDS = 9,
    MG_ACC_TYPE50_RECORDS = 10,
    MG_ACC_TYPE51_RECORDS = 11,
    MG_ACC_TYPE49_SUPPORTED = 12,
    MG_ACC_TYPE53_SUPPORTED = 13,
    MG_ACC_TYPE50_TOPOLOGY_SUPPORTED = 14,
    MG_ACC_TYPE51_TOPOLOGY_SUPPORTED = 15,
    MG_ACC_UNSUPPORTED_RATE_TYPE_RECORDS = 16,
    MG_ACC_UNSUPPORTED_DATA_TYPE_RECORDS = 17,
    MG_ACC_SOURCE_ORDER_RECORDS = 18,
    MG_ACC_PRODUCT_ACTIVE = 19,
    MG_ACC_COUNTER_COUNT = 20
};

} // namespace xstar_backend

#endif
