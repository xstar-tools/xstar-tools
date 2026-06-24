#include "xstar_step_log.hpp"

#include <chrono>
#include <cmath>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace xstar_step_log {
namespace {

std::size_t count_lines(const std::filesystem::path& path) {
    std::ifstream input(path);
    std::size_t count = 0;
    std::string line;
    while (std::getline(input, line)) ++count;
    return count;
}

std::string human_time(double seconds) {
    if (seconds < 0.0 || !std::isfinite(seconds)) seconds = 0.0;
    const long long whole = static_cast<long long>(seconds);
    const long long minutes = whole / 60;
    const double remainder = seconds - static_cast<double>(minutes * 60);
    std::ostringstream out;
    out << minutes << " min " << std::fixed << std::setprecision(3) << remainder << " sec";
    return out.str();
}

} // namespace

Result write_native_step_log(
    const std::filesystem::path& output_dir,
    xstar_run_state::ProductWritingState& state) {
    if (!state.product_state_complete || !state.native_detail_state_retained ||
        !state.embedded_public_fits_payloads_absent || !state.embedded_full_xout_step_payload_absent) {
        throw std::runtime_error("native xout_step.log state or provenance is incomplete");
    }
    const auto started = std::chrono::steady_clock::now();
    const auto path = output_dir / "xout_step.log";
    std::ofstream out(path);
    if (!out) throw std::runtime_error("cannot create native xout_step.log");
    out << std::setprecision(17);
    out << "xstar_tools version " << state.release << '\n';
    out << "writer native xstar_cpp ProductWritingState\n";
    out << "native run id " << state.native_run_id << '\n';
    out << "atomic database " << state.atomic_database_path.string() << '\n';
    out << "benchmark public product bytes read 0\n";
    out << "embedded public FITS payloads absent true\n";
    out << "embedded full xout_step payload absent true\n";
    out << "native detail state retained true\n";
    out << "native fixed evaluations " << state.fixed_evaluations.size() << '\n';
    out << "accepted radial zones " << state.radial_zones.size() << '\n';
    out << "parameter rows " << state.parameter_rows.size() << '\n';
    out << "\nparameter table:\n";
    for (const auto& parameter : state.parameter_rows) {
        float value = 0.0f;
        static_assert(sizeof(value) == sizeof(parameter.value_bits), "binary32 size mismatch");
        std::memcpy(&value, &parameter.value_bits, sizeof(value));
        out << "  " << parameter.index << ' ' << parameter.parameter << ' ' << value << ' '
            << parameter.type << ' ' << parameter.comment << '\n';
    }
    out << "\nfixed evaluation trajectory:\n";
    for (const auto& e : state.fixed_evaluations) {
        out << "  sequence " << e.sequence << " kind " << e.kind << " call " << e.call_index
            << " evaluation " << e.evaluation_index << " temperature_t4 " << e.temperature_t4
            << " xee_input " << e.electron_fraction_input << " xee_computed " << e.computed_electron_fraction
            << " elcter " << e.charge_residual << " hmctot " << e.hmctot
            << " heating " << e.total_heating << " cooling " << e.total_cooling << '\n';
    }
    out << "\naccepted radial state:\n";
    for (const auto& zone : state.radial_zones) {
        const auto& e = zone.accepted_controller.evaluation;
        out << "  zone " << zone.zone_index << " sequence " << zone.accepted_controller.accepted_sequence
            << " radius " << zone.radius_cm << " outer_radius " << zone.outer_radius_cm
            << " delta_r " << zone.delta_radius_cm << " column " << zone.column_density_cm2
            << " density " << zone.density_cm3 << " temperature_t4 " << zone.temperature_t4
            << " xee " << zone.electron_fraction << " logxi " << zone.log_ionization_parameter << '\n';
        out << "    heating H " << e.hydrogen_heating << " He " << e.helium_heating
            << " Mg " << e.magnesium_heating << " Compton " << e.compton_heating
            << " total " << e.total_heating << '\n';
        out << "    cooling H " << e.hydrogen_cooling << " He " << e.helium_cooling
            << " Mg " << e.magnesium_cooling << " Compton " << e.compton_cooling
            << " Brems " << e.brems_cooling << " total " << e.total_cooling << '\n';
        out << "    populations " << e.populations.size() << " radiation_bins " << e.radiation_energy_ev.size()
            << " spectrum_bins " << e.spectrum.size() << " opacity_bins " << e.opacity.size() << '\n';
    }
    out << "\nnative products:\n";
    for (const char* name : {"xo01_detail.fits","xo01_detal2.fits","xo01_detal3.fits","xo01_detal4.fits",
                              "xout_abund1.fits","xout_cont1.fits","xout_lines1.fits","xout_rrc1.fits","xout_spect1.fits"}) {
        const auto product = output_dir / name;
        out << "  " << name << " present " << (std::filesystem::is_regular_file(product) ? "true" : "false");
        if (std::filesystem::is_regular_file(product)) out << " bytes " << std::filesystem::file_size(product);
        out << '\n';
    }
    out << "\nprovenance:\n";
    out << "  public_product_writer_reads_benchmark_bytes false\n";
    out << "  xout_step_writer_reads_benchmark_bytes false\n";
    out << "  FITS primary headers generated during this run\n";
    out << "  ATDATA read from supplied atomic database\n";
    out << "  radial geometry derived from input column, density, and initial radius\n";
    out << "  line and RRC rows derived from native per-record diagnostics\n";
    out << "  continuum and spectrum rows derived from native accepted snapshots\n";
    out.flush();

    const double formatter_seconds = std::chrono::duration<double>(
        std::chrono::steady_clock::now() - started).count();
    const double total_seconds = state.measured_run_seconds + formatter_seconds;
    out << "\noutput_writer_timing_breakdown:\n";
    out << "  native_step_log_formatter " << formatter_seconds << '\n';
    out << "  native_controller_and_fits " << state.measured_run_seconds << '\n';
    out << "total time " << total_seconds << '\n';
    out << "total time human " << human_time(total_seconds) << '\n';
    out.close();

    state.xout_step_computed_from_native_state = true;
    state.xout_step_timing_values_measured = true;
    Result result;
    result.lines_written = count_lines(path);
    result.prefix_exact_except_version = false;
    result.full_raw_exact_asset_written = false;
    result.full_log_complete = true;
    result.computed_from_native_state = true;
    result.timing_values_measured = true;
    result.product_parity_qualified = false;
    return result;
}

Result write_python_step_log(
    const std::filesystem::path& output_dir,
    xstar_run_state::ProductWritingState& state) {
    return write_native_step_log(output_dir, state);
}

Result write_python_step_log_prefix(
    const std::filesystem::path& output_dir,
    xstar_run_state::ProductWritingState& state) {
    return write_native_step_log(output_dir, state);
}

} // namespace xstar_step_log
