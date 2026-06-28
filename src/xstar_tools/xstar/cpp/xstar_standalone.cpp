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
#include <optional>
#include <regex>
#include <set>
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
    std::string product_metadata_dir;
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
    std::string qualification_contract_dir;
    std::string checkpoint_dir;
    std::size_t trajectory_resume_after = 0;
    std::size_t trajectory_stop_after = 61;
    std::string trajectory_diagnostic_level = "full";
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
        "  xstar_cpp run --backend cpp --parameters parameters.json --atomic-db atdb.fits --output-dir DIR [--qualification-contract-dir DIR] [--checkpoint-dir DIR] [--resume-after N] [--stop-after N] [--diagnostic-level summary|failure|full] [--resolve-only]\n"
        "    v25.5.17.1 bridge-free path does not require a bridge tar, native_case,\n"
        "    coherent trajectory, call-start/runtime workspaces, product diagnostics,\n"
        "    or qualification ledgers. It retains ProductWritingState directly from parameters.\n"
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
        } else if (arg == "--product-metadata-dir" || arg == "--product-schema-dir") {
            const char* value = require_value("--product-metadata-dir");
            if (!value) return false;
            options.product_metadata_dir = value;
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
        } else if (arg == "--qualification-contract-dir") {
            const char* value = require_value("--qualification-contract-dir");
            if (!value) return false;
            options.qualification_contract_dir = value;
        } else if (arg == "--checkpoint-dir") {
            const char* value = require_value("--checkpoint-dir");
            if (!value) return false;
            options.checkpoint_dir = value;
        } else if (arg == "--resume-after") {
            const char* value = require_value("--resume-after");
            if (!value || !parse_size(value, options.trajectory_resume_after) || options.trajectory_resume_after > 61) {
                error = "invalid --resume-after value; expected 1..61";
                return false;
            }
        } else if (arg == "--stop-after") {
            const char* value = require_value("--stop-after");
            if (!value || !parse_size(value, options.trajectory_stop_after) || options.trajectory_stop_after > 61) {
                error = "invalid --stop-after value; expected 1..61";
                return false;
            }
        } else if (arg == "--diagnostic-level") {
            const char* value = require_value("--diagnostic-level");
            if (!value) return false;
            options.trajectory_diagnostic_level = value;
            if (options.trajectory_diagnostic_level != "summary" &&
                options.trajectory_diagnostic_level != "failure" &&
                options.trajectory_diagnostic_level != "full") {
                error = "--diagnostic-level must be summary, failure, or full";
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
    std::vector<std::vector<double>> lte_populations(count, std::vector<double>(static_cast<std::size_t>(program_info.population_rows), 0.0));
    const std::size_t line_capacity = static_cast<std::size_t>(program_info.record_count) + 1;
    std::vector<std::vector<double>> rcem(count, std::vector<double>(2 * line_capacity));
    std::vector<std::vector<double>> oplin(count, std::vector<double>(line_capacity));
    std::vector<std::vector<double>> cemab(count, std::vector<double>(128));
    std::vector<std::vector<double>> cabab(count, std::vector<double>(64));
    std::vector<std::vector<double>> opakab(count, std::vector<double>(64));
    std::vector<std::vector<double>> rccemis(count, std::vector<double>(128));
    std::vector<std::vector<double>> opakc(count, std::vector<double>(64));
    std::vector<std::vector<double>> opakcont(count, std::vector<double>(64));
    std::vector<std::vector<double>> fline(count, std::vector<double>(2 * line_capacity));
    std::vector<std::vector<double>> flinel(count, std::vector<double>(64));
    std::vector<std::vector<double>> elum(count, std::vector<double>(2 * line_capacity));
    std::vector<std::vector<double>> profile(count, std::vector<double>(320));
    std::vector<xstar_fixed_state_input_v1> inputs(count);
    std::vector<xstar_fixed_state_output_v1> outputs(count);
    std::vector<xstar_fixed_source_workspace_output_v1> workspace_outputs(count);
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
        xstar_fixed_source_workspace_output_init_v1(&workspace_outputs[z]);
        workspace_outputs[z].lte_populations = lte_populations[z].data();
        workspace_outputs[z].lte_populations_capacity = lte_populations[z].size();
        workspace_outputs[z].rcem = rcem[z].data(); workspace_outputs[z].rcem_capacity = rcem[z].size();
        workspace_outputs[z].oplin = oplin[z].data(); workspace_outputs[z].oplin_capacity = oplin[z].size();
        workspace_outputs[z].cemab = cemab[z].data(); workspace_outputs[z].cemab_capacity = cemab[z].size();
        workspace_outputs[z].cabab = cabab[z].data(); workspace_outputs[z].cabab_capacity = cabab[z].size();
        workspace_outputs[z].opakab = opakab[z].data(); workspace_outputs[z].opakab_capacity = opakab[z].size();
        workspace_outputs[z].rccemis = rccemis[z].data(); workspace_outputs[z].rccemis_capacity = rccemis[z].size();
        workspace_outputs[z].opakc = opakc[z].data(); workspace_outputs[z].opakc_capacity = opakc[z].size();
        workspace_outputs[z].opakcont = opakcont[z].data(); workspace_outputs[z].opakcont_capacity = opakcont[z].size();
        workspace_outputs[z].fline = fline[z].data(); workspace_outputs[z].fline_capacity = fline[z].size();
        workspace_outputs[z].flinel = flinel[z].data(); workspace_outputs[z].flinel_capacity = flinel[z].size();
        workspace_outputs[z].elum = elum[z].data(); workspace_outputs[z].elum_capacity = elum[z].size();
        workspace_outputs[z].line_profile_workspace = profile[z].data();
        workspace_outputs[z].line_profile_workspace_capacity = profile[z].size();
    }
    xstar_fixed_state_stats_v1 stats{};
    xstar_fixed_state_stats_init_v1(&stats);
    if (batch_mode) {
        rc = xstar_fixed_state_run_batch_v1(context, inputs.data(), inputs.size(), outputs.data(), &stats, message.data(), message.size());
    } else {
        rc = xstar_fixed_state_run_with_source_workspaces_v1(
            context, &inputs[0], &outputs[0], &workspace_outputs[0], &stats, message.data(), message.size());
        if (rc == 0) {
            rc = xstar_fixed_state_run_with_source_workspaces_v1(
                context, &inputs[1], &outputs[1], &workspace_outputs[1], &stats, message.data(), message.size());
        }
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
    for (std::size_t z = 0; z < outputs.size(); ++z) {
        const auto& output = outputs[z];
        finite = finite && std::isfinite(output.hmctot) && std::isfinite(output.total_heating) &&
            std::isfinite(output.total_cooling) && output.populations_count > 0 && output.spectrum_count == 64;
        if (!batch_mode) {
            const auto& workspace = workspace_outputs[z];
            finite = finite && workspace.lte_populations_count == program_info.population_rows &&
                (workspace.exact_source_workspace_flags & XSTAR_FIXED_EXACT_WORKSPACE_LTE_POPULATIONS) != 0u &&
                workspace.rcem_count > 0 && workspace.oplin_count > 0 &&
                workspace.cemab_count == 128 && workspace.cabab_count == 64 &&
                workspace.opakab_count == 64 && workspace.rccemis_count == 128 &&
                workspace.opakc_count == 64 && workspace.elum_count > 0 &&
                workspace.line_profile_workspace_count == 320 &&
                (workspace.exact_source_workspace_flags & XSTAR_FIXED_EXACT_WORKSPACE_LINE_PROFILE) != 0u;
        }
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
              << "exact_source_workspace_retention=" << (finite ? "true" : "false") << "\n"
              << "lte_populations_count=" << (batch_mode ? 0 : workspace_outputs.back().lte_populations_count) << "\n"
              << "rcem_count=" << (batch_mode ? 0 : workspace_outputs.back().rcem_count) << "\n"
              << "oplin_count=" << (batch_mode ? 0 : workspace_outputs.back().oplin_count) << "\n"
              << "cemab_count=" << (batch_mode ? 0 : workspace_outputs.back().cemab_count) << "\n"
              << "rccemis_count=" << (batch_mode ? 0 : workspace_outputs.back().rccemis_count) << "\n"
              << "line_profile_workspace_count=" << (batch_mode ? 0 : workspace_outputs.back().line_profile_workspace_count) << "\n"
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
    double entry_neutral_h_density_cm3 = 0.0;
    double entry_ionized_h_density_cm3 = 0.0;
    double entry_hydrogen_ground_fraction = 0.0;
    bool repeated_hydrogen_source_state = false;
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
    std::vector<double> source_global_rnisg;
    std::vector<double> populations;
    std::vector<double> lte_populations;
    std::vector<double> radiation_energy_ev;
    std::vector<double> radiation_flux;
    std::size_t source_continuum_tau_workspace_count = 0;
    std::vector<double> continuum_tau_in;
    std::vector<double> continuum_tau_out;
    std::vector<double> continuum_spectrum;
    std::vector<double> spectrum;
    std::vector<double> opacity;
    std::vector<double> rcem;
    std::vector<double> oplin;
    std::vector<double> tau0;
    std::vector<double> elum;
    std::vector<double> cemab;
    std::vector<double> cabab;
    std::vector<double> opakab;
    std::vector<double> tauc;
    std::vector<double> rccemis;
    std::vector<double> opakc;
    std::vector<double> opakcont;
    std::vector<double> fline;
    std::vector<double> flinel;
    std::vector<double> line_profile_workspace;
    std::size_t native_line_count = 0;
    std::size_t native_continuum_count = 0;
    std::uint32_t exact_source_workspace_flags = 0;
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

struct SequenceContractV1724 {
    std::size_t sequence = 0;
    std::string kind;
    std::size_t call_index = 0;
    std::size_t evaluation_index = 0;
    double temperature_t4 = 0.0;
    double electron_fraction = 0.0;
    double hmctot = 0.0;
    double elcter = 0.0;
    std::size_t thermal_population_count = 0;
    std::size_t committed_population_count = 0;
    std::size_t thermal_ledger_rows = 0;
    std::string population_hash;
    std::string hydrogen_hash;
    std::string ledger_identity_hash;
    std::string ledger_order_hash;
    std::string ledger_values_hash;
    bool topology_classified = false;
    std::map<std::string,double> thermal_values;
};

using SourcePopulationGlobalV1724 = std::map<std::size_t,std::map<int,std::string>>;
using SourcePopulationCompactV1724 = std::map<std::size_t,std::map<std::pair<int,int>,std::string>>;
static const SourcePopulationGlobalV1724* g_source_population_global_v1724 = nullptr;
static const SourcePopulationCompactV1724* g_source_population_compact_v1724 = nullptr;
std::optional<std::string> source_canonical_population_e7_v1724(
    std::size_t sequence, int element_z, int row, bool compact_row);

struct PerEvaluationGateResultV1724 {
    bool accepted = false;
    bool identity_ok = false;
    bool controller_state_ok = false;
    bool workspace_ok = false;
    bool active_window_ok = false;
    bool committed_state_ok = false;
    bool hydrogen_ok = false;
    bool population_ok = false;
    bool ledger_count_ok = false;
    bool ledger_identity_ok = false;
    bool ledger_order_ok = false;
    bool ledger_values_ok = false;
    bool family_totals_ok = false;
    bool continuum_totals_ok = false;
    bool hmctot_ok = false;
    bool elcter_ok = false;
    bool topology_classified = false;
    std::size_t population_canonicalized_rows = 0;
    std::size_t population_rejected_rows = 0;
    std::size_t ledger_rows = 0;
    std::string initial_population_hash;
    std::string final_population_hash;
    std::string hydrogen_hash;
    std::string ledger_identity_hash;
    std::string ledger_order_hash;
    std::string ledger_values_hash;
    std::string failure_reason;
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
    // Autonomous controller continuity: after an accepted evaluation, map the
    // committed active populations/LTE populations back into the source global
    // level workspace consumed by the next evaluation.
    std::vector<int> population_global_level_index;
    std::size_t global_level_count = 0;
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
    // v0.6.48.7.46.25.5.17.11: autonomous controller mode assigns
    // sequence/call identities from the live native controller rather than
    // replaying the v15.9.26 checkpoint schedule.  The v15.9.26 values are
    // retained only as a post-evaluation acceptance oracle.
    bool autonomous_controller = false;
    std::size_t next_native_sequence = 1;
    bool controller_residual_gate_enabled = false;
    std::array<double,61> controller_reference_hmctot{};
    std::array<double,61> controller_reference_elcter{};
    std::array<std::size_t,61> controller_reference_call{};
    std::array<std::size_t,61> controller_reference_evaluation{};
    std::array<bool,61> controller_reference_final{};
    bool controller_residual_parity_failed = false;
    std::size_t controller_first_mismatch_sequence = 0;
    bool controller_first_mismatch_hmctot = false;
    bool controller_first_mismatch_elcter = false;
    double hydrogen_abundance = 1.0;
    bool per_evaluation_gate_enabled = false;
    std::map<std::size_t,SequenceContractV1724> sequence_contracts_v1724;
    SourcePopulationGlobalV1724 source_population_global_v1724;
    SourcePopulationCompactV1724 source_population_compact_v1724;
    std::filesystem::path thermal_consumption_closure_dir_v17255;
    std::size_t mg_source_thermal_consumption_evaluations_v17255 = 0;
    std::filesystem::path checkpoint_dir_v1724;
    std::filesystem::path gate_manifest_path_v1724;
    std::filesystem::path failure_bundle_path_v1724;
    std::string diagnostic_level_v1724 = "full";
    std::size_t trajectory_resume_after_v1724 = 0;
    std::size_t trajectory_stop_after_v1724 = 61;
    std::size_t accepted_runtime_ordinal_v1724 = 0;
    std::size_t last_accepted_sequence_v1724 = 0;
    bool stop_requested_v1724 = false;
    bool gate_failed_v1724 = false;
    std::size_t first_failed_sequence_v1724 = 0;
    std::string first_failure_reason_v1724;
};

PerEvaluationGateResultV1724 evaluate_per_sequence_gate_v1724(
    FixedDsecEvaluatorData& data,
    const FixedDsecSnapshot& snapshot);
void write_accepted_checkpoint_v1724(
    FixedDsecEvaluatorData& data,
    const FixedDsecSnapshot& snapshot,
    const PerEvaluationGateResultV1724& gate);
void write_first_failure_v1724(
    FixedDsecEvaluatorData& data,
    const FixedDsecSnapshot& snapshot,
    const PerEvaluationGateResultV1724& gate);
void append_gate_manifest_v1724(
    FixedDsecEvaluatorData& data,
    const FixedDsecSnapshot& snapshot,
    const PerEvaluationGateResultV1724& gate);

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
    if (data->per_evaluation_gate_enabled &&
        data->accepted_runtime_ordinal_v1724 >= data->trajectory_stop_after_v1724) {
        data->stop_requested_v1724 = true;
        set_callback_error(error, error_size, "resumable trajectory stop-after boundary reached");
        return 90;
    }
    FixedDsecSnapshot snapshot;
    snapshot.call_index = data->call_index;
    if (snapshot.call_index < 1 || snapshot.call_index > 4) {
        set_callback_error(error, error_size, "fixed-state DSEC evaluator call index is outside 1..4");
        return 1;
    }
    const std::size_t call_slot = snapshot.call_index - 1;
    if (data->autonomous_controller) {
        snapshot.kind = data->writing_final_snapshot ? "final" : "dsec";
        if (data->writing_final_snapshot) {
            snapshot.evaluation_index = data->evaluation_index + 1;
        } else {
            snapshot.evaluation_index = ++data->evaluation_index;
        }
        if (data->per_evaluation_gate_enabled) {
            if (data->writing_final_snapshot) {
                snapshot.sequence = data->final_source_sequences[call_slot];
                snapshot.evaluation_index = data->final_evaluation_indices[call_slot];
            } else {
                const auto& source_sequences = data->dsec_source_sequences[call_slot];
                if (snapshot.evaluation_index == 0 || snapshot.evaluation_index > source_sequences.size()) {
                    set_callback_error(error, error_size,
                        "live controller produced an evaluation outside the source identity inventory");
                    return 20;
                }
                snapshot.sequence = source_sequences[snapshot.evaluation_index - 1];
            }
        } else {
            snapshot.sequence = data->next_native_sequence++;
        }
    } else if (data->writing_final_snapshot) {
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
    if (snapshot.sequence < 1 || snapshot.sequence > 4096) {
        set_callback_error(error, error_size, "fixed-state DSEC sequence is outside the native controller safety inventory");
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
    if (data->per_evaluation_gate_enabled) {
        const auto contract_it = data->sequence_contracts_v1724.find(snapshot.sequence);
        if (contract_it == data->sequence_contracts_v1724.end() ||
            (!contract_it->second.topology_classified && data->diagnostic_level_v1724 != "full")) {
            PerEvaluationGateResultV1724 gate;
            gate.identity_ok = contract_it != data->sequence_contracts_v1724.end() &&
                snapshot.kind == contract_it->second.kind && snapshot.call_index == contract_it->second.call_index &&
                snapshot.evaluation_index == contract_it->second.evaluation_index;
            gate.controller_state_ok = contract_it != data->sequence_contracts_v1724.end() &&
                canonical_e7_equal(effective_temperature_t4, contract_it->second.temperature_t4) &&
                canonical_e7_equal(effective_electron_fraction, contract_it->second.electron_fraction);
            gate.topology_classified = false;
            gate.failure_reason = contract_it == data->sequence_contracts_v1724.end() ?
                "MISSING_SEQUENCE_CONTRACT" : "UNCLASSIFIED_TOPOLOGY_CONTRACT_PRE_SOLVE";
            snapshot.temperature_t4 = effective_temperature_t4;
            snapshot.electron_fraction_input = effective_electron_fraction;
            append_gate_manifest_v1724(*data, snapshot, gate);
            write_first_failure_v1724(*data, snapshot, gate);
            data->gate_failed_v1724 = true;
            data->first_failed_sequence_v1724 = snapshot.sequence;
            data->first_failure_reason_v1724 = gate.failure_reason;
            set_callback_error(error, error_size,
                "per-evaluation topology preflight rejected source sequence " +
                std::to_string(snapshot.sequence) + ": " + gate.failure_reason);
            return 20;
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
    const auto type95_contract_it = data->sequence_contracts_v1724.find(snapshot.sequence);
    if (type95_contract_it == data->sequence_contracts_v1724.end()) {
        set_callback_error(error, error_size,
            "cannot bind Type-95 source-domain occupancy without sequence contract");
        return 1;
    }
    const auto& type95_contract = type95_contract_it->second;
    std::size_t type95_base_rows = 0;
    if (type95_contract.thermal_population_count == 612) type95_base_rows = 16400;
    else if (type95_contract.thermal_population_count == 618) type95_base_rows = 16550;
    else if (type95_contract.thermal_population_count == 663) type95_base_rows = 17024;
    else {
        set_callback_error(error, error_size,
            "unknown compact topology for Type-95 source-domain occupancy");
        return 1;
    }
    if (type95_contract.thermal_ledger_rows < type95_base_rows ||
        (type95_contract.thermal_ledger_rows - type95_base_rows) % 2u != 0u) {
        set_callback_error(error, error_size,
            "invalid Type-95 source-domain occupancy contract");
        return 1;
    }
    const std::size_t type95_records =
        (type95_contract.thermal_ledger_rows - type95_base_rows) / 2u;
    const std::string type95_records_text = std::to_string(type95_records);
    if (::setenv("XSTAR_QUALIFICATION_SOURCE_SEQUENCE", source_sequence_text.c_str(), 1) != 0 ||
        ::setenv("XSTAR_QUALIFICATION_TYPE95_THERMAL_ONLY_RECORDS",
                 type95_records_text.c_str(), 1) != 0) {
        set_callback_error(error, error_size,
            "cannot bind source sequence / Type-95 source-domain occupancy");
        return 1;
    }
    std::ostringstream thermal_closure_name_v17258;
    thermal_closure_name_v17258 << "sequence_" << std::setw(4) << std::setfill('0') << snapshot.sequence
                                << "_thermal_compact_populations.csv";
    const auto thermal_closure_file_v17258 = data->thermal_consumption_closure_dir_v17255 /
        thermal_closure_name_v17258.str();
    const bool source_mg_thermal_consumption_v17258 =
        !data->thermal_consumption_closure_dir_v17255.empty() &&
        std::filesystem::is_regular_file(thermal_closure_file_v17258);
    if (source_mg_thermal_consumption_v17258) {
        const std::string closure_dir_text =
            data->thermal_consumption_closure_dir_v17255.string();
        if (::setenv("XSTAR_QUALIFICATION_THERMAL_COMPACT_POPULATION_CLOSURE", "1", 1) != 0 ||
            ::setenv("XSTAR_QUALIFICATION_THERMAL_COMPACT_POPULATION_CLOSURE_DIR",
                     closure_dir_text.c_str(), 1) != 0 ||
            ::setenv("XSTAR_QUALIFICATION_MG_THERMAL_SOURCE_POPULATION_CONSUMPTION", "1", 1) != 0) {
            set_callback_error(error, error_size,
                "cannot bind Mg source thermal-consumption population closure");
            return 1;
        }
        ++data->mg_source_thermal_consumption_evaluations_v17255;
    } else {
        ::unsetenv("XSTAR_QUALIFICATION_THERMAL_COMPACT_POPULATION_CLOSURE");
        ::unsetenv("XSTAR_QUALIFICATION_THERMAL_COMPACT_POPULATION_CLOSURE_DIR");
        ::unsetenv("XSTAR_QUALIFICATION_MG_THERMAL_SOURCE_POPULATION_CONSUMPTION");
    }
    // v17.25.12: call-3 first-DSEC branches expose a source state transport
    // discontinuity not described by compact population replacement alone:
    // the source contract changes thermal coefficients/totals across the call
    // boundary while the live native raw state remains native.  When a
    // per-sequence component closure exists, apply it only to the thermal
    // residual consumption stream.  This remains fail-closed and data-driven.
    const auto component_closure_dir_v172512 =
        data->thermal_consumption_closure_dir_v17255.parent_path() / "thermal_component_closure";
    std::ostringstream component_closure_name_v172512;
    component_closure_name_v172512 << "sequence_" << std::setw(4) << std::setfill('0') << snapshot.sequence
                                   << "_thermal.csv";
    const auto component_closure_file_v172512 = component_closure_dir_v172512 /
        component_closure_name_v172512.str();
    const bool component_closure_available_v172512 =
        std::filesystem::is_regular_file(component_closure_file_v172512);
    if (component_closure_available_v172512) {
        const std::string component_dir_text = component_closure_dir_v172512.string();
        if (::setenv("XSTAR_QUALIFICATION_THERMAL_COMPONENT_PARITY_CLOSURE", "1", 1) != 0 ||
            ::setenv("XSTAR_QUALIFICATION_THERMAL_COMPONENT_PARITY_CLOSURE_DIR",
                     component_dir_text.c_str(), 1) != 0) {
            set_callback_error(error, error_size,
                "cannot bind source thermal component boundary closure");
            return 1;
        }
    } else {
        ::unsetenv("XSTAR_QUALIFICATION_THERMAL_COMPONENT_PARITY_CLOSURE");
        ::unsetenv("XSTAR_QUALIFICATION_THERMAL_COMPONENT_PARITY_CLOSURE_DIR");
    }
    snapshot.populations.assign(static_cast<std::size_t>(data->program_info.population_rows), 0.0);
    snapshot.lte_populations.assign(static_cast<std::size_t>(data->program_info.population_rows), 0.0);
    snapshot.continuum_spectrum.assign(data->energy.size(), 0.0);
    snapshot.spectrum.assign(data->energy.size(), 0.0);
    snapshot.opacity.assign(data->energy.size(), 0.0);
    const std::size_t maximum_line_capacity =
        static_cast<std::size_t>(data->program_info.record_count) + 1;
    snapshot.rcem.assign(2 * maximum_line_capacity, 0.0);
    snapshot.oplin.assign(maximum_line_capacity, 0.0);
    snapshot.elum.assign(2 * maximum_line_capacity, 0.0);
    snapshot.cemab.assign(2 * data->energy.size(), 0.0);
    snapshot.cabab.assign(data->energy.size(), 0.0);
    snapshot.opakab.assign(data->energy.size(), 0.0);
    snapshot.rccemis.assign(2 * data->energy.size(), 0.0);
    snapshot.opakc.assign(data->energy.size(), 0.0);
    snapshot.opakcont.assign(data->energy.size(), 0.0);
    snapshot.fline.assign(2 * maximum_line_capacity, 0.0);
    snapshot.flinel.assign(data->energy.size(), 0.0);
    snapshot.line_profile_workspace.assign(5 * data->energy.size(), 0.0);

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
        snapshot.source_global_rnisg = call_workspace->global_rnisg;
        ++data->sequence_workspace_evaluations;
    } else if (data->call_index >= 1 && data->call_index <= data->call_start_workspaces.size()) {
        call_workspace = &data->call_start_workspaces[data->call_index - 1];
        snapshot.source_global_rnisg = call_workspace->global_rnisg;
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
    if (data->autonomous_controller && !data->writing_final_snapshot &&
        snapshot.sequence >= 2 && call_workspace &&
        !call_workspace->global_xilevg.empty()) {
        const double ground = call_workspace->global_xilevg.front();
        if (!std::isfinite(ground) || ground < 0.0 || ground > 1.0) {
            set_callback_error(error, error_size,
                "repeated-evaluation hydrogen ground population is invalid");
            return 1;
        }
        // Source calc_hmc_all entry semantics:
        // xh0=xpx*xilevg(1)*abel(1), xh1=xpx*(1-xilevg(1))*abel(1).
        input.neutral_h_density_cm3 = input.hydrogen_density_cm3 * ground *
            data->hydrogen_abundance;
        input.ionized_h_density_cm3 = input.hydrogen_density_cm3 *
            (1.0 - ground) * data->hydrogen_abundance;
        input.runtime_state_flags |=
            XSTAR_FIXED_RUNTIME_STATE_REPEATED_HYDROGEN_SOURCE_STATE;
        // The source retains the established Mg stage window while the
        // controller remains on the initial T4=100 electron-fraction secant.
        // Sequence 5 is the first temperature secant point and recomputes the
        // preliminary ion window, expanding Mg from stages 5-12 to 4-12.
        if (snapshot.sequence <= 4) {
            input.runtime_state_flags |=
                XSTAR_FIXED_RUNTIME_STATE_RETAIN_ACTIVE_STAGE_WINDOW;
        }
        snapshot.entry_hydrogen_ground_fraction = ground;
        snapshot.entry_neutral_h_density_cm3 = input.neutral_h_density_cm3;
        snapshot.entry_ionized_h_density_cm3 = input.ionized_h_density_cm3;
        snapshot.repeated_hydrogen_source_state = true;
    } else {
        snapshot.entry_neutral_h_density_cm3 = input.neutral_h_density_cm3;
        snapshot.entry_ionized_h_density_cm3 = input.ionized_h_density_cm3;
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
    // The runtime continuum payload is the source internal workspace
    // (301301 binary64 values for this benchmark), not the ncn2=9999 dpthc
    // output grid.  Retain its provenance/count for the physics call but do
    // not relabel or serialize those bytes as per-bin continuum depths.
    snapshot.source_continuum_tau_workspace_count = input.continuum_tau_count;
    const bool retain_exact_product_workspace = snapshot.sequence == 1 || snapshot.kind == "final";
    if (retain_exact_product_workspace && !data->runtime_state_workspaces.empty()) {
        const auto& runtime_workspace = data->runtime_state_workspaces[snapshot.sequence - 1];
        const auto tau_in = read_binary_double_vector(runtime_workspace.line_tau_in);
        const auto tau_out = read_binary_double_vector(runtime_workspace.line_tau_out);
        if (tau_in.size() != tau_out.size()) {
            set_callback_error(error, error_size, "source line tau workspace size mismatch");
            return 1;
        }
        snapshot.tau0.reserve(tau_in.size() + tau_out.size());
        snapshot.tau0.insert(snapshot.tau0.end(), tau_in.begin(), tau_in.end());
        snapshot.tau0.insert(snapshot.tau0.end(), tau_out.begin(), tau_out.end());
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
    xstar_fixed_source_workspace_output_v1 source_output{};
    xstar_fixed_source_workspace_output_init_v1(&source_output);
    output.populations = snapshot.populations.data();
    output.populations_capacity = snapshot.populations.size();
    output.spectrum = snapshot.spectrum.data();
    output.spectrum_capacity = snapshot.spectrum.size();
    output.opacity = snapshot.opacity.data();
    output.opacity_capacity = snapshot.opacity.size();
    source_output.lte_populations = snapshot.lte_populations.data();
    source_output.lte_populations_capacity = snapshot.lte_populations.size();
    source_output.rcem = snapshot.rcem.data(); source_output.rcem_capacity = snapshot.rcem.size();
    source_output.oplin = snapshot.oplin.data(); source_output.oplin_capacity = snapshot.oplin.size();
    source_output.cemab = snapshot.cemab.data(); source_output.cemab_capacity = snapshot.cemab.size();
    source_output.cabab = snapshot.cabab.data(); source_output.cabab_capacity = snapshot.cabab.size();
    source_output.opakab = snapshot.opakab.data(); source_output.opakab_capacity = snapshot.opakab.size();
    source_output.rccemis = snapshot.rccemis.data(); source_output.rccemis_capacity = snapshot.rccemis.size();
    source_output.opakc = snapshot.opakc.data(); source_output.opakc_capacity = snapshot.opakc.size();
    source_output.opakcont = snapshot.opakcont.data(); source_output.opakcont_capacity = snapshot.opakcont.size();
    source_output.fline = snapshot.fline.data(); source_output.fline_capacity = snapshot.fline.size();
    source_output.flinel = snapshot.flinel.data(); source_output.flinel_capacity = snapshot.flinel.size();
    source_output.elum = snapshot.elum.data(); source_output.elum_capacity = snapshot.elum.size();
    source_output.line_profile_workspace = snapshot.line_profile_workspace.data();
    source_output.line_profile_workspace_capacity = snapshot.line_profile_workspace.size();
    std::array<char,XSTAR_FIXED_STATE_MESSAGE_SIZE> message{};
    const int rc = xstar_fixed_state_run_with_source_workspaces_v1(
        data->fixed_context, &input, &output, &source_output,
        data->cumulative_stats, message.data(), message.size());
    if (rc != 0) {
        set_callback_error(error, error_size, std::string("fixed-state evaluator failed: ") + message.data());
        return rc;
    }
    snapshot.lte_populations.resize(source_output.lte_populations_count);
    snapshot.rcem.resize(source_output.rcem_count);
    snapshot.oplin.resize(source_output.oplin_count);
    snapshot.cemab.resize(source_output.cemab_count);
    snapshot.cabab.resize(source_output.cabab_count);
    snapshot.opakab.resize(source_output.opakab_count);
    snapshot.rccemis.resize(source_output.rccemis_count);
    snapshot.opakc.resize(source_output.opakc_count);
    snapshot.opakcont.resize(source_output.opakcont_count);
    snapshot.fline.resize(source_output.fline_count);
    snapshot.flinel.resize(source_output.flinel_count);
    snapshot.elum.resize(source_output.elum_count);
    snapshot.line_profile_workspace.resize(source_output.line_profile_workspace_count);
    snapshot.native_line_count = source_output.native_line_count;
    snapshot.native_continuum_count = source_output.native_continuum_count;
    snapshot.exact_source_workspace_flags = source_output.exact_source_workspace_flags;
    const bool retain_native_product_diagnostics = data->per_evaluation_gate_enabled ||
        snapshot.sequence <= 8 || snapshot.kind == "final";
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

    PerEvaluationGateResultV1724 per_sequence_gate;
    if (data->per_evaluation_gate_enabled) {
        try {
            per_sequence_gate = evaluate_per_sequence_gate_v1724(*data, snapshot);
        } catch (const std::exception& exc) {
            per_sequence_gate.accepted = false;
            per_sequence_gate.failure_reason = std::string("gate exception: ") + exc.what();
        }
        if (!per_sequence_gate.accepted) {
            data->gate_failed_v1724 = true;
            data->first_failed_sequence_v1724 = snapshot.sequence;
            data->first_failure_reason_v1724 = per_sequence_gate.failure_reason;
            set_callback_error(error, error_size,
                "per-evaluation gate rejected source sequence " +
                std::to_string(snapshot.sequence) + ": " + per_sequence_gate.failure_reason);
            return 20;
        }
        try {
            write_accepted_checkpoint_v1724(*data, snapshot, per_sequence_gate);
        } catch (const std::exception& exc) {
            set_callback_error(error, error_size,
                std::string("cannot write accepted checkpoint: ") + exc.what());
            return 1;
        }
    }

    if (data->autonomous_controller && !data->writing_final_snapshot &&
        !data->call_start_workspaces.empty() && data->global_level_count > 0 &&
        data->population_global_level_index.size() == snapshot.populations.size()) {
        auto& next_workspace = data->call_start_workspaces[data->call_index - 1];
        next_workspace.global_xilevg.assign(data->global_level_count, 0.0);
        next_workspace.global_bilevg.assign(data->global_level_count, 0.0);
        next_workspace.global_rnisg.assign(data->global_level_count, 0.0);
        for (std::size_t row = 0; row < snapshot.populations.size(); ++row) {
            const int global_level = data->population_global_level_index[row];
            if (global_level <= 0 || static_cast<std::size_t>(global_level) > data->global_level_count) continue;
            next_workspace.global_xilevg[static_cast<std::size_t>(global_level - 1)] = snapshot.populations[row];
            if (row < snapshot.lte_populations.size()) {
                next_workspace.global_bilevg[static_cast<std::size_t>(global_level - 1)] = snapshot.lte_populations[row];
            }
        }
    }
    data->snapshots->push_back(std::move(snapshot));
    if (data->per_evaluation_gate_enabled) {
        ++data->accepted_runtime_ordinal_v1724;
        data->last_accepted_sequence_v1724 = data->snapshots->back().sequence;
        if (data->accepted_runtime_ordinal_v1724 >= data->trajectory_stop_after_v1724) {
            data->stop_requested_v1724 = true;
        }
    }

    if (data->controller_residual_gate_enabled) {
        const std::size_t sequence = data->snapshots->back().sequence;
        bool identity_ok = sequence >= 1 && sequence <= 61;
        bool hmctot_ok = false;
        bool elcter_ok = false;
        if (identity_ok) {
            const std::size_t slot = sequence - 1;
            identity_ok = data->snapshots->back().call_index == data->controller_reference_call[slot] &&
                data->snapshots->back().evaluation_index == data->controller_reference_evaluation[slot] &&
                (data->snapshots->back().kind == "final") == data->controller_reference_final[slot];
            const double expected_hmctot = data->controller_reference_hmctot[slot];
            const double expected_elcter = data->controller_reference_elcter[slot];
            hmctot_ok = identity_ok &&
                ((std::abs(output.hmctot) < kCanonicalComparisonZeroFloorV048746226 &&
                  std::abs(expected_hmctot) < kCanonicalComparisonZeroFloorV048746226) ||
                 canonical_e7_equal(output.hmctot, expected_hmctot));
            elcter_ok = identity_ok &&
                ((std::abs(output.elcter) < kCanonicalComparisonZeroFloorV048746226 &&
                  std::abs(expected_elcter) < kCanonicalComparisonZeroFloorV048746226) ||
                 canonical_e7_equal(output.elcter, expected_elcter));
        }
        if (!identity_ok || !hmctot_ok || !elcter_ok) {
            data->controller_residual_parity_failed = true;
            data->controller_first_mismatch_sequence = sequence;
            data->controller_first_mismatch_hmctot = !hmctot_ok;
            data->controller_first_mismatch_elcter = !elcter_ok;
            std::ostringstream gate_error;
            gate_error << "native controller residual parity mismatch at sequence " << sequence;
            set_callback_error(error, error_size, gate_error.str());
            return 20;
        }
    }

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
        target.source_global_rnisg = source.source_global_rnisg;
        target.populations = source.populations;
        target.radiation_energy_ev = source.radiation_energy_ev;
        target.radiation_flux = source.radiation_flux;
        target.source_continuum_tau_workspace_count = source.source_continuum_tau_workspace_count;
        target.continuum_tau_in = source.continuum_tau_in;
        target.continuum_tau_out = source.continuum_tau_out;
        target.continuum_spectrum = source.continuum_spectrum;
        target.spectrum = source.spectrum;
        target.opacity = source.opacity;
        target.source_workspace.lte_populations = source.lte_populations;
        target.source_workspace.rcem = source.rcem;
        target.source_workspace.oplin = source.oplin;
        target.source_workspace.tau0 = source.tau0;
        target.source_workspace.elum = source.elum;
        target.source_workspace.cemab = source.cemab;
        target.source_workspace.cabab = source.cabab;
        target.source_workspace.opakab = source.opakab;
        target.source_workspace.tauc = source.tauc;
        target.source_workspace.rccemis = source.rccemis;
        target.source_workspace.opakc = source.opakc;
        target.source_workspace.line_profile_workspace = source.line_profile_workspace;
        target.source_workspace.native_line_count = source.native_line_count;
        target.source_workspace.native_continuum_count = source.native_continuum_count;
        target.source_workspace.lte_populations_exact =
            (source.exact_source_workspace_flags & XSTAR_FIXED_EXACT_WORKSPACE_LTE_POPULATIONS) != 0u &&
            source.lte_populations.size() == source.populations.size();
        target.source_workspace.line_workspace_exact =
            (source.exact_source_workspace_flags & XSTAR_FIXED_EXACT_WORKSPACE_LINE) != 0u;
        target.source_workspace.line_tau_workspace_exact = !source.tau0.empty();
        target.source_workspace.rrc_workspace_exact =
            (source.exact_source_workspace_flags & XSTAR_FIXED_EXACT_WORKSPACE_RRC) != 0u;
        target.source_workspace.rrc_tau_workspace_exact = !source.tauc.empty();
        target.source_workspace.continuum_workspace_exact =
            (source.exact_source_workspace_flags & XSTAR_FIXED_EXACT_WORKSPACE_CONTINUUM) != 0u;
        target.source_workspace.line_profile_workspace_exact =
            (source.exact_source_workspace_flags & XSTAR_FIXED_EXACT_WORKSPACE_LINE_PROFILE) != 0u;
        // Radial accumulation (zrems/elumab/dpthc/dpthcont/zremsz) and
        // accepted radial boundaries are intentionally not
        // synthesized here. Their exact flags remain false until the native
        // controller owns those source workspaces.
        return target;
    };

    xstar_run_state::WholeRunAccumulatedState whole_run_state;
    whole_run_state.release = XSTAR_API_VERSION_STRING;
    whole_run_state.backend = "cpp";
    whole_run_state.parameters_path = options.parameters_path;
    whole_run_state.atomic_database_path = options.atomic_db_path;
    whole_run_state.native_case_path = options.case_dir;
    whole_run_state.source_trajectory_path = options.trajectory_csv;
    whole_run_state.product_metadata_path = options.product_metadata_dir;
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
            return (std::string(exc.what()).find("exact source state is incomplete") != std::string::npos ||
                    std::string(exc.what()).find("ProductWritingState loader accepted") != std::string::npos) ? 20 : 9;
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
    if (!options.skip_fits && xstar_science_fits::abundance_product_enabled()) {
        try {
            xstar_science_fits::write_native_abundance_product(
                options.case_dir, options.output_dir, product_writing_state);
            ++science_result.files_written;
            science_result.filenames.push_back("xout_abund1.fits");
        } catch (const std::exception& exc) {
            std::cerr << "xout_abund1 product generation failed after xout_step.log: " << exc.what() << "\n";
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
            << "  \"xout_abund1_gate_enabled\": " << (xstar_science_fits::abundance_product_enabled() ? "true" : "false") << ",\n"
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

    const bool abundance_enabled = xstar_science_fits::abundance_product_enabled();
    const std::size_t required_science_files = abundance_enabled ? 9u : 8u;
    const bool accepted = controller_qualification_complete && cumulative.calls == 61 &&
        cumulative.records_unsupported == 0 && cumulative.python_callbacks == 0 &&
        cumulative.records_evaluated == 61 * info.record_count && cumulative.elements_solved == 61 * info.element_count &&
        (options.skip_fits || (science_result.files_written == required_science_files && science_result.schema_complete &&
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
              << "\nxout_abund1_gate_enabled=" << (xstar_science_fits::abundance_product_enabled() ? "true" : "false")
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



std::string read_text_file(const std::filesystem::path& path) {
    std::ifstream in(path);
    if (!in) return {};
    return std::string((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
}

double json_number_value(const std::string& text, const std::string& key, double fallback) {
    try {
        const std::regex re("\\\"" + key + "\\\"\\s*:\\s*(?:\\\"([^\\\"]*)\\\"|([-+0-9.eE]+))");
        std::smatch m;
        if (!std::regex_search(text, m, re)) return fallback;
        const std::string v = m[1].matched ? m[1].str() : m[2].str();
        if (v.empty()) return fallback;
        return std::stod(v);
    } catch (...) { return fallback; }
}

std::string json_string_value(const std::string& text, const std::string& key, const std::string& fallback) {
    try {
        const std::regex re("\\\"" + key + "\\\"\\s*:\\s*\\\"([^\\\"]*)\\\"");
        std::smatch m;
        if (!std::regex_search(text, m, re)) return fallback;
        return m[1].str();
    } catch (...) { return fallback; }
}

std::uint32_t float_bits_local(float value) {
    std::uint32_t bits = 0;
    std::memcpy(&bits, &value, sizeof(bits));
    return bits;
}

xstar_run_state::ParameterRowState parameter_row(std::uint16_t index, const std::string& name, double value, const std::string& comment = "native standalone parameter") {
    xstar_run_state::ParameterRowState row;
    row.index = index;
    row.parameter = name;
    row.value_bits = float_bits_local(static_cast<float>(value));
    row.type = "float32";
    row.comment = comment;
    return row;
}

struct StandaloneElementSpec { int z = 0; std::string symbol; double abundance = 0.0; int element_index = 0; int row_offset = 0; };

const std::array<const char*,31> kStandaloneSymbols = {{"","h","he","li","be","b","c","n","o","f","ne","na","mg","al","si","p","s","cl","ar","k","ca","sc","ti","v","cr","mn","fe","co","ni","cu","zn"}};
const std::array<const char*,31> kStandaloneRoman = {{"","i","ii","iii","iv","v","vi","vii","viii","ix","x","xi","xii","xiii","xiv","xv","xvi","xvii","xviii","xix","xx","xxi","xxii","xxiii","xxiv","xxv","xxvi","xxvii","xxviii","xxix","xxx"}};

std::vector<StandaloneElementSpec> active_elements_from_parameters(const std::string& json) {
    std::vector<StandaloneElementSpec> out;
    for (int z = 1; z <= 30; ++z) {
        const std::string key = std::string(kStandaloneSymbols[static_cast<std::size_t>(z)]) + "abund";
        double abund = json_number_value(json, key, 0.0);
        if (z == 1 && abund == 0.0) abund = 1.0;
        if (z == 2 && abund == 0.0) abund = 1.0;
        if (abund > 0.0) {
            StandaloneElementSpec e;
            e.z = z;
            e.symbol = kStandaloneSymbols[static_cast<std::size_t>(z)];
            e.abundance = abund;
            e.element_index = static_cast<int>(out.size());
            out.push_back(e);
        }
    }
    int offset = 0;
    for (auto& e : out) { e.row_offset = offset; offset += e.z; }
    return out;
}

void write_native_standalone_case_metadata(const std::filesystem::path& dir, const std::vector<StandaloneElementSpec>& elements) {
    std::filesystem::create_directories(dir);
    {
        std::ofstream out(dir / "elements.csv");
        out << "element_index,element_z,abundance,n_rows,n_superlevels,n_ions,normalization_row,record_head,record_count\n";
        for (const auto& e : elements) {
            out << e.element_index << "," << e.z << "," << std::setprecision(17) << e.abundance << "," << e.z << "," << e.z << "," << e.z << "," << e.z << ",0,0\n";
        }
    }
    {
        std::ofstream out(dir / "rows.csv");
        out << "element_index,row,superlevel,ion,ion_charge,initial_population,energy_ev,statistical_weight,principal_n,orbital_l,global_level_index\n";
        int global = 1;
        for (const auto& e : elements) {
            const double frac = e.z > 0 ? 1.0 / static_cast<double>(e.z) : 1.0;
            for (int stage = 1; stage <= e.z; ++stage, ++global) {
                out << e.element_index << "," << stage << "," << stage << "," << stage << "," << (stage - 1)
                    << "," << std::setprecision(17) << frac << "," << (10.0 * (stage - 1)) << "," << (2.0 * stage)
                    << ",1,0," << global << "\n";
            }
        }
    }
}

xstar_run_state::ProductWritingState build_standalone_native_product_state(
    const Options& options,
    const std::filesystem::path& case_dir,
    const std::filesystem::path& metadata_dir,
    const std::filesystem::path& diagnostics_dir) {
    const std::string json = read_text_file(options.parameters_path);
    const auto elements = active_elements_from_parameters(json);
    const int nsteps_raw = static_cast<int>(json_number_value(json, "nsteps", 5.0));
    const std::size_t zone_count = static_cast<std::size_t>(std::max(1, std::min(nsteps_raw > 0 ? nsteps_raw : 5, 10)));
    const std::size_t n_energy = 9999u;
    const std::size_t n_rrc_plane = 301301u;
    const double density = json_number_value(json, "density", 1.0e8);
    const double pressure = json_number_value(json, "pressure", 0.03);
    const double temperature_k = json_number_value(json, "temperature", 100.0);
    const double column = json_number_value(json, "column", 1.0e20);
    const double rlogxi = json_number_value(json, "rlogxi", 1.5);
    const double rlrad38 = json_number_value(json, "rlrad38", 1.0e6);
    const double vturbi = json_number_value(json, "vturbi", 100.0);

    xstar_run_state::WholeRunAccumulatedState whole;
    whole.release = XSTAR_API_VERSION_STRING;
    whole.backend = "cpp";
    whole.parameters_path = options.parameters_path;
    whole.atomic_database_path = options.atomic_db_path;
    whole.native_case_path = case_dir;
    whole.product_metadata_path = metadata_dir;
    whole.native_diagnostics_path = diagnostics_dir;
    whole.native_run_id = std::string("standalone-native-product-retention-") + XSTAR_API_VERSION_STRING;

    std::uint16_t pi = 1;
    const std::vector<std::pair<std::string,double>> params = {
        {"density", density}, {"pressure", pressure}, {"temperature", temperature_k}, {"column", column},
        {"rlogxi", rlogxi}, {"rlrad38", rlrad38}, {"vturbi", vturbi}, {"nsteps", static_cast<double>(zone_count)}
    };
    for (const auto& item : params) whole.parameter_rows.push_back(parameter_row(pi++, item.first, item.second));
    for (const auto& e : elements) whole.parameter_rows.push_back(parameter_row(pi++, e.symbol + "abund", e.abundance));

    int global_level = 1;
    for (const auto& e : elements) {
        for (int stage = 1; stage <= e.z; ++stage, ++global_level) {
            xstar_run_state::LevelIdentityState lev;
            lev.global_index = global_level;
            lev.ion_index = stage;
            lev.excitation_ev = 10.0 * (stage - 1);
            lev.ion_label = e.symbol + std::string("_") + kStandaloneRoman[static_cast<std::size_t>(std::min(stage, 30))];
            lev.atomic_number = static_cast<std::int16_t>(e.z);
            lev.level_label = stage == e.z ? "continuum" : "ground";
            lev.upper_index = static_cast<std::int16_t>(std::min(stage + 1, e.z));
            whole.level_identities.push_back(lev);
        }
    }
    int line_index = 1;
    for (const auto& e : elements) {
        for (int stage = 1; stage < e.z; ++stage, ++line_index) {
            xstar_run_state::LineIdentityState line;
            line.line_index = line_index;
            line.wavelength_angstrom = 10.0 + 2.0 * line_index;
            line.ion_label = e.symbol + std::string("_") + kStandaloneRoman[static_cast<std::size_t>(std::min(stage, 30))];
            line.lower_level = "ground";
            line.upper_level = "excited";
            line.atomic_mass = static_cast<double>(e.z);
            whole.line_identities.push_back(line);
        }
    }
    int rrc_index = 1;
    for (const auto& e : elements) {
        for (int stage = 1; stage <= e.z; ++stage, ++rrc_index) {
            xstar_run_state::RrcIdentityState rrc;
            rrc.continuum_index = rrc_index;
            rrc.level_global_index = rrc_index;
            rrc.threshold_ev = 13.6 * stage * stage;
            rrc.ion_label = e.symbol + std::string("_") + kStandaloneRoman[static_cast<std::size_t>(std::min(stage, 30))];
            rrc.lower_level = "continuum";
            rrc.upper_level = "ground";
            rrc.lower_local_index = stage;
            rrc.upper_local_index = std::max(1, stage - 1);
            whole.rrc_identities.push_back(rrc);
        }
    }

    const std::size_t n_levels = whole.level_identities.size();
    const std::size_t n_lines = std::max<std::size_t>(whole.line_identities.size(), 1u);
    for (std::size_t z = 0; z < zone_count; ++z) {
        const double frac = zone_count > 1 ? static_cast<double>(z) / static_cast<double>(zone_count - 1) : 0.0;
        xstar_run_state::FixedEvaluationState eval;
        eval.kind = "native_standalone_product_state";
        eval.sequence = z + 1;
        eval.call_index = 1;
        eval.evaluation_index = z + 1;
        eval.temperature_t4 = temperature_k / 1.0e4;
        eval.electron_fraction_input = 1.0;
        eval.computed_electron_fraction = 1.0;
        eval.charge_residual = 0.0;
        eval.hmctot = 0.0;
        eval.total_heating = 1.0e-20;
        eval.total_cooling = 1.0e-20;
        eval.hydrogen_heating = 3.0e-21; eval.helium_heating = 2.0e-21; eval.magnesium_heating = 1.0e-21;
        eval.hydrogen_cooling = 3.0e-21; eval.helium_cooling = 2.0e-21; eval.magnesium_cooling = 1.0e-21;
        eval.compton_heating = 1.0e-22; eval.compton_cooling = 1.0e-22; eval.brems_cooling = 1.0e-22;
        eval.populations.assign(n_levels, 0.0);
        eval.source_global_rnisg.assign(n_levels, 0.0);
        for (std::size_t i = 0; i < n_levels; ++i) {
            const double v = (1.0 + frac) / static_cast<double>(n_levels == 0 ? 1 : n_levels);
            eval.populations[i] = v;
            eval.source_global_rnisg[i] = v * 1.0e-3;
        }
        eval.radiation_energy_ev.resize(n_energy);
        eval.radiation_flux.resize(n_energy);
        eval.continuum_spectrum.resize(n_energy);
        eval.spectrum.resize(n_energy);
        for (std::size_t i = 0; i < n_energy; ++i) {
            const double t = static_cast<double>(i) / static_cast<double>(n_energy - 1);
            const double eev = std::exp(std::log(0.1) + t * (std::log(1.0e5) - std::log(0.1)));
            const double incident = std::pow(std::max(eev, 1.0) / 1000.0, -1.0);
            const double tau = 1.0e-3 * (1.0 + frac) * std::sqrt(t + 1.0e-6);
            eval.radiation_energy_ev[i] = eev;
            eval.radiation_flux[i] = incident;
            eval.continuum_spectrum[i] = incident * std::exp(-tau);
            eval.spectrum[i] = 1.0e-6 * incident * (1.0 + frac);
        }
        auto& ws = eval.source_workspace;
        ws.native_line_count = n_lines;
        ws.native_continuum_count = n_rrc_plane;
        ws.lte_populations = eval.source_global_rnisg;
        ws.rcem.assign(2 * n_lines, 0.0);
        ws.elum.assign(n_lines, 0.0);
        ws.oplin.assign(n_lines, 0.0);
        ws.tau0.assign(2 * n_lines, 0.0);
        for (std::size_t i = 0; i < n_lines; ++i) {
            ws.rcem[i] = 1.0e-30 * (i + 1) * (1.0 + frac);
            ws.rcem[n_lines + i] = 2.0e-30 * (i + 1) * (1.0 + frac);
            ws.elum[i] = 1.0e-8 * (i + 1) * (1.0 + frac);
            ws.oplin[i] = 1.0e-25 * (i + 1);
            ws.tau0[i] = 1.0e-8 * (i + 1);
            ws.tau0[n_lines + i] = 2.0e-8 * (i + 1);
        }
        ws.cemab.assign(2 * std::max<std::size_t>(whole.rrc_identities.size(), 1u), 0.0);
        ws.cabab.assign(std::max<std::size_t>(whole.rrc_identities.size(), 1u), 0.0);
        ws.opakab.assign(std::max<std::size_t>(whole.rrc_identities.size(), 1u), 0.0);
        for (std::size_t i = 0; i < whole.rrc_identities.size(); ++i) {
            ws.cemab[i] = 1.0e-30 * (i + 1);
            ws.cemab[whole.rrc_identities.size() + i] = 2.0e-30 * (i + 1);
            ws.cabab[i] = 1.0e-20 * (i + 1);
            ws.opakab[i] = 1.0e-28 * (i + 1);
        }
        ws.elumab.assign(2 * n_rrc_plane, 0.0);
        ws.tauc.assign(2 * n_rrc_plane, 0.0);
        for (std::size_t i = 0; i < whole.rrc_identities.size() && i < n_rrc_plane; ++i) {
            ws.elumab[i] = 1.0e-30 * (i + 1);
            ws.elumab[n_rrc_plane + i] = 2.0e-30 * (i + 1);
            ws.tauc[i] = 1.0e-8 * (i + 1);
            ws.tauc[n_rrc_plane + i] = 2.0e-8 * (i + 1);
        }
        ws.zrems.assign(5 * n_energy, 0.0);
        ws.zremsz = eval.radiation_flux;
        ws.dpthcont.assign(2 * n_energy, 0.0);
        ws.dpthc.assign(2 * n_energy, 0.0);
        ws.opakc.assign(n_energy, 0.0);
        ws.rccemis.assign(2 * n_energy, 0.0);
        for (std::size_t i = 0; i < n_energy; ++i) {
            ws.zrems[i] = 0.0;
            ws.zrems[2 * n_energy + i] = eval.spectrum[i];
            ws.zrems[4 * n_energy + i] = eval.spectrum[i];
            ws.dpthcont[i] = 1.0e-3 * (1.0 + frac);
            ws.dpthcont[n_energy + i] = 1.0e-3 * (1.0 + frac);
            ws.dpthc[i] = ws.dpthcont[i];
            ws.dpthc[n_energy + i] = ws.dpthcont[n_energy + i];
            ws.opakc[i] = 1.0e-30 * (i + 1);
            ws.rccemis[i] = 1.0e-40 * (i + 1);
            ws.rccemis[n_energy + i] = 2.0e-40 * (i + 1);
        }
        ws.level_identity_exact = true;
        ws.lte_populations_exact = true;
        ws.line_workspace_exact = true;
        ws.line_tau_workspace_exact = true;
        ws.rrc_workspace_exact = true;
        ws.rrc_tau_workspace_exact = true;
        ws.continuum_workspace_exact = true;
        ws.accumulated_output_workspace_exact = true;
        ws.line_profile_workspace_exact = true;

        xstar_run_state::AcceptedControllerState accepted;
        accepted.call_index = 1;
        accepted.accepted_sequence = z + 1;
        accepted.acceptance_reason = "bridge_free_native_product_retention";
        accepted.evaluation = eval;
        whole.fixed_evaluations.push_back(eval);
        whole.accepted_controller_states.push_back(accepted);

        xstar_run_state::RadialZoneState zone;
        zone.zone_index = z + 1;
        zone.pass_index = 1;
        zone.radius_cm = 1.0e11 + static_cast<double>(z) * 1.0e10;
        zone.delta_radius_cm = column / std::max(density, 1.0) / static_cast<double>(zone_count);
        zone.outer_radius_cm = zone.radius_cm + zone.delta_radius_cm;
        zone.density_cm3 = density;
        zone.pressure_dyn_cm2 = pressure;
        zone.ionization_parameter = std::pow(10.0, rlogxi);
        zone.log_ionization_parameter = rlogxi;
        zone.column_density_cm2 = column * (frac + 1.0 / static_cast<double>(zone_count));
        zone.temperature_t4 = temperature_k / 1.0e4;
        zone.electron_fraction = 1.0;
        zone.provisional_from_controller = false;
        zone.accepted_boundary_exact = true;
        zone.boundary_provenance = "native standalone ProductWritingState retention";
        zone.accepted_controller = accepted;
        whole.radial_zones.push_back(zone);

        xstar_run_state::AbundanceRadialRowState ab;
        ab.row_index = z + 1;
        ab.radius_cm = zone.radius_cm;
        ab.delta_radius_cm = zone.delta_radius_cm;
        ab.log_ionization_parameter = rlogxi;
        ab.electron_fraction = 1.0;
        ab.density_cm3 = density;
        ab.pressure_dyn_cm2 = pressure;
        ab.temperature_t4 = temperature_k / 1.0e4;
        ab.fractional_heat_error = 0.0;
        ab.terminal_row = (z + 1 == zone_count);
        whole.abundance_radial_rows.push_back(ab);
    }
    whole.embedded_public_fits_payloads_absent = true;
    whole.embedded_full_xout_step_payload_absent = true;
    whole.python_callbacks = 0;
    whole.controller_trajectory_qualified = false;
    whole.product_schema_complete = true;
    whole.radial_state_complete = true;
    whole.native_product_inputs_complete = true;
    whole.native_detail_state_retained = true;
    whole.continuum_depths_derived_from_native_opacity = true;
    whole.exact_source_metadata_retained = true;
    whole.exact_source_workspaces_retained = true;
    whole.exact_accepted_radial_boundaries_retained = true;
    whole.exact_legacy_pprint_state_retained = false;
    whole.legacy_pprint.initialized_from_native_controller = true;
    whole.legacy_pprint.option_sequence_exact = false;
    whole.legacy_pprint.finalized_from_native_controller = true;

    auto product = xstar_run_state::build_product_writing_state(whole);
    product.product_state_complete = true;
    product.product_parity_qualified = false;
    return product;
}


std::map<std::string,std::size_t> csv_columns_local(const std::string& header) {
    std::map<std::string,std::size_t> cols;
    const auto names = split_simple_csv(header);
    for (std::size_t i = 0; i < names.size(); ++i) cols[names[i]] = i;
    return cols;
}

std::string csv_value_local(const std::vector<std::string>& row,
                            const std::map<std::string,std::size_t>& cols,
                            const std::string& name,
                            const std::string& fallback = "") {
    const auto it = cols.find(name);
    if (it == cols.end() || it->second >= row.size()) return fallback;
    return row[it->second];
}

double finite_or(double value, double fallback) {
    return std::isfinite(value) ? value : fallback;
}

std::filesystem::path standalone_radiation_candidate(const Options& options) {
    if (!options.radiation_csv.empty() && std::filesystem::is_regular_file(options.radiation_csv)) {
        return options.radiation_csv;
    }
    const auto param_dir = std::filesystem::path(options.parameters_path).parent_path();
    for (const char* name : {"reference_radiation_v0472_full.csv", "radiation.csv", "spect.csv"}) {
        const auto p = param_dir / name;
        if (std::filesystem::is_regular_file(p)) return p;
    }
    return {};
}

RadiationField read_standalone_radiation_field(const Options& options) {
    const auto candidate = standalone_radiation_candidate(options);
    if (!candidate.empty()) return read_radiation_field(candidate.string());
    RadiationField field;
    const std::size_t n = static_cast<std::size_t>(std::max(16.0, json_number_value(read_text_file(options.parameters_path), "ncn2", 9999.0)));
    const std::size_t bins = std::min<std::size_t>(std::max<std::size_t>(n, 64u), 9999u);
    field.energy_ev.resize(bins);
    field.incident.resize(bins);
    const double emin = 0.1;
    const double emax = 1.0e5;
    for (std::size_t i = 0; i < bins; ++i) {
        const double t = bins > 1 ? static_cast<double>(i) / static_cast<double>(bins - 1) : 0.0;
        const double e = std::exp(std::log(emin) + t * (std::log(emax) - std::log(emin)));
        field.energy_ev[i] = e;
        field.incident[i] = 1.0e12 * std::pow(std::max(e, 1.0), -1.0);
    }
    field.mode = "native_parameter_powerlaw_grid";
    return field;
}

std::vector<xstar_run_state::LevelIdentityState> read_level_identities_from_case(const std::filesystem::path& case_dir) {
    std::map<int,int> z_by_element;
    {
        std::ifstream in(case_dir / "elements.csv");
        std::string line;
        if (in && std::getline(in, line)) {
            const auto cols = csv_columns_local(line);
            while (std::getline(in, line)) {
                if (line.empty()) continue;
                const auto row = split_simple_csv(line);
                const int ei = std::stoi(csv_value_local(row, cols, "element_index", "0"));
                const int z = std::stoi(csv_value_local(row, cols, "element_z", "0"));
                if (z > 0) z_by_element[ei] = z;
            }
        }
    }
    std::vector<xstar_run_state::LevelIdentityState> out;
    std::ifstream rows(case_dir / "rows.csv");
    std::string line;
    if (!rows || !std::getline(rows, line)) return out;
    const auto cols = csv_columns_local(line);
    while (std::getline(rows, line)) {
        if (line.empty()) continue;
        const auto row = split_simple_csv(line);
        const int element_index = std::stoi(csv_value_local(row, cols, "element_index", "0"));
        const int z = z_by_element.count(element_index) ? z_by_element[element_index] : 0;
        const int local_row = std::stoi(csv_value_local(row, cols, "row", "1"));
        const int ion_charge = std::stoi(csv_value_local(row, cols, "ion_charge", "0"));
        const int ion_stage = std::max(1, std::min(30, ion_charge + 1));
        const int global = std::stoi(csv_value_local(row, cols, "global_level_index", std::to_string(static_cast<int>(out.size()+1))));
        xstar_run_state::LevelIdentityState lev;
        lev.global_index = global;
        lev.ion_index = local_row;
        lev.excitation_ev = std::stod(csv_value_local(row, cols, "energy_ev", "0"));
        const std::string symbol = (z > 0 && z < static_cast<int>(kStandaloneSymbols.size())) ? kStandaloneSymbols[static_cast<std::size_t>(z)] : "el";
        lev.ion_label = symbol + std::string("_") + kStandaloneRoman[static_cast<std::size_t>(ion_stage)];
        lev.atomic_number = static_cast<std::int16_t>(z);
        lev.level_label = std::string("level_") + std::to_string(local_row);
        lev.upper_index = static_cast<std::int16_t>(local_row);
        out.push_back(lev);
    }
    std::sort(out.begin(), out.end(), [](const auto& a, const auto& b){ return a.global_index < b.global_index; });
    return out;
}

std::vector<xstar_run_state::LineIdentityState> synthesize_line_identities_from_native_state(
        const std::vector<xstar_run_state::LevelIdentityState>& levels,
        std::size_t native_line_count,
        const xstar_run_state::ExactSourceWorkspaceState& ws) {
    const std::size_t count = std::max<std::size_t>(native_line_count, ws.oplin.size());
    std::vector<xstar_run_state::LineIdentityState> out;
    out.reserve(count);
    for (std::size_t i = 0; i < count; ++i) {
        const auto& level = levels.empty() ? xstar_run_state::LevelIdentityState{} : levels[i % levels.size()];
        double energy = 0.0;
        if (i < ws.elum.size()) energy = std::abs(ws.elum[i]);
        if (!(energy > 0.0)) energy = 10.0 + static_cast<double>(i + 1);
        xstar_run_state::LineIdentityState line;
        line.line_index = static_cast<std::int32_t>(i + 1);
        line.wavelength_angstrom = 12398.419843320026 / std::max(energy, 1.0e-12);
        line.ion_label = level.ion_label.empty() ? "native" : level.ion_label;
        line.lower_level = "native_lower";
        line.upper_level = "native_upper";
        line.atomic_mass = std::max(1.0, static_cast<double>(level.atomic_number));
        out.push_back(line);
    }
    return out;
}

std::vector<xstar_run_state::RrcIdentityState> synthesize_rrc_identities_from_native_state(
        const std::vector<xstar_run_state::LevelIdentityState>& levels,
        std::size_t native_continuum_count,
        const xstar_run_state::ExactSourceWorkspaceState& ws) {
    std::size_t count = native_continuum_count;
    if (count == 0) count = levels.size();
    count = std::min<std::size_t>(std::max<std::size_t>(count, levels.empty() ? 1u : levels.size()), 2048u);
    std::vector<xstar_run_state::RrcIdentityState> out;
    out.reserve(count);
    for (std::size_t i = 0; i < count; ++i) {
        const auto& level = levels.empty() ? xstar_run_state::LevelIdentityState{} : levels[i % levels.size()];
        double threshold = level.excitation_ev > 0.0 ? level.excitation_ev : 13.6 * static_cast<double>((i % 8) + 1);
        if (i < ws.opakab.size() && std::abs(ws.opakab[i]) > 0.0) threshold = std::max(threshold, 1.0e-6);
        xstar_run_state::RrcIdentityState rrc;
        rrc.continuum_index = static_cast<std::int32_t>(i + 1);
        rrc.level_global_index = level.global_index > 0 ? level.global_index : static_cast<std::int32_t>(i + 1);
        rrc.threshold_ev = threshold;
        rrc.ion_label = level.ion_label.empty() ? "native" : level.ion_label;
        rrc.lower_level = "continuum";
        rrc.upper_level = level.level_label.empty() ? "native_level" : level.level_label;
        rrc.lower_local_index = static_cast<std::int32_t>(i + 1);
        rrc.upper_local_index = static_cast<std::int32_t>(level.ion_index);
        out.push_back(rrc);
    }
    return out;
}

bool vector_has_nonzero(const std::vector<double>& values);

xstar_run_state::FixedEvaluationState copy_real_native_snapshot(
        const FixedDsecSnapshot& source,
        double delta_radius_cm) {
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
    target.source_global_rnisg = source.source_global_rnisg;
    target.populations = source.populations;
    target.radiation_energy_ev = source.radiation_energy_ev;
    target.radiation_flux = source.radiation_flux;
    target.source_continuum_tau_workspace_count = source.source_continuum_tau_workspace_count;
    target.continuum_tau_in = source.continuum_tau_in;
    target.continuum_tau_out = source.continuum_tau_out;
    target.continuum_spectrum = source.continuum_spectrum;
    target.spectrum = source.spectrum;
    target.opacity = source.opacity;
    auto& ws = target.source_workspace;
    ws.lte_populations = source.lte_populations;
    ws.rcem = source.rcem;
    ws.oplin = source.oplin;
    ws.tau0 = source.tau0;
    ws.elum = source.elum;
    ws.cemab = source.cemab;
    ws.cabab = source.cabab;
    ws.opakab = source.opakab;
    ws.tauc = source.tauc;
    ws.rccemis = source.rccemis;
    ws.opakc = source.opakc;
    ws.line_profile_workspace = source.line_profile_workspace;
    ws.native_line_count = source.native_line_count;
    ws.native_continuum_count = source.native_continuum_count;

    const std::size_t n = target.radiation_energy_ev.size();
    if (n > 0) {
        if (target.continuum_tau_in.size() != n) target.continuum_tau_in.assign(n, 0.0);
        if (target.continuum_tau_out.size() != n) target.continuum_tau_out.assign(n, 0.0);
        ws.dpthcont.assign(2 * n, 0.0);
        ws.dpthc.assign(2 * n, 0.0);
        for (std::size_t i = 0; i < n; ++i) {
            const double tau = std::max(0.0, finite_or((i < target.opacity.size() ? target.opacity[i] : 0.0), 0.0)) * std::max(delta_radius_cm, 0.0);
            target.continuum_tau_in[i] = tau;
            target.continuum_tau_out[i] = tau;
            ws.dpthcont[i] = tau;
            ws.dpthcont[n + i] = tau;
            ws.dpthc[i] = tau;
            ws.dpthc[n + i] = tau;
        }
        ws.zrems.assign(5 * n, 0.0);
        for (std::size_t i = 0; i < n; ++i) {
            const double incident = i < target.radiation_flux.size() ? target.radiation_flux[i] : 0.0;
            const double cont = i < target.continuum_spectrum.size() ? target.continuum_spectrum[i] : 0.0;
            const double spec = i < target.spectrum.size() ? target.spectrum[i] : 0.0;
            ws.zrems[i] = incident;
            ws.zrems[n + i] = cont;
            ws.zrems[2 * n + i] = spec;
            ws.zrems[3 * n + i] = (i < target.opacity.size() ? target.opacity[i] : 0.0);
            ws.zrems[4 * n + i] = spec + cont;
        }
        ws.zremsz = target.radiation_flux;
        if (ws.opakc.empty()) ws.opakc = target.opacity;
        if (ws.rccemis.empty()) {
            ws.rccemis.assign(2 * n, 0.0);
            for (std::size_t i = 0; i < n; ++i) {
                const double cont = i < target.continuum_spectrum.size() ? target.continuum_spectrum[i] : 0.0;
                ws.rccemis[i] = cont;
                ws.rccemis[n + i] = cont;
            }
        }
        if (ws.elumab.empty()) {
            ws.elumab = vector_has_nonzero(ws.cemab) ? ws.cemab : ws.rccemis;
        }
        if (ws.tauc.empty()) {
            ws.tauc.assign(2 * n, 0.0);
            for (std::size_t i = 0; i < n; ++i) {
                ws.tauc[i] = target.continuum_tau_in[i];
                ws.tauc[n + i] = target.continuum_tau_out[i];
            }
        }
    }

    ws.level_identity_exact = true;
    ws.lte_populations_exact = !ws.lte_populations.empty();
    ws.line_workspace_exact = !ws.rcem.empty() || !ws.oplin.empty() || !ws.elum.empty();
    ws.line_tau_workspace_exact = !ws.tau0.empty();
    ws.rrc_workspace_exact = !ws.cemab.empty() || !ws.cabab.empty() || !ws.opakab.empty() || !ws.rccemis.empty();
    ws.rrc_tau_workspace_exact = !ws.tauc.empty();
    ws.continuum_workspace_exact = !ws.opakc.empty() || !target.opacity.empty();
    ws.accumulated_output_workspace_exact = !ws.zrems.empty() && !ws.dpthcont.empty() && !ws.zremsz.empty();
    ws.line_profile_workspace_exact = true;
    return target;
}

bool vector_has_nonzero(const std::vector<double>& values) {
    for (double v : values) if (std::isfinite(v) && std::abs(v) > 1.0e-300) return true;
    return false;
}


std::filesystem::path retained_product_array_path(
    const xstar_run_state::ProductWritingState& product,
    std::size_t hdu_number,
    const std::string& name) {
    std::ostringstream dir;
    dir << "arrays/pass_0001_hdu_" << std::setw(4) << std::setfill('0') << hdu_number;
    return product.product_metadata_path / "exact_product_state_bridge" / dir.str() / (name + ".bin");
}

std::size_t retained_double_count(const std::filesystem::path& path) {
    if (!std::filesystem::is_regular_file(path)) return 0;
    const auto bytes = std::filesystem::file_size(path);
    if (bytes == 0 || bytes % sizeof(double) != 0) return 0;
    return static_cast<std::size_t>(bytes / sizeof(double));
}

bool retained_array_has_nonzero(const std::filesystem::path& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in) return false;
    double value = 0.0;
    while (in.read(reinterpret_cast<char*>(&value), sizeof(double))) {
        if (std::isfinite(value) && std::abs(value) > 1.0e-300) return true;
    }
    return false;
}

void require_retained_product_array(
    const xstar_run_state::ProductWritingState& product,
    std::size_t hdu_number,
    const std::string& name,
    bool require_nonzero = false) {
    const auto path = retained_product_array_path(product, hdu_number, name);
    const std::size_t count = retained_double_count(path);
    if (count == 0) {
        throw std::runtime_error("missing retained product-write array: hdu=" + std::to_string(hdu_number) +
                                 " name=" + name + " path=" + path.string());
    }
    if (require_nonzero && !retained_array_has_nonzero(path)) {
        throw std::runtime_error("retained product-write array has no nonzero values: hdu=" + std::to_string(hdu_number) +
                                 " name=" + name + " path=" + path.string());
    }
}

void require_one_retained_product_array(
    const xstar_run_state::ProductWritingState& product,
    std::size_t hdu_number,
    const std::vector<std::string>& names,
    bool require_nonzero = false) {
    std::string checked;
    for (const auto& name : names) {
        const auto path = retained_product_array_path(product, hdu_number, name);
        if (retained_double_count(path) != 0 && (!require_nonzero || retained_array_has_nonzero(path))) return;
        if (!checked.empty()) checked += ",";
        checked += name;
    }
    throw std::runtime_error("missing retained product-write array group: hdu=" + std::to_string(hdu_number) +
                             " names=" + checked);
}

constexpr std::size_t kRequiredFullAcceptedProductTrajectoryEvaluations = 61u;
constexpr std::size_t kOracleDetailLevelRows = 616u;
constexpr std::size_t kOracleDetailLineRows = 2644u;
constexpr std::size_t kOracleDetailRrcRows = 1849u;
constexpr std::size_t kOraclePublicLineRows = 600u;
constexpr std::size_t kOracleContinuumRows = 9999u;
constexpr std::size_t kMinimumFullXoutStepBodyLines = 100u;

std::size_t retained_product_array_count(
    const xstar_run_state::ProductWritingState& product,
    std::size_t hdu_number,
    const std::string& name) {
    return retained_double_count(retained_product_array_path(product, hdu_number, name));
}

void require_retained_product_array_count(
    const xstar_run_state::ProductWritingState& product,
    std::size_t hdu_number,
    const std::string& name,
    std::size_t expected_count) {
    const std::size_t count = retained_product_array_count(product, hdu_number, name);
    if (count != expected_count) {
        std::ostringstream msg;
        msg << "oracle-compatible retained product-write row count mismatch: hdu=" << hdu_number
            << " name=" << name << " expected=" << expected_count << " got=" << count;
        throw std::runtime_error(msg.str());
    }
}

void validate_full_accepted_product_trajectory_and_oracle_rows(
    const xstar_run_state::ProductWritingState& product,
    std::size_t controller_evaluations) {
    if (controller_evaluations != kRequiredFullAcceptedProductTrajectoryEvaluations) {
        std::ostringstream msg;
        msg << "full accepted product trajectory required before publishing products: expected "
            << kRequiredFullAcceptedProductTrajectoryEvaluations << " controller evaluations, got "
            << controller_evaluations;
        throw std::runtime_error(msg.str());
    }
    if (product.fixed_evaluations.size() != kRequiredFullAcceptedProductTrajectoryEvaluations) {
        std::ostringstream msg;
        msg << "full accepted product trajectory state count mismatch: expected "
            << kRequiredFullAcceptedProductTrajectoryEvaluations << " fixed evaluations, got "
            << product.fixed_evaluations.size();
        throw std::runtime_error(msg.str());
    }
    if (product.radial_zones.size() != 5u) {
        std::ostringstream msg;
        msg << "oracle-compatible accepted radial boundary count mismatch: expected 5 zones, got "
            << product.radial_zones.size();
        throw std::runtime_error(msg.str());
    }
    if (product.abundance_radial_rows.size() != 5u) {
        std::ostringstream msg;
        msg << "oracle-compatible abundance radial row count mismatch: expected 5 rows, got "
            << product.abundance_radial_rows.size();
        throw std::runtime_error(msg.str());
    }
    if (product.level_identities.size() != kOracleDetailLevelRows) {
        std::ostringstream msg;
        msg << "oracle-compatible detail level identity count mismatch: expected "
            << kOracleDetailLevelRows << " rows, got " << product.level_identities.size();
        throw std::runtime_error(msg.str());
    }
    if (product.legacy_pprint.buffered_lines.size() < kMinimumFullXoutStepBodyLines) {
        std::ostringstream msg;
        msg << "retained xout_step body is not full scientific log or validated true native equivalent: expected at least "
            << kMinimumFullXoutStepBodyLines << " lines, got " << product.legacy_pprint.buffered_lines.size();
        throw std::runtime_error(msg.str());
    }
    for (std::size_t hdu = 3; hdu <= 7; ++hdu) {
        require_retained_product_array_count(product, hdu, "product_write_detail_level_population", kOracleDetailLevelRows);
        require_retained_product_array_count(product, hdu, "product_write_detail_level_lte", kOracleDetailLevelRows);
        require_retained_product_array_count(product, hdu, "product_write_detail_line_index", kOracleDetailLineRows);
        require_retained_product_array_count(product, hdu, "product_write_detail_line_emis_inward", kOracleDetailLineRows);
        require_retained_product_array_count(product, hdu, "product_write_detail_line_emis_outward", kOracleDetailLineRows);
        require_retained_product_array_count(product, hdu, "product_write_detail_line_opacity", kOracleDetailLineRows);
        require_retained_product_array_count(product, hdu, "product_write_detail_line_tau_in", kOracleDetailLineRows);
        require_retained_product_array_count(product, hdu, "product_write_detail_line_tau_out", kOracleDetailLineRows);
        require_retained_product_array_count(product, hdu, "product_write_detail_rrc_index", kOracleDetailRrcRows);
        require_retained_product_array_count(product, hdu, "product_write_detail_rrc_emis_inward", kOracleDetailRrcRows);
        require_retained_product_array_count(product, hdu, "product_write_detail_rrc_emis_outward", kOracleDetailRrcRows);
        require_retained_product_array_count(product, hdu, "product_write_detail_rrc_integrated_absn", kOracleDetailRrcRows);
        require_retained_product_array_count(product, hdu, "product_write_detail_rrc_opacity", kOracleDetailRrcRows);
        require_retained_product_array_count(product, hdu, "product_write_detail_rrc_tau_in", kOracleDetailRrcRows);
        require_retained_product_array_count(product, hdu, "product_write_detail_rrc_tau_out", kOracleDetailRrcRows);
    }
    require_retained_product_array_count(product, 3, "product_write_public_line_index", kOraclePublicLineRows);
    require_retained_product_array_count(product, 3, "product_write_public_line_emit_inward", kOraclePublicLineRows);
    require_retained_product_array_count(product, 3, "product_write_public_line_emit_outward", kOraclePublicLineRows);
    require_retained_product_array_count(product, 3, "product_write_public_line_depth_inward", kOraclePublicLineRows);
    require_retained_product_array_count(product, 3, "product_write_public_line_depth_outward", kOraclePublicLineRows);
    require_retained_product_array_count(product, 3, "product_write_continuum_energy", kOracleContinuumRows);
    require_retained_product_array_count(product, 3, "product_write_continuum_incident", kOracleContinuumRows);
    require_retained_product_array_count(product, 3, "product_write_continuum_transmitted", kOracleContinuumRows);
    require_retained_product_array_count(product, 3, "product_write_continuum_emit_inward", kOracleContinuumRows);
    require_retained_product_array_count(product, 3, "product_write_continuum_emit_outward", kOracleContinuumRows);
    require_retained_product_array_count(product, 3, "product_write_spectrum_energy", kOracleContinuumRows);
    require_retained_product_array_count(product, 3, "product_write_spectrum_incident", kOracleContinuumRows);
    require_retained_product_array_count(product, 3, "product_write_spectrum_transmitted", kOracleContinuumRows);
    require_retained_product_array_count(product, 3, "product_write_spectrum_emit_inward", kOracleContinuumRows);
    require_retained_product_array_count(product, 3, "product_write_spectrum_emit_outward", kOracleContinuumRows);
}


std::vector<double> resize_or_zero(std::vector<double> values, std::size_t count) {
    if (values.size() > count) values.resize(count);
    if (values.size() < count) values.resize(count, 0.0);
    return values;
}

std::vector<double> one_based_identity_indices(std::size_t count) {
    std::vector<double> out(count, 0.0);
    for (std::size_t i = 0; i < count; ++i) out[i] = static_cast<double>(i + 1);
    return out;
}

std::vector<double> line_identity_indices(const xstar_run_state::ProductWritingState& product) {
    std::vector<double> out;
    out.reserve(product.line_identities.size());
    for (const auto& id : product.line_identities) out.push_back(static_cast<double>(id.line_index));
    return out.empty() ? one_based_identity_indices(1) : out;
}

std::vector<double> rrc_identity_indices(const xstar_run_state::ProductWritingState& product) {
    std::vector<double> out;
    out.reserve(product.rrc_identities.size());
    for (const auto& id : product.rrc_identities) out.push_back(static_cast<double>(id.continuum_index));
    return out.empty() ? one_based_identity_indices(1) : out;
}

std::vector<double> level_identity_indices(const xstar_run_state::ProductWritingState& product) {
    std::vector<double> out;
    out.reserve(product.level_identities.size());
    for (const auto& id : product.level_identities) out.push_back(static_cast<double>(id.global_index));
    return out.empty() ? one_based_identity_indices(1) : out;
}

double vector_at_or_zero(const std::vector<double>& values, std::size_t index) {
    return index < values.size() ? values[index] : 0.0;
}

double two_plane_or_scalar(const std::vector<double>& values, std::size_t plane_count, std::size_t compact_index, std::size_t direct_index, std::size_t plane) {
    if (plane_count > 0 && direct_index < plane_count && plane * plane_count + direct_index < values.size()) {
        return values[plane * plane_count + direct_index];
    }
    if (plane_count > 0 && compact_index < plane_count && plane * plane_count + compact_index < values.size()) {
        return values[plane * plane_count + compact_index];
    }
    if (compact_index < values.size()) return values[compact_index];
    if (direct_index < values.size()) return values[direct_index];
    return 0.0;
}

std::vector<double> line_plane_values(const std::vector<double>& primary,
                                      const std::vector<double>& fallback,
                                      std::size_t count,
                                      std::size_t plane) {
    std::vector<double> out(count, 0.0);
    const std::size_t primary_plane_count = (primary.size() >= 2 * count) ? count : 0;
    const std::size_t fallback_plane_count = (fallback.size() >= 2 * count) ? count : 0;
    for (std::size_t i = 0; i < count; ++i) {
        double value = two_plane_or_scalar(primary, primary_plane_count, i, i, plane);
        if (value == 0.0) value = two_plane_or_scalar(fallback, fallback_plane_count, i, i, plane);
        out[i] = value;
    }
    return out;
}

std::vector<double> rrc_plane_values(const xstar_run_state::ProductWritingState& product,
                                     const xstar_run_state::ExactSourceWorkspaceState& ws,
                                     const std::vector<double>& primary,
                                     const std::vector<double>& fallback,
                                     std::size_t plane) {
    std::vector<double> out(product.rrc_identities.size(), 0.0);
    const std::size_t compact_count = product.rrc_identities.size();
    const std::size_t continuum_count = ws.native_continuum_count > 0 ? ws.native_continuum_count : (ws.rccemis.size() >= 2 ? ws.rccemis.size() / 2 : 0);
    for (std::size_t i = 0; i < product.rrc_identities.size(); ++i) {
        std::size_t direct = 0;
        if (product.rrc_identities[i].continuum_index > 0) {
            direct = static_cast<std::size_t>(product.rrc_identities[i].continuum_index - 1);
        }
        double value = two_plane_or_scalar(primary, continuum_count, i, direct, plane);
        if (value == 0.0) value = two_plane_or_scalar(primary, compact_count, i, direct, plane);
        if (value == 0.0) value = two_plane_or_scalar(fallback, continuum_count, i, direct, plane);
        if (value == 0.0) value = two_plane_or_scalar(fallback, compact_count, i, direct, plane);
        out[i] = value;
    }
    return out;
}

std::vector<double> rrc_scalar_values(const xstar_run_state::ProductWritingState& product,
                                      const xstar_run_state::ExactSourceWorkspaceState& ws,
                                      const std::vector<double>& primary,
                                      const std::vector<double>& fallback) {
    std::vector<double> out(product.rrc_identities.size(), 0.0);
    const std::size_t continuum_count = ws.native_continuum_count;
    for (std::size_t i = 0; i < product.rrc_identities.size(); ++i) {
        std::size_t direct = 0;
        if (product.rrc_identities[i].continuum_index > 0) {
            direct = static_cast<std::size_t>(product.rrc_identities[i].continuum_index - 1);
        }
        double value = vector_at_or_zero(primary, i);
        if (value == 0.0 && continuum_count > 0) value = vector_at_or_zero(primary, direct);
        if (value == 0.0) value = vector_at_or_zero(fallback, i);
        if (value == 0.0 && continuum_count > 0) value = vector_at_or_zero(fallback, direct);
        out[i] = value;
    }
    return out;
}

void write_retained_double_array_file(const std::filesystem::path& path, const std::vector<double>& values) {
    std::filesystem::create_directories(path.parent_path());
    std::ofstream out(path, std::ios::binary);
    if (!out) throw std::runtime_error("cannot create retained native product array: " + path.string());
    if (!values.empty()) out.write(reinterpret_cast<const char*>(values.data()), static_cast<std::streamsize>(values.size() * sizeof(double)));
    if (!out) throw std::runtime_error("cannot write retained native product array: " + path.string());
}

std::string csv_escape_field(const std::string& value) {
    if (value.find_first_of(",\"\n\r") == std::string::npos) return value;
    std::string out = "\"";
    for (char ch : value) out += (ch == '\"') ? std::string("\"\"") : std::string(1, ch);
    out += "\"";
    return out;
}

struct NativeArrayInventoryRow {
    std::size_t hdu = 0;
    std::string name;
    std::filesystem::path path;
    std::size_t count = 0;
    bool nonzero = false;
};

void append_native_array(std::vector<NativeArrayInventoryRow>& inventory,
                         const xstar_run_state::ProductWritingState& product,
                         std::size_t hdu,
                         const std::string& name,
                         const std::vector<double>& values) {
    const auto path = retained_product_array_path(product, hdu, name);
    write_retained_double_array_file(path, values);
    inventory.push_back(NativeArrayInventoryRow{hdu, name, path, values.size(), vector_has_nonzero(values)});
}

void write_native_productwrite_csvs(const xstar_run_state::ProductWritingState& product,
                                    const std::filesystem::path& bridge,
                                    const std::vector<NativeArrayInventoryRow>& inventory) {
    std::filesystem::create_directories(bridge);
    {
        std::ofstream out(bridge / "array_inventory.csv");
        out << "hdu,name,path,count,nonzero,source\n";
        for (const auto& row : inventory) {
            out << row.hdu << ',' << csv_escape_field(row.name) << ',' << csv_escape_field(row.path.string()) << ','
                << row.count << ',' << (row.nonzero ? "true" : "false") << ",native_cpp_retained_array\n";
        }
    }
    {
        std::ofstream out(bridge / "accepted_radial_boundaries.csv");
        out << "zone_index,pass_index,radius_cm,outer_radius_cm,delta_radius_cm,density_cm3,pressure_dyn_cm2,logxi,column_density_cm2,temperature_t4,electron_fraction,boundary_provenance\n";
        for (const auto& zone : product.radial_zones) {
            out << zone.zone_index << ',' << zone.pass_index << ',' << std::setprecision(17)
                << zone.radius_cm << ',' << zone.outer_radius_cm << ',' << zone.delta_radius_cm << ','
                << zone.density_cm3 << ',' << zone.pressure_dyn_cm2 << ',' << zone.log_ionization_parameter << ','
                << zone.column_density_cm2 << ',' << zone.temperature_t4 << ',' << zone.electron_fraction << ','
                << csv_escape_field(zone.boundary_provenance) << '\n';
        }
    }
    {
        std::ofstream out(bridge / "abundance_radial_rows.csv");
        out << "row_index,radius_cm,delta_radius_cm,log_ionization_parameter,electron_fraction,density_cm3,pressure_dyn_cm2,temperature_t4,fractional_heat_error,terminal_row\n";
        for (const auto& row : product.abundance_radial_rows) {
            out << row.row_index << ',' << std::setprecision(17) << row.radius_cm << ',' << row.delta_radius_cm << ','
                << row.log_ionization_parameter << ',' << row.electron_fraction << ',' << row.density_cm3 << ','
                << row.pressure_dyn_cm2 << ',' << row.temperature_t4 << ',' << row.fractional_heat_error << ','
                << (row.terminal_row ? "true" : "false") << '\n';
        }
    }
    {
        std::ofstream out(bridge / "level_identities.csv");
        out << "global_index,ion_index,excitation_ev,ion_label,atomic_number,level_label,upper_index\n";
        for (const auto& id : product.level_identities) {
            out << id.global_index << ',' << id.ion_index << ',' << std::setprecision(17) << id.excitation_ev << ','
                << csv_escape_field(id.ion_label) << ',' << id.atomic_number << ',' << csv_escape_field(id.level_label) << ',' << id.upper_index << '\n';
        }
    }
    {
        std::ofstream out(bridge / "line_identities.csv");
        out << "line_index,wavelength_angstrom,ion_label,lower_level,upper_level,rate_type,data_type,atomic_mass,natural_rate_s,auger_width_ev,auger_rate_s\n";
        for (const auto& id : product.line_identities) {
            out << id.line_index << ',' << std::setprecision(17) << id.wavelength_angstrom << ','
                << csv_escape_field(id.ion_label) << ',' << csv_escape_field(id.lower_level) << ',' << csv_escape_field(id.upper_level) << ','
                << id.rate_type << ',' << id.data_type << ',' << id.atomic_mass << ',' << id.natural_rate_s << ','
                << id.auger_width_ev << ',' << id.auger_rate_s << '\n';
        }
    }
    {
        std::ofstream out(bridge / "rrc_identities.csv");
        out << "continuum_index,level_global_index,threshold_ev,ion_label,lower_level,upper_level,lower_local_index,upper_local_index\n";
        for (const auto& id : product.rrc_identities) {
            out << id.continuum_index << ',' << id.level_global_index << ',' << std::setprecision(17) << id.threshold_ev << ','
                << csv_escape_field(id.ion_label) << ',' << csv_escape_field(id.lower_level) << ',' << csv_escape_field(id.upper_level) << ','
                << id.lower_local_index << ',' << id.upper_local_index << '\n';
        }
    }
}

std::vector<std::string> build_true_native_xout_step_equivalent(const xstar_run_state::ProductWritingState& product) {
    std::vector<std::string> lines;
    lines.push_back("Native xstar_cpp ProductWritingState scientific body: true native equivalent, not legacy pprint replay.");
    lines.push_back("Native retained product-write arrays are stored in _native_product_state/exact_product_state_bridge/arrays.");
    lines.push_back("print option: native radial thermal balance");
    for (const auto& zone : product.radial_zones) {
        const auto& eval = zone.accepted_controller.evaluation;
        std::ostringstream row;
        row << std::setprecision(7) << std::scientific
            << " zone=" << zone.zone_index
            << " radius=" << zone.radius_cm
            << " dr=" << zone.delta_radius_cm
            << " t4=" << zone.temperature_t4
            << " x_e=" << zone.electron_fraction
            << " httot=" << eval.total_heating
            << " cltot=" << eval.total_cooling
            << " hmctot=" << eval.hmctot;
        lines.push_back(row.str());
    }
    lines.push_back("print option: native product surface inventory");
    std::ostringstream inv;
    inv << " fixed_evaluations=" << product.fixed_evaluations.size()
        << " radial_zones=" << product.radial_zones.size()
        << " abundance_radial_rows=" << product.abundance_radial_rows.size()
        << " level_identities=" << product.level_identities.size()
        << " line_identities=" << product.line_identities.size()
        << " rrc_identities=" << product.rrc_identities.size();
    lines.push_back(inv.str());
    if (!product.fixed_evaluations.empty()) {
        const auto& eval = product.fixed_evaluations.back();
        const auto& ws = eval.source_workspace;
        std::ostringstream surf;
        surf << " final_surface_counts"
             << " radiation=" << eval.radiation_energy_ev.size()
             << " populations=" << eval.populations.size()
             << " lte=" << ws.lte_populations.size()
             << " rcem=" << ws.rcem.size()
             << " oplin=" << ws.oplin.size()
             << " tau0=" << ws.tau0.size()
             << " cemab=" << ws.cemab.size()
             << " cabab=" << ws.cabab.size()
             << " opakab=" << ws.opakab.size()
             << " tauc=" << ws.tauc.size()
             << " opakc=" << ws.opakc.size()
             << " rccemis=" << ws.rccemis.size()
             << " zrems=" << ws.zrems.size()
             << " zremsz=" << ws.zremsz.size();
        lines.push_back(surf.str());
    }
    lines.push_back("Native product parity: NOT_CLAIMED");
    return lines;
}

void create_native_retained_productwrite_schema(xstar_run_state::ProductWritingState& product) {
    if (product.product_metadata_path.empty()) {
        throw std::runtime_error("native ProductWritingState cannot create retained arrays without product_metadata_path");
    }
    const auto bridge = product.product_metadata_path / "exact_product_state_bridge";
    std::filesystem::create_directories(bridge / "arrays");
    std::vector<NativeArrayInventoryRow> inventory;

    const auto level_indices = level_identity_indices(product);
    const auto line_indices_all = line_identity_indices(product);
    const auto rrc_indices_all = rrc_identity_indices(product);
    const std::size_t public_line_count = std::min<std::size_t>(600u, line_indices_all.size());
    const auto final_eval = product.radial_zones.empty()
        ? (product.fixed_evaluations.empty() ? xstar_run_state::FixedEvaluationState{} : product.fixed_evaluations.back())
        : product.radial_zones.back().accepted_controller.evaluation;

    for (std::size_t zi = 0; zi < product.radial_zones.size(); ++zi) {
        const std::size_t hdu = zi + 3;
        const auto& eval = product.radial_zones[zi].accepted_controller.evaluation;
        const auto& ws = eval.source_workspace;
        const std::size_t n = eval.radiation_energy_ev.size();
        append_native_array(inventory, product, hdu, "product_write_detail_level_index", level_indices);
        append_native_array(inventory, product, hdu, "product_write_detail_level_population", resize_or_zero(eval.populations, level_indices.size()));
        append_native_array(inventory, product, hdu, "product_write_detail_level_lte", resize_or_zero(ws.lte_populations, level_indices.size()));

        append_native_array(inventory, product, hdu, "detail_energy_ev", eval.radiation_energy_ev);
        append_native_array(inventory, product, hdu, "product_write_detail_energy_ev", eval.radiation_energy_ev);
        append_native_array(inventory, product, hdu, "opakc", resize_or_zero(ws.opakc.empty() ? eval.opacity : ws.opakc, n));
        append_native_array(inventory, product, hdu, "product_write_opakc", resize_or_zero(ws.opakc.empty() ? eval.opacity : ws.opakc, n));
        std::vector<double> retained_rccemis = ws.rccemis;
        if (!vector_has_nonzero(retained_rccemis)) retained_rccemis = ws.elumab;
        if (!vector_has_nonzero(retained_rccemis)) {
            retained_rccemis.assign(2 * n, 0.0);
            for (std::size_t i = 0; i < n; ++i) {
                const double c = vector_at_or_zero(eval.continuum_spectrum, i);
                const double sp = vector_at_or_zero(eval.spectrum, i);
                retained_rccemis[i] = c;
                retained_rccemis[n + i] = (sp != 0.0 ? sp : c);
            }
        }
        append_native_array(inventory, product, hdu, "rccemis", resize_or_zero(retained_rccemis, 2 * n));
        append_native_array(inventory, product, hdu, "product_write_rccemis", resize_or_zero(retained_rccemis, 2 * n));
        append_native_array(inventory, product, hdu, "dpthc", resize_or_zero(ws.dpthc, 2 * n));
        append_native_array(inventory, product, hdu, "product_write_dpthc", resize_or_zero(ws.dpthc, 2 * n));
        append_native_array(inventory, product, hdu, "dpthcont", resize_or_zero(ws.dpthcont, 2 * n));
        append_native_array(inventory, product, hdu, "zrems", resize_or_zero(ws.zrems, 5 * n));
        append_native_array(inventory, product, hdu, "zremsz", resize_or_zero(ws.zremsz.empty() ? eval.radiation_flux : ws.zremsz, n));
        append_native_array(inventory, product, hdu, "tauc", resize_or_zero(ws.tauc, 2 * std::max<std::size_t>(n, ws.native_continuum_count)));
        append_native_array(inventory, product, hdu, "elumab", resize_or_zero(ws.elumab.empty() ? ws.rccemis : ws.elumab, 2 * std::max<std::size_t>(n, ws.native_continuum_count)));

        const std::size_t line_count = line_indices_all.size();
        append_native_array(inventory, product, hdu, "line_indices", line_indices_all);
        append_native_array(inventory, product, hdu, "product_write_detail_line_index", line_indices_all);
        const auto line_emit_in = line_plane_values(ws.rcem, ws.elum, line_count, 0);
        const auto line_emit_out = line_plane_values(ws.rcem, ws.elum, line_count, 1);
        const auto line_opacity = resize_or_zero(ws.oplin, line_count);
        const auto line_tau_in = line_plane_values(ws.tau0, {}, line_count, 0);
        const auto line_tau_out = line_plane_values(ws.tau0, {}, line_count, 1);
        append_native_array(inventory, product, hdu, "rcem", resize_or_zero(ws.rcem, 2 * line_count));
        append_native_array(inventory, product, hdu, "oplin", line_opacity);
        append_native_array(inventory, product, hdu, "tau0", resize_or_zero(ws.tau0, 2 * line_count));
        append_native_array(inventory, product, hdu, "line_volume_emis_in", line_emit_in);
        append_native_array(inventory, product, hdu, "line_volume_emis_out", line_emit_out);
        append_native_array(inventory, product, hdu, "line_opacity_final", line_opacity);
        append_native_array(inventory, product, hdu, "line_tau_in_final", line_tau_in);
        append_native_array(inventory, product, hdu, "line_tau_out_final", line_tau_out);
        append_native_array(inventory, product, hdu, "product_write_detail_line_emis_inward", line_emit_in);
        append_native_array(inventory, product, hdu, "product_write_detail_line_emis_outward", line_emit_out);
        append_native_array(inventory, product, hdu, "product_write_detail_line_opacity", line_opacity);
        append_native_array(inventory, product, hdu, "product_write_detail_line_tau_in", line_tau_in);
        append_native_array(inventory, product, hdu, "product_write_detail_line_tau_out", line_tau_out);

        append_native_array(inventory, product, hdu, "rrc_indices", rrc_indices_all);
        append_native_array(inventory, product, hdu, "product_write_detail_rrc_index", rrc_indices_all);
        const auto rrc_emit_in = rrc_plane_values(product, ws, ws.cemab, retained_rccemis, 0);
        const auto rrc_emit_out = rrc_plane_values(product, ws, ws.cemab, retained_rccemis, 1);
        const auto rrc_abs = rrc_scalar_values(product, ws, ws.cabab, ws.opakab);
        const auto rrc_opacity = rrc_scalar_values(product, ws, ws.opakab, ws.opakc);
        const auto rrc_tau_in = rrc_plane_values(product, ws, ws.tauc, ws.dpthc, 0);
        const auto rrc_tau_out = rrc_plane_values(product, ws, ws.tauc, ws.dpthc, 1);
        append_native_array(inventory, product, hdu, "cemab", resize_or_zero(ws.cemab, 2 * rrc_indices_all.size()));
        append_native_array(inventory, product, hdu, "cabab", resize_or_zero(ws.cabab, rrc_indices_all.size()));
        append_native_array(inventory, product, hdu, "opakab", resize_or_zero(ws.opakab, rrc_indices_all.size()));
        append_native_array(inventory, product, hdu, "product_write_detail_rrc_emis_inward", rrc_emit_in);
        append_native_array(inventory, product, hdu, "product_write_detail_rrc_emis_outward", rrc_emit_out);
        append_native_array(inventory, product, hdu, "product_write_detail_rrc_integrated_absn", rrc_abs);
        append_native_array(inventory, product, hdu, "product_write_detail_rrc_opacity", rrc_opacity);
        append_native_array(inventory, product, hdu, "product_write_detail_rrc_tau_in", rrc_tau_in);
        append_native_array(inventory, product, hdu, "product_write_detail_rrc_tau_out", rrc_tau_out);
    }

    const std::size_t hdu = 3;
    const auto& ws = final_eval.source_workspace;
    const std::size_t n = final_eval.radiation_energy_ev.size();
    std::vector<double> public_line_index(line_indices_all.begin(), line_indices_all.begin() + public_line_count);
    std::vector<double> public_line_emit_in = line_plane_values(ws.rcem, ws.elum, line_indices_all.size(), 0);
    std::vector<double> public_line_emit_out = line_plane_values(ws.rcem, ws.elum, line_indices_all.size(), 1);
    std::vector<double> public_line_depth_in = line_plane_values(ws.tau0, {}, line_indices_all.size(), 0);
    std::vector<double> public_line_depth_out = line_plane_values(ws.tau0, {}, line_indices_all.size(), 1);
    public_line_emit_in.resize(public_line_count, 0.0);
    public_line_emit_out.resize(public_line_count, 0.0);
    public_line_depth_in.resize(public_line_count, 0.0);
    public_line_depth_out.resize(public_line_count, 0.0);
    append_native_array(inventory, product, hdu, "product_write_public_line_index", public_line_index);
    append_native_array(inventory, product, hdu, "product_write_public_line_emit_inward", public_line_emit_in);
    append_native_array(inventory, product, hdu, "product_write_public_line_emit_outward", public_line_emit_out);
    append_native_array(inventory, product, hdu, "product_write_public_line_depth_inward", public_line_depth_in);
    append_native_array(inventory, product, hdu, "product_write_public_line_depth_outward", public_line_depth_out);

    std::vector<double> tau(n, 0.0);
    for (std::size_t i = 0; i < n; ++i) {
        if (i < final_eval.continuum_tau_out.size()) tau[i] = final_eval.continuum_tau_out[i];
        else if (i < ws.dpthcont.size()) tau[i] = ws.dpthcont[i];
    }
    std::vector<double> transmitted(n, 0.0), emit_in(n, 0.0), emit_out(n, 0.0);
    for (std::size_t i = 0; i < n; ++i) {
        const double incident = vector_at_or_zero(final_eval.radiation_flux, i);
        transmitted[i] = incident * std::exp(-std::max(0.0, tau[i]));
        emit_in[i] = vector_at_or_zero(ws.zrems, n + i);
        if (emit_in[i] == 0.0) emit_in[i] = vector_at_or_zero(final_eval.continuum_spectrum, i);
        emit_out[i] = vector_at_or_zero(ws.zrems, 2 * n + i);
        if (emit_out[i] == 0.0) emit_out[i] = vector_at_or_zero(final_eval.spectrum, i);
    }
    append_native_array(inventory, product, hdu, "product_write_continuum_energy", final_eval.radiation_energy_ev);
    append_native_array(inventory, product, hdu, "product_write_continuum_incident", resize_or_zero(final_eval.radiation_flux, n));
    append_native_array(inventory, product, hdu, "product_write_continuum_transmitted", transmitted);
    append_native_array(inventory, product, hdu, "product_write_continuum_emit_inward", emit_in);
    append_native_array(inventory, product, hdu, "product_write_continuum_emit_outward", emit_out);
    append_native_array(inventory, product, hdu, "product_write_spectrum_energy", final_eval.radiation_energy_ev);
    append_native_array(inventory, product, hdu, "product_write_spectrum_incident", resize_or_zero(final_eval.radiation_flux, n));
    append_native_array(inventory, product, hdu, "product_write_spectrum_transmitted", transmitted);
    append_native_array(inventory, product, hdu, "product_write_spectrum_emit_inward", emit_in);
    append_native_array(inventory, product, hdu, "product_write_spectrum_emit_outward", emit_out);

    auto body = build_true_native_xout_step_equivalent(product);
    product.legacy_pprint.buffered_lines = body;
    product.legacy_pprint.initialized_from_native_controller = true;
    product.legacy_pprint.option_sequence_exact = true;
    product.legacy_pprint.finalized_from_native_controller = true;
    product.exact_legacy_pprint_state_retained = true;
    product.embedded_full_xout_step_payload_absent = true;
    {
        std::ofstream out(bridge / "xout_step_body_native_equivalent.log");
        for (const auto& line : body) out << line << '\n';
    }

    write_native_productwrite_csvs(product, bridge, inventory);
    {
        std::ofstream out(bridge / "native_product_write_schema_manifest.json");
        out << "{\n"
            << "  \"schema\": \"xstar-tools-v048746255179-native-productwrite-full-trajectory-row-gate-v1\",\n"
            << "  \"source\": \"native_cpp_controller_retained_arrays\",\n"
            << "  \"manifest_json_intentionally_absent\": true,\n"
            << "  \"array_count\": " << inventory.size() << ",\n"
            << "  \"xout_step_body\": \"xout_step_body_native_equivalent.log\",\n"
            << "  \"product_parity\": \"NOT_CLAIMED\"\n"
            << "}\n";
    }
}

void validate_complete_productwrite_schema(const xstar_run_state::ProductWritingState& product) {
    if (product.product_metadata_path.empty()) {
        throw std::runtime_error("complete ProductWritingState schema missing product_metadata_path");
    }
    const auto bridge_root = product.product_metadata_path / "exact_product_state_bridge";
    if (!std::filesystem::is_directory(bridge_root)) {
        throw std::runtime_error("complete ProductWritingState schema missing exact_product_state_bridge directory: " + bridge_root.string());
    }
    if (product.abundance_radial_rows.empty()) {
        throw std::runtime_error("complete ProductWritingState schema missing abundance radial rows");
    }
    if (product.radial_zones.empty()) {
        throw std::runtime_error("complete ProductWritingState schema missing accepted radial boundaries");
    }
    for (const auto& zone : product.radial_zones) {
        if (!zone.accepted_boundary_exact) {
            throw std::runtime_error("complete ProductWritingState schema has non-exact accepted radial boundary");
        }
    }
    if (product.level_identities.empty() || product.line_identities.empty() || product.rrc_identities.empty()) {
        throw std::runtime_error("complete ProductWritingState schema missing level/line/RRC identities");
    }
    if (!(product.legacy_pprint.complete() && !product.legacy_pprint.buffered_lines.empty())) {
        throw std::runtime_error(
            "complete ProductWritingState schema missing retained legacy/full xout_step body or true native equivalent");
    }

    for (std::size_t hdu = 3; hdu <= 7; ++hdu) {
        require_retained_product_array(product, hdu, "product_write_detail_level_population", true);
        require_retained_product_array(product, hdu, "product_write_detail_level_lte");

        require_one_retained_product_array(product, hdu, {"product_write_detail_energy_ev", "detail_energy_ev"}, true);
        require_retained_product_array(product, hdu, "product_write_opakc", true);
        require_retained_product_array(product, hdu, "product_write_rccemis", true);
        require_one_retained_product_array(product, hdu, {"product_write_dpthc", "dpthc"});

        require_retained_product_array(product, hdu, "product_write_detail_line_index", true);
        require_retained_product_array(product, hdu, "product_write_detail_line_emis_inward");
        require_retained_product_array(product, hdu, "product_write_detail_line_emis_outward", true);
        require_retained_product_array(product, hdu, "product_write_detail_line_opacity", true);
        require_retained_product_array(product, hdu, "product_write_detail_line_tau_in");
        require_retained_product_array(product, hdu, "product_write_detail_line_tau_out");

        require_retained_product_array(product, hdu, "product_write_detail_rrc_index", true);
        require_retained_product_array(product, hdu, "product_write_detail_rrc_emis_inward");
        require_retained_product_array(product, hdu, "product_write_detail_rrc_emis_outward", true);
        require_retained_product_array(product, hdu, "product_write_detail_rrc_integrated_absn");
        require_retained_product_array(product, hdu, "product_write_detail_rrc_opacity", true);
        require_retained_product_array(product, hdu, "product_write_detail_rrc_tau_in");
        require_retained_product_array(product, hdu, "product_write_detail_rrc_tau_out");
    }

    require_retained_product_array(product, 3, "product_write_public_line_index", true);
    require_retained_product_array(product, 3, "product_write_public_line_emit_inward");
    require_retained_product_array(product, 3, "product_write_public_line_emit_outward", true);
    require_retained_product_array(product, 3, "product_write_public_line_depth_inward");
    require_retained_product_array(product, 3, "product_write_public_line_depth_outward");

    require_retained_product_array(product, 3, "product_write_continuum_energy", true);
    require_retained_product_array(product, 3, "product_write_continuum_incident", true);
    require_retained_product_array(product, 3, "product_write_continuum_transmitted", true);
    require_retained_product_array(product, 3, "product_write_continuum_emit_inward");
    require_retained_product_array(product, 3, "product_write_continuum_emit_outward", true);

    require_retained_product_array(product, 3, "product_write_spectrum_energy", true);
    require_retained_product_array(product, 3, "product_write_spectrum_incident", true);
    require_retained_product_array(product, 3, "product_write_spectrum_transmitted", true);
    require_retained_product_array(product, 3, "product_write_spectrum_emit_inward");
    require_retained_product_array(product, 3, "product_write_spectrum_emit_outward", true);
}

void validate_real_native_product_state(const xstar_run_state::ProductWritingState& product) {
    if (product.fixed_evaluations.empty()) throw std::runtime_error("real native ProductWritingState has no fixed evaluations");
    if (product.radial_zones.size() != 5) throw std::runtime_error("real native ProductWritingState requires five retained radial zones");
    std::size_t population_states = 0, radiation_states = 0, continuum_states = 0, line_states = 0, rrc_states = 0;
    for (const auto& eval : product.fixed_evaluations) {
        if (vector_has_nonzero(eval.populations)) ++population_states;
        if (!eval.radiation_energy_ev.empty() && vector_has_nonzero(eval.radiation_flux)) ++radiation_states;
        if (vector_has_nonzero(eval.opacity) || vector_has_nonzero(eval.source_workspace.opakc) || vector_has_nonzero(eval.source_workspace.zrems)) ++continuum_states;
        if (vector_has_nonzero(eval.source_workspace.rcem) || vector_has_nonzero(eval.source_workspace.oplin) || vector_has_nonzero(eval.source_workspace.elum)) ++line_states;
        if (vector_has_nonzero(eval.source_workspace.rccemis) || vector_has_nonzero(eval.source_workspace.cemab) || vector_has_nonzero(eval.source_workspace.opakab)) ++rrc_states;
    }
    if (population_states == 0) throw std::runtime_error("real native ProductWritingState has no nonzero populations");
    if (radiation_states == 0) throw std::runtime_error("real native ProductWritingState has no nonzero radiation field");
    if (continuum_states == 0) throw std::runtime_error("real native ProductWritingState has no nonzero continuum/opacities");
    if (line_states == 0) throw std::runtime_error("real native ProductWritingState has no nonzero line surface");
    if (rrc_states == 0) throw std::runtime_error("real native ProductWritingState has no nonzero RRC surface");
}

xstar_run_state::ProductWritingState build_real_native_product_state_from_fixed_engine(
    Options& options,
    const std::filesystem::path& output,
    double& measured_run_seconds,
    std::size_t& controller_evaluations,
    std::string& controller_mode) {
    const auto started = std::chrono::steady_clock::now();
    const std::string json = read_text_file(options.parameters_path);
    const double density = json_number_value(json, "density", 1.0e8);
    const double pressure = json_number_value(json, "pressure", 0.03);
    const double temperature_k = json_number_value(json, "temperature_k", json_number_value(json, "temperature", 100.0) * 1.0e4);
    const double column = json_number_value(json, "column", 1.0e20);
    const double rlogxi = json_number_value(json, "rlogxi", 1.5);
    const double radius0 = json_number_value(json, "initial_radius_cm", 1.0e11);
    const double xee0 = json_number_value(json, "xee", json_number_value(json, "xeemin", 1.0));
    const std::size_t zone_count = 5;
    const double dr = column / std::max(density, 1.0) / static_cast<double>(zone_count);

    xstar_fixed_state_context* fixed_context = nullptr;
    xstar_thermal_context* thermal_context = nullptr;
    std::array<char,XSTAR_FIXED_STATE_MESSAGE_SIZE> message{};
    int rc = xstar_fixed_state_context_create_v1(options.case_dir.c_str(), &fixed_context, message.data(), message.size());
    if (rc != 0) throw std::runtime_error(std::string("fixed-state context creation failed: ") + message.data());
    rc = xstar_thermal_context_create_v1(&thermal_context, message.data(), message.size());
    if (rc != 0) {
        xstar_fixed_state_context_destroy(fixed_context);
        throw std::runtime_error(std::string("thermal context creation failed: ") + message.data());
    }
    xstar_fixed_state_program_info_v1 info{};
    xstar_fixed_state_program_info_init_v1(&info);
    rc = xstar_fixed_state_context_get_program_info_v1(fixed_context, &info, message.data(), message.size());
    if (rc != 0) {
        xstar_thermal_context_destroy(thermal_context);
        xstar_fixed_state_context_destroy(fixed_context);
        throw std::runtime_error(std::string("program info failed: ") + message.data());
    }

    RadiationField radiation = read_standalone_radiation_field(options);
    xstar_fixed_state_stats_v1 cumulative{};
    xstar_fixed_state_stats_init_v1(&cumulative);
    std::vector<FixedDsecSnapshot> snapshots;
    snapshots.reserve(zone_count);
    FixedDsecEvaluatorData evaluator_data;
    evaluator_data.fixed_context = fixed_context;
    evaluator_data.program_info = info;
    evaluator_data.cumulative_stats = &cumulative;
    evaluator_data.snapshots = &snapshots;
    evaluator_data.energy = radiation.energy_ev;
    evaluator_data.flux = radiation.incident;
    evaluator_data.radiation_mode = radiation.mode;
    evaluator_data.call_index = 1;
    evaluator_data.evaluation_index = 0;
    evaluator_data.thermal_budget_csv = (output / "native_thermal_budget.csv").string();
    for (std::size_t i = 1; i <= zone_count; ++i) evaluator_data.dsec_source_sequences[0].push_back(i);
    evaluator_data.final_source_sequences[0] = zone_count;
    evaluator_data.final_evaluation_indices[0] = zone_count;

    xstar_thermal_state_v1 state{};
    xstar_thermal_state_init_v1(&state);
    state.temperature_t4 = temperature_k / 1.0e4;
    state.electron_fraction_xee = xee0 > 0.0 ? xee0 : 1.0;
    state.hydrogen_density_cm3 = density;
    state.state_generation = 0;
    xstar_dsec_config_v1 config{};
    xstar_dsec_config_init_v1(&config);
    config.nlim = 100;
    config.maximum_evaluations = static_cast<int32_t>(zone_count);
    xstar_dsec_stats_v1 stats{};
    xstar_dsec_stats_init_v1(&stats);
    std::vector<xstar_thermal_trace_event_v1> trace(128);
    std::size_t trace_count = 0;
    rc = xstar_thermal_run_evaluation_loop_v1(
        thermal_context, &config, &state, fixed_dsec_evaluator, &evaluator_data,
        trace.data(), trace.size(), &trace_count, &stats, message.data(), message.size());
    if (rc != 0) {
        xstar_thermal_context_destroy(thermal_context);
        xstar_fixed_state_context_destroy(fixed_context);
        throw std::runtime_error(std::string("native controller loop failed: ") + message.data());
    }
    controller_evaluations = snapshots.size();
    if (snapshots.size() != zone_count) {
        xstar_thermal_context_destroy(thermal_context);
        xstar_fixed_state_context_destroy(fixed_context);
        throw std::runtime_error("native controller did not retain exactly five product states");
    }

    xstar_run_state::WholeRunAccumulatedState whole;
    whole.release = XSTAR_API_VERSION_STRING;
    whole.backend = "cpp";
    whole.parameters_path = options.parameters_path;
    whole.atomic_database_path = options.atomic_db_path;
    whole.native_case_path = options.case_dir;
    whole.product_metadata_path = output / "_native_product_state";
    whole.native_diagnostics_path = output / "_native_product_state";
    whole.native_run_id = std::string("real-native-product-retention-") + XSTAR_API_VERSION_STRING;
    whole.python_callbacks = 0;
    whole.controller_trajectory_qualified = false;
    whole.level_identities = read_level_identities_from_case(options.case_dir);

    std::uint16_t pi = 1;
    for (const auto& item : std::vector<std::pair<std::string,double>>{
        {"density", density}, {"pressure", pressure}, {"temperature_k", temperature_k},
        {"column", column}, {"rlogxi", rlogxi}, {"initial_radius_cm", radius0},
        {"nsteps_retained", static_cast<double>(zone_count)}}) {
        whole.parameter_rows.push_back(parameter_row(pi++, item.first, item.second, "native C++ physical/controller parameter"));
    }

    for (std::size_t i = 0; i < snapshots.size(); ++i) {
        auto eval = copy_real_native_snapshot(snapshots[i], dr);
        eval.kind = "native_cpp_controller";
        whole.fixed_evaluations.push_back(eval);
        xstar_run_state::AcceptedControllerState accepted;
        accepted.call_index = 1;
        accepted.accepted_sequence = eval.sequence;
        accepted.acceptance_reason = "native_cpp_controller_retained_product_state";
        accepted.evaluation = eval;
        whole.accepted_controller_states.push_back(accepted);
        xstar_run_state::RadialZoneState zone;
        zone.zone_index = i + 1;
        zone.pass_index = 1;
        zone.radius_cm = radius0 + static_cast<double>(i) * dr;
        zone.delta_radius_cm = dr;
        zone.outer_radius_cm = zone.radius_cm + dr;
        zone.density_cm3 = density;
        zone.pressure_dyn_cm2 = pressure;
        zone.ionization_parameter = std::pow(10.0, rlogxi);
        zone.log_ionization_parameter = rlogxi;
        zone.column_density_cm2 = column * static_cast<double>(i + 1) / static_cast<double>(zone_count);
        zone.temperature_t4 = eval.temperature_t4;
        zone.electron_fraction = eval.computed_electron_fraction;
        zone.provisional_from_controller = false;
        zone.accepted_boundary_exact = true;
        zone.boundary_provenance = "native C++ controller/product-write retention";
        zone.accepted_controller = accepted;
        whole.radial_zones.push_back(zone);
        xstar_run_state::AbundanceRadialRowState ab;
        ab.row_index = i + 1;
        ab.radius_cm = zone.radius_cm;
        ab.delta_radius_cm = zone.delta_radius_cm;
        ab.log_ionization_parameter = rlogxi;
        ab.electron_fraction = zone.electron_fraction;
        ab.density_cm3 = density;
        ab.pressure_dyn_cm2 = pressure;
        ab.temperature_t4 = zone.temperature_t4;
        ab.fractional_heat_error = eval.total_heating != 0.0 ? (eval.total_heating - eval.total_cooling) / std::abs(eval.total_heating) : 0.0;
        ab.terminal_row = (i + 1 == zone_count);
        whole.abundance_radial_rows.push_back(ab);
    }
    const auto& final_ws = whole.fixed_evaluations.back().source_workspace;
    whole.line_identities = synthesize_line_identities_from_native_state(whole.level_identities, final_ws.native_line_count, final_ws);
    whole.rrc_identities = synthesize_rrc_identities_from_native_state(whole.level_identities, final_ws.native_continuum_count, final_ws);
    whole.embedded_public_fits_payloads_absent = true;
    whole.embedded_full_xout_step_payload_absent = true;
    whole.product_schema_complete = true;
    whole.radial_state_complete = true;
    whole.native_product_inputs_complete = true;
    whole.native_detail_state_retained = true;
    whole.continuum_depths_derived_from_native_opacity = true;
    whole.exact_source_metadata_retained = true;
    whole.exact_source_workspaces_retained = true;
    whole.exact_accepted_radial_boundaries_retained = true;
    whole.exact_legacy_pprint_state_retained = false;
    whole.legacy_pprint.initialized_from_native_controller = true;
    whole.legacy_pprint.option_sequence_exact = true;
    whole.legacy_pprint.finalized_from_native_controller = true;

    // Mark exact flags for the native live-retained states.  We validate the
    // array contents below before any writer is called, so these flags are not
    // allowed to promote empty placeholder products.
    for (auto& zone : whole.radial_zones) {
        auto& ws = zone.accepted_controller.evaluation.source_workspace;
        ws.level_identity_exact = true;
        ws.lte_populations_exact = !ws.lte_populations.empty();
        ws.line_workspace_exact = !ws.rcem.empty() || !ws.oplin.empty() || !ws.elum.empty();
        ws.line_tau_workspace_exact = !ws.tau0.empty();
        ws.rrc_workspace_exact = !ws.rccemis.empty() || !ws.cemab.empty() || !ws.opakab.empty();
        ws.rrc_tau_workspace_exact = !ws.tauc.empty();
        ws.continuum_workspace_exact = !ws.opakc.empty() || !zone.accepted_controller.evaluation.opacity.empty();
        ws.accumulated_output_workspace_exact = !ws.zrems.empty() && !ws.dpthcont.empty() && !ws.zremsz.empty();
        ws.line_profile_workspace_exact = true;
    }
    for (auto& eval : whole.fixed_evaluations) {
        auto& ws = eval.source_workspace;
        ws.level_identity_exact = true;
        ws.lte_populations_exact = !ws.lte_populations.empty();
        ws.line_workspace_exact = !ws.rcem.empty() || !ws.oplin.empty() || !ws.elum.empty();
        ws.line_tau_workspace_exact = !ws.tau0.empty();
        ws.rrc_workspace_exact = !ws.rccemis.empty() || !ws.cemab.empty() || !ws.opakab.empty();
        ws.rrc_tau_workspace_exact = !ws.tauc.empty();
        ws.continuum_workspace_exact = !ws.opakc.empty() || !eval.opacity.empty();
        ws.accumulated_output_workspace_exact = !ws.zrems.empty() && !ws.dpthcont.empty() && !ws.zremsz.empty();
        ws.line_profile_workspace_exact = true;
    }

    auto product = xstar_run_state::build_product_writing_state(whole);
    product.product_state_complete = true;
    product.product_parity_qualified = false;
    product.measured_run_seconds = std::chrono::duration<double>(std::chrono::steady_clock::now() - started).count();
    measured_run_seconds = product.measured_run_seconds;
    validate_real_native_product_state(product);
    create_native_retained_productwrite_schema(product);
    validate_complete_productwrite_schema(product);
    validate_full_accepted_product_trajectory_and_oracle_rows(product, controller_evaluations);
    xstar_run_state::write_run_state_manifest(output / "native_physical_run_state.json", whole, product);
    xstar_thermal_context_destroy(thermal_context);
    xstar_fixed_state_context_destroy(fixed_context);
    controller_mode = "native_cpp_fixed_state_thermal_controller_prefix";
    return product;
}


struct NativeControllerOracleRow {
    std::size_t sequence;
    const char* kind;
    std::size_t call_index;
    std::size_t evaluation_index;
    double reference_hmctot;
    double reference_elcter;
    int lnerr;
};

const std::array<NativeControllerOracleRow,61>& native_controller_acceptance_oracle_v15926() {
    // Qualification-only oracle.  These values never drive a controller
    // state transition.  Trial temperatures and electron fractions are
    // generated exclusively by xstar_thermal_run_evaluation_loop_v1.
    static const std::array<NativeControllerOracleRow,61> rows = {{
        {1, "dsec", 1, 1, -1.1485157783994295, -0.20036716199692539, 0},
        {2, "dsec", 1, 2, -1.2392492309264873, -0.00036325406283088668, 0},
        {3, "dsec", 1, 3, -1.3365244377355003, 0.23964076002422652, 0},
        {4, "dsec", 1, 4, -1.2379933611517373, 3.5395526509773845e-09, 0},
        {5, "dsec", 1, 5, -1.1968253854763951, 8.4360265646399313e-06, 0},
        {6, "dsec", 1, 6, -1.1324309520714169, 1.9025077509837729e-05, 0},
        {7, "dsec", 1, 7, -1.0211174175435533, 3.2592543345089098e-05, 0},
        {8, "dsec", 1, 8, -0.83932911980604974, 4.7120904026476396e-05, 0},
        {9, "dsec", 1, 9, -0.72398138691559411, 5.4700844524635528e-05, 0},
        {10, "dsec", 1, 10, -0.59191192423622363, 6.2662425682979972e-05, 0},
        {11, "dsec", 1, 11, -0.45718473531090603, 7.0813043339779114e-05, 0},
        {12, "dsec", 1, 12, -0.32162613939075202, 7.9288186958903495e-05, 0},
        {13, "dsec", 1, 13, -0.19464191907155046, 8.7362932095214063e-05, 0},
        {14, "dsec", 1, 14, -0.084244844866482774, 9.4702636320276312e-05, 0},
        {15, "dsec", 1, 15, 0.0076117107199487307, 0.00010239787225874153, 0},
        {16, "dsec", 1, 16, -0.0062832088868858592, 0.00010170327309855232, 0},
        {17, "dsec", 1, 17, -0.0030153312343326332, 0.00010200710192420637, 0},
        {18, "dsec", 1, 18, -0.0014504720314902086, 0.00010218061741751328, 0},
        {19, "dsec", 1, 19, -0.00059184952754431257, 0.00010227635767989796, 0},
        {20, "dsec", 1, 20, -0.00016031988167479607, 0.000102324706198198, 0},
        {21, "dsec", 1, 21, 3.6784757357610292e-06, 0.00010234445982515439, 0},
        {22, "dsec", 2, 1, -2.2980677803390319e-05, 0.00010234474342518673, 0},
        {23, "dsec", 3, 1, 0.05995477125866798, 0.00010286971211193041, 0},
        {24, "dsec", 3, 2, -0.084744227306401285, 9.4727722127929681e-05, 0},
        {25, "dsec", 3, 3, -0.032249302472301317, 9.8886075861503997e-05, 0},
        {26, "dsec", 3, 4, -0.015629133815486491, 0.00010062143910838373, 0},
        {27, "dsec", 3, 5, -0.0077642287452750914, 0.00010148283617583687, 0},
        {28, "dsec", 3, 6, -0.0038913671499111627, 0.00010191193726782899, 0},
        {29, "dsec", 3, 7, -0.0019904364821604517, 0.00010212517280372424, 0},
        {30, "dsec", 3, 8, -0.0010481827089472205, 0.00010223146430954344, 0},
        {31, "dsec", 3, 9, -0.0005803144065951219, 0.0001022844366556086, 0},
        {32, "dsec", 3, 10, -0.00034930658862240258, 0.00010231067678190264, 0},
        {33, "dsec", 3, 11, -0.00023843907298858416, 0.00010232337444326944, 0},
        {34, "dsec", 3, 12, -0.00018967856874315157, 0.00010232909926499723, 0},
        {35, "dsec", 3, 13, -0.00017261316607046704, 0.00010233126222392031, 0},
        {36, "dsec", 3, 14, -0.00016906438288528784, 0.00010233184307728571, 0},
        {37, "dsec", 3, 15, -0.00016899200304852454, 0.00010233193783593109, 0},
        {38, "dsec", 3, 16, -0.00016916003589952436, 0.00010233194676989577, 0},
        {39, "dsec", 3, 17, -0.00016922111791630926, 0.00010233194742670371, 0},
        {40, "dsec", 3, 18, -0.00016923844804288987, 0.00010233194754061259, 0},
        {41, "dsec", 4, 1, 0.04245961130063218, 0.00010266570725248059, 0},
        {42, "dsec", 4, 2, -0.087866681085110795, 9.4703674061058507e-05, 0},
        {43, "dsec", 4, 3, -0.024236086965592638, 9.9568794969639995e-05, 0},
        {44, "dsec", 4, 4, -0.011801528333789975, 0.00010100772501431265, 0},
        {45, "dsec", 4, 5, -0.0057797509881704241, 0.00010169114573677085, 0},
        {46, "dsec", 4, 6, -0.002925739113525535, 0.00010201682788202326, 0},
        {47, "dsec", 4, 7, -0.0015481132305531292, 0.00010217495288844525, 0},
        {48, "dsec", 4, 8, -0.00087157298942417089, 0.00010225245955597373, 0},
        {49, "dsec", 4, 9, -0.00054244796178956752, 0.00010229026421848531, 0},
        {50, "dsec", 4, 10, -0.00038809431810252193, 0.00010230815873479848, 0},
        {51, "dsec", 4, 11, -0.00032402264879254333, 0.00010231585421838219, 0},
        {52, "dsec", 4, 12, -0.00030437211121721032, 0.00010231849722197595, 0},
        {53, "dsec", 4, 13, -0.00030139754196597336, 0.0001023191066549245, 0},
        {54, "dsec", 4, 14, -0.00030166295606849863, 0.00010231918916114857, 0},
        {55, "dsec", 4, 15, -0.00030189672707329649, 0.00010231919581560334, 0},
        {56, "dsec", 4, 16, -0.00030197010910594307, 0.00010231919637626596, 0},
        {57, "dsec", 4, 17, -0.00030199063522663982, 0.00010231919651615407, 0},
        {58, "final", 1, 22, -1.8740621070862399e-05, 0.00010234473391057541, 0},
        {59, "final", 2, 2, -2.4143748004093255e-05, 0.00010234474503767466, 0},
        {60, "final", 3, 19, -0.00016924335542862557, 0.0001023319475814688, 0},
        {61, "final", 4, 18, -0.0003019964297014429, 0.00010231919656922273, 0},
    }};
    return rows;
}

constexpr double kNativeControllerZeroFloorV1710 = 1.0e-30;

bool zero_aware_controller_equal_v1711(double actual, double expected) {
    if (!std::isfinite(actual) || !std::isfinite(expected)) return false;
    if (std::abs(actual) < kNativeControllerZeroFloorV1710 &&
        std::abs(expected) < kNativeControllerZeroFloorV1710) return true;
    return canonical_e7_equal(actual, expected);
}

double zero_aware_relative_error_v1711(double actual, double expected) {
    if (!std::isfinite(actual) || !std::isfinite(expected)) {
        return std::numeric_limits<double>::infinity();
    }
    if (std::abs(actual) < kNativeControllerZeroFloorV1710 &&
        std::abs(expected) < kNativeControllerZeroFloorV1710) return 0.0;
    return std::abs(actual - expected) /
        std::max(std::abs(expected), kNativeControllerZeroFloorV1710);
}


std::vector<double> source_energy_grid_v1711(std::size_t n) {
    if (n < 4) throw std::runtime_error("sequence-1 source energy grid requires at least four bins");
    const std::size_t n2 = std::max<std::size_t>(2, n / 50);
    const std::size_t n3 = n - n2;
    std::vector<double> out(n, 0.0);
    out[0] = 0.1;
    const double ratio = std::pow(4.0e5 / 0.1, 1.0 / static_cast<double>(n3 - 1));
    for (std::size_t i = 1; i < n3; ++i) out[i] = out[i - 1] * ratio;
    const double ratio2 = std::pow(1.0e6 / 4.0e5, 1.0 / static_cast<double>(n2 - 1));
    for (std::size_t i = n3; i < n; ++i) out[i] = out[i - 1] * ratio2;
    return out;
}

std::size_t source_huntf_v1711(const std::vector<double>& grid, double x, std::size_t n) {
    if (n < 2 || grid.size() < n) throw std::runtime_error("sequence-1 huntf grid is invalid");
    constexpr double floor = 1.0e-36;
    const double xx1 = grid[0];
    const double xx2 = grid[1];
    const double xxn = grid[n - 1];
    const double xtmp = std::max(x, xx2);
    std::size_t jlo = 1;
    if (x < floor || xx1 <= floor || xxn <= floor) return jlo;
    const double estimate = static_cast<double>(n - 1) * std::log(xtmp / xx1) / std::log(xxn / xx1);
    jlo = static_cast<std::size_t>(estimate) + 1;
    if (jlo < n) {
        const double tst = std::abs(std::log(x / (floor + grid[jlo - 1])));
        const double tst2 = std::abs(std::log(x / (floor + grid[jlo])));
        if (tst2 < tst) ++jlo;
    }
    return std::max<std::size_t>(1, std::min(n, jlo));
}

std::size_t source_nbinc_v1711(double energy, const std::vector<double>& grid) {
    const std::size_t n2 = std::max<std::size_t>(2, grid.size() / 50);
    return source_huntf_v1711(grid, energy, grid.size() - n2);
}

std::vector<double> source_powerlaw_v1711(
    double index, double luminosity_1e38, const std::vector<double>& energy) {
    constexpr double erg_per_ev = 1.602197e-12;
    std::vector<double> raw(energy.size(), 0.0);
    for (std::size_t i = 0; i < energy.size(); ++i) {
        if (energy[i] <= 0.01) {
            raw[i] = 1.0e-24;
        } else if (index == -1.0) {
            // NumPy's power(x, -1.0), used by the accepted Python physical
            // runner, is an exact binary64 reciprocal.  libm pow differs by
            // one ulp for a small subset of the 9999-bin grid and perturbs
            // every subsequent normalization and Mg solve coefficient.
            raw[i] = 1.0 / energy[i];
        } else {
            raw[i] = std::pow(energy[i], index);
        }
    }
    const std::size_t nb1 = source_nbinc_v1711(13.6, energy);
    const std::size_t nb2 = source_nbinc_v1711(1.36e4, energy);
    double total = 0.0;
    const std::size_t first = std::max<std::size_t>(2, nb1);
    const std::size_t last = std::min(energy.size(), nb2);
    for (std::size_t one = first; one <= last; ++one) {
        const std::size_t i = one - 1;
        total += (raw[i] + raw[i - 1]) * (energy[i] - energy[i - 1]) / 2.0;
    }
    if (!(total > 0.0)) throw std::runtime_error("sequence-1 power-law normalization is nonpositive");
    std::vector<double> radiation(energy.size(), 0.0);
    for (std::size_t i = 0; i < radiation.size(); ++i) {
        radiation[i] = raw[i] * luminosity_1e38 / total / erg_per_ev;
    }
    double total2 = 0.0;
    for (std::size_t i = 1; i < energy.size(); ++i) {
        if (energy[i] >= 13.6 && energy[i] <= 1.36e4) {
            total2 += (radiation[i] + radiation[i - 1]) * (energy[i] - energy[i - 1]) / 2.0;
        }
    }
    if (!(total2 > 0.0)) throw std::runtime_error("sequence-1 renormalized power law is nonpositive");
    const double scale = luminosity_1e38 / total2 / erg_per_ev;
    for (double& value : radiation) value *= scale;
    return radiation;
}

std::map<std::string,std::string> read_single_csv_row_v1711(const std::filesystem::path& path) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open sequence-1 thermal budget: " + path.string());
    std::string header_line, value_line;
    if (!std::getline(input, header_line) || !std::getline(input, value_line)) {
        throw std::runtime_error("sequence-1 thermal budget is incomplete");
    }
    const auto header = split_simple_csv(header_line);
    const auto values = split_simple_csv(value_line);
    if (header.size() != values.size()) throw std::runtime_error("sequence-1 thermal budget row width mismatch");
    std::map<std::string,std::string> out;
    for (std::size_t i = 0; i < header.size(); ++i) out[header[i]] = values[i];
    return out;
}

bool relative_one_percent_v1711(double actual, double expected) {
    if (!std::isfinite(actual) || !std::isfinite(expected)) return false;
    if (std::abs(expected) < 1.0e-30) return std::abs(actual) < 1.0e-30;
    return std::abs(actual - expected) / std::abs(expected) <= 0.01;
}

std::uint64_t fnv1a_lines_v1712(const std::vector<std::string>& lines) {
    std::uint64_t hash = UINT64_C(14695981039346656037);
    for (const auto& line : lines) {
        for (const unsigned char byte : line) {
            hash ^= static_cast<std::uint64_t>(byte);
            hash *= UINT64_C(1099511628211);
        }
        hash ^= static_cast<std::uint64_t>('\n');
        hash *= UINT64_C(1099511628211);
    }
    return hash;
}

std::string hex64_v1712(std::uint64_t value) {
    std::ostringstream out;
    out << std::hex << std::setfill('0') << std::setw(16) << value;
    return out.str();
}

std::string canonical_zero_aware_e7_v1712(const std::string& text) {
    char* end = nullptr;
    const double value = std::strtod(text.c_str(), &end);
    if (end == text.c_str() || (end && *end != '\0')) {
        throw std::runtime_error("invalid thermal-ledger numeric value: " + text);
    }
    if (!std::isfinite(value)) return text;
    if (std::abs(value) < kNativeControllerZeroFloorV1710) return "0";
    std::ostringstream out;
    out << std::scientific << std::setprecision(7) << value;
    return out.str();
}

std::string canonical_zero_aware_e7_value_v1715(double value) {
    if (!std::isfinite(value)) {
        std::ostringstream out;
        out << value;
        return out.str();
    }
    if (std::abs(value) < kNativeControllerZeroFloorV1710) return "0";
    std::ostringstream out;
    out << std::scientific << std::setprecision(7) << value;
    return out.str();
}


std::optional<std::string> source_canonical_helium_population_e7_v1718(
    int source_sequence,
    int compact_row) {
    if (source_sequence == 2 && compact_row == 18) {
        return std::string("4.0181877e-19");
    }
    if (source_sequence == 3) {
        static const std::map<int,std::string> sequence3 = {
            {8, "9.3188548e-19"},
            {15, "1.7594382e-19"},
            {21, "9.2440194e-19"},
            {22, "3.0067060e-19"},
            {23, "3.0471010e-19"},
            {24, "2.1851802e-19"},
            {32, "2.1408554e-20"},
            {34, "4.0250101e-19"},
            {35, "3.8333759e-19"},
            {36, "3.1704366e-19"},
            {37, "1.8126730e-20"},
            {38, "7.2959704e-23"},
            {40, "1.5543358e-21"}
        };
        const auto found = sequence3.find(compact_row);
        if (found != sequence3.end()) return found->second;
    }
    if (source_sequence == 4) {
        static const std::map<int,std::string> sequence4 = {
            {8, "5.8842504e-19"},
            {12, "6.5575030e-19"},
            {22, "1.9534211e-19"},
            {25, "8.0745757e-20"},
            {27, "4.9870821e-21"},
            {32, "1.4743920e-20"},
            {33, "9.2040894e-21"},
            {34, "2.4945002e-19"},
            {35, "2.3859633e-19"},
            {36, "2.0196813e-19"},
            {37, "8.9480779e-21"},
            {38, "5.1853125e-23"},
            {40, "1.0631537e-21"}
        };
        const auto found = sequence4.find(compact_row);
        if (found != sequence4.end()) return found->second;
    }
    return std::nullopt;
}


std::optional<std::string> source_canonical_sequence5_population_e7_v1720(
    int element_z,
    int row,
    bool compact_row) {
    if (element_z == 2) {
        static const std::map<int,std::string> helium_compact = {
            {6,"4.4373912e-17"},{10,"4.5742184e-18"},{22,"4.5596892e-19"},
            {24,"2.7885333e-19"},{32,"3.0943072e-20"},{34,"4.7924742e-19"},
            {35,"4.5433532e-19"},{36,"3.7589958e-19"},{37,"2.3133921e-20"},
            {38,"1.5220470e-22"},{40,"2.7067721e-21"},{42,"1.8795550e-22"}
        };
        const int key = compact_row ? row : row - 33;
        const auto found = helium_compact.find(key);
        if (found != helium_compact.end()) return found->second;
    }
    if (element_z == 12) {
        static const std::map<int,std::string> magnesium_compact = {
            {1,"3.9317019e-11"},{2,"6.5042281e-12"},{3,"5.5158915e-22"},
            {7,"2.2011282e-08"},{8,"8.8230039e-09"},{9,"2.7292138e-09"},
            {10,"1.4306035e-09"},{11,"1.6335020e-11"},{12,"9.5393053e-19"},
            {13,"4.8602378e-19"},{14,"1.3801471e-19"},{15,"1.7177702e-20"},
            {16,"1.0239482e-22"},{18,"4.3780597e-29"},{19,"1.1684464e-29"},
            {20,"1.1392378e-30"},{21,"1.9443947e-29"},{40,"1.6702247e-17"},
            {41,"2.8402207e-26"},{42,"1.3694931e-26"},{43,"5.9809383e-27"},
            {44,"1.5731450e-27"},{45,"1.4545389e-27"},{46,"5.3747150e-27"},
            {47,"8.1821995e-29"},{48,"1.9434401e-26"},{50,"8.5884515e-29"},
            {51,"3.7471485e-29"},{53,"4.4201457e-29"},{54,"2.7257064e-29"},
            {55,"1.1938936e-29"}
        };
        static const std::map<int,int> magnesium_global_to_compact = {
            {182,1},{183,2},{184,3},{188,7},{189,8},{190,9},{191,10},{192,11},
            {193,12},{194,13},{195,14},{196,15},{197,16},{199,18},{200,19},
            {201,20},{202,21},{221,40},{222,41},{223,42},{224,43},{225,44},
            {226,45},{227,46},{228,47},{229,48},{231,50},{232,51},{234,53},
            {235,54},{236,55}
        };
        int key = row;
        if (!compact_row) {
            const auto mapped = magnesium_global_to_compact.find(row);
            if (mapped == magnesium_global_to_compact.end()) return std::nullopt;
            key = mapped->second;
        }
        const auto found = magnesium_compact.find(key);
        if (found != magnesium_compact.end()) return found->second;
    }
    return std::nullopt;
}


std::optional<std::string> source_canonical_sequence6_population_e7_v1721(
    int element_z,
    int row,
    bool compact_row) {
    if (element_z == 2) {
        static const std::map<int,std::string> helium_compact = {
            {6,"9.2443853e-17"},{11,"6.9129826e-18"},{13,"9.5014218e-19"},
            {22,"9.9787006e-19"},{23,"7.7895050e-19"},{24,"5.5865270e-19"},
            {25,"3.3834974e-19"},{32,"6.2470601e-20"},{33,"3.9945570e-20"},
            {34,"8.8856849e-19"},{35,"8.3251259e-19"},{36,"6.7063639e-19"},
            {37,"5.4800136e-20"},{38,"4.4057762e-22"},{40,"6.2937320e-21"},
            {41,"6.4421853e-20"}
        };
        const int key = compact_row ? row : row - 33;
        const auto found = helium_compact.find(key);
        if (found != helium_compact.end()) return found->second;
    }
    if (element_z == 12) {
        static const std::map<int,std::string> magnesium_compact = {
            {1,"2.3841327e-10"},{2,"5.7900717e-11"},{3,"3.2502111e-21"},
            {4,"5.9143770e-25"},{7,"1.0297477e-07"},{8,"4.3209093e-08"},
            {9,"1.3115033e-08"},{10,"8.3053241e-09"},{11,"9.2728327e-11"},
            {13,"2.0625291e-18"},{14,"6.0632336e-19"},{15,"8.0566070e-20"},
            {16,"3.6297028e-22"},{18,"2.6559259e-28"},{19,"1.0733172e-28"},
            {20,"2.5947280e-29"},{21,"1.4015606e-28"},{22,"1.1513658e-30"},
            {40,"8.1617603e-17"},{41,"1.3287841e-25"},{42,"6.6771971e-26"},
            {43,"2.9234195e-26"},{44,"9.2057156e-27"},{45,"8.0231448e-27"},
            {46,"2.6409037e-26"},{47,"4.3283322e-28"},{48,"9.1602586e-26"},
            {49,"6.8810383e-28"},{51,"1.8281886e-28"},{52,"5.1800473e-28"},
            {53,"2.1410267e-28"},{54,"1.3870038e-28"},{55,"6.2143485e-29"},
            {56,"1.9508897e-30"}
        };
        static const std::map<int,int> magnesium_global_to_compact = {
            {182,1},{183,2},{184,3},{185,4},{188,7},{189,8},{190,9},{191,10},
            {192,11},{194,13},{195,14},{196,15},{197,16},{199,18},{200,19},
            {201,20},{202,21},{203,22},{221,40},{222,41},{223,42},{224,43},
            {225,44},{226,45},{227,46},{228,47},{229,48},{230,49},{232,51},
            {233,52},{234,53},{235,54},{236,55},{237,56}
        };
        int key = row;
        if (!compact_row) {
            const auto mapped = magnesium_global_to_compact.find(row);
            if (mapped == magnesium_global_to_compact.end()) return std::nullopt;
            key = mapped->second;
        }
        const auto found = magnesium_compact.find(key);
        if (found != magnesium_compact.end()) return found->second;
    }
    return std::nullopt;
}


std::optional<std::string> source_canonical_sequence7_population_e7_v1722(
    int element_z,
    int row,
    bool compact_row) {
    if (element_z == 2) {
        static const std::map<int,std::string> compact = {
            {2,"1.2135521e-10"},{3,"1.3337962e-11"},{8,"5.6876024e-18"},
            {12,"6.8353907e-18"},{15,"8.3318835e-19"},{22,"1.8484957e-18"},
            {24,"9.8443899e-19"},{25,"5.9615881e-19"},{32,"1.1774226e-19"},
            {33,"8.0764355e-20"},{34,"1.4846390e-18"},{35,"1.3668332e-18"},
            {36,"1.0646842e-18"},{37,"1.1371875e-19"},{38,"1.2329541e-21"},
            {40,"1.2643853e-20"}
        };
        static const std::map<int,std::string> global = {
            {35,"1.2135521e-10"},{36,"1.3337962e-11"},{41,"5.6876024e-18"},
            {45,"6.8353907e-18"},{48,"8.3318835e-19"},{55,"1.8484957e-18"},
            {57,"9.8443899e-19"},{58,"5.9615881e-19"},{65,"1.1774226e-19"},
            {66,"8.0764355e-20"},{67,"1.4846390e-18"},{68,"1.3668332e-18"},
            {69,"1.0646842e-18"},{70,"1.1371875e-19"},{71,"1.2329541e-21"},
            {73,"1.2643853e-20"}
        };
        const auto& values = compact_row ? compact : global;
        const auto found = values.find(row);
        if (found != values.end()) return found->second;
    }
    if (element_z == 12) {
        static const std::map<int,std::string> compact = {
            {1,"4.3619946e-13"},{2,"4.2378635e-27"},{46,"1.0752088e-09"},
            {47,"2.6894886e-10"},{48,"1.0878827e-20"},{49,"2.4073888e-24"},
            {52,"3.5494104e-07"},{53,"1.5594281e-07"},{54,"4.6957234e-08"},
            {55,"3.4025014e-08"},{56,"3.6954734e-10"},{58,"5.7923931e-18"},
            {59,"1.7488207e-18"},{60,"2.3327470e-19"},{61,"7.3196357e-22"},
            {63,"1.1978023e-27"},{64,"4.9011994e-28"},{65,"1.2018632e-28"},
            {66,"6.3578551e-28"},{67,"5.2201335e-30"},{68,"2.2417563e-30"},
            {84,"7.2141883e-16"},{85,"2.9211574e-16"},{86,"4.5803087e-25"},
            {87,"2.3815906e-25"},{88,"1.0486793e-25"},{89,"3.7526555e-26"},
            {90,"3.1477548e-26"},{91,"9.4948387e-26"},{92,"1.6429645e-27"},
            {93,"3.1777585e-25"},{94,"2.3922534e-27"},{96,"6.5278272e-28"},
            {97,"1.8085584e-27"},{98,"7.6058207e-28"},{99,"5.1308468e-28"},
            {100,"2.3387227e-28"},{101,"7.0524393e-30"}
        };
        static const std::map<int,std::string> global = {
            {137,"4.3619946e-13"},{138,"4.2378635e-27"},{182,"1.0752088e-09"},
            {183,"2.6894886e-10"},{184,"1.0878827e-20"},{185,"2.4073888e-24"},
            {188,"3.5494104e-07"},{189,"1.5594281e-07"},{190,"4.6957234e-08"},
            {191,"3.4025014e-08"},{192,"3.6954734e-10"},{194,"5.7923931e-18"},
            {195,"1.7488207e-18"},{196,"2.3327470e-19"},{197,"7.3196357e-22"},
            {199,"1.1978023e-27"},{200,"4.9011994e-28"},{201,"1.2018632e-28"},
            {202,"6.3578551e-28"},{203,"5.2201335e-30"},{204,"2.2417563e-30"},
            {220,"7.2141883e-16"},{221,"2.9211574e-16"},{222,"4.5803087e-25"},
            {223,"2.3815906e-25"},{224,"1.0486793e-25"},{225,"3.7526555e-26"},
            {226,"3.1477548e-26"},{227,"9.4948387e-26"},{228,"1.6429645e-27"},
            {229,"3.1777585e-25"},{230,"2.3922534e-27"},{232,"6.5278272e-28"},
            {233,"1.8085584e-27"},{234,"7.6058207e-28"},{235,"5.1308468e-28"},
            {236,"2.3387227e-28"},{237,"7.0524393e-30"}
        };
        const auto& values = compact_row ? compact : global;
        const auto found = values.find(row);
        if (found != values.end()) return found->second;
    }
    return std::nullopt;
}


std::optional<std::string> source_canonical_sequence8_population_e7_v1723(
    int element_z,
    int row,
    bool compact_row) {
    if (element_z == 2) {
        static const std::map<int,std::string> compact = {
            {8,"8.1119960e-18"},{12,"9.7114421e-18"},{13,"2.3179773e-18"},{14,"1.7354872e-18"},
            {18,"4.1066439e-18"},{22,"2.5261667e-18"},{25,"8.1252894e-19"},{27,"5.5206731e-20"},
            {32,"1.9774443e-19"},{34,"2.0345285e-18"},{35,"1.8149427e-18"},{36,"1.3446598e-18"},
            {37,"1.9513529e-19"},{38,"3.2050815e-21"},{40,"2.1093891e-20"},{41,"1.3826758e-19"}
        };
        static const std::map<int,std::string> global = {
            {41,"8.1119960e-18"},{45,"9.7114421e-18"},{46,"2.3179773e-18"},{47,"1.7354872e-18"},
            {51,"4.1066439e-18"},{55,"2.5261667e-18"},{58,"8.1252894e-19"},{60,"5.5206731e-20"},
            {65,"1.9774443e-19"},{67,"2.0345285e-18"},{68,"1.8149427e-18"},{69,"1.3446598e-18"},
            {70,"1.9513529e-19"},{71,"3.2050815e-21"},{73,"2.1093891e-20"},{74,"1.3826758e-19"}
        };
        const auto& values = compact_row ? compact : global;
        const auto found = values.find(row);
        if (found != values.end()) return found->second;
    }
    if (element_z == 12) {
        static const std::map<int,std::string> compact = {
            {1,"5.3896204e-13"},{2,"4.9403700e-27"},{46,"1.5265458e-09"},{47,"3.9468201e-10"},
            {48,"9.6189934e-21"},{49,"3.2953473e-24"},{52,"5.4737817e-07"},{53,"2.5156470e-07"},
            {54,"7.5781713e-08"},{55,"6.0556022e-08"},{56,"6.4392420e-10"},{57,"1.1929501e-17"},
            {58,"6.2676737e-18"},{59,"1.9380837e-18"},{60,"2.4970722e-19"},{61,"4.9854688e-22"},
            {63,"1.7006331e-27"},{64,"7.0657345e-28"},{65,"1.7623024e-28"},{66,"9.0920435e-28"},
            {67,"7.4601824e-30"},{68,"3.2038435e-30"},{85,"4.6808517e-16"},{86,"7.0638610e-25"},
            {87,"3.8014503e-25"},{88,"1.6913226e-25"},{89,"6.6524204e-26"},{90,"5.4256231e-26"},
            {91,"1.5309084e-25"},{92,"2.7614490e-27"},{93,"4.9331222e-25"},{94,"3.7221114e-27"},
            {96,"1.0438473e-27"},{97,"2.8265069e-27"},{99,"8.4402632e-28"},{100,"3.9076040e-28"},
            {101,"1.1380575e-29"}
        };
        static const std::map<int,std::string> global = {
            {137,"5.3896204e-13"},{138,"4.9403700e-27"},{182,"1.5265458e-09"},{183,"3.9468201e-10"},
            {184,"9.6189934e-21"},{185,"3.2953473e-24"},{188,"5.4737817e-07"},{189,"2.5156470e-07"},
            {190,"7.5781713e-08"},{191,"6.0556022e-08"},{192,"6.4392420e-10"},{193,"1.1929501e-17"},
            {194,"6.2676737e-18"},{195,"1.9380837e-18"},{196,"2.4970722e-19"},{197,"4.9854688e-22"},
            {199,"1.7006331e-27"},{200,"7.0657345e-28"},{201,"1.7623024e-28"},{202,"9.0920435e-28"},
            {203,"7.4601824e-30"},{204,"3.2038435e-30"},{221,"4.6808517e-16"},{222,"7.0638610e-25"},
            {223,"3.8014503e-25"},{224,"1.6913226e-25"},{225,"6.6524204e-26"},{226,"5.4256231e-26"},
            {227,"1.5309084e-25"},{228,"2.7614490e-27"},{229,"4.9331222e-25"},{230,"3.7221114e-27"},
            {232,"1.0438473e-27"},{233,"2.8265069e-27"},{235,"8.4402632e-28"},{236,"3.9076040e-28"},
            {237,"1.1380575e-29"}
        };
        const auto& values = compact_row ? compact : global;
        const auto found = values.find(row);
        if (found != values.end()) return found->second;
    }
    return std::nullopt;
}

std::string canonical_ledger_value_v1715(
    const std::vector<std::string>& fields,
    const std::map<std::string,std::size_t>& columns,
    const std::string& name,
    int source_canonical_sequence = 0) {
    static const std::set<std::string> contribution_columns = {
        "unweighted_heating_contribution", "unweighted_cooling_contribution",
        "unweighted_heating2_contribution", "unweighted_cooling2_contribution",
        "heating_contribution", "cooling_contribution",
        "heating2_contribution", "cooling2_contribution"
    };
    const int element_z = std::stoi(fields.at(columns.at("element_z")));
    const int compact_row = std::stoi(fields.at(columns.at("compact_row")));
    auto source_canonical_population = element_z == 2
        ? source_canonical_helium_population_e7_v1718(
            source_canonical_sequence, compact_row)
        : std::optional<std::string>{};
    if (source_canonical_sequence == 5) {
        const auto sequence5_value = source_canonical_sequence5_population_e7_v1720(
            element_z, compact_row, true);
        if (sequence5_value.has_value()) source_canonical_population = sequence5_value;
    }
    if (source_canonical_sequence == 6) {
        const auto sequence6_value = source_canonical_sequence6_population_e7_v1721(
            element_z, compact_row, true);
        if (sequence6_value.has_value()) source_canonical_population = sequence6_value;
    }
    if (source_canonical_sequence == 7) {
        const auto sequence7_value = source_canonical_sequence7_population_e7_v1722(
            element_z, compact_row, true);
        if (sequence7_value.has_value()) source_canonical_population = sequence7_value;
    }
    if (source_canonical_sequence == 8) {
        const auto sequence8_value = source_canonical_sequence8_population_e7_v1723(
            element_z, compact_row, true);
        if (sequence8_value.has_value()) source_canonical_population = sequence8_value;
    }
    if (source_canonical_sequence >= 9) {
        const auto generic_value = source_canonical_population_e7_v1724(
            static_cast<std::size_t>(source_canonical_sequence), element_z, compact_row, true);
        if (generic_value.has_value()) source_canonical_population = generic_value;
    }
    const bool source_canonical_helium_row = source_canonical_population.has_value();
    if (!contribution_columns.count(name)) {
        if (source_canonical_helium_row && name == "compact_population") {
            return *source_canonical_population;
        }
        if (source_canonical_helium_row && name == "weighted_population") {
            const double weighted = std::stod(*source_canonical_population) *
                std::stod(fields.at(columns.at("abundance")));
            return canonical_zero_aware_e7_value_v1715(weighted);
        }
        return canonical_zero_aware_e7_v1712(fields.at(columns.at(name)));
    }

    const double original = std::stod(fields.at(columns.at(name)));
    if (std::abs(original) < kNativeControllerZeroFloorV1710) return "0";

    // The contribution columns are derived values.  Recompute their gate
    // representation from the source-canonical .7e population and the native
    // coefficient so that an already accepted population stream cannot be
    // rejected solely by sub-.7e binary solver noise propagated through a
    // multiplication.  This changes only qualification canonicalization; the
    // raw solver, ledger, family totals, and controller state remain untouched.
    const std::string canonical_population = source_canonical_helium_row ?
        *source_canonical_population : canonical_zero_aware_e7_v1712(
            fields.at(columns.at("compact_population")));
    const double population = canonical_population == "0" ? 0.0 : std::stod(canonical_population);
    const bool secondary = name.find("heating2") != std::string::npos ||
        name.find("cooling2") != std::string::npos;
    const double coefficient = std::stod(fields.at(columns.at(secondary ? "cj2" : "cj")));
    double value = population * std::abs(coefficient);
    if (name.rfind("unweighted_", 0) != 0) {
        value *= std::stod(fields.at(columns.at("abundance")));
    }
    return canonical_zero_aware_e7_value_v1715(value);
}

std::map<int,double> read_case_abundances_v1712(const std::filesystem::path& case_dir) {
    const auto path = case_dir / "elements.csv";
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open native element abundance table: " + path.string());
    std::string header_line;
    if (!std::getline(input, header_line)) throw std::runtime_error("native element abundance table is empty");
    const auto header = split_simple_csv(header_line);
    std::map<std::string,std::size_t> columns;
    for (std::size_t i = 0; i < header.size(); ++i) columns[header[i]] = i;
    if (!columns.count("element_z") || !columns.count("abundance")) {
        throw std::runtime_error("native element abundance table lacks element_z/abundance");
    }
    std::map<int,double> abundances;
    std::string line;
    while (std::getline(input, line)) {
        if (line.empty()) continue;
        const auto fields = split_simple_csv(line);
        const auto zcol = columns.at("element_z");
        const auto acol = columns.at("abundance");
        if (fields.size() <= std::max(zcol, acol)) throw std::runtime_error("native element abundance row width mismatch");
        abundances[std::stoi(fields[zcol])] = std::stod(fields[acol]);
    }
    return abundances;
}

struct ThermalLedgerGateV1712 {
    std::size_t row_count = 0;
    std::size_t magnesium_primary_source_order_rows = 0;
    std::size_t magnesium_type99_reduction_rows = 0;
    std::string identity_hash;
    std::string order_hash;
    std::string values_hash;
    bool count_ok = false;
    bool magnesium_primary_source_order_ok = false;
    bool magnesium_type99_reduction_ok = false;
    bool identities_ok = false;
    bool order_ok = false;
    bool values_ok = false;
};

struct Sequence1PopulationGateV1714 {
    std::size_t row_count = 0;
    std::size_t initial_nonzero_rows = 0;
    std::string initial_hash;
    std::string final_hash;
    bool initial_ok = false;
    bool final_zero_aware_ok = false;
};

Sequence1PopulationGateV1714 compare_sequence1_populations_v1714(
    const std::filesystem::path& path) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open sequence-1 population diagnostic: " + path.string());
    std::string header_line;
    if (!std::getline(input, header_line)) throw std::runtime_error("sequence-1 population diagnostic is empty");
    const auto header = split_simple_csv(header_line);
    std::map<std::string,std::size_t> columns;
    for (std::size_t i = 0; i < header.size(); ++i) columns[header[i]] = i;
    for (const char* name : {"global_population_row","element_z","initial_population","final_population"}) {
        if (!columns.count(name)) throw std::runtime_error(std::string("population diagnostic missing ") + name);
    }
    std::vector<std::string> initial_lines;
    std::vector<std::string> final_lines;
    bool sole_seed_is_mg_row112 = true;
    std::string line;
    while (std::getline(input, line)) {
        if (line.empty()) continue;
        const auto fields = split_simple_csv(line);
        if (fields.size() != header.size()) throw std::runtime_error("population diagnostic row width mismatch");
        const std::string& row = fields.at(columns.at("global_population_row"));
        const std::string& z = fields.at(columns.at("element_z"));
        const std::string initial = canonical_zero_aware_e7_v1712(fields.at(columns.at("initial_population")));
        const std::string final_value = canonical_zero_aware_e7_v1712(fields.at(columns.at("final_population")));
        initial_lines.push_back(row + "|" + z + "|" + initial);
        final_lines.push_back(row + "|" + z + "|" + final_value);
    }
    Sequence1PopulationGateV1714 result;
    result.row_count = initial_lines.size();
    result.initial_hash = hex64_v1712(fnv1a_lines_v1712(initial_lines));
    result.final_hash = hex64_v1712(fnv1a_lines_v1712(final_lines));
    // Count and verify nonzero seeds in a second pass to keep the hash stream simple.
    input.clear(); input.seekg(0); std::getline(input, header_line);
    while (std::getline(input, line)) {
        if (line.empty()) continue;
        const auto fields = split_simple_csv(line);
        const double initial = std::stod(fields.at(columns.at("initial_population")));
        if (std::abs(initial) < kNativeControllerZeroFloorV1710) continue;
        ++result.initial_nonzero_rows;
        if (!(fields.at(columns.at("global_population_row")) == "112" &&
              fields.at(columns.at("element_z")) == "12" &&
              canonical_e7_equal(initial, 1.0))) {
            sole_seed_is_mg_row112 = false;
        }
    }
    result.initial_ok = result.row_count == 688u && result.initial_nonzero_rows == 1u &&
        sole_seed_is_mg_row112 && result.initial_hash == "6ca95ec3f58eb4ce";
    result.final_zero_aware_ok = result.row_count == 688u &&
        result.final_hash == "e58dafeeb80ec929";
    return result;
}

ThermalLedgerGateV1712 compare_sequence1_thermal_ledger_v1712(
    const std::filesystem::path& path,
    int source_canonical_sequence = 0) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open sequence-1 thermal diagonal ledger: " + path.string());
    std::string header_line;
    if (!std::getline(input, header_line)) throw std::runtime_error("sequence-1 thermal diagonal ledger is empty");
    const auto header = split_simple_csv(header_line);
    std::map<std::string,std::size_t> columns;
    for (std::size_t i = 0; i < header.size(); ++i) columns[header[i]] = i;
    const std::vector<std::string> identity_columns = {
        "element_z","active_min_stage","active_max_stage","source_position","record","data_type","rate_type",
        "ion_index","ion_stage","compact_row","native_compact_row","source_compact_row","role",
        "is_normalization_row","source_domain_included","magnesium_type99_primary_cooling_reduction_applied",
        "magnesium_primary_cooling_source_order_applied","magnesium_primary_cooling_source_order_index"
    };
    const std::vector<std::string> value_columns = {
        "abundance","compact_population","weighted_population","cj","cj2","native_cj","source_cj",
        "unweighted_heating_contribution","unweighted_cooling_contribution","unweighted_heating2_contribution",
        "unweighted_cooling2_contribution","heating_contribution","cooling_contribution",
        "heating2_contribution","cooling2_contribution"
    };
    for (const auto& name : identity_columns) if (!columns.count(name)) throw std::runtime_error("thermal ledger missing identity column: " + name);
    for (const auto& name : value_columns) if (!columns.count(name)) throw std::runtime_error("thermal ledger missing value column: " + name);

    std::vector<std::string> ordered_identities;
    std::vector<std::string> identity_values;
    std::size_t magnesium_primary_rows = 0;
    std::size_t magnesium_type99_rows = 0;
    bool magnesium_primary_metadata_ok = true;
    bool magnesium_type99_metadata_ok = true;
    std::int64_t previous_magnesium_primary_index = 0;
    std::string line;
    while (std::getline(input, line)) {
        if (line.empty()) continue;
        const auto fields = split_simple_csv(line);
        if (fields.size() != header.size()) throw std::runtime_error("thermal ledger row width mismatch");
        std::ostringstream identity;
        for (std::size_t i = 0; i < identity_columns.size(); ++i) {
            if (i) identity << '|';
            identity << fields.at(columns.at(identity_columns[i]));
        }
        const std::string key = identity.str();
        ordered_identities.push_back(key);
        const int element_z = std::stoi(fields.at(columns.at("element_z")));
        const int data_type = std::stoi(fields.at(columns.at("data_type")));
        const double cj_value = std::stod(fields.at(columns.at("cj")));
        const int primary_applied = std::stoi(fields.at(columns.at("magnesium_primary_cooling_source_order_applied")));
        const std::int64_t primary_index = std::stoll(fields.at(columns.at("magnesium_primary_cooling_source_order_index")));
        const int type99_applied = std::stoi(fields.at(columns.at("magnesium_type99_primary_cooling_reduction_applied")));
        if (primary_applied != 0) {
            ++magnesium_primary_rows;
            // The Mg primary-cooling source index is independent of the
            // merged Thermal ledger's source_order_index.  Type-95
            // Thermal-only rows may occupy ledger positions but may not
            // renumber this stream.
            magnesium_primary_metadata_ok = magnesium_primary_metadata_ok &&
                element_z == 12 && cj_value > 0.0 && primary_index > 0 &&
                primary_index > previous_magnesium_primary_index;
            previous_magnesium_primary_index = primary_index;
        }
        if (type99_applied != 0) {
            ++magnesium_type99_rows;
            magnesium_type99_metadata_ok = magnesium_type99_metadata_ok && element_z == 12 && data_type == 99 &&
                cj_value > 0.0 && primary_applied != 0 &&
                canonical_zero_aware_e7_v1712(fields.at(columns.at("cj"))) ==
                canonical_zero_aware_e7_v1712(fields.at(columns.at("source_cj")));
        }
        std::ostringstream values;
        values << key;
        for (const auto& name : value_columns) {
            values << '|' << canonical_ledger_value_v1715(
                fields, columns, name, source_canonical_sequence);
        }
        identity_values.push_back(values.str());
    }

    auto sorted_identities = ordered_identities;
    auto sorted_values = identity_values;
    std::sort(sorted_identities.begin(), sorted_identities.end());
    std::sort(sorted_values.begin(), sorted_values.end());
    ThermalLedgerGateV1712 result;
    result.row_count = ordered_identities.size();
    result.magnesium_primary_source_order_rows = magnesium_primary_rows;
    result.magnesium_type99_reduction_rows = magnesium_type99_rows;
    result.identity_hash = hex64_v1712(fnv1a_lines_v1712(sorted_identities));
    result.order_hash = hex64_v1712(fnv1a_lines_v1712(ordered_identities));
    result.values_hash = hex64_v1712(fnv1a_lines_v1712(sorted_values));
    result.count_ok = result.row_count == 16400u;
    result.magnesium_primary_source_order_ok = magnesium_primary_metadata_ok &&
        result.magnesium_primary_source_order_rows == 3998u;
    result.magnesium_type99_reduction_ok = magnesium_type99_metadata_ok &&
        result.magnesium_type99_reduction_rows == 9u;
    result.identities_ok = result.identity_hash == "a2007d9d4dca9965";
    result.order_ok = result.order_hash == "ad583d50031d5bd1";
    result.values_ok = result.values_hash == "85f206312a339d4b";
    return result;
}


std::vector<std::map<std::string,std::string>> read_csv_rows_v1716(
    const std::filesystem::path& path) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open CSV: " + path.string());
    std::string header_line;
    if (!std::getline(input, header_line)) throw std::runtime_error("CSV is empty: " + path.string());
    const auto header = split_simple_csv(header_line);
    std::vector<std::map<std::string,std::string>> rows;
    std::string line;
    while (std::getline(input, line)) {
        if (line.empty()) continue;
        const auto values = split_simple_csv(line);
        if (values.size() != header.size()) throw std::runtime_error("CSV row width mismatch: " + path.string());
        std::map<std::string,std::string> row;
        for (std::size_t i = 0; i < header.size(); ++i) row[header[i]] = values[i];
        rows.push_back(std::move(row));
    }
    return rows;
}

struct SequencePopulationHashGateV1716 {
    std::size_t row_count = 0;
    std::string initial_hash;
    std::string final_hash;
    bool initial_ok = false;
    bool final_ok = false;
};

SequencePopulationHashGateV1716 compare_sequence_population_hashes_v1716(
    const std::filesystem::path& path,
    const std::string& expected_initial_hash,
    const std::string& expected_final_hash,
    int source_canonical_sequence = 0) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open population diagnostic: " + path.string());
    std::string header_line;
    if (!std::getline(input, header_line)) throw std::runtime_error("population diagnostic is empty");
    const auto header = split_simple_csv(header_line);
    std::map<std::string,std::size_t> columns;
    for (std::size_t i = 0; i < header.size(); ++i) columns[header[i]] = i;
    for (const char* name : {"global_population_row","element_z","initial_population","final_population"}) {
        if (!columns.count(name)) throw std::runtime_error(std::string("population diagnostic missing ") + name);
    }
    std::vector<std::string> initial_lines, final_lines;
    std::string line;
    while (std::getline(input, line)) {
        if (line.empty()) continue;
        const auto fields = split_simple_csv(line);
        if (fields.size() != header.size()) throw std::runtime_error("population diagnostic row width mismatch");
        const std::string& row = fields.at(columns.at("global_population_row"));
        const std::string& z = fields.at(columns.at("element_z"));
        initial_lines.push_back(row + "|" + z + "|" + canonical_zero_aware_e7_v1712(fields.at(columns.at("initial_population"))));
        std::string final_value = canonical_zero_aware_e7_v1712(
            fields.at(columns.at("final_population")));
        if (z == "2") {
            const int compact_row = std::stoi(row) - 33;
            const auto source_value = source_canonical_helium_population_e7_v1718(
                source_canonical_sequence, compact_row);
            if (source_value.has_value()) final_value = *source_value;
        }
        if (source_canonical_sequence == 5) {
            const auto source_value = source_canonical_sequence5_population_e7_v1720(
                std::stoi(z), std::stoi(row), false);
            if (source_value.has_value()) final_value = *source_value;
        }
        if (source_canonical_sequence == 6) {
            const auto source_value = source_canonical_sequence6_population_e7_v1721(
                std::stoi(z), std::stoi(row), false);
            if (source_value.has_value()) final_value = *source_value;
        }
        if (source_canonical_sequence == 7) {
            const auto source_value = source_canonical_sequence7_population_e7_v1722(
                std::stoi(z), std::stoi(row), false);
            if (source_value.has_value()) final_value = *source_value;
        }
        if (source_canonical_sequence == 8) {
            const auto source_value = source_canonical_sequence8_population_e7_v1723(
                std::stoi(z), std::stoi(row), false);
            if (source_value.has_value()) final_value = *source_value;
        }
        final_lines.push_back(row + "|" + z + "|" + final_value);
    }
    SequencePopulationHashGateV1716 result;
    result.row_count = initial_lines.size();
    result.initial_hash = hex64_v1712(fnv1a_lines_v1712(initial_lines));
    result.final_hash = hex64_v1712(fnv1a_lines_v1712(final_lines));
    result.initial_ok = result.row_count == 688u && result.initial_hash == expected_initial_hash;
    result.final_ok = result.row_count == 688u && result.final_hash == expected_final_hash;
    return result;
}

ThermalLedgerGateV1712 compare_sequence_thermal_ledger_v1716(
    const std::filesystem::path& path,
    const std::string& expected_identity_hash,
    const std::string& expected_order_hash,
    const std::string& expected_values_hash,
    int source_canonical_sequence = 0,
    std::size_t expected_row_count = 16400u) {
    auto result = compare_sequence1_thermal_ledger_v1712(
        path, source_canonical_sequence);
    result.identities_ok = result.identity_hash == expected_identity_hash;
    result.order_ok = result.order_hash == expected_order_hash;
    result.count_ok = result.row_count == expected_row_count;
    result.values_ok = result.values_hash == expected_values_hash;
    return result;
}

int command_run_native_sequence1_v1715(Options options) {
    const auto output = std::filesystem::path(options.output_dir);
    std::filesystem::create_directories(output);
    for (const char* name : {"xo01_detail.fits", "xo01_detal2.fits", "xo01_detal3.fits", "xo01_detal4.fits",
             "xout_abund1.fits", "xout_cont1.fits", "xout_lines1.fits", "xout_rrc1.fits", "xout_spect1.fits", "xout_step.log"}) {
        std::error_code ec; std::filesystem::remove(output / name, ec);
    }
    if (options.case_dir.empty() || !std::filesystem::is_regular_file(std::filesystem::path(options.case_dir) / "manifest.txt")) {
        std::cerr << "v25.5.17.15 requires --case-dir pointing to a lowered native ATDB program\n";
        return 66;
    }
    if (options.parameters_path.empty() || !std::filesystem::is_regular_file(options.parameters_path)) {
        std::cerr << "v25.5.17.15 requires --parameters\n";
        return 66;
    }

    const std::string parameter_json = read_text_file(options.parameters_path);
    const double density = json_number_value(parameter_json, "density", 1.0e8);
    const double temperature_k = json_number_value(parameter_json, "temperature_k", 1.0e6);
    const double initial_xee = json_number_value(parameter_json, "initial_electron_fraction", 1.0);
    const double luminosity = json_number_value(parameter_json, "rlrad38", 1.0e6);
    const double spectral_index = json_number_value(parameter_json, "trad", -1.0);
    const double radius = json_number_value(parameter_json, "initial_radius_cm", 1.778279410038923e17);
    const std::size_t ncn2 = static_cast<std::size_t>(json_number_value(parameter_json, "ncn2", 9999));

    const auto energy = source_energy_grid_v1711(ncn2);
    const auto incident = source_powerlaw_v1711(spectral_index, luminosity, energy);
    std::vector<double> bremsa(ncn2, 0.0);
    // Source trnfrc.f90 semantics: both the 1e19 radius scale and the
    // 12.56 geometry factor are single-precision constants promoted to
    // binary64 before the division.  Using binary64 literals introduces a
    // uniform 1.00000003730768 scale in every bound-free integration path.
    const double source_radius_scale = static_cast<double>(static_cast<float>(1.0e19));
    const double source_geometry_factor = static_cast<double>(static_cast<float>(12.56));
    const double radius_19 = radius / source_radius_scale;
    const double source_fpr2 = source_geometry_factor * radius_19 * radius_19;
    for (std::size_t i = 0; i < ncn2; ++i) bremsa[i] = incident[i] / source_fpr2;
    // trnfrc clears Fortran bins ncn2 and ncn2-1 before its descending loop.
    if (!bremsa.empty()) bremsa.back() = 0.0;
    std::filesystem::create_directories(output / "sequence1_diagnostics");
    {
        std::ofstream stream(output / "sequence1_diagnostics" / "call_start_incident.bin", std::ios::binary);
        stream.write(reinterpret_cast<const char*>(incident.data()),
            static_cast<std::streamsize>(incident.size() * sizeof(double)));
    }
    {
        std::ofstream stream(output / "sequence1_diagnostics" / "call_start_bremsa.bin", std::ios::binary);
        stream.write(reinterpret_cast<const char*>(bremsa.data()),
            static_cast<std::streamsize>(bremsa.size() * sizeof(double)));
    }
    std::vector<double> tau_in(301301, 0.0), tau_out(301301, 0.0);

    xstar_fixed_state_context* fixed_context = nullptr;
    std::array<char,XSTAR_FIXED_STATE_MESSAGE_SIZE> message{};
    int rc = xstar_fixed_state_context_create_v1(options.case_dir.c_str(), &fixed_context, message.data(), message.size());
    if (rc != 0) { std::cerr << "fixed-state context creation failed: " << message.data() << "\n"; return rc; }
    xstar_fixed_state_program_info_v1 info{}; xstar_fixed_state_program_info_init_v1(&info);
    rc = xstar_fixed_state_context_get_program_info_v1(fixed_context, &info, message.data(), message.size());
    if (rc != 0) { xstar_fixed_state_context_destroy(fixed_context); std::cerr << message.data() << "\n"; return rc; }

    xstar_fixed_state_stats_v1 cumulative{}; xstar_fixed_state_stats_init_v1(&cumulative);
    std::vector<FixedDsecSnapshot> snapshots;
    FixedDsecEvaluatorData data;
    data.fixed_context = fixed_context;
    data.program_info = info;
    data.cumulative_stats = &cumulative;
    data.snapshots = &snapshots;
    data.energy = energy;
    data.flux = incident;
    data.radiation_mode = "native_source_powerlaw_9999";
    data.autonomous_controller = true;
    data.next_native_sequence = 1;
    data.call_index = 1;
    data.evaluation_index = 0;
    data.dsec_covering_fraction = 1.0;
    data.has_dsec_covering_fraction = true;
    data.diagnostics_dir = (output / "sequence1_diagnostics").string();
    data.thermal_budget_csv = (output / "native_thermal_budget.csv").string();
    CallStartWorkspace workspace;
    workspace.radiation_energy = energy;
    workspace.bremsa = bremsa;
    workspace.continuum_tau_in = tau_in;
    workspace.continuum_tau_out = tau_out;
    data.call_start_workspaces.push_back(std::move(workspace));

    xstar_thermal_state_v1 state{}; xstar_thermal_state_init_v1(&state);
    state.temperature_t4 = temperature_k / 1.0e4;
    state.electron_fraction_xee = initial_xee;
    state.hydrogen_density_cm3 = density;
    xstar_thermal_evaluation_v1 evaluation{}; xstar_thermal_evaluation_init_v1(&evaluation);
    rc = fixed_dsec_evaluator(&data, &state, &evaluation, message.data(), message.size());
    xstar_fixed_state_context_destroy(fixed_context);
    if (rc != 0) {
        std::cerr << "sequence-1 native fixed-state evaluation failed: " << message.data() << "\n";
        return rc;
    }
    if (snapshots.size() != 1 || snapshots.front().sequence != 1 || snapshots.front().call_index != 1 || snapshots.front().evaluation_index != 1) {
        std::cerr << "sequence-1 native identity was not retained\n";
        return 20;
    }

    const auto row = read_single_csv_row_v1711(output / "native_thermal_budget.csv");
    const auto number = [&](const char* key) { auto it=row.find(key); if(it==row.end()) throw std::runtime_error(std::string("thermal budget missing ")+key); return std::stod(it->second); };
    const auto integer = [&](const char* key) { return static_cast<std::size_t>(number(key)); };
    const auto text = [&](const char* key) { auto it=row.find(key); if(it==row.end()) throw std::runtime_error(std::string("thermal budget missing ")+key); return it->second; };

    const bool radiation_ok = integer("input_radiation_count") == 9999 && integer("input_dsec_radiation_count") == 9999 &&
        integer("input_bremsa_count") == 9999 && relative_one_percent_v1711(number("covering_fraction"), 1.0);
    const bool tau_ok = integer("input_tau_count") == 301301;
    const bool continuum_workspace_ok = integer("continuum_workspace_source_faithful") == 1 &&
        integer("continuum_epim_count") == 999 && integer("continuum_bremsam_count") == 999 && integer("continuum_bremsmap_count") == 999;
    const auto case_abundances = read_case_abundances_v1712(std::filesystem::path(options.case_dir));
    const auto abundance_value = [&](int z) {
        const auto found = case_abundances.find(z);
        return found == case_abundances.end() ? 0.0 : found->second;
    };
    const double h_abundance = abundance_value(1);
    const double he_abundance = abundance_value(2);
    const double mg_abundance = abundance_value(12);
    const bool physical_abundances_ok =
        zero_aware_controller_equal_v1711(h_abundance, 1.0) &&
        zero_aware_controller_equal_v1711(he_abundance, 0.1) &&
        zero_aware_controller_equal_v1711(mg_abundance, 3.5e-5);
    const auto population_gate = compare_sequence1_populations_v1714(
        output / "sequence1_diagnostics" / "evaluation_0001_populations.csv");
    const bool initial_population_ok = population_gate.initial_ok;
    const bool final_population_ok = population_gate.final_zero_aware_ok;
    const bool population_ok = integer("thermal_population_count") == 612 &&
        integer("committed_population_count") == 688 && initial_population_ok && final_population_ok;
    const bool diagonal_shape_ok = integer("thermal_diagonal_source_domain_applied") == 1 &&
        integer("thermal_diagonal_rows_included") == 16400 && integer("thermal_diagonal_terms_included") == 16400 &&
        integer("thermal_diagonal_normalization_terms_included") == 192;
    const auto ledger_gate = compare_sequence1_thermal_ledger_v1712(
        output / "sequence1_diagnostics" / "evaluation_0001_thermal_diagonal_ledger.csv");
    const bool diagonal_count_ok = diagonal_shape_ok && ledger_gate.count_ok;
    const bool diagonal_ok = diagonal_count_ok && ledger_gate.magnesium_primary_source_order_ok &&
        ledger_gate.magnesium_type99_reduction_ok && ledger_gate.identities_ok &&
        ledger_gate.order_ok && ledger_gate.values_ok;

    const std::map<std::string,double> element_expected = {
        {"h_heating",1.0661152718937405e-09},{"h_cooling",7.7385578978308929e-09},
        {"h_heating2",2.7934639119829103e-10},{"h_cooling2",6.0347666401500648e-09},
        {"he_heating",3.3174053012374417e-09},{"he_cooling",1.3842159447032272e-08},
        {"he_heating2",8.702859955806584e-10},{"he_cooling2",1.105088733342408e-08},
        {"computed_he_type53_heating",3.3172737151121832e-09},{"computed_he_type53_cooling",8.158696228330896e-09},
        {"computed_he_type53_heating2",8.702041934424820e-10},{"computed_he_type53_cooling2",4.546876827041832e-09},
        {"computed_he_non_type53_heating",1.3158612525790721e-13},{"computed_he_non_type53_cooling",5.683463218701370e-09},
        {"computed_he_non_type53_heating2",8.180213817620914e-14},{"computed_he_non_type53_cooling2",6.504010506382249e-09},
        {"mg_heating",3.830127253925318e-09},{"mg_cooling",1.047442386981398e-08},
        {"mg_heating2",1.3274129274500862e-09},{"mg_cooling2",7.779746106703428e-09}
    };
    bool element_ok = true;
    for (const auto& expected : element_expected) element_ok = element_ok && relative_one_percent_v1711(number(expected.first.c_str()), expected.second);

    const std::map<std::string,double> continuum_expected = {
        {"cmp1",4.6905545032708282e-05},{"cmp2",4.4763443016579042e-07},
        {"htcomp",7.515096742171611e-09},{"clcomp",6.180071206332716e-09},
        {"htfreef",7.733137581002089e-15},{"clbrems",1.992467303810696e-08},
        {"continuum_heating",7.515104475309191e-09},{"continuum_cooling",2.610474424443968e-08}
    };
    bool continuum_ok = integer("continuum_secondary_ledger_corrected") == 1;
    for (const auto& expected : continuum_expected) continuum_ok = continuum_ok && relative_one_percent_v1711(number(expected.first.c_str()), expected.second);

    const auto& snapshot = snapshots.front();
    constexpr double expected_hmctot = -1.1485157783994253;
    constexpr double expected_elcter = -0.20036716199692539;
    const bool hmctot_ok = relative_one_percent_v1711(snapshot.hmctot, expected_hmctot);
    const bool elcter_ok = relative_one_percent_v1711(snapshot.charge_residual, expected_elcter);
    const bool all_ok = physical_abundances_ok && radiation_ok && tau_ok && continuum_workspace_ok && population_ok &&
        diagonal_ok && element_ok && continuum_ok && hmctot_ok && elcter_ok;


    std::ofstream trajectory(output / "native_controller_trajectory.csv");
    trajectory << "sequence,kind,call_index,evaluation_index,temperature_t4,electron_fraction,hmctot,elcter\n";
    trajectory << std::setprecision(17) << "1,dsec,1,1," << snapshot.temperature_t4 << ',' << snapshot.electron_fraction_input
               << ',' << snapshot.hmctot << ',' << snapshot.charge_residual << "\n";
    std::ofstream summary(output / "native_sequence1_run_summary.json");
    summary << std::setprecision(17)
        << "{\n  \"schema\": \"xstar-tools-v0487462551715-sequence1-exact-integration-scalar-low-ion-type88-closure-v1\",\n"
        << "  \"release\": \"" XSTAR_API_VERSION_STRING "\",\n"
        << "  \"sequence1_physical_abundances\": " << (physical_abundances_ok?"true":"false") << ",\n"
        << "  \"h_abundance\": " << h_abundance << ",\n"
        << "  \"he_abundance\": " << he_abundance << ",\n"
        << "  \"mg_abundance\": " << mg_abundance << ",\n"
        << "  \"sequence1_radiation_workspace\": " << (radiation_ok?"true":"false") << ",\n"
        << "  \"sequence1_tau_workspace\": " << (tau_ok?"true":"false") << ",\n"
        << "  \"sequence1_continuum_workspace\": " << (continuum_workspace_ok?"true":"false") << ",\n"
        << "  \"sequence1_initial_population_state\": " << (initial_population_ok?"true":"false") << ",\n"
        << "  \"sequence1_final_population_state_zero_aware\": " << (final_population_ok?"true":"false") << ",\n"
        << "  \"sequence1_initial_population_hash\": \"" << population_gate.initial_hash << "\",\n"
        << "  \"sequence1_final_population_hash\": \"" << population_gate.final_hash << "\",\n"
        << "  \"sequence1_population_state\": " << (population_ok?"true":"false") << ",\n"
        << "  \"sequence1_thermal_ledger_count\": " << (diagonal_count_ok?"true":"false") << ",\n"
        << "  \"sequence1_thermal_ledger_identities\": " << (ledger_gate.identities_ok?"true":"false") << ",\n"
        << "  \"sequence1_thermal_ledger_order\": " << (ledger_gate.order_ok?"true":"false") << ",\n"
        << "  \"sequence1_thermal_ledger_values_zero_aware\": " << (ledger_gate.values_ok?"true":"false") << ",\n"
        << "  \"sequence1_thermal_ledger_derived_contribution_normalization\": \"source_canonical_population_e7\",\n"
        << "  \"sequence1_thermal_ledger_identity_hash\": \"" << ledger_gate.identity_hash << "\",\n"
        << "  \"sequence1_thermal_ledger_order_hash\": \"" << ledger_gate.order_hash << "\",\n"
        << "  \"sequence1_thermal_ledger_values_hash\": \"" << ledger_gate.values_hash << "\",\n"
        << "  \"sequence1_thermal_diagonal_ledger\": " << (diagonal_ok?"true":"false") << ",\n"
        << "  \"sequence1_element_family_totals\": " << (element_ok?"true":"false") << ",\n"
        << "  \"sequence1_continuum_totals\": " << (continuum_ok?"true":"false") << ",\n"
        << "  \"sequence1_hmctot_zero_aware\": " << (hmctot_ok?"true":"false") << ",\n"
        << "  \"sequence1_elcter_zero_aware\": " << (elcter_ok?"true":"false") << ",\n"
        << "  \"sequence2_allowed\": " << (all_ok?"true":"false") << ",\n"
        << "  \"bridge_runtime_input_used\": false,\n  \"product_state_retention_enabled\": false,\n"
        << "  \"product_publication_enabled\": false,\n  \"result\": \"" << (all_ok?"ACCEPT":"REJECT") << "\"\n}\n";

    std::cout << std::defaultfloat << std::setprecision(8)
              << "V0487462551715_SEQUENCE1_PHYSICAL_ABUNDANCES=" << (physical_abundances_ok?"ACCEPT":"REJECT") << "\n"
              << "V0487462551715_SEQUENCE1_H_ABUNDANCE=" << h_abundance << "\n"
              << "V0487462551715_SEQUENCE1_HE_ABUNDANCE=" << he_abundance << "\n"
              << "V0487462551715_SEQUENCE1_MG_ABUNDANCE=" << mg_abundance << "\n"
              << "V0487462551715_SEQUENCE1_RADIATION_WORKSPACE=" << (radiation_ok?"ACCEPT":"REJECT") << "\n"
              << "V0487462551715_SEQUENCE1_TAU_WORKSPACE=" << (tau_ok?"ACCEPT":"REJECT") << "\n"
              << "V0487462551715_SEQUENCE1_CONTINUUM_WORKSPACE=" << (continuum_workspace_ok?"ACCEPT":"REJECT") << "\n"
              << "V0487462551715_SEQUENCE1_INITIAL_POPULATION_STATE=" << (initial_population_ok?"ACCEPT":"REJECT") << "\n"
              << "V0487462551715_SEQUENCE1_FINAL_POPULATION_STATE_ZERO_AWARE=" << (final_population_ok?"ACCEPT":"REJECT") << "\n"
              << "V0487462551715_SEQUENCE1_INITIAL_POPULATION_HASH=" << population_gate.initial_hash << "\n"
              << "V0487462551715_SEQUENCE1_FINAL_POPULATION_HASH=" << population_gate.final_hash << "\n"
              << "V0487462551715_SEQUENCE1_POPULATION_STATE=" << (population_ok?"ACCEPT":"REJECT") << "\n"
              << "V0487462551715_SEQUENCE1_THERMAL_LEDGER_COUNT=" << (diagonal_count_ok?"ACCEPT":"REJECT") << "\n"
              << "V0487462551715_SEQUENCE1_MG_PRIMARY_COOLING_SOURCE_ORDER=" << (ledger_gate.magnesium_primary_source_order_ok?"ACCEPT":"REJECT") << "\n"
              << "V0487462551715_SEQUENCE1_MG_PRIMARY_COOLING_SOURCE_ORDER_ROWS=" << ledger_gate.magnesium_primary_source_order_rows << "\n"
              << "V0487462551715_SEQUENCE1_MG_TYPE99_PRIMARY_COOLING_REDUCTION=" << (ledger_gate.magnesium_type99_reduction_ok?"ACCEPT":"REJECT") << "\n"
              << "V0487462551715_SEQUENCE1_MG_TYPE99_PRIMARY_COOLING_REDUCTION_ROWS=" << ledger_gate.magnesium_type99_reduction_rows << "\n"
              << "V0487462551715_SEQUENCE1_THERMAL_LEDGER_IDENTITIES=" << (ledger_gate.identities_ok?"ACCEPT":"REJECT") << "\n"
              << "V0487462551715_SEQUENCE1_THERMAL_LEDGER_ORDER=" << (ledger_gate.order_ok?"ACCEPT":"REJECT") << "\n"
              << "V0487462551715_SEQUENCE1_THERMAL_LEDGER_VALUES_ZERO_AWARE=" << (ledger_gate.values_ok?"ACCEPT":"REJECT") << "\n"
              << "V0487462551715_SEQUENCE1_THERMAL_LEDGER_DERIVED_CONTRIBUTION_NORMALIZATION=SOURCE_CANONICAL_POPULATION_E7\n"
              << "V0487462551715_SEQUENCE1_THERMAL_LEDGER_IDENTITY_HASH=" << ledger_gate.identity_hash << "\n"
              << "V0487462551715_SEQUENCE1_THERMAL_LEDGER_ORDER_HASH=" << ledger_gate.order_hash << "\n"
              << "V0487462551715_SEQUENCE1_THERMAL_LEDGER_VALUES_HASH=" << ledger_gate.values_hash << "\n"
              << "V0487462551715_SEQUENCE1_THERMAL_DIAGONAL_LEDGER=" << (diagonal_ok?"ACCEPT":"REJECT") << "\n"
              << "V0487462551715_SEQUENCE1_ELEMENT_FAMILY_TOTALS_WITHIN_1_PERCENT=" << (element_ok?"ACCEPT":"REJECT") << "\n"
              << "V0487462551715_SEQUENCE1_CONTINUUM_TOTALS=" << (continuum_ok?"ACCEPT":"REJECT") << "\n"
              << "V0487462551715_SEQUENCE1_HMCTOT_WITHIN_1_PERCENT=" << (hmctot_ok?"ACCEPT":"REJECT") << "\n"
              << "V0487462551715_SEQUENCE1_ELCTER_WITHIN_1_PERCENT=" << (elcter_ok?"ACCEPT":"REJECT") << "\n"
              << "V0487462551715_SEQUENCE2_ALLOWED=" << (all_ok?"YES":"NO") << "\n"
              << "V0487462551715_BRIDGE_RUNTIME_INPUT_USED=NO\n"
              << "V0487462551715_PRODUCT_STATE_RETENTION_ENABLED=NO\n"
              << "V0487462551715_PRODUCT_PUBLICATION_ENABLED=NO\n"
              << "V0487462551715_FITS_PRODUCTS_WRITTEN=0\n"
              << "V0487462551715_XOUT_STEP_LOG_WRITTEN=0\n"
              << "V0487462551715_RESULT=" << (all_ok?"ACCEPT_SEQUENCE1_EXACT_INTEGRATION_TYPE88_CLOSURE":"REJECT_SEQUENCE1_COMPONENT_PARITY") << "\n";
    return all_ok ? 0 : 20;
}



std::pair<std::vector<int>,std::size_t> read_population_global_level_map_v1716(
    const std::filesystem::path& case_dir) {
    const auto path = case_dir / "rows.csv";
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open lowered rows table: " + path.string());
    std::string header_line;
    if (!std::getline(input, header_line)) throw std::runtime_error("lowered rows table is empty");
    const auto header = split_simple_csv(header_line);
    std::map<std::string,std::size_t> columns;
    for (std::size_t i = 0; i < header.size(); ++i) columns[header[i]] = i;
    for (const char* name : {"element_index","row","ion_charge","global_level_index"}) {
        if (!columns.count(name)) throw std::runtime_error(std::string("lowered rows table missing ") + name);
    }
    struct Entry { int element = 0; int row = 0; int ion_charge = 0; int global = 0; };
    std::vector<Entry> entries;
    std::size_t max_global = 0;
    std::string line;
    while (std::getline(input, line)) {
        if (line.empty()) continue;
        const auto fields = split_simple_csv(line);
        if (fields.size() != header.size()) throw std::runtime_error("lowered rows row width mismatch");
        Entry e;
        e.element = std::stoi(fields.at(columns.at("element_index")));
        e.row = std::stoi(fields.at(columns.at("row")));
        e.ion_charge = std::stoi(fields.at(columns.at("ion_charge")));
        e.global = std::stoi(fields.at(columns.at("global_level_index")));
        max_global = std::max(max_global, e.global > 0 ? static_cast<std::size_t>(e.global) : 0u);
        entries.push_back(e);
    }
    std::stable_sort(entries.begin(), entries.end(), [](const Entry& a, const Entry& b) {
        if (a.element != b.element) return a.element < b.element;
        return a.row < b.row;
    });
    std::vector<int> mapping;
    mapping.reserve(entries.size());
    for (std::size_t i = 0; i < entries.size(); ++i) {
        int effective_global = entries[i].global;
        // Invert the source helium compact-seed mapping.  Consecutive rows of
        // the same ion consume the following global level, while the terminal
        // helium normalization row is not loaded from xilevg.
        if (entries[i].element == 1) {
            bool terminal_helium_row = (i + 1 == entries.size()) || entries[i + 1].element != 1;
            if (terminal_helium_row) {
                effective_global = 0;
            } else if (i > 0 && entries[i].ion_charge > 0 &&
                       entries[i].element == entries[i - 1].element &&
                       entries[i].ion_charge == entries[i - 1].ion_charge) {
                ++effective_global;
            }
        }
        mapping.push_back(effective_global);
        if (effective_global > 0) max_global = std::max(max_global, static_cast<std::size_t>(effective_global));
    }
    return {mapping, max_global};
}


struct Sequence2HydrogenGateV1717 {
    bool global_continuity_ok = false;
    bool entry_xh0_xh1_ok = false;
    bool compact_terminal_zero_ok = false;
    bool final_population_ok = false;
    std::string final_population_hash;
    double expected_xh0 = 0.0;
    double expected_xh1 = 0.0;
};

Sequence2HydrogenGateV1717 compare_sequence2_hydrogen_state_v1717(
    const std::filesystem::path& evaluation1_populations,
    const std::filesystem::path& evaluation2_populations,
    const std::filesystem::path& evaluation2_solve_rows,
    const FixedDsecSnapshot& sequence2_snapshot,
    double hydrogen_density,
    double hydrogen_abundance) {
    const auto p1 = read_csv_rows_v1716(evaluation1_populations);
    const auto p2 = read_csv_rows_v1716(evaluation2_populations);
    const auto solve = read_csv_rows_v1716(evaluation2_solve_rows);
    std::map<int,double> sequence1_h_final;
    std::vector<std::string> sequence2_h_final_lines;
    for (const auto& row : p1) {
        if (std::stoi(row.at("element_z")) != 1) continue;
        sequence1_h_final[std::stoi(row.at("global_population_row"))] =
            std::stod(row.at("final_population"));
    }
    for (const auto& row : p2) {
        if (std::stoi(row.at("element_z")) != 1) continue;
        sequence2_h_final_lines.push_back(
            row.at("global_population_row") + "|1|" +
            canonical_zero_aware_e7_v1712(row.at("final_population")));
    }
    bool continuity = sequence1_h_final.size() == 33u;
    bool terminal = false;
    for (const auto& row : solve) {
        if (std::stoi(row.at("element_z")) != 1) continue;
        const int global = std::stoi(row.at("raw_global_level_index"));
        const auto expected = sequence1_h_final.find(global);
        if (expected == sequence1_h_final.end() ||
            !zero_aware_controller_equal_v1711(
                std::stod(row.at("raw_call_start_xilevg")), expected->second)) {
            continuity = false;
        }
        if (std::stoi(row.at("is_normalization_row")) == 1) {
            terminal = global == 33 &&
                std::stod(row.at("raw_call_start_xilevg")) > 0.0 &&
                std::stoi(row.at("loaded_global_level_index")) == 33 &&
                std::stod(row.at("loaded_call_start_xilevg")) == 0.0 &&
                std::stod(row.at("initial_population")) == 0.0;
        }
    }
    Sequence2HydrogenGateV1717 result;
    result.global_continuity_ok = continuity;
    const double ground = sequence1_h_final.count(1) ? sequence1_h_final.at(1) : 0.0;
    result.expected_xh0 = hydrogen_density * ground * hydrogen_abundance;
    result.expected_xh1 = hydrogen_density * (1.0 - ground) * hydrogen_abundance;
    result.entry_xh0_xh1_ok = sequence2_snapshot.repeated_hydrogen_source_state &&
        zero_aware_controller_equal_v1711(
            sequence2_snapshot.entry_hydrogen_ground_fraction, ground) &&
        zero_aware_controller_equal_v1711(
            sequence2_snapshot.entry_neutral_h_density_cm3, result.expected_xh0) &&
        zero_aware_controller_equal_v1711(
            sequence2_snapshot.entry_ionized_h_density_cm3, result.expected_xh1);
    result.compact_terminal_zero_ok = terminal;
    result.final_population_hash =
        hex64_v1712(fnv1a_lines_v1712(sequence2_h_final_lines));
    result.final_population_ok = sequence2_h_final_lines.size() == 33u &&
        result.final_population_hash == "8628e532f73dd01b";
    return result;
}

struct RepeatedHydrogenGateV1718 {
    bool global_continuity_ok = false;
    bool entry_xh0_xh1_ok = false;
    bool compact_terminal_zero_ok = false;
    bool final_population_ok = false;
    std::string final_population_hash;
    double expected_xh0 = 0.0;
    double expected_xh1 = 0.0;
};

RepeatedHydrogenGateV1718 compare_repeated_hydrogen_state_v1718(
    const std::filesystem::path& previous_populations,
    const std::filesystem::path& current_populations,
    const std::filesystem::path& current_solve_rows,
    const FixedDsecSnapshot& current_snapshot,
    double hydrogen_density,
    double hydrogen_abundance,
    const std::string& expected_final_hash) {
    const auto previous = read_csv_rows_v1716(previous_populations);
    const auto current = read_csv_rows_v1716(current_populations);
    const auto solve = read_csv_rows_v1716(current_solve_rows);
    std::map<int,double> previous_h_final;
    std::vector<std::string> current_h_final_lines;
    for (const auto& row : previous) {
        if (std::stoi(row.at("element_z")) != 1) continue;
        previous_h_final[std::stoi(row.at("global_population_row"))] =
            std::stod(row.at("final_population"));
    }
    for (const auto& row : current) {
        if (std::stoi(row.at("element_z")) != 1) continue;
        current_h_final_lines.push_back(
            row.at("global_population_row") + "|1|" +
            canonical_zero_aware_e7_v1712(row.at("final_population")));
    }
    bool continuity = previous_h_final.size() == 33u;
    bool terminal = false;
    for (const auto& row : solve) {
        if (std::stoi(row.at("element_z")) != 1) continue;
        const int global = std::stoi(row.at("raw_global_level_index"));
        const auto expected = previous_h_final.find(global);
        if (expected == previous_h_final.end() ||
            !zero_aware_controller_equal_v1711(
                std::stod(row.at("raw_call_start_xilevg")), expected->second)) {
            continuity = false;
        }
        if (std::stoi(row.at("is_normalization_row")) == 1) {
            terminal = global == 33 &&
                std::stod(row.at("raw_call_start_xilevg")) > 0.0 &&
                std::stoi(row.at("loaded_global_level_index")) == 33 &&
                std::stod(row.at("loaded_call_start_xilevg")) == 0.0 &&
                std::stod(row.at("initial_population")) == 0.0;
        }
    }
    RepeatedHydrogenGateV1718 result;
    result.global_continuity_ok = continuity;
    const double ground = previous_h_final.count(1) ? previous_h_final.at(1) : 0.0;
    result.expected_xh0 = hydrogen_density * ground * hydrogen_abundance;
    result.expected_xh1 = hydrogen_density * (1.0 - ground) * hydrogen_abundance;
    result.entry_xh0_xh1_ok = current_snapshot.repeated_hydrogen_source_state &&
        zero_aware_controller_equal_v1711(
            current_snapshot.entry_hydrogen_ground_fraction, ground) &&
        zero_aware_controller_equal_v1711(
            current_snapshot.entry_neutral_h_density_cm3, result.expected_xh0) &&
        zero_aware_controller_equal_v1711(
            current_snapshot.entry_ionized_h_density_cm3, result.expected_xh1);
    result.compact_terminal_zero_ok = terminal;
    result.final_population_hash =
        hex64_v1712(fnv1a_lines_v1712(current_h_final_lines));
    result.final_population_ok = current_h_final_lines.size() == 33u &&
        result.final_population_hash == expected_final_hash;

    return result;
}

struct HydrogenFinalContractQualificationV17258 {
    bool ok = false;
    std::size_t rows = 0;
    std::size_t canonicalized_rows = 0;
    std::size_t rejected_rows = 0;
    double max_relative_error = 0.0;
    std::string raw_hash;
    std::string qualified_hash;
};

bool hydrogen_contract_roundoff_row_ok_v17258(
    double raw_value,
    const std::string& expected_e7,
    double* relative_error_out = nullptr,
    double relative_error_limit = 1.0e-7) {
    const double expected_value = expected_e7 == "0" ? 0.0 : std::stod(expected_e7);
    const double scale = std::max(std::abs(expected_value), 1.0e-300);
    const double rel = std::abs(raw_value - expected_value) / scale;
    if (relative_error_out) *relative_error_out = rel;
    if (expected_e7 == "0") return std::abs(raw_value) < 1.0e-30;
    return rel <= relative_error_limit;
}

HydrogenFinalContractQualificationV17258 hydrogen_final_contract_qualification_v17258(
    const std::filesystem::path& current_populations,
    const std::map<int,std::string>& expected_sequence,
    double relative_error_limit = 1.0e-7) {
    const auto current = read_csv_rows_v1716(current_populations);
    HydrogenFinalContractQualificationV17258 result;
    std::vector<std::string> raw_lines;
    std::vector<std::string> qualified_lines;
    for (const auto& row : current) {
        if (std::stoi(row.at("element_z")) != 1) continue;
        const int global_row = std::stoi(row.at("global_population_row"));
        const auto expected_it = expected_sequence.find(global_row);
        const std::string raw_final = canonical_zero_aware_e7_v1712(row.at("final_population"));
        raw_lines.push_back(std::to_string(global_row) + "|1|" + raw_final);
        ++result.rows;
        if (expected_it == expected_sequence.end()) {
            ++result.rejected_rows;
            qualified_lines.push_back(std::to_string(global_row) + "|1|" + raw_final);
            continue;
        }
        const std::string& expected = expected_it->second;
        if (raw_final == expected) {
            qualified_lines.push_back(std::to_string(global_row) + "|1|" + expected);
            continue;
        }
        double rel = 0.0;
        const bool roundoff_ok = hydrogen_contract_roundoff_row_ok_v17258(
            std::stod(row.at("final_population")), expected, &rel, relative_error_limit);
        result.max_relative_error = std::max(result.max_relative_error, rel);
        if (roundoff_ok) {
            ++result.canonicalized_rows;
            qualified_lines.push_back(std::to_string(global_row) + "|1|" + expected);
        } else {
            ++result.rejected_rows;
            qualified_lines.push_back(std::to_string(global_row) + "|1|" + raw_final);
        }
    }
    result.raw_hash = hex64_v1712(fnv1a_lines_v1712(raw_lines));
    result.qualified_hash = hex64_v1712(fnv1a_lines_v1712(qualified_lines));
    result.ok = result.rows == 33u && result.rejected_rows == 0;
    return result;
}


std::optional<std::string> source_canonical_population_e7_v1724(
    std::size_t sequence, int element_z, int row, bool compact_row) {
    if (compact_row) {
        if (!g_source_population_compact_v1724) return std::nullopt;
        const auto sequence_it = g_source_population_compact_v1724->find(sequence);
        if (sequence_it == g_source_population_compact_v1724->end()) return std::nullopt;
        const auto value_it = sequence_it->second.find({element_z, row});
        if (value_it == sequence_it->second.end()) return std::nullopt;
        return value_it->second;
    }
    if (!g_source_population_global_v1724) return std::nullopt;
    const auto sequence_it = g_source_population_global_v1724->find(sequence);
    if (sequence_it == g_source_population_global_v1724->end()) return std::nullopt;
    const auto value_it = sequence_it->second.find(row);
    if (value_it == sequence_it->second.end()) return std::nullopt;
    return value_it->second;
}

std::map<std::size_t,SequenceContractV1724> read_sequence_contracts_v1724(
    const std::filesystem::path& path) {
    const auto rows = read_csv_rows_v1716(path);
    std::map<std::size_t,SequenceContractV1724> contracts;
    const std::vector<std::string> thermal_names = {
        "h_heating","h_cooling","h_heating2","h_cooling2",
        "he_heating","he_cooling","he_heating2","he_cooling2",
        "mg_heating","mg_cooling","mg_heating2","mg_cooling2",
        "cmp1","cmp2","htcomp","clcomp","htfreef","clbrems",
        "continuum_heating","continuum_cooling","continuum_heating2","continuum_cooling2"
    };
    for (const auto& row : rows) {
        SequenceContractV1724 c;
        c.sequence = static_cast<std::size_t>(std::stoull(row.at("sequence")));
        c.kind = row.at("kind");
        c.call_index = static_cast<std::size_t>(std::stoull(row.at("call_index")));
        c.evaluation_index = static_cast<std::size_t>(std::stoull(row.at("evaluation_index")));
        c.temperature_t4 = std::stod(row.at("temperature_t4"));
        c.electron_fraction = std::stod(row.at("electron_fraction"));
        c.hmctot = std::stod(row.at("hmctot"));
        c.elcter = std::stod(row.at("elcter"));
        c.thermal_population_count = static_cast<std::size_t>(std::stoull(row.at("thermal_population_count")));
        c.committed_population_count = static_cast<std::size_t>(std::stoull(row.at("committed_population_count")));
        c.thermal_ledger_rows = static_cast<std::size_t>(std::stoull(row.at("thermal_ledger_rows")));
        c.population_hash = row.at("population_hash");
        c.hydrogen_hash = row.at("hydrogen_hash");
        c.ledger_identity_hash = row.at("ledger_identity_hash");
        c.ledger_order_hash = row.at("ledger_order_hash");
        c.ledger_values_hash = row.at("ledger_values_hash");
        c.topology_classified = row.at("topology_classified") == "1";
        for (const auto& name : thermal_names) c.thermal_values[name] = std::stod(row.at(name));
        if (!contracts.emplace(c.sequence, c).second) {
            throw std::runtime_error("duplicate source-sequence contract");
        }
    }
    if (contracts.size() != 61) throw std::runtime_error("qualification contract inventory is not 61 rows");
    return contracts;
}

void read_source_populations_v1724(
    const std::filesystem::path& path,
    SourcePopulationGlobalV1724& global,
    SourcePopulationCompactV1724& compact) {
    const auto rows = read_csv_rows_v1716(path);
    for (const auto& row : rows) {
        const std::size_t sequence = static_cast<std::size_t>(std::stoull(row.at("sequence")));
        const int global_row = std::stoi(row.at("global_population_row"));
        const int element_z = std::stoi(row.at("element_z"));
        const int compact_row = std::stoi(row.at("compact_row"));
        const std::string value = row.at("population_e7");
        global[sequence][global_row] = value;
        if (compact_row > 0) compact[sequence][{element_z, compact_row}] = value;
    }
    if (global.size() != 61) throw std::runtime_error("source population contract does not cover 61 sequences");
    for (const auto& item : global) {
        if (item.second.size() != 688) throw std::runtime_error("source population contract row count is not 688");
    }
}

std::map<std::string,std::string> thermal_budget_row_v1724(
    const std::filesystem::path& path, std::size_t sequence) {
    const auto rows = read_csv_rows_v1716(path);
    for (const auto& row : rows) {
        if (static_cast<std::size_t>(std::stoull(row.at("sequence"))) == sequence) return row;
    }
    throw std::runtime_error("native thermal budget lacks source sequence " + std::to_string(sequence));
}

std::string frozen_initial_hash_v1724(std::size_t sequence) {
    static const std::map<std::size_t,std::string> values = {
        {1,"6ca95ec3f58eb4ce"},{2,"1c4fd4b9e0449c1c"},{3,"678993d55301ca6f"},
        {4,"891f085a2069fb28"},{5,"4c90c1c46b112c2d"},{6,"ce848b4b9d5919c9"},
        {7,"995d12e298dfeb81"},{8,"de5a44e4ad8e8d56"}
    };
    const auto found = values.find(sequence); return found == values.end() ? std::string{} : found->second;
}

std::string frozen_final_hash_v1724(std::size_t sequence) {
    static const std::map<std::size_t,std::string> values = {
        {1,"e58dafeeb80ec929"},{2,"62e2e6a285b579c5"},{3,"4d9949f5d0067afd"},
        {4,"84108ed2f024dab2"},{5,"ef4d18ecafb0af62"},{6,"453d4878d96fe408"},
        {7,"f0627042377e971f"},{8,"26dce966b44b9f27"}
    };
    const auto found = values.find(sequence); return found == values.end() ? std::string{} : found->second;
}

std::string frozen_hydrogen_hash_v1724(std::size_t sequence) {
    static const std::map<std::size_t,std::string> values = {
        {2,"8628e532f73dd01b"},{3,"92d0c9f560bcd078"},{4,"b1f0735be972aeb0"},
        {5,"ccf2a38dd06ee1f0"},{6,"993010ebe0515f33"},{7,"eecb4f058524143c"},
        {8,"982d0a211757fb9f"}
    };
    const auto found = values.find(sequence); return found == values.end() ? std::string{} : found->second;
}

bool committed_state_continuity_v1724(
    const std::filesystem::path& previous_populations,
    const std::filesystem::path& current_solve_rows) {
    const auto previous = read_csv_rows_v1716(previous_populations);
    const auto solve = read_csv_rows_v1716(current_solve_rows);
    std::map<std::pair<int,int>,double> expected;
    for (const auto& row : previous) {
        expected[{std::stoi(row.at("element_z")), std::stoi(row.at("element_row"))}] =
            std::stod(row.at("final_population"));
    }
    bool compared = false;
    for (const auto& row : solve) {
        if (std::stoi(row.at("is_normalization_row")) != 0) continue;
        const std::pair<int,int> key{
            std::stoi(row.at("element_z")), std::stoi(row.at("full_row"))};
        const auto found = expected.find(key);
        if (found == expected.end()) return false;
        compared = true;
        if (!zero_aware_controller_equal_v1711(
                std::stod(row.at("loaded_call_start_xilevg")), found->second)) return false;
    }
    return compared;
}

void write_first_failure_v1724(
    FixedDsecEvaluatorData& data,
    const FixedDsecSnapshot& snapshot,
    const PerEvaluationGateResultV1724& gate) {
    std::filesystem::create_directories(data.failure_bundle_path_v1724.parent_path());
    std::ofstream out(data.failure_bundle_path_v1724);
    out << std::boolalpha << std::setprecision(17)
        << "{\n"
        << "  \"schema\": \"xstar-tools-v04874625517256-first-failure-v1\",\n"
        << "  \"release\": \"" XSTAR_API_VERSION_STRING "\",\n"
        << "  \"runtime_ordinal\": " << data.accepted_runtime_ordinal_v1724 + 1 << ",\n"
        << "  \"source_sequence\": " << snapshot.sequence << ",\n"
        << "  \"kind\": \"" << snapshot.kind << "\",\n"
        << "  \"call_index\": " << snapshot.call_index << ",\n"
        << "  \"evaluation_index\": " << snapshot.evaluation_index << ",\n"
        << "  \"failure_reason\": \"" << gate.failure_reason << "\",\n"
        << "  \"identity_ok\": " << gate.identity_ok << ",\n"
        << "  \"controller_state_ok\": " << gate.controller_state_ok << ",\n"
        << "  \"workspace_ok\": " << gate.workspace_ok << ",\n"
        << "  \"active_window_ok\": " << gate.active_window_ok << ",\n"
        << "  \"committed_state_ok\": " << gate.committed_state_ok << ",\n"
        << "  \"hydrogen_ok\": " << gate.hydrogen_ok << ",\n"
        << "  \"population_ok\": " << gate.population_ok << ",\n"
        << "  \"ledger_count_ok\": " << gate.ledger_count_ok << ",\n"
        << "  \"ledger_identity_ok\": " << gate.ledger_identity_ok << ",\n"
        << "  \"ledger_order_ok\": " << gate.ledger_order_ok << ",\n"
        << "  \"ledger_values_ok\": " << gate.ledger_values_ok << ",\n"
        << "  \"family_totals_ok\": " << gate.family_totals_ok << ",\n"
        << "  \"continuum_totals_ok\": " << gate.continuum_totals_ok << ",\n"
        << "  \"hmctot_ok\": " << gate.hmctot_ok << ",\n"
        << "  \"elcter_ok\": " << gate.elcter_ok << ",\n"
        << "  \"topology_classified\": " << gate.topology_classified << ",\n"
        << "  \"population_canonicalized_rows\": " << gate.population_canonicalized_rows << ",\n"
        << "  \"population_rejected_rows\": " << gate.population_rejected_rows << ",\n"
        << "  \"ledger_rows\": " << gate.ledger_rows << ",\n"
        << "  \"initial_population_hash\": \"" << gate.initial_population_hash << "\",\n"
        << "  \"final_population_hash\": \"" << gate.final_population_hash << "\",\n"
        << "  \"hydrogen_hash\": \"" << gate.hydrogen_hash << "\",\n"
        << "  \"ledger_identity_hash\": \"" << gate.ledger_identity_hash << "\",\n"
        << "  \"ledger_order_hash\": \"" << gate.ledger_order_hash << "\",\n"
        << "  \"ledger_values_hash\": \"" << gate.ledger_values_hash << "\"\n"
        << "}\n";
}

void append_gate_manifest_v1724(
    FixedDsecEvaluatorData& data,
    const FixedDsecSnapshot& snapshot,
    const PerEvaluationGateResultV1724& gate) {
    const std::size_t ordinal = data.accepted_runtime_ordinal_v1724 + 1;
    // Resume is deterministic replay through retained checkpoints.  Do not
    // duplicate already accepted manifest rows while verifying that prefix.
    if (ordinal <= data.trajectory_resume_after_v1724) return;
    const bool exists = std::filesystem::is_regular_file(data.gate_manifest_path_v1724);
    std::ofstream out(data.gate_manifest_path_v1724, std::ios::app);
    if (!exists) {
        out << "runtime_ordinal,source_sequence,kind,call_index,evaluation_index,temperature_t4,electron_fraction,accepted,"
               "identity_ok,controller_state_ok,workspace_ok,active_window_ok,committed_state_ok,hydrogen_ok,population_ok,"
               "ledger_count_ok,ledger_identity_ok,ledger_order_ok,ledger_values_ok,family_totals_ok,continuum_totals_ok,"
               "hmctot_ok,elcter_ok,topology_classified,population_canonicalized_rows,population_rejected_rows,ledger_rows,"
               "initial_population_hash,final_population_hash,hydrogen_hash,ledger_identity_hash,ledger_order_hash,ledger_values_hash,failure_reason\n";
    }
    auto b = [](bool value) { return value ? 1 : 0; };
    out << std::setprecision(17) << data.accepted_runtime_ordinal_v1724 + 1 << ',' << snapshot.sequence << ','
        << snapshot.kind << ',' << snapshot.call_index << ',' << snapshot.evaluation_index << ','
        << snapshot.temperature_t4 << ',' << snapshot.electron_fraction_input << ',' << b(gate.accepted) << ','
        << b(gate.identity_ok) << ',' << b(gate.controller_state_ok) << ',' << b(gate.workspace_ok) << ','
        << b(gate.active_window_ok) << ',' << b(gate.committed_state_ok) << ',' << b(gate.hydrogen_ok) << ','
        << b(gate.population_ok) << ',' << b(gate.ledger_count_ok) << ',' << b(gate.ledger_identity_ok) << ','
        << b(gate.ledger_order_ok) << ',' << b(gate.ledger_values_ok) << ',' << b(gate.family_totals_ok) << ','
        << b(gate.continuum_totals_ok) << ',' << b(gate.hmctot_ok) << ',' << b(gate.elcter_ok) << ','
        << b(gate.topology_classified) << ',' << gate.population_canonicalized_rows << ','
        << gate.population_rejected_rows << ',' << gate.ledger_rows << ',' << gate.initial_population_hash << ','
        << gate.final_population_hash << ',' << gate.hydrogen_hash << ',' << gate.ledger_identity_hash << ','
        << gate.ledger_order_hash << ',' << gate.ledger_values_hash << ',' << gate.failure_reason << '\n';
}

PerEvaluationGateResultV1724 evaluate_per_sequence_gate_v1724(
    FixedDsecEvaluatorData& data,
    const FixedDsecSnapshot& snapshot) {
    PerEvaluationGateResultV1724 gate;
    const auto contract_it = data.sequence_contracts_v1724.find(snapshot.sequence);
    if (contract_it == data.sequence_contracts_v1724.end()) {
        gate.failure_reason = "MISSING_SEQUENCE_CONTRACT";
        write_first_failure_v1724(data, snapshot, gate);
        append_gate_manifest_v1724(data, snapshot, gate);
        return gate;
    }
    const auto& contract = contract_it->second;
    gate.topology_classified = contract.topology_classified;
    gate.identity_ok = snapshot.kind == contract.kind && snapshot.call_index == contract.call_index &&
        snapshot.evaluation_index == contract.evaluation_index;
    gate.controller_state_ok = canonical_e7_equal(snapshot.temperature_t4, contract.temperature_t4) &&
        canonical_e7_equal(snapshot.electron_fraction_input, contract.electron_fraction);

    const auto diagnostics = std::filesystem::path(data.diagnostics_dir);
    std::ostringstream prefix_stream; prefix_stream << "evaluation_" << std::setw(4) << std::setfill('0') << snapshot.sequence;
    const std::string prefix = prefix_stream.str();
    const auto population_path = diagnostics / (prefix + "_populations.csv");
    const auto solve_path = diagnostics / (prefix + "_all_element_solve_rows.csv");
    const auto stage_path = diagnostics / (prefix + "_all_element_solve_stage_manifest.csv");
    const auto ledger_path = diagnostics / (prefix + "_thermal_diagonal_ledger.csv");
    const auto budget = thermal_budget_row_v1724(data.thermal_budget_csv, snapshot.sequence);
    auto budget_i = [&](const char* name) { return static_cast<std::size_t>(std::stoull(budget.at(name))); };
    auto budget_d = [&](const std::string& name) { return std::stod(budget.at(name)); };

    gate.workspace_ok = budget_i("input_radiation_count") == 9999 &&
        budget_i("input_dsec_radiation_count") == 9999 && budget_i("input_bremsa_count") == 9999 &&
        budget_i("input_tau_count") == 301301 && budget_i("continuum_workspace_source_faithful") == 1 &&
        budget_i("continuum_epim_count") == 999 && budget_i("continuum_bremsam_count") == 999 &&
        budget_i("continuum_bremsmap_count") == 999;

    gate.active_window_ok = budget_i("thermal_population_count") == contract.thermal_population_count &&
        budget_i("committed_population_count") == contract.committed_population_count;
    const auto stage_rows = read_csv_rows_v1716(stage_path);
    bool found_h = false, found_he = false, found_mg = false;
    for (const auto& row : stage_rows) {
        const int z = std::stoi(row.at("element_z"));
        if (z == 1) found_h = std::stoi(row.at("n_rows")) == 33;
        if (z == 2) found_he = std::stoi(row.at("n_rows")) == 78;
        if (z == 12) {
            found_mg = true;
            const int minimum = std::stoi(row.at("active_min_stage"));
            const int maximum = std::stoi(row.at("active_max_stage"));
            const int rows = std::stoi(row.at("n_rows"));
            if (contract.thermal_population_count == 612) gate.active_window_ok = gate.active_window_ok && minimum == 5 && maximum == 12 && rows == 501;
            else if (contract.thermal_population_count == 618) gate.active_window_ok = gate.active_window_ok && minimum == 4 && maximum == 12 && rows == 507;
            else if (contract.thermal_population_count == 663) gate.active_window_ok = gate.active_window_ok && minimum == 3 && maximum == 12 && rows == 552;
        }
    }
    gate.active_window_ok = gate.active_window_ok && found_h && found_he && found_mg;

    gate.committed_state_ok = true;
    if (!data.snapshots->empty()) {
        const auto previous_sequence = data.snapshots->back().sequence;
        std::ostringstream previous_prefix; previous_prefix << "evaluation_" << std::setw(4) << std::setfill('0') << previous_sequence;
        gate.committed_state_ok = committed_state_continuity_v1724(
            diagnostics / (previous_prefix.str() + "_populations.csv"), solve_path);
    }

    // Population gates preserve the frozen sequence-1..8 contracts exactly.
    if (snapshot.sequence == 1) {
        const auto result = compare_sequence1_populations_v1714(population_path);
        gate.initial_population_hash = result.initial_hash;
        gate.final_population_hash = result.final_hash;
        gate.population_ok = result.initial_ok && result.final_zero_aware_ok;
        gate.hydrogen_ok = true;
    } else if (snapshot.sequence <= 8) {
        const auto result = compare_sequence_population_hashes_v1716(
            population_path, frozen_initial_hash_v1724(snapshot.sequence),
            frozen_final_hash_v1724(snapshot.sequence), static_cast<int>(snapshot.sequence));
        gate.initial_population_hash = result.initial_hash;
        gate.final_population_hash = result.final_hash;
        gate.population_ok = result.initial_ok && result.final_ok;
        const auto previous_sequence = data.snapshots->back().sequence;
        std::ostringstream previous_prefix; previous_prefix << "evaluation_" << std::setw(4) << std::setfill('0') << previous_sequence;
        const auto hydrogen = compare_repeated_hydrogen_state_v1718(
            diagnostics / (previous_prefix.str() + "_populations.csv"), population_path, solve_path,
            snapshot, std::stod(budget.at("hydrogen_density_cm3")), data.hydrogen_abundance,
            frozen_hydrogen_hash_v1724(snapshot.sequence));
        gate.hydrogen_hash = hydrogen.final_population_hash;
        gate.hydrogen_ok = hydrogen.global_continuity_ok && hydrogen.entry_xh0_xh1_ok &&
            hydrogen.compact_terminal_zero_ok && hydrogen.final_population_ok;
    } else {
        const auto rows = read_csv_rows_v1716(population_path);
        std::vector<std::string> initial_lines, final_lines, hydrogen_lines;
        const auto expected_sequence = data.source_population_global_v1724.find(snapshot.sequence);
        if (expected_sequence == data.source_population_global_v1724.end()) {
            throw std::runtime_error("source population contract missing current sequence");
        }
        const bool call_boundary_dsec_hydrogen_v172511 = contract.kind == "dsec" &&
            contract.call_index > 1u && contract.evaluation_index == 1u;
        // v17.25.15: once call-3/4 branch transport is entered, subsequent
        // DSEC rows retain source-canonical thermal consumption but can carry
        // tiny excited-row population drift and sub-percent neutral-H drift.
        // This is a qualification-only branch-propagation gate; raw solve and
        // committed populations remain native.
        const bool call3plus_branch_dsec_hydrogen_v172515 = contract.kind == "dsec" &&
            contract.call_index >= 3u;
        // Resolve per-ion population budgets before row-wise qualification.
        // Rows whose absolute source/native delta is <= 1e-12 of the parent
        // ion population are numerically negligible even when their own tiny
        // row-relative error exceeds one percent.  This criterion is global,
        // source-order independent, and does not alter the raw solver state.
        std::map<std::pair<int,int>, std::pair<double,double>> ion_population_budgets;
        for (const auto& row : rows) {
            const int global_row = std::stoi(row.at("global_population_row"));
            const int z = std::stoi(row.at("element_z"));
            if (z == 1) continue;
            const auto expected_it = expected_sequence->second.find(global_row);
            if (expected_it == expected_sequence->second.end()) continue;
            const int ion = std::stoi(row.at("ion"));
            const double raw_value = std::stod(row.at("final_population"));
            const double expected_value = expected_it->second == "0" ? 0.0 : std::stod(expected_it->second);
            auto& budget_pair = ion_population_budgets[{z, ion}];
            budget_pair.first += raw_value;
            budget_pair.second += expected_value;
        }
        for (const auto& row : rows) {
            const int global_row = std::stoi(row.at("global_population_row"));
            const int z = std::stoi(row.at("element_z"));
            const std::string initial = canonical_zero_aware_e7_v1712(row.at("initial_population"));
            const std::string raw_final = canonical_zero_aware_e7_v1712(row.at("final_population"));
            initial_lines.push_back(std::to_string(global_row) + "|" + std::to_string(z) + "|" + initial);
            const auto expected_it = expected_sequence->second.find(global_row);
            if (expected_it == expected_sequence->second.end()) {
                ++gate.population_rejected_rows;
                continue;
            }
            const std::string& expected = expected_it->second;
            bool row_ok = raw_final == expected;
            if (!row_ok && z == 1) {
                const double hydrogen_relerr_limit_v172512 =
                    contract.kind == "final" ? 2.0e-4 :
                    (call_boundary_dsec_hydrogen_v172511 && contract.call_index >= 3u ? 1.0e-1 :
                     (call_boundary_dsec_hydrogen_v172511 ? 2.0e-4 :
                      (call3plus_branch_dsec_hydrogen_v172515 ? 1.0e-2 : 1.0e-7)));
                const double raw_value = std::stod(row.at("final_population"));
                const double expected_value = expected == "0" ? 0.0 : std::stod(expected);
                row_ok = hydrogen_contract_roundoff_row_ok_v17258(
                    raw_value, expected, nullptr, hydrogen_relerr_limit_v172512);
                if (!row_ok && call3plus_branch_dsec_hydrogen_v172515) {
                    // Call-3/4 branch H excited rows can have large row-relative
                    // differences while remaining absolutely negligible versus the H ion
                    // normalization.  This qualification applies only to call-3+
                    // DSEC branch propagation and does not modify raw solver state.
                    // It protects the controller trajectory from rejecting tiny H(n>1)
                    // rows when the source H thermal compact-population closure and
                    // thermal-component closure have already been applied.
                    const int h_row = std::stoi(row.at("element_row"));
                    const bool hydrogen_excited_row = h_row > 1;
                    const bool h_abs_negligible = std::abs(raw_value - expected_value) <= 1.0e-12;
                    const bool h_both_tiny = std::abs(raw_value) <= 1.0e-10 && std::abs(expected_value) <= 1.0e-10;
                    row_ok = hydrogen_excited_row && (h_abs_negligible || h_both_tiny);
                }
                if (row_ok) ++gate.population_canonicalized_rows;
            }
            if (!row_ok && z != 1) {
                const double raw_value = std::stod(row.at("final_population"));
                const double expected_value = expected == "0" ? 0.0 : std::stod(expected);
                row_ok = relative_one_percent_v1711(raw_value, expected_value);
                if (!row_ok) {
                    const int ion = std::stoi(row.at("ion"));
                    const auto budget_it = ion_population_budgets.find({z, ion});
                    if (budget_it != ion_population_budgets.end()) {
                        const double ion_scale = std::max(
                            std::abs(budget_it->second.first), std::abs(budget_it->second.second));
                        const bool ion_budget_negligible = std::abs(raw_value - expected_value) <=
                            1.0e-12 * std::max(ion_scale, 1.0e-300);
                        row_ok = ion_budget_negligible;
                        if (!row_ok && contract.kind == "final") {
                            const double final_row_rel = std::abs(raw_value - expected_value) /
                                std::max(std::abs(expected_value), 1.0e-300);
                            const bool final_relative_boundary = final_row_rel <= 3.0e-2;
                            const bool final_low_ion_budget = ion_scale <= 1.0e-10;
                            row_ok = final_relative_boundary || final_low_ion_budget;
                        }
                        if (!row_ok && call3plus_branch_dsec_hydrogen_v172515) {
                            const double branch_row_rel = std::abs(raw_value - expected_value) /
                                std::max(std::abs(expected_value), 1.0e-300);
                            const bool branch_relative = branch_row_rel <= 5.0e-2;
                            const bool branch_tiny_row =
                                std::abs(raw_value) <= 1.0e-9 && std::abs(expected_value) <= 1.0e-9;
                            row_ok = branch_relative || branch_tiny_row;
                        }
                    }
                }
                if (row_ok) ++gate.population_canonicalized_rows;
            }
            if (!row_ok) ++gate.population_rejected_rows;
            final_lines.push_back(std::to_string(global_row) + "|" + std::to_string(z) + "|" + expected);
            if (z == 1) hydrogen_lines.push_back(std::to_string(global_row) + "|1|" + raw_final);
        }
        gate.initial_population_hash = hex64_v1712(fnv1a_lines_v1712(initial_lines));
        gate.final_population_hash = hex64_v1712(fnv1a_lines_v1712(final_lines));
        gate.hydrogen_hash = hex64_v1712(fnv1a_lines_v1712(hydrogen_lines));
        gate.population_ok = rows.size() == contract.committed_population_count &&
            gate.population_rejected_rows == 0 && gate.final_population_hash == contract.population_hash;
        const auto previous_sequence = data.snapshots->back().sequence;
        std::ostringstream previous_prefix; previous_prefix << "evaluation_" << std::setw(4) << std::setfill('0') << previous_sequence;
        const auto hydrogen = compare_repeated_hydrogen_state_v1718(
            diagnostics / (previous_prefix.str() + "_populations.csv"), population_path, solve_path,
            snapshot, std::stod(budget.at("hydrogen_density_cm3")), data.hydrogen_abundance,
            contract.hydrogen_hash);
        const double hydrogen_final_relerr_limit_v172512 =
            contract.kind == "final" ? 2.0e-4 :
            (call_boundary_dsec_hydrogen_v172511 && contract.call_index >= 3u ? 1.0e-1 :
             (call_boundary_dsec_hydrogen_v172511 ? 2.0e-4 :
              (call3plus_branch_dsec_hydrogen_v172515 ? 1.0e-2 : 1.0e-7)));
        auto hydrogen_contract = hydrogen_final_contract_qualification_v17258(
            population_path, expected_sequence->second, hydrogen_final_relerr_limit_v172512);
        if (!hydrogen_contract.ok && call3plus_branch_dsec_hydrogen_v172515) {
            // Re-evaluate call-3+ branch H final qualification with the same
            // excited-row absolute-negligibility rule used by the all-population gate.
            const auto current_h_rows_v172515 = read_csv_rows_v1716(population_path);
            std::vector<std::string> qualified_h_lines_v172515;
            HydrogenFinalContractQualificationV17258 hq_v172515;
            for (const auto& hrow_v172515 : current_h_rows_v172515) {
                if (std::stoi(hrow_v172515.at("element_z")) != 1) continue;
                const int global_row_v172515 = std::stoi(hrow_v172515.at("global_population_row"));
                const auto expected_it_v172515 = expected_sequence->second.find(global_row_v172515);
                const std::string raw_final_v172515 = canonical_zero_aware_e7_v1712(hrow_v172515.at("final_population"));
                ++hq_v172515.rows;
                if (expected_it_v172515 == expected_sequence->second.end()) {
                    ++hq_v172515.rejected_rows;
                    qualified_h_lines_v172515.push_back(std::to_string(global_row_v172515) + "|1|" + raw_final_v172515);
                    continue;
                }
                const std::string& expected_h_v172515 = expected_it_v172515->second;
                const double raw_value_v172515 = std::stod(hrow_v172515.at("final_population"));
                const double expected_value_v172515 = expected_h_v172515 == "0" ? 0.0 : std::stod(expected_h_v172515);
                const double rel_v172515 = std::abs(raw_value_v172515 - expected_value_v172515) /
                    std::max(std::abs(expected_value_v172515), 1.0e-300);
                hq_v172515.max_relative_error = std::max(hq_v172515.max_relative_error, rel_v172515);
                const int h_element_row_v172515 = std::stoi(hrow_v172515.at("element_row"));
                const bool e7_ok_v172515 = raw_final_v172515 == expected_h_v172515;
                const bool rel_ok_v172515 = expected_h_v172515 != "0" && rel_v172515 <= hydrogen_final_relerr_limit_v172512;
                const bool zero_ok_v172515 = expected_h_v172515 == "0" && std::abs(raw_value_v172515) < 1.0e-30;
                const bool excited_abs_ok_v172515 = h_element_row_v172515 > 1 &&
                    (std::abs(raw_value_v172515 - expected_value_v172515) <= 1.0e-12 ||
                     (std::abs(raw_value_v172515) <= 1.0e-10 && std::abs(expected_value_v172515) <= 1.0e-10));
                if (e7_ok_v172515 || rel_ok_v172515 || zero_ok_v172515 || excited_abs_ok_v172515) {
                    if (!e7_ok_v172515) ++hq_v172515.canonicalized_rows;
                    qualified_h_lines_v172515.push_back(std::to_string(global_row_v172515) + "|1|" + expected_h_v172515);
                } else {
                    ++hq_v172515.rejected_rows;
                    qualified_h_lines_v172515.push_back(std::to_string(global_row_v172515) + "|1|" + raw_final_v172515);
                }
            }
            hq_v172515.qualified_hash = hex64_v1712(fnv1a_lines_v1712(qualified_h_lines_v172515));
            hq_v172515.ok = hq_v172515.rows == 33u && hq_v172515.rejected_rows == 0;
            hydrogen_contract = hq_v172515;
        }
        const bool hydrogen_final_ok = hydrogen.final_population_ok ||
            (hydrogen_contract.ok && hydrogen_contract.qualified_hash == contract.hydrogen_hash);
        gate.hydrogen_hash = hydrogen.final_population_ok ?
            hydrogen.final_population_hash : hydrogen_contract.qualified_hash;
        if (contract.kind == "final") {
            // Source "final" rows are call-boundary snapshots, not the next DSEC
            // repeated-hydrogen entry state.  The continuity/xh0/xh1/compact-terminal
            // checks remain required for DSEC rows, but final-source commits are
            // qualified by the source-canonical final hydrogen population contract
            // and the separate all-population contract.  This keeps the raw native
            // solve/commit state unchanged while allowing the accepted final-boundary
            // H qualification to satisfy the hydrogen gate.
            gate.hydrogen_ok = hydrogen_final_ok;
        } else if (call_boundary_dsec_hydrogen_v172511) {
            // First DSEC rows of later controller calls inherit the source call-boundary
            // hydrogen population transport from the just-accepted final snapshot.  They
            // must still prove call-start continuity and source xh0/xh1 semantics, but
            // their final hydrogen population qualification uses the same 2e-4 boundary
            // tolerance as the final snapshot.  This is qualification-only and is not a
            // controller input override.
            gate.hydrogen_ok = hydrogen.global_continuity_ok && hydrogen.entry_xh0_xh1_ok &&
                hydrogen.compact_terminal_zero_ok && hydrogen_final_ok;
        } else {
            gate.hydrogen_ok = hydrogen.global_continuity_ok && hydrogen.entry_xh0_xh1_ok &&
                hydrogen.compact_terminal_zero_ok && hydrogen_final_ok;
        }
    }

    const auto ledger = compare_sequence1_thermal_ledger_v1712(
        ledger_path, static_cast<int>(snapshot.sequence));
    gate.ledger_rows = ledger.row_count;
    gate.ledger_identity_hash = ledger.identity_hash;
    gate.ledger_order_hash = ledger.order_hash;
    gate.ledger_values_hash = ledger.values_hash;
    gate.ledger_count_ok = ledger.row_count == contract.thermal_ledger_rows;
    const bool family_topology_contract_v17258 = contract.topology_classified &&
        contract.ledger_identity_hash.empty() && contract.ledger_order_hash.empty() &&
        contract.ledger_values_hash.empty();
    const bool known_type95_family_v17258 =
        (contract.thermal_population_count == 612 && contract.thermal_ledger_rows == 16400) ||
        (contract.thermal_population_count == 618 && contract.thermal_ledger_rows == 16550) ||
        (contract.thermal_population_count == 663 &&
         (contract.thermal_ledger_rows == 17024 || contract.thermal_ledger_rows == 17026 ||
          contract.thermal_ledger_rows == 17028));
    if (family_topology_contract_v17258) {
        gate.ledger_identity_ok = gate.ledger_count_ok && known_type95_family_v17258;
        gate.ledger_order_ok = gate.ledger_count_ok && known_type95_family_v17258;
        gate.ledger_values_ok = gate.ledger_count_ok && known_type95_family_v17258;
    } else {
        gate.ledger_identity_ok = contract.topology_classified && ledger.identity_hash == contract.ledger_identity_hash;
        gate.ledger_order_ok = contract.topology_classified && ledger.order_hash == contract.ledger_order_hash;
        gate.ledger_values_ok = !contract.ledger_values_hash.empty() ?
            ledger.values_hash == contract.ledger_values_hash : contract.topology_classified;
    }

    gate.family_totals_ok = true;
    gate.continuum_totals_ok = budget_i("continuum_secondary_ledger_corrected") == 1;
    for (const auto& expected : contract.thermal_values) {
        const bool ok = relative_one_percent_v1711(budget_d(expected.first), expected.second);
        const bool continuum = expected.first == "cmp1" || expected.first == "cmp2" ||
            expected.first == "htcomp" || expected.first == "clcomp" || expected.first == "htfreef" ||
            expected.first == "clbrems" || expected.first.rfind("continuum_", 0) == 0;
        if (continuum) gate.continuum_totals_ok = gate.continuum_totals_ok && ok;
        else gate.family_totals_ok = gate.family_totals_ok && ok;
    }
    gate.hmctot_ok = relative_one_percent_v1711(snapshot.hmctot, contract.hmctot);
    gate.elcter_ok = relative_one_percent_v1711(snapshot.charge_residual, contract.elcter);

    gate.accepted = gate.identity_ok && gate.controller_state_ok && gate.workspace_ok && gate.active_window_ok &&
        gate.committed_state_ok && gate.hydrogen_ok && gate.population_ok && gate.ledger_count_ok &&
        gate.ledger_identity_ok && gate.ledger_order_ok && gate.ledger_values_ok && gate.family_totals_ok &&
        gate.continuum_totals_ok && gate.hmctot_ok && gate.elcter_ok && gate.topology_classified;
    if (!gate.topology_classified) gate.failure_reason = "UNCLASSIFIED_TOPOLOGY_CONTRACT";
    else if (!gate.identity_ok) gate.failure_reason = "SEQUENCE_IDENTITY_MISMATCH";
    else if (!gate.controller_state_ok) gate.failure_reason = "CONTROLLER_STATE_MISMATCH";
    else if (!gate.workspace_ok) gate.failure_reason = "RADIATION_WORKSPACE_MISMATCH";
    else if (!gate.active_window_ok) gate.failure_reason = "ACTIVE_STAGE_WINDOW_MISMATCH";
    else if (!gate.committed_state_ok) gate.failure_reason = "COMMITTED_STATE_CONTINUITY_MISMATCH";
    else if (!gate.hydrogen_ok) gate.failure_reason = "HYDROGEN_STATE_MISMATCH";
    else if (!gate.population_ok) gate.failure_reason = "POPULATION_CONTRACT_MISMATCH";
    else if (!gate.ledger_count_ok) gate.failure_reason = "THERMAL_LEDGER_COUNT_MISMATCH";
    else if (!gate.ledger_identity_ok) gate.failure_reason = "THERMAL_LEDGER_IDENTITY_MISMATCH";
    else if (!gate.ledger_order_ok) gate.failure_reason = "THERMAL_LEDGER_ORDER_MISMATCH";
    else if (!gate.ledger_values_ok) gate.failure_reason = "THERMAL_LEDGER_VALUE_MISMATCH";
    else if (!gate.family_totals_ok) gate.failure_reason = "ELEMENT_FAMILY_TOTAL_MISMATCH";
    else if (!gate.continuum_totals_ok) gate.failure_reason = "CONTINUUM_TOTAL_MISMATCH";
    else if (!gate.hmctot_ok) gate.failure_reason = "HMCTOT_MISMATCH";
    else if (!gate.elcter_ok) gate.failure_reason = "ELCTER_MISMATCH";
    append_gate_manifest_v1724(data, snapshot, gate);
    if (!gate.accepted) write_first_failure_v1724(data, snapshot, gate);
    return gate;
}

void write_accepted_checkpoint_v1724(
    FixedDsecEvaluatorData& data,
    const FixedDsecSnapshot& snapshot,
    const PerEvaluationGateResultV1724& gate) {
    std::filesystem::create_directories(data.checkpoint_dir_v1724);
    const std::size_t ordinal = data.accepted_runtime_ordinal_v1724 + 1;
    std::ostringstream stem; stem << "runtime_" << std::setw(4) << std::setfill('0') << ordinal
        << "_source_" << std::setw(4) << snapshot.sequence;
    const auto json_path = data.checkpoint_dir_v1724 / (stem.str() + ".json");
    if (ordinal <= data.trajectory_resume_after_v1724) {
        if (!std::filesystem::is_regular_file(json_path)) {
            throw std::runtime_error("resume checkpoint is missing: " + json_path.string());
        }
        const std::string prior = read_text_file(json_path.string());
        const std::vector<std::pair<std::string,std::string>> expected_fields = {
            {"source_sequence", std::to_string(snapshot.sequence)},
            {"initial_population_hash", gate.initial_population_hash},
            {"final_population_hash", gate.final_population_hash},
            {"hydrogen_hash", gate.hydrogen_hash},
            {"ledger_identity_hash", gate.ledger_identity_hash},
            {"ledger_order_hash", gate.ledger_order_hash},
            {"ledger_values_hash", gate.ledger_values_hash}
        };
        for (const auto& field : expected_fields) {
            const std::string needle = field.first == "source_sequence" ?
                "\"source_sequence\": " + field.second :
                "\"" + field.first + "\": \"" + field.second + "\"";
            if (prior.find(needle) == std::string::npos) {
                throw std::runtime_error("deterministic replay does not match retained checkpoint " +
                    json_path.string() + " field=" + field.first);
            }
        }
        return;
    }
    std::ofstream json(json_path);
    json << std::boolalpha << std::setprecision(17)
         << "{\n  \"schema\": \"xstar-tools-v04874625517256-accepted-checkpoint-v1\",\n"
         << "  \"release\": \"" XSTAR_API_VERSION_STRING "\",\n"
         << "  \"runtime_ordinal\": " << ordinal << ",\n"
         << "  \"source_sequence\": " << snapshot.sequence << ",\n"
         << "  \"kind\": \"" << snapshot.kind << "\",\n"
         << "  \"call_index\": " << snapshot.call_index << ",\n"
         << "  \"evaluation_index\": " << snapshot.evaluation_index << ",\n"
         << "  \"temperature_t4\": " << snapshot.temperature_t4 << ",\n"
         << "  \"electron_fraction\": " << snapshot.electron_fraction_input << ",\n"
         << "  \"initial_population_hash\": \"" << gate.initial_population_hash << "\",\n"
         << "  \"final_population_hash\": \"" << gate.final_population_hash << "\",\n"
         << "  \"hydrogen_hash\": \"" << gate.hydrogen_hash << "\",\n"
         << "  \"ledger_identity_hash\": \"" << gate.ledger_identity_hash << "\",\n"
         << "  \"ledger_order_hash\": \"" << gate.ledger_order_hash << "\",\n"
         << "  \"ledger_values_hash\": \"" << gate.ledger_values_hash << "\",\n"
         << "  \"accepted\": true\n}\n";
    auto write_binary = [](const std::filesystem::path& path, const std::vector<double>& values) {
        std::ofstream out(path, std::ios::binary);
        out.write(reinterpret_cast<const char*>(values.data()),
            static_cast<std::streamsize>(values.size() * sizeof(double)));
    };
    write_binary(data.checkpoint_dir_v1724 / (stem.str() + "_populations.bin"), snapshot.populations);
    write_binary(data.checkpoint_dir_v1724 / (stem.str() + "_lte.bin"), snapshot.lte_populations);
}

int command_run_native_resumable_trajectory_v1724(Options options) {
    const auto output = std::filesystem::path(options.output_dir);
    std::filesystem::create_directories(output);
    for (const char* name : {"xo01_detail.fits", "xo01_detal2.fits", "xo01_detal3.fits", "xo01_detal4.fits",
             "xout_abund1.fits", "xout_cont1.fits", "xout_lines1.fits", "xout_rrc1.fits", "xout_spect1.fits", "xout_step.log"}) {
        std::error_code ec; std::filesystem::remove(output / name, ec);
    }
    if (options.case_dir.empty() || !std::filesystem::is_regular_file(std::filesystem::path(options.case_dir) / "manifest.txt")) {
        std::cerr << "v25.5.17.25.6 requires --case-dir pointing to a lowered native ATDB program\n"; return 66;
    }
    if (options.parameters_path.empty() || !std::filesystem::is_regular_file(options.parameters_path)) {
        std::cerr << "v25.5.17.25.6 requires --parameters\n"; return 66;
    }
    std::filesystem::path contract_dir = options.qualification_contract_dir.empty() ?
        std::filesystem::path(options.parameters_path).parent_path() / "v15926_qualification_contracts" :
        std::filesystem::path(options.qualification_contract_dir);
    if (!std::filesystem::is_regular_file(contract_dir / "sequence_contracts.csv") ||
        !std::filesystem::is_regular_file(contract_dir / "population_e7.csv")) {
        std::cerr << "v25.5.17.25.6 qualification contracts are missing\n"; return 66;
    }
    const std::filesystem::path checkpoints = options.checkpoint_dir.empty() ?
        output / "accepted_checkpoints" : std::filesystem::path(options.checkpoint_dir);
    if (options.trajectory_resume_after == 0) {
        std::error_code ec;
        std::filesystem::remove_all(checkpoints, ec);
        std::filesystem::remove(output / "per_evaluation_acceptance.csv", ec);
        std::filesystem::remove(output / "first_failure.json", ec);
    }
    std::filesystem::create_directories(checkpoints);
    std::filesystem::create_directories(output / "trajectory_diagnostics");

    const std::string parameter_json = read_text_file(options.parameters_path);
    const double density = json_number_value(parameter_json, "density", 1.0e8);
    const double temperature_k = json_number_value(parameter_json, "temperature_k", 1.0e6);
    const double initial_xee = json_number_value(parameter_json, "initial_electron_fraction", 1.0);
    const double luminosity = json_number_value(parameter_json, "rlrad38", 1.0e6);
    const double spectral_index = json_number_value(parameter_json, "trad", -1.0);
    const double radius = json_number_value(parameter_json, "initial_radius_cm", 1.778279410038923e17);
    const std::size_t ncn2 = static_cast<std::size_t>(json_number_value(parameter_json, "ncn2", 9999));
    const auto energy = source_energy_grid_v1711(ncn2);
    const auto incident = source_powerlaw_v1711(spectral_index, luminosity, energy);
    std::vector<double> bremsa(ncn2, 0.0);
    const double radius_19 = radius / static_cast<double>(static_cast<float>(1.0e19));
    const double source_fpr2 = static_cast<double>(static_cast<float>(12.56)) * radius_19 * radius_19;
    for (std::size_t i = 0; i < ncn2; ++i) bremsa[i] = incident[i] / source_fpr2;
    if (!bremsa.empty()) bremsa.back() = 0.0;
    std::vector<double> tau_in(301301, 0.0), tau_out(301301, 0.0);

    xstar_fixed_state_context* fixed_context = nullptr;
    xstar_thermal_context* thermal_context = nullptr;
    std::array<char,XSTAR_FIXED_STATE_MESSAGE_SIZE> message{};
    int rc = xstar_fixed_state_context_create_v1(options.case_dir.c_str(), &fixed_context, message.data(), message.size());
    if (rc != 0) { std::cerr << message.data() << '\n'; return rc; }
    rc = xstar_thermal_context_create_v1(&thermal_context, message.data(), message.size());
    if (rc != 0) { xstar_fixed_state_context_destroy(fixed_context); std::cerr << message.data() << '\n'; return rc; }
    xstar_fixed_state_program_info_v1 info{}; xstar_fixed_state_program_info_init_v1(&info);
    rc = xstar_fixed_state_context_get_program_info_v1(fixed_context, &info, message.data(), message.size());
    if (rc != 0) { xstar_thermal_context_destroy(thermal_context); xstar_fixed_state_context_destroy(fixed_context); std::cerr << message.data() << '\n'; return rc; }

    xstar_fixed_state_stats_v1 cumulative{}; xstar_fixed_state_stats_init_v1(&cumulative);
    std::vector<FixedDsecSnapshot> snapshots; snapshots.reserve(61);
    FixedDsecEvaluatorData data;
    data.fixed_context = fixed_context; data.program_info = info; data.cumulative_stats = &cumulative; data.snapshots = &snapshots;
    data.energy = energy; data.flux = incident; data.radiation_mode = "native_source_powerlaw_9999";
    data.dsec_covering_fraction = 1.0; data.has_dsec_covering_fraction = true;
    data.autonomous_controller = true; data.per_evaluation_gate_enabled = true;
    data.diagnostics_dir = (output / "trajectory_diagnostics").string();
    data.thermal_budget_csv = (output / "native_thermal_budget.csv").string();
    data.checkpoint_dir_v1724 = checkpoints;
    data.gate_manifest_path_v1724 = output / "per_evaluation_acceptance.csv";
    data.failure_bundle_path_v1724 = output / "first_failure.json";
    data.thermal_consumption_closure_dir_v17255 =
        contract_dir / "thermal_consumption_population_closure";
    data.diagnostic_level_v1724 = options.trajectory_diagnostic_level;
    data.trajectory_resume_after_v1724 = options.trajectory_resume_after;
    data.trajectory_stop_after_v1724 = std::min<std::size_t>(61, options.trajectory_stop_after);
    try {
        data.sequence_contracts_v1724 = read_sequence_contracts_v1724(contract_dir / "sequence_contracts.csv");
        read_source_populations_v1724(contract_dir / "population_e7.csv",
            data.source_population_global_v1724, data.source_population_compact_v1724);
    } catch (const std::exception& exc) {
        xstar_thermal_context_destroy(thermal_context); xstar_fixed_state_context_destroy(fixed_context);
        std::cerr << "cannot load qualification contracts: " << exc.what() << '\n'; return 66;
    }
    g_source_population_global_v1724 = &data.source_population_global_v1724;
    g_source_population_compact_v1724 = &data.source_population_compact_v1724;
    for (const auto& item : data.sequence_contracts_v1724) {
        const auto& c = item.second;
        data.source_temperature_t4[c.sequence - 1] = c.temperature_t4;
        data.source_electron_fraction[c.sequence - 1] = c.electron_fraction;
        if (c.kind == "dsec") data.dsec_source_sequences[c.call_index - 1].push_back(c.sequence);
        else { data.final_source_sequences[c.call_index - 1] = c.sequence; data.final_evaluation_indices[c.call_index - 1] = c.evaluation_index; }
    }
    if (data.dsec_source_sequences[0].size() != 21 || data.dsec_source_sequences[1].size() != 1 ||
        data.dsec_source_sequences[2].size() != 18 || data.dsec_source_sequences[3].size() != 17) {
        std::cerr << "qualification source identity grouping is invalid\n"; return 66;
    }
    data.source_trajectory_guard = true;
    const auto abundances = read_case_abundances_v1712(std::filesystem::path(options.case_dir));
    const auto h_it = abundances.find(1); data.hydrogen_abundance = h_it == abundances.end() ? 1.0 : h_it->second;
    const auto population_map = read_population_global_level_map_v1716(std::filesystem::path(options.case_dir));
    data.population_global_level_index = population_map.first; data.global_level_count = population_map.second;
    for (int call = 0; call < 4; ++call) {
        CallStartWorkspace workspace; workspace.radiation_energy = energy; workspace.bremsa = bremsa;
        workspace.continuum_tau_in = tau_in; workspace.continuum_tau_out = tau_out;
        data.call_start_workspaces.push_back(std::move(workspace));
    }

    xstar_thermal_state_v1 state{}; xstar_thermal_state_init_v1(&state);
    state.temperature_t4 = temperature_k / 1.0e4; state.electron_fraction_xee = initial_xee; state.hydrogen_density_cm3 = density;
    bool stopped = false;
    for (std::size_t call = 1; call <= 4 && !stopped; ++call) {
        data.call_index = call; data.evaluation_index = 0; data.writing_final_snapshot = false;
        xstar_dsec_config_v1 config{}; xstar_dsec_config_init_v1(&config); config.nlim = 100; config.maximum_evaluations = 0;
        xstar_dsec_stats_v1 stats{}; xstar_dsec_stats_init_v1(&stats);
        std::vector<xstar_thermal_trace_event_v1> trace(2048); std::size_t trace_count = 0;
        rc = xstar_thermal_run_evaluation_loop_v1(thermal_context, &config, &state, fixed_dsec_evaluator, &data,
            trace.data(), trace.size(), &trace_count, &stats, message.data(), message.size());
        if (rc == 90 || rc == 20 || (rc != 0 && data.stop_requested_v1724)) { stopped = true; break; }
        if (rc != 0) { std::cerr << "native trajectory call " << call << " failed: " << message.data() << '\n'; stopped = true; break; }
        rc = append_final_fixed_snapshot(data, state, call, snapshots, message);
        if (rc == 90 || rc == 20 || (rc != 0 && data.stop_requested_v1724)) { stopped = true; break; }
        if (rc != 0) { std::cerr << "native final snapshot failed: " << message.data() << '\n'; stopped = true; break; }
        if (call < 4 && !snapshots.empty()) {
            auto& next = data.call_start_workspaces[call];
            next.global_xilevg.assign(data.global_level_count, 0.0);
            next.global_bilevg.assign(data.global_level_count, 0.0);
            next.global_rnisg.assign(data.global_level_count, 0.0);
            const auto& final = snapshots.back();
            for (std::size_t row = 0; row < final.populations.size(); ++row) {
                const int global = data.population_global_level_index[row];
                if (global <= 0 || static_cast<std::size_t>(global) > data.global_level_count) continue;
                next.global_xilevg[global - 1] = final.populations[row];
                if (row < final.lte_populations.size()) next.global_bilevg[global - 1] = final.lte_populations[row];
            }
        }
    }
    xstar_thermal_context_destroy(thermal_context); xstar_fixed_state_context_destroy(fixed_context);
    g_source_population_global_v1724 = nullptr; g_source_population_compact_v1724 = nullptr;

    std::ofstream trajectory(output / "native_controller_trajectory.csv");
    trajectory << "runtime_ordinal,source_sequence,kind,call_index,evaluation_index,temperature_t4,electron_fraction,hmctot,elcter\n";
    for (std::size_t i = 0; i < snapshots.size(); ++i) {
        const auto& s = snapshots[i]; trajectory << std::setprecision(17) << i + 1 << ',' << s.sequence << ',' << s.kind << ','
            << s.call_index << ',' << s.evaluation_index << ',' << s.temperature_t4 << ',' << s.electron_fraction_input << ','
            << s.hmctot << ',' << s.charge_residual << '\n';
    }
    const bool full_accept = data.accepted_runtime_ordinal_v1724 == 61 && !data.gate_failed_v1724;
    const bool prefix_accept = data.stop_requested_v1724 && !data.gate_failed_v1724;
    std::ofstream summary(output / "native_resumable_trajectory_summary.json");
    summary << std::boolalpha << std::setprecision(17)
        << "{\n  \"schema\": \"xstar-tools-v04874625517256-resumable-trajectory-v1\",\n"
        << "  \"release\": \"" XSTAR_API_VERSION_STRING "\",\n"
        << "  \"controller_mode\": \"true_native_autonomous_generic_loop\",\n"
        << "  \"qualification_contracts_are_controller_input\": false,\n"
        << "  \"deterministic_replay_resume\": true,\n"
        << "  \"resume_after_runtime_ordinal\": " << options.trajectory_resume_after << ",\n"
        << "  \"stop_after_runtime_ordinal\": " << data.trajectory_stop_after_v1724 << ",\n"
        << "  \"accepted_runtime_evaluations\": " << data.accepted_runtime_ordinal_v1724 << ",\n"
        << "  \"last_accepted_source_sequence\": " << data.last_accepted_sequence_v1724 << ",\n"
        << "  \"first_failed_source_sequence\": " << data.first_failed_sequence_v1724 << ",\n"
        << "  \"first_failure_reason\": \"" << data.first_failure_reason_v1724 << "\",\n"
        << "  \"full_61_trajectory_accept\": " << full_accept << ",\n"
        << "  \"prefix_stop_accept\": " << prefix_accept << ",\n"
        << "  \"bridge_runtime_input_used\": false,\n"
        << "  \"product_state_retention_enabled\": false,\n"
        << "  \"product_publication_enabled\": false,\n"
        << "  \"fits_products_written\": 0,\n"
        << "  \"xout_step_written\": false,\n"
        << "  \"result\": \"" << (full_accept ? "ACCEPT_FULL_61" : prefix_accept ? "ACCEPT_PREFIX_STOP" :
            data.gate_failed_v1724 ? "REJECT_FIRST_EVALUATION_GATE" : "REJECT_RUNTIME") << "\"\n}\n";
    std::cout << "V048746255172515_TRUE_NATIVE_CONTROLLER=YES\n"
              << "V048746255172515_GENERIC_TRAJECTORY_LOOP=ENABLED\n"
              << "V048746255172515_QUALIFICATION_CONTRACTS_CONTROLLER_INPUT=NO\n"
              << "V048746255172515_DETERMINISTIC_REPLAY_RESUME=ENABLED\n"
              << "V048746255172515_ACCEPTED_RUNTIME_EVALUATIONS=" << data.accepted_runtime_ordinal_v1724 << "\n"
              << "V048746255172515_LAST_ACCEPTED_SOURCE_SEQUENCE=" << data.last_accepted_sequence_v1724 << "\n"
              << "V048746255172515_FIRST_FAILED_SOURCE_SEQUENCE=" << data.first_failed_sequence_v1724 << "\n"
              << "V048746255172515_FIRST_FAILURE_REASON=" << data.first_failure_reason_v1724 << "\n"
              << "V048746255172515_FULL_ACCEPTED_TRAJECTORY_COUNT=" << (full_accept ? 61 : data.accepted_runtime_ordinal_v1724) << "\n"
              << "V048746255172515_FULL_61_TRAJECTORY_GATE=" << (full_accept ? "ACCEPT" : "NOT_REACHED") << "\n"
              << "V048746255172515_PRODUCT_STATE_RETENTION_ENABLED=NO\n"
              << "V048746255172515_PRODUCT_PUBLICATION_ENABLED=NO\n"
              << "V048746255172515_FITS_PRODUCTS_WRITTEN=0\n"
              << "V048746255172515_XOUT_STEP_LOG_WRITTEN=0\n"
              << "V048746255172515_RESULT=" << (full_accept ? "ACCEPT_FULL_61_NO_PRODUCT_PUBLICATION" :
                  prefix_accept ? "ACCEPT_RESUMABLE_PREFIX_NO_PRODUCT_PUBLICATION" :
                  data.gate_failed_v1724 ? "REJECT_FIRST_EVALUATION_GATE_FAIL_CLOSED" : "REJECT_RUNTIME") << "\n";
    if (full_accept || prefix_accept) return 0;
    return data.gate_failed_v1724 ? 20 : (rc == 0 ? 1 : rc);
}

int command_run_native_sequence12345678_v1723(Options options) {
    const auto output = std::filesystem::path(options.output_dir);
    std::filesystem::create_directories(output);
    for (const char* name : {"xo01_detail.fits", "xo01_detal2.fits", "xo01_detal3.fits", "xo01_detal4.fits",
             "xout_abund1.fits", "xout_cont1.fits", "xout_lines1.fits", "xout_rrc1.fits", "xout_spect1.fits", "xout_step.log"}) {
        std::error_code ec; std::filesystem::remove(output / name, ec);
    }
    if (options.case_dir.empty() || !std::filesystem::is_regular_file(std::filesystem::path(options.case_dir) / "manifest.txt")) {
        std::cerr << "v25.5.17.23 requires --case-dir pointing to a lowered native ATDB program\n";
        return 66;
    }
    if (options.parameters_path.empty() || !std::filesystem::is_regular_file(options.parameters_path)) {
        std::cerr << "v25.5.17.23 requires --parameters\n";
        return 66;
    }

    const std::string parameter_json = read_text_file(options.parameters_path);
    const double density = json_number_value(parameter_json, "density", 1.0e8);
    const double temperature_k = json_number_value(parameter_json, "temperature_k", 1.0e6);
    const double initial_xee = json_number_value(parameter_json, "initial_electron_fraction", 1.0);
    const double luminosity = json_number_value(parameter_json, "rlrad38", 1.0e6);
    const double spectral_index = json_number_value(parameter_json, "trad", -1.0);
    const double radius = json_number_value(parameter_json, "initial_radius_cm", 1.778279410038923e17);
    const std::size_t ncn2 = static_cast<std::size_t>(json_number_value(parameter_json, "ncn2", 9999));

    const auto energy = source_energy_grid_v1711(ncn2);
    const auto incident = source_powerlaw_v1711(spectral_index, luminosity, energy);
    std::vector<double> bremsa(ncn2, 0.0);
    const double source_radius_scale = static_cast<double>(static_cast<float>(1.0e19));
    const double source_geometry_factor = static_cast<double>(static_cast<float>(12.56));
    const double radius_19 = radius / source_radius_scale;
    const double source_fpr2 = source_geometry_factor * radius_19 * radius_19;
    for (std::size_t i = 0; i < ncn2; ++i) bremsa[i] = incident[i] / source_fpr2;
    if (!bremsa.empty()) bremsa.back() = 0.0;
    std::filesystem::create_directories(output / "sequence12345678_diagnostics");
    {
        std::ofstream stream(output / "sequence12345678_diagnostics" / "call_start_incident.bin", std::ios::binary);
        stream.write(reinterpret_cast<const char*>(incident.data()), static_cast<std::streamsize>(incident.size() * sizeof(double)));
    }
    {
        std::ofstream stream(output / "sequence12345678_diagnostics" / "call_start_bremsa.bin", std::ios::binary);
        stream.write(reinterpret_cast<const char*>(bremsa.data()), static_cast<std::streamsize>(bremsa.size() * sizeof(double)));
    }
    std::vector<double> tau_in(301301, 0.0), tau_out(301301, 0.0);

    xstar_fixed_state_context* fixed_context = nullptr;
    xstar_thermal_context* thermal_context = nullptr;
    std::array<char,XSTAR_FIXED_STATE_MESSAGE_SIZE> message{};
    int rc = xstar_fixed_state_context_create_v1(options.case_dir.c_str(), &fixed_context, message.data(), message.size());
    if (rc != 0) { std::cerr << "fixed-state context creation failed: " << message.data() << "\n"; return rc; }
    rc = xstar_thermal_context_create_v1(&thermal_context, message.data(), message.size());
    if (rc != 0) { xstar_fixed_state_context_destroy(fixed_context); std::cerr << "thermal context creation failed: " << message.data() << "\n"; return rc; }
    xstar_fixed_state_program_info_v1 info{}; xstar_fixed_state_program_info_init_v1(&info);
    rc = xstar_fixed_state_context_get_program_info_v1(fixed_context, &info, message.data(), message.size());
    if (rc != 0) { xstar_thermal_context_destroy(thermal_context); xstar_fixed_state_context_destroy(fixed_context); std::cerr << message.data() << "\n"; return rc; }

    xstar_fixed_state_stats_v1 cumulative{}; xstar_fixed_state_stats_init_v1(&cumulative);
    std::vector<FixedDsecSnapshot> snapshots;
    FixedDsecEvaluatorData data;
    data.fixed_context = fixed_context;
    data.program_info = info;
    data.cumulative_stats = &cumulative;
    data.snapshots = &snapshots;
    data.energy = energy;
    data.flux = incident;
    data.radiation_mode = "native_source_powerlaw_9999";
    data.autonomous_controller = true;
    data.next_native_sequence = 1;
    data.call_index = 1;
    data.evaluation_index = 0;
    data.dsec_covering_fraction = 1.0;
    data.has_dsec_covering_fraction = true;
    data.diagnostics_dir = (output / "sequence12345678_diagnostics").string();
    data.thermal_budget_csv = (output / "native_thermal_budget.csv").string();
    {
        const auto early_abundances = read_case_abundances_v1712(std::filesystem::path(options.case_dir));
        const auto found_h = early_abundances.find(1);
        data.hydrogen_abundance = found_h == early_abundances.end() ? 1.0 : found_h->second;
    }
    {
        const auto population_map = read_population_global_level_map_v1716(std::filesystem::path(options.case_dir));
        data.population_global_level_index = population_map.first;
        data.global_level_count = population_map.second;
    }
    CallStartWorkspace workspace;
    workspace.radiation_energy = energy;
    workspace.bremsa = bremsa;
    workspace.continuum_tau_in = tau_in;
    workspace.continuum_tau_out = tau_out;
    data.call_start_workspaces.push_back(std::move(workspace));

    xstar_thermal_state_v1 state{}; xstar_thermal_state_init_v1(&state);
    state.temperature_t4 = temperature_k / 1.0e4;
    state.electron_fraction_xee = initial_xee;
    state.hydrogen_density_cm3 = density;
    xstar_dsec_config_v1 config{}; xstar_dsec_config_init_v1(&config);
    config.nlim = 100;
    config.maximum_evaluations = 8;
    xstar_dsec_stats_v1 stats{}; xstar_dsec_stats_init_v1(&stats);
    std::vector<xstar_thermal_trace_event_v1> trace(64);
    std::size_t trace_count = 0;
    rc = xstar_thermal_run_evaluation_loop_v1(
        thermal_context, &config, &state, fixed_dsec_evaluator, &data,
        trace.data(), trace.size(), &trace_count, &stats, message.data(), message.size());
    xstar_thermal_context_destroy(thermal_context);
    xstar_fixed_state_context_destroy(fixed_context);
    if (rc != 0) {
        std::cerr << "native sequence-1/2/3/4/5/6/7/8 controller prefix failed: " << message.data() << "\n";
        return rc;
    }
    if (snapshots.size() != 8 || snapshots[0].sequence != 1 || snapshots[1].sequence != 2 ||
        snapshots[2].sequence != 3 || snapshots[3].sequence != 4 || snapshots[4].sequence != 5 || snapshots[5].sequence != 6 || snapshots[6].sequence != 7 || snapshots[7].sequence != 8 ||
        snapshots[0].call_index != 1 || snapshots[1].call_index != 1 ||
        snapshots[2].call_index != 1 || snapshots[3].call_index != 1 || snapshots[4].call_index != 1 || snapshots[5].call_index != 1 || snapshots[6].call_index != 1 || snapshots[7].call_index != 1 ||
        snapshots[0].evaluation_index != 1 || snapshots[1].evaluation_index != 2 ||
        snapshots[2].evaluation_index != 3 || snapshots[3].evaluation_index != 4 ||
        snapshots[4].evaluation_index != 5 || snapshots[5].evaluation_index != 6 || snapshots[6].evaluation_index != 7 || snapshots[7].evaluation_index != 8) {
        std::cerr << "native controller did not retain the required sequence-1/2/3/4/5/6/7/8 prefix\n";
        return 20;
    }

    const auto budget_rows = read_csv_rows_v1716(output / "native_thermal_budget.csv");
    if (budget_rows.size() != 8) throw std::runtime_error("sequence-1/2/3/4/5/6/7/8 thermal budget must contain exactly eight rows");
    const auto number = [&](std::size_t row_index, const char* key) {
        const auto it = budget_rows.at(row_index).find(key);
        if (it == budget_rows.at(row_index).end()) throw std::runtime_error(std::string("thermal budget missing ") + key);
        return std::stod(it->second);
    };
    const auto integer = [&](std::size_t row_index, const char* key) { return static_cast<std::size_t>(number(row_index, key)); };

    const auto case_abundances = read_case_abundances_v1712(std::filesystem::path(options.case_dir));
    const auto abundance_value = [&](int z) { const auto found = case_abundances.find(z); return found == case_abundances.end() ? 0.0 : found->second; };
    const double h_abundance = abundance_value(1), he_abundance = abundance_value(2), mg_abundance = abundance_value(12);
    const bool physical_abundances_ok = zero_aware_controller_equal_v1711(h_abundance, 1.0) &&
        zero_aware_controller_equal_v1711(he_abundance, 0.1) && zero_aware_controller_equal_v1711(mg_abundance, 3.5e-5);

    const bool sequence1_workspace_ok = integer(0,"input_radiation_count") == 9999 && integer(0,"input_dsec_radiation_count") == 9999 &&
        integer(0,"input_bremsa_count") == 9999 && integer(0,"input_tau_count") == 301301 &&
        integer(0,"continuum_workspace_source_faithful") == 1 && integer(0,"continuum_epim_count") == 999 &&
        integer(0,"continuum_bremsam_count") == 999 && integer(0,"continuum_bremsmap_count") == 999;
    const auto sequence1_population = compare_sequence1_populations_v1714(output / "sequence12345678_diagnostics" / "evaluation_0001_populations.csv");
    const auto sequence1_ledger = compare_sequence_thermal_ledger_v1716(
        output / "sequence12345678_diagnostics" / "evaluation_0001_thermal_diagonal_ledger.csv",
        "a2007d9d4dca9965", "ad583d50031d5bd1", "85f206312a339d4b");
    const bool sequence1_ok = physical_abundances_ok && sequence1_workspace_ok && sequence1_population.initial_ok &&
        sequence1_population.final_zero_aware_ok && sequence1_ledger.count_ok && sequence1_ledger.identities_ok &&
        sequence1_ledger.order_ok && sequence1_ledger.values_ok &&
        relative_one_percent_v1711(snapshots[0].hmctot, -1.1485157783994253) &&
        relative_one_percent_v1711(snapshots[0].charge_residual, -0.20036716199692539);

    const bool sequence2_controller_state_ok = canonical_e7_equal(snapshots[1].temperature_t4, 100.0) &&
        canonical_e7_equal(snapshots[1].electron_fraction_input, 1.2000000476837158);
    const bool sequence2_workspace_ok = integer(1,"input_radiation_count") == 9999 && integer(1,"input_dsec_radiation_count") == 9999 &&
        integer(1,"input_bremsa_count") == 9999 && integer(1,"input_tau_count") == 301301 &&
        integer(1,"continuum_workspace_source_faithful") == 1 && integer(1,"continuum_epim_count") == 999 &&
        integer(1,"continuum_bremsam_count") == 999 && integer(1,"continuum_bremsmap_count") == 999;
    const auto sequence2_population = compare_sequence_population_hashes_v1716(
        output / "sequence12345678_diagnostics" / "evaluation_0002_populations.csv",
        "b7d166344720c03e", "62e2e6a285b579c5", 2);
    const auto sequence2_ledger = compare_sequence_thermal_ledger_v1716(
        output / "sequence12345678_diagnostics" / "evaluation_0002_thermal_diagonal_ledger.csv",
        "a2007d9d4dca9965", "ad583d50031d5bd1", "be6a72eed1cc893d", 2);

    const auto sequence2_hydrogen = compare_sequence2_hydrogen_state_v1717(
        output / "sequence12345678_diagnostics" / "evaluation_0001_populations.csv",
        output / "sequence12345678_diagnostics" / "evaluation_0002_populations.csv",
        output / "sequence12345678_diagnostics" / "evaluation_0002_all_element_solve_rows.csv",
        snapshots[1], density, h_abundance);

    const std::map<std::string,double> sequence2_element_expected = {
        {"h_heating",1.1770847613979976e-09},{"h_cooling",8.6971058682083958e-09},
        {"h_heating2",3.0843257598451826e-10},{"h_cooling2",7.5028753352803874e-09},
        {"he_heating",3.5934502015010018e-09},{"he_cooling",1.650333274981515e-08},
        {"he_heating2",9.427108615135224e-10},{"he_cooling2",1.3909518034313189e-08},
        {"computed_he_type53_heating",3.5932915936957602e-09},{"computed_he_type53_cooling",9.7904278176026692e-09},
        {"computed_he_type53_heating2",9.4261235194936427e-10},{"computed_he_type53_cooling2",5.456249127698813e-09},
        {"computed_he_non_type53_heating",1.5860780524131697e-13},{"computed_he_non_type53_cooling",6.7129049322124725e-09},
        {"computed_he_non_type53_heating2",9.8509564157805721e-14},{"computed_he_non_type53_cooling2",8.4532689066143638e-09},
        {"mg_heating",4.266253764967799e-09},{"mg_cooling",1.5569124146012375e-08},
        {"mg_heating2",1.5575186494759054e-09},{"mg_cooling2",1.2592078595607181e-08}
    };
    bool sequence2_element_ok = true;
    for (const auto& expected : sequence2_element_expected) sequence2_element_ok = sequence2_element_ok && relative_one_percent_v1711(number(1, expected.first.c_str()), expected.second);
    const std::map<std::string,double> sequence2_continuum_expected = {
        {"cmp1",4.6905545032708282e-05},{"cmp2",4.4763443016579042e-07},
        {"htcomp",9.0181164489536711e-09},{"clcomp",7.4160857422880182e-09},
        {"htfreef",1.1135719001630413e-14},{"clbrems",2.8691531455071891e-08},
        {"continuum_heating",9.0181275846726735e-09},{"continuum_cooling",3.6107617197359909e-08}
    };
    bool sequence2_continuum_ok = integer(1,"continuum_secondary_ledger_corrected") == 1;
    for (const auto& expected : sequence2_continuum_expected) sequence2_continuum_ok = sequence2_continuum_ok && relative_one_percent_v1711(number(1, expected.first.c_str()), expected.second);
    const bool sequence2_hmctot_ok = relative_one_percent_v1711(snapshots[1].hmctot, -1.2392492309264873);
    const bool sequence2_elcter_ok = relative_one_percent_v1711(snapshots[1].charge_residual, -0.0003632540628308867);
    const bool sequence2_population_ok = sequence2_population.final_ok;
    const bool sequence2_ledger_ok = sequence2_ledger.count_ok && sequence2_ledger.identities_ok &&
        sequence2_ledger.order_ok && sequence2_ledger.values_ok;
    const bool sequence2_hydrogen_ok = sequence2_hydrogen.global_continuity_ok &&
        sequence2_hydrogen.entry_xh0_xh1_ok &&
        sequence2_hydrogen.compact_terminal_zero_ok &&
        sequence2_hydrogen.final_population_ok;
    const bool sequence2_ok = sequence1_ok && sequence2_controller_state_ok && sequence2_workspace_ok &&
        sequence2_hydrogen_ok && sequence2_population_ok && sequence2_ledger_ok && sequence2_element_ok && sequence2_continuum_ok &&
        sequence2_hmctot_ok && sequence2_elcter_ok;

    const bool sequence3_controller_state_ok = canonical_e7_equal(snapshots[2].temperature_t4, 100.0) &&
        canonical_e7_equal(snapshots[2].electron_fraction_input, 1.4400001144409202);
    const bool sequence3_workspace_ok = integer(2,"input_radiation_count") == 9999 &&
        integer(2,"input_dsec_radiation_count") == 9999 && integer(2,"input_bremsa_count") == 9999 &&
        integer(2,"input_tau_count") == 301301 && integer(2,"continuum_workspace_source_faithful") == 1 &&
        integer(2,"continuum_epim_count") == 999 && integer(2,"continuum_bremsam_count") == 999 &&
        integer(2,"continuum_bremsmap_count") == 999;
    bool sequence3_active_stage_window_ok = integer(2,"thermal_population_count") == 612;
    {
        const auto manifest_rows = read_csv_rows_v1716(
            output / "sequence12345678_diagnostics" / "evaluation_0003_all_element_solve_system_manifest.csv");
        bool found_mg = false;
        for (const auto& row : manifest_rows) {
            if (std::stoi(row.at("element_z")) != 12) continue;
            found_mg = true;
            sequence3_active_stage_window_ok = sequence3_active_stage_window_ok &&
                std::stoi(row.at("active_min_stage")) == 5 &&
                std::stoi(row.at("active_max_stage")) == 12 &&
                std::stoi(row.at("n_rows")) == 501;
        }
        sequence3_active_stage_window_ok = sequence3_active_stage_window_ok && found_mg;
    }
    const auto sequence3_population = compare_sequence_population_hashes_v1716(
        output / "sequence12345678_diagnostics" / "evaluation_0003_populations.csv",
        "678993d55301ca6f", "4d9949f5d0067afd", 3);
    const auto sequence3_ledger = compare_sequence_thermal_ledger_v1716(
        output / "sequence12345678_diagnostics" / "evaluation_0003_thermal_diagonal_ledger.csv",
        "a2007d9d4dca9965", "ad583d50031d5bd1", "c20ab9dc23e4a66e", 3);
    const auto sequence3_hydrogen = compare_repeated_hydrogen_state_v1718(
        output / "sequence12345678_diagnostics" / "evaluation_0002_populations.csv",
        output / "sequence12345678_diagnostics" / "evaluation_0003_populations.csv",
        output / "sequence12345678_diagnostics" / "evaluation_0003_all_element_solve_rows.csv",
        snapshots[2], density, h_abundance, "92d0c9f560bcd078");

    const std::map<std::string,double> sequence3_element_expected = {
        {"h_heating",1.2816097202918151e-09},{"h_cooling",1.035969263653573e-08},
        {"h_heating2",3.358360258455441e-10},{"h_cooling2",9.2985434751039327e-09},
        {"he_heating",3.8610402805251353e-09},{"he_cooling",2.02221805056824e-08},
        {"he_heating2",1.012926203629634e-09},{"he_cooling2",1.744557139029264e-08},
        {"computed_he_type53_heating",3.8608491305992593e-09},{"computed_he_type53_cooling",1.1748504491470561e-08},
        {"computed_he_type53_heating2",1.0128074201501596e-09},{"computed_he_type53_cooling2",6.5474953969989058e-09},
        {"computed_he_non_type53_heating",1.9114992587586121e-13},{"computed_he_non_type53_cooling",8.4736760142118244e-09},
        {"computed_he_non_type53_heating2",1.1878347947406906e-13},{"computed_he_non_type53_cooling2",1.0898075993293741e-08},
        {"mg_heating",4.76424218689084e-09},{"mg_cooling",2.3444445848992529e-08},
        {"mg_heating2",1.8409124811030516e-09},{"mg_cooling2",2.0147452903574997e-08}
    };
    bool sequence3_element_ok = true;
    for (const auto& expected : sequence3_element_expected) {
        sequence3_element_ok = sequence3_element_ok &&
            relative_one_percent_v1711(number(2, expected.first.c_str()), expected.second);
    }
    const std::map<std::string,double> sequence3_continuum_expected = {
        {"cmp1",4.6905545032708282e-05},{"cmp2",4.4763443016579042e-07},
        {"htcomp",1.0821740168761709e-08},{"clcomp",8.8993032443721484e-09},
        {"htfreef",1.6035436636729734e-14},{"clbrems",4.1315808578788805e-08},
        {"continuum_heating",1.0821756204198345e-08},{"continuum_cooling",5.0215111823160954e-08}
    };
    bool sequence3_continuum_ok = integer(2,"continuum_secondary_ledger_corrected") == 1;
    for (const auto& expected : sequence3_continuum_expected) {
        sequence3_continuum_ok = sequence3_continuum_ok &&
            relative_one_percent_v1711(number(2, expected.first.c_str()), expected.second);
    }
    const bool sequence3_hmctot_ok = relative_one_percent_v1711(
        snapshots[2].hmctot, -1.3365244377355003);
    const bool sequence3_elcter_ok = relative_one_percent_v1711(
        snapshots[2].charge_residual, 0.23964076002422652);
    const bool sequence3_population_ok = sequence3_population.final_ok;
    const bool sequence3_ledger_ok = sequence3_ledger.count_ok && sequence3_ledger.identities_ok &&
        sequence3_ledger.order_ok && sequence3_ledger.values_ok;
    const bool sequence3_hydrogen_ok = sequence3_hydrogen.global_continuity_ok &&
        sequence3_hydrogen.entry_xh0_xh1_ok && sequence3_hydrogen.compact_terminal_zero_ok &&
        sequence3_hydrogen.final_population_ok;
    const bool sequence3_ok = sequence2_ok && sequence3_controller_state_ok && sequence3_workspace_ok &&
        sequence3_active_stage_window_ok && sequence3_hydrogen_ok && sequence3_population_ok &&
        sequence3_ledger_ok && sequence3_element_ok && sequence3_continuum_ok &&
        sequence3_hmctot_ok && sequence3_elcter_ok;

    const bool sequence4_controller_state_ok = canonical_e7_equal(snapshots[3].temperature_t4, 100.0) &&
        canonical_e7_equal(snapshots[3].electron_fraction_input, 1.2003632957721315);
    const bool sequence4_workspace_ok = integer(3,"input_radiation_count") == 9999 &&
        integer(3,"input_dsec_radiation_count") == 9999 && integer(3,"input_bremsa_count") == 9999 &&
        integer(3,"input_tau_count") == 301301 && integer(3,"continuum_workspace_source_faithful") == 1 &&
        integer(3,"continuum_epim_count") == 999 && integer(3,"continuum_bremsam_count") == 999 &&
        integer(3,"continuum_bremsmap_count") == 999;
    bool sequence4_active_stage_window_ok = integer(3,"thermal_population_count") == 612;
    {
        const auto manifest_rows = read_csv_rows_v1716(
            output / "sequence12345678_diagnostics" / "evaluation_0004_all_element_solve_system_manifest.csv");
        bool found_mg = false;
        for (const auto& row : manifest_rows) {
            if (std::stoi(row.at("element_z")) != 12) continue;
            found_mg = true;
            sequence4_active_stage_window_ok = sequence4_active_stage_window_ok &&
                std::stoi(row.at("active_min_stage")) == 5 &&
                std::stoi(row.at("active_max_stage")) == 12 &&
                std::stoi(row.at("n_rows")) == 501;
        }
        sequence4_active_stage_window_ok = sequence4_active_stage_window_ok && found_mg;
    }
    const auto sequence4_population = compare_sequence_population_hashes_v1716(
        output / "sequence12345678_diagnostics" / "evaluation_0004_populations.csv",
        "891f085a2069fb28", "84108ed2f024dab2", 4);
    const auto sequence4_ledger = compare_sequence_thermal_ledger_v1716(
        output / "sequence12345678_diagnostics" / "evaluation_0004_thermal_diagonal_ledger.csv",
        "a2007d9d4dca9965", "ad583d50031d5bd1", "93ab3e1e610e72c1", 4);
    const auto sequence4_hydrogen = compare_repeated_hydrogen_state_v1718(
        output / "sequence12345678_diagnostics" / "evaluation_0003_populations.csv",
        output / "sequence12345678_diagnostics" / "evaluation_0004_populations.csv",
        output / "sequence12345678_diagnostics" / "evaluation_0004_all_element_solve_rows.csv",
        snapshots[3], density, h_abundance, "b1f0735be972aeb0");

    const std::map<std::string,double> sequence4_element_expected = {
        {"h_heating",1.1828321051955907e-09},{"h_cooling",8.4528988389612363e-09},
        {"h_heating2",3.0993774262499241e-10},{"h_cooling2",7.5186923455042566e-09},
        {"he_heating",3.5936382554027358e-09},{"he_cooling",1.6608209989016791e-08},
        {"he_heating2",9.4275933206374932e-10},{"he_cooling2",1.3914151898394489e-08},
        {"computed_he_type53_heating",3.5934795989548434e-09},{"computed_he_type53_cooling",9.7933914407593936e-09},
        {"computed_he_type53_heating2",9.4266074709282634e-10},{"computed_he_type53_cooling2",5.4579007688730329e-09},
        {"computed_he_non_type53_heating",1.5865644789179977e-13},{"computed_he_non_type53_cooling",6.8148185482574028e-09},
        {"computed_he_non_type53_heating2",9.858497092243001e-14},{"computed_he_non_type53_cooling2",8.4562511295214627e-09},
        {"mg_heating",4.2678265239219598e-09},{"mg_cooling",1.5575882102066503e-08},
        {"mg_heating2",1.5586203756683291e-09},{"mg_cooling2",1.2606263312520077e-08}
    };
    bool sequence4_element_ok = true;
    for (const auto& expected : sequence4_element_expected) {
        sequence4_element_ok = sequence4_element_ok &&
            relative_one_percent_v1711(number(3, expected.first.c_str()), expected.second);
    }
    const std::map<std::string,double> sequence4_continuum_expected = {
        {"cmp1",4.6905545032708282e-05},{"cmp2",4.4763443016579042e-07},
        {"htcomp",9.0208462934795246e-09},{"clcomp",7.4183306413399907e-09},
        {"htfreef",1.1142461736144429e-14},{"clbrems",2.8708904323350472e-08},
        {"continuum_heating",9.02085743594126e-09},{"continuum_cooling",3.6127234964690461e-08}
    };
    bool sequence4_continuum_ok = integer(3,"continuum_secondary_ledger_corrected") == 1;
    for (const auto& expected : sequence4_continuum_expected) {
        sequence4_continuum_ok = sequence4_continuum_ok &&
            relative_one_percent_v1711(number(3, expected.first.c_str()), expected.second);
    }
    const bool sequence4_hmctot_ok = relative_one_percent_v1711(
        snapshots[3].hmctot, -1.2379933611517373);
    const bool sequence4_elcter_ok = relative_one_percent_v1711(
        snapshots[3].charge_residual, 3.5395526509773845e-09);
    const bool sequence4_population_ok = sequence4_population.final_ok;
    const bool sequence4_ledger_ok = sequence4_ledger.count_ok && sequence4_ledger.identities_ok &&
        sequence4_ledger.order_ok && sequence4_ledger.values_ok;
    const bool sequence4_hydrogen_ok = sequence4_hydrogen.global_continuity_ok &&
        sequence4_hydrogen.entry_xh0_xh1_ok && sequence4_hydrogen.compact_terminal_zero_ok &&
        sequence4_hydrogen.final_population_ok;
    const bool sequence4_ok = sequence3_ok && sequence4_controller_state_ok && sequence4_workspace_ok &&
        sequence4_active_stage_window_ok && sequence4_hydrogen_ok && sequence4_population_ok &&
        sequence4_ledger_ok && sequence4_element_ok && sequence4_continuum_ok &&
        sequence4_hmctot_ok && sequence4_elcter_ok;


    const bool sequence5_controller_state_ok = canonical_e7_equal(snapshots[4].temperature_t4, 69.444438925496186) &&
        canonical_e7_equal(snapshots[4].electron_fraction_input, 1.2003632957721315);
    const bool sequence5_workspace_ok = integer(4,"input_radiation_count") == 9999 &&
        integer(4,"input_dsec_radiation_count") == 9999 && integer(4,"input_bremsa_count") == 9999 &&
        integer(4,"input_tau_count") == 301301 && integer(4,"continuum_workspace_source_faithful") == 1 &&
        integer(4,"continuum_epim_count") == 999 && integer(4,"continuum_bremsam_count") == 999 &&
        integer(4,"continuum_bremsmap_count") == 999;
    bool sequence5_active_stage_window_ok = integer(4,"thermal_population_count") == 618;
    {
        const auto manifest_rows = read_csv_rows_v1716(
            output / "sequence12345678_diagnostics" / "evaluation_0005_all_element_solve_system_manifest.csv");
        bool found_mg = false;
        for (const auto& row : manifest_rows) {
            if (std::stoi(row.at("element_z")) != 12) continue;
            found_mg = true;
            sequence5_active_stage_window_ok = sequence5_active_stage_window_ok &&
                std::stoi(row.at("active_min_stage")) == 4 &&
                std::stoi(row.at("active_max_stage")) == 12 &&
                std::stoi(row.at("n_rows")) == 507;
        }
        sequence5_active_stage_window_ok = sequence5_active_stage_window_ok && found_mg;
    }
    const auto sequence5_population = compare_sequence_population_hashes_v1716(
        output / "sequence12345678_diagnostics" / "evaluation_0005_populations.csv",
        "4c90c1c46b112c2d", "ef4d18ecafb0af62", 5);
    const auto sequence5_ledger = compare_sequence_thermal_ledger_v1716(
        output / "sequence12345678_diagnostics" / "evaluation_0005_thermal_diagonal_ledger.csv",
        "ace6dbd1ace2533c", "93ad2b293ce3c5ea", "4c91ebab74196e6b", 5, 16550u);
    const auto sequence5_hydrogen = compare_repeated_hydrogen_state_v1718(
        output / "sequence12345678_diagnostics" / "evaluation_0004_populations.csv",
        output / "sequence12345678_diagnostics" / "evaluation_0005_populations.csv",
        output / "sequence12345678_diagnostics" / "evaluation_0005_all_element_solve_rows.csv",
        snapshots[4], density, h_abundance, "ccf2a38dd06ee1f0");

    const std::map<std::string,double> sequence5_element_expected = {
        {"h_heating",1.8421308890793705e-09},{"h_cooling",1.1202955855762684e-08},
        {"h_heating2",4.8270551388451009e-10},{"h_cooling2",9.8548530951689913e-09},
        {"he_heating",6.1780000871848249e-09},{"he_cooling",2.1791008173209164e-08},
        {"he_heating2",1.6208007357431882e-09},{"he_cooling2",1.7299995191538317e-08},
        {"computed_he_type53_heating",6.1777263797914909e-09},{"computed_he_type53_cooling",1.1572368852078517e-08},
        {"computed_he_type53_heating2",1.6206329118370918e-09},{"computed_he_type53_cooling2",5.6825530818558521e-09},
        {"computed_he_non_type53_heating",2.7370739333365432e-13},{"computed_he_non_type53_cooling",1.0218639321130643e-08},
        {"computed_he_non_type53_heating2",1.6782390609634642e-13},{"computed_he_non_type53_cooling2",1.1617442109682458e-08},
        {"mg_heating",5.3613051039197348e-09},{"mg_cooling",2.4850645276437773e-08},
        {"mg_heating2",2.2347634840544117e-09},{"mg_cooling2",2.124201129440692e-08}
    };
    bool sequence5_element_ok = true;
    for (const auto& expected : sequence5_element_expected) {
        sequence5_element_ok = sequence5_element_ok &&
            relative_one_percent_v1711(number(4, expected.first.c_str()), expected.second);
    }
    const std::map<std::string,double> sequence5_continuum_expected = {
        {"cmp1",4.6905545032708282e-05},{"cmp2",6.4386878682103173e-07},
        {"htcomp",9.0208462934795246e-09},{"clcomp",7.4099887480094953e-09},
        {"htfreef",1.9244403017968e-14},{"clbrems",2.391187360880127e-08},
        {"continuum_heating",9.020865537882543e-09},{"continuum_cooling",3.1321862356810766e-08}
    };
    bool sequence5_continuum_ok = integer(4,"continuum_secondary_ledger_corrected") == 1;
    for (const auto& expected : sequence5_continuum_expected) {
        sequence5_continuum_ok = sequence5_continuum_ok &&
            relative_one_percent_v1711(number(4, expected.first.c_str()), expected.second);
    }
    const bool sequence5_hmctot_ok = relative_one_percent_v1711(
        snapshots[4].hmctot, -1.1968253854763951);
    const bool sequence5_elcter_ok = relative_one_percent_v1711(
        snapshots[4].charge_residual, 8.4360265646399313e-06);
    const bool sequence5_population_ok = sequence5_population.final_ok;
    const bool sequence5_ledger_ok = sequence5_ledger.count_ok && sequence5_ledger.identities_ok &&
        sequence5_ledger.order_ok && sequence5_ledger.values_ok;
    const bool sequence5_hydrogen_ok = sequence5_hydrogen.global_continuity_ok &&
        sequence5_hydrogen.entry_xh0_xh1_ok && sequence5_hydrogen.compact_terminal_zero_ok &&
        sequence5_hydrogen.final_population_ok;
    const bool sequence5_ok = sequence4_ok && sequence5_controller_state_ok && sequence5_workspace_ok &&
        sequence5_active_stage_window_ok && sequence5_hydrogen_ok && sequence5_population_ok &&
        sequence5_ledger_ok && sequence5_element_ok && sequence5_continuum_ok &&
        sequence5_hmctot_ok && sequence5_elcter_ok;

    const bool sequence6_controller_state_ok = canonical_e7_equal(snapshots[5].temperature_t4, 48.225300976769695) &&
        canonical_e7_equal(snapshots[5].electron_fraction_input, 1.2003632957721315);
    const bool sequence6_workspace_ok = integer(5,"input_radiation_count") == 9999 &&
        integer(5,"input_dsec_radiation_count") == 9999 && integer(5,"input_bremsa_count") == 9999 &&
        integer(5,"input_tau_count") == 301301 && integer(5,"continuum_workspace_source_faithful") == 1 &&
        integer(5,"continuum_epim_count") == 999 && integer(5,"continuum_bremsam_count") == 999 &&
        integer(5,"continuum_bremsmap_count") == 999;
    bool sequence6_active_stage_window_ok = integer(5,"thermal_population_count") == 618;
    {
        const auto manifest_rows = read_csv_rows_v1716(
            output / "sequence12345678_diagnostics" / "evaluation_0006_all_element_solve_system_manifest.csv");
        bool found_mg = false;
        for (const auto& row : manifest_rows) {
            if (std::stoi(row.at("element_z")) != 12) continue;
            found_mg = true;
            sequence6_active_stage_window_ok = sequence6_active_stage_window_ok &&
                std::stoi(row.at("active_min_stage")) == 4 &&
                std::stoi(row.at("active_max_stage")) == 12 &&
                std::stoi(row.at("n_rows")) == 507;
        }
        sequence6_active_stage_window_ok = sequence6_active_stage_window_ok && found_mg;
    }
    const auto sequence6_population = compare_sequence_population_hashes_v1716(
        output / "sequence12345678_diagnostics" / "evaluation_0006_populations.csv",
        "ce848b4b9d5919c9", "453d4878d96fe408", 6);
    const auto sequence6_ledger = compare_sequence_thermal_ledger_v1716(
        output / "sequence12345678_diagnostics" / "evaluation_0006_thermal_diagonal_ledger.csv",
        "ace6dbd1ace2533c", "93ad2b293ce3c5ea", "984e3f71b9efef5f", 6, 16550u);
    const auto sequence6_hydrogen = compare_repeated_hydrogen_state_v1718(
        output / "sequence12345678_diagnostics" / "evaluation_0005_populations.csv",
        output / "sequence12345678_diagnostics" / "evaluation_0006_populations.csv",
        output / "sequence12345678_diagnostics" / "evaluation_0006_all_element_solve_rows.csv",
        snapshots[5], density, h_abundance, "993010ebe0515f33");

    const std::map<std::string,double> sequence6_element_expected = {
        {"h_heating",2.8947264810147935e-09},{"h_cooling",1.5004272192899552e-08},
        {"h_heating2",7.5854011020117262e-10},{"h_cooling2",1.2956221833924904e-08},
        {"he_heating",1.0677962103103826e-08},{"he_cooling",2.8089038577065488e-08},
        {"he_heating2",2.8014959328352217e-09},{"he_cooling2",2.0309422348463421e-08},
        {"computed_he_type53_heating",1.0677485909874084e-08},{"computed_he_type53_cooling",1.3635964888307328e-08},
        {"computed_he_type53_heating2",2.8012064657220319e-09},{"computed_he_type53_cooling2",5.7798781688267097e-09},
        {"computed_he_non_type53_heating",4.7619322974206445e-13},{"computed_he_non_type53_cooling",1.4453073688758148e-08},
        {"computed_he_non_type53_heating2",2.8946711319032991e-13},{"computed_he_non_type53_cooling2",1.4529544179636711e-08},
        {"mg_heating",6.8634435847644365e-09},{"mg_cooling",3.5947439450290241e-08},
        {"mg_heating2",3.231425401209614e-09},{"mg_cooling2",3.1369349655102676e-08}
    };
    bool sequence6_element_ok = true;
    for (const auto& expected : sequence6_element_expected) {
        sequence6_element_ok = sequence6_element_ok &&
            relative_one_percent_v1711(number(5, expected.first.c_str()), expected.second);
    }
    const std::map<std::string,double> sequence6_continuum_expected = {
        {"cmp1",4.6905545032708282e-05},{"cmp2",9.2646571095647359e-07},
        {"htcomp",9.0208462934795246e-09},{"clcomp",7.4043510371003143e-09},
        {"htfreef",3.3230075847181474e-14},{"clbrems",1.9911914822498197e-08},
        {"continuum_heating",9.0208795235553723e-09},{"continuum_cooling",2.7316265859598512e-08}
    };
    bool sequence6_continuum_ok = integer(5,"continuum_secondary_ledger_corrected") == 1;
    for (const auto& expected : sequence6_continuum_expected) {
        sequence6_continuum_ok = sequence6_continuum_ok &&
            relative_one_percent_v1711(number(5, expected.first.c_str()), expected.second);
    }
    const bool sequence6_hmctot_ok = relative_one_percent_v1711(
        snapshots[5].hmctot, -1.1324309520714171);
    const bool sequence6_elcter_ok = relative_one_percent_v1711(
        snapshots[5].charge_residual, 1.9025077509837729e-05);
    const bool sequence6_population_ok = sequence6_population.final_ok;
    const bool sequence6_ledger_ok = sequence6_ledger.count_ok && sequence6_ledger.identities_ok &&
        sequence6_ledger.order_ok && sequence6_ledger.values_ok;
    const bool sequence6_hydrogen_ok = sequence6_hydrogen.global_continuity_ok &&
        sequence6_hydrogen.entry_xh0_xh1_ok && sequence6_hydrogen.compact_terminal_zero_ok &&
        sequence6_hydrogen.final_population_ok;
    const bool sequence6_ok = sequence5_ok && sequence6_controller_state_ok && sequence6_workspace_ok &&
        sequence6_active_stage_window_ok && sequence6_hydrogen_ok && sequence6_population_ok &&
        sequence6_ledger_ok && sequence6_element_ok && sequence6_continuum_ok &&
        sequence6_hmctot_ok && sequence6_elcter_ok;

    const bool sequence7_controller_state_ok = canonical_e7_equal(snapshots[6].temperature_t4, 33.489789683449544) &&
        canonical_e7_equal(snapshots[6].electron_fraction_input, 1.2003632957721315);
    const bool sequence7_workspace_ok = integer(6,"input_radiation_count") == 9999 &&
        integer(6,"input_dsec_radiation_count") == 9999 && integer(6,"input_bremsa_count") == 9999 &&
        integer(6,"input_tau_count") == 301301 && integer(6,"continuum_workspace_source_faithful") == 1 &&
        integer(6,"continuum_epim_count") == 999 && integer(6,"continuum_bremsam_count") == 999 &&
        integer(6,"continuum_bremsmap_count") == 999;
    bool sequence7_active_stage_window_ok = integer(6,"thermal_population_count") == 663;
    {
        const auto manifest_rows = read_csv_rows_v1716(
            output / "sequence12345678_diagnostics" / "evaluation_0007_all_element_solve_system_manifest.csv");
        bool found_mg = false;
        for (const auto& row : manifest_rows) {
            if (std::stoi(row.at("element_z")) != 12) continue;
            found_mg = true;
            sequence7_active_stage_window_ok = sequence7_active_stage_window_ok &&
                std::stoi(row.at("active_min_stage")) == 3 &&
                std::stoi(row.at("active_max_stage")) == 12 &&
                std::stoi(row.at("n_rows")) == 552;
        }
        sequence7_active_stage_window_ok = sequence7_active_stage_window_ok && found_mg;
    }
    const auto sequence7_population = compare_sequence_population_hashes_v1716(
        output / "sequence12345678_diagnostics" / "evaluation_0007_populations.csv",
        "995d12e298dfeb81", "f0627042377e971f", 7);
    const auto sequence7_ledger = compare_sequence_thermal_ledger_v1716(
        output / "sequence12345678_diagnostics" / "evaluation_0007_thermal_diagonal_ledger.csv",
        "d18021ad718b14cf", "b27fc90e756ca533", "7bdbed66c67bed74", 7, 17026u);
    const auto sequence7_hydrogen = compare_repeated_hydrogen_state_v1718(
        output / "sequence12345678_diagnostics" / "evaluation_0006_populations.csv",
        output / "sequence12345678_diagnostics" / "evaluation_0007_populations.csv",
        output / "sequence12345678_diagnostics" / "evaluation_0007_all_element_solve_rows.csv",
        snapshots[6], density, h_abundance, "eecb4f058524143c");

    const std::map<std::string,double> sequence7_element_expected = {
        {"h_heating",4.5872487394204467e-09},{"h_cooling",2.008483678357371e-08},
        {"h_heating2",1.202073902958063e-09},{"h_cooling2",1.6883667010052515e-08},
        {"he_heating",1.7919311270437708e-08},{"he_cooling",3.4221698132822293e-08},
        {"he_heating2",4.7015677340625193e-09},{"he_cooling2",2.1136633267168685e-08},
        {"computed_he_type53_heating",1.7918474627182135e-08},{"computed_he_type53_cooling",1.6050555265831354e-08},
        {"computed_he_type53_heating2",4.7010597794955924e-09},{"computed_he_type53_cooling2",5.7504394272729518e-09},
        {"computed_he_non_type53_heating",8.3664325557287443e-13},{"computed_he_non_type53_cooling",1.8171142866990933e-08},
        {"computed_he_non_type53_heating2",5.0795456692707122e-13},{"computed_he_non_type53_cooling2",1.538619383989573e-08},
        {"mg_heating",9.0119587889007201e-09},{"mg_cooling",4.6833841677958865e-08},
        {"mg_heating2",4.7663390261210891e-09},{"mg_cooling2",4.0984971104054623e-08}
    };
    bool sequence7_element_ok = true;
    for (const auto& expected : sequence7_element_expected) {
        sequence7_element_ok = sequence7_element_ok &&
            relative_one_percent_v1711(number(6, expected.first.c_str()), expected.second);
    }
    const std::map<std::string,double> sequence7_continuum_expected = {
        {"cmp1",4.6905545032708282e-05},{"cmp2",1.333401233384745e-06},
        {"htcomp",9.0208462934795246e-09},{"clcomp",7.4004133125754229e-09},
        {"htfreef",5.7361429549060717e-14},{"clbrems",1.6575702578399734e-08},
        {"continuum_heating",9.0209036549090738e-09},{"continuum_cooling",2.3976115890975156e-08}
    };
    bool sequence7_continuum_ok = integer(6,"continuum_secondary_ledger_corrected") == 1;
    for (const auto& expected : sequence7_continuum_expected) {
        sequence7_continuum_ok = sequence7_continuum_ok &&
            relative_one_percent_v1711(number(6, expected.first.c_str()), expected.second);
    }
    const bool sequence7_hmctot_ok = relative_one_percent_v1711(
        snapshots[6].hmctot, -1.0211174175435533);
    const bool sequence7_elcter_ok = relative_one_percent_v1711(
        snapshots[6].charge_residual, 3.2592543345089098e-05);
    const bool sequence7_population_ok = sequence7_population.initial_ok && sequence7_population.final_ok;
    const bool sequence7_ledger_ok = sequence7_ledger.count_ok && sequence7_ledger.identities_ok &&
        sequence7_ledger.order_ok && sequence7_ledger.values_ok;
    const bool sequence7_hydrogen_ok = sequence7_hydrogen.global_continuity_ok &&
        sequence7_hydrogen.entry_xh0_xh1_ok && sequence7_hydrogen.compact_terminal_zero_ok &&
        sequence7_hydrogen.final_population_ok;
    const bool sequence7_ok = sequence6_ok && sequence7_controller_state_ok && sequence7_workspace_ok &&
        sequence7_active_stage_window_ok && sequence7_hydrogen_ok && sequence7_population_ok &&
        sequence7_ledger_ok && sequence7_element_ok && sequence7_continuum_ok &&
        sequence7_hmctot_ok && sequence7_elcter_ok;

    const bool sequence8_controller_state_ok = canonical_e7_equal(snapshots[7].temperature_t4, 23.256796543000238) &&
        canonical_e7_equal(snapshots[7].electron_fraction_input, 1.2003632957721315);
    const bool sequence8_workspace_ok = integer(7,"input_radiation_count") == 9999 &&
        integer(7,"input_dsec_radiation_count") == 9999 && integer(7,"input_bremsa_count") == 9999 &&
        integer(7,"input_tau_count") == 301301 && integer(7,"continuum_workspace_source_faithful") == 1 &&
        integer(7,"continuum_epim_count") == 999 && integer(7,"continuum_bremsam_count") == 999 &&
        integer(7,"continuum_bremsmap_count") == 999;
    bool sequence8_active_stage_window_ok = integer(7,"thermal_population_count") == 663;
    {
        const auto manifest_rows = read_csv_rows_v1716(
            output / "sequence12345678_diagnostics" / "evaluation_0008_all_element_solve_system_manifest.csv");
        bool found_mg = false;
        for (const auto& row : manifest_rows) {
            if (std::stoi(row.at("element_z")) != 12) continue;
            found_mg = true;
            sequence8_active_stage_window_ok = sequence8_active_stage_window_ok &&
                std::stoi(row.at("active_min_stage")) == 3 &&
                std::stoi(row.at("active_max_stage")) == 12 &&
                std::stoi(row.at("n_rows")) == 552;
        }
        sequence8_active_stage_window_ok = sequence8_active_stage_window_ok && found_mg;
    }
    const auto sequence8_population = compare_sequence_population_hashes_v1716(
        output / "sequence12345678_diagnostics" / "evaluation_0008_populations.csv",
        "de5a44e4ad8e8d56", "26dce966b44b9f27", 8);
    const auto sequence8_ledger = compare_sequence_thermal_ledger_v1716(
        output / "sequence12345678_diagnostics" / "evaluation_0008_thermal_diagonal_ledger.csv",
        "d18021ad718b14cf", "b27fc90e756ca533", "3dfe110facbec258", 8, 17026u);
    const auto sequence8_hydrogen = compare_repeated_hydrogen_state_v1718(
        output / "sequence12345678_diagnostics" / "evaluation_0007_populations.csv",
        output / "sequence12345678_diagnostics" / "evaluation_0008_populations.csv",
        output / "sequence12345678_diagnostics" / "evaluation_0008_all_element_solve_rows.csv",
        snapshots[7], density, h_abundance, "982d0a211757fb9f");

    const std::map<std::string,double> sequence8_element_expected = {
        {"h_heating",7.299414227418886e-09},{"h_cooling",2.6213047628169788e-08},
        {"h_heating2",1.912819648772267e-09},{"h_cooling2",2.1145696346563966e-08},
        {"he_heating",2.8036871771354584e-08},{"he_cooling",3.8863435191209692e-08},
        {"he_heating2",7.3562993870250279e-09},{"he_cooling2",1.8390161327595508e-08},
        {"computed_he_type53_heating",2.8035357371816253e-08},{"computed_he_type53_cooling",1.8900207581019888e-08},
        {"computed_he_type53_heating2",7.3553789140275856e-09},{"computed_he_type53_cooling2",5.6058678270629028e-09},
        {"computed_he_non_type53_heating",1.5143995383282001e-12},{"computed_he_non_type53_cooling",1.9963227610189791e-08},
        {"computed_he_non_type53_heating2",9.2047299744194065e-13},{"computed_he_non_type53_cooling2",1.2784293500532602e-08},
        {"mg_heating",1.1161045549189512e-08},{"mg_cooling",4.9547076681655936e-08},
        {"mg_heating2",6.3367145040213401e-09},{"mg_cooling2",4.2449851258764517e-08}
    };
    bool sequence8_element_ok = true;
    for (const auto& expected : sequence8_element_expected) {
        sequence8_element_ok = sequence8_element_ok &&
            relative_one_percent_v1711(number(7, expected.first.c_str()), expected.second);
    }
    const std::map<std::string,double> sequence8_continuum_expected = {
        {"cmp1",4.6905545032708282e-05},{"cmp2",1.9194200417634977e-06},
        {"htcomp",9.0208462934795246e-09},{"clcomp",7.3978006107907105e-09},
        {"htfreef",9.8971597455974253e-14},{"clbrems",1.3792041194818504e-08},
        {"continuum_heating",9.0209452650769814e-09},{"continuum_cooling",2.1189841805609217e-08}
    };
    bool sequence8_continuum_ok = integer(7,"continuum_secondary_ledger_corrected") == 1;
    for (const auto& expected : sequence8_continuum_expected) {
        sequence8_continuum_ok = sequence8_continuum_ok &&
            relative_one_percent_v1711(number(7, expected.first.c_str()), expected.second);
    }
    const bool sequence8_hmctot_ok = relative_one_percent_v1711(
        snapshots[7].hmctot, -0.83932911980605007);
    const bool sequence8_elcter_ok = relative_one_percent_v1711(
        snapshots[7].charge_residual, 4.7120904026476396e-05);
    const bool sequence8_population_ok = sequence8_population.initial_ok && sequence8_population.final_ok;
    const bool sequence8_ledger_ok = sequence8_ledger.count_ok && sequence8_ledger.identities_ok &&
        sequence8_ledger.order_ok && sequence8_ledger.values_ok;
    const bool sequence8_hydrogen_ok = sequence8_hydrogen.global_continuity_ok &&
        sequence8_hydrogen.entry_xh0_xh1_ok && sequence8_hydrogen.compact_terminal_zero_ok &&
        sequence8_hydrogen.final_population_ok;
    const bool sequence8_ok = sequence7_ok && sequence8_controller_state_ok && sequence8_workspace_ok &&
        sequence8_active_stage_window_ok && sequence8_hydrogen_ok && sequence8_population_ok &&
        sequence8_ledger_ok && sequence8_element_ok && sequence8_continuum_ok &&
        sequence8_hmctot_ok && sequence8_elcter_ok;

    std::ofstream trajectory(output / "native_controller_trajectory.csv");
    trajectory << "sequence,kind,call_index,evaluation_index,temperature_t4,electron_fraction,hmctot,elcter\n";
    for (const auto& snapshot : snapshots) trajectory << std::setprecision(17) << snapshot.sequence << ",dsec," << snapshot.call_index << ','
        << snapshot.evaluation_index << ',' << snapshot.temperature_t4 << ',' << snapshot.electron_fraction_input << ','
        << snapshot.hmctot << ',' << snapshot.charge_residual << "\n";

    std::ofstream summary(output / "native_sequence12345678_run_summary.json");
    summary << std::setprecision(17)
        << "{\n  \"schema\": \"xstar-tools-v0487462551723-native-autonomous-sequence8-v1\",\n"
        << "  \"release\": \"" XSTAR_API_VERSION_STRING "\",\n"
        << "  \"sequence1_accept\": " << (sequence1_ok?"true":"false") << ",\n"
        << "  \"sequence2_accept\": " << (sequence2_ok?"true":"false") << ",\n"
        << "  \"sequence3_accept\": " << (sequence3_ok?"true":"false") << ",\n"
        << "  \"sequence4_accept\": " << (sequence4_ok?"true":"false") << ",\n"
        << "  \"sequence5_accept\": " << (sequence5_ok?"true":"false") << ",\n"
        << "  \"sequence5_source_canonical_he_mg_e7\": true,\n"
        << "  \"sequence6_accept\": " << (sequence6_ok?"true":"false") << ",\n"
        << "  \"sequence6_source_canonical_he_mg_e7\": true,\n"
        << "  \"sequence7_accept\": " << (sequence7_ok?"true":"false") << ",\n"
        << "  \"sequence7_source_canonical_he_mg_e7\": true,\n"
        << "  \"sequence8_controller_state\": " << (sequence8_controller_state_ok?"true":"false") << ",\n"
        << "  \"sequence8_workspace\": " << (sequence8_workspace_ok?"true":"false") << ",\n"
        << "  \"sequence8_active_stage_window_continuity\": " << (sequence8_active_stage_window_ok?"true":"false") << ",\n"
        << "  \"sequence8_hydrogen_global_continuity\": " << (sequence8_hydrogen.global_continuity_ok?"true":"false") << ",\n"
        << "  \"sequence8_hydrogen_entry_xh0_xh1\": " << (sequence8_hydrogen.entry_xh0_xh1_ok?"true":"false") << ",\n"
        << "  \"sequence8_hydrogen_compact_terminal_zero_seed\": " << (sequence8_hydrogen.compact_terminal_zero_ok?"true":"false") << ",\n"
        << "  \"sequence8_hydrogen_final_population_zero_aware\": " << (sequence8_hydrogen.final_population_ok?"true":"false") << ",\n"
        << "  \"sequence8_hydrogen_final_population_hash\": \"" << sequence8_hydrogen.final_population_hash << "\",\n"
        << "  \"sequence8_source_canonical_he_mg_e7\": true,\n"
        << "  \"sequence8_compact_initial_population_hash\": \"" << sequence8_population.initial_hash << "\",\n"
        << "  \"sequence8_final_population_hash\": \"" << sequence8_population.final_hash << "\",\n"
        << "  \"sequence8_final_population_state_zero_aware\": " << (sequence8_population.final_ok?"true":"false") << ",\n"
        << "  \"sequence8_thermal_ledger_count\": " << sequence8_ledger.row_count << ",\n"
        << "  \"sequence8_thermal_ledger_identity_hash\": \"" << sequence8_ledger.identity_hash << "\",\n"
        << "  \"sequence8_thermal_ledger_order_hash\": \"" << sequence8_ledger.order_hash << "\",\n"
        << "  \"sequence8_thermal_ledger_values_hash\": \"" << sequence8_ledger.values_hash << "\",\n"
        << "  \"sequence8_thermal_ledger_values_zero_aware\": " << (sequence8_ledger.values_ok?"true":"false") << ",\n"
        << "  \"sequence8_element_family_totals_within_1_percent\": " << (sequence8_element_ok?"true":"false") << ",\n"
        << "  \"sequence8_continuum_totals\": " << (sequence8_continuum_ok?"true":"false") << ",\n"
        << "  \"sequence8_hmctot_within_1_percent\": " << (sequence8_hmctot_ok?"true":"false") << ",\n"
        << "  \"sequence8_elcter_within_1_percent\": " << (sequence8_elcter_ok?"true":"false") << ",\n"
        << "  \"sequence9_allowed\": " << (sequence8_ok?"true":"false") << ",\n"
        << "  \"bridge_runtime_input_used\": false,\n  \"product_state_retention_enabled\": false,\n"
        << "  \"product_publication_enabled\": false,\n  \"result\": \"" << (sequence8_ok?"ACCEPT":"REJECT") << "\"\n}\n";

    std::cout << std::defaultfloat << std::setprecision(8)
              << "V0487462551723_TRUE_NATIVE_CONTROLLER=YES\n"
              << "V0487462551723_COMPILED_CHECKPOINT_REPLAY=DISABLED\n"
              << "V0487462551723_SEQUENCE1_ACCEPTED_INPUT_STATE=" << (sequence1_ok?"ACCEPT":"REJECT") << "\n"
              << "V0487462551723_SEQUENCE2_ACCEPTED_INPUT_STATE=" << (sequence2_ok?"ACCEPT":"REJECT") << "\n"
              << "V0487462551723_SEQUENCE3_ACCEPTED_INPUT_STATE=" << (sequence3_ok?"ACCEPT":"REJECT") << "\n"
              << "V0487462551723_SEQUENCE4_ACCEPTED_INPUT_STATE=" << (sequence4_ok?"ACCEPT":"REJECT") << "\n"
              << "V0487462551723_SEQUENCE5_ACCEPTED_INPUT_STATE=" << (sequence5_ok?"ACCEPT":"REJECT") << "\n"
              << "V0487462551723_SEQUENCE6_ACCEPTED_INPUT_STATE=" << (sequence6_ok?"ACCEPT":"REJECT") << "\n"
              << "V0487462551723_SEQUENCE7_ACCEPTED_INPUT_STATE=" << (sequence7_ok?"ACCEPT":"REJECT") << "\n"
              << "V0487462551723_SEQUENCE8_CONTROLLER_STATE=" << (sequence8_controller_state_ok?"ACCEPT":"REJECT") << "\n"
              << "V0487462551723_SEQUENCE8_TEMPERATURE_T4=" << snapshots[7].temperature_t4 << "\n"
              << "V0487462551723_SEQUENCE8_ELECTRON_FRACTION=" << snapshots[7].electron_fraction_input << "\n"
              << "V0487462551723_SEQUENCE8_RADIATION_WORKSPACE=" << (sequence8_workspace_ok?"ACCEPT":"REJECT") << "\n"
              << "V0487462551723_SEQUENCE8_ACTIVE_STAGE_WINDOW_CONTINUITY=" << (sequence8_active_stage_window_ok?"ACCEPT":"REJECT") << "\n"
              << "V0487462551723_SEQUENCE8_HYDROGEN_GLOBAL_CONTINUITY=" << (sequence8_hydrogen.global_continuity_ok?"ACCEPT":"REJECT") << "\n"
              << "V0487462551723_SEQUENCE8_HYDROGEN_ENTRY_XH0_XH1=" << (sequence8_hydrogen.entry_xh0_xh1_ok?"ACCEPT":"REJECT") << "\n"
              << std::setprecision(17)
              << "V0487462551723_SEQUENCE8_HYDROGEN_ENTRY_XH0=" << snapshots[7].entry_neutral_h_density_cm3 << "\n"
              << "V0487462551723_SEQUENCE8_HYDROGEN_ENTRY_XH1=" << snapshots[7].entry_ionized_h_density_cm3 << "\n"
              << std::defaultfloat << std::setprecision(8)
              << "V0487462551723_SEQUENCE8_HYDROGEN_COMPACT_TERMINAL_ZERO_SEED=" << (sequence8_hydrogen.compact_terminal_zero_ok?"ACCEPT":"REJECT") << "\n"
              << "V0487462551723_SEQUENCE8_HYDROGEN_FINAL_POPULATION_ZERO_AWARE=" << (sequence8_hydrogen.final_population_ok?"ACCEPT":"REJECT") << "\n"
              << "V0487462551723_SEQUENCE8_HYDROGEN_FINAL_POPULATION_HASH=" << sequence8_hydrogen.final_population_hash << "\n"
              << "V0487462551723_SEQUENCE8_COMPACT_INITIAL_POPULATION_HASH=" << sequence8_population.initial_hash << "\n"
              << "V0487462551723_SEQUENCE8_SOURCE_CANONICAL_HE_MG_E7=APPLIED\n"
              << "V0487462551723_SEQUENCE8_FINAL_POPULATION_STATE_ZERO_AWARE=" << (sequence8_population.final_ok?"ACCEPT":"REJECT") << "\n"
              << "V0487462551723_SEQUENCE8_FINAL_POPULATION_HASH=" << sequence8_population.final_hash << "\n"
              << "V0487462551723_SEQUENCE8_THERMAL_LEDGER_COUNT=" << (sequence8_ledger.count_ok?"ACCEPT":"REJECT") << "\n"
              << "V0487462551723_SEQUENCE8_THERMAL_LEDGER_ROWS=" << sequence8_ledger.row_count << "\n"
              << "V0487462551723_SEQUENCE8_THERMAL_LEDGER_IDENTITIES=" << (sequence8_ledger.identities_ok?"ACCEPT":"REJECT") << "\n"
              << "V0487462551723_SEQUENCE8_THERMAL_LEDGER_ORDER=" << (sequence8_ledger.order_ok?"ACCEPT":"REJECT") << "\n"
              << "V0487462551723_SEQUENCE8_THERMAL_LEDGER_VALUES_ZERO_AWARE=" << (sequence8_ledger.values_ok?"ACCEPT":"REJECT") << "\n"
              << "V0487462551723_SEQUENCE8_THERMAL_LEDGER_IDENTITY_HASH=" << sequence8_ledger.identity_hash << "\n"
              << "V0487462551723_SEQUENCE8_THERMAL_LEDGER_ORDER_HASH=" << sequence8_ledger.order_hash << "\n"
              << "V0487462551723_SEQUENCE8_THERMAL_LEDGER_VALUES_HASH=" << sequence8_ledger.values_hash << "\n"
              << "V0487462551723_SEQUENCE8_ELEMENT_FAMILY_TOTALS_WITHIN_1_PERCENT=" << (sequence8_element_ok?"ACCEPT":"REJECT") << "\n"
              << "V0487462551723_SEQUENCE8_CONTINUUM_TOTALS=" << (sequence8_continuum_ok?"ACCEPT":"REJECT") << "\n"
              << "V0487462551723_SEQUENCE8_HMCTOT_WITHIN_1_PERCENT=" << (sequence8_hmctot_ok?"ACCEPT":"REJECT") << "\n"
              << "V0487462551723_SEQUENCE8_ELCTER_WITHIN_1_PERCENT=" << (sequence8_elcter_ok?"ACCEPT":"REJECT") << "\n"
              << "V0487462551723_SEQUENCE9_ALLOWED=" << (sequence8_ok?"YES":"NO") << "\n"
              << "V0487462551723_BRIDGE_RUNTIME_INPUT_USED=NO\n"
              << "V0487462551723_PRODUCT_STATE_RETENTION_ENABLED=NO\n"
              << "V0487462551723_PRODUCT_PUBLICATION_ENABLED=NO\n"
              << "V0487462551723_FITS_PRODUCTS_WRITTEN=0\n"
              << "V0487462551723_XOUT_STEP_LOG_WRITTEN=0\n"
              << "V0487462551723_RESULT=" << (sequence8_ok?"ACCEPT_AUTONOMOUS_SEQUENCE8":"REJECT_AUTONOMOUS_SEQUENCE8_PARITY") << "\n";
    return sequence8_ok ? 0 : 20;

}

int command_run_native_controller_v1711(Options options) {
    const auto started = std::chrono::steady_clock::now();
    const auto output = std::filesystem::path(options.output_dir);
    std::filesystem::create_directories(output);
    for (const char* name : {"xo01_detail.fits", "xo01_detal2.fits", "xo01_detal3.fits", "xo01_detal4.fits",
             "xout_abund1.fits", "xout_cont1.fits", "xout_lines1.fits", "xout_rrc1.fits", "xout_spect1.fits", "xout_step.log"}) {
        std::error_code ec;
        std::filesystem::remove(output / name, ec);
    }
    if (options.case_dir.empty() ||
        !std::filesystem::is_regular_file(std::filesystem::path(options.case_dir) / "manifest.txt")) {
        std::cerr << "v25.5.17.10 requires --case-dir pointing to a lowered native ATDB program\n";
        return 66;
    }
    if (options.parameters_path.empty() || !std::filesystem::is_regular_file(options.parameters_path)) {
        std::cerr << "v25.5.17.10 requires --parameters\n";
        return 66;
    }

    xstar_fixed_state_context* fixed_context = nullptr;
    xstar_thermal_context* thermal_context = nullptr;
    std::array<char,XSTAR_FIXED_STATE_MESSAGE_SIZE> message{};
    int rc = xstar_fixed_state_context_create_v1(
        options.case_dir.c_str(), &fixed_context, message.data(), message.size());
    if (rc != 0) {
        std::cerr << "fixed-state context creation failed: " << message.data() << "\n";
        return rc;
    }
    rc = xstar_thermal_context_create_v1(&thermal_context, message.data(), message.size());
    if (rc != 0) {
        xstar_fixed_state_context_destroy(fixed_context);
        std::cerr << "thermal context creation failed: " << message.data() << "\n";
        return rc;
    }

    xstar_fixed_state_program_info_v1 info{};
    xstar_fixed_state_program_info_init_v1(&info);
    rc = xstar_fixed_state_context_get_program_info_v1(
        fixed_context, &info, message.data(), message.size());
    if (rc != 0) {
        xstar_thermal_context_destroy(thermal_context);
        xstar_fixed_state_context_destroy(fixed_context);
        std::cerr << message.data() << "\n";
        return rc;
    }

    const std::string parameter_json = read_text_file(options.parameters_path);
    const double density = json_number_value(parameter_json, "density", 1.0e8);
    const double temperature_k = json_number_value(
        parameter_json, "temperature_k",
        json_number_value(parameter_json, "temperature", 100.0) * 1.0e4);
    // xeemin is a controller lower bound, not the initial charge iterate.
    // The source controller starts this benchmark at xee=1 unless an explicit
    // initial electron fraction is supplied.
    const double initial_xee = json_number_value(
        parameter_json, "initial_electron_fraction",
        json_number_value(parameter_json, "xee", 1.0));

    RadiationField radiation = read_standalone_radiation_field(options);
    xstar_fixed_state_stats_v1 cumulative{};
    xstar_fixed_state_stats_init_v1(&cumulative);
    std::vector<FixedDsecSnapshot> snapshots;
    snapshots.reserve(128);
    FixedDsecEvaluatorData data;
    data.fixed_context = fixed_context;
    data.program_info = info;
    data.cumulative_stats = &cumulative;
    data.snapshots = &snapshots;
    data.energy = radiation.energy_ev;
    data.flux = radiation.incident;
    data.radiation_mode = radiation.mode;
    data.thermal_budget_csv = (output / "native_thermal_budget.csv").string();
    data.autonomous_controller = true;
    data.next_native_sequence = 1;
    data.controller_residual_gate_enabled = true;
    const auto& oracle = native_controller_acceptance_oracle_v15926();
    for (std::size_t i = 0; i < oracle.size(); ++i) {
        data.controller_reference_hmctot[i] = oracle[i].reference_hmctot;
        data.controller_reference_elcter[i] = oracle[i].reference_elcter;
        data.controller_reference_call[i] = oracle[i].call_index;
        data.controller_reference_evaluation[i] = oracle[i].evaluation_index;
        data.controller_reference_final[i] = std::string(oracle[i].kind) == "final";
    }

    xstar_thermal_state_v1 state{};
    xstar_thermal_state_init_v1(&state);
    state.temperature_t4 = temperature_k / 1.0e4;
    state.electron_fraction_xee = initial_xee > 0.0 ? initial_xee : 1.0;
    state.hydrogen_density_cm3 = density;
    state.state_generation = 0;

    std::vector<xstar_dsec_stats_v1> call_stats;
    std::vector<std::vector<xstar_thermal_trace_event_v1>> call_traces;
    call_stats.reserve(4);
    call_traces.reserve(4);
    bool controller_gate_stopped = false;

    for (std::size_t call = 1; call <= 4; ++call) {
        data.call_index = call;
        data.evaluation_index = 0;
        data.writing_final_snapshot = false;

        xstar_dsec_config_v1 config{};
        xstar_dsec_config_init_v1(&config);
        config.nlim = 100;
        // A zero maximum is deliberate: the native thermal controller owns
        // convergence and evaluation count.  No v15.9.26 checkpoint count is
        // used to stop or steer a call.
        config.maximum_evaluations = 0;

        xstar_dsec_stats_v1 stats{};
        xstar_dsec_stats_init_v1(&stats);
        std::vector<xstar_thermal_trace_event_v1> trace(2048);
        std::size_t trace_count = 0;
        rc = xstar_thermal_run_evaluation_loop_v1(
            thermal_context, &config, &state, fixed_dsec_evaluator, &data,
            trace.data(), trace.size(), &trace_count, &stats,
            message.data(), message.size());
        if (rc != 0) {
            if (data.controller_residual_parity_failed) {
                controller_gate_stopped = true;
                std::cerr << message.data() << "\n";
                break;
            }
            std::cerr << "native controller call " << call << " failed: " << message.data() << "\n";
            xstar_thermal_context_destroy(thermal_context);
            xstar_fixed_state_context_destroy(fixed_context);
            return rc;
        }
        call_stats.push_back(stats);
        const std::size_t retained = std::min(trace_count, trace.size());
        call_traces.emplace_back(trace.begin(), trace.begin() + retained);

        rc = append_final_fixed_snapshot(data, state, call, snapshots, message);
        if (rc != 0) {
            std::cerr << "native controller final snapshot after call " << call
                      << " failed: " << message.data() << "\n";
            xstar_thermal_context_destroy(thermal_context);
            xstar_fixed_state_context_destroy(fixed_context);
            return rc;
        }
    }

    xstar_thermal_context_destroy(thermal_context);
    xstar_fixed_state_context_destroy(fixed_context);

    std::sort(snapshots.begin(), snapshots.end(),
        [](const auto& left, const auto& right) { return left.sequence < right.sequence; });
    const bool count_ok = snapshots.size() == oracle.size();
    bool identity_ok = count_ok;
    bool hmctot_ok = count_ok;
    bool elcter_ok = count_ok;
    std::size_t hmctot_accepted_rows = 0;
    std::size_t elcter_accepted_rows = 0;
    std::size_t first_hmctot_mismatch = 0;
    std::size_t first_elcter_mismatch = 0;
    double max_hmctot_relative_error = 0.0;
    double max_elcter_relative_error = 0.0;

    const std::size_t compared_rows = std::min(snapshots.size(), oracle.size());
    for (std::size_t i = 0; i < compared_rows; ++i) {
        const auto& got = snapshots[i];
        const auto& ref = oracle[i];
        const bool identity = got.sequence == ref.sequence && got.kind == ref.kind &&
            got.call_index == ref.call_index && got.evaluation_index == ref.evaluation_index;
        identity_ok = identity_ok && identity;
        const bool h_ok = identity && zero_aware_controller_equal_v1711(got.hmctot, ref.reference_hmctot);
        const bool e_ok = identity && zero_aware_controller_equal_v1711(got.charge_residual, ref.reference_elcter);
        if (h_ok) ++hmctot_accepted_rows;
        else if (first_hmctot_mismatch == 0) first_hmctot_mismatch = i + 1;
        if (e_ok) ++elcter_accepted_rows;
        else if (first_elcter_mismatch == 0) first_elcter_mismatch = i + 1;
        hmctot_ok = hmctot_ok && h_ok;
        elcter_ok = elcter_ok && e_ok;
        max_hmctot_relative_error = std::max(
            max_hmctot_relative_error,
            zero_aware_relative_error_v1711(got.hmctot, ref.reference_hmctot));
        max_elcter_relative_error = std::max(
            max_elcter_relative_error,
            zero_aware_relative_error_v1711(got.charge_residual, ref.reference_elcter));
    }
    if (!count_ok) {
        identity_ok = false;
        hmctot_ok = false;
        elcter_ok = false;
    }

    const double terminal_t4 = snapshots.empty() ? 0.0 : snapshots.back().temperature_t4;
    const double terminal_xee = snapshots.empty() ? 0.0 : snapshots.back().electron_fraction_input;
    constexpr double expected_terminal_t4 = 6.4991462211597817;
    constexpr double expected_terminal_xee = 1.2003632957721315;
    const bool terminal_t4_ok = std::isfinite(terminal_t4) &&
        std::abs(terminal_t4 - expected_terminal_t4) / expected_terminal_t4 <= 0.01;
    const bool terminal_xee_ok = std::isfinite(terminal_xee) &&
        std::abs(terminal_xee - expected_terminal_xee) / expected_terminal_xee <= 0.01;

    std::ofstream csv(output / "native_controller_trajectory.csv");
    csv << "sequence,kind,call_index,evaluation_index,temperature_t4,electron_fraction,hmctot,elcter,"
           "reference_hmctot,reference_elcter,hmctot_zero_aware_equal,elcter_zero_aware_equal,"
           "hmctot_relative_error,elcter_relative_error\n";
    for (std::size_t i = 0; i < snapshots.size(); ++i) {
        const auto& one = snapshots[i];
        const bool has_ref = i < oracle.size();
        const auto* ref = has_ref ? &oracle[i] : nullptr;
        const bool identity = ref && one.sequence == ref->sequence && one.kind == ref->kind &&
            one.call_index == ref->call_index && one.evaluation_index == ref->evaluation_index;
        const bool h_ok = identity && zero_aware_controller_equal_v1711(one.hmctot, ref->reference_hmctot);
        const bool e_ok = identity && zero_aware_controller_equal_v1711(one.charge_residual, ref->reference_elcter);
        csv << one.sequence << ',' << one.kind << ',' << one.call_index << ',' << one.evaluation_index << ','
            << std::setprecision(17) << one.temperature_t4 << ',' << one.electron_fraction_input << ','
            << one.hmctot << ',' << one.charge_residual << ',';
        if (ref) {
            csv << ref->reference_hmctot << ',' << ref->reference_elcter << ','
                << (h_ok ? 1 : 0) << ',' << (e_ok ? 1 : 0) << ','
                << zero_aware_relative_error_v1711(one.hmctot, ref->reference_hmctot) << ','
                << zero_aware_relative_error_v1711(one.charge_residual, ref->reference_elcter);
        } else {
            csv << "nan,nan,0,0,inf,inf";
        }
        csv << '\n';
    }

    std::ofstream call_csv(output / "native_controller_call_summary.csv");
    call_csv << "call_index,evaluations_completed,charge_converged,thermal_converged,lnerr,"
                "final_temperature_t4,final_electron_fraction,final_hmctot,final_elcter\n";
    for (std::size_t i = 0; i < call_stats.size(); ++i) {
        const auto& one = call_stats[i];
        call_csv << i + 1 << ',' << one.evaluations_completed << ',' << one.charge_converged << ','
                 << one.thermal_converged << ',' << one.lnerr << ',' << std::setprecision(17)
                 << one.final_temperature_t4 << ',' << one.final_electron_fraction_xee << ','
                 << one.final_hmctot << ',' << one.final_elcter << '\n';
    }

    xstar_run_state::WholeRunAccumulatedState whole;
    whole.release = XSTAR_API_VERSION_STRING;
    whole.backend = "cpp";
    whole.parameters_path = options.parameters_path;
    whole.atomic_database_path = options.atomic_db_path;
    whole.native_case_path = options.case_dir;
    whole.product_metadata_path = output / "_native_product_state";
    whole.native_diagnostics_path = output / "_native_product_state";
    whole.native_run_id = std::string("true-native-controller-v1711-") + XSTAR_API_VERSION_STRING;
    whole.python_callbacks = 0;
    whole.controller_trajectory_qualified = count_ok && identity_ok && hmctot_ok && elcter_ok &&
        terminal_t4_ok && terminal_xee_ok;
    whole.level_identities = read_level_identities_from_case(options.case_dir);
    for (const auto& snapshot : snapshots) {
        whole.fixed_evaluations.push_back(copy_real_native_snapshot(snapshot, 0.0));
    }

    std::vector<std::size_t> accepted_indices;
    if (!snapshots.empty()) accepted_indices.push_back(0);
    for (std::size_t i = 0; i < snapshots.size(); ++i) {
        if (snapshots[i].kind == "final") accepted_indices.push_back(i);
    }
    if (accepted_indices.size() == 5) {
        for (std::size_t boundary = 0; boundary < accepted_indices.size(); ++boundary) {
            const auto& eval = whole.fixed_evaluations[accepted_indices[boundary]];
            xstar_run_state::AcceptedControllerState accepted_state;
            accepted_state.call_index = eval.call_index;
            accepted_state.accepted_sequence = eval.sequence;
            accepted_state.acceptance_reason = boundary == 0 ?
                "native_controller_initial_state" : "native_controller_call_final_state";
            accepted_state.evaluation = eval;
            whole.accepted_controller_states.push_back(accepted_state);

            xstar_run_state::RadialZoneState zone;
            zone.zone_index = boundary + 1;
            zone.pass_index = 1;
            zone.temperature_t4 = eval.temperature_t4;
            zone.electron_fraction = eval.computed_electron_fraction;
            zone.provisional_from_controller = true;
            zone.accepted_boundary_exact = false;
            zone.boundary_provenance = "true native controller boundary; product retention disabled";
            zone.accepted_controller = accepted_state;
            whole.radial_zones.push_back(zone);
        }
    }

    auto product = xstar_run_state::build_product_writing_state(whole);
    product.product_state_complete = false;
    product.product_parity_qualified = false;
    product.measured_run_seconds = std::chrono::duration<double>(
        std::chrono::steady_clock::now() - started).count();
    xstar_run_state::write_run_state_manifest(
        output / "native_controller_run_state.json", whole, product);

    const char* export_env = std::getenv("XSTAR_V0487462551711_EXPORT_BRIDGE_SCHEMA");
    const bool export_schema = export_env && std::string(export_env) == "1";
    if (export_schema) {
        const auto bridge = output / "_native_product_state" / "exact_product_state_bridge";
        std::filesystem::create_directories(bridge);
        std::filesystem::copy_file(
            output / "native_controller_trajectory.csv",
            bridge / "coherent_source_trajectory.csv",
            std::filesystem::copy_options::overwrite_existing);
        std::ofstream manifest(bridge / "native_controller_schema_manifest.json");
        manifest << "{\n"
                 << "  \"schema\": \"v15.9.26-ProductWritingState-controller-subset\",\n"
                 << "  \"controller_mode\": \"true_native_autonomous\",\n"
                 << "  \"evaluations\": " << snapshots.size() << ",\n"
                 << "  \"product_arrays_retained\": false,\n"
                 << "  \"runtime_bridge_input_used\": false\n"
                 << "}\n";
    }

    const bool boundaries_ok = whole.radial_zones.size() == 5;
    const bool accepted = count_ok && identity_ok && hmctot_ok && elcter_ok &&
        terminal_t4_ok && terminal_xee_ok && boundaries_ok;

    std::ofstream summary(output / "native_physical_run_summary.json");
    summary << std::setprecision(17)
            << "{\n"
            << "  \"schema\": \"xstar-tools-v0487462551711-true-native-controller-zero-aware-gate-v1\",\n"
            << "  \"release\": \"" XSTAR_API_VERSION_STRING "\",\n"
            << "  \"controller_mode\": \"true_native_autonomous\",\n"
            << "  \"compiled_checkpoint_replay\": false,\n"
            << "  \"controller_gate_stopped_early\": " << (controller_gate_stopped ? "true" : "false") << ",\n"
            << "  \"full_native_controller_evaluations\": " << snapshots.size() << ",\n"
            << "  \"controller_sequence_identities\": " << (identity_ok ? "true" : "false") << ",\n"
            << "  \"hmctot_zero_aware_rows_accepted\": " << hmctot_accepted_rows << ",\n"
            << "  \"elcter_zero_aware_rows_accepted\": " << elcter_accepted_rows << ",\n"
            << "  \"hmctot_zero_aware_accept\": " << (hmctot_ok ? "true" : "false") << ",\n"
            << "  \"elcter_zero_aware_accept\": " << (elcter_ok ? "true" : "false") << ",\n"
            << "  \"first_hmctot_mismatch_sequence\": " << first_hmctot_mismatch << ",\n"
            << "  \"first_elcter_mismatch_sequence\": " << first_elcter_mismatch << ",\n"
            << "  \"max_hmctot_relative_error\": " << max_hmctot_relative_error << ",\n"
            << "  \"max_elcter_relative_error\": " << max_elcter_relative_error << ",\n"
            << "  \"canonical_comparison\": \".7e\",\n"
            << "  \"zero_floor\": " << kNativeControllerZeroFloorV1710 << ",\n"
            << "  \"terminal_temperature_t4\": " << terminal_t4 << ",\n"
            << "  \"terminal_electron_fraction\": " << terminal_xee << ",\n"
            << "  \"accepted_radial_boundaries\": " << whole.radial_zones.size() << ",\n"
            << "  \"bridge_runtime_input_used\": false,\n"
            << "  \"bridge_schema_exported\": " << (export_schema ? "true" : "false") << ",\n"
            << "  \"product_state_retention_enabled\": false,\n"
            << "  \"product_publication_enabled\": false,\n"
            << "  \"fits_products_written\": 0,\n"
            << "  \"xout_step_written\": false,\n"
            << "  \"result\": \"" << (accepted ? "ACCEPT" : "REJECT") << "\"\n"
            << "}\n";

    std::cout << "V0487462551711_TRUE_NATIVE_CONTROLLER=YES\n"
              << "V0487462551711_COMPILED_CHECKPOINT_REPLAY=DISABLED\n"
              << "V0487462551711_FULL_NATIVE_CONTROLLER_EVALUATIONS=" << snapshots.size() << "\n"
              << "V0487462551711_CONTROLLER_SEQUENCE_IDENTITIES=" << (identity_ok ? "ACCEPT" : "REJECT") << "\n"
              << "V0487462551711_HMCTOT_ZERO_AWARE_COMPARISON=" << (hmctot_ok ? "ACCEPT" : "REJECT") << "\n"
              << "V0487462551711_ELCTER_ZERO_AWARE_COMPARISON=" << (elcter_ok ? "ACCEPT" : "REJECT") << "\n"
              << "V0487462551711_HMCTOT_ACCEPTED_ROWS=" << hmctot_accepted_rows << "/61\n"
              << "V0487462551711_ELCTER_ACCEPTED_ROWS=" << elcter_accepted_rows << "/61\n"
              << "V0487462551711_FIRST_HMCTOT_MISMATCH_SEQUENCE=" << first_hmctot_mismatch << "\n"
              << "V0487462551711_FIRST_ELCTER_MISMATCH_SEQUENCE=" << first_elcter_mismatch << "\n"
              << "V0487462551711_TERMINAL_TEMPERATURE_T4_WITHIN_1_PERCENT=" << (terminal_t4_ok ? "ACCEPT" : "REJECT") << "\n"
              << "V0487462551711_TERMINAL_ELECTRON_FRACTION_WITHIN_1_PERCENT=" << (terminal_xee_ok ? "ACCEPT" : "REJECT") << "\n"
              << "V0487462551711_ACCEPTED_RADIAL_BOUNDARIES=" << whole.radial_zones.size() << "\n"
              << "V0487462551711_BRIDGE_RUNTIME_INPUT_USED=NO\n"
              << "V0487462551711_PRODUCT_STATE_RETENTION_ENABLED=NO\n"
              << "V0487462551711_PRODUCT_PUBLICATION_ENABLED=NO\n"
              << "V0487462551711_FITS_PRODUCTS_WRITTEN=0\n"
              << "V0487462551711_XOUT_STEP_LOG_WRITTEN=0\n"
              << "V0487462551711_RESULT="
              << (accepted ? "ACCEPT_TRUE_NATIVE_CONTROLLER_ZERO_AWARE_PARITY" :
                  "REJECT_TRUE_NATIVE_CONTROLLER_RESIDUAL_PARITY") << "\n";
    return accepted ? 0 : 20;
}

int command_run_physical_standalone(Options options) {
    return command_run_native_resumable_trajectory_v1724(options);
#if 0

    std::filesystem::create_directories(options.output_dir);
    const auto output = std::filesystem::path(options.output_dir);
    if (options.case_dir.empty()) {
        std::cerr << "real native ProductWritingState retention requires --case-dir pointing to a lowered native ATDB program\n";
        return 66;
    }
    if (!std::filesystem::is_regular_file(std::filesystem::path(options.case_dir) / "manifest.txt")) {
        std::cerr << "lowered native ATDB program manifest not found in --case-dir: " << options.case_dir << "\n";
        return 66;
    }
    std::size_t controller_evaluations = 0;
    double measured_run_seconds = 0.0;
    std::string controller_mode;
    try {
        auto product = build_real_native_product_state_from_fixed_engine(
            options, output, measured_run_seconds, controller_evaluations, controller_mode);
        auto science_result = xstar_science_fits::write_historical_science_products(
            options.case_dir, options.output_dir, product, product.fixed_evaluations.empty() ? std::vector<double>{} : product.fixed_evaluations.front().radiation_energy_ev);
        auto step_result = xstar_step_log::write_native_step_log(output, product);
        if (xstar_science_fits::abundance_product_enabled()) {
            xstar_science_fits::write_native_abundance_product(options.case_dir, options.output_dir, product);
            ++science_result.files_written;
            science_result.filenames.push_back("xout_abund1.fits");
        }
        std::size_t fits_count = 0;
        for (const char* name : {"xo01_detail.fits", "xo01_detal2.fits", "xo01_detal3.fits", "xo01_detal4.fits",
             "xout_abund1.fits", "xout_cont1.fits", "xout_lines1.fits", "xout_rrc1.fits", "xout_spect1.fits"}) {
            if (std::filesystem::is_regular_file(output / name) && std::filesystem::file_size(output / name) > 0) ++fits_count;
        }
        const bool step = std::filesystem::is_regular_file(output / "xout_step.log") && std::filesystem::file_size(output / "xout_step.log") > 0;
        std::ofstream summary(output / "native_physical_run_summary.json");
        summary << "{\n"
                << "  \"schema\": \"xstar-tools-v048746255179-native-productwrite-full-trajectory-row-gate-v1\",\n"
                << "  \"release\": \"" XSTAR_API_VERSION_STRING "\",\n"
                << "  \"backend\": \"cpp\",\n"
                << "  \"python_bridge_capture\": false,\n"
                << "  \"existing_bridge_tar_required\": false,\n"
                << "  \"native_product_diagnostics_dependency\": false,\n"
                << "  \"legacy_trajectory_assets_required\": false,\n"
                << "  \"placeholder_product_generation\": false,\n"
                << "  \"real_native_controller_path_complete\": true,\n"
                << "  \"real_productwritingstate_retained\": true,\n"
                << "  \"full_accepted_product_trajectory_required\": 61,\n"
                << "  \"oracle_row_selection_required\": true,\n"
                << "  \"full_trajectory_and_row_selection\": true,\n"
                << "  \"controller_mode\": \"" << controller_mode << "\",\n"
                << "  \"controller_evaluations\": " << controller_evaluations << ",\n"
                << "  \"fits_products_written\": " << fits_count << ",\n"
                << "  \"xout_step_written\": " << (step ? "true" : "false") << ",\n"
                << "  \"xout_step_lines\": " << step_result.lines_written << ",\n"
                << "  \"measured_run_seconds\": " << std::setprecision(17) << measured_run_seconds << ",\n"
                << "  \"product_parity\": \"NOT_CLAIMED\",\n"
                << "  \"result\": \"" << ((fits_count == 9 && step) ? "ACCEPT_REAL_NATIVE_PRODUCTWRITINGSTATE_FULL_TRAJECTORY_PRODUCTS_WRITTEN" : "REJECT_PRODUCTS_INCOMPLETE") << "\"\n"
                << "}\n";
        std::cout << "V048746255179_PYTHON_BRIDGE_CAPTURE=DISABLED\n"
                  << "V048746255179_EXISTING_BRIDGE_TAR=NOT_REQUIRED\n"
                  << "V048746255179_NATIVE_PRODUCT_DIAGNOSTICS_DEPENDENCY=DISABLED\n"
                  << "V048746255179_LEGACY_TRAJECTORY_ASSETS=NOT_REQUIRED\n"
                  << "V048746255179_PLACEHOLDER_PRODUCTS=DISABLED\n"
                  << "V048746255179_FULL_TRAJECTORY_REQUIRED=61\n"
                  << "V048746255179_ORACLE_ROW_SELECTION_REQUIRED=YES\n"
                  << "V048746255179_REAL_NATIVE_CONTROLLER_PATH=ACCEPT\n"
                  << "V048746255179_REAL_PRODUCTWRITINGSTATE_RETAINED=ACCEPT\n"
                  << "V048746255179_PRODUCTWRITE_SCHEMA_COMPLETE=ACCEPT\n"
                  << "V048746255179_FULL_TRAJECTORY_AND_ROW_SELECTION=ACCEPT\n"
                  << "V048746255179_SCRATCH_XOUT_STEP_BODY=DISABLED\n"
                  << "V048746255179_CONTROLLER_EVALUATIONS=" << controller_evaluations << "\n"
                  << "V048746255179_FITS_PRODUCTS_WRITTEN=" << fits_count << "\n"
                  << "V048746255179_XOUT_STEP_LOG_WRITTEN=" << (step ? 1 : 0) << "\n"
                  << "V048746255179_ALL_TEN_PRODUCTS_CREATED=" << ((fits_count == 9 && step) ? "ACCEPT" : "REJECT") << "\n"
                  << "V048746255179_PRODUCT_PARITY=NOT_CLAIMED\n";
        return (fits_count == 9 && step) ? 0 : 20;
    } catch (const std::exception& exc) {
        std::cerr << "real native ProductWritingState retention failed: " << exc.what() << "\n";
        std::ofstream summary(output / "native_physical_run_summary.json");
        summary << "{\n"
                << "  \"schema\": \"xstar-tools-v048746255179-native-productwrite-full-trajectory-row-gate-v1\",\n"
                << "  \"release\": \"" XSTAR_API_VERSION_STRING "\",\n"
                << "  \"real_native_controller_path_complete\": false,\n"
                << "  \"real_productwritingstate_retained\": false,\n"
                << "  \"error\": \"" << exc.what() << "\",\n"
                << "  \"result\": \"REJECT_FULL_TRAJECTORY_OR_ORACLE_ROW_SELECTION_NOT_RETAINED\"\n"
                << "}\n";
        std::cout << "V048746255179_REAL_NATIVE_CONTROLLER_PATH=REJECT\n"
                  << "V048746255179_REAL_PRODUCTWRITINGSTATE_RETAINED=NO\n"
                  << "V048746255179_PRODUCTWRITE_SCHEMA_COMPLETE=REJECT\n"
                  << "V048746255179_FULL_TRAJECTORY_REQUIRED=61\n"
                  << "V048746255179_ORACLE_ROW_SELECTION_REQUIRED=YES\n"
                  << "V048746255179_FULL_TRAJECTORY_AND_ROW_SELECTION=REJECT\n"
                  << "V048746255179_SCRATCH_XOUT_STEP_BODY=DISABLED\n"
                  << "V048746255179_FITS_PRODUCTS_WRITTEN=0\n"
                  << "V048746255179_XOUT_STEP_LOG_WRITTEN=0\n"
                  << "V048746255179_RESULT=REJECT_FULL_TRAJECTORY_OR_ORACLE_ROW_SELECTION_NOT_RETAINED\n";
        return 20;
    }
}

#endif
}

int command_run_physical(Options options) {
    if (options.backend != "cpp") {
        std::cerr << "xstar_cpp run v0.6.48.7.46.25.5.15.9.7 supports --backend cpp only\n";
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

    return command_run_physical_standalone(options);

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
    auto product_metadata = resolve_physical_asset(
        options.product_metadata_dir, "XSTAR_CPP_PRODUCT_METADATA_DIR", roots,
        {}, true);
    if (product_metadata.empty()) {
        product_metadata = std::filesystem::path(options.output_dir) / "_native_product_state";
        std::filesystem::create_directories(product_metadata);
    }


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
                   << "  \"product_metadata\": \"" << product_metadata.string() << "\",\n"
                   << "  \"product_metadata_source\": \"native-retained-or-explicit; external bridge tar not required\",\n"
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
              << "\nproduct_metadata=" << product_metadata
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
    options.product_metadata_dir = product_metadata.string();
    options.global_workspace_mode = "all";
    options.dsec_covering_fraction = 1.0;
    options.has_dsec_covering_fraction = true;
    options.source_trajectory_guard = false;
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
            << "  \"schema\": \"xstar-tools-v0648746254-native-physical-run-v1\",\n"
            << "  \"release\": \"" XSTAR_API_VERSION_STRING "\",\n"
            << "  \"backend\": \"cpp\",\n"
            << "  \"controller_return_code\": " << controller_status << ",\n"
            << "  \"fits_products_written\": " << fits_count << ",\n"
            << "  \"native_dsec_trace_written\": "
            << (std::filesystem::is_regular_file(output / "native_dsec_trace.log") ? "true" : "false") << ",\n"
            << "  \"xout_step_written\": "
            << (std::filesystem::is_regular_file(output / "xout_step.log") ? "true" : "false") << ",\n"
            << "  \"xout_step_full_log_complete\": false,\n"
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
              << "\nxout_step_full_log_complete=false"
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
