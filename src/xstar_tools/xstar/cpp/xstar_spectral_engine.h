#ifndef XSTAR_SPECTRAL_ENGINE_H
#define XSTAR_SPECTRAL_ENGINE_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define XSTAR_SPECTRAL_ENGINE_ABI_VERSION 60460u

#define XSTAR_SPECTRAL_KIND_EMISAB_BOUND_FREE 1u
#define XSTAR_SPECTRAL_KIND_EMISAB_LINE 2u
#define XSTAR_SPECTRAL_KIND_EMIS_OPACITY_ONLY 3u
#define XSTAR_SPECTRAL_KIND_EMIS_LINE 4u
#define XSTAR_SPECTRAL_KIND_FULL_LINE 5u

#define XSTAR_SPECTRAL_STATUS_SOURCE_ORDERED 1u
#define XSTAR_SPECTRAL_STATUS_NATIVE_EMISSIVITY 2u
#define XSTAR_SPECTRAL_STATUS_NATIVE_OPACITY 4u
#define XSTAR_SPECTRAL_STATUS_PERSISTENT_CONTEXT 8u
#define XSTAR_SPECTRAL_STATUS_EXACT_GRID_ORACLE 16u

/* v0.6.48.3 qualification-only packed temporary-grid oracle. */
#define XSTAR_SPECTRAL_EXACT_GRID_MAGIC 60472.0
#define XSTAR_SPECTRAL_EXACT_GRID_POINTS 20000u
#define XSTAR_SPECTRAL_EXACT_GRID_HEADER_VALUES 6u
#define XSTAR_SPECTRAL_EXACT_GRID_STRIDE \
    (XSTAR_SPECTRAL_EXACT_GRID_HEADER_VALUES + 2u * XSTAR_SPECTRAL_EXACT_GRID_POINTS)

typedef struct xstar_spectral_context xstar_spectral_context;

typedef struct xstar_spectral_contribution_v1 {
    uint64_t source_position;
    int64_t record;
    uint32_t kind;
    int32_t rate_type;
    int32_t data_type;
    int32_t output_index;
    int32_t bin_one_based;
    int32_t reserved0;
    int32_t reserved1;
    double ptmp1;
    double ptmp2;
    double abundance_lower;
    double abundance_upper;
    double hydrogen_density;
    double ans1;
    double ans2;
    double ans3;
    double ans4;
    double opakab;
    double line_energy_eV;
    double bin_width_eV;
    double atomic_mass_amu;
    double natural_width_eV;
    double turbulent_velocity_km_s;
    double temperature_1e4K;
} xstar_spectral_contribution_v1;

typedef struct xstar_spectral_workspace_v1 {
    uint32_t struct_size;
    uint32_t abi_version;
    uint32_t flags;
    uint32_t reserved0;
    double* rcem;
    size_t rcem_count;
    double* oplin;
    size_t oplin_count;
    double* cemab;
    size_t cemab_count;
    double* cabab;
    size_t cabab_count;
    double* opakab;
    size_t opakab_count;
    double* rccemis;
    size_t rccemis_count;
    double* opakc;
    size_t opakc_count;
    double* opakcont;
    size_t opakcont_count;
    double* fline;
    size_t fline_count;
    double* flinel;
    size_t flinel_count;
    const double* epi_eV;
    size_t energy_count;
} xstar_spectral_workspace_v1;

typedef struct xstar_spectral_stats_v1 {
    uint32_t struct_size;
    uint32_t abi_version;
    uint32_t status_flags;
    uint32_t reserved0;
    uint64_t calls;
    uint64_t contributions_attempted;
    uint64_t contributions_committed;
    uint64_t emissivity_contributions;
    uint64_t opacity_contributions;
    uint64_t line_profiles;
    uint64_t source_order_violations;
    double construction_seconds;
    double opacity_seconds;
    double commit_seconds;
} xstar_spectral_stats_v1;

/*
 * v0.6.48.9.2 measurement-only broad spectral construction diagnostics.
 * This is a separate ABI from xstar_spectral_stats_v1 so the accepted
 * science/runtime statistics layout remains unchanged.  The implementation
 * reuses opacity/profile kernel timers that already existed before 9.2; it
 * does not add a clock read per contribution or per line profile.
 */
#define XSTAR_SPECTRAL_PERF_V064892_ABI_VERSION 604892u
#define XSTAR_SPECTRAL_PERF_V064892_FAMILY_COUNT 8u

typedef struct xstar_spectral_perf_v064892 {
    uint32_t struct_size;
    uint32_t abi_version;
    uint32_t flags;
    uint32_t reserved0;
    uint64_t apply_calls;
    uint64_t contributions;
    uint64_t line_profiles;
    uint64_t exact_grid_profiles;
    uint64_t native_profile_profiles;
    uint64_t updated_continuum_bins;
    uint64_t exact_grid_valid_points;
    uint64_t kind_bound_free;
    uint64_t kind_emisab_line;
    uint64_t kind_opacity_only;
    uint64_t kind_emis_line;
    uint64_t kind_full_line;
    uint64_t family_contributions[XSTAR_SPECTRAL_PERF_V064892_FAMILY_COUNT];
    uint64_t family_line_profiles[XSTAR_SPECTRAL_PERF_V064892_FAMILY_COUNT];
    uint64_t family_updated_bins[XSTAR_SPECTRAL_PERF_V064892_FAMILY_COUNT];
    double apply_seconds;
    double profile_kernel_seconds;
    double exact_grid_profile_seconds;
    double native_profile_seconds;
    double family_profile_seconds[XSTAR_SPECTRAL_PERF_V064892_FAMILY_COUNT];
} xstar_spectral_perf_v064892;

uint32_t xstar_spectral_engine_abi_version(void);
const char* xstar_spectral_engine_backend_name(void);
uint32_t xstar_spectral_engine_feature_flags(void);
void xstar_spectral_workspace_init_v1(xstar_spectral_workspace_v1* workspace);
void xstar_spectral_stats_init_v1(xstar_spectral_stats_v1* stats);
void xstar_spectral_perf_init_v064892(xstar_spectral_perf_v064892* perf);
void xstar_spectral_perf_reset_v064892(void);
int xstar_spectral_perf_snapshot_v064892(xstar_spectral_perf_v064892* perf);
void xstar_spectral_type50_vector_perf_reset_v064812324(void);
void xstar_spectral_type50_vector_perf_snapshot_v064812324(
    uint64_t* vectorized_profiles, uint64_t* scalar_profiles);
void xstar_spectral_type50_phase_perf_reset_v064812326(void);
void xstar_spectral_type50_phase_perf_snapshot_v064812326(
    uint64_t* phase_profiles, uint64_t* span_events, uint64_t* span_bins,
    uint64_t* vectorizable_span_events, uint64_t* vectorizable_span_bins,
    uint64_t* max_span, double* profile_value_seconds, double* rebin_seconds,
    double* range_update_seconds, uint64_t* range_avx2_profiles,
    uint64_t* range_avx2_blocks, uint64_t* range_avx2_bins,
    uint64_t* range_scalar_bins);
void xstar_spectral_type50_perf_reset_v064812327(void);
void xstar_spectral_type50_perf_snapshot_v064812327(
    uint64_t* schedule_profiles, uint64_t* cache_hits, uint64_t* cache_misses,
    uint64_t* cache_uncached, uint64_t* distinct_cached_keys, uint64_t* cache_bytes,
    uint64_t* cached_events, double* schedule_build_seconds,
    uint64_t* ncut_histogram, size_t ncut_histogram_len,
    uint64_t* gaussian_points, uint64_t* small_a_core_points,
    uint64_t* small_a_farwing_points, uint64_t* large_a_points,
    uint64_t* inline_avx2_profiles, uint64_t* inline_avx2_blocks,
    uint64_t* inline_avx2_points, uint64_t* inline_scalar_points);
void xstar_spectral_type50_perf_reset_v064812328(void);
void xstar_spectral_type50_perf_snapshot_v064812328(
    uint64_t* prod_avx2_profiles, uint64_t* prod_scalar_profiles,
    uint64_t* prod_avx2_blocks, uint64_t* prod_avx2_points,
    uint64_t* prod_scalar_profile_points, uint64_t* ncut4_profiles,
    uint64_t* ncut4_fast_blocks, uint64_t* ncut4_boundary_fallback_blocks,
    uint64_t* ncut4_fast_points, uint64_t* decomp_profiles,
    uint64_t* decomp_avx2_points, uint64_t* decomp_scalar_points,
    double* decomp_avx2_profile_seconds, double* decomp_scalar_profile_seconds,
    double* decomp_consume_seconds);
int xstar_spectral_context_create_v1(
    xstar_spectral_context** context,
    char* error,
    size_t error_size
);
void xstar_spectral_context_destroy(xstar_spectral_context* context);
int xstar_spectral_context_reset_v1(
    xstar_spectral_context* context,
    char* error,
    size_t error_size
);
int xstar_spectral_apply_contributions_v1(
    xstar_spectral_context* context,
    const xstar_spectral_contribution_v1* contributions,
    size_t contribution_count,
    const double* seed_profiles,
    size_t seed_profile_stride,
    xstar_spectral_workspace_v1* workspace,
    xstar_spectral_stats_v1* stats,
    char* error,
    size_t error_size
);

#ifdef __cplusplus
}
#endif

#endif
