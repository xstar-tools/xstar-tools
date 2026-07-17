#include "xstar_step_log.hpp"

#include <algorithm>
#include <chrono>
#include <cctype>
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

double parameter_numeric_value(const xstar_run_state::ParameterRowState& row) {
    float value = 0.0f;
    static_assert(sizeof(value) == sizeof(row.value_bits), "parameter bits size mismatch");
    std::uint32_t bits = row.value_bits;
    std::memcpy(&value, &bits, sizeof(value));
    return static_cast<double>(value);
}

const xstar_run_state::ParameterRowState* parameter_row(
    const xstar_run_state::ProductWritingState& state,
    const std::string& name) {
    for (const auto& row : state.parameter_rows) if (row.parameter == name) return &row;
    return nullptr;
}

double parameter_number(const xstar_run_state::ProductWritingState& state,
                        const std::string& name,
                        double fallback = 0.0) {
    const auto* row = parameter_row(state, name);
    return row ? parameter_numeric_value(*row) : fallback;
}

std::string parameter_text(const xstar_run_state::ProductWritingState& state,
                           const std::string& name,
                           const std::string& fallback = "") {
    const auto* row = parameter_row(state, name);
    return row && !row->comment.empty() ? row->comment : fallback;
}

std::string e3(double value) {
    std::ostringstream out;
    out << std::uppercase << std::scientific << std::setprecision(3)
        << (std::isfinite(value) ? value : 0.0);
    return out.str();
}

void append_native_input_parameters(std::ofstream& out,
                                    const xstar_run_state::ProductWritingState& state) {
    out << " print option: 3\n \n print option: 2\n input parameters:\n";
    out << "covering fraction=      " << e3(parameter_number(state, "cfrac", 1.0)) << "\n";
    out << "temperature (/10**4K)=  " << e3(parameter_number(state, "temperature", 0.0)) << "\n";
    out << " constant pressure switch (1=yes, 0=no)= "
        << static_cast<long long>(std::llround(parameter_number(state, "lcpres", 0.0))) << "\n";
    out << "pressure (dyne/cm**2)=  " << e3(parameter_number(state, "pressure", 0.0)) << "\n";
    out << "density (cm**-3)=       " << e3(parameter_number(state, "density", 0.0)) << "\n";
    out << " spectrum type=" << parameter_text(state, "spectrum", "unavailable") << "\n";
    out << " spectrum file=" << parameter_text(state, "spectrum_file", "unavailable") << "\n";
    out << " spectrum units? (0=energy, 1=photons) "
        << static_cast<long long>(std::llround(parameter_number(state, "spectun", 0.0))) << "\n";
    out << "radiation temperature or alpha= " << e3(parameter_number(state, "trad", 0.0)) << "\n";
    out << "luminosity (/10**38 erg/s)=  " << e3(parameter_number(state, "rlrad38", 0.0)) << "\n";
    out << "column density (cm**-2)=  " << e3(parameter_number(state, "column", 0.0)) << "\n";
    out << "log(ionization parameter)=  " << e3(parameter_number(state, "rlogxi", 0.0)) << "\n";
    const double density = parameter_number(state, "density", 0.0);
    const double logxi = parameter_number(state, "rlogxi", 0.0);
    out << "flux=                   " << e3(density > 0.0 ? density * std::pow(10.0, logxi) : 0.0) << "\n";
    out << " abundance table: " << parameter_text(state, "abundtbl", "unavailable") << "\n";
    out << " relative-to-cosmic abundance parameters retained by the native run:\n";
    const std::pair<const char*,const char*> abundance_names[] = {
        {"H","habund"},{"He","heabund"},{"Li","liabund"},{"Be","beabund"},{"B","babund"},
        {"C","cabund"},{"N","nabund"},{"O","oabund"},{"F","fabund"},{"Ne","neabund"},
        {"Na","naabund"},{"Mg","mgabund"},{"Al","alabund"},{"Si","siabund"},{"P","pabund"},
        {"S","sabund"},{"Cl","clabund"},{"Ar","arabund"},{"K","kabund"},{"Ca","caabund"},
        {"Sc","scabund"},{"Ti","tiabund"},{"V","vabund"},{"Cr","crabund"},{"Mn","mnabund"},
        {"Fe","feabund"},{"Co","coabund"},{"Ni","niabund"},{"Cu","cuabund"},{"Zn","znabund"}
    };
    for (const auto& item : abundance_names) {
        out << " " << std::left << std::setw(8) << item.first << std::right
            << e3(parameter_number(state, item.second, 0.0)) << "\n";
    }
    out << " relative-to-H and H=12 abundance columns are not emitted because those ATDB-derived values are not retained in ProductWritingState.\n";
    out << " model name=" << parameter_text(state, "modelname", "unavailable") << "\n";
    out << " number of steps= " << static_cast<long long>(std::llround(parameter_number(state, "nsteps", 0.0))) << "\n";
    out << " number of iterations= " << static_cast<long long>(std::llround(parameter_number(state, "niter", 0.0))) << "\n";
    out << " write switch (1=yes, 0=no)= " << static_cast<long long>(std::llround(parameter_number(state, "lwrite", 0.0))) << "\n";
    out << " print switch (1=yes, 0=no)= " << static_cast<long long>(std::llround(parameter_number(state, "lprint", 0.0))) << "\n";
    out << " step size choice switch= " << static_cast<long long>(std::llround(parameter_number(state, "lstep", 0.0))) << "\n";
    out << " loop control (0=standalone)= " << static_cast<long long>(std::llround(parameter_number(state, "loopcontrol", 0.0))) << "\n";
    out << " number of passes= " << static_cast<long long>(std::llround(parameter_number(state, "npass", 0.0))) << "\n";
    out << " emult=  " << e3(parameter_number(state, "emult", 0.0)) << "\n";
    out << " taumax=  " << e3(parameter_number(state, "taumax", 0.0)) << "\n";
    out << " xeemin=  " << e3(parameter_number(state, "xeemin", 0.0)) << "\n";
    out << " critf=  " << e3(parameter_number(state, "critf", 0.0)) << "\n";
    out << " vturbi=  " << e3(parameter_number(state, "vturbi", 0.0)) << "\n";
}

void append_native_radial_summary(std::ofstream& out,
                                  const xstar_run_state::ProductWritingState& state) {
    out << "\n running ...\n\n pass number= 1 -1\n print option:17\n";
    out << "   log(r) delr/r log(N) log(xi) x_e   log(n) log(t) h-c(%)\n";
    auto safe_log = [](double value) { return value > 0.0 ? std::log10(value) : -10.0; };
    for (const auto& row : state.abundance_radial_rows) {
        out << std::fixed << std::setprecision(2)
            << std::setw(8) << safe_log(row.radius_cm)
            << std::setw(7) << (row.radius_cm > 0.0 && row.delta_radius_cm > 0.0 ? std::log10(row.delta_radius_cm / row.radius_cm) : -36.0)
            << std::setw(7) << safe_log(row.density_cm3 * row.delta_radius_cm)
            << std::setw(7) << row.log_ionization_parameter
            << std::setw(7) << row.electron_fraction
            << std::setw(7) << safe_log(row.density_cm3)
            << std::setw(7) << safe_log(row.temperature_t4)
            << std::setw(9) << 100.0 * row.fractional_heat_error
            << "\n";
    }
    out.unsetf(std::ios::floatfield);
    out << std::setprecision(17);
    if (!state.abundance_radial_rows.empty()) {
        const auto& row = state.abundance_radial_rows.back();
        const auto& eval = state.radial_zones.empty()
            ? state.fixed_evaluations.back()
            : state.radial_zones.back().accepted_controller.evaluation;
        double tau_forward = 0.0;
        for (double value : eval.continuum_tau_out) tau_forward = std::max(tau_forward, value);
        double tau_reverse = 0.0;
        for (double value : eval.continuum_tau_in) tau_reverse = std::max(tau_reverse, value);
        out << " print option:22\n";
        out << " r=  " << e3(row.radius_cm)
            << " t=  " << e3(row.temperature_t4)
            << " log(xi)=  " << e3(row.log_ionization_parameter)
            << " n_e=  " << e3(row.electron_fraction * row.density_cm3)
            << " n_p=  " << e3(row.density_cm3) << "\n";
        out << "httot=  " << e3(eval.total_heating)
            << " cltot=  " << e3(eval.total_cooling)
            << " taulc=  " << e3(tau_forward)
            << " taulcb=  " << e3(tau_reverse) << "\n";
    }
}

bool move_to_last_named_hdu(fitsfile* fptr, const std::string& extname) {
    int status = 0;
    int nhdus = 0;
    fits_get_num_hdus(fptr, &nhdus, &status);
    if (status != 0) return false;
    for (int hdu = nhdus; hdu >= 2; --hdu) {
        int hdutype = 0;
        status = 0;
        fits_movabs_hdu(fptr, hdu, &hdutype, &status);
        if (status != 0) continue;
        char value[FLEN_VALUE]{};
        status = 0;
        fits_read_key(fptr, TSTRING, const_cast<char*>("EXTNAME"), value, nullptr, &status);
        if (status == 0 && extname == value) return true;
    }
    return false;
}

int column_number(fitsfile* fptr, const char* name) {
    int status = 0;
    int col = 0;
    fits_get_colnum(fptr, CASEINSEN, const_cast<char*>(name), &col, &status);
    return status == 0 ? col : 0;
}

long long table_rows(fitsfile* fptr) {
    int status = 0;
    LONGLONG rows = 0;
    fits_get_num_rowsll(fptr, &rows, &status);
    return status == 0 ? static_cast<long long>(rows) : 0;
}

long long read_integer_cell(fitsfile* fptr, int col, long long row) {
    if (col <= 0) return 0;
    int status = 0;
    int anynul = 0;
    LONGLONG value = 0;
    LONGLONG nulval = 0;
    fits_read_col(fptr, TLONGLONG, col, row, 1, 1, &nulval, &value, &anynul, &status);
    return status == 0 ? static_cast<long long>(value) : 0;
}

double read_double_cell(fitsfile* fptr, int col, long long row) {
    if (col <= 0) return 0.0;
    int status = 0;
    int anynul = 0;
    double value = 0.0;
    double nulval = 0.0;
    fits_read_col(fptr, TDOUBLE, col, row, 1, 1, &nulval, &value, &anynul, &status);
    return status == 0 && std::isfinite(value) ? value : 0.0;
}

std::string read_string_cell(fitsfile* fptr, int col, long long row) {
    if (col <= 0) return "unavailable";
    int status = 0;
    int anynul = 0;
    char buffer[256]{};
    char* ptr = buffer;
    char nulval[] = "";
    fits_read_col(fptr, TSTRING, col, row, 1, 1, nulval, &ptr, &anynul, &status);
    if (status != 0) return "unavailable";
    std::string out(buffer);
    while (!out.empty() && std::isspace(static_cast<unsigned char>(out.back()))) out.pop_back();
    return out.empty() ? "unavailable" : out;
}

void append_native_public_line_sections(std::ofstream& out,
                                        const std::filesystem::path& output_dir) {
    fitsfile* fptr = nullptr;
    int status = 0;
    const auto path = output_dir / "xout_lines1.fits";
    fits_open_file(&fptr, path.c_str(), READONLY, &status);
    if (status != 0 || !move_to_last_named_hdu(fptr, "XSTAR_LINES")) {
        if (fptr) { int close_status = 0; fits_close_file(fptr, &close_status); }
        out << "\n native public line sections unavailable: xout_lines1.fits was not readable.\n";
        return;
    }
    const int c_index = column_number(fptr, "index");
    const int c_ion = column_number(fptr, "ion");
    const int c_wave = column_number(fptr, "wavelength");
    const int c_ein = column_number(fptr, "emit_inward");
    const int c_eout = column_number(fptr, "emit_outward");
    const int c_din = column_number(fptr, "depth_inward");
    const int c_dout = column_number(fptr, "depth_outward");
    const long long rows = table_rows(fptr);
    out << "\n print option:11\n\n print option: 1\n";
    out << " emission line luminosities (erg/sec/10**38))\n";
    out << " index, ion, wavelength, reflected, transmitted\n";
    for (long long row = 1; row <= rows; ++row) {
        out << std::setw(8) << read_integer_cell(fptr, c_index, row) << " "
            << std::left << std::setw(10) << read_string_cell(fptr, c_ion, row) << std::right
            << std::setw(14) << std::uppercase << std::scientific << std::setprecision(5)
            << read_double_cell(fptr, c_wave, row)
            << std::setw(14) << read_double_cell(fptr, c_ein, row)
            << std::setw(14) << read_double_cell(fptr, c_eout, row) << "\n";
    }
    out << " print option:23\n line depths\n";
    out << " index, ion, wavelength, reflected, transmitted\n";
    for (long long row = 1; row <= rows; ++row) {
        out << std::setw(8) << read_integer_cell(fptr, c_index, row) << " "
            << std::left << std::setw(10) << read_string_cell(fptr, c_ion, row) << std::right
            << std::setw(14) << std::uppercase << std::scientific << std::setprecision(5)
            << read_double_cell(fptr, c_wave, row)
            << std::setw(14) << read_double_cell(fptr, c_din, row)
            << std::setw(14) << read_double_cell(fptr, c_dout, row) << "\n";
    }
    int close_status = 0;
    fits_close_file(fptr, &close_status);
    out.unsetf(std::ios::floatfield);
    out << std::setprecision(17);
}

void append_native_public_rrc_sections(std::ofstream& out,
                                       const std::filesystem::path& output_dir) {
    fitsfile* fptr = nullptr;
    int status = 0;
    const auto path = output_dir / "xout_rrc1.fits";
    fits_open_file(&fptr, path.c_str(), READONLY, &status);
    if (status != 0 || !move_to_last_named_hdu(fptr, "XSTAR_SPECTRA")) {
        if (fptr) { int close_status = 0; fits_close_file(fptr, &close_status); }
        out << "\n native public RRC sections unavailable: xout_rrc1.fits was not readable.\n";
        return;
    }
    const int c_index = column_number(fptr, "index");
    const int c_ion = column_number(fptr, "ion");
    const int c_level = column_number(fptr, "level");
    const int c_energy = column_number(fptr, "energy");
    const int c_eout = column_number(fptr, "emit_outward");
    const int c_ein = column_number(fptr, "emit_inward");
    const int c_dout = column_number(fptr, "depth_outward");
    const int c_din = column_number(fptr, "depth_inward");
    const long long rows = table_rows(fptr);
    out << " print option:24\n absorption edge depths\n";
    out << " index, ion, level, energy (eV), outward depth, inward depth\n";
    for (long long row = 1; row <= rows; ++row) {
        out << std::setw(8) << read_integer_cell(fptr, c_index, row) << " "
            << std::left << std::setw(10) << read_string_cell(fptr, c_ion, row)
            << std::setw(24) << read_string_cell(fptr, c_level, row) << std::right
            << std::setw(14) << std::uppercase << std::scientific << std::setprecision(5)
            << read_double_cell(fptr, c_energy, row)
            << std::setw(14) << read_double_cell(fptr, c_dout, row)
            << std::setw(14) << read_double_cell(fptr, c_din, row) << "\n";
    }
    out << " print option:19\n recombination continuum luminosities(erg/sec/10**38))\n";
    out << " index, ion, level, energy (eV), outward RRC luminosity, inward RRC luminosity\n";
    for (long long row = 1; row <= rows; ++row) {
        out << std::setw(8) << read_integer_cell(fptr, c_index, row) << " "
            << std::left << std::setw(10) << read_string_cell(fptr, c_ion, row)
            << std::setw(24) << read_string_cell(fptr, c_level, row) << std::right
            << std::setw(14) << std::uppercase << std::scientific << std::setprecision(5)
            << read_double_cell(fptr, c_energy, row)
            << std::setw(14) << read_double_cell(fptr, c_eout, row)
            << std::setw(14) << read_double_cell(fptr, c_ein, row) << "\n";
    }
    int close_status = 0;
    fits_close_file(fptr, &close_status);
    out.unsetf(std::ios::floatfield);
    out << std::setprecision(17);
}

void append_native_detail_line_section(std::ofstream& out,
                                       const std::filesystem::path& output_dir) {
    fitsfile* fptr = nullptr;
    int status = 0;
    const auto path = output_dir / "xo01_detal2.fits";
    fits_open_file(&fptr, path.c_str(), READONLY, &status);
    if (status != 0 || !move_to_last_named_hdu(fptr, "XSTAR_RADIAL")) {
        if (fptr) { int close_status = 0; fits_close_file(fptr, &close_status); }
        out << "\n native detailed line section unavailable: xo01_detal2.fits was not readable.\n";
        return;
    }
    const int c_index = column_number(fptr, "index");
    const int c_wave = column_number(fptr, "wavelength");
    const int c_ion = column_number(fptr, "ion");
    const int c_lower = column_number(fptr, "lower_level");
    const int c_upper = column_number(fptr, "upper_level");
    const int c_ein = column_number(fptr, "emis_inward");
    const int c_eout = column_number(fptr, "emis_outward");
    const int c_tin = column_number(fptr, "tau_in");
    const int c_tout = column_number(fptr, "tau_out");
    const long long rows = table_rows(fptr);
    out << " print option:15\n line luminosities and depths from native terminal XSTAR_RADIAL\n";
    out << " line, wavelength, ion, inward emissivity, outward emissivity, inward depth, outward depth, transition\n";
    for (long long row = 1; row <= rows; ++row) {
        out << std::setw(8) << read_integer_cell(fptr, c_index, row)
            << std::setw(14) << std::uppercase << std::scientific << std::setprecision(5)
            << read_double_cell(fptr, c_wave, row) << " "
            << std::left << std::setw(10) << read_string_cell(fptr, c_ion, row) << std::right
            << std::setw(14) << read_double_cell(fptr, c_ein, row)
            << std::setw(14) << read_double_cell(fptr, c_eout, row)
            << std::setw(14) << read_double_cell(fptr, c_tin, row)
            << std::setw(14) << read_double_cell(fptr, c_tout, row) << " "
            << read_string_cell(fptr, c_lower, row) << "-" << read_string_cell(fptr, c_upper, row) << "\n";
    }
    int close_status = 0;
    fits_close_file(fptr, &close_status);
    out.unsetf(std::ios::floatfield);
    out << std::setprecision(17);
}

void append_native_product_sections(std::ofstream& out,
                                    const std::filesystem::path& output_dir) {
    append_native_public_line_sections(out, output_dir);
    append_native_public_rrc_sections(out, output_dir);
    append_native_detail_line_section(out, output_dir);
    out << " print option:16\n";
    out << " source CPU accumulators and per-rate call counts: unavailable (not retained by the native controller).\n";
    out << " print option:27\n";
    out << " ion column density integral: unavailable (per-zone source ion-column accumulator is not retained).\n";
    out << " print option: 5\n";
    out << " source energy-sum accounting tuple: unavailable (not retained by the native controller).\n";
}

void append_source_like_timing_footer(std::ofstream& out,
                                      double measured_run_seconds,
                                      double formatter_seconds) {
    const double total_seconds = std::max(0.0, measured_run_seconds) + std::max(0.0, formatter_seconds);
    out << "\nnative output timing (measured):\n";
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
    std::size_t source_nry = 0;
    std::size_t output_nry = 0;
    if (!state.radial_zones.empty()) {
        const auto& eval = state.radial_zones.back().accepted_controller.evaluation;
        source_nry = eval.source_continuum_tau_workspace_count;
        output_nry = eval.radiation_energy_ev.size();
    }
    out << " nry= " << std::setw(11) << source_nry << std::setw(12) << output_nry << "\n";
    out << " Loading Atomic Database...\n";
    out << " Atomic Data Version: " << read_atomic_data_version(state.atomic_database_path) << "\n";
    out << " in readtbl:\n";
    out << " native readtbl pointer/reals/integers/characters counters: unavailable (not retained by native ATDB lowering)\n";
    out << " native atomic line/rrc database totals: unavailable (not retained by native ATDB lowering)\n";
    out << " done with setptrs\n";
    append_native_input_parameters(out, state);
    append_native_radial_summary(out, state);
    append_native_product_sections(out, output_dir);
    if (state.legacy_pprint.buffered_lines.empty()) {
        out << "\n native ProductWritingState diagnostic summary (not an oracle pprint byte copy):\n";
        out << "run_summary:\n";
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
    result.full_log_complete = state.legacy_pprint.complete() && !state.legacy_pprint.buffered_lines.empty();
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
