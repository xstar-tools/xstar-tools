#ifndef XSTAR_ZONE_BACKEND_BRIDGE_H
#define XSTAR_ZONE_BACKEND_BRIDGE_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define XSTAR_ZONE_BACKEND_ABI_VERSION 60481020u
#define XSTAR_ZONE_BACKEND_MESSAGE_SIZE 512u

typedef struct xstar_zone_backend_context xstar_zone_backend_context;

typedef struct {
    uint32_t struct_size;
    uint32_t abi_version;
    const char* atdb_path;
    const double* abundances_by_z;
    size_t abundance_count;
    double emission_covering_fraction;
    double dsec_covering_fraction;
    double turbulent_velocity_km_s;
} xstar_zone_backend_context_config_v1;

typedef struct {
    uint32_t struct_size;
    uint32_t abi_version;
    int32_t zone_index;
    int32_t nlim;
    double tinf_t4;
    double temperature_k;
    double electron_fraction_xee;
    double hydrogen_density_cm3;
    double neutral_h_density_cm3;
    double ionized_h_density_cm3;
    const double* radiation_energy_ev;
    const double* incident_flux;
    const double* dsec_bremsa;
    size_t radiation_bin_count;
    const double* continuum_tau_in;
    const double* continuum_tau_out;
    size_t continuum_tau_count;
    const double* line_tau_in;
    const double* line_tau_out;
    size_t line_tau_count;
    const double* global_xilevg;
    const double* global_bilevg;
    const double* global_rnisg;
    size_t global_level_count;
} xstar_zone_backend_input_v1;

typedef struct {
    uint32_t struct_size;
    uint32_t abi_version;
    int32_t lnerr;
    int32_t ntotit;
    int32_t temperature_iterations;
    int32_t temperature_attempts;
    uint32_t charge_converged;
    uint32_t thermal_converged;
    uint32_t prefix_terminated;
    uint32_t reserved0;
    double final_temperature_t4;
    double final_electron_fraction_xee;
    double final_hmctot;
    double final_elcter;
    double* global_xilevg;
    size_t global_xilevg_capacity;
    size_t global_xilevg_count;
    double* global_bilevg;
    size_t global_bilevg_capacity;
    size_t global_bilevg_count;
    double* global_rnisg;
    size_t global_rnisg_capacity;
    size_t global_rnisg_count;
    double fixed_state_seconds;
    double dsec_orchestration_seconds;
    double total_seconds;
    char message[XSTAR_ZONE_BACKEND_MESSAGE_SIZE];
} xstar_zone_backend_output_v1;

uint32_t xstar_zone_backend_bridge_abi_version(void);
const char* xstar_zone_backend_bridge_backend_name(void);
int xstar_zone_backend_context_config_init_v1(xstar_zone_backend_context_config_v1* config);
int xstar_zone_backend_input_init_v1(xstar_zone_backend_input_v1* input);
int xstar_zone_backend_output_init_v1(xstar_zone_backend_output_v1* output);
int xstar_zone_backend_context_create_v1(
    const xstar_zone_backend_context_config_v1* config,
    xstar_zone_backend_context** context,
    char* message,
    size_t message_size);
void xstar_zone_backend_context_destroy_v1(xstar_zone_backend_context* context);
int xstar_zone_backend_run_v1(
    xstar_zone_backend_context* context,
    const xstar_zone_backend_input_v1* input,
    xstar_zone_backend_output_v1* output,
    char* message,
    size_t message_size);

#ifdef __cplusplus
}
#endif
#endif
