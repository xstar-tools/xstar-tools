// XSTAR-SOURCE-CORRESPONDENCE-BEGIN
// Fortran: xstarcalc.f90
// Role: Stable bridge for one production-zone evaluation using the shared native scientific operator.
// Relation: C ABI wrapper around the xstarcalc-equivalent zone boundary; no independent physics.
// Concordance: ARCH-001; BACKEND-001
// Qualification: production-zone ABI 6048110; 12.3.44
// XSTAR-SOURCE-CORRESPONDENCE-END

#ifndef XSTAR_PRODUCTION_ZONE_BRIDGE_H
#define XSTAR_PRODUCTION_ZONE_BRIDGE_H

#include <cstddef>
#include <cstdint>

#ifdef __cplusplus
extern "C" {
#endif

#define XSTAR_PRODUCTION_ZONE_ABI_V0648110 6048110

typedef struct xstar_production_zone_result_v0648110 {
    int32_t zone_index;
    int32_t dsec_evaluations;
    int32_t source_sequence;
    int32_t done_after_zone;
    double seconds;
    double temperature_t4;
    double electron_fraction;
    double hmctot;
    double heating_minus_cooling_percent;
} xstar_production_zone_result_v0648110;

int32_t xstar_production_zone_abi_version_v0648110(void);
const char* xstar_production_zone_backend_name_v0648110(void);

/* One-shot exact standalone-production trajectory (cpp-all). */
int32_t xstar_production_zone_run_all_v0648110(
    const char* parameters_path,
    const char* output_dir,
    const char* executable_path,
    char* message,
    std::size_t message_size);

/* Persistent exact standalone-production context (cpp-zone). */
int32_t xstar_production_zone_context_create_v0648110(
    const char* parameters_path,
    const char* output_dir,
    const char* executable_path,
    void** out_context,
    char* message,
    std::size_t message_size);

/* Release exactly the next physical radial zone. */
int32_t xstar_production_zone_context_run_next_zone_v0648110(
    void* context,
    xstar_production_zone_result_v0648110* out_result,
    char* message,
    std::size_t message_size);

/* Query whether the physical radial loop has completed. */
int32_t xstar_production_zone_context_done_v0648110(
    void* context,
    int32_t* out_done,
    int32_t* out_completed_zones,
    char* message,
    std::size_t message_size);

int32_t xstar_production_zone_context_finalize_v0648110(
    void* context,
    char* message,
    std::size_t message_size);
void xstar_production_zone_context_destroy_v0648110(void* context);

#ifdef __cplusplus
}
#endif

#endif
