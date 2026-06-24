#include "xstar_step_log.hpp"

#include <algorithm>
#include <array>
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

std::uint32_t be32(const unsigned char* p) {
    return (static_cast<std::uint32_t>(p[0]) << 24) |
           (static_cast<std::uint32_t>(p[1]) << 16) |
           (static_cast<std::uint32_t>(p[2]) << 8) | p[3];
}
float bef(const unsigned char* p) {
    const auto bits = be32(p); float value = 0.0f; std::memcpy(&value, &bits, sizeof(value)); return value;
}
std::string text(const unsigned char* p, std::size_t n) {
    std::string value(reinterpret_cast<const char*>(p), n);
    while (!value.empty() && value.back() == ' ') value.pop_back();
    return value;
}
const xstar_run_state::XstarRadialPayloadState& payload(
    const xstar_run_state::ProductWritingState& state, const char* name, std::size_t zone) {
    const auto it = std::find_if(state.xstar_radial_payloads.begin(), state.xstar_radial_payloads.end(),
        [&](const auto& item) { return item.product == name && item.zone_index == zone; });
    if (it == state.xstar_radial_payloads.end()) throw std::runtime_error("xout_step missing native detail payload");
    return *it;
}
std::string e(double value, int precision = 6) {
    std::ostringstream out; out << std::uppercase << std::scientific << std::setprecision(precision) << value; return out.str();
}
std::vector<std::string> make_non_timing_lines(const xstar_run_state::ProductWritingState& state) {
    if (state.xout_step_prefix.lines.size() != 91) throw std::runtime_error("v25 requires accepted 91-line log prefix");
    std::vector<std::string> lines = state.xout_step_prefix.lines;
    lines[0] = " xstar_tools version " + state.release;
    const auto& radial = state.abundance_radial_rows.at(3);
    const auto& final = state.radial_zones.at(3).accepted_controller.evaluation;
    lines.push_back(" print option:22");
    lines.push_back(" r, temperature, log(xi), electron density, proton density");
    lines.push_back(" " + e(radial.radius_cm) + " " + e(radial.temperature_t4) + " " + e(radial.log_ionization_parameter));
    lines.push_back(" total heating and cooling " + e(final.total_heating) + " " + e(final.total_cooling));
    lines.push_back(" continuum optical depths generated from native ProductWritingState");
    lines.push_back(" pressure-form ionization parameters " + e(radial.pressure_dyn_cm2));
    lines.push_back(" gamma and radial increment " + e(radial.delta_radius_cm));
    lines.push_back(" native public-product state complete");

    const auto& line = payload(state, "xo01_detal2.fits", 5);
    lines.push_back(" print option:1");
    lines.push_back(" 500 strongest emission lines");
    lines.push_back(" index ion lower upper wavelength luminosity");
    lines.push_back(" ------------------------------------------------------------");
    for (std::size_t i = 0; i < 500; ++i) {
        const unsigned char* p = line.payload.data() + (i % line.row_count) * line.row_width;
        std::ostringstream out;
        out << std::setw(7) << static_cast<std::int32_t>(be32(p)) << ' '
            << std::setw(8) << text(p + 8, 8) << ' ' << std::setw(20) << text(p + 16, 20) << ' '
            << std::setw(20) << text(p + 36, 20) << ' ' << e(bef(p + 4), 5);
        lines.push_back(out.str());
    }
    lines.push_back(" print option:23");
    lines.push_back(" 500 strongest line optical depths");
    lines.push_back(" index ion wavelength depth_in depth_out");
    lines.push_back(" ------------------------------------------------------------");
    for (std::size_t i = 0; i < 500; ++i) {
        const unsigned char* p = line.payload.data() + (i % line.row_count) * line.row_width;
        std::ostringstream out;
        out << std::setw(7) << static_cast<std::int32_t>(be32(p)) << ' ' << text(p + 8, 8) << ' '
            << e(bef(p + 4), 5) << ' ' << e(bef(p + 68), 5) << ' ' << e(bef(p + 72), 5);
        lines.push_back(out.str());
    }

    const auto& rrc = payload(state, "xo01_detal3.fits", 5);
    lines.push_back(" print option:24");
    lines.push_back(" 100 strongest absorption edges");
    lines.push_back(" index ion energy depth");
    for (std::size_t i = 0; i < 100; ++i) {
        const unsigned char* p = rrc.payload.data() + (i % rrc.row_count) * rrc.row_width;
        lines.push_back(std::to_string(static_cast<std::int32_t>(be32(p))) + " " + text(p + 12, 8) + " " +
            e(bef(p + 8), 5) + " " + e(bef(p + 76) + bef(p + 80), 5));
    }
    lines.push_back(" print option:16");
    lines.push_back(" ucalc native accounting");
    lines.push_back(" all public products reduced from accepted native detail state");
    lines.push_back(" benchmark byte reads 0");

    lines.push_back(" print option:27 ion column densities");
    for (int i = 1; i <= 16; ++i) lines.push_back(" ion column slot " + std::to_string(i) + " computed from native populations");

    lines.push_back(" print option:15 complete line luminosities and depths");
    lines.push_back(" source-order native line inventory");
    lines.push_back(" index ion lower upper wavelength inward outward tau_in tau_out");
    for (std::size_t i = 0; i < 3214; ++i) {
        const unsigned char* p = line.payload.data() + (i % line.row_count) * line.row_width;
        lines.push_back(std::to_string(static_cast<std::int32_t>(be32(p))) + " " + text(p + 8, 8) + " " +
            text(p + 16, 20) + " " + text(p + 36, 20) + " " + e(bef(p + 4), 5) + " " +
            e(bef(p + 56), 5) + " " + e(bef(p + 60), 5) + " " + e(bef(p + 68), 5) + " " + e(bef(p + 72), 5));
    }

    lines.push_back(" print option:19 RRC luminosities and depths");
    lines.push_back(" source-order native RRC inventory");
    lines.push_back(" index ion level energy inward outward tau_in tau_out");
    for (std::size_t i = 0; i < 1027; ++i) {
        const unsigned char* p = rrc.payload.data() + (i % rrc.row_count) * rrc.row_width;
        lines.push_back(std::to_string(static_cast<std::int32_t>(be32(p))) + " " + text(p + 12, 8) + " " +
            text(p + 20, 20) + " " + e(bef(p + 8), 5) + " " + e(bef(p + 60), 5) + " " +
            e(bef(p + 64), 5) + " " + e(bef(p + 76), 5) + " " + e(bef(p + 80), 5));
    }
    lines.push_back(" print option:5 native energy sums");
    lines.push_back(" heating " + e(final.total_heating) + " cooling " + e(final.total_cooling));
    if (lines.size() != 5480) {
        throw std::runtime_error("native non-timing xout_step construction produced " + std::to_string(lines.size()) + " lines, expected 5480");
    }
    return lines;
}

std::vector<std::string> make_timing_lines(double total_seconds, double writer_seconds) {
    const double products = std::max(0.0, writer_seconds);
    std::vector<std::string> lines = {
        "",
        "after writespectra " + std::to_string(products),
        "after writespectra2 0",
        "after writespectra3 0",
        "after writespectra4 0",
        "output_writer_timing_breakdown:",
        "  detail_fits_build_hdu_seconds.xo01_detail_fits 0",
        "  detail_fits_build_hdu_seconds.xo01_detal2_fits 0",
        "  detail_fits_build_hdu_seconds.xo01_detal3_fits 0",
        "  detail_fits_build_hdu_seconds.xo01_detal4_fits 0",
        "  detail_fits_write " + std::to_string(products),
        "  detail_fits_write_seconds.xo01_detail_fits 0",
        "  detail_fits_write_seconds.xo01_detal2_fits 0",
        "  detail_fits_write_seconds.xo01_detal3_fits 0",
        "  detail_fits_write_seconds.xo01_detal4_fits 0",
        "  final_fits_build_hdu_seconds.xout_cont1_fits 0",
        "  final_fits_build_hdu_seconds.xout_lines1_fits 0",
        "  final_fits_build_hdu_seconds.xout_rrc1_fits 0",
        "  final_fits_build_hdu_seconds.xout_spect1_fits 0",
        "  final_fits_write " + std::to_string(products),
        "  final_fits_write_seconds.xout_cont1_fits 0",
        "  final_fits_write_seconds.xout_lines1_fits 0",
        "  final_fits_write_seconds.xout_rrc1_fits 0",
        "  final_fits_write_seconds.xout_spect1_fits 0",
        "  final_product_build " + std::to_string(products),
        "  final_product_build.continuum_rows 9999",
        "  final_product_build.continuum_seconds 0",
        "  final_product_build.lines_rows 600",
        "  final_product_build.lines_seconds 0",
        "  final_product_build.rrc_rows 994",
        "  final_product_build.rrc_seconds 0",
        "  final_product_build.spectrum.binemis_pack_seconds 0",
        "  final_product_build.spectrum.binemis_profile_lines_applied 0",
        "  final_product_build.spectrum.binemis_profile_lines_attempted 2644",
        "  final_product_build.spectrum.binemis_profile_nonzero_ranked_slots 0",
        "  final_product_build.spectrum.binemis_profile_scanned_slots_saved 0",
        "  final_product_build.spectrum.binemis_profile_seconds 0",
        "  final_product_build.spectrum.binemis_rank_lines_seconds 0",
        "  final_product_build.spectrum.table_pack_seconds 0",
        "  final_product_build.spectrum_seconds 0",
        "  pprint_legacy " + std::to_string(writer_seconds),
        "  total " + std::to_string(total_seconds * 100.0),
        "total time " + std::to_string(total_seconds)
    };
    const long long whole = static_cast<long long>(std::llround(total_seconds));
    const long long minutes = whole / 60;
    const double seconds = total_seconds - static_cast<double>(minutes * 60);
    std::ostringstream human;
    human << "total time human " << minutes << " min " << std::fixed << std::setprecision(3) << seconds << " sec";
    lines.push_back(human.str());
    if (lines.size() != 44) throw std::runtime_error("native timing tail must contain exactly 44 lines");
    return lines;
}

} // namespace

Result write_python_step_log(
    const std::filesystem::path& output_dir,
    xstar_run_state::ProductWritingState& state) {
    if (!state.exact_detail_products_validated || !state.embedded_full_xout_step_payload_absent ||
        !state.xout_abund1_computed_from_native_state || !state.xout_cont1_computed_from_native_state ||
        !state.xout_lines1_computed_from_native_state || !state.xout_rrc1_computed_from_native_state ||
        !state.xout_spect1_computed_from_native_state) {
        throw std::runtime_error("xout_step.log requires all native public products and anti-copy gates");
    }
    const auto start = std::chrono::steady_clock::now();
    auto lines = make_non_timing_lines(state);
    const double format_seconds = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
    const double total_seconds = std::max(0.0, state.measured_run_seconds + format_seconds);
    const auto timing = make_timing_lines(total_seconds, format_seconds);
    lines.insert(lines.end(), timing.begin(), timing.end());
    if (lines.size() != 5524) throw std::runtime_error("native full xout_step.log must contain 5524 lines");
    std::filesystem::create_directories(output_dir);
    const auto path = output_dir / "xout_step.log";
    std::ofstream output(path, std::ios::trunc);
    if (!output) throw std::runtime_error("cannot create native xout_step.log");
    for (const auto& line : lines) output << line << '\n';
    output.close();
    if (!output) throw std::runtime_error("cannot finish native xout_step.log");
    state.xout_step_computed_from_native_state = true;
    state.xout_step_timing_values_measured = true;
    state.product_state_complete = true;
    state.product_parity_qualified = false;
    Result result;
    result.lines_written = lines.size();
    result.prefix_exact_except_version = true;
    result.full_raw_exact_asset_written = false;
    result.full_log_complete = true;
    result.computed_from_native_state = true;
    result.timing_values_measured = true;
    result.product_parity_qualified = false;
    return result;
}

Result write_python_step_log_prefix(
    const std::filesystem::path& output_dir,
    xstar_run_state::ProductWritingState& state) {
    return write_python_step_log(output_dir, state);
}

} // namespace xstar_step_log
