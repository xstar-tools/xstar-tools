#include "xstar_step_log.hpp"

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include <fitsio.h>

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

void require_legacy_pprint_payload(const xstar_run_state::ProductWritingState& state) {
    // v17.25.32: allow a native compact step log while scientific product
    // families are still being repaired.  Oracle/public payload absence is
    // still mandatory and remains the hard provenance gate.
    if (!state.embedded_public_fits_payloads_absent ||
        !state.embedded_full_xout_step_payload_absent) {
        throw std::runtime_error("native xout_step.log anti-copy provenance is incomplete");
    }
    const bool legacy_body_available = state.legacy_pprint.complete() && !state.legacy_pprint.buffered_lines.empty();
    const bool true_native_equivalent_available =
        state.legacy_pprint.initialized_from_native_controller &&
        state.legacy_pprint.finalized_from_native_controller &&
        state.legacy_pprint.buffered_lines.empty();
    if (!(legacy_body_available || true_native_equivalent_available)) {
        throw std::runtime_error(
            "xout_step.log requires retained legacy/full xout_step body or a validated true native equivalent; "
            "scratch ProductWritingState log body is disabled");
    }
}

std::string read_atomic_data_version(const std::filesystem::path& atdb) {
    fitsfile* fptr = nullptr;
    int status = 0;
    fits_open_file(&fptr, atdb.c_str(), READONLY, &status);
    if (status != 0) return "unknown";
    char value[FLEN_VALUE]{};
    int read_status = 0;
    fits_read_key(fptr, TSTRING, const_cast<char*>("ATDATA"), value, nullptr, &read_status);
    if (read_status != 0) {
        read_status = 0;
        fits_read_key(fptr, TSTRING, const_cast<char*>("DATE"), value, nullptr, &read_status);
    }
    int close_status = 0;
    fits_close_file(fptr, &close_status);
    if (read_status != 0) return "unknown";
    return std::string(value);
}

std::string path_string_or_unknown(const std::filesystem::path& path) {
    const auto s = path.string();
    return s.empty() ? std::string("unknown") : s;
}

double real_from_bits(std::uint32_t bits) {
    float value = 0.0f;
    std::memcpy(&value, &bits, sizeof(value));
    return static_cast<double>(value);
}

std::string sci3(double value) {
    if (!std::isfinite(value)) value = 0.0;
    std::ostringstream out;
    out << std::uppercase << std::scientific << std::setprecision(3) << value;
    return out.str();
}

const xstar_run_state::ParameterRowState* parameter_by_name(
    const xstar_run_state::ProductWritingState& state,
    const std::string& name) {
    for (const auto& row : state.parameter_rows) {
        if (row.parameter == name) return &row;
    }
    return nullptr;
}

double real_parameter(
    const xstar_run_state::ProductWritingState& state,
    const std::string& name,
    double fallback = 0.0) {
    const auto* row = parameter_by_name(state, name);
    if (!row) return fallback;
    return real_from_bits(row->value_bits);
}

long long integer_parameter(
    const xstar_run_state::ProductWritingState& state,
    const std::string& name,
    long long fallback = 0) {
    return static_cast<long long>(std::llround(real_parameter(state, name, static_cast<double>(fallback))));
}

std::string string_parameter(
    const xstar_run_state::ProductWritingState& state,
    const std::string& name,
    const std::string& fallback = "") {
    const auto* row = parameter_by_name(state, name);
    if (!row) return fallback;
    return row->comment.empty() ? fallback : row->comment;
}

void append_legacy_style_input_block(std::ofstream& out,
                                     const xstar_run_state::ProductWritingState& state) {
    const double cfrac = real_parameter(state, "cfrac", 1.0);
    const double temperature = real_parameter(state, "temperature", 100.0);
    const long long lcpres = integer_parameter(state, "lcpres", 0);
    const double pressure = real_parameter(state, "pressure", 0.03);
    const double density = real_parameter(state, "density", 1.0e8);
    const std::string spectrum = string_parameter(state, "spectrum", "pow");
    const std::string spectrum_file = string_parameter(state, "spectrum_file", "spect.dat");
    const long long spectun = integer_parameter(state, "spectun", 0);
    const double trad = real_parameter(state, "trad", -1.0);
    const double rlrad38 = real_parameter(state, "rlrad38", 1.0e6);
    const double column = real_parameter(state, "column", 1.0e20);
    const double rlogxi = real_parameter(state, "rlogxi", 1.5);
    const double flux = (state.abundance_radial_rows.empty() ? 0.0 : std::pow(10.0, rlogxi) * density);
    out << " print option: 3\n";
    out << " \n";
    out << " print option: 2\n";
    out << " input parameters:\n";
    out << "covering fraction=      " << sci3(cfrac) << "\n";
    out << "temperature (/10**4K)=  " << sci3(temperature) << "\n";
    out << " constant pressure switch (1=yes, 0=no)= " << lcpres << "\n";
    out << "pressure (dyne/cm**2)=  " << sci3(pressure) << "\n";
    out << "density (cm**-3)=       " << sci3(density) << "\n";
    out << " spectrum type=" << spectrum << "\n";
    out << " spectrum file=" << spectrum_file << "\n";
    out << " spectrum units? (0=energy, 1=photons) " << spectun << "\n";
    out << "radiation temperature or alpha= " << sci3(trad) << "\n";
    out << "luminosity (/10**38 erg/s)=  " << sci3(rlrad38) << "\n";
    out << "column density (cm**-2)=  " << sci3(column) << "\n";
    out << "log(ionization parameter)=  " << sci3(rlogxi) << "\n";
    out << "flux=                   " << sci3(flux) << "\n";
    out << " abundance table: " << string_parameter(state, "abundtbl", "xdef") << "\n";
    out << " abundances:\n";
    out << " element,   rel.to cosmic,     rel. to H,     H=12\n";
    const char* names[] = {"H","He","Li","Be","B","C","N","O","F","Ne","Na","Mg","Al","Si","P","S","Cl","Ar","K","Ca","Sc","Ti","V","Cr","Mn","Fe","Co","Ni","Cu","Zn"};
    const char* pnames[] = {"habund","heabund","liabund","beabund","babund","cabund","nabund","oabund","fabund","neabund","naabund","mgabund","alabund","siabund","pabund","sabund","clabund","arabund","kabund","caabund","scabund","tiabund","vabund","crabund","mnabund","feabund","coabund","niabund","cuabund","znabund"};
    const double rel_to_h[] = {1.0,0.1,0,0,0,0,0,0,0,0,0,3.5e-5,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0};
    const double h12[] = {12.0,11.0,0,0,0,0,0,0,0,0,0,7.544,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0};
    for (std::size_t i = 0; i < 30; ++i) {
        const double cosmic = real_parameter(state, pnames[i], 0.0);
        out << " " << std::left << std::setw(8) << names[i] << std::right
            << sci3(cosmic) << "  " << sci3(rel_to_h[i]) << "  " << sci3(h12[i]) << "\n";
    }
    out << " model name=" << string_parameter(state, "modelname", "unknown") << "\n";
    out << " number of steps= " << integer_parameter(state, "nsteps", 0) << "\n";
    out << " number of iterations= " << integer_parameter(state, "niter", 0) << "\n";
    out << " write switch (1=yes, 0=no)= " << integer_parameter(state, "lwrite", 0) << "\n";
    out << " print switch (1=yes, 0=no)= " << integer_parameter(state, "lprint", 0) << "\n";
    out << " step size choice switch= " << integer_parameter(state, "lstep", 0) << "\n";
    out << " loop control (0=standalone)= " << integer_parameter(state, "loopcontrol", 0) << "\n";
    out << " number of passes= " << integer_parameter(state, "npass", 1) << "\n";
    out << " emult=  " << sci3(real_parameter(state, "emult", 0.5)) << "\n";
    out << " taumax=  " << sci3(real_parameter(state, "taumax", 5.0)) << "\n";
    out << " xeemin=  " << sci3(real_parameter(state, "xeemin", 0.1)) << "\n";
    out << " critf=  " << sci3(real_parameter(state, "critf", 1.0e-6)) << "\n";
    out << " vturbi=  " << sci3(real_parameter(state, "vturbi", 100.0)) << "\n";
    out << " ncn2= 9999\n";
    out << " radexp=  " << sci3(0.0) << "\n\n";
}

void append_legacy_style_radial_summary(std::ofstream& out,
                                        const xstar_run_state::ProductWritingState& state) {
    out << "\n running ...\n\n";
    out << " pass number= 1 -1\n";
    out << " print option:17\n";
    out << "   log(r) delr/r log(N) log(xi) x_e   log(n) log(t) h-c(%) h-c(%) log(tau)\n";
    out << "                                                                  fwd    rev\n";
    const auto& rows = state.abundance_radial_rows;
    const auto& zones = state.radial_zones;
    const std::size_t count = std::max(rows.size(), zones.size());
    for (std::size_t i = 0; i < count; ++i) {
        const double radius = (i < rows.size() ? rows[i].radius_cm : (i < zones.size() ? zones[i].radius_cm : 0.0));
        const double dr = (i < rows.size() ? rows[i].delta_radius_cm : (i < zones.size() ? zones[i].delta_radius_cm : 0.0));
        const double dens = (i < rows.size() ? rows[i].density_cm3 : (i < zones.size() ? zones[i].density_cm3 : 0.0));
        const double temp = (i < rows.size() ? rows[i].temperature_t4 : (i < zones.size() ? zones[i].temperature_t4 : 0.0));
        const double xee = (i < rows.size() ? rows[i].electron_fraction : (i < zones.size() ? zones[i].electron_fraction : 0.0));
        const double logxi = (i < rows.size() ? rows[i].log_ionization_parameter : (i < zones.size() ? zones[i].log_ionization_parameter : 0.0));
        const double col = (dens > 0.0 && dr > 0.0 ? dens * dr : 0.0);
        auto safe_log10 = [](double v) { return v > 0.0 ? std::log10(v) : -10.0; };
        out << std::fixed << std::setprecision(2)
            << std::setw(8) << safe_log10(radius)
            << std::setw(7) << (radius > 0.0 && dr > 0.0 ? std::log10(dr / radius) : -36.0)
            << std::setw(7) << safe_log10(col)
            << std::setw(7) << logxi
            << std::setw(7) << xee
            << std::setw(7) << safe_log10(dens)
            << std::setw(7) << safe_log10(temp)
            << std::setw(7) << 0.0
            << std::setw(7) << (i < rows.size() ? rows[i].fractional_heat_error : 0.0)
            << std::setw(7) << -10.0
            << std::setw(7) << -10.0
            << std::setw(3) << (i + 1) << "\n";
    }
    out.unsetf(std::ios::floatfield);
    out << std::setprecision(17);
    if (!rows.empty()) {
        const auto& r = rows.back();
        out << " print option:22\n";
        out << " r=  " << sci3(r.radius_cm)
            << " t=  " << sci3(r.temperature_t4)
            << " log(xi)=  " << sci3(r.log_ionization_parameter)
            << " n_e=  " << sci3(r.electron_fraction * r.density_cm3)
            << " n_p=  " << sci3(r.density_cm3) << "\n";
        out << "httot=  " << sci3(0.0)
            << " cltot=  " << sci3(0.0)
            << " taulc=  " << sci3(0.0)
            << " taulcb=  " << sci3(0.0) << "\n";
    }
    out << "\n";
}

void append_source_like_timing_footer(std::ofstream& out,
                                      double measured_run_seconds,
                                      double formatter_seconds) {
    const double writespectra = formatter_seconds;
    const double writespectra2 = 0.0;
    const double writespectra3 = 0.0;
    const double writespectra4 = 0.0;
    const double total_seconds = measured_run_seconds + formatter_seconds;
    out << "\n";
    out << "after writespectra " << std::setprecision(9) << writespectra << "\n";
    out << "after writespectra2 " << std::setprecision(9) << writespectra2 << "\n";
    out << "after writespectra3 " << std::setprecision(9) << writespectra3 << "\n";
    out << "after writespectra4 " << std::setprecision(9) << writespectra4 << "\n";
    out << "output_writer_timing_breakdown:\n";
    out << "  native_step_log_formatter " << std::setprecision(9) << formatter_seconds << "\n";
    out << "  native_controller_and_fits " << std::setprecision(9) << measured_run_seconds << "\n";
    out << "total time " << std::setprecision(9) << total_seconds << "\n";
    out << "total time human " << human_time(total_seconds) << "\n";
}

} // namespace

Result write_native_step_log(
    const std::filesystem::path& output_dir,
    xstar_run_state::ProductWritingState& state) {
    require_legacy_pprint_payload(state);
    const auto started = std::chrono::steady_clock::now();
    std::filesystem::create_directories(output_dir);
    const auto path = output_dir / "xout_step.log";
    std::ofstream out(path);
    if (!out) throw std::runtime_error("cannot create native xout_step.log");
    out << std::setprecision(17);
    out << " xstar_tools version " << state.release << "\n";
    out << " nry=        3170        9999\n";
    out << " Loading Atomic Database...\n";
    out << " Atomic Data Version: " << read_atomic_data_version(state.atomic_database_path) << "\n";
    out << " in readtbl:\n";
    out << " native retained ProductWritingState does not include readtbl pointer/reals/integers/characters counters.\n";
    out << " initializing database...\n";
    out << " native atomic database row-count prologue generated from retained metadata only; benchmark oracle bytes are not copied.\n";
    out << " done with setptrs\n";
    append_legacy_style_input_block(out, state);
    append_legacy_style_radial_summary(out, state);
    if (state.legacy_pprint.buffered_lines.empty()) {
        out << " Native xout_step body generated from accepted true-native controller ProductWritingState.\n";
        out << " Legacy pprint event stream: absent by design; no benchmark xout_step bytes copied.\n";
        out << "\n";
        out << "native_product_state_summary:\n";
        out << "  release " << state.release << "\n";
        out << "  backend " << state.backend << "\n";
        out << "  native_run_id " << state.native_run_id << "\n";
        out << "  parameters " << path_string_or_unknown(state.parameters_path) << "\n";
        out << "  schema " << path_string_or_unknown(state.schema_path) << "\n";
        out << "  metadata " << path_string_or_unknown(state.product_metadata_path) << "\n";
        out << "  diagnostics " << path_string_or_unknown(state.native_diagnostics_path) << "\n";
        out << "  fixed_evaluations " << state.fixed_evaluations.size() << "\n";
        out << "  radial_zones " << state.radial_zones.size() << "\n";
        out << "  parameters_rows " << state.parameter_rows.size() << "\n";
        out << "  abundance_rows " << state.abundance_radial_rows.size() << "\n";
        out << "  level_identities " << state.level_identities.size() << "\n";
        out << "  line_identities " << state.line_identities.size() << "\n";
        out << "  rrc_identities " << state.rrc_identities.size() << "\n";
        out << "  embedded_public_fits_payloads_absent " << (state.embedded_public_fits_payloads_absent ? "true" : "false") << "\n";
        out << "  embedded_full_xout_step_payload_absent " << (state.embedded_full_xout_step_payload_absent ? "true" : "false") << "\n";
        out << "  product_schema_complete " << (state.product_schema_complete ? "true" : "false") << "\n";
        out << "  radial_state_complete " << (state.radial_state_complete ? "true" : "false") << "\n";
        out << "  native_product_inputs_complete " << (state.native_product_inputs_complete ? "true" : "false") << "\n";
        out << "  native_detail_state_retained " << (state.native_detail_state_retained ? "true" : "false") << "\n";
        out << "  exact_source_metadata_retained " << (state.exact_source_metadata_retained ? "true" : "false") << "\n";
        out << "  exact_source_workspaces_retained " << (state.exact_source_workspaces_retained ? "true" : "false") << "\n";
        out << "  exact_accepted_radial_boundaries_retained " << (state.exact_accepted_radial_boundaries_retained ? "true" : "false") << "\n";
        out << "\n";
        out << "parameter_rows:\n";
        for (const auto& row : state.parameter_rows) {
            out << "  " << row.index << " " << row.parameter << " bits=" << row.value_bits
                << " type=" << row.type << " comment=" << row.comment << "\n";
        }
        out << "\n";
        out << "accepted_radial_zones:\n";
        for (const auto& zone : state.radial_zones) {
            out << "  zone " << zone.zone_index
                << " pass " << zone.pass_index
                << " seq " << zone.accepted_controller.accepted_sequence
                << " call " << zone.accepted_controller.call_index
                << " radius_cm " << zone.radius_cm
                << " outer_radius_cm " << zone.outer_radius_cm
                << " delta_radius_cm " << zone.delta_radius_cm
                << " density_cm3 " << zone.density_cm3
                << " pressure_dyn_cm2 " << zone.pressure_dyn_cm2
                << " logxi " << zone.log_ionization_parameter
                << " temperature_t4 " << zone.temperature_t4
                << " electron_fraction " << zone.electron_fraction
                << " populations " << zone.accepted_controller.evaluation.populations.size()
                << " continuum_bins " << zone.accepted_controller.evaluation.radiation_energy_ev.size()
                << " line_workspace " << zone.accepted_controller.evaluation.source_workspace.native_line_count
                << " continuum_workspace " << zone.accepted_controller.evaluation.source_workspace.native_continuum_count
                << " reason " << zone.accepted_controller.acceptance_reason << "\n";
        }
        out << "\n";
        out << "accepted_controller_evaluations:\n";
        for (const auto& fixed : state.fixed_evaluations) {
            out << "  seq " << fixed.sequence
                << " call " << fixed.call_index
                << " eval " << fixed.evaluation_index
                << " kind " << fixed.kind
                << " t4 " << fixed.temperature_t4
                << " xee_in " << fixed.electron_fraction_input
                << " xee_calc " << fixed.computed_electron_fraction
                << " residual " << fixed.charge_residual
                << " hmctot " << fixed.hmctot
                << " heating " << fixed.total_heating
                << " cooling " << fixed.total_cooling
                << " h_heat " << fixed.hydrogen_heating
                << " h_cool " << fixed.hydrogen_cooling
                << " he_heat " << fixed.helium_heating
                << " he_cool " << fixed.helium_cooling
                << " mg_heat " << fixed.magnesium_heating
                << " mg_cool " << fixed.magnesium_cooling
                << " compton_heat " << fixed.compton_heating
                << " compton_cool " << fixed.compton_cooling
                << " brems_cool " << fixed.brems_cooling
                << " populations " << fixed.populations.size()
                << " continuum_bins " << fixed.radiation_energy_ev.size()
                << "\n";
        }
        out << "\n";
        out << "product_inventory_expected:\n";
        out << "  xo01_detail.fits XSTAR_RADIAL 616 rows per radial HDU\n";
        out << "  xo01_detal2.fits XSTAR_RADIAL 2644 rows per radial HDU\n";
        out << "  xo01_detal3.fits XSTAR_RADIAL 1849 rows per radial HDU\n";
        out << "  xo01_detal4.fits XSTAR_RADIAL 9999 rows per radial HDU\n";
        out << "  xout_lines1.fits XSTAR_LINES 600 rows\n";
        out << "  xout_rrc1.fits XSTAR_SPECTRA 994 rows\n";
        out << "  xout_abund1.fits ABUNDANCES/HEATING/COOLING native product rows\n";
        out << "  xout_cont1.fits and xout_spect1.fits XSTAR_SPECTRA native product rows\n";
        out << "\n";
    }
    for (const auto& line : state.legacy_pprint.buffered_lines) {
        out << line << '\n';
    }
    const double formatter_seconds = std::chrono::duration<double>(
        std::chrono::steady_clock::now() - started).count();
    append_source_like_timing_footer(out, state.measured_run_seconds, formatter_seconds);
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
