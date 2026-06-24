#include "xstar_run_state.hpp"

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <regex>
#include <sstream>
#include <stdexcept>

namespace xstar_run_state {
namespace {

std::string json_escape(const std::string& value) {
    std::string out;
    out.reserve(value.size() + 8);
    for (unsigned char ch : value) {
        switch (ch) {
            case '\\': out += "\\\\"; break;
            case '"': out += "\\\""; break;
            case '\n': out += "\\n"; break;
            case '\r': out += "\\r"; break;
            case '\t': out += "\\t"; break;
            default: out += static_cast<char>(ch); break;
        }
    }
    return out;
}

std::string read_text(const std::filesystem::path& path) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open native product input: " + path.string());
    std::ostringstream out;
    out << input.rdbuf();
    return out.str();
}

std::string json_scalar_text(const std::string& text, const std::string& key, const std::string& fallback = "") {
    const std::regex quoted("\\\"" + key + "\\\"\\s*:\\s*\\\"([^\\\"]*)\\\"");
    std::smatch match;
    if (std::regex_search(text, match, quoted)) return match[1].str();
    const std::regex bare("\\\"" + key + "\\\"\\s*:\\s*([-+0-9.eE]+|true|false|null)");
    if (std::regex_search(text, match, bare)) return match[1].str();
    return fallback;
}

double json_number(const std::string& text, const std::string& key, double fallback) {
    const std::string value = json_scalar_text(text, key);
    if (value.empty()) return fallback;
    try { return std::stod(value); } catch (...) { return fallback; }
}

std::uint32_t float_bits(float value) {
    std::uint32_t bits = 0;
    static_assert(sizeof(bits) == sizeof(value), "binary32 size mismatch");
    std::memcpy(&bits, &value, sizeof(bits));
    return bits;
}

bool finite_vector(const std::vector<double>& values) {
    return std::all_of(values.begin(), values.end(), [](double value) {
        return std::isfinite(value);
    });
}

void derive_output_grid_continuum_depths(std::vector<RadialZoneState>& zones) {
    if (zones.size() != 5) {
        throw std::runtime_error("native continuum-depth reduction requires five accepted boundary states");
    }
    const std::size_t bins = zones.front().accepted_controller.evaluation.radiation_energy_ev.size();
    if (bins == 0) {
        throw std::runtime_error("native continuum-depth reduction has an empty radiation grid");
    }
    for (const auto& zone : zones) {
        const auto& evaluation = zone.accepted_controller.evaluation;
        if (evaluation.radiation_energy_ev.size() != bins ||
            evaluation.radiation_flux.size() != bins ||
            evaluation.continuum_spectrum.size() != bins ||
            evaluation.spectrum.size() != bins || evaluation.opacity.size() != bins) {
            throw std::runtime_error("accepted native snapshots do not share one complete output radiation grid");
        }
        if (evaluation.source_continuum_tau_workspace_count == 0) {
            throw std::runtime_error("accepted native snapshot did not consume the source continuum workspace");
        }
        if (!finite_vector(evaluation.radiation_energy_ev) || !finite_vector(evaluation.radiation_flux) ||
            !finite_vector(evaluation.continuum_spectrum) || !finite_vector(evaluation.spectrum) ||
            !finite_vector(evaluation.opacity)) {
            throw std::runtime_error("accepted native snapshot contains non-finite output-grid state");
        }
        const auto& reference_grid = zones.front().accepted_controller.evaluation.radiation_energy_ev;
        if (!std::equal(evaluation.radiation_energy_ev.begin(), evaluation.radiation_energy_ev.end(),
                        reference_grid.begin())) {
            throw std::runtime_error("accepted native snapshots use different output radiation grids");
        }
    }

    for (auto& zone : zones) {
        auto& evaluation = zone.accepted_controller.evaluation;
        evaluation.continuum_tau_in.assign(bins, 0.0);
        evaluation.continuum_tau_out.assign(bins, 0.0);
    }

    // The five retained controller states represent radial boundaries, hence
    // four physical intervals.  Integrate the native per-bin opacity across
    // each interval with a trapezoidal rule.  This constructs dpthc on the
    // output grid from live C++ state and never truncates or reinterprets the
    // 301301-value source workspace.
    for (std::size_t bin = 0; bin < bins; ++bin) {
        std::array<double,4> interval_tau{};
        for (std::size_t interval = 0; interval < 4; ++interval) {
            const auto& left = zones[interval];
            const auto& right = zones[interval + 1];
            const double width = std::max(0.0, right.radius_cm - left.radius_cm);
            const double opacity_left = left.accepted_controller.evaluation.opacity[bin];
            const double opacity_right = right.accepted_controller.evaluation.opacity[bin];
            interval_tau[interval] = 0.5 * (opacity_left + opacity_right) * width;
            if (!std::isfinite(interval_tau[interval])) {
                throw std::runtime_error("native continuum-depth integration produced a non-finite value");
            }
        }
        double forward = 0.0;
        zones[0].accepted_controller.evaluation.continuum_tau_in[bin] = 0.0;
        for (std::size_t boundary = 1; boundary < zones.size(); ++boundary) {
            forward += interval_tau[boundary - 1];
            zones[boundary].accepted_controller.evaluation.continuum_tau_in[bin] = forward;
        }
        double backward = 0.0;
        zones.back().accepted_controller.evaluation.continuum_tau_out[bin] = 0.0;
        for (std::size_t boundary = zones.size() - 1; boundary-- > 0;) {
            backward += interval_tau[boundary];
            zones[boundary].accepted_controller.evaluation.continuum_tau_out[bin] = backward;
        }
    }
}

std::string diagnostics_incomplete_reason(
    const std::filesystem::path& root,
    const std::vector<RadialZoneState>& zones) {
    if (!std::filesystem::is_directory(root)) return "native diagnostics directory is missing";
    if (zones.size() != 5) return "accepted radial-state count is not five";
    for (const auto& zone : zones) {
        std::ostringstream stem;
        stem << "evaluation_" << std::setw(4) << std::setfill('0')
             << zone.accepted_controller.accepted_sequence;
        const auto records = root / (stem.str() + "_records.csv");
        if (!std::filesystem::is_regular_file(records)) {
            return "record diagnostics missing for sequence " +
                std::to_string(zone.accepted_controller.accepted_sequence);
        }
        const auto& evaluation = zone.accepted_controller.evaluation;
        const std::size_t bins = evaluation.radiation_energy_ev.size();
        if (evaluation.populations.empty()) {
            return "population state missing for sequence " +
                std::to_string(zone.accepted_controller.accepted_sequence);
        }
        if (bins == 0 || evaluation.radiation_flux.size() != bins ||
            evaluation.continuum_spectrum.size() != bins || evaluation.spectrum.size() != bins ||
            evaluation.opacity.size() != bins || evaluation.continuum_tau_in.size() != bins ||
            evaluation.continuum_tau_out.size() != bins) {
            std::ostringstream detail;
            detail << "output-grid state incomplete for sequence "
                   << zone.accepted_controller.accepted_sequence
                   << " bins=" << bins
                   << " flux=" << evaluation.radiation_flux.size()
                   << " continuum=" << evaluation.continuum_spectrum.size()
                   << " spectrum=" << evaluation.spectrum.size()
                   << " opacity=" << evaluation.opacity.size()
                   << " tau_in=" << evaluation.continuum_tau_in.size()
                   << " tau_out=" << evaluation.continuum_tau_out.size()
                   << " source_tau_workspace=" << evaluation.source_continuum_tau_workspace_count;
            return detail.str();
        }
    }
    return {};
}

} // namespace

void prepare_native_product_state(
    WholeRunAccumulatedState& state,
    const std::filesystem::path& diagnostics_path) {
    if (state.radial_zones.size() != 5) {
        throw std::runtime_error("native product construction requires five accepted controller zones");
    }
    const std::string parameters = read_text(state.parameters_path);
    const double initial_radius = json_number(parameters, "initial_radius_cm", 1.0e17);
    const double density = json_number(parameters, "density", 1.0e8);
    const double total_column = json_number(parameters, "column", 1.0e20);
    const double logxi = json_number(parameters, "rlogxi", 0.0);
    const double input_pressure = json_number(parameters, "pressure", 0.0);
    const double total_thickness = density > 0.0 ? total_column / density : 0.0;
    const double shell_thickness = total_thickness / 4.0;

    for (std::size_t i = 0; i < state.radial_zones.size(); ++i) {
        auto& zone = state.radial_zones[i];
        const auto& evaluation = zone.accepted_controller.evaluation;
        zone.zone_index = i + 1;
        zone.pass_index = 1;
        zone.radius_cm = initial_radius + static_cast<double>(i) * shell_thickness;
        zone.outer_radius_cm = i < 4 ? zone.radius_cm + shell_thickness : zone.radius_cm;
        zone.delta_radius_cm = shell_thickness;
        zone.density_cm3 = density;
        zone.temperature_t4 = evaluation.temperature_t4;
        zone.electron_fraction = evaluation.computed_electron_fraction;
        zone.log_ionization_parameter = logxi;
        zone.ionization_parameter = logxi;
        zone.column_density_cm2 = total_column * static_cast<double>(i) / 4.0;
        zone.pressure_dyn_cm2 = input_pressure > 0.0
            ? input_pressure
            : density * evaluation.computed_electron_fraction * 1.380649e-16 * evaluation.temperature_t4 * 1.0e4;
        zone.provisional_from_controller = false;
    }

    state.abundance_radial_rows.clear();
    for (std::size_t i = 0; i < state.radial_zones.size(); ++i) {
        const auto& zone = state.radial_zones[i];
        const auto& evaluation = zone.accepted_controller.evaluation;
        AbundanceRadialRowState row;
        row.row_index = i + 1;
        row.radius_cm = zone.radius_cm;
        row.delta_radius_cm = zone.delta_radius_cm;
        row.log_ionization_parameter = zone.log_ionization_parameter;
        row.electron_fraction = zone.electron_fraction;
        row.density_cm3 = zone.density_cm3;
        row.pressure_dyn_cm2 = zone.pressure_dyn_cm2;
        row.temperature_t4 = zone.temperature_t4;
        const double scale = std::max(std::abs(evaluation.total_heating) + std::abs(evaluation.total_cooling), 1.0e-300);
        row.fractional_heat_error = std::abs(evaluation.hmctot) / scale;
        row.terminal_row = i + 1 == state.radial_zones.size();
        state.abundance_radial_rows.push_back(row);
    }

    state.parameter_rows.clear();
    const std::vector<std::string> keys = {
        "cfrac","column","density","emult","initial_radius_cm","lcdd","lcpres","loopcontrol",
        "lprint","lstep","lwrite","ncn2","niter","npass","nsteps","pressure","radexp","rlogxi",
        "rlrad38","spectun","taumax","temperature","temperature_k","trad","vturbi","xeemin",
        "habund","heabund","mgabund","critf"
    };
    std::uint16_t index = 1;
    for (const auto& key : keys) {
        const std::string value_text = json_scalar_text(parameters, key);
        if (value_text.empty()) continue;
        float value = 0.0f;
        try { value = static_cast<float>(std::stod(value_text)); } catch (...) { value = 0.0f; }
        ParameterRowState row;
        row.index = index++;
        row.parameter = key;
        row.value_bits = float_bits(value);
        row.type = "native";
        row.comment = "parsed from parameters.json";
        state.parameter_rows.push_back(std::move(row));
    }

    derive_output_grid_continuum_depths(state.radial_zones);
    state.continuum_depths_derived_from_native_opacity = true;

    state.product_schema_path.clear();
    state.native_diagnostics_path = diagnostics_path;
    const auto run_ticks = std::chrono::duration_cast<std::chrono::nanoseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();
    state.native_run_id = state.release + "-" + std::to_string(run_ticks);
    state.embedded_public_fits_payloads_absent = true;
    state.embedded_full_xout_step_payload_absent = true;
    state.product_schema_complete = true;
    state.radial_state_complete = true;
    const std::string diagnostic_error = diagnostics_incomplete_reason(diagnostics_path, state.radial_zones);
    state.native_detail_state_retained = diagnostic_error.empty();
    state.native_product_inputs_complete = state.native_detail_state_retained &&
        state.continuum_depths_derived_from_native_opacity &&
        state.embedded_public_fits_payloads_absent && state.embedded_full_xout_step_payload_absent;
    if (!state.native_detail_state_retained) {
        throw std::runtime_error("native detail-state diagnostics are incomplete: " + diagnostic_error);
    }
}

ProductWritingState build_product_writing_state(const WholeRunAccumulatedState& state) {
    ProductWritingState product;
    product.release = state.release;
    product.backend = state.backend;
    product.parameters_path = state.parameters_path;
    product.atomic_database_path = state.atomic_database_path;
    product.schema_path = state.product_schema_path;
    product.native_diagnostics_path = state.native_diagnostics_path;
    product.native_run_id = state.native_run_id;
    product.fixed_evaluations = state.fixed_evaluations;
    product.radial_zones = state.radial_zones;
    product.parameter_rows = state.parameter_rows;
    product.abundance_radial_rows = state.abundance_radial_rows;
    product.embedded_public_fits_payloads_absent = state.embedded_public_fits_payloads_absent;
    product.embedded_full_xout_step_payload_absent = state.embedded_full_xout_step_payload_absent;
    product.run_state_layers_distinct = true;
    product.product_schema_complete = state.product_schema_complete;
    product.radial_state_complete = state.radial_state_complete;
    product.native_detail_state_retained = state.native_detail_state_retained;
    product.continuum_depths_derived_from_native_opacity =
        state.continuum_depths_derived_from_native_opacity;
    product.native_product_inputs_complete = state.native_product_inputs_complete;
    product.product_state_complete = state.product_schema_complete && state.radial_state_complete &&
        state.native_detail_state_retained && state.continuum_depths_derived_from_native_opacity &&
        state.native_product_inputs_complete;
    product.product_parity_qualified = false;
    return product;
}

void write_run_state_manifest(
    const std::filesystem::path& path,
    const WholeRunAccumulatedState& whole,
    const ProductWritingState& product) {
    std::ofstream out(path);
    if (!out) throw std::runtime_error("cannot create run-state manifest: " + path.string());
    out << std::setprecision(17)
        << "{\n"
        << "  \"schema\": \"xstar-tools-v0648746254-native-product-state-v1\",\n"
        << "  \"release\": \"" << json_escape(whole.release) << "\",\n"
        << "  \"backend\": \"" << json_escape(whole.backend) << "\",\n"
        << "  \"parameters_path\": \"" << json_escape(whole.parameters_path.string()) << "\",\n"
        << "  \"atomic_database_path\": \"" << json_escape(whole.atomic_database_path.string()) << "\",\n"
        << "  \"native_case_path\": \"" << json_escape(whole.native_case_path.string()) << "\",\n"
        << "  \"native_diagnostics_path\": \"" << json_escape(product.native_diagnostics_path.string()) << "\",\n"
        << "  \"native_run_id\": \"" << json_escape(product.native_run_id) << "\",\n"
        << "  \"fixed_evaluations\": " << whole.fixed_evaluations.size() << ",\n"
        << "  \"accepted_controller_states\": " << whole.accepted_controller_states.size() << ",\n"
        << "  \"radial_zones\": " << whole.radial_zones.size() << ",\n"
        << "  \"native_detail_state_retained\": " << (product.native_detail_state_retained ? "true" : "false") << ",\n"
        << "  \"continuum_depths_derived_from_native_opacity\": "
        << (product.continuum_depths_derived_from_native_opacity ? "true" : "false") << ",\n"
        << "  \"embedded_public_fits_payloads_absent\": " << (product.embedded_public_fits_payloads_absent ? "true" : "false") << ",\n"
        << "  \"embedded_full_xout_step_payload_absent\": " << (product.embedded_full_xout_step_payload_absent ? "true" : "false") << ",\n"
        << "  \"public_product_runtime_reads_benchmark_bytes\": false,\n"
        << "  \"xout_step_runtime_reads_benchmark_bytes\": false,\n"
        << "  \"xout_abund1_computed_from_native_state\": " << (product.xout_abund1_computed_from_native_state ? "true" : "false") << ",\n"
        << "  \"xout_cont1_computed_from_native_state\": " << (product.xout_cont1_computed_from_native_state ? "true" : "false") << ",\n"
        << "  \"xout_lines1_computed_from_native_state\": " << (product.xout_lines1_computed_from_native_state ? "true" : "false") << ",\n"
        << "  \"xout_rrc1_computed_from_native_state\": " << (product.xout_rrc1_computed_from_native_state ? "true" : "false") << ",\n"
        << "  \"xout_spect1_computed_from_native_state\": " << (product.xout_spect1_computed_from_native_state ? "true" : "false") << ",\n"
        << "  \"xout_step_computed_from_native_state\": " << (product.xout_step_computed_from_native_state ? "true" : "false") << ",\n"
        << "  \"xout_step_timing_values_measured\": " << (product.xout_step_timing_values_measured ? "true" : "false") << ",\n"
        << "  \"product_state_complete\": " << (product.product_state_complete ? "true" : "false") << ",\n"
        << "  \"product_parity_qualified\": false,\n"
        << "  \"production_promotion_ready\": false\n"
        << "}\n";
}

} // namespace xstar_run_state
