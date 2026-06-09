#include "xstar_api.h"
#include "xstar_python_bridge.h"
#include "xstar_standalone_internal.hpp"

#include <array>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <filesystem>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

namespace {

struct Options {
    std::string command = "help";
    std::string backend = "cpp";
    std::string plugin_dir;
    std::string python_path;
    std::string engine_backend = "inherit";
    std::string rates_backend = "inherit";
    std::string matrix_backend = "inherit";
    std::string solver_backend = "inherit";
    std::string emissivity_backend = "inherit";
    std::string opacity_backend = "inherit";
    std::string thermal_backend = "inherit";
    std::size_t batch = 3;
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
        "  Component overrides: --engine-backend, --rates-backend, --matrix-backend,\n"
        "    --solver-backend, --emissivity-backend, --opacity-backend, --thermal-backend.\n"
        "  xstar_cpp run-zone --backend cpp|python --allow-scaffold [options]\n"
        "  xstar_cpp python-bridge-test [--plugin-dir DIR] [--python-path DIR]\n\n"
        "v0.6.45 adds a product-capable native element boundary for H, He, and Mg:\n"
        "source-ordered matrix construction, normalization, Lucy solve, and state\n"
        "commit execute in libxstar_engine.so with one call per element/evaluation.\n";
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

int command_element_self_test(const Options& options, bool evaluation) {
    xstar_context* context = nullptr;
    const int create_status = create_context(options, &context);
    if (create_status != XSTAR_STATUS_OK) return create_status;
    const std::size_t count = evaluation ? 3u : 1u;
    std::vector<ElementBuffers> buffers(count);
    std::vector<xstar_element_input_v1> inputs(count);
    std::vector<xstar_element_output_v1> outputs(count);
    const int elements[3] = {1, 2, 12};
    for (std::size_t i = 0; i < count; ++i) initialize_element(elements[i], buffers[i], inputs[i], outputs[i]);
    const int status = evaluation
        ? xstar_context_run_evaluation_v1(context, inputs.data(), count, outputs.data())
        : xstar_context_run_element_v1(context, inputs.data(), outputs.data());
    if (status != XSTAR_STATUS_OK) {
        std::cerr << "native element test failed: " << xstar_context_last_error(context) << "\n";
        xstar_context_destroy(context);
        return status;
    }
    for (std::size_t i = 0; i < count; ++i) {
        if (!validate_element(buffers[i], outputs[i])) {
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
    if (options.command == "element-self-test") return command_element_self_test(options, false);
    if (options.command == "evaluation-self-test") return command_element_self_test(options, true);
    if (options.command == "run-zone") return command_run_zone(options);
    if (options.command == "python-bridge-test") return command_python_bridge_test(options);
    std::cerr << "unknown command: " << options.command << "\n";
    usage(std::cerr);
    return 2;
}
