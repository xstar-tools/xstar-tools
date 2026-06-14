#ifndef XSTAR_API_H
#define XSTAR_API_H

#include <stddef.h>
#include <stdint.h>
#include "xstar_element_engine.h"
#include "xstar_spectral_engine.h"
#include "xstar_thermal_engine.h"

#ifdef _WIN32
#  ifdef XSTAR_API_BUILD
#    define XSTAR_API_EXPORT __declspec(dllexport)
#  else
#    define XSTAR_API_EXPORT __declspec(dllimport)
#  endif
#else
#  define XSTAR_API_EXPORT __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#endif

#define XSTAR_API_ABI_VERSION 60487u
#define XSTAR_API_VERSION_STRING "0.6.48.7.29"
#define XSTAR_BACKEND_NAME_SIZE 32u
#define XSTAR_PATH_SIZE 1024u
#define XSTAR_MESSAGE_SIZE 1024u

typedef enum xstar_status_code {
    XSTAR_STATUS_OK = 0,
    XSTAR_STATUS_INVALID_ARGUMENT = 1,
    XSTAR_STATUS_ABI_MISMATCH = 2,
    XSTAR_STATUS_BACKEND_NOT_FOUND = 3,
    XSTAR_STATUS_BACKEND_LOAD_FAILED = 4,
    XSTAR_STATUS_BACKEND_ERROR = 5,
    XSTAR_STATUS_BUFFER_TOO_SMALL = 6,
    XSTAR_STATUS_NOT_IMPLEMENTED = 7,
    XSTAR_STATUS_INTERNAL_ERROR = 8
} xstar_status_code;

typedef enum xstar_config_flags {
    XSTAR_CONFIG_ENABLE_FALLBACK = 1u << 0,
    XSTAR_CONFIG_ALLOW_SCAFFOLD_MODEL = 1u << 1,
    XSTAR_CONFIG_STRICT_SOURCE_ORDER = 1u << 2,
    XSTAR_CONFIG_QUALIFICATION_MODE = 1u << 3
} xstar_config_flags;

typedef enum xstar_zone_status_flags {
    XSTAR_ZONE_STATUS_NONE = 0u,
    XSTAR_ZONE_STATUS_SCAFFOLD_RESULT = 1u << 0,
    XSTAR_ZONE_STATUS_CPP_BACKEND = 1u << 1,
    XSTAR_ZONE_STATUS_PYTHON_BACKEND = 1u << 2,
    XSTAR_ZONE_STATUS_FALLBACK_USED = 1u << 3,
    XSTAR_ZONE_STATUS_COMPILED_CASE = 1u << 4
} xstar_zone_status_flags;

typedef enum xstar_component_id {
    XSTAR_COMPONENT_ENGINE = 0,
    XSTAR_COMPONENT_RATES = 1,
    XSTAR_COMPONENT_MATRIX = 2,
    XSTAR_COMPONENT_SOLVER = 3,
    XSTAR_COMPONENT_EMISSIVITY = 4,
    XSTAR_COMPONENT_OPACITY = 5,
    XSTAR_COMPONENT_THERMAL = 6,
    XSTAR_COMPONENT_IO = 7,
    XSTAR_COMPONENT_COUNT = 8
} xstar_component_id;

typedef enum xstar_component_flags {
    XSTAR_COMPONENT_LIBRARY_LOADED = 1u << 0,
    XSTAR_COMPONENT_IMPLEMENTATION_AVAILABLE = 1u << 1,
    XSTAR_COMPONENT_PRODUCT_ACTIVE = 1u << 2,
    XSTAR_COMPONENT_SCAFFOLD_ONLY = 1u << 3,
    XSTAR_COMPONENT_PYTHON_MODULE_AVAILABLE = 1u << 4
} xstar_component_flags;

typedef struct xstar_config_v1 {
    uint32_t struct_size;
    uint32_t abi_version;
    uint32_t flags;
    uint32_t thread_count;
    char backend[XSTAR_BACKEND_NAME_SIZE];
    char engine_backend[XSTAR_BACKEND_NAME_SIZE];
    char rates_backend[XSTAR_BACKEND_NAME_SIZE];
    char matrix_backend[XSTAR_BACKEND_NAME_SIZE];
    char solver_backend[XSTAR_BACKEND_NAME_SIZE];
    char emissivity_backend[XSTAR_BACKEND_NAME_SIZE];
    char opacity_backend[XSTAR_BACKEND_NAME_SIZE];
    char thermal_backend[XSTAR_BACKEND_NAME_SIZE];
    char plugin_directory[XSTAR_PATH_SIZE];
    char atomic_database_path[XSTAR_PATH_SIZE];
    char cache_directory[XSTAR_PATH_SIZE];
    char python_home[XSTAR_PATH_SIZE];
    char python_path[XSTAR_PATH_SIZE];
} xstar_config_v1;

typedef struct xstar_zone_input_v1 {
    uint32_t struct_size;
    uint32_t flags;
    uint64_t zone_id;
    double temperature;
    double electron_density;
    double hydrogen_density;
    double electron_fraction;
    double ionization_parameter;
    double column_density;
    const double* abundances;
    size_t abundance_count;
    const double* radiation_energy;
    const double* radiation_flux;
    size_t radiation_bin_count;
} xstar_zone_input_v1;

typedef struct xstar_zone_output_v1 {
    uint32_t struct_size;
    uint32_t status_flags;
    uint64_t zone_id;
    double heating;
    double cooling;
    double electron_fraction;
    double* ion_fractions;
    size_t ion_fraction_capacity;
    size_t ion_fraction_count;
    double* spectrum;
    size_t spectrum_capacity;
    size_t spectrum_count;
    double* opacity;
    size_t opacity_capacity;
    size_t opacity_count;
    char backend[XSTAR_BACKEND_NAME_SIZE];
    char message[XSTAR_MESSAGE_SIZE];
} xstar_zone_output_v1;

typedef struct xstar_context_stats_v1 {
    uint32_t struct_size;
    uint32_t reserved;
    uint64_t zones_attempted;
    uint64_t zones_completed;
    uint64_t batch_calls;
    uint64_t fallback_count;
} xstar_context_stats_v1;

typedef struct xstar_component_info_v1 {
    uint32_t struct_size;
    uint32_t component_id;
    uint32_t abi_version;
    uint32_t feature_flags;
    uint32_t status_flags;
    char component_name[XSTAR_BACKEND_NAME_SIZE];
    char requested_backend[XSTAR_BACKEND_NAME_SIZE];
    char implementation[128];
    char library_path[XSTAR_PATH_SIZE];
    char message[XSTAR_MESSAGE_SIZE];
} xstar_component_info_v1;

typedef struct xstar_context xstar_context;

XSTAR_API_EXPORT uint32_t xstar_api_abi_version(void);
XSTAR_API_EXPORT const char* xstar_api_version_string(void);
XSTAR_API_EXPORT size_t xstar_backend_count(void);
XSTAR_API_EXPORT const char* xstar_backend_name(size_t index);
XSTAR_API_EXPORT const char* xstar_status_string(int status);
XSTAR_API_EXPORT const char* xstar_api_last_error(void);

XSTAR_API_EXPORT int xstar_config_init_v1(xstar_config_v1* config);
XSTAR_API_EXPORT int xstar_zone_input_init_v1(xstar_zone_input_v1* input);
XSTAR_API_EXPORT int xstar_zone_output_init_v1(xstar_zone_output_v1* output);
XSTAR_API_EXPORT int xstar_context_stats_init_v1(xstar_context_stats_v1* stats);
XSTAR_API_EXPORT int xstar_component_info_init_v1(xstar_component_info_v1* info);

XSTAR_API_EXPORT int xstar_context_create_v1(
    const xstar_config_v1* config,
    xstar_context** context
);
XSTAR_API_EXPORT void xstar_context_destroy(xstar_context* context);
XSTAR_API_EXPORT int xstar_context_reset(xstar_context* context);
XSTAR_API_EXPORT const char* xstar_context_backend_name(const xstar_context* context);
XSTAR_API_EXPORT const char* xstar_context_last_error(const xstar_context* context);
XSTAR_API_EXPORT int xstar_context_get_stats_v1(
    const xstar_context* context,
    xstar_context_stats_v1* stats
);
XSTAR_API_EXPORT int xstar_context_get_component_info_v1(
    const xstar_context* context,
    uint32_t component_id,
    xstar_component_info_v1* info
);
XSTAR_API_EXPORT int xstar_context_run_zone_v1(
    xstar_context* context,
    const xstar_zone_input_v1* input,
    xstar_zone_output_v1* output
);
XSTAR_API_EXPORT int xstar_context_run_batch_v1(
    xstar_context* context,
    const xstar_zone_input_v1* inputs,
    size_t zone_count,
    xstar_zone_output_v1* outputs
);
XSTAR_API_EXPORT int xstar_context_run_element_construction_v1(
    xstar_context* context,
    const xstar_element_input_v1* input,
    const xstar_element_contribution_v1* contributions,
    size_t contribution_count,
    xstar_element_output_v1* output
);
XSTAR_API_EXPORT int xstar_context_run_element_v1(
    xstar_context* context,
    const xstar_element_input_v1* input,
    xstar_element_output_v1* output
);
XSTAR_API_EXPORT int xstar_context_run_construction_evaluation_v1(
    xstar_context* context,
    const xstar_element_input_v1* inputs,
    const xstar_element_contribution_v1* const* contribution_arrays,
    const size_t* contribution_counts,
    size_t element_count,
    xstar_element_output_v1* outputs
);
XSTAR_API_EXPORT int xstar_context_run_evaluation_v1(
    xstar_context* context,
    const xstar_element_input_v1* inputs,
    size_t element_count,
    xstar_element_output_v1* outputs
);
XSTAR_API_EXPORT int xstar_context_get_element_stats_v1(
    const xstar_context* context,
    xstar_element_engine_stats_v1* stats
);
XSTAR_API_EXPORT int xstar_context_apply_spectral_contributions_v1(
    xstar_context* context,
    const xstar_spectral_contribution_v1* contributions,
    size_t contribution_count,
    const double* seed_profiles,
    size_t seed_profile_stride,
    xstar_spectral_workspace_v1* workspace,
    xstar_spectral_stats_v1* stats
);
XSTAR_API_EXPORT int xstar_context_apply_heatt_v1(
    xstar_context* context,
    xstar_heatt_workspace_v1* workspace,
    const xstar_heatt_line_v1* lines,
    size_t line_count,
    const xstar_heatt_rrc_v1* rrcs,
    size_t rrc_count,
    xstar_heatt_stats_v1* stats
);
XSTAR_API_EXPORT int xstar_context_run_thermal_evaluation_loop_v1(
    xstar_context* context,
    const xstar_dsec_config_v1* config,
    xstar_thermal_state_v1* state,
    xstar_thermal_evaluator_fn_v1 evaluator,
    void* user_data,
    xstar_thermal_trace_event_v1* trace,
    size_t trace_capacity,
    size_t* trace_count,
    xstar_dsec_stats_v1* stats
);

#define XSTAR_COMPILED_CASE_ABI_VERSION 60480u
#define XSTAR_COMPILED_CASE_ID_SIZE 128u
#define XSTAR_FINGERPRINT_SIZE 65u

typedef enum xstar_compiled_case_status_flags {
    XSTAR_COMPILED_CASE_STATUS_NONE = 0u,
    XSTAR_COMPILED_CASE_STATUS_LOADED = 1u << 0,
    XSTAR_COMPILED_CASE_STATUS_CALLBACK_FREE = 1u << 1,
    XSTAR_COMPILED_CASE_STATUS_EXACT_REFERENCE_STATE = 1u << 2,
    XSTAR_COMPILED_CASE_STATUS_SCIENCE_FILES_VERIFIED = 1u << 3
} xstar_compiled_case_status_flags;

typedef struct xstar_compiled_case_stats_v1 {
    uint32_t struct_size;
    uint32_t abi_version;
    uint32_t status_flags;
    uint32_t reserved0;
    uint64_t evaluations_native;
    uint64_t python_callbacks;
    uint64_t science_files_written;
    uint64_t science_files_verified;
    uint64_t zones_attempted;
    uint64_t zones_completed;
    uint64_t batch_calls;
    uint64_t reserved1;
    double run_seconds;
    double final_temperature_t4;
    double final_electron_fraction_xee;
    double final_hmctot;
    double final_elcter;
    char case_id[XSTAR_COMPILED_CASE_ID_SIZE];
    char parameter_fingerprint[XSTAR_FINGERPRINT_SIZE];
    char message[XSTAR_MESSAGE_SIZE];
} xstar_compiled_case_stats_v1;

typedef struct xstar_compiled_case_context xstar_compiled_case_context;

XSTAR_API_EXPORT int xstar_compiled_case_stats_init_v1(
    xstar_compiled_case_stats_v1* stats
);
XSTAR_API_EXPORT int xstar_compiled_case_context_create_v1(
    const char* case_directory,
    xstar_compiled_case_context** context,
    char* message,
    size_t message_size
);
XSTAR_API_EXPORT void xstar_compiled_case_context_destroy(
    xstar_compiled_case_context* context
);
XSTAR_API_EXPORT int xstar_compiled_case_run_files_v1(
    xstar_compiled_case_context* context,
    const char* output_directory,
    xstar_compiled_case_stats_v1* stats,
    char* message,
    size_t message_size
);
XSTAR_API_EXPORT int xstar_compiled_case_run_zone_v1(
    xstar_compiled_case_context* context,
    const xstar_zone_input_v1* input,
    xstar_zone_output_v1* output,
    xstar_compiled_case_stats_v1* stats,
    char* message,
    size_t message_size
);
XSTAR_API_EXPORT int xstar_compiled_case_run_batch_v1(
    xstar_compiled_case_context* context,
    const xstar_zone_input_v1* inputs,
    size_t zone_count,
    xstar_zone_output_v1* outputs,
    xstar_compiled_case_stats_v1* stats,
    char* message,
    size_t message_size
);

#ifdef __cplusplus
}
#endif

#endif
