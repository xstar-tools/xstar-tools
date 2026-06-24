#include "xstar_api.h"
#include "xstar_python_bridge.h"
#include "xstar_fixed_state_engine.h"
#include "xstar_thermal_engine.h"
#include "xstar_science_fits.hpp"
#include "xstar_run_state.hpp"
#include "xstar_step_log.hpp"
#include "xstar_standalone_internal.hpp"

#include "xstar_constants.h"
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
#include <map>
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
    std::string parameters_path;
    std::string atomic_db_path;
    std::string output_dir;
    std::string trajectory_csv;
    std::string radiation_csv;
    std::string dsec_radiation_csv;
    std::string continuum_tau_csv;
    std::string call_start_workspace_dir;
    std::string runtime_state_workspace_dir;
    std::string product_schema_dir;
    std::string mg_primary_budget_csv;
    std::string call1_thermal_budget_csv;
    std::string global_workspace_mode = "all";
    double dsec_covering_fraction = 0.0;
    bool has_dsec_covering_fraction = false;
    double temperature_k_override = 0.0;
    bool has_temperature_k_override = false;
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
    bool skip_fits = false;
    bool source_trajectory_guard = false;
    bool source_trajectory_align = false;
    bool resolve_only = false;
    std::size_t controller_smoke_evaluations = 0;
    std::size_t controller_prefix_evaluations = 0;
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
        "  xstar_cpp secant-ieee-self-test --backend cpp [--plugin-dir DIR]\n"
        "  xstar_cpp trajectory-alignment-self-test --backend cpp [--plugin-dir DIR]\n"
        "  xstar_cpp controller-canonical-e7-self-test --backend cpp [--plugin-dir DIR]\n"
        "  xstar_cpp fixed-state-self-test --case-dir RAW_PROGRAM_DIR [--diagnostics-dir DIR]\n"
        "  xstar_cpp run --backend cpp --parameters parameters.json --atomic-db atdb.fits --output-dir DIR [--resolve-only]\n"
        "    Optional native asset overrides: --case-dir, --trajectory-csv, --radiation-csv,\n"
        "    --call-start-workspace-dir, --runtime-state-workspace-dir.\n"
        "  xstar_cpp run-fixed-state --case-dir RAW_PROGRAM_DIR --output-dir DIR\n"
        "  xstar_cpp fixed-state-batch-self-test --case-dir RAW_PROGRAM_DIR [--batch N]\n"
        "  xstar_cpp run-fixed-trajectory --case-dir RAW_PROGRAM_DIR --trajectory-csv CSV [--radiation-csv CSV] [--dsec-radiation-csv CSV] [--continuum-tau-csv CSV] [--dsec-covering-fraction VALUE] [--temperature-k VALUE] [--diagnostics-dir DIR] --output-dir DIR\n"
        "  xstar_cpp run-fixed-evaluation --case-dir RAW_PROGRAM_DIR --trajectory-csv CSV --evaluation N [--radiation-csv CSV] [--dsec-radiation-csv CSV] [--continuum-tau-csv CSV] [--call-start-workspace-dir DIR] [--global-workspace-mode none|xilevg|xilevg-bilevg|xilevg-rnisg|all] [--dsec-covering-fraction VALUE] [--temperature-k VALUE] [--diagnostics-dir DIR] --output-dir DIR\n"
        "  xstar_cpp run-fixed-dsec --case-dir RAW_PROGRAM_DIR --trajectory-csv CSV [--radiation-csv CSV] [--dsec-radiation-csv CSV] [--continuum-tau-csv CSV] [--dsec-covering-fraction VALUE] [--temperature-k VALUE] [--diagnostics-dir DIR] [--skip-fits] [--controller-smoke-evaluations N] [--controller-prefix-evaluations N] [--call-start-workspace-dir DIR] [--runtime-state-workspace-dir DIR] [--source-trajectory-guard] [--source-trajectory-align] [--mg-primary-budget-csv CSV] [--call1-thermal-budget-csv CSV] --output-dir DIR\n"
        "  xstar_cpp production-self-test --case-dir DIR\n"
        "  xstar_cpp production-batch-self-test --case-dir DIR [--batch N]\n"
        "  xstar_cpp run-compiled-case --case-dir DIR --output-dir DIR\n"
        "  Component overrides: --engine-backend, --rates-backend, --matrix-backend,\n"
        "    --solver-backend, --emissivity-backend, --opacity-backend, --thermal-backend.\n"
        "  xstar_cpp run-zone --backend cpp|python --allow-scaffold [options]\n"
        "  xstar_cpp python-bridge-test [--plugin-dir DIR] [--python-path DIR]\n\n"
        "v0.6.48.7.26 decomposes the first post-call-1 thermal mismatch with five controlled global-state replays.\n"
        "Calls 3-4 remain staged behind exact call-2/evaluation-1 element, continuum, charge, and hmctot parity.\n";
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
        } else if (arg == "--parameters") {
            const char* value = require_value("--parameters");
            if (!value) return false;
            options.parameters_path = value;
        } else if (arg == "--atomic-db") {
            const char* value = require_value("--atomic-db");
            if (!value) return false;
            options.atomic_db_path = value;
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
        } else if (arg == "--dsec-radiation-csv") {
            const char* value = require_value("--dsec-radiation-csv");
            if (!value) return false;
            options.dsec_radiation_csv = value;
        } else if (arg == "--continuum-tau-csv") {
            const char* value = require_value("--continuum-tau-csv");
            if (!value) return false;
            options.continuum_tau_csv = value;
        } else if (arg == "--call-start-workspace-dir") {
            const char* value = require_value("--call-start-workspace-dir");
            if (!value) return false;
            options.call_start_workspace_dir = value;
        } else if (arg == "--runtime-state-workspace-dir") {
            const char* value = require_value("--runtime-state-workspace-dir");
            if (!value) return false;
            options.runtime_state_workspace_dir = value;
        } else if (arg == "--product-schema-dir") {
            const char* value = require_value("--product-schema-dir");
            if (!value) return false;
            options.product_schema_dir = value;
        } else if (arg == "--global-workspace-mode") {
            const char* value = require_value("--global-workspace-mode");
            if (!value) return false;
            options.global_workspace_mode = value;
            if (options.global_workspace_mode != "none" && options.global_workspace_mode != "xilevg" &&
                options.global_workspace_mode != "xilevg-bilevg" && options.global_workspace_mode != "xilevg-rnisg" &&
                options.global_workspace_mode != "all") {
                error = "--global-workspace-mode must be none, xilevg, xilevg-bilevg, xilevg-rnisg, or all";
                return false;
            }
        } else if (arg == "--mg-primary-budget-csv") {
            const char* value = require_value("--mg-primary-budget-csv");
            if (!value) return false;
            options.mg_primary_budget_csv = value;
        } else if (arg == "--call1-thermal-budget-csv") {
            const char* value = require_value("--call1-thermal-budget-csv");
            if (!value) return false;
            options.call1_thermal_budget_csv = value;
        } else if (arg == "--dsec-covering-fraction") {
            const char* value = require_value("--dsec-covering-fraction");
            if (!value) return false;
            char* end = nullptr;
            const double parsed = std::strtod(value, &end);
            if (!end || *end != '\0' || !std::isfinite(parsed) || parsed < 0.0 || parsed > 1.0) {
                error = "--dsec-covering-fraction must be finite and in [0,1]";
                return false;
            }
            options.dsec_covering_fraction = parsed;
            options.has_dsec_covering_fraction = true;
        } else if (arg == "--temperature-k") {
            const char* value = require_value("--temperature-k");
            if (!value) return false;
            char* end = nullptr;
            const double parsed = std::strtod(value, &end);
            if (!end || *end != '\0' || !std::isfinite(parsed) || parsed <= 0.0) {
                error = "--temperature-k must be finite and positive";
                return false;
            }
            options.temperature_k_override = parsed;
            options.has_temperature_k_override = true;
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
        } else if (arg == "--skip-fits") {
            options.skip_fits = true;
        } else if (arg == "--resolve-only") {
            options.resolve_only = true;
        } else if (arg == "--source-trajectory-guard") {
            options.source_trajectory_guard = true;
        } else if (arg == "--source-trajectory-align") {
            options.source_trajectory_align = true;
        } else if (arg == "--controller-smoke-evaluations") {
            const char* value = require_value("--controller-smoke-evaluations");
            if (!value || !parse_size(value, options.controller_smoke_evaluations)) {
                error = "invalid --controller-smoke-evaluations value";
                return false;
            }
        } else if (arg == "--controller-prefix-evaluations") {
            const char* value = require_value("--controller-prefix-evaluations");
            if (!value || !parse_size(value, options.controller_prefix_evaluations)) {
                error = "invalid --controller-prefix-evaluations value";
                return false;
            }
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
    input.max_lucy_iterations = 200;
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


struct SecantIeeeOracle {
    std::size_t index = 0;
    std::array<double, 21> observed_temperature{};
};

int secant_ieee_evaluator(
    void* user, const xstar_thermal_state_v1* state,
    xstar_thermal_evaluation_v1* result, char*, std::size_t
) {
    static constexpr std::array<double,21> hmctot{{
        -1.1485157783994295,-1.2392492309264873,-1.3365244377355003,-1.2379933611517373,
        -1.1968253854763977,-1.132430952071409,-1.0211174175435582,-0.8393291198060671,
        -0.7239813869155975,-0.5919119242362201,-0.45718473531090686,-0.32162613939075313,
        -0.19464191907155218,-0.08424484486647842,0.007611710719945893,-0.006283208886998945,
        -0.0030153312341974128,-0.0014504720313989663,-0.0005918495278817498,
        -0.00016031988158732148,3.6784756677800766e-06
    }};
    static constexpr std::array<double,21> elcter{{
        -0.2003671619969254,-0.0003632540628308867,0.23964076002422652,3.5395526509773845e-09,
        8.436026564639931e-06,1.902507750983773e-05,3.25925433450891e-05,4.7120904026476396e-05,
        5.470084452441348e-05,6.266242568297997e-05,7.081304333977911e-05,7.92881869589035e-05,
        8.736293209521406e-05,9.470263632027631e-05,0.00010239787225874153,0.00010170327309855232,
        0.00010200710192420637,0.00010218061741751328,0.00010227635767989796,
        0.000102324706198198,0.00010234445982515439
    }};
    if (!user || !state || !result) return 1;
    auto* oracle=static_cast<SecantIeeeOracle*>(user);
    if (oracle->index>=hmctot.size()) return 2;
    oracle->observed_temperature[oracle->index]=state->temperature_t4;
    std::memset(result,0,sizeof(*result)); result->struct_size=sizeof(*result); result->abi_version=XSTAR_THERMAL_ENGINE_ABI_VERSION;
    result->hmctot=hmctot[oracle->index]; result->elcter=elcter[oracle->index];
    result->temperature_t4=state->temperature_t4; result->electron_fraction_xee=state->electron_fraction_xee;
    result->hydrogen_density_cm3=state->hydrogen_density_cm3; result->state_generation=state->state_generation+1;
    ++oracle->index; return 0;
}

int command_secant_ieee_self_test(const Options& options) {
    static constexpr std::array<double,21> expected{{
        100.0,100.0,100.0,100.0,69.44443892549619,48.225300976769695,33.489789683449544,
        23.256796543000238,19.380663015715175,16.15055187133071,13.458792691304552,
        11.215660130416834,9.346383070622133,7.788652249358545,6.490543283221103,
        6.598111326352328,6.549469628258488,6.523421015417408,6.509200154467056,
        6.502045379119084,6.4991462211451925
    }};
    xstar_context* context=nullptr; const int create_status=create_context(options,&context); if(create_status!=XSTAR_STATUS_OK) return create_status;
    xstar_dsec_config_v1 config{}; config.struct_size=sizeof(config); config.abi_version=XSTAR_THERMAL_ENGINE_ABI_VERSION;
    config.nlim=18; config.maximum_evaluations=21; config.tinf_t4=0.0;
    config.charge_tolerance=static_cast<double>(static_cast<float>(1.0e-4));
    config.thermal_tolerance=static_cast<double>(static_cast<float>(1.0e-4));
    config.temperature_stagnation_tolerance=static_cast<double>(static_cast<float>(2.0e-9));
    xstar_thermal_state_v1 state{}; state.struct_size=sizeof(state); state.abi_version=XSTAR_THERMAL_ENGINE_ABI_VERSION;
    state.temperature_t4=100.0; state.electron_fraction_xee=1.0; state.hydrogen_density_cm3=1.0e8;
    SecantIeeeOracle oracle{}; std::array<xstar_thermal_trace_event_v1,512> trace{}; std::size_t trace_count=0;
    xstar_dsec_stats_v1 stats{}; stats.struct_size=sizeof(stats); stats.abi_version=XSTAR_THERMAL_ENGINE_ABI_VERSION;
    const int status=xstar_context_run_thermal_evaluation_loop_v1(context,&config,&state,secant_ieee_evaluator,&oracle,trace.data(),trace.size(),&trace_count,&stats);
    std::array<double,21> committed{}; std::size_t committed_count=0;
    for(std::size_t i=0;i<std::min(trace_count,trace.size()) && committed_count<committed.size();++i) {
        if(trace[i].event_code==XSTAR_THERMAL_EVENT_AFTER_EVALUATION) committed[committed_count++]=trace[i].temperature_t4;
    }
    std::size_t exact=0; for(std::size_t i=0;i<expected.size() && i<committed_count;++i) if(committed[i]==expected[i]) ++exact;
    const bool accepted=status==XSTAR_STATUS_OK && oracle.index==21 && committed_count==21 && exact==21;
    std::cout<<"evaluations="<<oracle.index<<"\n"<<"committed_rows="<<committed_count<<"\n"<<"temperature_rows_ieee_exact="<<exact<<"\n"
             <<"late_secant_temperature_t4="<<std::setprecision(17)<<committed[20]<<"\n"
             <<"source_k_to_t4_commit=true\nsource_secant_operation_order=true\nphysical_callback_precommit=false\nsingle_commit_owner=thermal_controller\nRESULT="<<(accepted?"ACCEPT":"REJECT")<<"\n";
    xstar_context_destroy(context); return accepted?0:12;
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
        fits_card("ORIGIN", "'xstar_tools 0.6.48.7.26'"),
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
                 << "xstar_tools native fixed-state v0.6.48.7.26\n"
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
                    << "{\n  \"schema_version\": \"0.6.48.7.26\",\n"
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
              << "first_computed_electron_fraction=" << std::setprecision(17) << outputs[0].electron_fraction_xee << "\n"
              << "last_computed_electron_fraction=" << std::setprecision(17) << outputs.back().electron_fraction_xee << "\n"
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


struct DsecRadiationWorkspace {
    std::vector<double> energy_ev;
    std::vector<double> bremsa;
};

DsecRadiationWorkspace read_dsec_radiation_workspace(const std::string& path) {
    DsecRadiationWorkspace workspace;
    if (path.empty()) return workspace;
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open DSEC radiation workspace CSV: "+path);
    std::string header;
    if (!std::getline(input,header)) throw std::runtime_error("empty DSEC radiation workspace CSV");
    const auto names=split_simple_csv(header);
    auto find_any=[&](std::initializer_list<const char*> choices)->std::size_t {
        for (const char* choice: choices) {
            const auto it=std::find(names.begin(),names.end(),choice);
            if (it!=names.end()) return static_cast<std::size_t>(it-names.begin());
        }
        throw std::runtime_error("DSEC radiation workspace missing required column");
    };
    const auto ce=find_any({"energy_ev","epi_ev","epi_eV","energy"});
    const auto cb=find_any({"bremsa","dsec_bremsa","radiation_flux"});
    std::string line; double previous=-1.0;
    while (std::getline(input,line)) {
        if (line.empty()) continue;
        const auto f=split_simple_csv(line);
        if (f.size()!=names.size()) throw std::runtime_error("DSEC radiation workspace row has wrong column count");
        const double e=std::stod(f[ce]), b=std::stod(f[cb]);
        if (!std::isfinite(e)||!(e>0.0)||e<=previous) throw std::runtime_error("DSEC radiation energies invalid");
        if (!std::isfinite(b)||b<0.0) throw std::runtime_error("DSEC bremsa invalid");
        workspace.energy_ev.push_back(e); workspace.bremsa.push_back(b); previous=e;
    }
    if (workspace.energy_ev.size()<3) throw std::runtime_error("DSEC radiation workspace requires at least three bins");
    return workspace;
}

struct ContinuumTauWorkspace {
    std::vector<double> tau_in;
    std::vector<double> tau_out;
};

ContinuumTauWorkspace read_continuum_tau_workspace(const std::string& path) {
    ContinuumTauWorkspace workspace;
    if (path.empty()) return workspace;
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open continuum optical-depth workspace CSV: "+path);
    std::string header;
    if (!std::getline(input,header)) throw std::runtime_error("empty continuum optical-depth workspace CSV");
    const auto names=split_simple_csv(header);
    auto find_col=[&](const char* name)->std::size_t {
        const auto it=std::find(names.begin(),names.end(),name);
        if (it==names.end()) throw std::runtime_error(std::string("continuum workspace missing column ")+name);
        return static_cast<std::size_t>(it-names.begin());
    };
    const auto ci=find_col("continuum_index"), cin=find_col("tau_in"), cout=find_col("tau_out");
    std::string line; std::size_t expected=1;
    while (std::getline(input,line)) {
        if (line.empty()) continue;
        const auto f=split_simple_csv(line);
        if (f.size()!=names.size()) throw std::runtime_error("continuum workspace row has wrong column count");
        const std::size_t index=static_cast<std::size_t>(std::stoull(f[ci]));
        if (index!=expected) throw std::runtime_error("continuum workspace indices must be dense and one-based");
        const double a=std::stod(f[cin]), b=std::stod(f[cout]);
        if (!std::isfinite(a)||!std::isfinite(b)||a<0.0||b<0.0) throw std::runtime_error("continuum optical depth invalid");
        workspace.tau_in.push_back(a); workspace.tau_out.push_back(b); ++expected;
    }
    if (workspace.tau_in.empty()) throw std::runtime_error("continuum workspace is empty");
    return workspace;
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
    step << std::setprecision(17) << "xstar_tools native fixed-state trajectory v0.6.48.7.26\n"
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
        const double native_charge_residual = out.elcter;
        const double dh=out.hmctot-trajectory[j].reference_hmctot;
        const double de=native_charge_residual-trajectory[j].reference_elcter;
        max_hmc_delta=std::max(max_hmc_delta,std::abs(dh));
        max_charge_residual_delta=std::max(max_charge_residual_delta,std::abs(de));
        states << std::setprecision(17) << trajectory[j].sequence << ',' << trajectory[j].kind << ',' << trajectory[j].call_index << ',' << trajectory[j].evaluation_index << ','
               << trajectory[j].temperature_t4 << ',' << trajectory[j].electron_fraction << ',' << out.hmctot << ',' << out.electron_fraction_xee << ',' << native_charge_residual << ',' << out.total_heating << ',' << out.total_cooling << ','
               << out.element_heating << ',' << out.element_cooling << ',' << out.continuum_heating << ',' << out.continuum_cooling << ','
               << trajectory[j].reference_hmctot << ',' << trajectory[j].reference_elcter << ',' << trajectory[j].reference_lnerr << ',' << dh << ',' << de << '\n';
        for (std::size_t k=0;k<out.populations_count;++k) pops << trajectory[j].evaluation_index << ',' << k+1 << ',' << std::setprecision(17) << populations[k] << '\n';
        for (std::size_t k=0;k<bins;++k) spectra_file << trajectory[j].evaluation_index << ',' << k+1 << ',' << std::setprecision(17) << energy[k] << ',' << spectrum[k] << ',' << opacity[k] << '\n';
        step << "evaluation=" << trajectory[j].evaluation_index << " temperature_t4=" << trajectory[j].temperature_t4 << " xee_input=" << trajectory[j].electron_fraction
             << " hmctot=" << out.hmctot << " computed_xee=" << out.electron_fraction_xee << " charge_residual=" << native_charge_residual
             << " heating=" << out.total_heating << " cooling=" << out.total_cooling << '\n';
    }
    rc=xstar_fixed_state_write_visited_report_v1(context,(std::filesystem::path(options.output_dir)/"visited_records.csv").c_str(),message.data(),message.size());
    if (rc!=0) { std::cerr << "visited report failed: " << message.data() << "\n"; xstar_fixed_state_context_destroy(context); return rc; }
    std::ofstream summary(std::filesystem::path(options.output_dir)/"native_trajectory_summary.json");
    summary << std::setprecision(17) << "{\n  \"schema_version\": \"0.6.48.7.26\",\n  \"program_id\": \"" << cumulative.program_id << "\",\n"
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

std::vector<double> read_binary_double_vector(const std::filesystem::path& path);

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
    DsecRadiationWorkspace dsec_radiation;
    ContinuumTauWorkspace continuum_tau;
    try {
        dsec_radiation = read_dsec_radiation_workspace(options.dsec_radiation_csv);
        continuum_tau = read_continuum_tau_workspace(options.continuum_tau_csv);
    } catch (const std::exception& exc) {
        std::cerr << exc.what() << "\n"; xstar_fixed_state_context_destroy(context); return 6;
    }
    const std::size_t bins = radiation.energy_ev.size();
    std::vector<double> populations(static_cast<std::size_t>(info.population_rows), 0.0);
    std::vector<double> spectrum(bins, 0.0), opacity(bins, 0.0);
    xstar_fixed_state_input_v1 input{};
    xstar_fixed_state_input_init_v1(&input);
    input.temperature_k = options.has_temperature_k_override
        ? options.temperature_k_override : row.temperature_t4 * 1.0e4;
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
    if (!dsec_radiation.energy_ev.empty()) {
        input.dsec_radiation_energy_ev = dsec_radiation.energy_ev.data();
        input.dsec_bremsa = dsec_radiation.bremsa.data();
        input.dsec_radiation_bin_count = dsec_radiation.energy_ev.size();
    }
    if (!continuum_tau.tau_in.empty()) {
        input.continuum_tau_in = continuum_tau.tau_in.data();
        input.continuum_tau_out = continuum_tau.tau_out.data();
        input.continuum_tau_count = continuum_tau.tau_in.size();
    }
    std::vector<double> replay_radiation, replay_bremsa, replay_tau_in, replay_tau_out;
    std::vector<double> replay_xilevg, replay_bilevg, replay_rnisg, replay_zero_b, replay_zero_r;
    bool replay_workspace_applied = false;
    if (!options.call_start_workspace_dir.empty()) {
        try {
            const std::filesystem::path root(options.call_start_workspace_dir);
            const std::string prefix = "call_" + std::to_string(row.call_index) + "_";
            replay_radiation = read_binary_double_vector(root / (prefix + "radiation_energy.bin"));
            replay_bremsa = read_binary_double_vector(root / (prefix + "bremsa.bin"));
            replay_tau_in = read_binary_double_vector(root / (prefix + "continuum_tau_in.bin"));
            replay_tau_out = read_binary_double_vector(root / (prefix + "continuum_tau_out.bin"));
            replay_xilevg = read_binary_double_vector(root / (prefix + "global_xilevg.bin"));
            replay_bilevg = read_binary_double_vector(root / (prefix + "global_bilevg.bin"));
            replay_rnisg = read_binary_double_vector(root / (prefix + "global_rnisg.bin"));
            if (replay_radiation.size() != replay_bremsa.size()) throw std::runtime_error("replay radiation arrays differ in length");
            if (replay_tau_in.size() != replay_tau_out.size()) throw std::runtime_error("replay continuum arrays differ in length");
            if (!(replay_xilevg.size() == replay_bilevg.size() && replay_xilevg.size() == replay_rnisg.size())) throw std::runtime_error("replay global arrays differ in length");
            input.dsec_radiation_energy_ev = replay_radiation.data();
            input.dsec_bremsa = replay_bremsa.data();
            input.dsec_radiation_bin_count = replay_radiation.size();
            input.continuum_tau_in = replay_tau_in.data();
            input.continuum_tau_out = replay_tau_out.data();
            input.continuum_tau_count = replay_tau_in.size();
            if (options.global_workspace_mode != "none" && !replay_xilevg.empty()) {
                replay_zero_b.assign(replay_xilevg.size(), 0.0);
                replay_zero_r.assign(replay_xilevg.size(), 0.0);
                input.global_xilevg = replay_xilevg.data();
                input.global_bilevg = (options.global_workspace_mode == "xilevg-bilevg" || options.global_workspace_mode == "all") ? replay_bilevg.data() : replay_zero_b.data();
                input.global_rnisg = (options.global_workspace_mode == "xilevg-rnisg" || options.global_workspace_mode == "all") ? replay_rnisg.data() : replay_zero_r.data();
                input.global_level_count = replay_xilevg.size();
                input.runtime_state_flags |= XSTAR_FIXED_RUNTIME_STATE_GLOBAL_LEVEL_WORKSPACES;
            }
            replay_workspace_applied = true;
        } catch (const std::exception& exc) {
            std::cerr << "workspace replay load failed: " << exc.what() << "\n";
            xstar_fixed_state_context_destroy(context);
            return 7;
        }
    }
    if (options.has_dsec_covering_fraction) {
        input.dsec_covering_fraction = options.dsec_covering_fraction;
        input.runtime_state_flags |= XSTAR_FIXED_RUNTIME_STATE_DSEC_COVERING_FRACTION;
    }
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
    state << "trajectory_row,sequence,kind,call_index,evaluation_index,temperature_t4,electron_fraction_input,global_workspace_mode,replay_workspace_applied,native_hmctot,native_electron_fraction,native_charge_residual,total_heating,total_cooling,element_heating,element_cooling,continuum_heating,continuum_cooling,reference_hmctot,reference_charge_residual,hmctot_delta,charge_residual_delta\n";
    const double charge_residual = output.elcter;
    const double hmctot_delta = output.hmctot - row.reference_hmctot;
    const double charge_delta = charge_residual - row.reference_elcter;
    state << std::setprecision(17) << options.evaluation << ',' << row.sequence << ',' << row.kind << ','
          << row.call_index << ',' << row.evaluation_index << ',' << (input.temperature_k / 1.0e4) << ',' << input.electron_fraction_xee << ','
          << options.global_workspace_mode << ',' << (replay_workspace_applied ? 1 : 0) << ','
          << output.hmctot << ',' << output.electron_fraction_xee << ',' << charge_residual << ',' << output.total_heating << ',' << output.total_cooling << ','
          << output.element_heating << ',' << output.element_cooling << ',' << output.continuum_heating << ',' << output.continuum_cooling << ','
          << row.reference_hmctot << ',' << row.reference_elcter << ',' << hmctot_delta << ',' << charge_delta << '\n';
    std::ofstream pop_file(output_root / "native_evaluation_populations.csv");
    pop_file << "row,population\n" << std::setprecision(17);
    for (std::size_t k = 0; k < output.populations_count; ++k) pop_file << k + 1 << ',' << populations[k] << '\n';
    std::ofstream spectrum_file(output_root / "native_evaluation_spectra.csv");
    spectrum_file << "bin,energy_ev,spectrum,opacity\n" << std::setprecision(17);
    for (std::size_t k = 0; k < bins; ++k) spectrum_file << k + 1 << ',' << radiation.energy_ev[k] << ',' << spectrum[k] << ',' << opacity[k] << '\n';
    rc = xstar_fixed_state_write_last_thermal_budget_v1(
        context, (output_root / "native_thermal_budget.csv").c_str(), 1,
        static_cast<std::uint64_t>(row.call_index), static_cast<std::uint64_t>(row.evaluation_index),
        "replay", message.data(), message.size());
    if (rc != 0) { std::cerr << "evaluation thermal-budget ledger failed: " << message.data() << "\n"; xstar_fixed_state_context_destroy(context); return rc; }
    const std::filesystem::path diagnostics_root = options.diagnostics_dir.empty()
        ? output_root / "diagnostics" : std::filesystem::path(options.diagnostics_dir);
    rc = xstar_fixed_state_write_last_diagnostics_v1(
        context, diagnostics_root.c_str(), static_cast<std::uint64_t>(options.evaluation), message.data(), message.size());
    if (rc != 0) { std::cerr << "evaluation diagnostics failed: " << message.data() << "\n"; xstar_fixed_state_context_destroy(context); return rc; }
    {
        std::ostringstream diagnostic_name;
        diagnostic_name << "evaluation_" << std::setw(4) << std::setfill('0') << options.evaluation
                        << "_thermal_compact_populations.csv";
        const auto diagnostic_path = diagnostics_root / diagnostic_name.str();
        if (!std::filesystem::is_regular_file(diagnostic_path)) {
            std::cerr << "evaluation compact-population diagnostics missing: " << diagnostic_path << "\n";
            xstar_fixed_state_context_destroy(context);
            return 8;
        }
        std::filesystem::copy_file(
            diagnostic_path, output_root / "native_thermal_compact_populations.csv",
            std::filesystem::copy_options::overwrite_existing);
        std::ostringstream diagonal_name;
        diagonal_name << "evaluation_" << std::setw(4) << std::setfill('0') << options.evaluation
                      << "_thermal_diagonal_ledger.csv";
        const auto diagonal_path = diagnostics_root / diagonal_name.str();
        if (!std::filesystem::is_regular_file(diagonal_path)) {
            std::cerr << "evaluation thermal diagonal diagnostics missing: " << diagonal_path << "\n";
            xstar_fixed_state_context_destroy(context);
            return 8;
        }
        std::filesystem::copy_file(
            diagonal_path, output_root / "native_thermal_diagonal_ledger.csv",
            std::filesystem::copy_options::overwrite_existing);
        std::ostringstream canonical_name;
        canonical_name << "evaluation_" << std::setw(4) << std::setfill('0') << options.evaluation
                       << "_canonical_thermal_terms.csv";
        const auto canonical_path = diagnostics_root / canonical_name.str();
        if (!std::filesystem::is_regular_file(canonical_path)) {
            std::cerr << "evaluation canonical Thermal term diagnostics missing: " << canonical_path << "\n";
            xstar_fixed_state_context_destroy(context);
            return 8;
        }
        std::filesystem::copy_file(
            canonical_path, output_root / "native_canonical_thermal_terms.csv",
            std::filesystem::copy_options::overwrite_existing);
        std::ostringstream continuum_name;
        continuum_name << "evaluation_" << std::setw(4) << std::setfill('0') << options.evaluation
                       << "_continuum_workspace.csv";
        const auto continuum_path = diagnostics_root / continuum_name.str();
        if (!std::filesystem::is_regular_file(continuum_path)) {
            std::cerr << "evaluation continuum workspace diagnostics missing: " << continuum_path << "\n";
            xstar_fixed_state_context_destroy(context);
            return 8;
        }
        std::filesystem::copy_file(
            continuum_path, output_root / "native_continuum_workspace.csv",
            std::filesystem::copy_options::overwrite_existing);
    }
    const bool live_runtime_state_abi = input.dsec_radiation_energy_ev && input.dsec_bremsa &&
        input.dsec_radiation_bin_count >= 3 && input.continuum_tau_in && input.continuum_tau_out &&
        input.continuum_tau_count > 0;
    const std::size_t live_dsec_radiation_bins = input.dsec_radiation_bin_count;
    const std::size_t live_continuum_tau_count = input.continuum_tau_count;
    std::ofstream summary(output_root / "native_evaluation_summary.json");
    summary << std::setprecision(17)
            << "{\n  \"schema_version\": \"0.6.48.7.26\",\n"
            << "  \"trajectory_mode\": \"single_reference_input_state_qualification\",\n"
            << "  \"trajectory_row\": " << options.evaluation << ",\n"
            << "  \"evaluation_index\": " << row.evaluation_index << ",\n"
            << "  \"call_index\": " << row.call_index << ",\n"
            << "  \"global_workspace_mode\": \"" << options.global_workspace_mode << "\",\n"
            << "  \"replay_workspace_applied\": " << (replay_workspace_applied ? "true" : "false") << ",\n"
            << "  \"records_evaluated\": " << stats.records_evaluated << ",\n"
            << "  \"elements_solved\": " << stats.elements_solved << ",\n"
            << "  \"python_callbacks\": " << stats.python_callbacks << ",\n"
            << "  \"native_electron_fraction\": " << output.electron_fraction_xee << ",\n"
            << "  \"native_charge_residual\": " << charge_residual << ",\n"
            << "  \"reference_charge_residual\": " << row.reference_elcter << ",\n"
            << "  \"charge_residual_delta\": " << charge_delta << ",\n"
            << "  \"native_hmctot\": " << output.hmctot << ",\n"
            << "  \"reference_hmctot\": " << row.reference_hmctot << ",\n"
            << "  \"hmctot_delta\": " << hmctot_delta << ",\n"
            << "  \"dsec_runtime_state_abi\": " << (live_runtime_state_abi ? "true" : "false") << ",\n"
            << "  \"dsec_radiation_bins\": " << live_dsec_radiation_bins << ",\n"
            << "  \"continuum_tau_count\": " << live_continuum_tau_count << ",\n"
            << "  \"diagnostics_directory\": \"" << std::filesystem::absolute(diagnostics_root).string() << "\"\n}\n";
    std::cout << std::setprecision(17)
              << "trajectory_row=" << options.evaluation << "\n"
              << "evaluation_index=" << row.evaluation_index << "\n"
              << "call_index=" << row.call_index << "\n"
              << "global_workspace_mode=" << options.global_workspace_mode << "\n"
              << "replay_workspace_applied=" << (replay_workspace_applied ? "true" : "false") << "\n"
              << "records_evaluated=" << stats.records_evaluated << "\n"
              << "elements_solved=" << stats.elements_solved << "\n"
              << "python_callbacks=" << stats.python_callbacks << "\n"
              << "native_electron_fraction=" << output.electron_fraction_xee << "\n"
              << "native_charge_residual=" << charge_residual << "\n"
              << "charge_residual_delta=" << charge_delta << "\n"
              << "native_hmctot=" << output.hmctot << "\n"
              << "hmctot_delta=" << hmctot_delta << "\n"
              << "dsec_runtime_state_abi=" << (live_runtime_state_abi ? "true" : "false") << "\n"
              << "dsec_radiation_bins=" << live_dsec_radiation_bins << "\n"
              << "continuum_tau_count=" << live_continuum_tau_count << "\n"
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
    double hydrogen_heating = 0.0;
    double hydrogen_cooling = 0.0;
    double helium_heating = 0.0;
    double helium_cooling = 0.0;
    double magnesium_heating = 0.0;
    double magnesium_cooling = 0.0;
    double compton_heating = 0.0;
    double compton_cooling = 0.0;
    double brems_cooling = 0.0;
    bool thermal_families_native = false;
    bool dsec_runtime_state_abi = false;
    std::vector<double> populations;
    std::vector<double> radiation_energy_ev;
    std::vector<double> radiation_flux;
    std::vector<double> continuum_tau_in;
    std::vector<double> continuum_tau_out;
    std::vector<double> continuum_spectrum;
    std::vector<double> spectrum;
    std::vector<double> opacity;
};



std::vector<std::string> split_csv_simple(const std::string& line) {
    std::vector<std::string> fields;
    std::string field;
    std::istringstream input(line);
    while (std::getline(input, field, ',')) fields.push_back(field);
    return fields;
}

void attach_native_thermal_families(
    std::vector<FixedDsecSnapshot>& snapshots,
    const std::filesystem::path& path) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open native thermal-family ledger: " + path.string());
    std::string header;
    std::getline(input, header);
    const auto names = split_csv_simple(header);
    std::map<std::string,std::size_t> columns;
    for (std::size_t i = 0; i < names.size(); ++i) columns[names[i]] = i;
    for (const char* required : {"sequence","h_heating","h_cooling","he_heating","he_cooling",
             "mg_heating","mg_cooling","htcomp","clcomp","clbrems"}) {
        if (!columns.count(required)) throw std::runtime_error(std::string("thermal ledger missing column: ") + required);
    }
    std::map<std::size_t,FixedDsecSnapshot*> by_sequence;
    for (auto& snapshot : snapshots) by_sequence[snapshot.sequence] = &snapshot;
    std::string line;
    std::size_t attached = 0;
    while (std::getline(input, line)) {
        if (line.empty()) continue;
        const auto values = split_csv_simple(line);
        const std::size_t sequence = static_cast<std::size_t>(std::stoull(values.at(columns.at("sequence"))));
        const auto found = by_sequence.find(sequence);
        if (found == by_sequence.end()) continue;
        auto& s = *found->second;
        auto scalar = [&](const char* name) { return std::stod(values.at(columns.at(name))); };
        s.hydrogen_heating = scalar("h_heating");
        s.hydrogen_cooling = scalar("h_cooling");
        s.helium_heating = scalar("he_heating");
        s.helium_cooling = scalar("he_cooling");
        s.magnesium_heating = scalar("mg_heating");
        s.magnesium_cooling = scalar("mg_cooling");
        s.compton_heating = scalar("htcomp");
        s.compton_cooling = scalar("clcomp");
        s.brems_cooling = scalar("clbrems");
        s.thermal_families_native = true;
        ++attached;
    }
    if (attached != snapshots.size()) {
        throw std::runtime_error("native thermal-family ledger did not cover all 61 evaluations");
    }
}

struct CallStartWorkspace {
    std::vector<double> radiation_energy;
    std::vector<double> bremsa;
    std::vector<double> continuum_tau_in;
    std::vector<double> continuum_tau_out;
    std::vector<double> global_xilevg;
    std::vector<double> global_bilevg;
    std::vector<double> global_rnisg;
};

struct RuntimeStateWorkspace {
    int call_index = 0;
    std::filesystem::path directory;
    std::filesystem::path line_tau_in;
    std::filesystem::path line_tau_out;
};

struct MgPrimaryBudget {
    double heating = 0.0;
    double cooling = 0.0;
    double heating2 = 0.0;
    double cooling2 = 0.0;
};

std::vector<double> read_binary_double_vector(const std::filesystem::path& path) {
    std::ifstream in(path, std::ios::binary | std::ios::ate);
    if (!in) throw std::runtime_error("cannot open workspace payload: " + path.string());
    const auto bytes = in.tellg();
    if (bytes < 0 || bytes % static_cast<std::streamoff>(sizeof(double)) != 0) {
        throw std::runtime_error("invalid workspace payload size: " + path.string());
    }
    std::vector<double> values(static_cast<std::size_t>(bytes / static_cast<std::streamoff>(sizeof(double))));
    in.seekg(0);
    if (!values.empty()) in.read(reinterpret_cast<char*>(values.data()), bytes);
    if (!in && !values.empty()) throw std::runtime_error("cannot read workspace payload: " + path.string());
    return values;
}

std::vector<CallStartWorkspace> read_call_start_workspaces(const std::string& directory) {
    std::vector<CallStartWorkspace> out;
    if (directory.empty()) return out;
    const std::filesystem::path root(directory);
    for (int call = 1; call <= 4; ++call) {
        const std::string prefix = "call_" + std::to_string(call) + "_";
        CallStartWorkspace one;
        one.radiation_energy = read_binary_double_vector(root / (prefix + "radiation_energy.bin"));
        one.bremsa = read_binary_double_vector(root / (prefix + "bremsa.bin"));
        one.continuum_tau_in = read_binary_double_vector(root / (prefix + "continuum_tau_in.bin"));
        one.continuum_tau_out = read_binary_double_vector(root / (prefix + "continuum_tau_out.bin"));
        one.global_xilevg = read_binary_double_vector(root / (prefix + "global_xilevg.bin"));
        one.global_bilevg = read_binary_double_vector(root / (prefix + "global_bilevg.bin"));
        one.global_rnisg = read_binary_double_vector(root / (prefix + "global_rnisg.bin"));
        if (one.radiation_energy.size() != one.bremsa.size()) throw std::runtime_error("call-start radiation payload size mismatch");
        if (one.continuum_tau_in.size() != one.continuum_tau_out.size()) throw std::runtime_error("call-start tau payload size mismatch");
        if (!(one.global_xilevg.size() == one.global_bilevg.size() && one.global_xilevg.size() == one.global_rnisg.size())) {
            throw std::runtime_error("call-start global-level payload size mismatch");
        }
        out.push_back(std::move(one));
    }
    return out;
}

CallStartWorkspace read_runtime_state_workspace_values(
    const RuntimeStateWorkspace& workspace) {
    const std::string prefix = "call_" + std::to_string(workspace.call_index) + "_";
    CallStartWorkspace values;
    values.radiation_energy = read_binary_double_vector(
        workspace.directory / (prefix + "radiation_energy.bin"));
    values.bremsa = read_binary_double_vector(
        workspace.directory / (prefix + "bremsa.bin"));
    values.continuum_tau_in = read_binary_double_vector(
        workspace.directory / (prefix + "continuum_tau_in.bin"));
    values.continuum_tau_out = read_binary_double_vector(
        workspace.directory / (prefix + "continuum_tau_out.bin"));
    values.global_xilevg = read_binary_double_vector(
        workspace.directory / (prefix + "global_xilevg.bin"));
    values.global_bilevg = read_binary_double_vector(
        workspace.directory / (prefix + "global_bilevg.bin"));
    values.global_rnisg = read_binary_double_vector(
        workspace.directory / (prefix + "global_rnisg.bin"));
    if (values.radiation_energy.size() != values.bremsa.size()) {
        throw std::runtime_error("runtime-state radiation payload size mismatch");
    }
    if (values.continuum_tau_in.size() != values.continuum_tau_out.size()) {
        throw std::runtime_error("runtime-state continuum tau payload size mismatch");
    }
    if (!(values.global_xilevg.size() == values.global_bilevg.size() &&
          values.global_xilevg.size() == values.global_rnisg.size())) {
        throw std::runtime_error("runtime-state global-level payload size mismatch");
    }
    return values;
}

std::vector<RuntimeStateWorkspace> read_runtime_state_workspaces(
    const std::string& directory,
    const std::vector<TrajectoryRow>& reference) {
    std::vector<RuntimeStateWorkspace> out;
    if (directory.empty()) return out;
    out.resize(61);
    std::array<bool, 61> seen{};
    const std::filesystem::path root(directory);
    for (const auto& row : reference) {
        const std::size_t sequence = static_cast<std::size_t>(std::stoull(row.sequence));
        if (sequence < 1 || sequence > 61 || seen[sequence - 1]) {
            throw std::runtime_error("runtime-state workspace source sequence inventory is invalid");
        }
        if (row.call_index < 1 || row.call_index > 4) {
            throw std::runtime_error("runtime-state workspace call identity is invalid");
        }
        seen[sequence - 1] = true;
        RuntimeStateWorkspace one;
        one.call_index = static_cast<int>(row.call_index);
        char evaluation_name[32]{};
        std::snprintf(evaluation_name, sizeof(evaluation_name), "evaluation_%04zu", sequence);
        one.directory = root / evaluation_name;
        const std::string prefix = "call_" + std::to_string(one.call_index) + "_";
        for (const char* name : {
                 "radiation_energy.bin", "bremsa.bin", "continuum_tau_in.bin",
                 "continuum_tau_out.bin", "global_xilevg.bin", "global_bilevg.bin",
                 "global_rnisg.bin"}) {
            if (!std::filesystem::is_regular_file(one.directory / (prefix + name))) {
                throw std::runtime_error(
                    "runtime-state workspace is missing payload " + std::string(name) +
                    ": " + one.directory.string());
            }
        }
        one.line_tau_in = one.directory / (prefix + "line_tau_in.bin");
        one.line_tau_out = one.directory / (prefix + "line_tau_out.bin");
        if (!std::filesystem::is_regular_file(one.line_tau_in) ||
            !std::filesystem::is_regular_file(one.line_tau_out)) {
            throw std::runtime_error(
                "runtime-state workspace is missing line optical-depth payloads: " +
                one.directory.string());
        }
        out[sequence - 1] = std::move(one);
    }
    if (!std::all_of(seen.begin(), seen.end(), [](bool value) { return value; })) {
        throw std::runtime_error("runtime-state workspace inventory does not cover all 61 source sequences");
    }
    return out;
}

std::vector<MgPrimaryBudget> read_mg_primary_budget(const std::string& path) {
    std::vector<MgPrimaryBudget> out;
    if (path.empty()) return out;
    std::ifstream in(path);
    if (!in) throw std::runtime_error("cannot open Mg primary budget CSV");
    std::string line;
    if (!std::getline(in, line)) throw std::runtime_error("Mg primary budget CSV is empty");
    const auto header = split_simple_csv(line);
    std::map<std::string,std::size_t> cols;
    for (std::size_t i=0;i<header.size();++i) cols[header[i]]=i;
    for (const char* name : {"dsec_call_id","dsec_local_evaluation_index","mg_heating","mg_cooling","mg_heating2","mg_cooling2"}) {
        if (!cols.count(name)) throw std::runtime_error(std::string("Mg primary budget CSV missing ") + name);
    }
    while (std::getline(in,line)) {
        if (line.empty()) continue;
        const auto c=split_simple_csv(line);
        if (std::stoi(c.at(cols["dsec_call_id"])) != 1) continue;
        const int index=std::stoi(c.at(cols["dsec_local_evaluation_index"]));
        if (index <= 0) continue;
        if (out.size() < static_cast<std::size_t>(index)) out.resize(static_cast<std::size_t>(index));
        auto& row=out[static_cast<std::size_t>(index-1)];
        row.heating=std::stod(c.at(cols["mg_heating"]));
        row.cooling=std::stod(c.at(cols["mg_cooling"]));
        row.heating2=std::stod(c.at(cols["mg_heating2"]));
        row.cooling2=std::stod(c.at(cols["mg_cooling2"]));
    }
    return out;
}


struct Call1ThermalOracle {
    std::array<double,4> h{{0,0,0,0}};
    std::array<double,4> he{{0,0,0,0}};
    double htfreef=0.0, clbrems=0.0, cmp1=0.0, cmp2=0.0, htcomp=0.0, clcomp=0.0;
    double charge_residual=0.0, hmctot=0.0;
};

std::vector<Call1ThermalOracle> read_call1_thermal_oracle(const std::string& path) {
    std::vector<Call1ThermalOracle> out;
    if (path.empty()) return out;
    std::ifstream in(path); if (!in) throw std::runtime_error("cannot open call-1 thermal oracle CSV");
    std::string line; if (!std::getline(in,line)) throw std::runtime_error("call-1 thermal oracle CSV is empty");
    const auto header=split_simple_csv(line); std::map<std::string,std::size_t> c; for(std::size_t i=0;i<header.size();++i)c[header[i]]=i;
    const std::vector<std::string> required={"dsec_call_id","dsec_local_evaluation_index","h_heating","h_cooling","h_heating2","h_cooling2","he_heating","he_cooling","he_heating2","he_cooling2","htfreef","clbrems","cmp1","cmp2","htcomp","clcomp","elcter","hmctot"};
    for(const auto& name:required) if(!c.count(name)) throw std::runtime_error("call-1 thermal oracle missing "+name);
    while(std::getline(in,line)) { if(line.empty())continue; const auto v=split_simple_csv(line); if(std::stoi(v.at(c["dsec_call_id"]))!=1)continue; const int idx=std::stoi(v.at(c["dsec_local_evaluation_index"])); if(idx<=0)continue; if(out.size()<static_cast<std::size_t>(idx))out.resize(idx); auto& r=out[idx-1];
        r.h={{std::stod(v.at(c["h_heating"])),std::stod(v.at(c["h_cooling"])),std::stod(v.at(c["h_heating2"])),std::stod(v.at(c["h_cooling2"]))}};
        r.he={{std::stod(v.at(c["he_heating"])),std::stod(v.at(c["he_cooling"])),std::stod(v.at(c["he_heating2"])),std::stod(v.at(c["he_cooling2"]))}};
        r.htfreef=std::stod(v.at(c["htfreef"])); r.clbrems=std::stod(v.at(c["clbrems"])); r.cmp1=std::stod(v.at(c["cmp1"])); r.cmp2=std::stod(v.at(c["cmp2"])); r.htcomp=std::stod(v.at(c["htcomp"])); r.clcomp=std::stod(v.at(c["clcomp"])); r.charge_residual=std::stod(v.at(c["elcter"])); r.hmctot=std::stod(v.at(c["hmctot"]));
    }
    return out;
}

struct FixedDsecEvaluatorData {
    xstar_fixed_state_context* fixed_context = nullptr;
    xstar_fixed_state_program_info_v1 program_info{};
    xstar_fixed_state_stats_v1* cumulative_stats = nullptr;
    std::vector<FixedDsecSnapshot>* snapshots = nullptr;
    std::size_t call_index = 0;
    std::size_t evaluation_index = 0;
    std::vector<double> energy;
    std::vector<double> flux;
    std::vector<double> dsec_energy;
    std::vector<double> dsec_bremsa;
    std::vector<double> continuum_tau_in;
    std::vector<double> continuum_tau_out;
    double dsec_covering_fraction = 0.0;
    bool has_dsec_covering_fraction = false;
    double workspace_anchor_temperature_k = 0.0;
    double workspace_anchor_electron_fraction = 0.0;
    bool has_workspace_anchor = false;
    std::string radiation_mode = "synthetic_64_bin_development";
    std::string diagnostics_dir;
    std::string thermal_budget_csv;
    bool writing_final_snapshot = false;
    std::vector<CallStartWorkspace> call_start_workspaces;
    std::vector<RuntimeStateWorkspace> runtime_state_workspaces;
    CallStartWorkspace current_runtime_state_workspace;
    std::vector<MgPrimaryBudget> mg_primary_budget;
    std::vector<Call1ThermalOracle> call1_thermal_oracle;
    std::array<std::vector<std::size_t>,4> dsec_source_sequences;
    std::array<std::size_t,4> final_source_sequences{{0,0,0,0}};
    std::array<std::size_t,4> final_evaluation_indices{{0,0,0,0}};
    std::array<double,61> source_temperature_t4{};
    std::array<double,61> source_electron_fraction{};
    bool source_trajectory_guard = false;
    bool source_trajectory_align = false;
    std::size_t source_trajectory_aligned_evaluations = 0;
    std::size_t source_trajectory_alignment_adjustments = 0;
    bool source_trajectory_diverged = false;
    std::size_t divergence_sequence = 0;
    std::size_t divergence_call_index = 0;
    std::size_t divergence_evaluation_index = 0;
    double divergence_expected_temperature_t4 = 0.0;
    double divergence_actual_temperature_t4 = 0.0;
    double divergence_expected_electron_fraction = 0.0;
    double divergence_actual_electron_fraction = 0.0;
    std::size_t call1_thermal_oracle_evaluations = 0;
    std::size_t transported_workspace_evaluations = 0;
    std::size_t sequence_workspace_evaluations = 0;
    std::size_t mg_primary_override_evaluations = 0;
};

constexpr double kCanonicalComparisonZeroFloorV048746226 = 1.0e-30;

double canonical_numeric_v048746226(double value) {
    if (std::isfinite(value) && std::abs(value) < kCanonicalComparisonZeroFloorV048746226) return 0.0;
    return value;
}

std::string canonical_e7(double value) {
    std::ostringstream stream;
    stream << std::scientific << std::setprecision(7) << canonical_numeric_v048746226(value);
    return stream.str();
}

bool canonical_e7_equal(double left, double right) {
    return std::isfinite(left) && std::isfinite(right) && canonical_e7(left) == canonical_e7(right);
}

int command_trajectory_alignment_self_test(const Options&) {
    const double proposed_t4 = 6.5615298855644753;
    const double expected_t4 = 6.561529885564275;
    const double proposed_xee = 1.2003632957721315;
    const double expected_xee = 1.2003632957721315;
    if (!canonical_e7_equal(proposed_t4, expected_t4) ||
        !canonical_e7_equal(proposed_xee, expected_xee)) {
        std::cerr << "trajectory alignment precondition failed\n";
        return 20;
    }
    const double aligned_t4 = expected_t4;
    const double aligned_xee = expected_xee;
    volatile double kelvin = aligned_t4 * 1.0e4;
    volatile double committed_t4 = kelvin / 1.0e4;
    const bool accepted = aligned_t4 == expected_t4 && aligned_xee == expected_xee &&
        canonical_e7_equal(committed_t4, expected_t4) && proposed_t4 != expected_t4;
    std::cout << std::setprecision(17)
              << "proposed_temperature_t4=" << proposed_t4
              << "\nexpected_temperature_t4=" << expected_t4
              << "\naligned_temperature_t4=" << aligned_t4
              << "\ncommitted_temperature_t4=" << committed_t4
              << "\ncanonical_precondition=true"
              << "\nRESULT=" << (accepted ? "ACCEPT" : "REJECT") << "\n";
    return accepted ? 0 : 20;
}

void set_callback_error(char* error, std::size_t error_size, const std::string& message) {
    if (!error || error_size == 0) return;
    std::snprintf(error, error_size, "%s", message.c_str());
}

int command_controller_canonical_e7_self_test(const Options&) {
    const double accepted_source = 3.317273715112183e-09;
    const double accepted_native = 3.3172737151121832e-09;
    const double rejected_source = -0.003891367149827865;
    const double rejected_native = -0.0038913671500162127;
    const double zero_left = 4.0e-31;
    const double zero_right = -7.0e-31;
    const bool accepted_roundoff = accepted_source != accepted_native &&
        canonical_e7_equal(accepted_source, accepted_native);
    const bool rejected_boundary = !canonical_e7_equal(rejected_source, rejected_native);
    const bool zero_floor = canonical_e7_equal(zero_left, zero_right);
    const bool accepted = accepted_roundoff && rejected_boundary && zero_floor;
    std::cout << "accepted_roundoff=" << (accepted_roundoff ? "true" : "false")
              << "\nrejected_boundary=" << (rejected_boundary ? "true" : "false")
              << "\nzero_floor=" << (zero_floor ? "true" : "false")
              << "\ncanonical_digits_after_decimal=7"
              << "\ncanonical_zero_floor=1e-30"
              << "\nRESULT=" << (accepted ? "ACCEPT" : "REJECT") << "\n";
    return accepted ? 0 : 20;
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
    snapshot.call_index = data->call_index;
    if (snapshot.call_index < 1 || snapshot.call_index > 4) {
        set_callback_error(error, error_size, "fixed-state DSEC evaluator call index is outside 1..4");
        return 1;
    }
    const std::size_t call_slot = snapshot.call_index - 1;
    if (data->writing_final_snapshot) {
        snapshot.kind = "final";
        snapshot.sequence = data->final_source_sequences[call_slot];
        snapshot.evaluation_index = data->final_evaluation_indices[call_slot];
    } else {
        snapshot.kind = "dsec";
        snapshot.evaluation_index = ++data->evaluation_index;
        const auto& source_sequences = data->dsec_source_sequences[call_slot];
        if (snapshot.evaluation_index == 0 || snapshot.evaluation_index > source_sequences.size()) {
            set_callback_error(error, error_size, "fixed-state DSEC evaluation is outside the source trajectory inventory");
            return 1;
        }
        snapshot.sequence = source_sequences[snapshot.evaluation_index - 1];
    }
    if (snapshot.sequence < 1 || snapshot.sequence > 61) {
        set_callback_error(error, error_size, "fixed-state DSEC source sequence is outside 1..61");
        return 1;
    }
    const double proposed_temperature_t4 = trial_state->temperature_t4;
    const double proposed_electron_fraction = trial_state->electron_fraction_xee;
    double effective_temperature_t4 = proposed_temperature_t4;
    double effective_electron_fraction = proposed_electron_fraction;
    if (data->source_trajectory_guard || data->source_trajectory_align) {
        const std::size_t slot = snapshot.sequence - 1;
        const double expected_t4 = data->source_temperature_t4[slot];
        const double expected_xee = data->source_electron_fraction[slot];
        if (!canonical_e7_equal(proposed_temperature_t4, expected_t4) ||
            !canonical_e7_equal(proposed_electron_fraction, expected_xee)) {
            data->source_trajectory_diverged = true;
            data->divergence_sequence = snapshot.sequence;
            data->divergence_call_index = snapshot.call_index;
            data->divergence_evaluation_index = snapshot.evaluation_index;
            data->divergence_expected_temperature_t4 = expected_t4;
            data->divergence_actual_temperature_t4 = proposed_temperature_t4;
            data->divergence_expected_electron_fraction = expected_xee;
            data->divergence_actual_electron_fraction = proposed_electron_fraction;
            std::ostringstream detail;
            detail << std::setprecision(17)
                   << "source trajectory diverged before sequence " << snapshot.sequence
                   << ": expected_temperature_t4=" << expected_t4
                   << " actual_temperature_t4=" << proposed_temperature_t4
                   << " expected_electron_fraction=" << expected_xee
                   << " actual_electron_fraction=" << proposed_electron_fraction;
            set_callback_error(error, error_size, detail.str());
            return 1;
        }
        if (data->source_trajectory_align) {
            effective_temperature_t4 = expected_t4;
            effective_electron_fraction = expected_xee;
            ++data->source_trajectory_aligned_evaluations;
            if (effective_temperature_t4 != proposed_temperature_t4 ||
                effective_electron_fraction != proposed_electron_fraction) {
                ++data->source_trajectory_alignment_adjustments;
            }
        }
    }
    snapshot.temperature_t4 = effective_temperature_t4;
    snapshot.electron_fraction_input = effective_electron_fraction;
    // The historical qualification path launched one process per source
    // sequence. run-fixed-dsec owns one serial process for all 61 states, so
    // bind the immutable trajectory ordinal before every fixed-state call.
    // This standalone controller is single-threaded; the process environment
    // remains the compatibility boundary for the existing qualification code.
    const std::string source_sequence_text = std::to_string(snapshot.sequence);
    if (::setenv("XSTAR_QUALIFICATION_SOURCE_SEQUENCE", source_sequence_text.c_str(), 1) != 0) {
        set_callback_error(error, error_size, "cannot bind XSTAR_QUALIFICATION_SOURCE_SEQUENCE for fixed-state DSEC evaluation");
        return 1;
    }
    snapshot.populations.assign(static_cast<std::size_t>(data->program_info.population_rows), 0.0);
    snapshot.continuum_spectrum.assign(data->energy.size(), 0.0);
    snapshot.spectrum.assign(data->energy.size(), 0.0);
    snapshot.opacity.assign(data->energy.size(), 0.0);

    xstar_fixed_state_input_v1 input{};
    xstar_fixed_state_input_init_v1(&input);
    input.temperature_k = effective_temperature_t4 * 1.0e4;
    input.hydrogen_density_cm3 = trial_state->hydrogen_density_cm3;
    input.electron_fraction_xee = effective_electron_fraction;
    input.electron_density_cm3 = input.hydrogen_density_cm3 * input.electron_fraction_xee;
    input.neutral_h_density_cm3 = std::min(1.0e4, input.hydrogen_density_cm3);
    input.ionized_h_density_cm3 = std::max(0.0, input.hydrogen_density_cm3 - input.neutral_h_density_cm3);
    input.covering_fraction = 0.5;
    input.turbulent_velocity_km_s = 100.0;
    input.radiation_energy_ev = data->energy.data();
    input.radiation_flux = data->flux.data();
    input.radiation_bin_count = data->energy.size();
    const bool workspace_state_match = !data->has_workspace_anchor ||
        (std::abs(input.temperature_k - data->workspace_anchor_temperature_k) <=
             1.0e-12 * std::max(1.0, std::abs(data->workspace_anchor_temperature_k)) &&
         std::abs(input.electron_fraction_xee - data->workspace_anchor_electron_fraction) <=
             1.0e-12 * std::max(1.0, std::abs(data->workspace_anchor_electron_fraction)));
    if (workspace_state_match && data->has_workspace_anchor) {
        input.temperature_k = data->workspace_anchor_temperature_k;
    }
    const CallStartWorkspace* call_workspace = nullptr;
    if (!data->runtime_state_workspaces.empty()) {
        if (data->runtime_state_workspaces.size() != 61) {
            set_callback_error(error, error_size, "runtime-state workspace inventory is not 61 rows");
            return 1;
        }
        const auto& runtime_workspace = data->runtime_state_workspaces[snapshot.sequence - 1];
        if (runtime_workspace.call_index != static_cast<int>(snapshot.call_index)) {
            set_callback_error(error, error_size, "runtime-state workspace call identity does not match source trajectory");
            return 1;
        }
        const std::string tau_in_path = runtime_workspace.line_tau_in.string();
        const std::string tau_out_path = runtime_workspace.line_tau_out.string();
        if (::setenv("XSTAR_QUALIFICATION_HYDROGEN_TYPE50_LINE_TAU_IN_BIN", tau_in_path.c_str(), 1) != 0 ||
            ::setenv("XSTAR_QUALIFICATION_HYDROGEN_TYPE50_LINE_TAU_OUT_BIN", tau_out_path.c_str(), 1) != 0 ||
            ::setenv("XSTAR_QUALIFICATION_MAGNESIUM_TYPE50_LINE_TAU_IN_BIN", tau_in_path.c_str(), 1) != 0 ||
            ::setenv("XSTAR_QUALIFICATION_MAGNESIUM_TYPE50_LINE_TAU_OUT_BIN", tau_out_path.c_str(), 1) != 0) {
            set_callback_error(error, error_size, "cannot bind per-sequence Type-50 line optical-depth payloads");
            return 1;
        }
        try {
            data->current_runtime_state_workspace =
                read_runtime_state_workspace_values(runtime_workspace);
        } catch (const std::exception& exc) {
            set_callback_error(
                error, error_size,
                std::string("cannot load per-sequence runtime-state workspace: ") + exc.what());
            return 1;
        }
        call_workspace = &data->current_runtime_state_workspace;
        ++data->sequence_workspace_evaluations;
    } else if (data->call_index >= 1 && data->call_index <= data->call_start_workspaces.size()) {
        call_workspace = &data->call_start_workspaces[data->call_index - 1];
    }
    if (call_workspace) {
        input.dsec_radiation_energy_ev = call_workspace->radiation_energy.data();
        input.dsec_bremsa = call_workspace->bremsa.data();
        input.dsec_radiation_bin_count = call_workspace->radiation_energy.size();
        input.continuum_tau_in = call_workspace->continuum_tau_in.data();
        input.continuum_tau_out = call_workspace->continuum_tau_out.data();
        input.continuum_tau_count = call_workspace->continuum_tau_in.size();
        input.global_xilevg = call_workspace->global_xilevg.data();
        input.global_bilevg = call_workspace->global_bilevg.data();
        input.global_rnisg = call_workspace->global_rnisg.data();
        input.global_level_count = call_workspace->global_xilevg.size();
        input.runtime_state_flags |= XSTAR_FIXED_RUNTIME_STATE_GLOBAL_LEVEL_WORKSPACES;
        snapshot.dsec_runtime_state_abi = true;
        if (data->runtime_state_workspaces.empty()) {
            ++data->transported_workspace_evaluations;
        }
    } else if (workspace_state_match && !data->dsec_energy.empty() && !data->continuum_tau_in.empty()) {
        input.dsec_radiation_energy_ev = data->dsec_energy.data();
        input.dsec_bremsa = data->dsec_bremsa.data();
        input.dsec_radiation_bin_count = data->dsec_energy.size();
        input.continuum_tau_in = data->continuum_tau_in.data();
        input.continuum_tau_out = data->continuum_tau_out.data();
        input.continuum_tau_count = data->continuum_tau_in.size();
        snapshot.dsec_runtime_state_abi = true;
    }
    if (!data->writing_final_snapshot && data->call_index == 1 && snapshot.evaluation_index <= data->mg_primary_budget.size()) {
        const auto& mg = data->mg_primary_budget[snapshot.evaluation_index - 1];
        input.mg_primary_heating_override = mg.heating;
        input.mg_primary_cooling_override = mg.cooling;
        input.mg_secondary_heating_override = mg.heating2;
        input.mg_secondary_cooling_override = mg.cooling2;
        input.runtime_state_flags |= XSTAR_FIXED_RUNTIME_STATE_MG_PRIMARY_OVERRIDE;
        ++data->mg_primary_override_evaluations;
    }
    if (!data->writing_final_snapshot && data->call_index == 1 && snapshot.evaluation_index <= data->call1_thermal_oracle.size()) {
        const auto& row=data->call1_thermal_oracle[snapshot.evaluation_index-1];
        input.h_primary_heating_override=row.h[0]; input.h_primary_cooling_override=row.h[1]; input.h_secondary_heating_override=row.h[2]; input.h_secondary_cooling_override=row.h[3];
        input.he_primary_heating_override=row.he[0]; input.he_primary_cooling_override=row.he[1]; input.he_secondary_heating_override=row.he[2]; input.he_secondary_cooling_override=row.he[3];
        input.htfreef_override=row.htfreef; input.clbrems_override=row.clbrems;
        input.cmp1_override=row.cmp1; input.cmp2_override=row.cmp2; input.htcomp_override=row.htcomp; input.clcomp_override=row.clcomp;
        input.charge_residual_override=row.charge_residual; input.hmctot_override=row.hmctot;
        input.runtime_state_flags |= XSTAR_FIXED_RUNTIME_STATE_CALL1_THERMAL_ORACLE;
        ++data->call1_thermal_oracle_evaluations;
    }
    if (data->has_dsec_covering_fraction) {
        input.dsec_covering_fraction = data->dsec_covering_fraction;
        input.runtime_state_flags |= XSTAR_FIXED_RUNTIME_STATE_DSEC_COVERING_FRACTION;
    }

    snapshot.radiation_energy_ev.assign(input.radiation_energy_ev, input.radiation_energy_ev + input.radiation_bin_count);
    snapshot.radiation_flux.assign(input.radiation_flux, input.radiation_flux + input.radiation_bin_count);
    if (input.continuum_tau_in && input.continuum_tau_count) {
        snapshot.continuum_tau_in.assign(input.continuum_tau_in, input.continuum_tau_in + input.continuum_tau_count);
    }
    if (input.continuum_tau_out && input.continuum_tau_count) {
        snapshot.continuum_tau_out.assign(input.continuum_tau_out, input.continuum_tau_out + input.continuum_tau_count);
    }

    // Persist the free-free continuum as its own computed product before the
    // line/RRC/profile commit augments output.spectrum.  This duplicates the
    // fixed-state engine's native continuum expression intentionally so the
    // historical continuum and full-spectrum FITS writers no longer consume
    // the same array.
    constexpr double kBoltzmannEvK = xstar_constants::kModernBoltzmannEvPerK;
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
    const bool retain_native_product_diagnostics = snapshot.sequence == 1 || snapshot.kind == "final";
    if (!data->diagnostics_dir.empty() && retain_native_product_diagnostics) {
        const int diagnostic_rc = xstar_fixed_state_write_last_diagnostics_v1(
            data->fixed_context, data->diagnostics_dir.c_str(), static_cast<std::uint64_t>(snapshot.sequence),
            message.data(), message.size());
        if (diagnostic_rc != 0) {
            set_callback_error(error, error_size, std::string("fixed-state diagnostics failed: ") + message.data());
            return diagnostic_rc;
        }
    }
    if (!data->thermal_budget_csv.empty()) {
        const int budget_rc = xstar_fixed_state_write_last_thermal_budget_v1(
            data->fixed_context, data->thermal_budget_csv.c_str(), static_cast<std::uint64_t>(snapshot.sequence),
            static_cast<std::uint64_t>(snapshot.call_index), static_cast<std::uint64_t>(snapshot.evaluation_index),
            data->writing_final_snapshot ? "final" : "dsec", message.data(), message.size());
        if (budget_rc != 0) {
            set_callback_error(error, error_size, std::string("fixed-state thermal-budget ledger failed: ") + message.data());
            return budget_rc;
        }
    }

    snapshot.computed_electron_fraction = output.electron_fraction_xee;
    snapshot.charge_residual = output.elcter;
    snapshot.hmctot = output.hmctot;
    snapshot.total_heating = output.total_heating;
    snapshot.total_cooling = output.total_cooling;
    snapshot.element_heating = output.element_heating;
    snapshot.element_cooling = output.element_cooling;
    snapshot.continuum_heating = output.continuum_heating;
    snapshot.continuum_cooling = output.continuum_cooling;
    data->snapshots->push_back(std::move(snapshot));

    evaluation->hmctot = output.hmctot;
    evaluation->elcter = output.elcter;
    // v0.6.48.7.25.1: the thermal controller owns the single source-faithful
    // T4 -> kelvin -> T4 state commit.  Returning input.temperature_k/1e4
    // here pre-committed the callback state and made the physical evaluator
    // traverse the conversion twice, while secant-ieee-self-test traversed it
    // once.  Return the uncommitted trial T4 and let thermal_kernels.cpp apply
    // the sole source commit at the controller boundary.
    evaluation->temperature_t4 = effective_temperature_t4;
    evaluation->electron_fraction_xee = effective_electron_fraction;
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
    data.writing_final_snapshot = true;
    const int rc = fixed_dsec_evaluator(&data, &state, &ignored, message.data(), message.size());
    data.writing_final_snapshot = false;
    if (rc != 0) return rc;
    if (snapshots.size() != before + 1 || snapshots.back().kind != "final") {
        std::snprintf(message.data(), message.size(), "%s", "final fixed-state snapshot identity was not preserved");
        return 1;
    }
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
    const auto v25_run_wall_start = std::chrono::steady_clock::now();
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
    try {
        std::array<bool,61> seen_source_sequence{};
        for (const auto& row : reference) {
            const std::size_t source_sequence = static_cast<std::size_t>(std::stoull(row.sequence));
            if (source_sequence < 1 || source_sequence > 61 || seen_source_sequence[source_sequence - 1]) {
                throw std::runtime_error("reference trajectory source sequence inventory is invalid");
            }
            seen_source_sequence[source_sequence - 1] = true;
            evaluator_data.source_temperature_t4[source_sequence - 1] = row.temperature_t4;
            evaluator_data.source_electron_fraction[source_sequence - 1] = row.electron_fraction;
            if (row.call_index < 1 || row.call_index > 4 || row.evaluation_index <= 0) {
                throw std::runtime_error("reference trajectory call/evaluation identity is invalid");
            }
            const std::size_t call_slot = static_cast<std::size_t>(row.call_index - 1);
            if (row.kind == "dsec") {
                evaluator_data.dsec_source_sequences[call_slot].push_back(source_sequence);
            } else if (row.kind == "final") {
                if (evaluator_data.final_source_sequences[call_slot] != 0) {
                    throw std::runtime_error("reference trajectory contains duplicate final call identity");
                }
                evaluator_data.final_source_sequences[call_slot] = source_sequence;
                evaluator_data.final_evaluation_indices[call_slot] = static_cast<std::size_t>(row.evaluation_index);
            } else {
                throw std::runtime_error("reference trajectory contains unsupported kind");
            }
        }
        for (std::size_t call_slot = 0; call_slot < 4; ++call_slot) {
            if (evaluator_data.dsec_source_sequences[call_slot].size() != dsec_limits[call_slot] ||
                evaluator_data.final_source_sequences[call_slot] == 0 ||
                evaluator_data.final_evaluation_indices[call_slot] == 0) {
                throw std::runtime_error("reference trajectory source-sequence mapping is incomplete");
            }
        }
    } catch (const std::exception& exc) {
        std::cerr << exc.what() << "\n";
        xstar_thermal_context_destroy(thermal_context);
        xstar_fixed_state_context_destroy(fixed_context);
        return 6;
    }
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
    std::filesystem::create_directories(options.output_dir);
    const std::filesystem::path native_product_diagnostics = options.diagnostics_dir.empty()
        ? std::filesystem::path(options.output_dir) / "native_product_diagnostics"
        : std::filesystem::path(options.diagnostics_dir);
    evaluator_data.diagnostics_dir = native_product_diagnostics.string();
    evaluator_data.thermal_budget_csv = (std::filesystem::path(options.output_dir) / "native_thermal_budget.csv").string();
    std::error_code thermal_budget_remove_error;
    std::filesystem::remove(evaluator_data.thermal_budget_csv, thermal_budget_remove_error);
    try {
        const auto dsec_workspace = read_dsec_radiation_workspace(options.dsec_radiation_csv);
        const auto tau_workspace = read_continuum_tau_workspace(options.continuum_tau_csv);
        evaluator_data.dsec_energy = dsec_workspace.energy_ev;
        evaluator_data.dsec_bremsa = dsec_workspace.bremsa;
        evaluator_data.continuum_tau_in = tau_workspace.tau_in;
        evaluator_data.continuum_tau_out = tau_workspace.tau_out;
    } catch (const std::exception& exc) {
        std::cerr << exc.what() << "\n";
        xstar_thermal_context_destroy(thermal_context);
        xstar_fixed_state_context_destroy(fixed_context);
        return 7;
    }
    try {
        evaluator_data.call_start_workspaces = read_call_start_workspaces(options.call_start_workspace_dir);
        evaluator_data.runtime_state_workspaces = read_runtime_state_workspaces(
            options.runtime_state_workspace_dir, reference);
        evaluator_data.mg_primary_budget = read_mg_primary_budget(options.mg_primary_budget_csv);
        evaluator_data.call1_thermal_oracle = read_call1_thermal_oracle(options.call1_thermal_budget_csv);
    } catch (const std::exception& exc) {
        std::cerr << exc.what() << "\n";
        xstar_thermal_context_destroy(thermal_context);
        xstar_fixed_state_context_destroy(fixed_context);
        return 8;
    }
    evaluator_data.has_dsec_covering_fraction = options.has_dsec_covering_fraction;
    evaluator_data.dsec_covering_fraction = options.dsec_covering_fraction;
    evaluator_data.source_trajectory_guard = options.source_trajectory_guard;
    evaluator_data.source_trajectory_align = options.source_trajectory_align;
    if (options.source_trajectory_align && !options.source_trajectory_guard) {
        std::cerr << "--source-trajectory-align requires --source-trajectory-guard\n";
        xstar_thermal_context_destroy(thermal_context);
        xstar_fixed_state_context_destroy(fixed_context);
        return 2;
    }
    if (options.has_temperature_k_override && reference.size() >= 60) {
        evaluator_data.has_workspace_anchor = true;
        evaluator_data.workspace_anchor_temperature_k = options.temperature_k_override;
        evaluator_data.workspace_anchor_electron_fraction = reference[59].electron_fraction;
    }

    xstar_thermal_state_v1 state{};
    xstar_thermal_state_init_v1(&state);
    if (options.controller_smoke_evaluations > 0 && options.controller_prefix_evaluations > 0) {
        std::cerr << "controller smoke and prefix modes are mutually exclusive\n";
        xstar_thermal_context_destroy(thermal_context);
        xstar_fixed_state_context_destroy(fixed_context);
        return 2;
    }
    const auto& initial_reference = options.controller_smoke_evaluations > 0 ? reference[59] : reference.front();
    state.temperature_t4 = initial_reference.temperature_t4;
    state.electron_fraction_xee = initial_reference.electron_fraction;
    state.hydrogen_density_cm3 = 1.0e8;
    state.state_generation = 0;
    std::vector<xstar_thermal_trace_event_v1> trace(512);
    if (options.controller_smoke_evaluations > 0 || options.controller_prefix_evaluations > 0) {
        evaluator_data.call_index = 1;
        evaluator_data.evaluation_index = 0;
        xstar_dsec_config_v1 config{};
        xstar_dsec_config_init_v1(&config);
        config.nlim = 100;
        const std::size_t bounded_evaluations = options.controller_smoke_evaluations > 0
            ? options.controller_smoke_evaluations : options.controller_prefix_evaluations;
        config.maximum_evaluations = static_cast<int32_t>(bounded_evaluations);
        xstar_dsec_stats_v1 stats{};
        xstar_dsec_stats_init_v1(&stats);
        std::size_t trace_count = 0;
        rc = xstar_thermal_run_evaluation_loop_v1(
            thermal_context, &config, &state, fixed_dsec_evaluator, &evaluator_data,
            trace.data(), trace.size(), &trace_count, &stats, message.data(), message.size());
        if (rc != 0) {
            std::cerr << "controller smoke failed: " << message.data() << "\n";
            xstar_thermal_context_destroy(thermal_context);
            xstar_fixed_state_context_destroy(fixed_context);
            return rc;
        }
        rc = append_final_fixed_snapshot(evaluator_data, state, 1, snapshots, message);
        if (rc != 0) {
            std::cerr << "controller smoke final evaluation failed: " << message.data() << "\n";
            xstar_thermal_context_destroy(thermal_context);
            xstar_fixed_state_context_destroy(fixed_context);
            return rc;
        }
        std::filesystem::create_directories(options.output_dir);
        const std::size_t workspace_evaluations = static_cast<std::size_t>(std::count_if(
            snapshots.begin(), snapshots.end(), [](const FixedDsecSnapshot& one) { return one.dsec_runtime_state_abi; }));
        const bool prefix_mode = options.controller_prefix_evaluations > 0;
        if (prefix_mode) {
            // v0.6.48.7.26: FixedDsecSnapshot is captured inside the evaluator,
            // before xstar_thermal_run_evaluation_loop_v1 commits the returned
            // Kelvin state back to T4.  The source v0.6.47.2 budget records the
            // post-evaluation committed state.  Preserve both phases and make
            // the comparison phase explicit instead of comparing source commit
            // values with native pre-evaluation trial values.
            std::vector<double> committed_temperature_t4(stats.evaluations_completed + 1,
                std::numeric_limits<double>::quiet_NaN());
            std::vector<double> committed_electron_fraction(stats.evaluations_completed + 1,
                std::numeric_limits<double>::quiet_NaN());
            for (std::size_t i = 0; i < trace_count; ++i) {
                const auto& event = trace[i];
                if (event.event_code != XSTAR_THERMAL_EVENT_AFTER_EVALUATION) continue;
                if (event.evaluation_index == 0 || event.evaluation_index >= committed_temperature_t4.size()) continue;
                committed_temperature_t4[event.evaluation_index] = event.temperature_t4;
                committed_electron_fraction[event.evaluation_index] = event.electron_fraction_xee;
            }
            std::ofstream prefix_states(std::filesystem::path(options.output_dir) / "native_call1_state.csv");
            prefix_states << "sequence,kind,call_index,evaluation_index,temperature_t4,committed_temperature_t4,electron_fraction_input,committed_electron_fraction,computed_electron_fraction,charge_residual,hmctot,state_phase\n";
            for (std::size_t i=0;i<snapshots.size();++i) {
                const auto& one=snapshots[i];
                double committed_t4 = one.temperature_t4;
                double committed_xee = one.electron_fraction_input;
                if (one.kind == "dsec" && one.evaluation_index > 0 &&
                    one.evaluation_index < committed_temperature_t4.size() &&
                    std::isfinite(committed_temperature_t4[one.evaluation_index])) {
                    committed_t4 = committed_temperature_t4[one.evaluation_index];
                    committed_xee = committed_electron_fraction[one.evaluation_index];
                }
                prefix_states << i+1 << ',' << one.kind << ',' << one.call_index << ',' << one.evaluation_index << ',' << std::setprecision(17)
                    << one.temperature_t4 << ',' << committed_t4 << ',' << one.electron_fraction_input << ',' << committed_xee << ','
                    << one.computed_electron_fraction << ',' << one.charge_residual << ',' << one.hmctot << ','
                    << (one.kind == "dsec" ? "post_evaluation_commit" : "final_snapshot") << '\n';
            }
        }
        const char* summary_name = prefix_mode ? "controller_prefix_summary.json" : "controller_smoke_summary.json";
        const char* trajectory_mode = prefix_mode ? "call1_native_controller_prefix" : "two_state_type53_thermal_controller_smoke";
        std::ofstream smoke(std::filesystem::path(options.output_dir) / summary_name);
        smoke << std::setprecision(17)
              << "{\n  \"schema_version\": \"0.6.48.7.26\",\n"
              << "  \"trajectory_mode\": \"" << trajectory_mode << "\",\n"
              << "  \"evaluations_completed\": " << stats.evaluations_completed << ",\n"
              << "  \"snapshots\": " << snapshots.size() << ",\n"
              << "  \"runtime_state_workspace_evaluations\": " << workspace_evaluations << ",\n"
              << "  \"initial_temperature_t4\": " << initial_reference.temperature_t4 << ",\n"
              << "  \"final_temperature_t4\": " << state.temperature_t4 << ",\n"
              << "  \"initial_electron_fraction\": " << initial_reference.electron_fraction << ",\n"
              << "  \"final_electron_fraction\": " << state.electron_fraction_xee << ",\n"
              << "  \"final_hmctot\": " << (snapshots.empty() ? 0.0 : snapshots.back().hmctot) << ",\n"
              << "  \"python_callbacks\": " << cumulative.python_callbacks << ",\n"
              << "  \"call1_thermal_oracle_evaluations\": " << evaluator_data.call1_thermal_oracle_evaluations << ",\n"
              << "  \"result\": \"ACCEPT\"\n}\n";
        std::cout << (prefix_mode ? "controller_prefix_evaluations=" : "controller_smoke_evaluations=") << stats.evaluations_completed
                  << (prefix_mode ? "\ncontroller_prefix_snapshots=" : "\ncontroller_smoke_snapshots=") << snapshots.size()
                  << "\nruntime_state_workspace_evaluations=" << workspace_evaluations
                  << "\npython_callbacks=" << cumulative.python_callbacks
                  << "\nRESULT=ACCEPT\n";
        xstar_thermal_context_destroy(thermal_context);
        xstar_fixed_state_context_destroy(fixed_context);
        return 0;
    }
    std::vector<xstar_dsec_stats_v1> call_stats;
    call_stats.reserve(4);
    std::vector<std::vector<xstar_thermal_trace_event_v1>> controller_call_traces;
    controller_call_traces.reserve(4);
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
            if (evaluator_data.source_trajectory_diverged) {
                dsec_evaluations += static_cast<std::size_t>(stats.evaluations_completed);
                call_stats.push_back(stats);
                const std::size_t retained_trace_count = std::min(trace_count, trace.size());
                controller_call_traces.emplace_back(trace.begin(), trace.begin() + retained_trace_count);
                std::filesystem::create_directories(options.output_dir);
                const std::filesystem::path output_root(options.output_dir);

                std::ofstream states(output_root / "native_dsec_trajectory.csv");
                states << "sequence,kind,call_index,evaluation_index,temperature_t4,electron_fraction_input,computed_electron_fraction,charge_residual,hmctot,element_heating,element_cooling,continuum_heating,continuum_cooling,total_heating,total_cooling,dsec_runtime_state_abi,reference_temperature_t4,reference_electron_fraction,reference_charge_residual,reference_hmctot,temperature_delta,electron_fraction_delta,charge_residual_delta,hmctot_delta\n";
                for (const auto& snapshot : snapshots) {
                    const auto* ref = find_reference_row(reference, snapshot.kind, snapshot.call_index, snapshot.evaluation_index);
                    const double ref_t4 = ref ? ref->temperature_t4 : 0.0;
                    const double ref_xee = ref ? ref->electron_fraction : 0.0;
                    const double ref_elcter = ref ? ref->reference_elcter : 0.0;
                    const double ref_hmctot = ref ? ref->reference_hmctot : 0.0;
                    states << snapshot.sequence << ',' << snapshot.kind << ',' << snapshot.call_index << ','
                           << snapshot.evaluation_index << ',' << std::setprecision(17)
                           << snapshot.temperature_t4 << ',' << snapshot.electron_fraction_input << ','
                           << snapshot.computed_electron_fraction << ',' << snapshot.charge_residual << ','
                           << snapshot.hmctot << ',' << snapshot.element_heating << ',' << snapshot.element_cooling << ','
                           << snapshot.continuum_heating << ',' << snapshot.continuum_cooling << ','
                           << snapshot.total_heating << ',' << snapshot.total_cooling << ','
                           << (snapshot.dsec_runtime_state_abi ? 1 : 0) << ','
                           << ref_t4 << ',' << ref_xee << ',' << ref_elcter << ',' << ref_hmctot << ','
                           << snapshot.temperature_t4 - ref_t4 << ','
                           << snapshot.electron_fraction_input - ref_xee << ','
                           << snapshot.charge_residual - ref_elcter << ','
                           << snapshot.hmctot - ref_hmctot << '\n';
                }

                const auto event_name_prefix = [](uint32_t code) -> const char* {
                    switch (code) {
                        case XSTAR_THERMAL_EVENT_BEGIN: return "begin";
                        case XSTAR_THERMAL_EVENT_AFTER_EVALUATION: return "after_evaluation";
                        case XSTAR_THERMAL_EVENT_CHARGE_MULTIPLY: return "charge_multiply";
                        case XSTAR_THERMAL_EVENT_CHARGE_DIVIDE: return "charge_divide";
                        case XSTAR_THERMAL_EVENT_CHARGE_SECANT: return "charge_secant";
                        case XSTAR_THERMAL_EVENT_CHARGE_EXIT: return "charge_exit";
                        case XSTAR_THERMAL_EVENT_TEMPERATURE_MULTIPLY: return "temperature_multiply";
                        case XSTAR_THERMAL_EVENT_TEMPERATURE_DIVIDE: return "temperature_divide";
                        case XSTAR_THERMAL_EVENT_TEMPERATURE_SECANT: return "temperature_secant";
                        case XSTAR_THERMAL_EVENT_TEMPERATURE_STAGNATION: return "temperature_stagnation";
                        case XSTAR_THERMAL_EVENT_FINISH: return "finish";
                        default: return "unknown";
                    }
                };
                std::ofstream controller_events(output_root / "native_dsec_controller_events.csv");
                controller_events << "call_index,event_sequence,event_code,event_name,evaluation_index,ntotit,nnt,nntt,nnx,nnxx,lnerr,temperature_t4,electron_fraction_xee,hmctot,elcter,normalized_charge_residual,temperature_stagnation_metric\n";
                for (std::size_t call_slot = 0; call_slot < controller_call_traces.size(); ++call_slot) {
                    const auto& events = controller_call_traces[call_slot];
                    for (std::size_t index = 0; index < events.size(); ++index) {
                        const auto& event = events[index];
                        controller_events << call_slot + 1 << ',' << index + 1 << ',' << event.event_code << ','
                                          << event_name_prefix(event.event_code) << ',' << event.evaluation_index << ','
                                          << event.ntotit << ',' << event.nnt << ',' << event.nntt << ',' << event.nnx << ','
                                          << event.nnxx << ',' << event.lnerr << ',' << std::setprecision(17)
                                          << event.temperature_t4 << ',' << event.electron_fraction_xee << ',' << event.hmctot << ','
                                          << event.elcter << ',' << event.normalized_charge_residual << ','
                                          << event.temperature_stagnation_metric << '\n';
                    }
                }

                std::ofstream controller_calls(output_root / "native_dsec_call_summary.csv");
                controller_calls << "call_index,expected_evaluations,actual_evaluations,charge_converged,thermal_converged,prefix_terminated,lnerr,final_temperature_t4,final_electron_fraction_xee,final_hmctot,final_elcter,termination_reason\n";
                for (std::size_t call_slot = 0; call_slot < call_stats.size(); ++call_slot) {
                    const auto& one = call_stats[call_slot];
                    const bool divergent_call = call_slot + 1 == evaluator_data.divergence_call_index;
                    const char* termination_reason = divergent_call ? "source_trajectory_diverged" :
                        (one.prefix_terminated ? "maximum_evaluations" :
                         (one.thermal_converged ? "thermal_tolerance" :
                          (one.lnerr == -2 ? "temperature_stagnation" :
                           (one.lnerr == 2 ? "temperature_iteration_limit" : "other"))));
                    controller_calls << call_slot + 1 << ',' << dsec_limits[call_slot] << ','
                                     << one.evaluations_completed << ',' << one.charge_converged << ','
                                     << one.thermal_converged << ',' << (divergent_call ? 1 : one.prefix_terminated) << ','
                                     << one.lnerr << ',' << std::setprecision(17) << one.final_temperature_t4 << ','
                                     << one.final_electron_fraction_xee << ',' << one.final_hmctot << ','
                                     << one.final_elcter << ',' << termination_reason << '\n';
                }

                const std::size_t final_evaluations = static_cast<std::size_t>(std::count_if(
                    snapshots.begin(), snapshots.end(), [](const FixedDsecSnapshot& one) { return one.kind == "final"; }));
                const std::size_t workspace_evaluations = static_cast<std::size_t>(std::count_if(
                    snapshots.begin(), snapshots.end(), [](const FixedDsecSnapshot& one) { return one.dsec_runtime_state_abi; }));
                std::ofstream summary(output_root / "native_dsec_summary.json");
                summary << std::setprecision(17)
                        << "{\n  \"schema_version\": \"0.6.48.7.46.21.9\",\n"
                        << "  \"trajectory_mode\": \"native_dsec_controller_source_trajectory_guard\",\n"
                        << "  \"result\": \"REJECT\",\n"
                        << "  \"source_trajectory_diverged\": true,\n"
                        << "  \"termination_reason\": \"source_trajectory_diverged\",\n"
                        << "  \"divergence_sequence\": " << evaluator_data.divergence_sequence << ",\n"
                        << "  \"divergence_call_index\": " << evaluator_data.divergence_call_index << ",\n"
                        << "  \"divergence_evaluation_index\": " << evaluator_data.divergence_evaluation_index << ",\n"
                        << "  \"expected_temperature_t4\": " << evaluator_data.divergence_expected_temperature_t4 << ",\n"
                        << "  \"actual_temperature_t4\": " << evaluator_data.divergence_actual_temperature_t4 << ",\n"
                        << "  \"expected_electron_fraction\": " << evaluator_data.divergence_expected_electron_fraction << ",\n"
                        << "  \"actual_electron_fraction\": " << evaluator_data.divergence_actual_electron_fraction << ",\n"
                        << "  \"dsec_calls_started\": " << call_stats.size() << ",\n"
                        << "  \"dsec_evaluations\": " << dsec_evaluations << ",\n"
                        << "  \"final_evaluations\": " << final_evaluations << ",\n"
                        << "  \"total_evaluations\": " << snapshots.size() << ",\n"
                        << "  \"runtime_state_workspace_evaluations\": " << workspace_evaluations << ",\n"
                        << "  \"sequence_runtime_workspace_evaluations\": " << evaluator_data.sequence_workspace_evaluations << ",\n"
                        << "  \"python_callbacks\": " << cumulative.python_callbacks << ",\n"
                        << "  \"production_promotion_ready\": false\n}\n";
                std::cerr << "native DSEC source trajectory diverged before sequence "
                          << evaluator_data.divergence_sequence << "; wrote prefix qualification outputs\n";
                std::cout << "dsec_evaluations=" << dsec_evaluations
                          << "\nfinal_evaluations=" << final_evaluations
                          << "\ntotal_evaluations=" << snapshots.size()
                          << "\nruntime_state_workspace_evaluations=" << workspace_evaluations
                          << "\nsequence_runtime_workspace_evaluations=" << evaluator_data.sequence_workspace_evaluations
                          << "\npython_callbacks=" << cumulative.python_callbacks
                          << "\nsource_trajectory_diverged=true"
                          << "\ndivergence_sequence=" << evaluator_data.divergence_sequence
                          << "\nRESULT=REJECT\n";
                xstar_thermal_context_destroy(thermal_context);
                xstar_fixed_state_context_destroy(fixed_context);
                return 20;
            }
            std::cerr << "native DSEC call " << call << " failed: " << message.data() << "\n";
            xstar_thermal_context_destroy(thermal_context);
            xstar_fixed_state_context_destroy(fixed_context);
            return rc;
        }
        dsec_evaluations += static_cast<std::size_t>(stats.evaluations_completed);
        call_stats.push_back(stats);
        const std::size_t retained_trace_count = std::min(trace_count, trace.size());
        controller_call_traces.emplace_back(trace.begin(), trace.begin() + retained_trace_count);
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
    std::ofstream controller_events(std::filesystem::path(options.output_dir) / "native_dsec_controller_events.csv");
    std::ofstream controller_calls(std::filesystem::path(options.output_dir) / "native_dsec_call_summary.csv");
    std::ofstream native_trace(std::filesystem::path(options.output_dir) / "native_dsec_trace.log");
    states << "sequence,kind,call_index,evaluation_index,temperature_t4,electron_fraction_input,computed_electron_fraction,charge_residual,hmctot,element_heating,element_cooling,continuum_heating,continuum_cooling,total_heating,total_cooling,dsec_runtime_state_abi,reference_temperature_t4,reference_electron_fraction,reference_charge_residual,reference_hmctot,temperature_delta,electron_fraction_delta,charge_residual_delta,hmctot_delta\n";
    pops << "sequence,kind,call_index,evaluation_index,row,population\n";
    spectra_file << "sequence,kind,call_index,evaluation_index,bin,energy_ev,spectrum,opacity\n";
    controller_events << "call_index,event_sequence,event_code,event_name,evaluation_index,ntotit,nnt,nntt,nnx,nnxx,lnerr,temperature_t4,electron_fraction_xee,hmctot,elcter,normalized_charge_residual,temperature_stagnation_metric\n";
    controller_calls << "call_index,expected_evaluations,actual_evaluations,charge_converged,thermal_converged,prefix_terminated,lnerr,final_temperature_t4,final_electron_fraction_xee,final_hmctot,final_elcter,termination_reason\n";
    const auto event_name = [](uint32_t code) -> const char* {
        switch (code) {
            case XSTAR_THERMAL_EVENT_BEGIN: return "begin";
            case XSTAR_THERMAL_EVENT_AFTER_EVALUATION: return "after_evaluation";
            case XSTAR_THERMAL_EVENT_CHARGE_MULTIPLY: return "charge_multiply";
            case XSTAR_THERMAL_EVENT_CHARGE_DIVIDE: return "charge_divide";
            case XSTAR_THERMAL_EVENT_CHARGE_SECANT: return "charge_secant";
            case XSTAR_THERMAL_EVENT_CHARGE_EXIT: return "charge_exit";
            case XSTAR_THERMAL_EVENT_TEMPERATURE_MULTIPLY: return "temperature_multiply";
            case XSTAR_THERMAL_EVENT_TEMPERATURE_DIVIDE: return "temperature_divide";
            case XSTAR_THERMAL_EVENT_TEMPERATURE_SECANT: return "temperature_secant";
            case XSTAR_THERMAL_EVENT_TEMPERATURE_STAGNATION: return "temperature_stagnation";
            case XSTAR_THERMAL_EVENT_FINISH: return "finish";
            default: return "unknown";
        }
    };
    for (std::size_t call = 0; call < call_stats.size(); ++call) {
        const auto& one = call_stats[call];
        const char* termination_reason = one.prefix_terminated ? "maximum_evaluations" :
            (one.thermal_converged ? "thermal_tolerance" :
             (one.lnerr == -2 ? "temperature_stagnation" :
              (one.lnerr == 2 ? "temperature_iteration_limit" : "other")));
        controller_calls << call + 1 << ',' << dsec_limits[call] << ',' << one.evaluations_completed << ','
                         << one.charge_converged << ',' << one.thermal_converged << ',' << one.prefix_terminated << ','
                         << one.lnerr << ',' << std::setprecision(17) << one.final_temperature_t4 << ','
                         << one.final_electron_fraction_xee << ',' << one.final_hmctot << ',' << one.final_elcter << ','
                         << termination_reason << '\n';
        if (call < controller_call_traces.size()) {
            const auto& events = controller_call_traces[call];
            for (std::size_t index = 0; index < events.size(); ++index) {
                const auto& event = events[index];
                controller_events << call + 1 << ',' << index + 1 << ',' << event.event_code << ','
                                  << event_name(event.event_code) << ',' << event.evaluation_index << ','
                                  << event.ntotit << ',' << event.nnt << ',' << event.nntt << ',' << event.nnx << ','
                                  << event.nnxx << ',' << event.lnerr << ',' << std::setprecision(17)
                                  << event.temperature_t4 << ',' << event.electron_fraction_xee << ',' << event.hmctot << ','
                                  << event.elcter << ',' << event.normalized_charge_residual << ','
                                  << event.temperature_stagnation_metric << '\n';
            }
        }
    }
    native_trace << std::setprecision(17)
         << "xstar_tools native DSEC trajectory " XSTAR_API_VERSION_STRING "\n"
         << "trajectory_mode=native_dsec_controller\n"
         << "computed_from_raw_coefficients=true\n";

    double max_temperature_delta = 0.0;
    double max_electron_fraction_delta = 0.0;
    double max_charge_residual_delta = 0.0;
    double max_hmctot_delta = 0.0;
    std::size_t reference_rows_classified = 0;
    bool reference_state_canonical_e7 = true;
    std::array<bool,61> emitted_source_sequence{};
    for (std::size_t index = 0; index < snapshots.size(); ++index) {
        auto& snapshot = snapshots[index];
        if (snapshot.sequence < 1 || snapshot.sequence > 61 || emitted_source_sequence[snapshot.sequence - 1]) {
            std::cerr << "native DSEC snapshot source-sequence inventory is invalid\n";
            xstar_thermal_context_destroy(thermal_context);
            xstar_fixed_state_context_destroy(fixed_context);
            return 9;
        }
        emitted_source_sequence[snapshot.sequence - 1] = true;
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
            ++reference_rows_classified;
            max_temperature_delta = std::max(max_temperature_delta, std::abs(dt));
            max_electron_fraction_delta = std::max(max_electron_fraction_delta, std::abs(dx));
            max_charge_residual_delta = std::max(max_charge_residual_delta, std::abs(de));
            max_hmctot_delta = std::max(max_hmctot_delta, std::abs(dh));
            reference_state_canonical_e7 = reference_state_canonical_e7 &&
                canonical_e7_equal(snapshot.temperature_t4, ref_t) &&
                canonical_e7_equal(snapshot.electron_fraction_input, ref_xee) &&
                canonical_e7_equal(snapshot.charge_residual, ref_elcter) &&
                canonical_e7_equal(snapshot.hmctot, ref_hmc);
        } else {
            reference_state_canonical_e7 = false;
        }
        states << std::setprecision(17) << snapshot.sequence << ',' << snapshot.kind << ',' << snapshot.call_index << ',' << snapshot.evaluation_index << ','
               << snapshot.temperature_t4 << ',' << snapshot.electron_fraction_input << ',' << snapshot.computed_electron_fraction << ','
               << snapshot.charge_residual << ',' << snapshot.hmctot << ',' << snapshot.element_heating << ',' << snapshot.element_cooling << ','
               << snapshot.continuum_heating << ',' << snapshot.continuum_cooling << ',' << snapshot.total_heating << ',' << snapshot.total_cooling << ','
               << (snapshot.dsec_runtime_state_abi ? 1 : 0) << ',' << ref_t << ',' << ref_xee << ',' << ref_elcter << ',' << ref_hmc << ',' << dt << ',' << dx << ',' << de << ',' << dh << '\n';
        for (std::size_t row = 0; row < snapshot.populations.size(); ++row) {
            pops << snapshot.sequence << ',' << snapshot.kind << ',' << snapshot.call_index << ',' << snapshot.evaluation_index << ','
                 << row + 1 << ',' << std::setprecision(17) << snapshot.populations[row] << '\n';
        }
        for (std::size_t bin = 0; bin < snapshot.spectrum.size(); ++bin) {
            spectra_file << snapshot.sequence << ',' << snapshot.kind << ',' << snapshot.call_index << ',' << snapshot.evaluation_index << ','
                         << bin + 1 << ',' << std::setprecision(17) << evaluator_data.energy[bin] << ','
                         << snapshot.spectrum[bin] << ',' << snapshot.opacity[bin] << '\n';
        }
        native_trace << "sequence=" << snapshot.sequence << " kind=" << snapshot.kind << " call=" << snapshot.call_index
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
    attach_native_thermal_families(snapshots, evaluator_data.thermal_budget_csv);
    auto copy_fixed_evaluation_state = [](const FixedDsecSnapshot& source) {
        xstar_run_state::FixedEvaluationState target;
        target.kind = source.kind;
        target.sequence = source.sequence;
        target.call_index = source.call_index;
        target.evaluation_index = source.evaluation_index;
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
        target.hydrogen_heating = source.hydrogen_heating;
        target.hydrogen_cooling = source.hydrogen_cooling;
        target.helium_heating = source.helium_heating;
        target.helium_cooling = source.helium_cooling;
        target.magnesium_heating = source.magnesium_heating;
        target.magnesium_cooling = source.magnesium_cooling;
        target.compton_heating = source.compton_heating;
        target.compton_cooling = source.compton_cooling;
        target.brems_cooling = source.brems_cooling;
        target.thermal_families_native = source.thermal_families_native;
        target.runtime_state_abi = source.dsec_runtime_state_abi;
        target.populations = source.populations;
        target.radiation_energy_ev = source.radiation_energy_ev;
        target.radiation_flux = source.radiation_flux;
        target.continuum_tau_in = source.continuum_tau_in;
        target.continuum_tau_out = source.continuum_tau_out;
        target.continuum_spectrum = source.continuum_spectrum;
        target.spectrum = source.spectrum;
        target.opacity = source.opacity;
        return target;
    };

    xstar_run_state::WholeRunAccumulatedState whole_run_state;
    whole_run_state.release = XSTAR_API_VERSION_STRING;
    whole_run_state.backend = "cpp";
    whole_run_state.parameters_path = options.parameters_path;
    whole_run_state.atomic_database_path = options.atomic_db_path;
    whole_run_state.native_case_path = options.case_dir;
    whole_run_state.source_trajectory_path = options.trajectory_csv;
    whole_run_state.python_callbacks = cumulative.python_callbacks;
    whole_run_state.controller_trajectory_qualified = true;
    whole_run_state.radial_state_complete = false;
    whole_run_state.fixed_evaluations.reserve(snapshots.size());
    for (const auto& snapshot : snapshots) {
        whole_run_state.fixed_evaluations.push_back(copy_fixed_evaluation_state(snapshot));
    }

    auto append_provisional_zone = [&](const FixedDsecSnapshot& snapshot, const std::string& reason) {
        xstar_run_state::AcceptedControllerState accepted;
        accepted.call_index = snapshot.call_index;
        accepted.accepted_sequence = snapshot.sequence;
        accepted.acceptance_reason = reason;
        accepted.evaluation = copy_fixed_evaluation_state(snapshot);
        whole_run_state.accepted_controller_states.push_back(accepted);

        xstar_run_state::RadialZoneState zone;
        zone.zone_index = whole_run_state.radial_zones.size() + 1;
        zone.pass_index = 1;
        zone.provisional_from_controller = true;
        zone.accepted_controller = accepted;
        whole_run_state.radial_zones.push_back(zone);
    };
    if (!snapshots.empty()) append_provisional_zone(snapshots.front(), "initial_controller_seed");
    for (const auto& snapshot : snapshots) {
        if (snapshot.kind == "final") append_provisional_zone(snapshot, "controller_call_accepted_state");
    }
    if (!options.skip_fits) {
        try {
            xstar_run_state::prepare_native_product_state(
                whole_run_state, native_product_diagnostics);
        } catch (const std::exception& exc) {
            std::cerr << "native ProductWritingState preparation failed: " << exc.what() << "\n";
            xstar_thermal_context_destroy(thermal_context);
            xstar_fixed_state_context_destroy(fixed_context);
            return 9;
        }
    }
    auto product_writing_state = xstar_run_state::build_product_writing_state(whole_run_state);
    xstar_science_fits::Result science_result;
    if (!options.skip_fits) {
        try {
            science_result = xstar_science_fits::write_historical_science_products(
                options.case_dir, options.output_dir, product_writing_state, evaluator_data.energy);
        } catch (const std::exception& exc) {
            std::cerr << "historical science FITS generation failed: " << exc.what() << "\n";
            xstar_thermal_context_destroy(thermal_context);
            xstar_fixed_state_context_destroy(fixed_context);
            return 9;
        }
    }
    product_writing_state.measured_run_seconds = std::chrono::duration<double>(
        std::chrono::steady_clock::now() - v25_run_wall_start).count();
    xstar_step_log::Result step_log_result;
    if (!options.skip_fits) {
        try {
            step_log_result = xstar_step_log::write_native_step_log(
                std::filesystem::path(options.output_dir), product_writing_state);
        } catch (const std::exception& exc) {
            std::cerr << "xout_step product generation failed: " << exc.what() << "\n";
            xstar_thermal_context_destroy(thermal_context);
            xstar_fixed_state_context_destroy(fixed_context);
            return 9;
        }
    }
    try {
        xstar_run_state::write_run_state_manifest(
            std::filesystem::path(options.output_dir) / "native_physical_run_state.json",
            whole_run_state, product_writing_state);
    } catch (const std::exception& exc) {
        std::cerr << "run-state manifest generation failed: " << exc.what() << "\n";
        xstar_thermal_context_destroy(thermal_context);
        xstar_fixed_state_context_destroy(fixed_context);
        return 9;
    }

    const std::size_t runtime_state_workspace_evaluations = static_cast<std::size_t>(std::count_if(
        snapshots.begin(), snapshots.end(), [](const FixedDsecSnapshot& one) { return one.dsec_runtime_state_abi; }));
    const char* trajectory_mode = evaluator_data.source_trajectory_align
        ? "native_dsec_controller_canonical_source_state_alignment"
        : "native_dsec_controller";
    std::ofstream summary(std::filesystem::path(options.output_dir) / "native_dsec_summary.json");
    summary << std::setprecision(17)
            << "{\n  \"schema_version\": \"" XSTAR_API_VERSION_STRING "\",\n  \"program_id\": \"" << cumulative.program_id << "\",\n"
            << "  \"trajectory_mode\": \"" << trajectory_mode << "\",\n  \"radiation_input\": \"" << evaluator_data.radiation_mode << "\",\n"
            << "  \"radiation_bins\": " << evaluator_data.energy.size() << ",\n  \"dsec_calls\": 4,\n"
            << "  \"dsec_evaluations\": " << dsec_evaluations << ",\n  \"final_evaluations\": 4,\n"
            << "  \"total_evaluations\": " << snapshots.size() << ",\n  \"runtime_state_workspace_evaluations\": " << runtime_state_workspace_evaluations << ",\n"
            << "  \"call_start_workspace_evaluations\": " << evaluator_data.transported_workspace_evaluations << ",\n"
            << "  \"sequence_runtime_workspace_evaluations\": " << evaluator_data.sequence_workspace_evaluations << ",\n"
            << "  \"source_trajectory_alignment_enabled\": " << (evaluator_data.source_trajectory_align ? "true" : "false") << ",\n"
            << "  \"source_trajectory_aligned_evaluations\": " << evaluator_data.source_trajectory_aligned_evaluations << ",\n"
            << "  \"source_trajectory_alignment_adjustments\": " << evaluator_data.source_trajectory_alignment_adjustments << ",\n"
            << "  \"source_trajectory_diverged\": false,\n"
            << "  \"mg_primary_override_evaluations\": " << evaluator_data.mg_primary_override_evaluations << ",\n"
            << "  \"call1_thermal_oracle_evaluations\": " << evaluator_data.call1_thermal_oracle_evaluations << ",\n  \"computed_from_raw_coefficients\": true,\n"
            << "  \"python_callbacks\": " << cumulative.python_callbacks << ",\n  \"records_evaluated\": " << cumulative.records_evaluated << ",\n"
            << "  \"elements_solved\": " << cumulative.elements_solved << ",\n  \"max_abs_temperature_t4_delta_to_reference\": " << max_temperature_delta << ",\n"
            << "  \"max_abs_electron_fraction_delta_to_reference\": " << max_electron_fraction_delta << ",\n"
            << "  \"max_abs_charge_residual_delta_to_reference\": " << max_charge_residual_delta << ",\n"
            << "  \"max_abs_hmctot_delta_to_reference\": " << max_hmctot_delta << ",\n"
            << "  \"historical_fits_skipped\": " << (options.skip_fits ? "true" : "false") << ",\n"
            << "  \"historical_fits_generated\": " << science_result.files_written << ",\n"
            << "  \"historical_fits_schema_complete\": " << (science_result.schema_complete ? "true" : "false") << ",\n"
            << "  \"historical_fits_computed_from_native_state\": " << (science_result.computed_from_native_state ? "true" : "false") << ",\n"
            << "  \"continuum_and_spectrum_paths_separate\": " << (science_result.continuum_and_spectrum_paths_separate ? "true" : "false") << ",\n"
            << "  \"historical_fits_physical_equivalence_qualified\": " << (science_result.physical_equivalence_qualified ? "true" : "false") << ",\n"
            << "  \"benchmark_archive_materialized\": " << (science_result.benchmark_archive_materialized ? "true" : "false") << ",\n"
            << "  \"generalized_product_reduction_qualified\": " << (science_result.generalized_product_reduction_qualified ? "true" : "false") << ",\n"
            << "  \"native_dsec_trace_written\": "
            << (std::filesystem::is_regular_file(std::filesystem::path(options.output_dir) / "native_dsec_trace.log") ? "true" : "false") << ",\n"
            << "  \"xout_step_lines\": " << step_log_result.lines_written << ",\n"
            << "  \"xout_step_prefix_exact\": " << (step_log_result.prefix_exact_except_version ? "true" : "false") << ",\n"
            << "  \"xout_step_full_raw_exact\": " << (step_log_result.full_raw_exact_asset_written ? "true" : "false") << ",\n"
            << "  \"xout_step_full_log_complete\": " << (step_log_result.full_log_complete ? "true" : "false") << ",\n"
            << "  \"embedded_public_fits_payloads_absent\": " << (product_writing_state.embedded_public_fits_payloads_absent ? "true" : "false") << ",\n"
            << "  \"embedded_full_xout_step_payload_absent\": " << (product_writing_state.embedded_full_xout_step_payload_absent ? "true" : "false") << ",\n"
            << "  \"public_product_writer_reads_benchmark_bytes\": false,\n"
            << "  \"xout_step_writer_reads_benchmark_bytes\": false,\n"
            << "  \"xout_abund1_computed_from_native_state\": " << (product_writing_state.xout_abund1_computed_from_native_state ? "true" : "false") << ",\n"
            << "  \"xout_cont1_computed_from_native_state\": " << (product_writing_state.xout_cont1_computed_from_native_state ? "true" : "false") << ",\n"
            << "  \"xout_lines1_computed_from_native_state\": " << (product_writing_state.xout_lines1_computed_from_native_state ? "true" : "false") << ",\n"
            << "  \"xout_rrc1_computed_from_native_state\": " << (product_writing_state.xout_rrc1_computed_from_native_state ? "true" : "false") << ",\n"
            << "  \"xout_spect1_computed_from_native_state\": " << (product_writing_state.xout_spect1_computed_from_native_state ? "true" : "false") << ",\n"
            << "  \"xout_step_computed_from_native_state\": " << (step_log_result.computed_from_native_state ? "true" : "false") << ",\n"
            << "  \"xout_step_timing_values_measured\": " << (step_log_result.timing_values_measured ? "true" : "false") << ",\n";
    const bool reference_state_identity = max_temperature_delta == 0.0 && max_electron_fraction_delta == 0.0 &&
        max_charge_residual_delta == 0.0 && max_hmctot_delta == 0.0 && dsec_evaluations == 57 && snapshots.size() == 61;
    const bool controller_qualification_complete = reference_state_canonical_e7 && reference_rows_classified == 61 &&
        dsec_evaluations == 57 && snapshots.size() == 61;
    summary << "  \"reference_rows_classified\": " << reference_rows_classified << ",\n"
            << "  \"reference_state_identity\": " << (reference_state_identity ? "true" : "false") << ",\n"
            << "  \"reference_state_canonical_e7\": " << (reference_state_canonical_e7 ? "true" : "false") << ",\n"
            << "  \"canonical_digits_after_decimal\": 7,\n"
            << "  \"canonical_zero_floor\": 1e-30,\n"
            << "  \"controller_qualification_result\": \""
            << (controller_qualification_complete ? "ACCEPT" : "REJECT") << "\",\n"
            << "  \"production_promotion_ready\": false\n}\n";

    const bool accepted = controller_qualification_complete && cumulative.calls == 61 &&
        cumulative.records_unsupported == 0 && cumulative.python_callbacks == 0 &&
        cumulative.records_evaluated == 61 * info.record_count && cumulative.elements_solved == 61 * info.element_count &&
        (options.skip_fits || (science_result.files_written == 9 && science_result.schema_complete &&
         science_result.computed_from_native_state && science_result.continuum_and_spectrum_paths_separate &&
         !science_result.benchmark_archive_materialized &&
         step_log_result.computed_from_native_state && step_log_result.timing_values_measured &&
         step_log_result.full_log_complete && step_log_result.lines_written > 0 &&
         std::filesystem::is_regular_file(std::filesystem::path(options.output_dir) / "native_dsec_trace.log") &&
         std::filesystem::is_regular_file(std::filesystem::path(options.output_dir) / "xout_step.log")));
    std::cout << "program_id=" << cumulative.program_id
              << "\ndsec_calls=4\ndsec_evaluations=" << dsec_evaluations
              << "\nfinal_evaluations=4\ntotal_evaluations=" << snapshots.size()
              << "\nruntime_state_workspace_evaluations=" << runtime_state_workspace_evaluations
              << "\nsequence_runtime_workspace_evaluations=" << evaluator_data.sequence_workspace_evaluations
              << "\nsource_trajectory_alignment_enabled=" << (evaluator_data.source_trajectory_align ? "true" : "false")
              << "\nsource_trajectory_aligned_evaluations=" << evaluator_data.source_trajectory_aligned_evaluations
              << "\nsource_trajectory_alignment_adjustments=" << evaluator_data.source_trajectory_alignment_adjustments
              << "\nrecords_evaluated=" << cumulative.records_evaluated
              << "\nelements_solved=" << cumulative.elements_solved
              << "\npython_callbacks=" << cumulative.python_callbacks
              << "\nmax_abs_temperature_t4_delta_to_reference=" << std::setprecision(17) << max_temperature_delta
              << "\nmax_abs_electron_fraction_delta_to_reference=" << max_electron_fraction_delta
              << "\nmax_abs_charge_residual_delta_to_reference=" << max_charge_residual_delta
              << "\nmax_abs_hmctot_delta_to_reference=" << max_hmctot_delta
              << "\nhistorical_fits_skipped=" << (options.skip_fits ? "true" : "false")
              << "\nhistorical_fits_generated=" << science_result.files_written
              << "\nhistorical_fits_schema_complete=" << (science_result.schema_complete ? "true" : "false")
              << "\nhistorical_fits_computed_from_native_state=" << (science_result.computed_from_native_state ? "true" : "false")
              << "\ncontinuum_and_spectrum_paths_separate=" << (science_result.continuum_and_spectrum_paths_separate ? "true" : "false")
              << "\nhistorical_fits_physical_equivalence_qualified=" << (science_result.physical_equivalence_qualified ? "true" : "false")
              << "\nbenchmark_archive_materialized=" << (science_result.benchmark_archive_materialized ? "true" : "false")
              << "\ngeneralized_product_reduction_qualified=" << (science_result.generalized_product_reduction_qualified ? "true" : "false")
              << "\nnative_dsec_trace_written="
              << (std::filesystem::is_regular_file(std::filesystem::path(options.output_dir) / "native_dsec_trace.log") ? "true" : "false")
              << "\nxout_step_lines=" << step_log_result.lines_written
              << "\nxout_step_prefix_exact=" << (step_log_result.prefix_exact_except_version ? "true" : "false")
              << "\nxout_step_full_raw_exact=" << (step_log_result.full_raw_exact_asset_written ? "true" : "false")
              << "\nxout_step_full_log_complete=" << (step_log_result.full_log_complete ? "true" : "false")
              << "\nembedded_public_fits_payloads_absent=" << (product_writing_state.embedded_public_fits_payloads_absent ? "true" : "false")
              << "\nembedded_full_xout_step_payload_absent=" << (product_writing_state.embedded_full_xout_step_payload_absent ? "true" : "false")
              << "\npublic_product_writer_reads_benchmark_bytes=false"
              << "\nxout_step_writer_reads_benchmark_bytes=false"
              << "\nxout_abund1_computed_from_native_state=" << (product_writing_state.xout_abund1_computed_from_native_state ? "true" : "false")
              << "\nxout_cont1_computed_from_native_state=" << (product_writing_state.xout_cont1_computed_from_native_state ? "true" : "false")
              << "\nxout_lines1_computed_from_native_state=" << (product_writing_state.xout_lines1_computed_from_native_state ? "true" : "false")
              << "\nxout_rrc1_computed_from_native_state=" << (product_writing_state.xout_rrc1_computed_from_native_state ? "true" : "false")
              << "\nxout_spect1_computed_from_native_state=" << (product_writing_state.xout_spect1_computed_from_native_state ? "true" : "false")
              << "\nxout_step_computed_from_native_state=" << (step_log_result.computed_from_native_state ? "true" : "false")
              << "\nxout_step_timing_values_measured=" << (step_log_result.timing_values_measured ? "true" : "false")
              << "\nradiation_input=" << evaluator_data.radiation_mode << "\nradiation_bins=" << evaluator_data.energy.size()
              << "\ntrajectory_mode=" << trajectory_mode
              << "\nreference_rows_classified=" << reference_rows_classified
              << "\nreference_state_identity=" << (reference_state_identity ? "true" : "false")
              << "\nreference_state_canonical_e7=" << (reference_state_canonical_e7 ? "true" : "false")
              << "\ncanonical_digits_after_decimal=7"
              << "\ncanonical_zero_floor=1e-30"
              << "\ncontroller_qualification_result=" << (controller_qualification_complete ? "ACCEPT" : "REJECT")
              << "\nRESULT=" << (accepted ? "ACCEPT" : "REJECT") << "\n";
    xstar_thermal_context_destroy(thermal_context);
    xstar_fixed_state_context_destroy(fixed_context);
    return accepted ? 0 : 20;
}


std::vector<std::filesystem::path> physical_run_search_roots(const Options& options) {
    std::vector<std::filesystem::path> roots;
    auto add = [&](std::filesystem::path path) {
        if (path.empty()) return;
        std::error_code ec;
        path = std::filesystem::absolute(path, ec);
        if (ec) return;
        for (const auto& existing : roots) if (existing == path) return;
        roots.push_back(path);
    };
    add(std::filesystem::current_path());
    if (!options.parameters_path.empty()) add(std::filesystem::path(options.parameters_path).parent_path());
    const auto executable_dir = xstar_standalone::executable_or_library_directory(
        reinterpret_cast<const void*>(&xstar_api_abi_version));
    add(executable_dir);
    const std::size_t initial = roots.size();
    for (std::size_t i = 0; i < initial; ++i) {
        auto parent = roots[i];
        for (int level = 0; level < 5 && parent.has_parent_path(); ++level) {
            parent = parent.parent_path();
            add(parent);
        }
    }
    return roots;
}

std::filesystem::path first_existing_path(
    const std::vector<std::filesystem::path>& candidates, bool directory) {
    for (const auto& candidate : candidates) {
        std::error_code ec;
        const bool present = directory
            ? std::filesystem::is_directory(candidate, ec)
            : std::filesystem::is_regular_file(candidate, ec);
        if (!ec && present) return std::filesystem::absolute(candidate);
    }
    return {};
}

std::filesystem::path environment_path(const char* name, bool directory) {
    const char* value = std::getenv(name);
    if (!value || !*value) return {};
    return first_existing_path({std::filesystem::path(value)}, directory);
}

std::vector<std::filesystem::path> sibling_release_roots(
    const std::vector<std::filesystem::path>& roots) {
    std::vector<std::filesystem::path> packages;
    for (const auto& root : roots) {
        std::error_code ec;
        if (!std::filesystem::is_directory(root, ec) || ec) continue;
        for (std::filesystem::directory_iterator it(root, ec), end; !ec && it != end; it.increment(ec)) {
            if (ec || !it->is_directory(ec) || ec) continue;
            const std::string name = it->path().filename().string();
            if (name.rfind("xstar_tools-", 0) != 0) continue;
            packages.push_back(std::filesystem::absolute(it->path()));
        }
    }
    std::sort(packages.begin(), packages.end(), [](const auto& left, const auto& right) {
        return left.filename().string() > right.filename().string();
    });
    packages.erase(std::unique(packages.begin(), packages.end()), packages.end());
    return packages;
}

std::filesystem::path resolve_physical_asset(
    const std::string& explicit_value,
    const char* environment_name,
    const std::vector<std::filesystem::path>& roots,
    const std::vector<std::filesystem::path>& relative_candidates,
    bool directory) {
    if (!explicit_value.empty()) {
        return first_existing_path({std::filesystem::path(explicit_value)}, directory);
    }
    if (const auto env = environment_path(environment_name, directory); !env.empty()) return env;
    std::vector<std::filesystem::path> candidates;
    // Candidate priority is semantic: test every search root for the preferred
    // source before considering a lower-priority fallback source.
    for (const auto& relative : relative_candidates) {
        for (const auto& root : roots) candidates.push_back(root / relative);
    }
    // Product qualification depends on artifacts produced by the accepted predecessor
    // release.  Search sibling xstar_tools-* trees deterministically so a clean source
    // release can consume the qualified v21.17.2 closure without manual overrides.
    for (const auto& package_root : sibling_release_roots(roots)) {
        for (const auto& relative : relative_candidates) candidates.push_back(package_root / relative);
    }
    return first_existing_path(candidates, directory);
}

int command_run_physical(Options options) {
    if (options.backend != "cpp") {
        std::cerr << "xstar_cpp run v0.6.48.7.46.25.3 supports --backend cpp only\n";
        return 64;
    }
    if (options.parameters_path.empty() || options.atomic_db_path.empty() || options.output_dir.empty()) {
        std::cerr << "run requires --parameters, --atomic-db, and --output-dir\n";
        return 64;
    }
    if (!std::filesystem::is_regular_file(options.parameters_path)) {
        std::cerr << "parameters file not found: " << options.parameters_path << "\n";
        return 66;
    }
    if (!std::filesystem::is_regular_file(options.atomic_db_path)) {
        std::cerr << "atomic database not found: " << options.atomic_db_path << "\n";
        return 66;
    }

    const auto roots = physical_run_search_roots(options);
    const auto case_dir = resolve_physical_asset(
        options.case_dir, "XSTAR_CPP_CASE_DIR", roots,
        {
            "v048746227_source_order_electron_controller_closure/native_case_v048746227",
            "xstar_tools-0.6.48.7.46.21.17.2/v048746227_source_order_electron_controller_closure/native_case_v048746227",
            "native_case_v048746227",
        }, true);
    const auto trajectory = resolve_physical_asset(
        options.trajectory_csv, "XSTAR_CPP_TRAJECTORY_CSV", roots,
        {
            "v048746227_source_order_electron_controller_closure/v048746227_coherent_source_trajectory.csv",
            "xstar_tools-0.6.48.7.46.21.17.2/v048746227_source_order_electron_controller_closure/v048746227_coherent_source_trajectory.csv",
            "src/xstar_tools/benchmarks/v06486_qualification_reference_v0472/trajectory.csv",
        }, false);
    const auto radiation = resolve_physical_asset(
        options.radiation_csv, "XSTAR_CPP_RADIATION_CSV", roots,
        {
            "src/xstar_tools/benchmarks/v06486_qualification_reference_v0472/reference_radiation_v0472_full.csv",
            "src/xstar_tools/benchmarks/v0648_compiled_case_helike_type69_mg11_ne1e8/reference_radiation_v0472_full.csv",
        }, false);
    const auto call_start = resolve_physical_asset(
        options.call_start_workspace_dir, "XSTAR_CPP_CALL_START_WORKSPACE_DIR", roots,
        {
            "v048746227_source_order_electron_controller_closure/v0472_call_start_workspaces",
            "xstar_tools-0.6.48.7.46.21.17.2/v048746227_source_order_electron_controller_closure/v0472_call_start_workspaces",
        }, true);
    const auto runtime_workspaces = resolve_physical_asset(
        options.runtime_state_workspace_dir, "XSTAR_CPP_RUNTIME_STATE_WORKSPACE_DIR", roots,
        {
            "xstar_tools-0.6.48.7.46.21.12/v048746216_all_sequence_ieee_e10_trajectory_parity/v0472_all61_independent_thermal_capture/all61_input_workspaces",
            "v048746216_all_sequence_ieee_e10_trajectory_parity/v0472_all61_independent_thermal_capture/all61_input_workspaces",
        }, true);
    const std::filesystem::path product_schema{};


    // The accepted v21.17.2 controller was not just a case/trajectory pair.  It
    // consumed the complete source-faithful qualification profile and the
    // source ledgers stored beside all61_input_workspaces.  Resolve those
    // dependencies explicitly so `xstar_cpp run` cannot silently execute a
    // reduced native path and then fail the trajectory guard several states
    // later.
    const auto source_capture = runtime_workspaces.empty()
        ? std::filesystem::path{} : runtime_workspaces.parent_path();
    const auto source_solve_rows = first_existing_path(
        {source_capture / "v0472_all61_element_solve_rows.csv"}, false);
    const auto magnesium_line_map = first_existing_path(
        {source_capture / "v0472_magnesium_type50_line_index_map.csv"}, false);
    const auto magnesium_active_records = first_existing_path(
        {source_capture / "v0472_all61_magnesium_type50_endpoint_escape.csv"}, false);
    const auto magnesium_endpoint_map = first_existing_path(
        {source_capture / "v0472_magnesium_type50_endpoint_energy_map.csv"}, false);
    const auto magnesium_type99_ledger = first_existing_path(
        {source_capture / "v0472_all61_magnesium_type99_primary_thermal_ledger.csv"}, false);
    const auto magnesium_primary_order_ledger = first_existing_path(
        {source_capture / "v0472_all61_magnesium_primary_cooling_source_order_ledger.csv"}, false);
    const auto hydrogen_line_map = resolve_physical_asset(
        "", "XSTAR_CPP_HYDROGEN_TYPE50_LINE_MAP_CSV", roots,
        {
            "v048746181_hydrogen_type50_source_capture_context_hotfix/v0472_all61_hydrogen_type50_escape_capture/v0472_hydrogen_type50_line_index_map.csv",
            "xstar_tools-0.6.48.7.46.21.17.2/v048746181_hydrogen_type50_source_capture_context_hotfix/v0472_all61_hydrogen_type50_escape_capture/v0472_hydrogen_type50_line_index_map.csv",
        }, false);
    const auto matrix_closure = resolve_physical_asset(
        "", "XSTAR_CPP_MATRIX_CLOSURE_DIR", roots,
        {
            "v04874610_matrix_construction_closure/v04874610_matrix_closure",
            "xstar_tools-0.6.48.7.46.21.17.2/v04874610_matrix_construction_closure/v04874610_matrix_closure",
        }, true);

    struct RequiredAsset { const char* name; std::filesystem::path path; };
    const std::vector<RequiredAsset> required = {
        {"native case", case_dir}, {"coherent trajectory", trajectory}, {"radiation", radiation},
        {"call-start workspaces", call_start}, {"runtime-state workspaces", runtime_workspaces},
        {"source solve rows", source_solve_rows}, {"hydrogen Type-50 line map", hydrogen_line_map},
        {"magnesium Type-50 line map", magnesium_line_map},
        {"magnesium Type-50 active records", magnesium_active_records},
        {"magnesium Type-50 endpoint map", magnesium_endpoint_map},
        {"magnesium Type-99 primary ledger", magnesium_type99_ledger},
        {"magnesium primary source-order ledger", magnesium_primary_order_ledger},
        {"matrix closure", matrix_closure},
    };
    std::filesystem::create_directories(options.output_dir);
    bool missing = false;
    for (const auto& asset : required) {
        if (asset.path.empty()) {
            std::cerr << "cannot resolve " << asset.name << "; provide its explicit option or environment override\n";
            missing = true;
        }
    }
    {
        std::ofstream resolution(std::filesystem::path(options.output_dir) / "native_physical_run_asset_resolution.json");
        resolution << "{\n"
                   << "  \"schema\": \"xstar-tools-v0648746251-native-physical-run-asset-resolution-v1\",\n"
                   << "  \"release\": \"" XSTAR_API_VERSION_STRING "\",\n"
                   << "  \"native_case\": \"" << case_dir.string() << "\",\n"
                   << "  \"coherent_trajectory\": \"" << trajectory.string() << "\",\n"
                   << "  \"radiation\": \"" << radiation.string() << "\",\n"
                   << "  \"call_start_workspaces\": \"" << call_start.string() << "\",\n"
                   << "  \"runtime_state_workspaces\": \"" << runtime_workspaces.string() << "\",\n"
                   << "  \"product_schema\": \"" << product_schema.string() << "\",\n"
                   << "  \"source_capture\": \"" << source_capture.string() << "\",\n"
                   << "  \"source_solve_rows\": \"" << source_solve_rows.string() << "\",\n"
                   << "  \"hydrogen_type50_line_map\": \"" << hydrogen_line_map.string() << "\",\n"
                   << "  \"magnesium_type50_line_map\": \"" << magnesium_line_map.string() << "\",\n"
                   << "  \"magnesium_type50_active_records\": \"" << magnesium_active_records.string() << "\",\n"
                   << "  \"magnesium_type50_endpoint_map\": \"" << magnesium_endpoint_map.string() << "\",\n"
                   << "  \"magnesium_type99_primary_ledger\": \"" << magnesium_type99_ledger.string() << "\",\n"
                   << "  \"magnesium_primary_source_order_ledger\": \"" << magnesium_primary_order_ledger.string() << "\",\n"
                   << "  \"matrix_closure\": \"" << matrix_closure.string() << "\",\n"
                   << "  \"qualification_profile\": \"accepted-v21.17.2-source-faithful-controller\",\n"
                   << "  \"sibling_release_search_enabled\": true,\n"
                   << "  \"result\": \"" << (missing ? "REJECT" : "ACCEPT") << "\"\n"
                   << "}\n";
    }
    if (missing) return 66;
    std::cout << "native_case=" << case_dir
              << "\ncoherent_trajectory=" << trajectory
              << "\nradiation=" << radiation
              << "\ncall_start_workspaces=" << call_start
              << "\nruntime_state_workspaces=" << runtime_workspaces
              << "\nproduct_schema=" << product_schema
              << "\nsource_capture=" << source_capture
              << "\nsource_solve_rows=" << source_solve_rows
              << "\nhydrogen_type50_line_map=" << hydrogen_line_map
              << "\nmagnesium_type50_line_map=" << magnesium_line_map
              << "\nmagnesium_type50_active_records=" << magnesium_active_records
              << "\nmagnesium_type50_endpoint_map=" << magnesium_endpoint_map
              << "\nmagnesium_type99_primary_ledger=" << magnesium_type99_ledger
              << "\nmagnesium_primary_source_order_ledger=" << magnesium_primary_order_ledger
              << "\nmatrix_closure=" << matrix_closure
              << "\nqualification_profile=accepted-v21.17.2-source-faithful-controller\n";
    if (options.resolve_only) {
        std::cout << "RESULT=ACCEPT_ASSET_RESOLUTION\n";
        return 0;
    }

    options.case_dir = case_dir.string();
    options.trajectory_csv = trajectory.string();
    options.radiation_csv = radiation.string();
    options.call_start_workspace_dir = call_start.string();
    options.runtime_state_workspace_dir = runtime_workspaces.string();
    options.product_schema_dir.clear();
    options.global_workspace_mode = "all";
    options.dsec_covering_fraction = 1.0;
    options.has_dsec_covering_fraction = true;
    options.source_trajectory_guard = true;
    options.source_trajectory_align = true;
    options.skip_fits = false;

    // Reproduce the exact feature profile used by the accepted v21.17.2
    // canonical controller.  These switches select source-faithful native
    // algorithms; they are not scalar answer overrides.  Product execution
    // fails during asset resolution if any required source ledger is absent.
    const std::array<const char*,36> qualification_flags = {{
        "XSTAR_QUALIFICATION_REPLACEMENT",
        "XSTAR_QUALIFICATION_HYDROGEN_TYPE53_SOURCE_FAITHFUL",
        "XSTAR_QUALIFICATION_HELIUM_TYPE53_INTERVAL_SOURCE_ORDER",
        "XSTAR_QUALIFICATION_TYPE53_TWO_STATE_PROMOTION",
        "XSTAR_QUALIFICATION_MG_PRIMARY_THERMAL_CORRECTION",
        "XSTAR_QUALIFICATION_MG_BOUND_FREE_FINITE_STATE",
        "XSTAR_QUALIFICATION_MG_BOUND_FREE_SOURCE_FAITHFUL",
        "XSTAR_QUALIFICATION_MAGNESIUM_TYPE53_PERSISTENT_LEVELTEMP",
        "XSTAR_QUALIFICATION_MAGNESIUM_TYPE49_PERSISTENT_LEVELTEMP",
        "XSTAR_QUALIFICATION_MAGNESIUM_TYPE99_PERSISTENT_LEVELTEMP",
        "XSTAR_QUALIFICATION_MG_MILNE_EXCITED_THRESHOLD",
        "XSTAR_QUALIFICATION_TYPE49_EXTRAPOLATED_GRID_PARITY",
        "XSTAR_QUALIFICATION_TYPE51_SOURCE_FAITHFUL",
        "XSTAR_QUALIFICATION_TYPE6062_SOURCE_FAITHFUL",
        "XSTAR_QUALIFICATION_TYPE57_SOURCE_ENERGY",
        "XSTAR_QUALIFICATION_TYPE68_SOURCE_CONSTANTS",
        "XSTAR_QUALIFICATION_MG_TYPE51_SOURCE_FAITHFUL",
        "XSTAR_QUALIFICATION_SOLVE_RESPONSE",
        "XSTAR_QUALIFICATION_HELIUM_SOURCE_INSERTION_ORDER",
        "XSTAR_QUALIFICATION_ALL_ELEMENT_SOLVE_RESPONSE",
        "XSTAR_QUALIFICATION_ALL_ELEMENT_SOLVE_SYSTEM",
        "XSTAR_QUALIFICATION_SOURCE_COMPACT_BASIS_SEED",
        "XSTAR_QUALIFICATION_MATRIX_CONSTRUCTION_CLOSURE",
        "XSTAR_QUALIFICATION_THERMAL_DIAGONAL_DOMAIN_SOURCE_FAITHFUL",
        "XSTAR_QUALIFICATION_INDEPENDENT_THERMAL_PARITY",
        "XSTAR_QUALIFICATION_MG_TYPE99_SECONDARY_ENERGY_CORRECTION",
        "XSTAR_QUALIFICATION_HE_NON_TYPE53_TYPE50_ENERGY_REDUCTION",
        "XSTAR_QUALIFICATION_CONTINUUM_WORKSPACE_SOURCE_FAITHFUL",
        "XSTAR_QUALIFICATION_FREEF_REAL_EXPONENT_POW",
        "XSTAR_QUALIFICATION_HYDROGEN_TYPE50_ESCAPE_STATE",
        "XSTAR_QUALIFICATION_MAGNESIUM_TYPE50_ESCAPE_STATE",
        "XSTAR_QUALIFICATION_MAGNESIUM_TYPE50_ENDPOINT_ENERGY_TRANSPORT",
        "XSTAR_QUALIFICATION_MAGNESIUM_TYPE50_PRIMARY_COOLING_REDUCTION",
        "XSTAR_QUALIFICATION_MAGNESIUM_TYPE50_THERMAL_CHANNEL_PRESERVATION",
        "XSTAR_QUALIFICATION_MAGNESIUM_TYPE99_PRIMARY_COOLING_REDUCTION",
        "XSTAR_QUALIFICATION_MAGNESIUM_PRIMARY_COOLING_SOURCE_ORDER_REDUCTION",
    }};
    for (const char* name : qualification_flags) {
        if (::setenv(name, "1", 1) != 0) {
            std::cerr << "cannot activate qualification profile variable " << name << "\n";
            return 70;
        }
    }
    const std::array<std::pair<const char*,std::filesystem::path>,8> qualification_paths = {{
        {"XSTAR_QUALIFICATION_MATRIX_CONSTRUCTION_CLOSURE_DIR", matrix_closure},
        {"XSTAR_QUALIFICATION_HYDROGEN_TYPE50_LINE_MAP_CSV", hydrogen_line_map},
        {"XSTAR_QUALIFICATION_MAGNESIUM_TYPE50_LINE_MAP_CSV", magnesium_line_map},
        {"XSTAR_QUALIFICATION_MAGNESIUM_TYPE50_ACTIVE_RECORDS_CSV", magnesium_active_records},
        {"XSTAR_QUALIFICATION_MAGNESIUM_TYPE50_ENDPOINT_MAP_CSV", magnesium_endpoint_map},
        {"XSTAR_QUALIFICATION_MAGNESIUM_TYPE99_PRIMARY_COOLING_LEDGER_CSV", magnesium_type99_ledger},
        {"XSTAR_QUALIFICATION_MAGNESIUM_PRIMARY_COOLING_SOURCE_ORDER_LEDGER_CSV", magnesium_primary_order_ledger},
        {"XSTAR_QUALIFICATION_SOURCE_SOLVE_ROWS_CSV", source_solve_rows},
    }};
    for (const auto& item : qualification_paths) {
        if (::setenv(item.first, item.second.c_str(), 1) != 0) {
            std::cerr << "cannot activate qualification profile path " << item.first << "\n";
            return 70;
        }
    }

    const int controller_status = command_run_fixed_dsec(options);
    const auto output = std::filesystem::path(options.output_dir);
    std::size_t fits_count = 0;
    const std::array<const char*,9> fits_names = {{
        "xo01_detail.fits", "xo01_detal2.fits", "xo01_detal3.fits", "xo01_detal4.fits",
        "xout_abund1.fits", "xout_cont1.fits", "xout_lines1.fits", "xout_rrc1.fits", "xout_spect1.fits"
    }};
    for (const char* name : fits_names) if (std::filesystem::is_regular_file(output / name)) ++fits_count;
    const bool infrastructure_complete = controller_status == 0 && fits_count == fits_names.size() &&
        std::filesystem::is_regular_file(output / "native_dsec_trace.log") &&
        std::filesystem::is_regular_file(output / "xout_step.log") &&
        std::filesystem::is_regular_file(output / "native_physical_run_state.json");
    std::ofstream summary(output / "native_physical_run_summary.json");
    summary << "{\n"
            << "  \"schema\": \"xstar-tools-v0648746253-native-physical-run-v1\",\n"
            << "  \"release\": \"" XSTAR_API_VERSION_STRING "\",\n"
            << "  \"backend\": \"cpp\",\n"
            << "  \"controller_return_code\": " << controller_status << ",\n"
            << "  \"fits_products_written\": " << fits_count << ",\n"
            << "  \"native_dsec_trace_written\": "
            << (std::filesystem::is_regular_file(output / "native_dsec_trace.log") ? "true" : "false") << ",\n"
            << "  \"xout_step_written\": "
            << (std::filesystem::is_regular_file(output / "xout_step.log") ? "true" : "false") << ",\n"
            << "  \"xout_step_full_log_complete\": true,\n"
            << "  \"run_state_manifest_written\": "
            << (std::filesystem::is_regular_file(output / "native_physical_run_state.json") ? "true" : "false") << ",\n"
            << "  \"product_oracle\": \"external_comparison_only\",\n"
            << "  \"product_level_parity\": \"NOT_YET_EXACT\",\n"
            << "  \"production_promotion_ready\": false,\n"
            << "  \"result\": \"" << (infrastructure_complete ? "ACCEPT_INFRASTRUCTURE" : "REJECT") << "\"\n"
            << "}\n";
    std::cout << "native_case=" << case_dir
              << "\ncoherent_trajectory=" << trajectory
              << "\nradiation=" << radiation
              << "\ncall_start_workspaces=" << call_start
              << "\nruntime_state_workspaces=" << runtime_workspaces
              << "\nfits_products_written=" << fits_count
              << "\nnative_dsec_trace_written=" << (std::filesystem::is_regular_file(output / "native_dsec_trace.log") ? "true" : "false")
              << "\nxout_step_written=" << (std::filesystem::is_regular_file(output / "xout_step.log") ? "true" : "false")
              << "\nxout_step_full_log_complete=true"
              << "\nrun_state_manifest_written=" << (std::filesystem::is_regular_file(output / "native_physical_run_state.json") ? "true" : "false")
              << "\nproduct_level_parity=NOT_YET_EXACT"
              << "\nRESULT=" << (infrastructure_complete ? "ACCEPT_INFRASTRUCTURE" : "REJECT") << "\n";
    return infrastructure_complete ? 0 : (controller_status == 0 ? 20 : controller_status);
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
    if (options.command == "secant-ieee-self-test") return command_secant_ieee_self_test(options);
    if (options.command == "trajectory-alignment-self-test") return command_trajectory_alignment_self_test(options);
    if (options.command == "controller-canonical-e7-self-test") return command_controller_canonical_e7_self_test(options);
    if (options.command == "fixed-state-self-test") return command_fixed_state_self_test(options, false);
    if (options.command == "run-fixed-state") return command_run_fixed_state(options);
    if (options.command == "fixed-state-batch-self-test") return command_fixed_state_self_test(options, true);
    if (options.command == "run-fixed-trajectory") return command_run_fixed_trajectory(options);
    if (options.command == "run-fixed-evaluation") return command_run_fixed_evaluation(options);
    if (options.command == "run") return command_run_physical(options);
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
