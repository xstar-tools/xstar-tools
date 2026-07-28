#ifndef XSTAR_FIXED_STATE_ENGINE_H
#define XSTAR_FIXED_STATE_ENGINE_H

#include <stddef.h>
#include <stdint.h>

#ifdef _WIN32
#  define XSTAR_FIXED_STATE_EXPORT __declspec(dllexport)
#else
#  define XSTAR_FIXED_STATE_EXPORT __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#endif

#define XSTAR_FIXED_STATE_ENGINE_ABI_VERSION 60487u
#define XSTAR_FIXED_STATE_PROGRAM_ABI_VERSION 60485u
#define XSTAR_FIXED_STATE_MESSAGE_SIZE 1024u
#define XSTAR_FIXED_STATE_ID_SIZE 128u

/* Raw-program opcodes. These encode formulas and coefficients, never evaluated answers. */
typedef enum xstar_fixed_opcode_v1 {
    XSTAR_FIXED_OPCODE_SIMPLE_UCALC = 1,
    XSTAR_FIXED_OPCODE_TYPE2_CHARGE_TRANSFER = 2,
    XSTAR_FIXED_OPCODE_TYPE7_DIELECTRONIC_RECOMB = 7,
    XSTAR_FIXED_OPCODE_TYPE9_CHARGE_TRANSFER = 9,
    XSTAR_FIXED_OPCODE_TYPE10_CHARGE_TRANSFER = 10,
    XSTAR_FIXED_OPCODE_TYPE30_THREE_BODY_RECOMB = 30,
    XSTAR_FIXED_OPCODE_TYPE38_RR_FIT = 38,
    XSTAR_FIXED_OPCODE_TYPE39_DR_FIT = 39,
    XSTAR_FIXED_OPCODE_TYPE49_BOUND_FREE = 49,
    XSTAR_FIXED_OPCODE_TYPE50_RADIATIVE_LINE = 50,
    XSTAR_FIXED_OPCODE_TYPE51_BT_COLLISION = 51,
    XSTAR_FIXED_OPCODE_TYPE53_BOUND_FREE = 53,
    XSTAR_FIXED_OPCODE_TYPE54_ANGULAR_REDIS = 54,
    XSTAR_FIXED_OPCODE_TYPE56_TABULATED_COLLISION = 56,
    XSTAR_FIXED_OPCODE_TYPE57_COLLISIONAL_IONIZATION = 57,
    XSTAR_FIXED_OPCODE_TYPE59_VERNER_BOUND_FREE = 59,
    XSTAR_FIXED_OPCODE_TYPE60_CALLAWAY_COLLISION = 60,
    XSTAR_FIXED_OPCODE_TYPE62_CALLAWAY_COLLISION = 62,
    XSTAR_FIXED_OPCODE_TYPE63_ALGORITHMIC_COLLISION = 63,
    XSTAR_FIXED_OPCODE_TYPE66_COLLISION = 66,
    XSTAR_FIXED_OPCODE_TYPE68_HELIKE_COLLISION = 68,
    XSTAR_FIXED_OPCODE_TYPE69_HELIKE_COLLISION = 69,
    XSTAR_FIXED_OPCODE_TYPE71_SUPERLEVEL_CASCADE = 71,
    XSTAR_FIXED_OPCODE_TYPE72_DIELECTRONIC_CAPTURE = 72,
    XSTAR_FIXED_OPCODE_TYPE73_HELIKE_COLLISION = 73,
    XSTAR_FIXED_OPCODE_TYPE74_DELTA_RESONANCE = 74,
    XSTAR_FIXED_OPCODE_TYPE76_TWO_PHOTON = 76,
    XSTAR_FIXED_OPCODE_TYPE77_SUPERLEVEL_COLLISION = 77,
    XSTAR_FIXED_OPCODE_TYPE86_AUGER = 86,
    XSTAR_FIXED_OPCODE_TYPE88_SUPERLEVEL_BOUND_FREE = 88,
    XSTAR_FIXED_OPCODE_TYPE95_SPLINE_IONIZATION = 95,
    XSTAR_FIXED_OPCODE_TYPE99_SUPERLEVEL_BOUND_FREE = 99
} xstar_fixed_opcode_v1;

typedef enum xstar_fixed_state_status_flags_v1 {
    XSTAR_FIXED_STATE_STATUS_NONE = 0u,
    XSTAR_FIXED_STATE_STATUS_RAW_PROGRAM_LOADED = 1u << 0,
    XSTAR_FIXED_STATE_STATUS_LINKED_TRAVERSAL = 1u << 1,
    XSTAR_FIXED_STATE_STATUS_NATIVE_UCALC = 1u << 2,
    XSTAR_FIXED_STATE_STATUS_NATIVE_ELEMENT_SOLVE = 1u << 3,
    XSTAR_FIXED_STATE_STATUS_NATIVE_CONTINUUM = 1u << 4,
    XSTAR_FIXED_STATE_STATUS_NATIVE_SPECTRAL = 1u << 5,
    XSTAR_FIXED_STATE_STATUS_STATE_DEPENDENT = 1u << 6,
    XSTAR_FIXED_STATE_STATUS_NO_CALLBACKS = 1u << 7,
    XSTAR_FIXED_STATE_STATUS_ACTIVE_ATDB_LOWERED = 1u << 8,
    XSTAR_FIXED_STATE_STATUS_DSEC_RUNTIME_STATE_ABI = 1u << 9
} xstar_fixed_state_status_flags_v1;

typedef enum xstar_fixed_exact_workspace_flags_v1 {
    XSTAR_FIXED_EXACT_WORKSPACE_NONE = 0u,
    XSTAR_FIXED_EXACT_WORKSPACE_LINE = 1u << 0,
    XSTAR_FIXED_EXACT_WORKSPACE_RRC = 1u << 1,
    XSTAR_FIXED_EXACT_WORKSPACE_CONTINUUM = 1u << 2,
    XSTAR_FIXED_EXACT_WORKSPACE_LINE_PROFILE = 1u << 3,
    XSTAR_FIXED_EXACT_WORKSPACE_LTE_POPULATIONS = 1u << 4
} xstar_fixed_exact_workspace_flags_v1;

typedef enum xstar_fixed_runtime_state_flags_v1 {
    XSTAR_FIXED_RUNTIME_STATE_NONE = 0u,
    XSTAR_FIXED_RUNTIME_STATE_DSEC_COVERING_FRACTION = 1u << 0,
    XSTAR_FIXED_RUNTIME_STATE_GLOBAL_LEVEL_WORKSPACES = 1u << 1,
    XSTAR_FIXED_RUNTIME_STATE_MG_PRIMARY_OVERRIDE = 1u << 2,
    XSTAR_FIXED_RUNTIME_STATE_CALL1_THERMAL_ORACLE = 1u << 3,
    /* v0.6.48.7.46.25.5.17.17: repeated-evaluation hydrogen uses the
     * committed global population workspace for xh0/xh1, but clears the
     * compact terminal normalization row before msolvelucy. */
    XSTAR_FIXED_RUNTIME_STATE_REPEATED_HYDROGEN_SOURCE_STATE = 1u << 4,
    /* v0.6.48.7.46.25.5.17.18: retain the accepted active ion-stage window
     * across autonomous repeated evaluations.  The source controller carries
     * the compact stage window as run state rather than recomputing a wider
     * preliminary window from every trial electron fraction. */
    XSTAR_FIXED_RUNTIME_STATE_RETAIN_ACTIVE_STAGE_WINDOW = 1u << 5,
    /* v0.6.48.7.46.25.5.17.25.63: retain the exact sparse line/RRC source
     * workspaces on every controller evaluation, but defer the expensive
     * 9999-bin continuum and line-profile projection until a real product
     * boundary is being retained.  The controller gates depend on the
     * populations and thermal state, not on these derived public surfaces. */
    XSTAR_FIXED_RUNTIME_STATE_DEFER_PRODUCT_PROJECTION = 1u << 6,
    /* Calls 3-4 consume the live line optical-depth workspace; calls 1-2
     * remain optically thin under source calc_hmc_ion semantics. */
    XSTAR_FIXED_RUNTIME_STATE_LINE_TAU_ACTIVE = 1u << 7
} xstar_fixed_runtime_state_flags_v1;

typedef struct xstar_fixed_state_input_v1 {
    uint32_t struct_size;
    uint32_t abi_version;
    double temperature_k;
    double electron_density_cm3;
    double hydrogen_density_cm3;
    double neutral_h_density_cm3;
    double ionized_h_density_cm3;
    double electron_fraction_xee;
    double covering_fraction;
    double turbulent_velocity_km_s;
    const double* radiation_energy_ev;
    const double* radiation_flux;
    size_t radiation_bin_count;

    /* v0.6.48.7.24 source-faithful DSEC runtime-state extension.
     * These arrays are observational input workspaces owned by the caller.
     * dsec_bremsa is the full source radiation field used by ucalc/phint53;
     * continuum_tau_* are indexed by the original one-based npconi2 index.
     */
    const double* dsec_radiation_energy_ev;
    const double* dsec_bremsa;
    size_t dsec_radiation_bin_count;
    const double* continuum_tau_in;
    const double* continuum_tau_out;
    size_t continuum_tau_count;
    uint32_t runtime_state_flags;
    uint32_t reserved_runtime_state;
    double dsec_covering_fraction;

    /* v0.6.48.7.24 qualification-only call-start state transport. */
    const double* global_xilevg;
    const double* global_bilevg;
    const double* global_rnisg;
    size_t global_level_count;
    double mg_primary_heating_override;
    double mg_primary_cooling_override;
    double mg_secondary_heating_override;
    double mg_secondary_cooling_override;

    /* v0.6.48.7.24 qualification-only call-1 leaf/state oracle. */
    double h_primary_heating_override;
    double h_primary_cooling_override;
    double h_secondary_heating_override;
    double h_secondary_cooling_override;
    double he_primary_heating_override;
    double he_primary_cooling_override;
    double he_secondary_heating_override;
    double he_secondary_cooling_override;
    double htfreef_override;
    double clbrems_override;
    double cmp1_override;
    double cmp2_override;
    double htcomp_override;
    double clcomp_override;
    double charge_residual_override;
    double hmctot_override;
} xstar_fixed_state_input_v1;

typedef struct xstar_fixed_state_output_v1 {
    uint32_t struct_size;
    uint32_t abi_version;
    uint32_t status_flags;
    uint32_t reserved0;
    double element_heating;
    double element_cooling;
    double continuum_heating;
    double continuum_cooling;
    double total_heating;
    double total_cooling;
    double hmctot;
    /* Computed electron contribution (source enelec), not the trial input. */
    double electron_fraction_xee;
    /* Source charge residual: input electron_fraction_xee - computed enelec. */
    double elcter;
    double* populations;
    size_t populations_capacity;
    size_t populations_count;
    double* spectrum;
    size_t spectrum_capacity;
    size_t spectrum_count;
    double* opacity;
    size_t opacity_capacity;
    size_t opacity_count;
    char message[XSTAR_FIXED_STATE_MESSAGE_SIZE];
} xstar_fixed_state_output_v1;

/* Optional exact source-workspace sidecar.  It is deliberately separate from
 * xstar_fixed_state_output_v1 so ABI 60487 callers compiled before v25.5 keep
 * the original structure size and layout unchanged.
 */
typedef struct xstar_fixed_source_workspace_output_v1 {
    uint32_t struct_size;
    uint32_t abi_version;
    uint32_t exact_source_workspace_flags;
    uint32_t reserved0;
    double* lte_populations;
    size_t lte_populations_capacity;
    size_t lte_populations_count;
    double* rcem;
    size_t rcem_capacity;
    size_t rcem_count;
    double* oplin;
    size_t oplin_capacity;
    size_t oplin_count;
    double* cemab;
    size_t cemab_capacity;
    size_t cemab_count;
    double* cabab;
    size_t cabab_capacity;
    size_t cabab_count;
    double* opakab;
    size_t opakab_capacity;
    size_t opakab_count;
    double* rccemis;
    size_t rccemis_capacity;
    size_t rccemis_count;
    double* opakc;
    size_t opakc_capacity;
    size_t opakc_count;
    double* opakcont;
    size_t opakcont_capacity;
    size_t opakcont_count;
    double* fline;
    size_t fline_capacity;
    size_t fline_count;
    double* flinel;
    size_t flinel_capacity;
    size_t flinel_count;
    double* elum;
    size_t elum_capacity;
    size_t elum_count;
    double* line_profile_workspace;
    size_t line_profile_workspace_capacity;
    size_t line_profile_workspace_count;
    size_t native_line_count;
    size_t native_continuum_count;
    char message[XSTAR_FIXED_STATE_MESSAGE_SIZE];
} xstar_fixed_source_workspace_output_v1;

typedef struct xstar_fixed_state_stats_v1 {
    uint32_t struct_size;
    uint32_t abi_version;
    uint32_t status_flags;
    uint32_t reserved0;
    uint64_t calls;
    uint64_t records_seen;
    uint64_t records_evaluated;
    uint64_t records_unsupported;
    uint64_t linked_hops;
    uint64_t elements_attempted;
    uint64_t elements_solved;
    uint64_t contributions_constructed;
    uint64_t spectral_contributions;
    uint64_t continuum_bins;
    uint64_t python_callbacks;
    uint64_t state_generation;
    uint64_t topology_rows_loaded;
    uint64_t active_program_records;
    uint64_t type56_records_evaluated;
    uint64_t visited_data_types;
    double traversal_seconds;
    double rate_seconds;
    double element_seconds;
    double continuum_seconds;
    double spectral_seconds;
    double total_seconds;
    char program_id[XSTAR_FIXED_STATE_ID_SIZE];
    char message[XSTAR_FIXED_STATE_MESSAGE_SIZE];
} xstar_fixed_state_stats_v1;

/* v0.6.48.9.5 measurement-only prepared Type49/53 bound-free counters. */
#define XSTAR_BOUND_FREE_PERF_V064895_ABI_VERSION 604895u
typedef struct xstar_bound_free_perf_v064895 {
    uint32_t struct_size;
    uint32_t abi_version;
    uint64_t reduced_geometry_builds;
    uint64_t reduced_geometry_reuses;
    uint64_t full_geometry_builds;
    uint64_t full_geometry_reuses;
    uint64_t reduced_dynamic_integrals;
    uint64_t reduced_duplicate_reuses;
    uint64_t legacy_reduced_duplicate_integrals;
    uint64_t full_dynamic_integrals;
    uint64_t full_selected_type49_integrals;
    uint64_t full_selected_type53_integrals;
    uint64_t legacy_full_eager_integrals;
} xstar_bound_free_perf_v064895;


/* In-memory raw-program bundle.  This is the file-silent counterpart of the
 * historical manifest/elements/rows/records/reals/ints directory format.  All
 * pointers are borrowed for the duration of context creation and copied into
 * the native context before this function returns. */
typedef struct xstar_fixed_program_element_v1 {
    int32_t element_index;
    int32_t element_z;
    double abundance;
    int32_t n_rows;
    int32_t n_superlevels;
    int32_t n_ions;
    int32_t normalization_row;
    int32_t record_head;
    int32_t record_count;
} xstar_fixed_program_element_v1;

typedef struct xstar_fixed_program_row_v1 {
    int32_t element_index;
    int32_t row;
    int32_t superlevel;
    int32_t ion;
    int32_t ion_charge;
    double initial_population;
    double energy_ev;
    double statistical_weight;
    int32_t principal_n;
    int32_t orbital_l;
    int32_t global_level_index;
} xstar_fixed_program_row_v1;

typedef struct xstar_fixed_lte_ion_topology_v1 {
    int32_t element_index;
    int32_t ion_stage;
    int32_t start_row;
    int32_t nlev;
    /* Exact Type-13 terminal-continuum metadata for this ion.  The compact
     * terminal row is shared with the next-ion ground state, so these values
     * cannot be recovered from xstar_fixed_program_row_v1 alone. */
    double terminal_energy_ev;
    double terminal_statistical_weight;
} xstar_fixed_lte_ion_topology_v1;

/* v82 patch 5.6: exact calc_rates_level_lte Type-13 leveltemp data.
 * Every source Type-13 level is retained by ion/local ordinal, including the
 * shared terminal continuum row.  levwk consumes energy and statistical
 * weight from this surface rather than from the compact-row owner. */
typedef struct xstar_fixed_lte_level_v1 {
    int32_t element_index;
    int32_t ion_stage;
    int32_t local_level;
    int32_t reserved0;
    int64_t source_record;
    double energy_ev;
    double statistical_weight;
} xstar_fixed_lte_level_v1;

typedef struct xstar_fixed_program_record_v1 {
    int64_t source_position;
    int64_t record;
    int32_t next_index;
    int32_t element_index;
    int32_t opcode;
    int32_t data_type;
    int32_t rate_type;
    int32_t ion_index;
    int32_t ion_stage;
    int32_t lower_row;
    int32_t upper_row;
    size_t real_offset;
    size_t real_count;
    size_t int_offset;
    size_t int_count;
    double density_scale;
    double line_energy_ev;
    double atomic_mass_amu;
    double natural_width_ev;
    int32_t line_index_one_based;
    int32_t continuum_index_one_based;
    uint32_t matrix_enabled;
    uint32_t reserved0;
} xstar_fixed_program_record_v1;

typedef struct xstar_fixed_program_bundle_v1 {
    uint32_t struct_size;
    uint32_t abi_version;
    const char* program_id;
    uint32_t active_atdb_lowered;
    uint32_t reserved0;
    uint64_t topology_record_count;
    uint64_t unsupported_record_count;
    size_t native_line_count;
    size_t native_continuum_count;
    const xstar_fixed_program_element_v1* elements;
    size_t element_count;
    const xstar_fixed_program_row_v1* rows;
    size_t row_count;
    const xstar_fixed_program_record_v1* records;
    size_t record_count;
    const double* reals;
    size_t real_count;
    const int64_t* ints;
    size_t int_count;

    /* v82 patch 5.4 optional append-only source-LTE topology sidecar.
     * Callers with the historical prefix remain valid when struct_size ends
     * before lte_ions. */
    const xstar_fixed_lte_ion_topology_v1* lte_ions;
    size_t lte_ion_count;

    /* v82 patch 5.6 optional append-only complete Type-13 LTE leveltemp
     * sidecar.  Historical callers ending at lte_ion_count remain valid. */
    const xstar_fixed_lte_level_v1* lte_levels;
    size_t lte_level_count;
} xstar_fixed_program_bundle_v1;

XSTAR_FIXED_STATE_EXPORT int xstar_fixed_program_bundle_init_v1(
    xstar_fixed_program_bundle_v1* bundle);
XSTAR_FIXED_STATE_EXPORT int xstar_fixed_state_context_create_from_bundle_v1(
    const xstar_fixed_program_bundle_v1* bundle,
    struct xstar_fixed_state_context** context,
    char* message,
    size_t message_size);

typedef struct xstar_fixed_state_program_info_v1 {
    uint32_t struct_size;
    uint32_t abi_version;
    uint32_t status_flags;
    uint32_t reserved0;
    uint64_t element_count;
    uint64_t population_rows;
    uint64_t record_count;
    uint64_t topology_record_count;
    uint64_t unsupported_record_count;
    uint64_t native_line_count;
    uint64_t native_continuum_count;
    char program_id[XSTAR_FIXED_STATE_ID_SIZE];
    char message[XSTAR_FIXED_STATE_MESSAGE_SIZE];
} xstar_fixed_state_program_info_v1;

typedef struct xstar_fixed_state_thermal_components_v1 {
    uint32_t struct_size;
    uint32_t abi_version;
    double hydrogen_heating;
    double hydrogen_cooling;
    double hydrogen_heating2;
    double hydrogen_cooling2;
    double helium_heating;
    double helium_cooling;
    double helium_heating2;
    double helium_cooling2;
    double magnesium_heating;
    double magnesium_cooling;
    double magnesium_heating2;
    double magnesium_cooling2;
    double compton_heating;
    double compton_cooling;
    double free_free_heating;
    double bremsstrahlung_cooling;
    double element_heating;
    double element_cooling;
    double continuum_heating;
    double continuum_cooling;
    double total_heating;
    double total_cooling;
} xstar_fixed_state_thermal_components_v1;


/* Typed in-memory product diagnostics. These are the file-silent equivalent
 * of the final evaluation_*_records.csv, *_elements.csv, and
 * *_continuum_workspace.csv surfaces consumed by the historical writers. */
typedef struct xstar_fixed_state_product_diagnostic_counts_v1 {
    uint32_t struct_size;
    uint32_t abi_version;
    size_t record_count;
    size_t continuum_count;
    size_t element_count;
} xstar_fixed_state_product_diagnostic_counts_v1;

typedef struct xstar_fixed_record_product_diagnostic_v1 {
    int64_t source_position;
    int64_t record;
    int32_t element_index;
    int32_t element_z;
    int32_t data_type;
    int32_t rate_type;
    int32_t ion_stage;
    int32_t lower_row;
    int32_t upper_row;
    uint32_t spectral;
    double ans[6];
    double line_energy_ev;
    double atomic_mass_amu;
    double density_scale;
    double natural_width_ev;
    double opakab;
    uint32_t type50_valid;
    int32_t type50_line_index_one_based;
    double type50_wavelength_a;
    double type50_ptmp1;
    double type50_ptmp2;
    double type50_tau_in;
    double type50_tau_out;
    uint32_t type53_valid;
    uint32_t type49_valid;
    uint32_t type99_valid;
    int32_t continuum_index_one_based;
    double type53_threshold_ev;
    double type53_base_threshold_ev;
    double type49_threshold_ev;
    double type99_threshold_ev;
    double threshold_abs_sigma_cm2;
    double threshold_stimulated_sigma_cm2;
    double type53_ptmp1;
    double type53_ptmp2;
    double type53_tau_in;
    double type53_tau_out;
} xstar_fixed_record_product_diagnostic_v1;

typedef struct xstar_fixed_continuum_product_diagnostic_v1 {
    int32_t full_bin_one_based;
    double energy_ev;
    double comp_sum1_contribution;
    double comp_sum2_contribution;
    double comp_sum3_contribution;
    double free_free_opacity_increment;
    double brcems;
    double running_htcomp;
    double running_clcomp;
    double running_htfreef;
    double running_clbrems;
} xstar_fixed_continuum_product_diagnostic_v1;

typedef struct xstar_fixed_element_product_diagnostic_v1 {
    int32_t element_z;
    double heating;
    double cooling;
} xstar_fixed_element_product_diagnostic_v1;

typedef struct xstar_fixed_state_context xstar_fixed_state_context;

XSTAR_FIXED_STATE_EXPORT uint32_t xstar_fixed_state_engine_abi_version(void);
XSTAR_FIXED_STATE_EXPORT const char* xstar_fixed_state_engine_backend_name(void);
XSTAR_FIXED_STATE_EXPORT uint32_t xstar_fixed_state_engine_feature_flags(void);
XSTAR_FIXED_STATE_EXPORT int xstar_fixed_state_input_init_v1(xstar_fixed_state_input_v1* input);
XSTAR_FIXED_STATE_EXPORT int xstar_fixed_state_output_init_v1(xstar_fixed_state_output_v1* output);
XSTAR_FIXED_STATE_EXPORT int xstar_fixed_source_workspace_output_init_v1(
    xstar_fixed_source_workspace_output_v1* output);
XSTAR_FIXED_STATE_EXPORT int xstar_fixed_state_stats_init_v1(xstar_fixed_state_stats_v1* stats);
XSTAR_FIXED_STATE_EXPORT int xstar_bound_free_perf_init_v064895(
    xstar_bound_free_perf_v064895* perf);
XSTAR_FIXED_STATE_EXPORT int xstar_fixed_state_get_bound_free_perf_v064895(
    const xstar_fixed_state_context* context,
    xstar_bound_free_perf_v064895* perf);
XSTAR_FIXED_STATE_EXPORT int xstar_fixed_state_program_info_init_v1(xstar_fixed_state_program_info_v1* info);
XSTAR_FIXED_STATE_EXPORT int xstar_fixed_state_context_create_v1(
    const char* program_directory,
    xstar_fixed_state_context** context,
    char* message,
    size_t message_size
);
XSTAR_FIXED_STATE_EXPORT void xstar_fixed_state_context_destroy(xstar_fixed_state_context* context);
XSTAR_FIXED_STATE_EXPORT int xstar_fixed_state_context_get_program_info_v1(
    const xstar_fixed_state_context* context,
    xstar_fixed_state_program_info_v1* info,
    char* message,
    size_t message_size
);
XSTAR_FIXED_STATE_EXPORT int xstar_fixed_state_context_set_runtime_line_tau_v1(
    xstar_fixed_state_context* context,
    const double* tau_in,
    const double* tau_out,
    size_t count,
    char* message,
    size_t message_size
);

XSTAR_FIXED_STATE_EXPORT int xstar_fixed_state_context_reset_v1(
    xstar_fixed_state_context* context,
    char* message,
    size_t message_size
);
XSTAR_FIXED_STATE_EXPORT int xstar_fixed_state_run_v1(
    xstar_fixed_state_context* context,
    const xstar_fixed_state_input_v1* input,
    xstar_fixed_state_output_v1* output,
    xstar_fixed_state_stats_v1* stats,
    char* message,
    size_t message_size
);
XSTAR_FIXED_STATE_EXPORT int xstar_fixed_state_run_with_source_workspaces_v1(
    xstar_fixed_state_context* context,
    const xstar_fixed_state_input_v1* input,
    xstar_fixed_state_output_v1* output,
    xstar_fixed_source_workspace_output_v1* source_workspaces,
    xstar_fixed_state_stats_v1* stats,
    char* message,
    size_t message_size
);
/*
 * v0.6.48.9.4 accepted-boundary reuse support.
 *
 * The engine retains the exact sparse source workspaces produced by its most
 * recent evaluation before optional public-product projection.  This copies
 * those already-computed workspaces into caller-owned buffers and performs no
 * physics evaluation.  It is used to promote the accepted final DSEC state to
 * the public product boundary without rerunning the complete fixed-state
 * engine.
 */
XSTAR_FIXED_STATE_EXPORT int xstar_fixed_state_copy_last_source_workspaces_v064894(
    xstar_fixed_state_context* context,
    xstar_fixed_source_workspace_output_v1* source_workspaces,
    char* message,
    size_t message_size
);
XSTAR_FIXED_STATE_EXPORT int xstar_fixed_state_get_last_thermal_components_v1(
    const xstar_fixed_state_context* context,
    xstar_fixed_state_thermal_components_v1* components,
    char* message,
    size_t message_size
);


XSTAR_FIXED_STATE_EXPORT int xstar_fixed_state_product_diagnostic_counts_init_v1(
    xstar_fixed_state_product_diagnostic_counts_v1* counts);
XSTAR_FIXED_STATE_EXPORT int xstar_fixed_state_get_last_product_diagnostic_counts_v1(
    const xstar_fixed_state_context* context,
    xstar_fixed_state_product_diagnostic_counts_v1* counts,
    char* message,
    size_t message_size);
XSTAR_FIXED_STATE_EXPORT int xstar_fixed_state_get_last_record_product_diagnostics_v1(
    const xstar_fixed_state_context* context,
    xstar_fixed_record_product_diagnostic_v1* rows,
    size_t capacity,
    size_t* count,
    char* message,
    size_t message_size);
XSTAR_FIXED_STATE_EXPORT int xstar_fixed_state_get_last_continuum_product_diagnostics_v1(
    const xstar_fixed_state_context* context,
    xstar_fixed_continuum_product_diagnostic_v1* rows,
    size_t capacity,
    size_t* count,
    char* message,
    size_t message_size);
XSTAR_FIXED_STATE_EXPORT int xstar_fixed_state_get_last_element_product_diagnostics_v1(
    const xstar_fixed_state_context* context,
    xstar_fixed_element_product_diagnostic_v1* rows,
    size_t capacity,
    size_t* count,
    char* message,
    size_t message_size);

XSTAR_FIXED_STATE_EXPORT int xstar_fixed_state_write_last_thermal_budget_v1(
    const xstar_fixed_state_context* context,
    const char* output_csv,
    uint64_t sequence,
    uint64_t call_index,
    uint64_t evaluation_index,
    const char* kind,
    char* message,
    size_t message_size
);

XSTAR_FIXED_STATE_EXPORT int xstar_fixed_state_write_visited_report_v1(
    const xstar_fixed_state_context* context,
    const char* output_path,
    char* message,
    size_t message_size
);
XSTAR_FIXED_STATE_EXPORT int xstar_fixed_state_write_last_diagnostics_v1(
    const xstar_fixed_state_context* context,
    const char* output_directory,
    uint64_t evaluation_ordinal,
    char* message,
    size_t message_size
);
XSTAR_FIXED_STATE_EXPORT int xstar_fixed_state_run_batch_v1(
    xstar_fixed_state_context* context,
    const xstar_fixed_state_input_v1* inputs,
    size_t input_count,
    xstar_fixed_state_output_v1* outputs,
    xstar_fixed_state_stats_v1* stats,
    char* message,
    size_t message_size
);

#ifdef __cplusplus
}
#endif

#endif
