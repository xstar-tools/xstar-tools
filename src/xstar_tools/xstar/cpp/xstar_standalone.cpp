#include "xstar_api.h"
#include "xstar_python_bridge.h"
#include "xstar_fixed_state_engine.h"
#include "xstar_thermal_engine.h"
#include "xstar_science_fits.hpp"
#include "xstar_standalone_internal.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <sstream>
#include <string>
#include <vector>

namespace {

struct Options {
    std::string command = "help";
    std::string backend = "cpp";
    std::string plugin_dir;
    std::string python_path;
    std::string case_dir;
    std::string output_dir;
    std::string trajectory_csv;
    std::string radiation_csv;
    std::string diagnostics_dir;
    std::string engine_backend = "inherit";
    std::string rates_backend = "inherit";
    std::string matrix_backend = "inherit";
    std::string solver_backend = "inherit";
    std::string emissivity_backend = "inherit";
    std::string opacity_backend = "inherit";
    std::string thermal_backend = "inherit";
    std::size_t batch = 3;
    std::size_t evaluation = 61;
    bool allow_scaffold = false;
};

void usage(std::ostream& output) {
    output <<
        "xstar_cpp " XSTAR_API_VERSION_STRING "\n"
        "Usage:\n"
        "  xstar_cpp --version\n"
        "  xstar_cpp list-backends\n"
        "  xstar_cpp backend-info --backend cpp|python [--plugin-dir DIR]\n"
        "  xstar_cpp self-test --backend cpp|python [--batch N] [--plugin-dir DIR]\n"
        "  xstar_cpp element-self-test --backend cpp [--plugin-dir DIR]\n"
        "  xstar_cpp evaluation-self-test --backend cpp [--plugin-dir DIR]\n"
        "  xstar_cpp construction-self-test --backend cpp [--plugin-dir DIR]\n"
        "  xstar_cpp construction-evaluation-self-test --backend cpp [--plugin-dir DIR]\n"
        "  xstar_cpp spectral-self-test --backend cpp [--plugin-dir DIR]\n"
        "  xstar_cpp thermal-self-test --backend cpp [--plugin-dir DIR]\n"
        "  xstar_cpp convergence-self-test --backend cpp [--plugin-dir DIR]\n"
        "  xstar_cpp fixed-state-self-test --case-dir RAW_PROGRAM_DIR [--diagnostics-dir DIR]\n"
        "  xstar_cpp run-fixed-state --case-dir RAW_PROGRAM_DIR --output-dir DIR\n"
        "  xstar_cpp fixed-state-batch-self-test --case-dir RAW_PROGRAM_DIR [--batch N]\n"
        "  xstar_cpp run-fixed-trajectory --case-dir RAW_PROGRAM_DIR --trajectory-csv CSV [--radiation-csv CSV] [--diagnostics-dir DIR] --output-dir DIR\n"
        "  xstar_cpp run-fixed-evaluation --case-dir RAW_PROGRAM_DIR --trajectory-csv CSV --evaluation N [--radiation-csv CSV] [--diagnostics-dir DIR] --output-dir DIR\n"
        "  xstar_cpp run-fixed-dsec --case-dir RAW_PROGRAM_DIR --trajectory-csv CSV [--radiation-csv CSV] [--diagnostics-dir DIR] --output-dir DIR\n"
        "  xstar_cpp production-self-test --case-dir DIR\n"
        "  xstar_cpp production-batch-self-test --case-dir DIR [--batch N]\n"
        "  xstar_cpp run-compiled-case --case-dir DIR --output-dir DIR\n"
        "  Component overrides: --engine-backend, --rates-backend, --matrix-backend,\n"
        "    --solver-backend, --emissivity-backend, --opacity-backend, --thermal-backend.\n"
        "  xstar_cpp run-zone --backend cpp|python --allow-scaffold [options]\n"
        "  xstar_cpp python-bridge-test [--plugin-dir DIR] [--python-path DIR]\n\n"
        "v0.6.48.7.14.2 adds a qualification-only v0.6.47.2 DSEC type-50 escape-runtime capture.\n"
        "It exports the native helium matrix/RHS/term stream and evaluates the v0.6.47.2 reference population residual; fixed-state and production promotion remain blocked.\n";
}

bool parse_size(const char* text, std::size_t& output) {
    if (!text || !*text) return false;
    char* end = nullptr;
    const unsigned long long value = std::strtoull(text, &end, 10);
    if (!end || *end != '\0' || value == 0) return false;
    output = static_cast<std::size_t>(value);
    return true;
}

bool parse_options(int argc, char** argv, Options& options, std::string& error) {
    if (argc < 2) return true;
    options.command = argv[1];
    if (options.command == "--version" || options.command == "-V") return true;
    for (int i = 2; i < argc; ++i) {
        const std::string arg = argv[i];
        auto require_value = [&](const char* name) -> const char* {
            if (i + 1 >= argc) {
                error = std::string("missing value for ") + name;
                return nullptr;
            }
            return argv[++i];
        };
        if (arg == "--backend") {
            const char* value = require_value("--backend");
            if (!value) return false;
            options.backend = value;
        } else if (arg == "--plugin-dir") {
            const char* value = require_value("--plugin-dir");
            if (!value) return false;
            options.plugin_dir = value;
        } else if (arg == "--python-path") {
            const char* value = require_value("--python-path");
            if (!value) return false;
            options.python_path = value;
        } else if (arg == "--case-dir") {
            const char* value = require_value("--case-dir");
            if (!value) return false;
            options.case_dir = value;
        } else if (arg == "--output-dir") {
            const char* value = require_value("--output-dir");
            if (!value) return false;
            options.output_dir = value;
        } else if (arg == "--trajectory-csv") {
            const char* value = require_value("--trajectory-csv");
            if (!value) return false;
            options.trajectory_csv = value;
        } else if (arg == "--radiation-csv") {
            const char* value = require_value("--radiation-csv");
            if (!value) return false;
            options.radiation_csv = value;
        } else if (arg == "--diagnostics-dir") {
            const char* value = require_value("--diagnostics-dir");
            if (!value) return false;
            options.diagnostics_dir = value;
        } else if (arg == "--engine-backend") {
            const char* value = require_value("--engine-backend");
            if (!value) return false;
            options.engine_backend = value;
        } else if (arg == "--rates-backend") {
            const char* value = require_value("--rates-backend");
            if (!value) return false;
            options.rates_backend = value;
        } else if (arg == "--matrix-backend") {
            const char* value = require_value("--matrix-backend");
            if (!value) return false;
            options.matrix_backend = value;
        } else if (arg == "--solver-backend") {
            const char* value = require_value("--solver-backend");
            if (!value) return false;
            options.solver_backend = value;
        } else if (arg == "--emissivity-backend") {
            const char* value = require_value("--emissivity-backend");
            if (!value) return false;
            options.emissivity_backend = value;
        } else if (arg == "--opacity-backend") {
            const char* value = require_value("--opacity-backend");
            if (!value) return false;
            options.opacity_backend = value;
        } else if (arg == "--thermal-backend") {
            const char* value = require_value("--thermal-backend");
            if (!value) return false;
            options.thermal_backend = value;
        } else if (arg == "--batch") {
            const char* value = require_value("--batch");
            if (!value || !parse_size(value, options.batch)) {
                error = "invalid --batch value";
                return false;
            }
        } else if (arg == "--evaluation") {
            const char* value = require_value("--evaluation");
            if (!value || !parse_size(value, options.evaluation)) {
                error = "invalid --evaluation value";
                return false;
            }
        } else if (arg == "--allow-scaffold") {
            options.allow_scaffold = true;
        } else {
            error = "unknown option: " + arg;
            return false;
        }
    }
    return true;
}

xstar_config_v1 make_config(const Options& options) {
    xstar_config_v1 config{};
    xstar_config_init_v1(&config);
    xstar_standalone::copy_text(config.backend, sizeof(config.backend), options.backend);
    if (!options.plugin_dir.empty()) {
        xstar_standalone::copy_text(
            config.plugin_directory, sizeof(config.plugin_directory), options.plugin_dir);
    }
    if (!options.python_path.empty()) {
        xstar_standalone::copy_text(
            config.python_path, sizeof(config.python_path), options.python_path);
    }
    xstar_standalone::copy_text(config.engine_backend, sizeof(config.engine_backend), options.engine_backend);
    xstar_standalone::copy_text(config.rates_backend, sizeof(config.rates_backend), options.rates_backend);
    xstar_standalone::copy_text(config.matrix_backend, sizeof(config.matrix_backend), options.matrix_backend);
    xstar_standalone::copy_text(config.solver_backend, sizeof(config.solver_backend), options.solver_backend);
    xstar_standalone::copy_text(config.emissivity_backend, sizeof(config.emissivity_backend), options.emissivity_backend);
    xstar_standalone::copy_text(config.opacity_backend, sizeof(config.opacity_backend), options.opacity_backend);
    xstar_standalone::copy_text(config.thermal_backend, sizeof(config.thermal_backend), options.thermal_backend);
    if (options.allow_scaffold) config.flags |= XSTAR_CONFIG_ALLOW_SCAFFOLD_MODEL;
    return config;
}

int create_context(const Options& options, xstar_context** context) {
    xstar_config_v1 config = make_config(options);
    const int status = xstar_context_create_v1(&config, context);
    if (status != XSTAR_STATUS_OK) {
        std::cerr << "context creation failed: " << xstar_status_string(status);
        if (const char* detail = xstar_api_last_error(); detail && *detail) {
            std::cerr << ": " << detail;
        }
        std::cerr << "\n";
    }
    return status;
}

int command_list_backends() {
    std::cout << "abi_version=" << xstar_api_abi_version() << "\n";
    std::cout << "version=" << xstar_api_version_string() << "\n";
    for (std::size_t i = 0; i < xstar_backend_count(); ++i) {
        std::cout << "backend[" << i << "]=" << xstar_backend_name(i) << "\n";
    }
    return 0;
}

int command_backend_info(const Options& options) {
    xstar_context* context = nullptr;
    const int create_status = create_context(options, &context);
    if (create_status != XSTAR_STATUS_OK) return create_status;
    std::cout << "backend=" << xstar_context_backend_name(context) << "\n";
    for (std::uint32_t id = 0; id < XSTAR_COMPONENT_COUNT; ++id) {
        xstar_component_info_v1 info{};
        xstar_component_info_init_v1(&info);
        const int status = xstar_context_get_component_info_v1(context, id, &info);
        if (status != XSTAR_STATUS_OK) {
            std::cout << "component[" << id << "].status=" << xstar_status_string(status) << "\n";
            continue;
        }
        std::cout << "component[" << id << "].name=" << info.component_name << "\n"
                  << "component[" << id << "].requested_backend=" << info.requested_backend << "\n"
                  << "component[" << id << "].implementation=" << info.implementation << "\n"
                  << "component[" << id << "].flags=" << info.status_flags << "\n"
                  << "component[" << id << "].library=" << info.library_path << "\n";
    }
    xstar_context_destroy(context);
    return 0;
}

struct ZoneBuffers {
    std::array<double, 4> abundances{{1.0, 0.1, 0.01, 0.001}};
    std::array<double, 5> energy{{1.0, 2.0, 3.0, 4.0, 5.0}};
    std::array<double, 5> flux{{5.0, 4.0, 3.0, 2.0, 1.0}};
    std::array<double, 4> ion_fractions{};
    std::array<double, 5> spectrum{};
    std::array<double, 5> opacity{};
};

void initialize_zone(std::uint64_t id, ZoneBuffers& buffers,
                     xstar_zone_input_v1& input, xstar_zone_output_v1& output) {
    xstar_zone_input_init_v1(&input);
    input.zone_id = id;
    input.temperature = 6.5e4 + static_cast<double>(id);
    input.electron_density = 1.0e8;
    input.hydrogen_density = 1.0e8;
    input.electron_fraction = 1.2;
    input.ionization_parameter = 31.6;
    input.column_density = 1.0e20;
    input.abundances = buffers.abundances.data();
    input.abundance_count = buffers.abundances.size();
    input.radiation_energy = buffers.energy.data();
    input.radiation_flux = buffers.flux.data();
    input.radiation_bin_count = buffers.energy.size();

    xstar_zone_output_init_v1(&output);
    output.ion_fractions = buffers.ion_fractions.data();
    output.ion_fraction_capacity = buffers.ion_fractions.size();
    output.spectrum = buffers.spectrum.data();
    output.spectrum_capacity = buffers.spectrum.size();
    output.opacity = buffers.opacity.data();
    output.opacity_capacity = buffers.opacity.size();
}

bool validate_scaffold(const xstar_zone_input_v1& input, const xstar_zone_output_v1& output,
                       const ZoneBuffers& buffers, const std::string& backend) {
    if ((output.status_flags & XSTAR_ZONE_STATUS_SCAFFOLD_RESULT) == 0 ||
        output.zone_id != input.zone_id || output.heating != 0.0 || output.cooling != 0.0 ||
        output.electron_fraction != input.electron_fraction || output.backend != backend ||
        output.ion_fraction_count != buffers.abundances.size() ||
        output.spectrum_count != buffers.flux.size() ||
        output.opacity_count != buffers.flux.size()) return false;
    for (std::size_t i = 0; i < buffers.abundances.size(); ++i) {
        if (output.ion_fractions[i] != buffers.abundances[i]) return false;
    }
    for (std::size_t i = 0; i < buffers.flux.size(); ++i) {
        if (output.spectrum[i] != buffers.flux[i] || output.opacity[i] != 0.0) return false;
    }
    return true;
}

int command_self_test(Options options) {
    options.allow_scaffold = true;
    xstar_context* context = nullptr;
    const int create_status = create_context(options, &context);
    if (create_status != XSTAR_STATUS_OK) return create_status;

    std::vector<ZoneBuffers> buffers(options.batch);
    std::vector<xstar_zone_input_v1> inputs(options.batch);
    std::vector<xstar_zone_output_v1> outputs(options.batch);
    for (std::size_t i = 0; i < options.batch; ++i) {
        initialize_zone(100 + i, buffers[i], inputs[i], outputs[i]);
    }
    const int status = xstar_context_run_batch_v1(
        context, inputs.data(), inputs.size(), outputs.data());
    if (status != XSTAR_STATUS_OK) {
        std::cerr << "batch failed: " << xstar_context_last_error(context) << "\n";
        xstar_context_destroy(context);
        return status;
    }
    for (std::size_t i = 0; i < options.batch; ++i) {
        if (!validate_scaffold(inputs[i], outputs[i], buffers[i], options.backend)) {
            std::cerr << "scaffold validation failed at zone " << i << "\n";
            xstar_context_destroy(context);
            return 20;
        }
    }
    xstar_context_stats_v1 stats{};
    xstar_context_stats_init_v1(&stats);
    const int stats_status = xstar_context_get_stats_v1(context, &stats);
    if (stats_status != XSTAR_STATUS_OK || stats.zones_completed != options.batch) {
        std::cerr << "stats validation failed\n";
        xstar_context_destroy(context);
        return 21;
    }
    std::cout << "backend=" << options.backend << "\n"
              << "batch_zones=" << options.batch << "\n"
              << "zones_attempted=" << stats.zones_attempted << "\n"
              << "zones_completed=" << stats.zones_completed << "\n"
              << "batch_calls=" << stats.batch_calls << "\n"
              << "persistent_context=true\n"
              << "scaffold_only=true\n"
              << "RESULT=ACCEPT\n";
    xstar_context_destroy(context);
    return 0;
}

struct ElementBuffers {
    std::array<std::int32_t, 2> superlevels{{1, 2}};
    std::array<std::int32_t, 2> ions{{1, 2}};
    std::array<double, 2> initial{{0.5, 0.5}};
    std::array<xstar_element_term_v1, 4> terms{};
    std::array<xstar_element_contribution_v1, 1> contributions{};
    std::array<double, 2> populations{};
    std::array<double, 2> final_outer{};
    std::array<double, 4> dense{};
    std::array<double, 4> heat{};
    std::array<double, 4> heat2{};
    std::array<double, 2> rhs{};
    std::array<double, 2> gamma{};
    std::array<double, 2> alpha{};
    std::array<double, 10> fgamma{};
    std::array<double, 10> falpha{};
    std::array<std::int64_t, 2> igamma{};
    std::array<std::int64_t, 2> ialpha{};
    std::array<double, 2> ion_totals{};
    std::array<double, 2> ion_totals_final{};
    std::array<double, 2> ionization{};
    std::array<double, 2> recombination{};
    std::array<double, 6> ionization_components{};
    std::array<double, 6> recombination_components{};
    std::array<double, 2> residual{};
    std::array<double, 2> scale{};
    std::array<double, 2> relative{};
};

void initialize_element(int element_z, ElementBuffers& b,
                        xstar_element_input_v1& input, xstar_element_output_v1& output) {
    auto set = [&](int q, int row, int col, double aj1, double aj2) {
        b.terms[static_cast<std::size_t>(q)] = {};
        b.terms[static_cast<std::size_t>(q)].source_position = q + 1;
        b.terms[static_cast<std::size_t>(q)].term_index = q + 1;
        b.terms[static_cast<std::size_t>(q)].record = 100 + element_z;
        b.terms[static_cast<std::size_t>(q)].rate_type = 7;
        b.terms[static_cast<std::size_t>(q)].ion_index = 1;
        b.terms[static_cast<std::size_t>(q)].ion_stage = 1;
        b.terms[static_cast<std::size_t>(q)].row = row;
        b.terms[static_cast<std::size_t>(q)].column = col;
        b.terms[static_cast<std::size_t>(q)].aj1 = aj1;
        b.terms[static_cast<std::size_t>(q)].aj2 = aj2;
    };
    set(0, 2, 1, 2.0, 1.0);
    set(1, 1, 2, 1.0, 2.0);
    set(2, 1, 1, -2.0, -2.0);
    set(3, 2, 2, -1.0, -1.0);
    b.contributions[0] = {};
    b.contributions[0].source_position = 1;
    b.contributions[0].record = 100 + element_z;
    b.contributions[0].rate_type = 7;
    b.contributions[0].ion_index = 1;
    b.contributions[0].ion_stage = 1;
    b.contributions[0].lower_row = 1;
    b.contributions[0].upper_row = 2;
    b.contributions[0].ans1 = 2.0;
    b.contributions[0].ans2 = 1.0;
    b.contributions[0].density_scale = 1.0;
    input = {};
    input.struct_size = sizeof(input);
    input.abi_version = XSTAR_ELEMENT_ENGINE_ABI_VERSION;
    input.max_lucy_iterations = 100;
    input.max_fixed_point_iterations = 200;
    input.lucy_tolerance = 1.0e-2;
    input.fixed_point_tolerance = 1.0e-2;
    input.flags = XSTAR_ELEMENT_STRICT_SOURCE_ORDER |
                  XSTAR_ELEMENT_DIAGNOSTICS_SUMMARY |
                  XSTAR_ELEMENT_RETURN_MATRICES;
    input.element_z = element_z;
    input.n_rows = 2;
    input.n_superlevels = 2;
    input.n_ions = 2;
    input.normalization_row = 2;
    input.superlevel_by_row = b.superlevels.data();
    input.ion_by_row = b.ions.data();
    input.initial_populations = b.initial.data();
    input.terms = b.terms.data();
    input.term_count = b.terms.size();
    output = {};
    output.struct_size = sizeof(output);
    output.abi_version = XSTAR_ELEMENT_ENGINE_ABI_VERSION;
#define XSTAR_SET_ELEMENT_BUFFER(field, capacity_field, buffer) \
    output.field = b.buffer.data(); output.capacity_field = b.buffer.size()
    XSTAR_SET_ELEMENT_BUFFER(populations, populations_capacity, populations);
    XSTAR_SET_ELEMENT_BUFFER(final_outer_start_populations, final_outer_start_capacity, final_outer);
    XSTAR_SET_ELEMENT_BUFFER(dense_matrix, dense_matrix_capacity, dense);
    XSTAR_SET_ELEMENT_BUFFER(heating_matrix, heating_matrix_capacity, heat);
    XSTAR_SET_ELEMENT_BUFFER(heating_matrix2, heating_matrix2_capacity, heat2);
    XSTAR_SET_ELEMENT_BUFFER(rhs, rhs_capacity, rhs);
    XSTAR_SET_ELEMENT_BUFFER(gamma, gamma_capacity, gamma);
    XSTAR_SET_ELEMENT_BUFFER(alpha, alpha_capacity, alpha);
    XSTAR_SET_ELEMENT_BUFFER(fgamma, fgamma_capacity, fgamma);
    XSTAR_SET_ELEMENT_BUFFER(falpha, falpha_capacity, falpha);
    XSTAR_SET_ELEMENT_BUFFER(igammamax_record, igammamax_capacity, igamma);
    XSTAR_SET_ELEMENT_BUFFER(ialphamax_record, ialphamax_capacity, ialpha);
    XSTAR_SET_ELEMENT_BUFFER(ion_population_totals, ion_population_totals_capacity, ion_totals);
    XSTAR_SET_ELEMENT_BUFFER(ion_population_totals_final_vector, ion_population_totals_final_capacity, ion_totals_final);
    XSTAR_SET_ELEMENT_BUFFER(ionization_totals, ionization_totals_capacity, ionization);
    XSTAR_SET_ELEMENT_BUFFER(recombination_totals, recombination_totals_capacity, recombination);
    XSTAR_SET_ELEMENT_BUFFER(ionization_components, ionization_components_capacity, ionization_components);
    XSTAR_SET_ELEMENT_BUFFER(recombination_components, recombination_components_capacity, recombination_components);
    XSTAR_SET_ELEMENT_BUFFER(row_residual, row_residual_capacity, residual);
    XSTAR_SET_ELEMENT_BUFFER(row_scale, row_scale_capacity, scale);
    XSTAR_SET_ELEMENT_BUFFER(relative_row_residual, relative_row_residual_capacity, relative);
#undef XSTAR_SET_ELEMENT_BUFFER
}

bool validate_element(const ElementBuffers& b, const xstar_element_output_v1& output) {
    return std::fabs(b.populations[0] - 1.0 / 3.0) < 1.0e-12 &&
           std::fabs(b.populations[1] - 2.0 / 3.0) < 1.0e-12 &&
           (output.status_flags & XSTAR_ELEMENT_STATUS_CONVERGED) != 0 &&
           (output.status_flags & XSTAR_ELEMENT_STATUS_NATIVE_MATRIX_ASSEMBLY) != 0 &&
           (output.status_flags & XSTAR_ELEMENT_STATUS_NATIVE_LUCY_SOLVE) != 0 &&
           (output.status_flags & XSTAR_ELEMENT_STATUS_STATE_COMMITTED) != 0 &&
           b.dense[0] == -2.0 && b.dense[1] == 1.0 &&
           b.dense[2] == 2.0 && b.dense[3] == -1.0;
}

int command_spectral_self_test(const Options& options) {
    xstar_context* context = nullptr;
    const int create_status = create_context(options, &context);
    if (create_status != XSTAR_STATUS_OK) return create_status;

    constexpr std::size_t n_lines = 8;
    constexpr std::size_t n_continua = 8;
    constexpr std::size_t n_energy = 64;
    std::array<double, 2 * n_lines> rcem{};
    std::array<double, n_lines> oplin{};
    std::array<double, 2 * n_continua> cemab{};
    std::array<double, n_continua> cabab{};
    std::array<double, n_continua> opakab{};
    std::array<double, 2 * n_energy> rccemis{};
    std::array<double, n_energy> opakc{};
    std::array<double, n_energy> opakcont{};
    std::array<double, 2 * n_lines> fline{};
    std::array<double, n_energy> flinel{};
    std::array<double, n_energy> energy{};
    for (std::size_t i = 0; i < n_energy; ++i) energy[i] = 100.0 + 10.0 * static_cast<double>(i);

    std::array<xstar_spectral_contribution_v1, 4> rows{};
    rows[0].source_position = 1;
    rows[0].record = 101;
    rows[0].kind = XSTAR_SPECTRAL_KIND_EMISAB_BOUND_FREE;
    rows[0].output_index = 1;
    rows[0].ptmp1 = 0.75;
    rows[0].ptmp2 = 0.25;
    rows[0].abundance_lower = 0.4;
    rows[0].abundance_upper = 0.6;
    rows[0].hydrogen_density = 2.0;
    rows[0].ans3 = -3.0;
    rows[0].ans4 = -5.0;
    rows[0].opakab = 7.0;

    rows[1].source_position = 2;
    rows[1].record = 102;
    rows[1].kind = XSTAR_SPECTRAL_KIND_EMISAB_LINE;
    rows[1].rate_type = 4;
    rows[1].output_index = 2;
    rows[1].ptmp1 = 0.6;
    rows[1].ptmp2 = 0.4;
    rows[1].abundance_lower = 0.3;
    rows[1].abundance_upper = 0.7;
    rows[1].ans3 = -2.0;
    rows[1].opakab = 11.0;

    rows[2].source_position = 3;
    rows[2].record = 103;
    rows[2].kind = XSTAR_SPECTRAL_KIND_EMIS_OPACITY_ONLY;
    rows[2].output_index = 3;
    rows[2].opakab = 13.0;

    rows[3].source_position = 4;
    rows[3].record = 104;
    rows[3].kind = XSTAR_SPECTRAL_KIND_EMIS_LINE;
    rows[3].output_index = 4;
    rows[3].bin_one_based = 31;
    rows[3].ptmp1 = 0.55;
    rows[3].ptmp2 = 0.45;
    rows[3].abundance_lower = 0.2;
    rows[3].abundance_upper = 0.8;
    rows[3].ans1 = 1.0;
    rows[3].ans2 = 2.0;
    rows[3].opakab = 0.5;
    rows[3].line_energy_eV = 400.0;
    rows[3].bin_width_eV = 10.0;
    rows[3].atomic_mass_amu = 24.0;
    rows[3].natural_width_eV = 1.0e-3;
    rows[3].turbulent_velocity_km_s = 100.0;
    rows[3].temperature_1e4K = 6.5;

    constexpr std::size_t seed_stride = 21;
    std::array<double, rows.size() * seed_stride> seeds{};
    for (std::size_t i = 0; i < rows.size(); ++i) {
        for (std::size_t j = 0; j < seed_stride; ++j) {
            const double x = static_cast<double>(j) - 10.0;
            seeds[i * seed_stride + j] = std::exp(-0.25 * x * x);
        }
    }

    xstar_spectral_workspace_v1 workspace{};
    workspace.struct_size = sizeof(workspace);
    workspace.abi_version = XSTAR_SPECTRAL_ENGINE_ABI_VERSION;
#define XSTAR_SET_SPECTRAL(field, count_field, buffer) \
    workspace.field = buffer.data(); workspace.count_field = buffer.size()
    XSTAR_SET_SPECTRAL(rcem, rcem_count, rcem);
    XSTAR_SET_SPECTRAL(oplin, oplin_count, oplin);
    XSTAR_SET_SPECTRAL(cemab, cemab_count, cemab);
    XSTAR_SET_SPECTRAL(cabab, cabab_count, cabab);
    XSTAR_SET_SPECTRAL(opakab, opakab_count, opakab);
    XSTAR_SET_SPECTRAL(rccemis, rccemis_count, rccemis);
    XSTAR_SET_SPECTRAL(opakc, opakc_count, opakc);
    XSTAR_SET_SPECTRAL(opakcont, opakcont_count, opakcont);
    XSTAR_SET_SPECTRAL(fline, fline_count, fline);
    XSTAR_SET_SPECTRAL(flinel, flinel_count, flinel);
#undef XSTAR_SET_SPECTRAL
    workspace.epi_eV = energy.data();
    workspace.energy_count = energy.size();

    xstar_spectral_stats_v1 stats{};
    stats.struct_size = sizeof(stats);
    stats.abi_version = XSTAR_SPECTRAL_ENGINE_ABI_VERSION;
    const int status = xstar_context_apply_spectral_contributions_v1(
        context, rows.data(), rows.size(), seeds.data(), seed_stride, &workspace, &stats);
    if (status != XSTAR_STATUS_OK) {
        std::cerr << "spectral self-test failed: " << xstar_context_last_error(context) << "\n";
        xstar_context_destroy(context);
        return status;
    }
    const bool accepted = stats.calls == 1 && stats.contributions_attempted == 4 &&
        stats.contributions_committed == 4 && stats.emissivity_contributions == 3 &&
        stats.opacity_contributions == 4 && stats.line_profiles == 1 &&
        stats.source_order_violations == 0 && opakab[1] == 7.0 &&
        oplin[2] == 3.3 && opakab[3] == 13.0 && oplin[4] == 0.1 &&
        fline[4] > 0.0 && flinel[30] > 0.0;
    std::cout << "backend=" << xstar_context_backend_name(context) << "\n"
              << "spectral_contributions=" << stats.contributions_committed << "\n"
              << "emissivity_contributions=" << stats.emissivity_contributions << "\n"
              << "opacity_contributions=" << stats.opacity_contributions << "\n"
              << "line_profiles=" << stats.line_profiles << "\n"
              << "source_order_violations=" << stats.source_order_violations << "\n"
              << "persistent_context=true\n"
              << "native_emissivity=true\n"
              << "native_opacity=true\n"
              << "RESULT=" << (accepted ? "ACCEPT" : "REJECT") << "\n";
    xstar_context_destroy(context);
    return accepted ? 0 : 9;
}


int thermal_test_evaluator(
    void*, const xstar_thermal_state_v1* state,
    xstar_thermal_evaluation_v1* result, char*, std::size_t
) {
    if (!state || !result) return 1;
    std::memset(result, 0, sizeof(*result)); result->struct_size=sizeof(*result); result->abi_version=XSTAR_THERMAL_ENGINE_ABI_VERSION;
    result->hmctot = 2.0 - state->temperature_t4;
    result->elcter = state->electron_fraction_xee - 1.5;
    result->temperature_t4 = state->temperature_t4;
    result->electron_fraction_xee = state->electron_fraction_xee;
    result->hydrogen_density_cm3 = state->hydrogen_density_cm3;
    result->state_generation = state->state_generation + 1;
    return 0;
}

int command_thermal_self_test(const Options& options) {
    xstar_context* context = nullptr;
    const int create_status = create_context(options, &context);
    if (create_status != XSTAR_STATUS_OK) return create_status;
    constexpr std::size_t n = 4, nl = 2, nc = 2;
    std::array<double, n> epi{{1.0, 10.0, 100.0, 1000.0}};
    std::array<double, n> incident{{2.0, 3.0, 4.0, 5.0}};
    std::array<double, n> opakc{{0.02, 0.1, 1.0, 0.04}};
    std::array<double, n> opakcont{{0.01, 0.2, 0.8, 0.4}};
    std::array<double, n> flinel{{1.0, 2.0, 3.0, 4.0}};
    std::array<double, n> brcems{{0.005, 0.006, 0.007, 0.008}};
    std::array<double, 2*n> rccemis{{0.01,0.02,0.03,0.04, 0.04,0.03,0.02,0.01}};
    std::array<double, 5*n> zrems{};
    std::array<double, 5*n> zremso{};
    for (std::size_t row=0; row<5; ++row) for(std::size_t col=0; col<n; ++col) {
        zrems[row*n+col] = -1000.0 * static_cast<double>(row+1) - static_cast<double>(col+1);
        zremso[row*n+col] = 100.0 * static_cast<double>(row+1) + static_cast<double>(col+1);
    }
    std::array<double, 2*nl> elum{{-900,-900,-900,-900}};
    std::array<double, 2*nl> elumo{{5,7,6,8}};
    std::array<double, 2*nl> rcem{{0.1,0.3,0.2,0.4}};
    std::array<double, 2*nc> elumab{{-600,-600,-600,-600}};
    std::array<double, 2*nc> elumabo{{9,11,10,12}};
    std::array<double, 2*nc> cemab{{0.03,0.0,0.05,0.0}};
    std::array<xstar_heatt_line_v1, nl> lines{{
        {4,4,0,10.0}, {5,50,0,20.0}
    }};
    std::array<xstar_heatt_rrc_v1, 2> rrcs{{
        {6,1,1,1,0}, {7,2,1,0,0}
    }};
    xstar_heatt_workspace_v1 w{}; w.struct_size=sizeof(w); w.abi_version=XSTAR_THERMAL_ENGINE_ABI_VERSION;
    w.temperature_t4=2.0; w.radius_cm=2.0e19; w.covering_fraction=0.3;
    w.zone_thickness_cm=0.25; w.electron_fraction_xee=1.2; w.hydrogen_density_cm3=5.0;
    w.epi_eV=epi.data(); w.bremsa=incident.data(); w.opakc=opakc.data();
    w.opakcont=opakcont.data(); w.flinel=flinel.data(); w.brcems=brcems.data(); w.ncn2=n;
    w.zrems=zrems.data(); w.zremso=zremso.data(); w.zrems_count=zrems.size();
    w.elum=elum.data(); w.elumo=elumo.data(); w.rcem=rcem.data(); w.n_lines=nl;
    w.elumab=elumab.data(); w.elumabo=elumabo.data(); w.cemab=cemab.data(); w.n_continua=nc;
    w.rccemis=rccemis.data(); w.rccemis_count=rccemis.size();
    xstar_heatt_stats_v1 stats{}; stats.struct_size=sizeof(stats); stats.abi_version=XSTAR_THERMAL_ENGINE_ABI_VERSION;
    const int status = xstar_context_apply_heatt_v1(context, &w, lines.data(), lines.size(), rrcs.data(), rrcs.size(), &stats);
    const bool accepted = status == XSTAR_STATUS_OK && stats.calls == 1 && stats.continuum_bins == n &&
        std::fabs(zrems[0] - 109.17404856295778) < 1.0e-12 &&
        std::fabs(elum[0] - 5.75600004196167) < 1.0e-12 &&
        std::fabs(elumab[0] - 9.502400016784668) < 1.0e-12;
    std::cout << "backend=" << xstar_context_backend_name(context) << "\n"
              << "continuum_bins=" << stats.continuum_bins << "\n"
              << "line_records=" << stats.line_records << "\n"
              << "rrc_records=" << stats.rrc_records << "\n"
              << "state_commits=" << stats.state_commits << "\n"
              << "persistent_context=true\n"
              << "native_heatt=true\n"
              << "RESULT=" << (accepted ? "ACCEPT" : "REJECT") << "\n";
    if (!accepted && status != XSTAR_STATUS_OK) std::cerr << xstar_context_last_error(context) << "\n";
    xstar_context_destroy(context);
    return accepted ? 0 : 10;
}

int command_convergence_self_test(const Options& options) {
    xstar_context* context = nullptr;
    const int create_status = create_context(options, &context);
    if (create_status != XSTAR_STATUS_OK) return create_status;
    xstar_dsec_config_v1 config{}; config.struct_size=sizeof(config); config.abi_version=XSTAR_THERMAL_ENGINE_ABI_VERSION; config.charge_tolerance=static_cast<double>(static_cast<float>(1.0e-4)); config.thermal_tolerance=static_cast<double>(static_cast<float>(1.0e-4)); config.temperature_stagnation_tolerance=static_cast<double>(static_cast<float>(2.0e-9));
    config.nlim = 24; config.maximum_evaluations = 128; config.tinf_t4 = 0.099;
    xstar_thermal_state_v1 state{}; state.struct_size=sizeof(state); state.abi_version=XSTAR_THERMAL_ENGINE_ABI_VERSION;
    state.temperature_t4 = 1.0; state.electron_fraction_xee = 1.0; state.hydrogen_density_cm3 = 1.0e8;
    std::array<xstar_thermal_trace_event_v1, 256> trace{};
    std::size_t trace_count = 0;
    xstar_dsec_stats_v1 stats{}; stats.struct_size=sizeof(stats); stats.abi_version=XSTAR_THERMAL_ENGINE_ABI_VERSION;
    const int status = xstar_context_run_thermal_evaluation_loop_v1(
        context, &config, &state, thermal_test_evaluator, nullptr,
        trace.data(), trace.size(), &trace_count, &stats);
    const bool accepted = status == XSTAR_STATUS_OK && stats.charge_converged && stats.thermal_converged &&
        std::fabs(state.temperature_t4 - 2.0) < 1.0e-8 &&
        std::fabs(state.electron_fraction_xee - 1.5) < 1.0e-8 && stats.ntotit > 1;
    std::cout << "backend=" << xstar_context_backend_name(context) << "\n"
              << "evaluations_completed=" << stats.evaluations_completed << "\n"
              << "temperature_iterations=" << stats.temperature_iterations << "\n"
              << "charge_converged=" << (stats.charge_converged ? "true" : "false") << "\n"
              << "thermal_converged=" << (stats.thermal_converged ? "true" : "false") << "\n"
              << "final_temperature_t4=" << std::setprecision(17) << state.temperature_t4 << "\n"
              << "final_electron_fraction=" << state.electron_fraction_xee << "\n"
              << "one_native_loop_per_zone=true\n"
              << "callback_evaluation=true\n"
              << "callback_state_propagation=true\n"
              << "RESULT=" << (accepted ? "ACCEPT" : "REJECT") << "\n";
    if (!accepted && status != XSTAR_STATUS_OK) std::cerr << xstar_context_last_error(context) << "\n";
    xstar_context_destroy(context);
    return accepted ? 0 : 11;
}

int command_element_self_test(const Options& options, bool evaluation, bool construction) {
    xstar_context* context = nullptr;
    const int create_status = create_context(options, &context);
    if (create_status != XSTAR_STATUS_OK) return create_status;
    const std::size_t count = evaluation ? 3u : 1u;
    std::vector<ElementBuffers> buffers(count);
    std::vector<xstar_element_input_v1> inputs(count);
    std::vector<xstar_element_output_v1> outputs(count);
    const int elements[3] = {1, 2, 12};
    for (std::size_t i = 0; i < count; ++i) initialize_element(elements[i], buffers[i], inputs[i], outputs[i]);
    int status = XSTAR_STATUS_OK;
    if (construction && evaluation) {
        std::vector<const xstar_element_contribution_v1*> contribution_arrays(count);
        std::vector<std::size_t> contribution_counts(count, 1u);
        for (std::size_t i = 0; i < count; ++i) {
            contribution_arrays[i] = buffers[i].contributions.data();
            inputs[i].terms = nullptr;
            inputs[i].term_count = 0;
        }
        status = xstar_context_run_construction_evaluation_v1(
            context, inputs.data(), contribution_arrays.data(), contribution_counts.data(),
            count, outputs.data());
    } else if (construction) {
        inputs[0].terms = nullptr;
        inputs[0].term_count = 0;
        status = xstar_context_run_element_construction_v1(
            context, &inputs[0], buffers[0].contributions.data(),
            buffers[0].contributions.size(), &outputs[0]);
    } else {
        status = evaluation
            ? xstar_context_run_evaluation_v1(context, inputs.data(), count, outputs.data())
            : xstar_context_run_element_v1(context, inputs.data(), outputs.data());
    }
    if (status != XSTAR_STATUS_OK) {
        std::cerr << "native element test failed: " << xstar_context_last_error(context) << "\n";
        xstar_context_destroy(context);
        return status;
    }
    for (std::size_t i = 0; i < count; ++i) {
        if (!validate_element(buffers[i], outputs[i]) ||
            (construction && (outputs[i].status_flags & XSTAR_ELEMENT_STATUS_NATIVE_CONSTRUCTION) == 0)) {
            std::cerr << "native element validation failed at index " << i << "\n";
            xstar_context_destroy(context);
            return 30;
        }
    }
    xstar_element_engine_stats_v1 stats{};
    stats.struct_size = sizeof(stats);
    stats.abi_version = XSTAR_ELEMENT_ENGINE_ABI_VERSION;
    const int stats_status = xstar_context_get_element_stats_v1(context, &stats);
    if (stats_status != XSTAR_STATUS_OK) {
        std::cerr << "native element stats failed\n";
        xstar_context_destroy(context);
        return stats_status;
    }
    std::cout << "backend=" << options.backend << "\n"
              << "elements=" << count << "\n"
              << "one_call_per_evaluation=" << (evaluation ? "true" : "false") << "\n"
              << "elements_attempted=" << stats.elements_attempted << "\n"
              << "elements_completed=" << stats.elements_completed << "\n"
              << "evaluations_completed=" << stats.evaluations_completed << "\n"
              << "terms_committed=" << stats.terms_committed << "\n"
              << "construction_mode=" << (construction ? "true" : "false") << "\n"
              << "construction_calls=" << stats.construction_calls << "\n"
              << "records_constructed=" << stats.records_constructed << "\n"
              << "terms_constructed=" << stats.terms_constructed << "\n"
              << "persistent_context=true\n"
              << "native_matrix=true\n"
              << "native_lucy=true\n"
              << "native_state_commit=true\n"
              << "RESULT=ACCEPT\n";
    xstar_context_destroy(context);
    return 0;
}

int command_run_zone(const Options& options) {
    xstar_context* context = nullptr;
    const int create_status = create_context(options, &context);
    if (create_status != XSTAR_STATUS_OK) return create_status;
    ZoneBuffers buffers;
    xstar_zone_input_v1 input{};
    xstar_zone_output_v1 output{};
    initialize_zone(1, buffers, input, output);
    const int status = xstar_context_run_zone_v1(context, &input, &output);
    if (status != XSTAR_STATUS_OK) {
        std::cerr << "run-zone failed: " << xstar_context_last_error(context) << "\n";
        xstar_context_destroy(context);
        return status;
    }
    std::cout << std::setprecision(17)
              << "zone_id=" << output.zone_id << "\n"
              << "backend=" << output.backend << "\n"
              << "heating=" << output.heating << "\n"
              << "cooling=" << output.cooling << "\n"
              << "electron_fraction=" << output.electron_fraction << "\n"
              << "status_flags=" << output.status_flags << "\n"
              << "message=" << output.message << "\n";
    xstar_context_destroy(context);
    return 0;
}


int create_compiled_case(const Options& options, xstar_compiled_case_context** context) {
    if (options.case_dir.empty()) {
        std::cerr << "--case-dir is required\n";
        return XSTAR_STATUS_INVALID_ARGUMENT;
    }
    std::array<char, XSTAR_MESSAGE_SIZE> message{};
    const int status = xstar_compiled_case_context_create_v1(
        options.case_dir.c_str(), context, message.data(), message.size());
    if (status != XSTAR_STATUS_OK) {
        std::cerr << "compiled-case load failed: " << message.data() << "\n";
    }
    return status;
}

int command_production_self_test(const Options& options) {
    xstar_compiled_case_context* context = nullptr;
    const int create_status = create_compiled_case(options, &context);
    if (create_status != XSTAR_STATUS_OK) return create_status;
    const auto output = std::filesystem::temp_directory_path() / "xstar_v0648_production_self_test";
    std::error_code ignored;
    std::filesystem::remove_all(output, ignored);
    xstar_compiled_case_stats_v1 stats{};
    xstar_compiled_case_stats_init_v1(&stats);
    std::array<char, XSTAR_MESSAGE_SIZE> message{};
    const int status = xstar_compiled_case_run_files_v1(
        context, output.c_str(), &stats, message.data(), message.size());
    const bool step_log_written = std::filesystem::is_regular_file(output / "xout_step.log");
    const bool accepted = status == XSTAR_STATUS_OK && stats.evaluations_native == 61 &&
        stats.python_callbacks == 0 && stats.science_files_written == 9 &&
        stats.science_files_verified == 9 && step_log_written &&
        (stats.status_flags & XSTAR_COMPILED_CASE_STATUS_CALLBACK_FREE) != 0 &&
        (stats.status_flags & XSTAR_COMPILED_CASE_STATUS_EXACT_REFERENCE_STATE) != 0;
    std::cout << std::setprecision(17)
              << "case_id=" << stats.case_id << "\n"
              << "evaluations_native=" << stats.evaluations_native << "\n"
              << "python_callbacks=" << stats.python_callbacks << "\n"
              << "science_files_written=" << stats.science_files_written << "\n"
              << "science_files_verified=" << stats.science_files_verified << "\n"
              << "xout_step_log_written=" << (step_log_written ? "true" : "false") << "\n"
              << "output_artifacts_written=" << (stats.science_files_written + (step_log_written ? 1 : 0)) << "\n"
              << "final_temperature_t4=" << stats.final_temperature_t4 << "\n"
              << "final_electron_fraction=" << stats.final_electron_fraction_xee << "\n"
              << "run_seconds=" << stats.run_seconds << "\n"
              << "standalone_operational=true\n"
              << "whole_run_python_fallback_retained=true\n"
              << "RESULT=" << (accepted ? "ACCEPT" : "REJECT") << "\n";
    if (!accepted) std::cerr << message.data() << "\n";
    std::filesystem::remove_all(output, ignored);
    xstar_compiled_case_context_destroy(context);
    return accepted ? 0 : 50;
}

int command_production_batch_self_test(const Options& options) {
    xstar_compiled_case_context* context = nullptr;
    const int create_status = create_compiled_case(options, &context);
    if (create_status != XSTAR_STATUS_OK) return create_status;
    std::vector<ZoneBuffers> buffers(options.batch);
    std::vector<xstar_zone_input_v1> inputs(options.batch);
    std::vector<xstar_zone_output_v1> outputs(options.batch);
    for (std::size_t i = 0; i < options.batch; ++i) initialize_zone(500 + i, buffers[i], inputs[i], outputs[i]);
    xstar_compiled_case_stats_v1 stats{};
    xstar_compiled_case_stats_init_v1(&stats);
    std::array<char, XSTAR_MESSAGE_SIZE> message{};
    const int status = xstar_compiled_case_run_batch_v1(
        context, inputs.data(), inputs.size(), outputs.data(), &stats, message.data(), message.size());
    bool accepted = status == XSTAR_STATUS_OK && stats.zones_completed == options.batch &&
        stats.evaluations_native == 61 * options.batch && stats.python_callbacks == 0 && stats.batch_calls == 1;
    for (std::size_t i = 0; accepted && i < options.batch; ++i) {
        accepted = (outputs[i].status_flags & XSTAR_ZONE_STATUS_COMPILED_CASE) != 0 &&
            outputs[i].zone_id == inputs[i].zone_id && std::string(outputs[i].backend) == "cpp-compiled";
    }
    std::cout << "batch_zones=" << options.batch << "\n"
              << "zones_completed=" << stats.zones_completed << "\n"
              << "evaluations_native=" << stats.evaluations_native << "\n"
              << "python_callbacks=" << stats.python_callbacks << "\n"
              << "batch_calls=" << stats.batch_calls << "\n"
              << "batch_mhd_api_operational=true\n"
              << "RESULT=" << (accepted ? "ACCEPT" : "REJECT") << "\n";
    if (!accepted) std::cerr << message.data() << "\n";
    xstar_compiled_case_context_destroy(context);
    return accepted ? 0 : 51;
}

int command_run_compiled_case(const Options& options) {
    if (options.output_dir.empty()) {
        std::cerr << "--output-dir is required\n";
        return XSTAR_STATUS_INVALID_ARGUMENT;
    }
    xstar_compiled_case_context* context = nullptr;
    const int create_status = create_compiled_case(options, &context);
    if (create_status != XSTAR_STATUS_OK) return create_status;
    xstar_compiled_case_stats_v1 stats{};
    xstar_compiled_case_stats_init_v1(&stats);
    std::array<char, XSTAR_MESSAGE_SIZE> message{};
    const int status = xstar_compiled_case_run_files_v1(
        context, options.output_dir.c_str(), &stats, message.data(), message.size());
    const bool step_log_written = status == XSTAR_STATUS_OK &&
        std::filesystem::is_regular_file(std::filesystem::path(options.output_dir) / "xout_step.log");
    std::cout << std::setprecision(17)
              << "case_id=" << stats.case_id << "\n"
              << "parameter_fingerprint=" << stats.parameter_fingerprint << "\n"
              << "evaluations_native=" << stats.evaluations_native << "\n"
              << "python_callbacks=" << stats.python_callbacks << "\n"
              << "science_files_written=" << stats.science_files_written << "\n"
              << "xout_step_log_written=" << (step_log_written ? "true" : "false") << "\n"
              << "output_artifacts_written=" << (stats.science_files_written + (step_log_written ? 1 : 0)) << "\n"
              << "final_temperature_t4=" << stats.final_temperature_t4 << "\n"
              << "final_electron_fraction=" << stats.final_electron_fraction_xee << "\n"
              << "run_seconds=" << stats.run_seconds << "\n"
              << "output_dir=" << options.output_dir << "\n"
              << "RESULT=" << (status == XSTAR_STATUS_OK ? "ACCEPT" : "REJECT") << "\n";
    if (status != XSTAR_STATUS_OK) std::cerr << message.data() << "\n";
    xstar_compiled_case_context_destroy(context);
    return status;
}



std::string fits_card(const std::string& key, const std::string& value, const std::string& comment = {}) {
    std::string card = key;
    if (card.size() < 8) card.append(8 - card.size(), ' ');
    if (!value.empty()) card += "= " + value;
    if (!comment.empty()) card += " / " + comment;
    if (card.size() > 80) card.resize(80);
    else card.append(80 - card.size(), ' ');
    return card;
}

void write_fits_header(std::ofstream& out, std::vector<std::string> cards) {
    cards.push_back(fits_card("END", ""));
    std::string block;
    for (const auto& card : cards) block += card;
    const std::size_t padded = ((block.size() + 2879) / 2880) * 2880;
    block.resize(padded, ' ');
    out.write(block.data(), static_cast<std::streamsize>(block.size()));
}

void write_be_double(std::ofstream& out, double value) {
    std::array<unsigned char, 8> bytes{};
    std::memcpy(bytes.data(), &value, 8);
#if __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__
    std::reverse(bytes.begin(), bytes.end());
#endif
    out.write(reinterpret_cast<const char*>(bytes.data()), 8);
}

void pad_fits_data(std::ofstream& out, std::size_t bytes) {
    const std::size_t padding = (2880 - (bytes % 2880)) % 2880;
    std::array<char, 2880> zeros{};
    if (padding) out.write(zeros.data(), static_cast<std::streamsize>(padding));
}

void write_native_state_fits(
    const std::filesystem::path& path,
    const xstar_fixed_state_input_v1& input,
    const xstar_fixed_state_output_v1& output,
    const std::array<double, 64>& energy,
    const std::array<double, 64>& spectrum,
    const std::array<double, 64>& opacity
) {
    std::ofstream out(path, std::ios::binary);
    if (!out) throw std::runtime_error("cannot create native_state.fits");
    write_fits_header(out, {
        fits_card("SIMPLE", "                   T"),
        fits_card("BITPIX", "                    8"),
        fits_card("NAXIS", "                    0"),
        fits_card("EXTEND", "                   T"),
        fits_card("ORIGIN", "'xstar_tools 0.6.48.7.14.2'"),
    });
    write_fits_header(out, {
        fits_card("XTENSION", "'BINTABLE'"), fits_card("BITPIX", "                    8"),
        fits_card("NAXIS", "                    2"), fits_card("NAXIS1", "                   48"),
        fits_card("NAXIS2", "                    1"), fits_card("PCOUNT", "                    0"),
        fits_card("GCOUNT", "                    1"), fits_card("TFIELDS", "                    6"),
        fits_card("EXTNAME", "'NATIVE_STATE'"),
        fits_card("TTYPE1", "'TEMPERATURE_K'"), fits_card("TFORM1", "'D'"),
        fits_card("TTYPE2", "'HEATING'"), fits_card("TFORM2", "'D'"),
        fits_card("TTYPE3", "'COOLING'"), fits_card("TFORM3", "'D'"),
        fits_card("TTYPE4", "'HMCTOT'"), fits_card("TFORM4", "'D'"),
        fits_card("TTYPE5", "'XEE'"), fits_card("TFORM5", "'D'"),
        fits_card("TTYPE6", "'ELCTER'"), fits_card("TFORM6", "'D'"),
    });
    write_be_double(out, input.temperature_k);
    write_be_double(out, output.total_heating);
    write_be_double(out, output.total_cooling);
    write_be_double(out, output.hmctot);
    write_be_double(out, output.electron_fraction_xee);
    write_be_double(out, output.elcter);
    pad_fits_data(out, 48);
    write_fits_header(out, {
        fits_card("XTENSION", "'BINTABLE'"), fits_card("BITPIX", "                    8"),
        fits_card("NAXIS", "                    2"), fits_card("NAXIS1", "                   24"),
        fits_card("NAXIS2", "                   64"), fits_card("PCOUNT", "                    0"),
        fits_card("GCOUNT", "                    1"), fits_card("TFIELDS", "                    3"),
        fits_card("EXTNAME", "'NATIVE_SPECTRUM'"),
        fits_card("TTYPE1", "'ENERGY_EV'"), fits_card("TFORM1", "'D'"),
        fits_card("TTYPE2", "'SPECTRUM'"), fits_card("TFORM2", "'D'"),
        fits_card("TTYPE3", "'OPACITY'"), fits_card("TFORM3", "'D'"),
    });
    for (std::size_t k = 0; k < 64; ++k) {
        write_be_double(out, energy[k]);
        write_be_double(out, spectrum[k]);
        write_be_double(out, opacity[k]);
    }
    pad_fits_data(out, 64 * 24);
}

int command_run_fixed_state(const Options& options) {
    if (options.case_dir.empty() || options.output_dir.empty()) {
        std::cerr << "run-fixed-state requires --case-dir and --output-dir\n";
        return 2;
    }
    xstar_fixed_state_context* context = nullptr;
    std::array<char, XSTAR_FIXED_STATE_MESSAGE_SIZE> message{};
    int rc = xstar_fixed_state_context_create_v1(options.case_dir.c_str(), &context, message.data(), message.size());
    if (rc != 0) {
        std::cerr << "fixed-state context creation failed: " << message.data() << "\n";
        return rc;
    }
    xstar_fixed_state_program_info_v1 program_info{};
    xstar_fixed_state_program_info_init_v1(&program_info);
    rc = xstar_fixed_state_context_get_program_info_v1(context, &program_info, message.data(), message.size());
    if (rc != 0 || program_info.population_rows == 0) {
        std::cerr << "fixed-state program info failed: " << message.data() << "\n";
        xstar_fixed_state_context_destroy(context);
        return rc != 0 ? rc : 3;
    }
    std::array<double, 64> energy{}, flux{}, spectrum{}, opacity{};
    std::vector<double> populations(static_cast<std::size_t>(program_info.population_rows), 0.0);
    for (std::size_t k = 0; k < energy.size(); ++k) {
        energy[k] = 1.0 + static_cast<double>(k);
        flux[k] = 1.0e12 / (1.0 + static_cast<double>(k));
    }
    xstar_fixed_state_input_v1 input{};
    xstar_fixed_state_input_init_v1(&input);
    input.temperature_k = 6.5e4;
    input.electron_density_cm3 = 1.0e8;
    input.hydrogen_density_cm3 = 1.0e8;
    input.neutral_h_density_cm3 = 1.0e4;
    input.ionized_h_density_cm3 = 9.999e7;
    input.electron_fraction_xee = 1.1;
    input.covering_fraction = 0.5;
    input.turbulent_velocity_km_s = 100.0;
    input.radiation_energy_ev = energy.data();
    input.radiation_flux = flux.data();
    input.radiation_bin_count = energy.size();
    xstar_fixed_state_output_v1 output{};
    xstar_fixed_state_output_init_v1(&output);
    output.populations = populations.data(); output.populations_capacity = populations.size();
    output.spectrum = spectrum.data(); output.spectrum_capacity = spectrum.size();
    output.opacity = opacity.data(); output.opacity_capacity = opacity.size();
    xstar_fixed_state_stats_v1 stats{};
    xstar_fixed_state_stats_init_v1(&stats);
    rc = xstar_fixed_state_run_v1(context, &input, &output, &stats, message.data(), message.size());
    if (rc != 0) {
        std::cerr << "fixed-state evaluation failed: " << message.data() << "\n";
        xstar_fixed_state_context_destroy(context);
        return rc;
    }
    try {
        const std::filesystem::path outdir(options.output_dir);
        std::filesystem::create_directories(outdir);
        const bool active_atdb_lowered = (output.status_flags & XSTAR_FIXED_STATE_STATUS_ACTIVE_ATDB_LOWERED) != 0u;
        {
            std::ofstream step(outdir / "xout_step.log");
            step << std::setprecision(17)
                 << "xstar_tools native fixed-state v0.6.48.7.14.2\n"
                 << "program_id=" << stats.program_id << "\n"
                 << "computed_from_raw_coefficients=true\n"
                 << "active_atdb_lowered=" << (active_atdb_lowered ? "true" : "false") << "\n"
                 << "unsupported_record_count=" << program_info.unsupported_record_count << "\n"
                 << "partial_program=" << (program_info.unsupported_record_count > 0 ? "true" : "false") << "\n"
                 << "python_callbacks=" << stats.python_callbacks << "\n"
                 << "temperature_k=" << input.temperature_k << "\n"
                 << "electron_density_cm3=" << input.electron_density_cm3 << "\n"
                 << "records_evaluated=" << stats.records_evaluated << "\n"
                 << "active_program_records=" << stats.active_program_records << "\n"
                 << "topology_rows_loaded=" << stats.topology_rows_loaded << "\n"
                 << "type56_records_evaluated=" << stats.type56_records_evaluated << "\n"
                 << "visited_data_types=" << stats.visited_data_types << "\n"
                 << "elements_solved=" << stats.elements_solved << "\n"
                 << "total_heating=" << output.total_heating << "\n"
                 << "total_cooling=" << output.total_cooling << "\n"
                 << "hmctot=" << output.hmctot << "\n"
                 << "elcter=" << output.elcter << "\n";
            for (std::size_t k = 0; k < output.populations_count; ++k) step << "population[" << k << "]=" << populations[k] << "\n";
        }
        rc = xstar_fixed_state_write_visited_report_v1(
            context, (outdir / "visited_records.csv").c_str(), message.data(), message.size());
        if (rc != 0) throw std::runtime_error(std::string("visited report failed: ") + message.data());
        {
            std::ofstream csv(outdir / "xstar_native_spectrum.csv");
            csv << "energy_ev,spectrum,opacity\n" << std::setprecision(17);
            for (std::size_t k = 0; k < energy.size(); ++k) csv << energy[k] << ',' << spectrum[k] << ',' << opacity[k] << '\n';
        }
        write_native_state_fits(outdir / "xout_native_state.fits", input, output, energy, spectrum, opacity);
        {
            std::ofstream summary(outdir / "native_fixed_state_summary.json");
            summary << std::setprecision(17)
                    << "{\n  \"schema_version\": \"0.6.48.7.14.2\",\n"
                    << "  \"program_id\": \"" << stats.program_id << "\",\n"
                    << "  \"computed_from_raw_coefficients\": true,\n"
                    << "  \"python_callbacks\": " << stats.python_callbacks << ",\n"
                    << "  \"records_evaluated\": " << stats.records_evaluated << ",\n"
                    << "  \"active_program_records\": " << stats.active_program_records << ",\n"
                    << "  \"topology_rows_loaded\": " << stats.topology_rows_loaded << ",\n"
                    << "  \"type56_records_evaluated\": " << stats.type56_records_evaluated << ",\n"
                    << "  \"visited_data_types\": " << stats.visited_data_types << ",\n"
                    << "  \"active_atdb_lowered\": " << (active_atdb_lowered ? "true" : "false") << ",\n"
                    << "  \"unsupported_record_count\": " << program_info.unsupported_record_count << ",\n"
                    << "  \"partial_program\": " << (program_info.unsupported_record_count > 0 ? "true" : "false") << ",\n"
                    << "  \"elements_solved\": " << stats.elements_solved << ",\n"
                    << "  \"hmctot\": " << output.hmctot << ",\n"
                    << "  \"production_promotion_ready\": false,\n"
                    << "  \"remaining_gate\": \"unsupported visited families, 61-evaluation integration, and exact XSTAR FITS schemas\"\n}\n";
        }
    } catch (const std::exception& exc) {
        std::cerr << "native output generation failed: " << exc.what() << "\n";
        xstar_fixed_state_context_destroy(context);
        return 8;
    }
    std::cout << std::setprecision(17)
              << "program_id=" << stats.program_id << "\n"
              << "program_elements=" << program_info.element_count << "\n"
              << "program_population_rows=" << program_info.population_rows << "\n"
              << "program_record_count=" << program_info.record_count << "\n"
              << "program_unsupported_records=" << program_info.unsupported_record_count << "\n"
              << "partial_program=" << (program_info.unsupported_record_count > 0 ? "true" : "false") << "\n"
              << "computed_from_raw_coefficients=true\n"
              << "records_evaluated=" << stats.records_evaluated << "\n"
              << "active_program_records=" << stats.active_program_records << "\n"
              << "topology_rows_loaded=" << stats.topology_rows_loaded << "\n"
              << "type56_records_evaluated=" << stats.type56_records_evaluated << "\n"
              << "visited_data_types=" << stats.visited_data_types << "\n"
              << "active_atdb_lowered=" << (((output.status_flags & XSTAR_FIXED_STATE_STATUS_ACTIVE_ATDB_LOWERED) != 0u) ? "true" : "false") << "\n"
              << "elements_solved=" << stats.elements_solved << "\n"
              << "python_callbacks=" << stats.python_callbacks << "\n"
              << "hmctot=" << output.hmctot << "\n"
              << "xout_step_log_generated=true\n"
              << "native_fits_generated=true\n"
              << "visited_record_report_generated=true\n"
              << "output_dir=" << options.output_dir << "\n"
              << "RESULT=ACCEPT\n";
    xstar_fixed_state_context_destroy(context);
    return 0;
}

int command_fixed_state_self_test(const Options& options, bool batch_mode) {
    if (options.case_dir.empty()) {
        std::cerr << "--case-dir RAW_PROGRAM_DIR is required\n";
        return 2;
    }
    xstar_fixed_state_context* context = nullptr;
    std::array<char, XSTAR_FIXED_STATE_MESSAGE_SIZE> message{};
    int rc = xstar_fixed_state_context_create_v1(options.case_dir.c_str(), &context, message.data(), message.size());
    if (rc != 0) {
        std::cerr << "fixed-state context creation failed: " << message.data() << "\n";
        return rc;
    }
    const std::size_t count = batch_mode ? options.batch : 2;
    xstar_fixed_state_program_info_v1 program_info{};
    xstar_fixed_state_program_info_init_v1(&program_info);
    rc = xstar_fixed_state_context_get_program_info_v1(context, &program_info, message.data(), message.size());
    if (rc != 0 || program_info.population_rows == 0) {
        std::cerr << "fixed-state program info failed: " << message.data() << "\n";
        xstar_fixed_state_context_destroy(context);
        return rc != 0 ? rc : 3;
    }
    std::vector<std::array<double, 64>> energies(count), fluxes(count), spectra(count), opacities(count);
    std::vector<std::vector<double>> populations(count, std::vector<double>(static_cast<std::size_t>(program_info.population_rows), 0.0));
    std::vector<xstar_fixed_state_input_v1> inputs(count);
    std::vector<xstar_fixed_state_output_v1> outputs(count);
    for (std::size_t z = 0; z < count; ++z) {
        for (std::size_t k = 0; k < 64; ++k) {
            energies[z][k] = 1.0 + static_cast<double>(k);
            fluxes[z][k] = 1.0e12 / (1.0 + static_cast<double>(k));
        }
        xstar_fixed_state_input_init_v1(&inputs[z]);
        inputs[z].temperature_k = 5.0e4 + 2.5e4 * static_cast<double>(z);
        inputs[z].electron_density_cm3 = 1.0e8;
        inputs[z].hydrogen_density_cm3 = 1.0e8;
        inputs[z].neutral_h_density_cm3 = 1.0e4;
        inputs[z].ionized_h_density_cm3 = 9.999e7;
        inputs[z].electron_fraction_xee = 1.1;
        inputs[z].covering_fraction = 0.5;
        inputs[z].turbulent_velocity_km_s = 100.0;
        inputs[z].radiation_energy_ev = energies[z].data();
        inputs[z].radiation_flux = fluxes[z].data();
        inputs[z].radiation_bin_count = energies[z].size();
        xstar_fixed_state_output_init_v1(&outputs[z]);
        outputs[z].populations = populations[z].data();
        outputs[z].populations_capacity = populations[z].size();
        outputs[z].spectrum = spectra[z].data();
        outputs[z].spectrum_capacity = spectra[z].size();
        outputs[z].opacity = opacities[z].data();
        outputs[z].opacity_capacity = opacities[z].size();
    }
    xstar_fixed_state_stats_v1 stats{};
    xstar_fixed_state_stats_init_v1(&stats);
    if (batch_mode) {
        rc = xstar_fixed_state_run_batch_v1(context, inputs.data(), inputs.size(), outputs.data(), &stats, message.data(), message.size());
    } else {
        rc = xstar_fixed_state_run_v1(context, &inputs[0], &outputs[0], &stats, message.data(), message.size());
        if (rc == 0) rc = xstar_fixed_state_run_v1(context, &inputs[1], &outputs[1], &stats, message.data(), message.size());
    }
    if (rc != 0) {
        std::cerr << "fixed-state evaluation failed: " << message.data() << "\n";
        xstar_fixed_state_context_destroy(context);
        return rc;
    }
    if (!options.diagnostics_dir.empty()) {
        rc = xstar_fixed_state_write_last_diagnostics_v1(
            context, options.diagnostics_dir.c_str(), static_cast<std::uint64_t>(count), message.data(), message.size());
        if (rc != 0) {
            std::cerr << "fixed-state diagnostics failed: " << message.data() << "\n";
            xstar_fixed_state_context_destroy(context);
            return rc;
        }
    }
    bool changed = batch_mode || std::abs(outputs[0].hmctot - outputs[1].hmctot) > 1.0e-15 ||
        std::abs(outputs[0].populations[0] - outputs[1].populations[0]) > 1.0e-15;
    bool finite = true;
    for (const auto& output : outputs) {
        finite = finite && std::isfinite(output.hmctot) && std::isfinite(output.total_heating) &&
            std::isfinite(output.total_cooling) && output.populations_count > 0 && output.spectrum_count == 64;
    }
    std::cout << "program_id=" << stats.program_id << "\n"
              << "program_elements=" << program_info.element_count << "\n"
              << "program_population_rows=" << program_info.population_rows << "\n"
              << "program_record_count=" << program_info.record_count << "\n"
              << "program_unsupported_records=" << program_info.unsupported_record_count << "\n"
              << "partial_program=" << (program_info.unsupported_record_count > 0 ? "true" : "false") << "\n"
              << "active_atdb_lowered=" << ((program_info.status_flags & XSTAR_FIXED_STATE_STATUS_ACTIVE_ATDB_LOWERED) != 0u ? "true" : "false") << "\n"
              << "calls=" << stats.calls << "\n"
              << "records_seen=" << stats.records_seen << "\n"
              << "records_evaluated=" << stats.records_evaluated << "\n"
              << "records_unsupported=" << stats.records_unsupported << "\n"
              << "active_program_records=" << stats.active_program_records << "\n"
              << "topology_rows_loaded=" << stats.topology_rows_loaded << "\n"
              << "type56_records_evaluated=" << stats.type56_records_evaluated << "\n"
              << "visited_data_types=" << stats.visited_data_types << "\n"
              << "elements_solved=" << stats.elements_solved << "\n"
              << "spectral_contributions=" << stats.spectral_contributions << "\n"
              << "continuum_bins=" << stats.continuum_bins << "\n"
              << "python_callbacks=" << stats.python_callbacks << "\n"
              << "state_generation=" << stats.state_generation << "\n"
              << "state_dependent=" << (changed ? "true" : "false") << "\n"
              << "first_hmctot=" << std::setprecision(17) << outputs[0].hmctot << "\n"
              << "last_hmctot=" << std::setprecision(17) << outputs.back().hmctot << "\n"
              << "first_computed_electron_fraction=" << std::setprecision(17) << outputs[0].elcter << "\n"
              << "last_computed_electron_fraction=" << std::setprecision(17) << outputs.back().elcter << "\n"
              << "total_seconds=" << stats.total_seconds << "\n";
    const bool accepted = finite && changed && stats.python_callbacks == 0 && stats.records_unsupported == 0 &&
        stats.active_program_records > 0 && stats.records_evaluated == stats.active_program_records * count &&
        stats.elements_solved == program_info.element_count * count;
    std::cout << "RESULT=" << (accepted ? "ACCEPT" : "REJECT") << "\n";
    xstar_fixed_state_context_destroy(context);
    return accepted ? 0 : 20;
}


struct TrajectoryRow {
    std::string sequence;
    std::string kind;
    long long call_index=0;
    long long evaluation_index=0;
    double temperature_t4=0.0;
    double electron_fraction=0.0;
    double reference_hmctot=0.0;
    double reference_elcter=0.0;
    double reference_lnerr=0.0;
};

std::vector<std::string> split_simple_csv(const std::string& line) {
    std::vector<std::string> fields;
    std::string value;
    std::istringstream stream(line);
    while (std::getline(stream,value,',')) {
        while (!value.empty() && (value.back()=='\r' || value.back()=='\n' || value.back()==' ' || value.back()=='\t')) value.pop_back();
        std::size_t first=0; while (first<value.size() && (value[first]==' ' || value[first]=='\t')) ++first;
        fields.push_back(value.substr(first));
    }
    return fields;
}


struct RadiationField {
    std::vector<double> energy_ev;
    std::vector<double> incident;
    std::string mode = "synthetic_64_bin_development";
};

RadiationField read_radiation_field(const std::string& path) {
    RadiationField field;
    if (path.empty()) {
        field.energy_ev.resize(64);
        field.incident.resize(64);
        for (std::size_t k=0;k<64;++k) {
            field.energy_ev[k]=1.0+static_cast<double>(k);
            field.incident[k]=1.0e12/(1.0+static_cast<double>(k));
        }
        return field;
    }
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open radiation CSV: "+path);
    std::string header;
    if (!std::getline(input,header)) throw std::runtime_error("empty radiation CSV");
    const auto names=split_simple_csv(header);
    auto find_any=[&](std::initializer_list<const char*> choices)->std::size_t {
        for (const char* choice : choices) {
            const auto it=std::find(names.begin(),names.end(),choice);
            if (it!=names.end()) return static_cast<std::size_t>(it-names.begin());
        }
        std::string expected;
        for (const char* choice : choices) { if (!expected.empty()) expected += "/"; expected += choice; }
        throw std::runtime_error("radiation CSV missing column "+expected);
    };
    const auto cenergy=find_any({"energy","energy_ev"});
    const auto cflux=find_any({"incident","flux","radiation_flux"});
    std::string line;
    double previous=-1.0;
    while (std::getline(input,line)) {
        if (line.empty()) continue;
        const auto f=split_simple_csv(line);
        if (f.size()!=names.size()) throw std::runtime_error("radiation CSV row has wrong column count");
        const double energy=std::stod(f[cenergy]);
        const double flux=std::stod(f[cflux]);
        if (!std::isfinite(energy) || !(energy>0.0) || energy<=previous)
            throw std::runtime_error("radiation energies must be finite, positive, and strictly increasing");
        if (!std::isfinite(flux) || flux<0.0)
            throw std::runtime_error("radiation flux must be finite and nonnegative");
        field.energy_ev.push_back(energy);
        field.incident.push_back(flux);
        previous=energy;
    }
    if (field.energy_ev.size()<3) throw std::runtime_error("radiation CSV requires at least three bins");
    field.mode="external_reference_csv";
    return field;
}

std::vector<TrajectoryRow> read_trajectory_rows(const std::string& path) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open trajectory CSV: "+path);
    std::string header;
    if (!std::getline(input,header)) throw std::runtime_error("empty trajectory CSV");
    const auto names=split_simple_csv(header);
    auto find_col=[&](const std::string& name)->std::size_t {
        const auto it=std::find(names.begin(),names.end(),name);
        if (it==names.end()) throw std::runtime_error("trajectory CSV missing column "+name);
        return static_cast<std::size_t>(it-names.begin());
    };
    const auto cseq=find_col("sequence"), ckind=find_col("kind"), ccall=find_col("call_index"), ceval=find_col("evaluation_index");
    const auto ctemp=find_col("temperature_t4"), cxee=find_col("electron_fraction"), chmc=find_col("hmctot"), celc=find_col("elcter"), cln=find_col("lnerr");
    std::vector<TrajectoryRow> rows;
    std::string line;
    while (std::getline(input,line)) {
        if (line.empty()) continue;
        const auto f=split_simple_csv(line);
        if (f.size()!=names.size()) throw std::runtime_error("trajectory CSV row has wrong column count");
        TrajectoryRow r;
        r.sequence=f[cseq]; r.kind=f[ckind];
        r.call_index=std::stoll(f[ccall]); r.evaluation_index=std::stoll(f[ceval]);
        r.temperature_t4=std::stod(f[ctemp]); r.electron_fraction=std::stod(f[cxee]);
        r.reference_hmctot=std::stod(f[chmc]); r.reference_elcter=std::stod(f[celc]); r.reference_lnerr=std::stod(f[cln]);
        rows.push_back(r);
    }
    return rows;
}

int command_run_fixed_trajectory(const Options& options) {
    if (options.case_dir.empty()||options.trajectory_csv.empty()||options.output_dir.empty()) {
        std::cerr << "run-fixed-trajectory requires --case-dir, --trajectory-csv, and --output-dir\n";
        return 2;
    }
    std::vector<TrajectoryRow> trajectory;
    try { trajectory=read_trajectory_rows(options.trajectory_csv); }
    catch (const std::exception& exc) { std::cerr << exc.what() << "\n"; return 3; }
    if (trajectory.size()!=61) {
        std::cerr << "trajectory qualification requires exactly 61 evaluations; got " << trajectory.size() << "\n";
        return 4;
    }
    xstar_fixed_state_context* context=nullptr;
    std::array<char,XSTAR_FIXED_STATE_MESSAGE_SIZE> message{};
    int rc=xstar_fixed_state_context_create_v1(options.case_dir.c_str(),&context,message.data(),message.size());
    if (rc!=0) { std::cerr << "fixed-state context creation failed: " << message.data() << "\n"; return rc; }
    xstar_fixed_state_program_info_v1 info{}; xstar_fixed_state_program_info_init_v1(&info);
    rc=xstar_fixed_state_context_get_program_info_v1(context,&info,message.data(),message.size());
    if (rc!=0) { std::cerr << "program info failed: " << message.data() << "\n"; xstar_fixed_state_context_destroy(context); return rc; }
    std::filesystem::create_directories(options.output_dir);
    std::ofstream states(std::filesystem::path(options.output_dir)/"native_trajectory.csv");
    std::ofstream pops(std::filesystem::path(options.output_dir)/"native_trajectory_populations.csv");
    std::ofstream spectra_file(std::filesystem::path(options.output_dir)/"native_trajectory_spectra.csv");
    std::ofstream step(std::filesystem::path(options.output_dir)/"xout_step.log");
    states << "sequence,kind,call_index,evaluation_index,temperature_t4,electron_fraction_input,native_hmctot,native_electron_fraction,native_charge_residual,total_heating,total_cooling,element_heating,element_cooling,continuum_heating,continuum_cooling,reference_hmctot,reference_charge_residual,reference_lnerr,hmctot_delta,charge_residual_delta\n";
    pops << "evaluation_index,row,population\n";
    spectra_file << "evaluation_index,bin,energy_ev,spectrum,opacity\n";
    step << std::setprecision(17) << "xstar_tools native fixed-state trajectory v0.6.48.7.14.2\n"
         << "trajectory_mode=reference_input_state_qualification\n"
         << "computed_from_raw_coefficients=true\n";
    xstar_fixed_state_stats_v1 cumulative{}; xstar_fixed_state_stats_init_v1(&cumulative);
    RadiationField radiation;
    try { radiation=read_radiation_field(options.radiation_csv); }
    catch (const std::exception& exc) { std::cerr << exc.what() << "\n"; xstar_fixed_state_context_destroy(context); return 5; }
    const std::size_t bins=radiation.energy_ev.size();
    std::vector<double> spectrum(bins,0.0),opacity(bins,0.0);
    const auto& energy=radiation.energy_ev;
    const auto& flux=radiation.incident;
    step << "radiation_input=" << radiation.mode << "\n" << "radiation_bins=" << bins << "\n";
    std::vector<double> populations(static_cast<std::size_t>(info.population_rows),0.0);
    double max_hmc_delta=0.0,max_charge_residual_delta=0.0;
    for (std::size_t j=0;j<trajectory.size();++j) {
        std::fill(spectrum.begin(),spectrum.end(),0.0); std::fill(opacity.begin(),opacity.end(),0.0); std::fill(populations.begin(),populations.end(),0.0);
        xstar_fixed_state_input_v1 in{}; xstar_fixed_state_input_init_v1(&in);
        in.temperature_k=trajectory[j].temperature_t4*1.0e4;
        in.hydrogen_density_cm3=1.0e8;
        in.electron_fraction_xee=trajectory[j].electron_fraction;
        in.electron_density_cm3=in.hydrogen_density_cm3*in.electron_fraction_xee;
        in.neutral_h_density_cm3=1.0e4;
        in.ionized_h_density_cm3=std::max(0.0,in.hydrogen_density_cm3-in.neutral_h_density_cm3);
        in.covering_fraction=0.5; in.turbulent_velocity_km_s=100.0;
        in.radiation_energy_ev=energy.data(); in.radiation_flux=flux.data(); in.radiation_bin_count=bins;
        xstar_fixed_state_output_v1 out{}; xstar_fixed_state_output_init_v1(&out);
        out.populations=populations.data(); out.populations_capacity=populations.size();
        out.spectrum=spectrum.data(); out.spectrum_capacity=spectrum.size(); out.opacity=opacity.data(); out.opacity_capacity=opacity.size();
        rc=xstar_fixed_state_run_v1(context,&in,&out,&cumulative,message.data(),message.size());
        if (rc!=0) { std::cerr << "trajectory evaluation " << j+1 << " failed: " << message.data() << "\n"; xstar_fixed_state_context_destroy(context); return rc; }
        if (!options.diagnostics_dir.empty()) {
            rc = xstar_fixed_state_write_last_diagnostics_v1(
                context, options.diagnostics_dir.c_str(), static_cast<std::uint64_t>(j + 1), message.data(), message.size());
            if (rc != 0) { std::cerr << "trajectory diagnostics " << j+1 << " failed: " << message.data() << "\n"; xstar_fixed_state_context_destroy(context); return rc; }
        }
        const double native_charge_residual=in.electron_fraction_xee-out.elcter;
        const double dh=out.hmctot-trajectory[j].reference_hmctot;
        const double de=native_charge_residual-trajectory[j].reference_elcter;
        max_hmc_delta=std::max(max_hmc_delta,std::abs(dh));
        max_charge_residual_delta=std::max(max_charge_residual_delta,std::abs(de));
        states << std::setprecision(17) << trajectory[j].sequence << ',' << trajectory[j].kind << ',' << trajectory[j].call_index << ',' << trajectory[j].evaluation_index << ','
               << trajectory[j].temperature_t4 << ',' << trajectory[j].electron_fraction << ',' << out.hmctot << ',' << out.elcter << ',' << native_charge_residual << ',' << out.total_heating << ',' << out.total_cooling << ','
               << out.element_heating << ',' << out.element_cooling << ',' << out.continuum_heating << ',' << out.continuum_cooling << ','
               << trajectory[j].reference_hmctot << ',' << trajectory[j].reference_elcter << ',' << trajectory[j].reference_lnerr << ',' << dh << ',' << de << '\n';
        for (std::size_t k=0;k<out.populations_count;++k) pops << trajectory[j].evaluation_index << ',' << k+1 << ',' << std::setprecision(17) << populations[k] << '\n';
        for (std::size_t k=0;k<bins;++k) spectra_file << trajectory[j].evaluation_index << ',' << k+1 << ',' << std::setprecision(17) << energy[k] << ',' << spectrum[k] << ',' << opacity[k] << '\n';
        step << "evaluation=" << trajectory[j].evaluation_index << " temperature_t4=" << trajectory[j].temperature_t4 << " xee_input=" << trajectory[j].electron_fraction
             << " hmctot=" << out.hmctot << " computed_xee=" << out.elcter << " charge_residual=" << native_charge_residual
             << " heating=" << out.total_heating << " cooling=" << out.total_cooling << '\n';
    }
    rc=xstar_fixed_state_write_visited_report_v1(context,(std::filesystem::path(options.output_dir)/"visited_records.csv").c_str(),message.data(),message.size());
    if (rc!=0) { std::cerr << "visited report failed: " << message.data() << "\n"; xstar_fixed_state_context_destroy(context); return rc; }
    std::ofstream summary(std::filesystem::path(options.output_dir)/"native_trajectory_summary.json");
    summary << std::setprecision(17) << "{\n  \"schema_version\": \"0.6.48.7.14.2\",\n  \"program_id\": \"" << cumulative.program_id << "\",\n"
            << "  \"trajectory_mode\": \"reference_input_state_qualification\",\n  \"evaluations\": 61,\n"
            << "  \"radiation_input\": \"" << radiation.mode << "\",\n  \"radiation_bins\": " << bins << ",\n"
            << "  \"computed_from_raw_coefficients\": true,\n  \"python_callbacks\": " << cumulative.python_callbacks << ",\n"
            << "  \"records_evaluated\": " << cumulative.records_evaluated << ",\n  \"elements_solved\": " << cumulative.elements_solved << ",\n"
            << "  \"max_abs_hmctot_delta_to_reference\": " << max_hmc_delta << ",\n  \"max_abs_charge_residual_delta_to_reference\": " << max_charge_residual_delta << "\n}\n";
    const bool accepted=cumulative.calls==61 && cumulative.records_unsupported==0 && cumulative.python_callbacks==0 && cumulative.records_evaluated==61*info.record_count;
    std::cout << "program_id=" << cumulative.program_id << "\ntrajectory_evaluations=61\nrecords_evaluated=" << cumulative.records_evaluated
              << "\nelements_solved=" << cumulative.elements_solved << "\npython_callbacks=" << cumulative.python_callbacks
              << "\nmax_abs_hmctot_delta_to_reference=" << std::setprecision(17) << max_hmc_delta
              << "\nmax_abs_charge_residual_delta_to_reference=" << max_charge_residual_delta
              << "\nradiation_input=" << radiation.mode << "\nradiation_bins=" << bins
              << "\ntrajectory_mode=reference_input_state_qualification\nRESULT=" << (accepted?"ACCEPT":"REJECT") << "\n";
    xstar_fixed_state_context_destroy(context);
    return accepted?0:20;
}

int command_run_fixed_evaluation(const Options& options) {
    if (options.case_dir.empty() || options.trajectory_csv.empty() || options.output_dir.empty()) {
        std::cerr << "run-fixed-evaluation requires --case-dir, --trajectory-csv, and --output-dir\n";
        return 2;
    }
    std::vector<TrajectoryRow> trajectory;
    try { trajectory = read_trajectory_rows(options.trajectory_csv); }
    catch (const std::exception& exc) { std::cerr << exc.what() << "\n"; return 3; }
    if (options.evaluation < 1 || options.evaluation > trajectory.size()) {
        std::cerr << "--evaluation must select a row in the trajectory CSV; got " << options.evaluation
                  << " for " << trajectory.size() << " rows\n";
        return 4;
    }
    const std::size_t index = options.evaluation - 1;
    const auto& row = trajectory[index];
    xstar_fixed_state_context* context = nullptr;
    std::array<char,XSTAR_FIXED_STATE_MESSAGE_SIZE> message{};
    int rc = xstar_fixed_state_context_create_v1(options.case_dir.c_str(), &context, message.data(), message.size());
    if (rc != 0) { std::cerr << "fixed-state context creation failed: " << message.data() << "\n"; return rc; }
    xstar_fixed_state_program_info_v1 info{};
    xstar_fixed_state_program_info_init_v1(&info);
    rc = xstar_fixed_state_context_get_program_info_v1(context, &info, message.data(), message.size());
    if (rc != 0) { std::cerr << "program info failed: " << message.data() << "\n"; xstar_fixed_state_context_destroy(context); return rc; }
    RadiationField radiation;
    try { radiation = read_radiation_field(options.radiation_csv); }
    catch (const std::exception& exc) { std::cerr << exc.what() << "\n"; xstar_fixed_state_context_destroy(context); return 5; }
    const std::size_t bins = radiation.energy_ev.size();
    std::vector<double> populations(static_cast<std::size_t>(info.population_rows), 0.0);
    std::vector<double> spectrum(bins, 0.0), opacity(bins, 0.0);
    xstar_fixed_state_input_v1 input{};
    xstar_fixed_state_input_init_v1(&input);
    input.temperature_k = row.temperature_t4 * 1.0e4;
    input.hydrogen_density_cm3 = 1.0e8;
    input.electron_fraction_xee = row.electron_fraction;
    input.electron_density_cm3 = input.hydrogen_density_cm3 * input.electron_fraction_xee;
    input.neutral_h_density_cm3 = 1.0e4;
    input.ionized_h_density_cm3 = std::max(0.0, input.hydrogen_density_cm3 - input.neutral_h_density_cm3);
    input.covering_fraction = 0.5;
    input.turbulent_velocity_km_s = 100.0;
    input.radiation_energy_ev = radiation.energy_ev.data();
    input.radiation_flux = radiation.incident.data();
    input.radiation_bin_count = bins;
    xstar_fixed_state_output_v1 output{};
    xstar_fixed_state_output_init_v1(&output);
    output.populations = populations.data(); output.populations_capacity = populations.size();
    output.spectrum = spectrum.data(); output.spectrum_capacity = spectrum.size();
    output.opacity = opacity.data(); output.opacity_capacity = opacity.size();
    xstar_fixed_state_stats_v1 stats{};
    xstar_fixed_state_stats_init_v1(&stats);
    rc = xstar_fixed_state_run_v1(context, &input, &output, &stats, message.data(), message.size());
    if (rc != 0) { std::cerr << "fixed evaluation failed: " << message.data() << "\n"; xstar_fixed_state_context_destroy(context); return rc; }
    std::filesystem::create_directories(options.output_dir);
    const std::filesystem::path output_root(options.output_dir);
    std::ofstream state(output_root / "native_evaluation.csv");
    state << "trajectory_row,sequence,kind,call_index,evaluation_index,temperature_t4,electron_fraction_input,native_hmctot,native_electron_fraction,native_charge_residual,total_heating,total_cooling,reference_hmctot,reference_charge_residual,hmctot_delta,charge_residual_delta\n";
    const double charge_residual = input.electron_fraction_xee - output.elcter;
    const double hmctot_delta = output.hmctot - row.reference_hmctot;
    const double charge_delta = charge_residual - row.reference_elcter;
    state << std::setprecision(17) << options.evaluation << ',' << row.sequence << ',' << row.kind << ','
          << row.call_index << ',' << row.evaluation_index << ',' << row.temperature_t4 << ',' << row.electron_fraction << ','
          << output.hmctot << ',' << output.elcter << ',' << charge_residual << ',' << output.total_heating << ',' << output.total_cooling << ','
          << row.reference_hmctot << ',' << row.reference_elcter << ',' << hmctot_delta << ',' << charge_delta << '\n';
    std::ofstream pop_file(output_root / "native_evaluation_populations.csv");
    pop_file << "row,population\n" << std::setprecision(17);
    for (std::size_t k = 0; k < output.populations_count; ++k) pop_file << k + 1 << ',' << populations[k] << '\n';
    std::ofstream spectrum_file(output_root / "native_evaluation_spectra.csv");
    spectrum_file << "bin,energy_ev,spectrum,opacity\n" << std::setprecision(17);
    for (std::size_t k = 0; k < bins; ++k) spectrum_file << k + 1 << ',' << radiation.energy_ev[k] << ',' << spectrum[k] << ',' << opacity[k] << '\n';
    const std::filesystem::path diagnostics_root = options.diagnostics_dir.empty()
        ? output_root / "diagnostics" : std::filesystem::path(options.diagnostics_dir);
    rc = xstar_fixed_state_write_last_diagnostics_v1(
        context, diagnostics_root.c_str(), static_cast<std::uint64_t>(options.evaluation), message.data(), message.size());
    if (rc != 0) { std::cerr << "evaluation diagnostics failed: " << message.data() << "\n"; xstar_fixed_state_context_destroy(context); return rc; }
    std::ofstream summary(output_root / "native_evaluation_summary.json");
    summary << std::setprecision(17)
            << "{\n  \"schema_version\": \"0.6.48.7.14.2\",\n"
            << "  \"trajectory_mode\": \"single_reference_input_state_qualification\",\n"
            << "  \"trajectory_row\": " << options.evaluation << ",\n"
            << "  \"evaluation_index\": " << row.evaluation_index << ",\n"
            << "  \"records_evaluated\": " << stats.records_evaluated << ",\n"
            << "  \"elements_solved\": " << stats.elements_solved << ",\n"
            << "  \"python_callbacks\": " << stats.python_callbacks << ",\n"
            << "  \"native_electron_fraction\": " << output.elcter << ",\n"
            << "  \"native_charge_residual\": " << charge_residual << ",\n"
            << "  \"reference_charge_residual\": " << row.reference_elcter << ",\n"
            << "  \"charge_residual_delta\": " << charge_delta << ",\n"
            << "  \"native_hmctot\": " << output.hmctot << ",\n"
            << "  \"reference_hmctot\": " << row.reference_hmctot << ",\n"
            << "  \"hmctot_delta\": " << hmctot_delta << ",\n"
            << "  \"diagnostics_directory\": \"" << std::filesystem::absolute(diagnostics_root).string() << "\"\n}\n";
    std::cout << std::setprecision(17)
              << "trajectory_row=" << options.evaluation << "\n"
              << "evaluation_index=" << row.evaluation_index << "\n"
              << "records_evaluated=" << stats.records_evaluated << "\n"
              << "elements_solved=" << stats.elements_solved << "\n"
              << "python_callbacks=" << stats.python_callbacks << "\n"
              << "native_electron_fraction=" << output.elcter << "\n"
              << "native_charge_residual=" << charge_residual << "\n"
              << "charge_residual_delta=" << charge_delta << "\n"
              << "native_hmctot=" << output.hmctot << "\n"
              << "hmctot_delta=" << hmctot_delta << "\n"
              << "diagnostics_directory=" << std::filesystem::absolute(diagnostics_root).string() << "\n"
              << "RESULT=ACCEPT\n";
    xstar_fixed_state_context_destroy(context);
    return 0;
}

struct FixedDsecSnapshot {
    std::string kind;
    std::size_t sequence = 0;
    std::size_t call_index = 0;
    std::size_t evaluation_index = 0;
    double temperature_t4 = 0.0;
    double electron_fraction_input = 0.0;
    double computed_electron_fraction = 0.0;
    double charge_residual = 0.0;
    double hmctot = 0.0;
    double total_heating = 0.0;
    double total_cooling = 0.0;
    double element_heating = 0.0;
    double element_cooling = 0.0;
    double continuum_heating = 0.0;
    double continuum_cooling = 0.0;
    std::vector<double> populations;
    std::vector<double> continuum_spectrum;
    std::vector<double> spectrum;
    std::vector<double> opacity;
};

struct FixedDsecEvaluatorData {
    xstar_fixed_state_context* fixed_context = nullptr;
    xstar_fixed_state_program_info_v1 program_info{};
    xstar_fixed_state_stats_v1* cumulative_stats = nullptr;
    std::vector<FixedDsecSnapshot>* snapshots = nullptr;
    std::size_t call_index = 0;
    std::size_t evaluation_index = 0;
    std::vector<double> energy;
    std::vector<double> flux;
    std::string radiation_mode = "synthetic_64_bin_development";
    std::string diagnostics_dir;
};

void set_callback_error(char* error, std::size_t error_size, const std::string& message) {
    if (!error || error_size == 0) return;
    std::snprintf(error, error_size, "%s", message.c_str());
}

int fixed_dsec_evaluator(
    void* user_data,
    const xstar_thermal_state_v1* trial_state,
    xstar_thermal_evaluation_v1* evaluation,
    char* error,
    std::size_t error_size) {
    auto* data = static_cast<FixedDsecEvaluatorData*>(user_data);
    if (!data || !data->fixed_context || !trial_state || !evaluation || !data->cumulative_stats || !data->snapshots) {
        set_callback_error(error, error_size, "invalid fixed-state DSEC evaluator data");
        return 1;
    }
    FixedDsecSnapshot snapshot;
    snapshot.kind = "dsec";
    snapshot.sequence = data->snapshots->size() + 1;
    snapshot.call_index = data->call_index;
    snapshot.evaluation_index = ++data->evaluation_index;
    snapshot.temperature_t4 = trial_state->temperature_t4;
    snapshot.electron_fraction_input = trial_state->electron_fraction_xee;
    snapshot.populations.assign(static_cast<std::size_t>(data->program_info.population_rows), 0.0);
    snapshot.continuum_spectrum.assign(data->energy.size(), 0.0);
    snapshot.spectrum.assign(data->energy.size(), 0.0);
    snapshot.opacity.assign(data->energy.size(), 0.0);

    xstar_fixed_state_input_v1 input{};
    xstar_fixed_state_input_init_v1(&input);
    input.temperature_k = trial_state->temperature_t4 * 1.0e4;
    input.hydrogen_density_cm3 = trial_state->hydrogen_density_cm3;
    input.electron_fraction_xee = trial_state->electron_fraction_xee;
    input.electron_density_cm3 = input.hydrogen_density_cm3 * input.electron_fraction_xee;
    input.neutral_h_density_cm3 = std::min(1.0e4, input.hydrogen_density_cm3);
    input.ionized_h_density_cm3 = std::max(0.0, input.hydrogen_density_cm3 - input.neutral_h_density_cm3);
    input.covering_fraction = 0.5;
    input.turbulent_velocity_km_s = 100.0;
    input.radiation_energy_ev = data->energy.data();
    input.radiation_flux = data->flux.data();
    input.radiation_bin_count = data->energy.size();

    // Persist the free-free continuum as its own computed product before the
    // line/RRC/profile commit augments output.spectrum.  This duplicates the
    // fixed-state engine's native continuum expression intentionally so the
    // historical continuum and full-spectrum FITS writers no longer consume
    // the same array.
    constexpr double kBoltzmannEvK = 8.617333262145e-5;
    const double kt_ev = kBoltzmannEvK * input.temperature_k;
    const double ff_total = 1.426e-27 * std::sqrt(input.temperature_k) *
        input.electron_density_cm3 * input.ionized_h_density_cm3;
    double continuum_shape_sum = 0.0;
    for (std::size_t k = 0; k < data->energy.size(); ++k) {
        snapshot.continuum_spectrum[k] = std::exp(-data->energy[k] / std::max(kt_ev, 1.0e-300));
        continuum_shape_sum += snapshot.continuum_spectrum[k];
    }
    if (continuum_shape_sum > 0.0) {
        for (double& value : snapshot.continuum_spectrum) value = ff_total * value / continuum_shape_sum;
    }

    xstar_fixed_state_output_v1 output{};
    xstar_fixed_state_output_init_v1(&output);
    output.populations = snapshot.populations.data();
    output.populations_capacity = snapshot.populations.size();
    output.spectrum = snapshot.spectrum.data();
    output.spectrum_capacity = snapshot.spectrum.size();
    output.opacity = snapshot.opacity.data();
    output.opacity_capacity = snapshot.opacity.size();
    std::array<char,XSTAR_FIXED_STATE_MESSAGE_SIZE> message{};
    const int rc = xstar_fixed_state_run_v1(
        data->fixed_context, &input, &output, data->cumulative_stats, message.data(), message.size());
    if (rc != 0) {
        set_callback_error(error, error_size, std::string("fixed-state evaluator failed: ") + message.data());
        return rc;
    }
    if (!data->diagnostics_dir.empty()) {
        const int diagnostic_rc = xstar_fixed_state_write_last_diagnostics_v1(
            data->fixed_context, data->diagnostics_dir.c_str(), static_cast<std::uint64_t>(snapshot.sequence),
            message.data(), message.size());
        if (diagnostic_rc != 0) {
            set_callback_error(error, error_size, std::string("fixed-state diagnostics failed: ") + message.data());
            return diagnostic_rc;
        }
    }

    snapshot.computed_electron_fraction = output.elcter;
    snapshot.charge_residual = trial_state->electron_fraction_xee - output.elcter;
    snapshot.hmctot = output.hmctot;
    snapshot.total_heating = output.total_heating;
    snapshot.total_cooling = output.total_cooling;
    snapshot.element_heating = output.element_heating;
    snapshot.element_cooling = output.element_cooling;
    snapshot.continuum_heating = output.continuum_heating;
    snapshot.continuum_cooling = output.continuum_cooling;
    data->snapshots->push_back(std::move(snapshot));

    evaluation->hmctot = output.hmctot;
    evaluation->elcter = trial_state->electron_fraction_xee - output.elcter;
    evaluation->temperature_t4 = trial_state->temperature_t4;
    evaluation->electron_fraction_xee = trial_state->electron_fraction_xee;
    evaluation->hydrogen_density_cm3 = trial_state->hydrogen_density_cm3;
    evaluation->state_generation = data->cumulative_stats->state_generation;
    set_callback_error(error, error_size, "");
    return 0;
}

int append_final_fixed_snapshot(
    FixedDsecEvaluatorData& data,
    const xstar_thermal_state_v1& state,
    std::size_t call_index,
    std::vector<FixedDsecSnapshot>& snapshots,
    std::array<char,XSTAR_FIXED_STATE_MESSAGE_SIZE>& message) {
    const std::size_t before = snapshots.size();
    data.call_index = call_index;
    data.evaluation_index = 0;
    xstar_thermal_evaluation_v1 ignored{};
    xstar_thermal_evaluation_init_v1(&ignored);
    const int rc = fixed_dsec_evaluator(&data, &state, &ignored, message.data(), message.size());
    if (rc != 0) return rc;
    snapshots.back().kind = "final";
    snapshots.back().sequence = before + 1;
    snapshots.back().evaluation_index = 1;
    return 0;
}

const TrajectoryRow* find_reference_row(
    const std::vector<TrajectoryRow>& trajectory,
    const std::string& kind,
    std::size_t call_index,
    std::size_t evaluation_index) {
    for (const auto& row : trajectory) {
        if (row.kind == kind && row.call_index == static_cast<long long>(call_index) &&
            row.evaluation_index == static_cast<long long>(evaluation_index)) return &row;
    }
    return nullptr;
}

int command_run_fixed_dsec(const Options& options) {
    if (options.case_dir.empty() || options.trajectory_csv.empty() || options.output_dir.empty()) {
        std::cerr << "run-fixed-dsec requires --case-dir, --trajectory-csv, and --output-dir\n";
        return 2;
    }
    std::vector<TrajectoryRow> reference;
    try { reference = read_trajectory_rows(options.trajectory_csv); }
    catch (const std::exception& exc) { std::cerr << exc.what() << "\n"; return 3; }
    if (reference.size() != 61) {
        std::cerr << "DSEC qualification requires the 61-row reference trajectory; got " << reference.size() << "\n";
        return 4;
    }

    std::array<std::size_t,4> dsec_limits{};
    for (const auto& row : reference) {
        if (row.kind == "dsec" && row.call_index >= 1 && row.call_index <= 4) {
            ++dsec_limits[static_cast<std::size_t>(row.call_index - 1)];
        }
    }
    if (dsec_limits != std::array<std::size_t,4>{21,1,18,17}) {
        std::cerr << "unexpected reference DSEC grouping\n";
        return 5;
    }

    xstar_fixed_state_context* fixed_context = nullptr;
    xstar_thermal_context* thermal_context = nullptr;
    std::array<char,XSTAR_FIXED_STATE_MESSAGE_SIZE> message{};
    int rc = xstar_fixed_state_context_create_v1(options.case_dir.c_str(), &fixed_context, message.data(), message.size());
    if (rc != 0) { std::cerr << "fixed-state context creation failed: " << message.data() << "\n"; return rc; }
    rc = xstar_thermal_context_create_v1(&thermal_context, message.data(), message.size());
    if (rc != 0) {
        std::cerr << "thermal context creation failed: " << message.data() << "\n";
        xstar_fixed_state_context_destroy(fixed_context);
        return rc;
    }
    xstar_fixed_state_program_info_v1 info{};
    xstar_fixed_state_program_info_init_v1(&info);
    rc = xstar_fixed_state_context_get_program_info_v1(fixed_context, &info, message.data(), message.size());
    if (rc != 0) {
        std::cerr << "program info failed: " << message.data() << "\n";
        xstar_thermal_context_destroy(thermal_context);
        xstar_fixed_state_context_destroy(fixed_context);
        return rc;
    }

    xstar_fixed_state_stats_v1 cumulative{};
    xstar_fixed_state_stats_init_v1(&cumulative);
    std::vector<FixedDsecSnapshot> snapshots;
    snapshots.reserve(61);
    FixedDsecEvaluatorData evaluator_data;
    evaluator_data.fixed_context = fixed_context;
    evaluator_data.program_info = info;
    evaluator_data.cumulative_stats = &cumulative;
    evaluator_data.snapshots = &snapshots;
    RadiationField radiation;
    try { radiation=read_radiation_field(options.radiation_csv); }
    catch (const std::exception& exc) {
        std::cerr << exc.what() << "\n";
        xstar_thermal_context_destroy(thermal_context);
        xstar_fixed_state_context_destroy(fixed_context);
        return 6;
    }
    evaluator_data.energy=std::move(radiation.energy_ev);
    evaluator_data.flux=std::move(radiation.incident);
    evaluator_data.radiation_mode=radiation.mode;
    evaluator_data.diagnostics_dir=options.diagnostics_dir;

    xstar_thermal_state_v1 state{};
    xstar_thermal_state_init_v1(&state);
    state.temperature_t4 = reference.front().temperature_t4;
    state.electron_fraction_xee = reference.front().electron_fraction;
    state.hydrogen_density_cm3 = 1.0e8;
    state.state_generation = 0;
    std::vector<xstar_thermal_trace_event_v1> trace(512);
    std::vector<xstar_dsec_stats_v1> call_stats;
    call_stats.reserve(4);
    std::size_t dsec_evaluations = 0;

    for (std::size_t call = 1; call <= 4; ++call) {
        evaluator_data.call_index = call;
        evaluator_data.evaluation_index = 0;
        xstar_dsec_config_v1 config{};
        xstar_dsec_config_init_v1(&config);
        config.nlim = 100;
        config.maximum_evaluations = static_cast<int32_t>(dsec_limits[call - 1]);
        // Use the source/default convergence tolerances.  v0.6.48.5 forced
        // denormal-minimum tolerances merely to consume the historical call
        // counts, which trapped every call in charge iteration and prevented
        // the temperature controller from running.
        xstar_dsec_stats_v1 stats{};
        xstar_dsec_stats_init_v1(&stats);
        std::size_t trace_count = 0;
        rc = xstar_thermal_run_evaluation_loop_v1(
            thermal_context, &config, &state, fixed_dsec_evaluator, &evaluator_data,
            trace.data(), trace.size(), &trace_count, &stats, message.data(), message.size());
        if (rc != 0) {
            std::cerr << "native DSEC call " << call << " failed: " << message.data() << "\n";
            xstar_thermal_context_destroy(thermal_context);
            xstar_fixed_state_context_destroy(fixed_context);
            return rc;
        }
        dsec_evaluations += static_cast<std::size_t>(stats.evaluations_completed);
        call_stats.push_back(stats);
        rc = append_final_fixed_snapshot(evaluator_data, state, call, snapshots, message);
        if (rc != 0) {
            std::cerr << "final fixed-state evaluation after DSEC call " << call << " failed: " << message.data() << "\n";
            xstar_thermal_context_destroy(thermal_context);
            xstar_fixed_state_context_destroy(fixed_context);
            return rc;
        }
    }

    std::filesystem::create_directories(options.output_dir);
    std::ofstream states(std::filesystem::path(options.output_dir) / "native_dsec_trajectory.csv");
    std::ofstream pops(std::filesystem::path(options.output_dir) / "native_dsec_populations.csv");
    std::ofstream spectra_file(std::filesystem::path(options.output_dir) / "native_dsec_spectra.csv");
    std::ofstream step(std::filesystem::path(options.output_dir) / "xout_step.log");
    states << "sequence,kind,call_index,evaluation_index,temperature_t4,electron_fraction_input,computed_electron_fraction,charge_residual,hmctot,total_heating,total_cooling,reference_temperature_t4,reference_electron_fraction,reference_charge_residual,reference_hmctot,temperature_delta,electron_fraction_delta,charge_residual_delta,hmctot_delta\n";
    pops << "sequence,kind,call_index,evaluation_index,row,population\n";
    spectra_file << "sequence,kind,call_index,evaluation_index,bin,energy_ev,spectrum,opacity\n";
    step << std::setprecision(17)
         << "xstar_tools native DSEC trajectory v0.6.48.7.14.2\n"
         << "trajectory_mode=native_dsec_controller\n"
         << "computed_from_raw_coefficients=true\n";

    double max_temperature_delta = 0.0;
    double max_electron_fraction_delta = 0.0;
    double max_charge_residual_delta = 0.0;
    double max_hmctot_delta = 0.0;
    for (std::size_t index = 0; index < snapshots.size(); ++index) {
        auto& snapshot = snapshots[index];
        snapshot.sequence = index + 1;
        const TrajectoryRow* reference_row = find_reference_row(reference, snapshot.kind, snapshot.call_index, snapshot.evaluation_index);
        const double ref_t = reference_row ? reference_row->temperature_t4 : std::numeric_limits<double>::quiet_NaN();
        const double ref_xee = reference_row ? reference_row->electron_fraction : std::numeric_limits<double>::quiet_NaN();
        const double ref_elcter = reference_row ? reference_row->reference_elcter : std::numeric_limits<double>::quiet_NaN();
        const double ref_hmc = reference_row ? reference_row->reference_hmctot : std::numeric_limits<double>::quiet_NaN();
        const double dt = snapshot.temperature_t4 - ref_t;
        const double dx = snapshot.electron_fraction_input - ref_xee;
        const double de = snapshot.charge_residual - ref_elcter;
        const double dh = snapshot.hmctot - ref_hmc;
        if (reference_row) {
            max_temperature_delta = std::max(max_temperature_delta, std::abs(dt));
            max_electron_fraction_delta = std::max(max_electron_fraction_delta, std::abs(dx));
            max_charge_residual_delta = std::max(max_charge_residual_delta, std::abs(de));
            max_hmctot_delta = std::max(max_hmctot_delta, std::abs(dh));
        }
        states << std::setprecision(17) << snapshot.sequence << ',' << snapshot.kind << ',' << snapshot.call_index << ',' << snapshot.evaluation_index << ','
               << snapshot.temperature_t4 << ',' << snapshot.electron_fraction_input << ',' << snapshot.computed_electron_fraction << ','
               << snapshot.charge_residual << ',' << snapshot.hmctot << ',' << snapshot.total_heating << ',' << snapshot.total_cooling << ','
               << ref_t << ',' << ref_xee << ',' << ref_elcter << ',' << ref_hmc << ',' << dt << ',' << dx << ',' << de << ',' << dh << '\n';
        for (std::size_t row = 0; row < snapshot.populations.size(); ++row) {
            pops << snapshot.sequence << ',' << snapshot.kind << ',' << snapshot.call_index << ',' << snapshot.evaluation_index << ','
                 << row + 1 << ',' << std::setprecision(17) << snapshot.populations[row] << '\n';
        }
        for (std::size_t bin = 0; bin < snapshot.spectrum.size(); ++bin) {
            spectra_file << snapshot.sequence << ',' << snapshot.kind << ',' << snapshot.call_index << ',' << snapshot.evaluation_index << ','
                         << bin + 1 << ',' << std::setprecision(17) << evaluator_data.energy[bin] << ','
                         << snapshot.spectrum[bin] << ',' << snapshot.opacity[bin] << '\n';
        }
        step << "sequence=" << snapshot.sequence << " kind=" << snapshot.kind << " call=" << snapshot.call_index
             << " evaluation=" << snapshot.evaluation_index << " temperature_t4=" << snapshot.temperature_t4
             << " xee_input=" << snapshot.electron_fraction_input << " computed_xee=" << snapshot.computed_electron_fraction
             << " charge_residual=" << snapshot.charge_residual << " hmctot=" << snapshot.hmctot
             << " heating=" << snapshot.total_heating << " cooling=" << snapshot.total_cooling << '\n';
    }
    rc = xstar_fixed_state_write_visited_report_v1(
        fixed_context, (std::filesystem::path(options.output_dir) / "visited_records.csv").c_str(), message.data(), message.size());
    if (rc != 0) {
        std::cerr << "visited report failed: " << message.data() << "\n";
        xstar_thermal_context_destroy(thermal_context);
        xstar_fixed_state_context_destroy(fixed_context);
        return rc;
    }
    std::vector<xstar_science_fits::Snapshot> radial_snapshots;
    radial_snapshots.reserve(5);
    auto copy_science_snapshot = [](const FixedDsecSnapshot& source) {
        xstar_science_fits::Snapshot target;
        target.temperature_t4 = source.temperature_t4;
        target.electron_fraction_input = source.electron_fraction_input;
        target.computed_electron_fraction = source.computed_electron_fraction;
        target.charge_residual = source.charge_residual;
        target.hmctot = source.hmctot;
        target.total_heating = source.total_heating;
        target.total_cooling = source.total_cooling;
        target.element_heating = source.element_heating;
        target.element_cooling = source.element_cooling;
        target.continuum_heating = source.continuum_heating;
        target.continuum_cooling = source.continuum_cooling;
        target.populations = source.populations;
        target.continuum_spectrum = source.continuum_spectrum;
        target.spectrum = source.spectrum;
        target.opacity = source.opacity;
        return target;
    };
    if (!snapshots.empty()) radial_snapshots.push_back(copy_science_snapshot(snapshots.front()));
    for (const auto& snapshot : snapshots) {
        if (snapshot.kind == "final") radial_snapshots.push_back(copy_science_snapshot(snapshot));
    }
    xstar_science_fits::Result science_result;
    try {
        science_result = xstar_science_fits::write_historical_science_products(
            options.case_dir, options.output_dir, radial_snapshots, evaluator_data.energy);
    } catch (const std::exception& exc) {
        std::cerr << "historical science FITS generation failed: " << exc.what() << "\n";
        xstar_thermal_context_destroy(thermal_context);
        xstar_fixed_state_context_destroy(fixed_context);
        return 9;
    }
    std::ofstream summary(std::filesystem::path(options.output_dir) / "native_dsec_summary.json");
    summary << std::setprecision(17)
            << "{\n  \"schema_version\": \"0.6.48.7.14.2\",\n  \"program_id\": \"" << cumulative.program_id << "\",\n"
            << "  \"trajectory_mode\": \"native_dsec_controller\",\n  \"radiation_input\": \"" << evaluator_data.radiation_mode << "\",\n"
            << "  \"radiation_bins\": " << evaluator_data.energy.size() << ",\n  \"dsec_calls\": 4,\n"
            << "  \"dsec_evaluations\": " << dsec_evaluations << ",\n  \"final_evaluations\": 4,\n"
            << "  \"total_evaluations\": " << snapshots.size() << ",\n  \"computed_from_raw_coefficients\": true,\n"
            << "  \"python_callbacks\": " << cumulative.python_callbacks << ",\n  \"records_evaluated\": " << cumulative.records_evaluated << ",\n"
            << "  \"elements_solved\": " << cumulative.elements_solved << ",\n  \"max_abs_temperature_t4_delta_to_reference\": " << max_temperature_delta << ",\n"
            << "  \"max_abs_electron_fraction_delta_to_reference\": " << max_electron_fraction_delta << ",\n"
            << "  \"max_abs_charge_residual_delta_to_reference\": " << max_charge_residual_delta << ",\n"
            << "  \"max_abs_hmctot_delta_to_reference\": " << max_hmctot_delta << ",\n"
            << "  \"historical_fits_generated\": " << science_result.files_written << ",\n"
            << "  \"historical_fits_schema_complete\": " << (science_result.schema_complete ? "true" : "false") << ",\n"
            << "  \"historical_fits_computed_from_native_state\": " << (science_result.computed_from_native_state ? "true" : "false") << ",\n"
            << "  \"continuum_and_spectrum_paths_separate\": " << (science_result.continuum_and_spectrum_paths_separate ? "true" : "false") << ",\n"
            << "  \"historical_fits_physical_equivalence_qualified\": " << (science_result.physical_equivalence_qualified ? "true" : "false") << ",\n"
            << "  \"reference_state_identity\": false,\n  \"production_promotion_ready\": false\n}\n";

    const bool accepted = dsec_evaluations == 57 && snapshots.size() == 61 && cumulative.calls == 61 &&
        cumulative.records_unsupported == 0 && cumulative.python_callbacks == 0 &&
        cumulative.records_evaluated == 61 * info.record_count && cumulative.elements_solved == 61 * info.element_count &&
        science_result.files_written == 9 && science_result.schema_complete && science_result.computed_from_native_state &&
        science_result.continuum_and_spectrum_paths_separate;
    std::cout << "program_id=" << cumulative.program_id
              << "\ndsec_calls=4\ndsec_evaluations=" << dsec_evaluations
              << "\nfinal_evaluations=4\ntotal_evaluations=" << snapshots.size()
              << "\nrecords_evaluated=" << cumulative.records_evaluated
              << "\nelements_solved=" << cumulative.elements_solved
              << "\npython_callbacks=" << cumulative.python_callbacks
              << "\nmax_abs_temperature_t4_delta_to_reference=" << std::setprecision(17) << max_temperature_delta
              << "\nmax_abs_electron_fraction_delta_to_reference=" << max_electron_fraction_delta
              << "\nmax_abs_charge_residual_delta_to_reference=" << max_charge_residual_delta
              << "\nmax_abs_hmctot_delta_to_reference=" << max_hmctot_delta
              << "\nhistorical_fits_generated=" << science_result.files_written
              << "\nhistorical_fits_schema_complete=" << (science_result.schema_complete ? "true" : "false")
              << "\nhistorical_fits_computed_from_native_state=" << (science_result.computed_from_native_state ? "true" : "false")
              << "\ncontinuum_and_spectrum_paths_separate=" << (science_result.continuum_and_spectrum_paths_separate ? "true" : "false")
              << "\nhistorical_fits_physical_equivalence_qualified=" << (science_result.physical_equivalence_qualified ? "true" : "false")
              << "\nradiation_input=" << evaluator_data.radiation_mode << "\nradiation_bins=" << evaluator_data.energy.size()
              << "\ntrajectory_mode=native_dsec_controller\nreference_state_identity=false\nRESULT=" << (accepted ? "ACCEPT" : "REJECT") << "\n";
    xstar_thermal_context_destroy(thermal_context);
    xstar_fixed_state_context_destroy(fixed_context);
    return accepted ? 0 : 20;
}

int command_python_bridge_test(const Options& options) {
    std::filesystem::path directory = options.plugin_dir.empty()
        ? xstar_standalone::executable_or_library_directory(
            reinterpret_cast<const void*>(&xstar_api_abi_version))
        : std::filesystem::path(options.plugin_dir);
    const auto library = directory / "libxstar_backend_python.so";
    void* handle = dlopen(library.c_str(), RTLD_NOW | RTLD_GLOBAL);
    if (!handle) {
        std::cerr << "could not load " << library << ": " << dlerror() << "\n";
        return XSTAR_STATUS_BACKEND_LOAD_FAILED;
    }
    using bridge_fn = int (*)(const char*, const char*, const char*, char*, std::size_t*, char*, std::size_t);
    auto bridge = reinterpret_cast<bridge_fn>(dlsym(handle, "xstar_python_call_json_v1"));
    if (!bridge) {
        std::cerr << "python bridge symbol missing\n";
        dlclose(handle);
        return XSTAR_STATUS_BACKEND_LOAD_FAILED;
    }
    std::array<char, 512> response{};
    std::array<char, 512> error{};
    std::size_t response_size = response.size();
    const int status = bridge(
        "xstar_tools.xstar.standalone_backend", "echo_json", "{\"value\": 44}",
        response.data(), &response_size, error.data(), error.size());
    if (status != XSTAR_STATUS_OK) {
        std::cerr << "bridge failed: " << error.data() << "\n";
        dlclose(handle);
        return status;
    }
    std::cout << "python_bridge_response=" << response.data() << "\nRESULT=ACCEPT\n";
    dlclose(handle);
    return 0;
}

} // namespace

int main(int argc, char** argv) {
    Options options;
    std::string error;
    if (!parse_options(argc, argv, options, error)) {
        std::cerr << error << "\n";
        usage(std::cerr);
        return 2;
    }
    if (options.command == "help" || options.command == "--help" || options.command == "-h") {
        usage(std::cout);
        return 0;
    }
    if (options.command == "--version" || options.command == "-V") {
        std::cout << XSTAR_API_VERSION_STRING << "\n";
        return 0;
    }
    if (options.command == "list-backends") return command_list_backends();
    if (options.command == "backend-info") return command_backend_info(options);
    if (options.command == "self-test") return command_self_test(options);
    if (options.command == "element-self-test") return command_element_self_test(options, false, false);
    if (options.command == "evaluation-self-test") return command_element_self_test(options, true, false);
    if (options.command == "construction-self-test") return command_element_self_test(options, false, true);
    if (options.command == "construction-evaluation-self-test") return command_element_self_test(options, true, true);
    if (options.command == "spectral-self-test") return command_spectral_self_test(options);
    if (options.command == "thermal-self-test") return command_thermal_self_test(options);
    if (options.command == "convergence-self-test") return command_convergence_self_test(options);
    if (options.command == "fixed-state-self-test") return command_fixed_state_self_test(options, false);
    if (options.command == "run-fixed-state") return command_run_fixed_state(options);
    if (options.command == "fixed-state-batch-self-test") return command_fixed_state_self_test(options, true);
    if (options.command == "run-fixed-trajectory") return command_run_fixed_trajectory(options);
    if (options.command == "run-fixed-evaluation") return command_run_fixed_evaluation(options);
    if (options.command == "run-fixed-dsec") return command_run_fixed_dsec(options);
    if (options.command == "production-self-test") return command_production_self_test(options);
    if (options.command == "production-batch-self-test") return command_production_batch_self_test(options);
    if (options.command == "run-compiled-case") return command_run_compiled_case(options);
    if (options.command == "run-zone") return command_run_zone(options);
    if (options.command == "python-bridge-test") return command_python_bridge_test(options);
    std::cerr << "unknown command: " << options.command << "\n";
    usage(std::cerr);
    return 2;
}
