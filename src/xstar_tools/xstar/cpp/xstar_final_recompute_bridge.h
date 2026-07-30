#ifndef XSTAR_FINAL_RECOMPUTE_BRIDGE_H
#define XSTAR_FINAL_RECOMPUTE_BRIDGE_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define XSTAR_FINAL_RECOMPUTE_ABI_VERSION 60481231u
#define XSTAR_FINAL_RECOMPUTE_MESSAGE_SIZE 512u

typedef struct xstar_final_recompute_input_v1 {
    uint32_t struct_size;
    uint32_t abi_version;
    const char* atdb_path;
    double temperature_k;
    double electron_density_cm3;
    double hydrogen_density_cm3;
    double neutral_h_density_cm3;
    double ionized_h_density_cm3;
    double electron_fraction_xee;
    double emission_covering_fraction;
    double dsec_covering_fraction;
    double turbulent_velocity_km_s;
    const double* abundances_by_z;
    size_t abundance_count;
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
    const double* source_leveltemp_energy_ev;
    size_t source_leveltemp_count;
} xstar_final_recompute_input_v1;

typedef struct xstar_final_recompute_output_v1 {
    uint32_t struct_size;
    uint32_t abi_version;
    double element_heating;
    double element_cooling;
    double continuum_heating;
    double continuum_cooling;
    double total_heating;
    double total_cooling;
    double hmctot;
    double computed_electron_fraction;
    double charge_residual;
    double hydrogen_heating;
    double hydrogen_cooling;
    double helium_heating;
    double helium_cooling;
    double magnesium_heating;
    double magnesium_cooling;
    double compton_heating;
    double compton_cooling;
    double free_free_heating;
    double bremsstrahlung_cooling;
    double* populations;
    size_t populations_capacity;
    size_t populations_count;
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
    double* brcems;
    size_t brcems_capacity;
    size_t brcems_count;
    double traversal_seconds;
    double rate_seconds;
    double element_seconds;
    double continuum_seconds;
    double spectral_seconds;
    double total_seconds;
    char message[XSTAR_FINAL_RECOMPUTE_MESSAGE_SIZE];
} xstar_final_recompute_output_v1;

uint32_t xstar_final_recompute_bridge_abi_version(void);
const char* xstar_final_recompute_bridge_backend_name(void);
int xstar_final_recompute_input_init_v1(xstar_final_recompute_input_v1* input);
int xstar_final_recompute_output_init_v1(xstar_final_recompute_output_v1* output);
int xstar_final_recompute_run_v1(
    const xstar_final_recompute_input_v1* input,
    xstar_final_recompute_output_v1* output,
    char* message,
    size_t message_size);

#ifdef __cplusplus
}
#endif
#endif
