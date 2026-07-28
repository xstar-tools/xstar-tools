#ifndef XSTAR_PRODUCTION_ZONE_BRIDGE_H
#define XSTAR_PRODUCTION_ZONE_BRIDGE_H

#include <cstddef>
#include <cstdint>

#ifdef __cplusplus
extern "C" {
#endif

#define XSTAR_PRODUCTION_ZONE_ABI_V064810211 604810211

typedef struct xstar_production_zone_result_v064810211 {
    int32_t zone_index;
    int32_t dsec_evaluations;
    int32_t source_sequence;
    double seconds;
    double temperature_t4;
    double electron_fraction;
    double hmctot;
    double heating_minus_cooling_percent;
} xstar_production_zone_result_v064810211;

int32_t xstar_production_zone_abi_version_v064810211(void);
const char* xstar_production_zone_backend_name_v064810211(void);

/* One-shot exact standalone-production trajectory (cpp-all). */
int32_t xstar_production_zone_run_all_v064810211(
    const char* parameters_path,
    const char* output_dir,
    const char* executable_path,
    char* message,
    std::size_t message_size);

/* Persistent exact standalone-production context (cpp-zone). */
int32_t xstar_production_zone_context_create_v064810211(
    const char* parameters_path,
    const char* output_dir,
    const char* executable_path,
    void** out_context,
    char* message,
    std::size_t message_size);
int32_t xstar_production_zone_context_run_zone_v064810211(
    void* context,
    int32_t zone_index,
    xstar_production_zone_result_v064810211* out_result,
    char* message,
    std::size_t message_size);
int32_t xstar_production_zone_context_finalize_v064810211(
    void* context,
    char* message,
    std::size_t message_size);
void xstar_production_zone_context_destroy_v064810211(void* context);

#ifdef __cplusplus
}
#endif

#endif
