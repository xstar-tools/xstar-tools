// XSTAR-SOURCE-CORRESPONDENCE-BEGIN
// Fortran: heatt.f90; dsec.f90; calc_hmc_all.f90
// Role: C ABI for thermal/HEATT workspaces, DSEC controller configuration, evaluations, and statistics.
// Relation: Interface representation of the source thermal controller/operator boundary.
// Concordance: THERM-001; DSEC-001
// Qualification: DSEC/thermal baseline 12.3.42/44
// XSTAR-SOURCE-CORRESPONDENCE-END

#ifndef XSTAR_THERMAL_ENGINE_H
#define XSTAR_THERMAL_ENGINE_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define XSTAR_THERMAL_ENGINE_ABI_VERSION 60471u

#define XSTAR_THERMAL_STATUS_NATIVE_HEATT 1u
#define XSTAR_THERMAL_STATUS_NATIVE_DSEC 2u
#define XSTAR_THERMAL_STATUS_NATIVE_STATE_PROPAGATION 4u
#define XSTAR_THERMAL_STATUS_PERSISTENT_CONTEXT 8u
#define XSTAR_THERMAL_STATUS_CALLBACK_EVALUATION 16u
#define XSTAR_THERMAL_STATUS_CALLBACK_STATE_PROPAGATION 32u

#define XSTAR_THERMAL_ACTION_FINISH 0u
#define XSTAR_THERMAL_ACTION_EVALUATE 1u

#define XSTAR_THERMAL_EVENT_BEGIN 1u
#define XSTAR_THERMAL_EVENT_AFTER_EVALUATION 2u
#define XSTAR_THERMAL_EVENT_CHARGE_MULTIPLY 3u
#define XSTAR_THERMAL_EVENT_CHARGE_DIVIDE 4u
#define XSTAR_THERMAL_EVENT_CHARGE_SECANT 5u
#define XSTAR_THERMAL_EVENT_CHARGE_EXIT 6u
#define XSTAR_THERMAL_EVENT_TEMPERATURE_MULTIPLY 7u
#define XSTAR_THERMAL_EVENT_TEMPERATURE_DIVIDE 8u
#define XSTAR_THERMAL_EVENT_TEMPERATURE_SECANT 9u
#define XSTAR_THERMAL_EVENT_TEMPERATURE_STAGNATION 10u
#define XSTAR_THERMAL_EVENT_FINISH 11u

#define XSTAR_THERMAL_OK 0
#define XSTAR_THERMAL_ERROR_INVALID_ARGUMENT 1
#define XSTAR_THERMAL_ERROR_ABI_MISMATCH 2
#define XSTAR_THERMAL_ERROR_EVALUATOR 3
#define XSTAR_THERMAL_ERROR_NONFINITE 4
#define XSTAR_THERMAL_ERROR_CAPACITY 5
#define XSTAR_THERMAL_ERROR_INTERNAL 6

typedef struct xstar_thermal_context xstar_thermal_context;

typedef struct {
    uint32_t struct_size;
    uint32_t abi_version;
    uint32_t flags;
    uint32_t reserved0;
    double temperature_t4;
    double radius_cm;
    double covering_fraction;
    double zone_thickness_cm;
    double electron_fraction_xee;
    double hydrogen_density_cm3;
    double *epi_eV;
    double *bremsa;
    double *opakc;
    double *opakcont;
    double *flinel;
    double *brcems;
    size_t ncn2;
    double *zrems;
    const double *zremso;
    size_t zrems_count;
    double *elum;
    const double *elumo;
    const double *rcem;
    size_t n_lines;
    double *elumab;
    const double *elumabo;
    const double *cemab;
    size_t n_continua;
    const double *rccemis;
    size_t rccemis_count;
} xstar_heatt_workspace_v1;

typedef struct {
    int64_t record;
    int32_t rate_type;
    int32_t reserved0;
    double wavelength_angstrom;
} xstar_heatt_line_v1;

typedef struct {
    int64_t record;
    int32_t continuum_index_one_based;
    int32_t destination_level;
    uint32_t active;
    uint32_t reserved0;
} xstar_heatt_rrc_v1;

typedef struct {
    uint32_t struct_size;
    uint32_t abi_version;
    uint32_t status_flags;
    uint32_t reserved0;
    uint64_t calls;
    uint64_t continuum_bins;
    uint64_t line_records;
    uint64_t rrc_records;
    uint64_t state_commits;
    double continuum_seconds;
    double line_seconds;
    double rrc_seconds;
    double commit_seconds;
    double fpr2;
    double continuum_net_integral;
    double continuum_positive_integral;
    double pre_compton_heating;
    double pre_compton_cooling;
    double bremsstrahlung_integral;
} xstar_heatt_stats_v1;

typedef struct {
    uint32_t struct_size;
    uint32_t abi_version;
    int32_t nlim;
    int32_t maximum_evaluations;
    double tinf_t4;
    double charge_tolerance;
    double thermal_tolerance;
    double temperature_stagnation_tolerance;
} xstar_dsec_config_v1;

typedef struct {
    uint32_t struct_size;
    uint32_t abi_version;
    uint32_t flags;
    uint32_t reserved0;
    double temperature_t4;
    double electron_fraction_xee;
    double hydrogen_density_cm3;
    uint64_t state_generation;
} xstar_thermal_state_v1;

typedef struct {
    uint32_t struct_size;
    uint32_t abi_version;
    uint32_t flags;
    uint32_t reserved0;
    double hmctot;
    double elcter;
    double temperature_t4;
    double electron_fraction_xee;
    double hydrogen_density_cm3;
    uint64_t state_generation;
} xstar_thermal_evaluation_v1;

typedef struct {
    uint32_t event_code;
    uint32_t evaluation_index;
    int32_t ntotit;
    int32_t nnt;
    int32_t nntt;
    int32_t nnx;
    int32_t nnxx;
    int32_t lnerr;
    double temperature_t4;
    double electron_fraction_xee;
    double hmctot;
    double elcter;
    double normalized_charge_residual;
    double temperature_stagnation_metric;
} xstar_thermal_trace_event_v1;

typedef struct {
    uint32_t struct_size;
    uint32_t abi_version;
    uint32_t status_flags;
    uint32_t reserved0;
    int32_t lnerr;
    int32_t ntotit;
    int32_t temperature_iterations;
    int32_t temperature_attempts;
    uint32_t charge_converged;
    uint32_t thermal_converged;
    uint32_t prefix_terminated;
    uint32_t reserved1;
    uint64_t evaluations_requested;
    uint64_t evaluations_completed;
    uint64_t state_commits;
    double orchestration_seconds;
    double callback_seconds;
    double final_hmctot;
    double final_elcter;
    double final_charge_residual;
    double final_temperature_t4;
    double final_electron_fraction_xee;
    double final_temperature_stagnation_metric;
} xstar_dsec_stats_v1;

typedef int (*xstar_thermal_evaluator_fn_v1)(
    void *user_data,
    const xstar_thermal_state_v1 *trial_state,
    xstar_thermal_evaluation_v1 *evaluation,
    char *error,
    size_t error_size);

uint32_t xstar_thermal_engine_abi_version(void);
const char *xstar_thermal_engine_backend_name(void);
uint32_t xstar_thermal_engine_feature_flags(void);

void xstar_heatt_workspace_init_v1(xstar_heatt_workspace_v1 *workspace);
void xstar_heatt_stats_init_v1(xstar_heatt_stats_v1 *stats);
void xstar_dsec_config_init_v1(xstar_dsec_config_v1 *config);
void xstar_thermal_state_init_v1(xstar_thermal_state_v1 *state);
void xstar_thermal_evaluation_init_v1(xstar_thermal_evaluation_v1 *evaluation);
void xstar_dsec_stats_init_v1(xstar_dsec_stats_v1 *stats);

int xstar_thermal_context_create_v1(
    xstar_thermal_context **out_context,
    char *error,
    size_t error_size);
void xstar_thermal_context_destroy(xstar_thermal_context *context);
int xstar_thermal_context_reset_v1(
    xstar_thermal_context *context,
    char *error,
    size_t error_size);

int xstar_thermal_apply_heatt_v1(
    xstar_thermal_context *context,
    xstar_heatt_workspace_v1 *workspace,
    const xstar_heatt_line_v1 *lines,
    size_t line_count,
    const xstar_heatt_rrc_v1 *rrcs,
    size_t rrc_count,
    xstar_heatt_stats_v1 *stats,
    char *error,
    size_t error_size);

int xstar_thermal_run_evaluation_loop_v1(
    xstar_thermal_context *context,
    const xstar_dsec_config_v1 *config,
    xstar_thermal_state_v1 *state,
    xstar_thermal_evaluator_fn_v1 evaluator,
    void *user_data,
    xstar_thermal_trace_event_v1 *trace,
    size_t trace_capacity,
    size_t *trace_count,
    xstar_dsec_stats_v1 *stats,
    char *error,
    size_t error_size);

#ifdef __cplusplus
}
#endif

#endif
