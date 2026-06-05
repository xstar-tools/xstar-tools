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
};

} // namespace xstar_backend

#endif
