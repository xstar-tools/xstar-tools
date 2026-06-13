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
    XSTAR_FIXED_OPCODE_TYPE9_CHARGE_TRANSFER = 9,
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
    XSTAR_FIXED_OPCODE_TYPE60_CALLAWAY_COLLISION = 60,
    XSTAR_FIXED_OPCODE_TYPE62_CALLAWAY_COLLISION = 62,
    XSTAR_FIXED_OPCODE_TYPE63_ALGORITHMIC_COLLISION = 63,
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

typedef enum xstar_fixed_runtime_state_flags_v1 {
    XSTAR_FIXED_RUNTIME_STATE_NONE = 0u,
    XSTAR_FIXED_RUNTIME_STATE_DSEC_COVERING_FRACTION = 1u << 0
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

    /* v0.6.48.7.21.1 source-faithful DSEC runtime-state extension.
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
    double electron_fraction_xee;
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
    char program_id[XSTAR_FIXED_STATE_ID_SIZE];
    char message[XSTAR_FIXED_STATE_MESSAGE_SIZE];
} xstar_fixed_state_program_info_v1;

typedef struct xstar_fixed_state_context xstar_fixed_state_context;

XSTAR_FIXED_STATE_EXPORT uint32_t xstar_fixed_state_engine_abi_version(void);
XSTAR_FIXED_STATE_EXPORT const char* xstar_fixed_state_engine_backend_name(void);
XSTAR_FIXED_STATE_EXPORT uint32_t xstar_fixed_state_engine_feature_flags(void);
XSTAR_FIXED_STATE_EXPORT int xstar_fixed_state_input_init_v1(xstar_fixed_state_input_v1* input);
XSTAR_FIXED_STATE_EXPORT int xstar_fixed_state_output_init_v1(xstar_fixed_state_output_v1* output);
XSTAR_FIXED_STATE_EXPORT int xstar_fixed_state_stats_init_v1(xstar_fixed_state_stats_v1* stats);
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
