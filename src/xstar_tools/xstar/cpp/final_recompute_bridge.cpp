#include "xstar_final_recompute_bridge.h"
#include "xstar_atdb_runtime.hpp"
#include "xstar_fixed_state_engine.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
void copy_message(char* dst, size_t n, const std::string& text) {
    if (!dst || n == 0u) return;
    const size_t k = std::min(n - 1u, text.size());
    std::memcpy(dst, text.data(), k);
    dst[k] = '\0';
}
void copy_output_message(xstar_final_recompute_output_v1* out, const std::string& text) {
    if (!out) return;
    copy_message(out->message, sizeof(out->message), text);
}
void require(bool value, const char* text) { if (!value) throw std::runtime_error(text); }

class ScopedEnvironment {
public:
    ScopedEnvironment(const char* key, const char* value) : key_(key) {
        if (const char* current = std::getenv(key)) { had_value_ = true; old_value_ = current; }
        ::setenv(key, value, 1);
    }
    ~ScopedEnvironment() {
        if (had_value_) ::setenv(key_.c_str(), old_value_.c_str(), 1);
        else ::unsetenv(key_.c_str());
    }
    ScopedEnvironment(const ScopedEnvironment&) = delete;
    ScopedEnvironment& operator=(const ScopedEnvironment&) = delete;
private:
    std::string key_;
    std::string old_value_;
    bool had_value_ = false;
};
}

extern "C" uint32_t xstar_final_recompute_bridge_abi_version(void) {
    return XSTAR_FINAL_RECOMPUTE_ABI_VERSION;
}
extern "C" const char* xstar_final_recompute_bridge_backend_name(void) {
    return "xstar_final_zero_thickness_fixed_state_bridge_v0648101";
}
extern "C" int xstar_final_recompute_input_init_v1(xstar_final_recompute_input_v1* input) {
    if (!input) return 1;
    std::memset(input, 0, sizeof(*input));
    input->struct_size = sizeof(*input);
    input->abi_version = XSTAR_FINAL_RECOMPUTE_ABI_VERSION;
    return 0;
}
extern "C" int xstar_final_recompute_output_init_v1(xstar_final_recompute_output_v1* output) {
    if (!output) return 1;
    std::memset(output, 0, sizeof(*output));
    output->struct_size = sizeof(*output);
    output->abi_version = XSTAR_FINAL_RECOMPUTE_ABI_VERSION;
    return 0;
}

extern "C" int xstar_final_recompute_run_v1(
    const xstar_final_recompute_input_v1* in,
    xstar_final_recompute_output_v1* out,
    char* message,
    size_t message_size) {
    try {
        require(in && out, "null final-recompute input/output");
        require(in->struct_size >= sizeof(*in) && out->struct_size >= sizeof(*out), "final-recompute struct size mismatch");
        require(in->abi_version == XSTAR_FINAL_RECOMPUTE_ABI_VERSION && out->abi_version == XSTAR_FINAL_RECOMPUTE_ABI_VERSION,
                "final-recompute ABI mismatch");
        require(in->atdb_path && *in->atdb_path, "missing atdb path");
        require(in->radiation_energy_ev && in->incident_flux && in->dsec_bremsa && in->radiation_bin_count > 1u,
                "missing radiation arrays");
        require(in->global_xilevg && in->global_bilevg && in->global_rnisg && in->global_level_count > 0u,
                "missing global level workspaces");

        xstar_atdb_runtime::ProductionParameters params;
        params.density_cm3 = in->hydrogen_density_cm3;
        params.temperature_k = in->temperature_k;
        params.covering_fraction = in->dsec_covering_fraction;
        params.emission_multiplier = in->emission_covering_fraction;
        params.turbulent_velocity_km_s = in->turbulent_velocity_km_s;
        for (size_t i = 0; i < in->abundance_count; ++i) {
            const double value = in->abundances_by_z ? in->abundances_by_z[i] : 0.0;
            if (std::isfinite(value) && value > 0.0) params.abundances_by_z[static_cast<int>(i + 1u)] = value;
        }
        auto program = xstar_atdb_runtime::lower_atdb_in_memory(std::filesystem::path(in->atdb_path), params);
        auto bundle = program.bundle();
        xstar_fixed_state_context* raw_context = nullptr;
        std::array<char,XSTAR_FIXED_STATE_MESSAGE_SIZE> fixed_message{};
        int rc = xstar_fixed_state_context_create_from_bundle_v1(&bundle, &raw_context, fixed_message.data(), fixed_message.size());
        if (rc != 0 || !raw_context) throw std::runtime_error(std::string("fixed context creation failed: ") + fixed_message.data());
        std::unique_ptr<xstar_fixed_state_context, decltype(&xstar_fixed_state_context_destroy)> context(raw_context, &xstar_fixed_state_context_destroy);

        if (in->line_tau_in && in->line_tau_out && in->line_tau_count > 0u) {
            rc = xstar_fixed_state_context_set_runtime_line_tau_v1(context.get(), in->line_tau_in, in->line_tau_out,
                                                                   in->line_tau_count, fixed_message.data(), fixed_message.size());
            if (rc != 0) throw std::runtime_error(std::string("line tau binding failed: ") + fixed_message.data());
        }

        xstar_fixed_state_input_v1 input{};
        xstar_fixed_state_input_init_v1(&input);
        input.temperature_k = in->temperature_k;
        input.electron_density_cm3 = in->electron_density_cm3;
        input.hydrogen_density_cm3 = in->hydrogen_density_cm3;
        input.neutral_h_density_cm3 = in->neutral_h_density_cm3;
        input.ionized_h_density_cm3 = in->ionized_h_density_cm3;
        input.electron_fraction_xee = in->electron_fraction_xee;
        input.covering_fraction = in->emission_covering_fraction;
        input.turbulent_velocity_km_s = in->turbulent_velocity_km_s;
        input.radiation_energy_ev = in->radiation_energy_ev;
        input.radiation_flux = in->incident_flux;
        input.radiation_bin_count = in->radiation_bin_count;
        input.dsec_radiation_energy_ev = in->radiation_energy_ev;
        input.dsec_bremsa = in->dsec_bremsa;
        input.dsec_radiation_bin_count = in->radiation_bin_count;
        input.continuum_tau_in = in->continuum_tau_in;
        input.continuum_tau_out = in->continuum_tau_out;
        input.continuum_tau_count = in->continuum_tau_count;
        input.dsec_covering_fraction = in->dsec_covering_fraction;
        input.global_xilevg = in->global_xilevg;
        input.global_bilevg = in->global_bilevg;
        input.global_rnisg = in->global_rnisg;
        input.global_level_count = in->global_level_count;
        input.runtime_state_flags = XSTAR_FIXED_RUNTIME_STATE_GLOBAL_LEVEL_WORKSPACES |
                                    XSTAR_FIXED_RUNTIME_STATE_DSEC_COVERING_FRACTION |
                                    XSTAR_FIXED_RUNTIME_STATE_REPEATED_HYDROGEN_SOURCE_STATE |
                                    XSTAR_FIXED_RUNTIME_STATE_LINE_TAU_ACTIVE;

        require(out->populations && out->populations_capacity >= program.rows.size(), "population output capacity too small");
        std::vector<double> spectrum(in->radiation_bin_count, 0.0), opacity(in->radiation_bin_count, 0.0);
        xstar_fixed_state_output_v1 fixed_out{};
        xstar_fixed_state_output_init_v1(&fixed_out);
        fixed_out.populations = out->populations; fixed_out.populations_capacity = out->populations_capacity;
        fixed_out.spectrum = spectrum.data(); fixed_out.spectrum_capacity = spectrum.size();
        fixed_out.opacity = opacity.data(); fixed_out.opacity_capacity = opacity.size();

        xstar_fixed_source_workspace_output_v1 source{};
        xstar_fixed_source_workspace_output_init_v1(&source);
        source.lte_populations = out->lte_populations; source.lte_populations_capacity = out->lte_populations_capacity;
        source.rcem = out->rcem; source.rcem_capacity = out->rcem_capacity;
        source.oplin = out->oplin; source.oplin_capacity = out->oplin_capacity;
        source.cemab = out->cemab; source.cemab_capacity = out->cemab_capacity;
        source.cabab = out->cabab; source.cabab_capacity = out->cabab_capacity;
        source.opakab = out->opakab; source.opakab_capacity = out->opakab_capacity;
        source.rccemis = out->rccemis; source.rccemis_capacity = out->rccemis_capacity;
        source.opakc = out->opakc; source.opakc_capacity = out->opakc_capacity;
        source.opakcont = out->opakcont; source.opakcont_capacity = out->opakcont_capacity;
        source.fline = out->fline; source.fline_capacity = out->fline_capacity;
        source.flinel = out->flinel; source.flinel_capacity = out->flinel_capacity;

        xstar_fixed_state_stats_v1 stats{};
        xstar_fixed_state_stats_init_v1(&stats);
        ScopedEnvironment source_sequence("XSTAR_NATIVE_SOURCE_SEQUENCE", "62");
        rc = xstar_fixed_state_run_with_source_workspaces_v1(context.get(), &input, &fixed_out, &source, &stats,
                                                             fixed_message.data(), fixed_message.size());
        if (rc != 0) throw std::runtime_error(std::string("native final fixed-state run failed: ") + fixed_message.data());

        xstar_fixed_state_thermal_components_v1 thermal{};
        thermal.struct_size = sizeof(thermal);
        thermal.abi_version = XSTAR_FIXED_STATE_ENGINE_ABI_VERSION;
        rc = xstar_fixed_state_get_last_thermal_components_v1(context.get(), &thermal, fixed_message.data(), fixed_message.size());
        if (rc != 0) throw std::runtime_error(std::string("thermal component fetch failed: ") + fixed_message.data());

        if (out->brcems && out->brcems_capacity > 0u) std::fill(out->brcems, out->brcems + out->brcems_capacity, 0.0);
        xstar_fixed_state_product_diagnostic_counts_v1 counts{};
        xstar_fixed_state_product_diagnostic_counts_init_v1(&counts);
        rc = xstar_fixed_state_get_last_product_diagnostic_counts_v1(context.get(), &counts, fixed_message.data(), fixed_message.size());
        if (rc != 0) throw std::runtime_error(std::string("product diagnostic count fetch failed: ") + fixed_message.data());
        std::vector<xstar_fixed_continuum_product_diagnostic_v1> continuum_rows(counts.continuum_count);
        size_t continuum_count = 0u;
        if (!continuum_rows.empty()) {
            rc = xstar_fixed_state_get_last_continuum_product_diagnostics_v1(context.get(), continuum_rows.data(), continuum_rows.size(),
                                                                             &continuum_count, fixed_message.data(), fixed_message.size());
            if (rc != 0) throw std::runtime_error(std::string("continuum diagnostic fetch failed: ") + fixed_message.data());
            for (size_t i = 0; i < continuum_count; ++i) {
                const int bin = continuum_rows[i].full_bin_one_based;
                if (bin >= 1 && static_cast<size_t>(bin) <= out->brcems_capacity) out->brcems[static_cast<size_t>(bin - 1)] = continuum_rows[i].brcems;
            }
        }

        out->element_heating = fixed_out.element_heating;
        out->element_cooling = fixed_out.element_cooling;
        out->continuum_heating = fixed_out.continuum_heating;
        out->continuum_cooling = fixed_out.continuum_cooling;
        out->total_heating = fixed_out.total_heating;
        out->total_cooling = fixed_out.total_cooling;
        out->hmctot = fixed_out.hmctot;
        out->computed_electron_fraction = fixed_out.electron_fraction_xee;
        out->charge_residual = fixed_out.elcter;
        out->hydrogen_heating = thermal.hydrogen_heating;
        out->hydrogen_cooling = thermal.hydrogen_cooling;
        out->helium_heating = thermal.helium_heating;
        out->helium_cooling = thermal.helium_cooling;
        out->magnesium_heating = thermal.magnesium_heating;
        out->magnesium_cooling = thermal.magnesium_cooling;
        out->compton_heating = thermal.compton_heating;
        out->compton_cooling = thermal.compton_cooling;
        out->free_free_heating = thermal.free_free_heating;
        out->bremsstrahlung_cooling = thermal.bremsstrahlung_cooling;
        out->populations_count = fixed_out.populations_count;
        out->lte_populations_count = source.lte_populations_count;
        out->rcem_count = source.rcem_count;
        out->oplin_count = source.oplin_count;
        out->cemab_count = source.cemab_count;
        out->cabab_count = source.cabab_count;
        out->opakab_count = source.opakab_count;
        out->rccemis_count = source.rccemis_count;
        out->opakc_count = source.opakc_count;
        out->opakcont_count = source.opakcont_count;
        out->fline_count = source.fline_count;
        out->flinel_count = source.flinel_count;
        out->brcems_count = std::min(out->brcems_capacity, in->radiation_bin_count);
        out->traversal_seconds = stats.traversal_seconds;
        out->rate_seconds = stats.rate_seconds;
        out->element_seconds = stats.element_seconds;
        out->continuum_seconds = stats.continuum_seconds;
        out->spectral_seconds = stats.spectral_seconds;
        out->total_seconds = stats.total_seconds;
        const std::string ok = "native final zero-thickness fixed-state bridge complete";
        copy_output_message(out, ok); copy_message(message, message_size, ok);
        return 0;
    } catch (const std::exception& exc) {
        copy_output_message(out, exc.what()); copy_message(message, message_size, exc.what());
        return 1;
    }
}
