// XSTAR-SOURCE-CORRESPONDENCE-BEGIN
// Fortran: calc_hmc_element.f90; calc_hmc_ion.f90; calc_ion_rates.f90; levwkelement.f90
// Role: C ABI structures/functions for per-element ion/rate/matrix/level-population evaluation.
// Relation: Interface representation of the mapped element fixed-state operator.
// Concordance: ION-001; LEVEL-001; MATRIX-001
// Qualification: matrix repair 12.3.25; C++ 12.3.44
// XSTAR-SOURCE-CORRESPONDENCE-END

#ifndef XSTAR_ELEMENT_ENGINE_H
#define XSTAR_ELEMENT_ENGINE_H

#include <stddef.h>
#include <stdint.h>

#ifdef _WIN32
#  define XSTAR_ELEMENT_EXPORT __declspec(dllexport)
#else
#  define XSTAR_ELEMENT_EXPORT __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#endif

#define XSTAR_ELEMENT_ENGINE_ABI_VERSION 60451u
#define XSTAR_ELEMENT_MESSAGE_SIZE 1024u

typedef enum xstar_element_flags_v1 {
    XSTAR_ELEMENT_STRICT_SOURCE_ORDER = 1u << 0,
    XSTAR_ELEMENT_DIAGNOSTICS_SUMMARY = 1u << 1,
    XSTAR_ELEMENT_RETURN_MATRICES = 1u << 2,
    XSTAR_ELEMENT_ALLOW_DENSE_RESCUE = 1u << 3
} xstar_element_flags_v1;

typedef enum xstar_element_status_flags_v1 {
    XSTAR_ELEMENT_STATUS_NONE = 0u,
    XSTAR_ELEMENT_STATUS_CONVERGED = 1u << 0,
    XSTAR_ELEMENT_STATUS_SOURCE_ORDER_VERIFIED = 1u << 1,
    XSTAR_ELEMENT_STATUS_NATIVE_MATRIX_ASSEMBLY = 1u << 2,
    XSTAR_ELEMENT_STATUS_NATIVE_LUCY_SOLVE = 1u << 3,
    XSTAR_ELEMENT_STATUS_STATE_COMMITTED = 1u << 4,
    XSTAR_ELEMENT_STATUS_DENSE_RESCUE_USED = 1u << 5,
    XSTAR_ELEMENT_STATUS_NATIVE_CONSTRUCTION = 1u << 6,
    XSTAR_ELEMENT_STATUS_CANONICAL_THERMAL_LEDGER = 1u << 7
} xstar_element_status_flags_v1;

typedef struct xstar_element_term_v1 {
    int64_t source_position;
    int64_t term_index;
    int64_t record;
    int32_t data_type;
    int32_t rate_type;
    int32_t ion_index;
    int32_t ion_stage;
    int32_t row;
    int32_t column;
    int32_t reserved0;
    int32_t reserved1;
    double aj1;
    double aj2;
    double cj;
    double cj2;
} xstar_element_term_v1;

typedef enum xstar_canonical_thermal_role_v1 {
    XSTAR_CANONICAL_THERMAL_FORWARD_DIAG_LOSS = 1,
    XSTAR_CANONICAL_THERMAL_REVERSE_DIAG_LOSS = 2
} xstar_canonical_thermal_role_v1;

typedef enum xstar_canonical_thermal_flags_v1 {
    XSTAR_CANONICAL_THERMAL_TYPE53 = 1u << 0,
    XSTAR_CANONICAL_THERMAL_NORMALIZATION_ROW = 1u << 1,
    XSTAR_CANONICAL_THERMAL_SOURCE_DOMAIN_INCLUDED = 1u << 2,
    XSTAR_CANONICAL_THERMAL_TYPE99_SOURCE_CORRECTED = 1u << 3,
    XSTAR_CANONICAL_THERMAL_PRIMARY_SOURCE_ORDERED = 1u << 4,
    XSTAR_CANONICAL_THERMAL_MATRIX_INSERTION_CAPTURED = 1u << 5
} xstar_canonical_thermal_flags_v1;

/*
 * Immutable diagonal Thermal term whose coefficients are captured when a
 * UCalc contribution enters the active matrix stream, before matrix-family
 * closure may alter ans1/ans2.  Closure may filter or restore source order,
 * but the same committed term objects are passed to the element and
 * fixed-state Thermal consumers.
 */
typedef struct xstar_canonical_thermal_term_v1 {
    int64_t source_position;
    int64_t term_index;
    int64_t record;
    int64_t primary_source_order_index;
    int32_t data_type;
    int32_t rate_type;
    int32_t ion_index;
    int32_t ion_stage;
    int32_t compact_row;
    int32_t native_compact_row;
    int32_t source_compact_row;
    int32_t role;
    uint32_t flags;
    uint32_t reserved0;
    double cj;
    double cj2;
    double native_cj;
    double source_cj;
} xstar_canonical_thermal_term_v1;

typedef struct xstar_element_contribution_v1 {
    int64_t source_position;
    int64_t record;
    int32_t data_type;
    int32_t rate_type;
    int32_t ion_index;
    int32_t ion_stage;
    int32_t lower_row;
    int32_t upper_row;
    int32_t reserved0;
    int32_t reserved1;
    double ans1;
    double ans2;
    double ans3;
    double ans4;
    double ans5;
    double ans6;
    double density_scale;
} xstar_element_contribution_v1;

typedef struct xstar_element_input_v1 {
    uint32_t struct_size;
    uint32_t abi_version;
    uint32_t flags;
    int32_t element_z;
    int32_t n_rows;
    int32_t n_superlevels;
    int32_t n_ions;
    int32_t normalization_row;
    int32_t max_lucy_iterations;
    int32_t max_fixed_point_iterations;
    int32_t reserved0;
    double lucy_tolerance;
    double fixed_point_tolerance;
    const int32_t* superlevel_by_row;
    const int32_t* ion_by_row;
    const double* initial_populations;
    const xstar_element_term_v1* terms;
    size_t term_count;
} xstar_element_input_v1;

typedef struct xstar_element_output_v1 {
    uint32_t struct_size;
    uint32_t abi_version;
    uint32_t status_flags;
    int32_t element_z;
    int32_t outer_iterations;
    int32_t fixed_point_iterations;
    int32_t n_negative_populations;
    int32_t condensed_dimension;
    int32_t reserved0;
    double final_outer_difference;
    double final_fixed_point_difference;
    double normalization;
    double normalization_error;
    double heating;
    double cooling;
    double heating2;
    double cooling2;
    double max_relative_row_residual;
    double max_active_relative_row_residual;
    double l1_row_residual;
    double l1_relative_row_residual;
    double matrix_assembly_seconds;
    double solver_seconds;
    double state_commit_seconds;
    double construction_seconds;
    uint64_t records_constructed;
    uint64_t terms_constructed;

    double* populations;
    size_t populations_capacity;
    size_t populations_count;
    double* final_outer_start_populations;
    size_t final_outer_start_capacity;
    size_t final_outer_start_count;

    double* dense_matrix;
    size_t dense_matrix_capacity;
    size_t dense_matrix_count;
    double* heating_matrix;
    size_t heating_matrix_capacity;
    size_t heating_matrix_count;
    double* heating_matrix2;
    size_t heating_matrix2_capacity;
    size_t heating_matrix2_count;
    double* rhs;
    size_t rhs_capacity;
    size_t rhs_count;

    double* gamma;
    size_t gamma_capacity;
    double* alpha;
    size_t alpha_capacity;
    double* fgamma;
    size_t fgamma_capacity;
    double* falpha;
    size_t falpha_capacity;
    int64_t* igammamax_record;
    size_t igammamax_capacity;
    int64_t* ialphamax_record;
    size_t ialphamax_capacity;

    double* ion_population_totals;
    size_t ion_population_totals_capacity;
    double* ion_population_totals_final_vector;
    size_t ion_population_totals_final_capacity;
    double* ionization_totals;
    size_t ionization_totals_capacity;
    double* recombination_totals;
    size_t recombination_totals_capacity;
    double* ionization_components;
    size_t ionization_components_capacity;
    double* recombination_components;
    size_t recombination_components_capacity;

    double* row_residual;
    size_t row_residual_capacity;
    double* row_scale;
    size_t row_scale_capacity;
    double* relative_row_residual;
    size_t relative_row_residual_capacity;

    char solver_method[128];
    char message[XSTAR_ELEMENT_MESSAGE_SIZE];
} xstar_element_output_v1;


#define XSTAR_ELEMENT_SOLVE_STAGE_TRACE_ABI_VERSION 1u

typedef struct xstar_element_solve_stage_trace_v1 {
    uint32_t struct_size;
    uint32_t abi_version;
    int32_t element_z;
    int32_t n_rows;
    int32_t n_superlevels;
    int32_t final_outer_iteration;
    int32_t final_fixed_iterations;
    int32_t total_fixed_point_iterations;
    uint32_t valid;
    uint32_t reserved0;

    double* final_outer_start_populations;
    size_t final_outer_start_capacity;
    size_t final_outer_start_count;
    double* final_superlevel_populations_before_solve;
    size_t final_superlevel_populations_before_solve_capacity;
    size_t final_superlevel_populations_before_solve_count;
    double* final_condensed_matrix;
    size_t final_condensed_matrix_capacity;
    size_t final_condensed_matrix_count;
    double* final_condensed_rhs;
    size_t final_condensed_rhs_capacity;
    size_t final_condensed_rhs_count;
    double* final_first_lu_solution;
    size_t final_first_lu_solution_capacity;
    size_t final_first_lu_solution_count;
    double* final_refinement_residual;
    size_t final_refinement_residual_capacity;
    size_t final_refinement_residual_count;
    double* final_refinement_correction;
    size_t final_refinement_correction_capacity;
    size_t final_refinement_correction_count;
    double* final_refined_superlevel_solution;
    size_t final_refined_superlevel_solution_capacity;
    size_t final_refined_superlevel_solution_count;
    double* final_population_after_condensed;
    size_t final_population_after_condensed_capacity;
    size_t final_population_after_condensed_count;
    double* final_fixed_point_population_before;
    size_t final_fixed_point_population_before_capacity;
    size_t final_fixed_point_population_before_count;
    double* final_fixed_point_population_after;
    size_t final_fixed_point_population_after_capacity;
    size_t final_fixed_point_population_after_count;
} xstar_element_solve_stage_trace_v1;

typedef struct xstar_element_engine_stats_v1 {
    uint32_t struct_size;
    uint32_t abi_version;
    uint64_t elements_attempted;
    uint64_t elements_completed;
    uint64_t evaluations_attempted;
    uint64_t evaluations_completed;
    uint64_t terms_committed;
    uint64_t source_order_failures;
    uint64_t workspace_resizes;
    uint64_t construction_calls;
    uint64_t records_constructed;
    uint64_t terms_constructed;
    double construction_seconds;
    double matrix_assembly_seconds;
    double solver_seconds;
    double state_commit_seconds;
} xstar_element_engine_stats_v1;

typedef struct xstar_element_engine_context xstar_element_engine_context;

XSTAR_ELEMENT_EXPORT uint32_t xstar_element_engine_abi_version(void);
XSTAR_ELEMENT_EXPORT const char* xstar_element_engine_backend_name(void);
XSTAR_ELEMENT_EXPORT int xstar_element_engine_feature_flags(void);
XSTAR_ELEMENT_EXPORT int xstar_element_input_init_v1(xstar_element_input_v1* input);
XSTAR_ELEMENT_EXPORT int xstar_element_output_init_v1(xstar_element_output_v1* output);
XSTAR_ELEMENT_EXPORT int xstar_element_engine_stats_init_v1(xstar_element_engine_stats_v1* stats);

XSTAR_ELEMENT_EXPORT int xstar_element_solve_stage_trace_init_v1(
    xstar_element_solve_stage_trace_v1* trace
);
XSTAR_ELEMENT_EXPORT int xstar_element_engine_get_last_solve_stage_trace_v1(
    const xstar_element_engine_context* context,
    xstar_element_solve_stage_trace_v1* trace,
    char* message,
    size_t message_size
);

XSTAR_ELEMENT_EXPORT int xstar_element_engine_context_create_v1(
    xstar_element_engine_context** context,
    char* message,
    size_t message_size
);
XSTAR_ELEMENT_EXPORT void xstar_element_engine_context_destroy(xstar_element_engine_context* context);
XSTAR_ELEMENT_EXPORT int xstar_element_engine_context_reset_v1(
    xstar_element_engine_context* context,
    char* message,
    size_t message_size
);
XSTAR_ELEMENT_EXPORT int xstar_element_engine_get_stats_v1(
    const xstar_element_engine_context* context,
    xstar_element_engine_stats_v1* stats,
    char* message,
    size_t message_size
);
XSTAR_ELEMENT_EXPORT int xstar_element_engine_run_construction_v1(
    xstar_element_engine_context* context,
    const xstar_element_input_v1* input,
    const xstar_element_contribution_v1* contributions,
    size_t contribution_count,
    xstar_element_output_v1* output,
    char* message,
    size_t message_size
);
XSTAR_ELEMENT_EXPORT int xstar_element_engine_run_construction_with_thermal_ledger_v1(
    xstar_element_engine_context* context,
    const xstar_element_input_v1* input,
    const xstar_element_contribution_v1* contributions,
    size_t contribution_count,
    const xstar_canonical_thermal_term_v1* thermal_terms,
    size_t thermal_term_count,
    uint64_t* consumed_thermal_ledger_fingerprint,
    xstar_element_output_v1* output,
    char* message,
    size_t message_size
);
XSTAR_ELEMENT_EXPORT int xstar_element_engine_run_element_v1(
    xstar_element_engine_context* context,
    const xstar_element_input_v1* input,
    xstar_element_output_v1* output,
    char* message,
    size_t message_size
);
XSTAR_ELEMENT_EXPORT int xstar_element_engine_run_construction_evaluation_v1(
    xstar_element_engine_context* context,
    const xstar_element_input_v1* inputs,
    const xstar_element_contribution_v1* const* contribution_arrays,
    const size_t* contribution_counts,
    size_t element_count,
    xstar_element_output_v1* outputs,
    char* message,
    size_t message_size
);
XSTAR_ELEMENT_EXPORT int xstar_element_engine_run_evaluation_v1(
    xstar_element_engine_context* context,
    const xstar_element_input_v1* inputs,
    size_t element_count,
    xstar_element_output_v1* outputs,
    char* message,
    size_t message_size
);

#ifdef __cplusplus
}
#endif

#endif
