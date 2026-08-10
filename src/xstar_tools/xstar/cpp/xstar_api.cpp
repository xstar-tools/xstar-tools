// XSTAR-SOURCE-CORRESPONDENCE-BEGIN
// Fortran: Scientific boundary: xstar.f90 / xstarcalc.f90; no direct ABI analogue in Fortran.
// Role: Public C ABI context/configuration and dispatch into the qualified engine, spectral, thermal,
//   element, and backend components.
// Relation: Productization infrastructure over the Fortran-equivalent scientific boundary; no independent
//   physics.
// Concordance: BACKEND-001; ARCH-001
// Qualification: ABI 6048110; three-mode parity 12.3.44
// XSTAR-SOURCE-CORRESPONDENCE-END

#include "xstar_api.h"
#include "xstar_backend_plugin.h"
#include "xstar_standalone_internal.hpp"

#include <array>
#include <cstdlib>
#include <dlfcn.h>
#include <filesystem>
#include <memory>
#include <mutex>
#include <sstream>
#include <string>
#include <vector>

namespace {

using xstar_standalone::copy_text;
using xstar_standalone::field_text;

constexpr std::array<const char*, 2> kBackends{{"cpp", "python"}};
thread_local std::string g_api_last_error;

using element_create_fn = int (*)(xstar_element_engine_context**, char*, size_t);
using element_destroy_fn = void (*)(xstar_element_engine_context*);
using element_reset_fn = int (*)(xstar_element_engine_context*, char*, size_t);
using element_run_fn = int (*)(xstar_element_engine_context*, const xstar_element_input_v1*, xstar_element_output_v1*, char*, size_t);
using element_eval_fn = int (*)(xstar_element_engine_context*, const xstar_element_input_v1*, size_t, xstar_element_output_v1*, char*, size_t);
using element_construct_fn = int (*)(xstar_element_engine_context*, const xstar_element_input_v1*, const xstar_element_contribution_v1*, size_t, xstar_element_output_v1*, char*, size_t);
using element_construct_eval_fn = int (*)(xstar_element_engine_context*, const xstar_element_input_v1*, const xstar_element_contribution_v1* const*, const size_t*, size_t, xstar_element_output_v1*, char*, size_t);
using element_stats_fn = int (*)(const xstar_element_engine_context*, xstar_element_engine_stats_v1*, char*, size_t);
using spectral_create_fn = int (*)(xstar_spectral_context**, char*, size_t);
using spectral_destroy_fn = void (*)(xstar_spectral_context*);
using spectral_reset_fn = int (*)(xstar_spectral_context*, char*, size_t);
using spectral_apply_fn = int (*)(xstar_spectral_context*, const xstar_spectral_contribution_v1*, size_t, const double*, size_t, xstar_spectral_workspace_v1*, xstar_spectral_stats_v1*, char*, size_t);
using thermal_create_fn = int (*)(xstar_thermal_context**, char*, size_t);
using thermal_destroy_fn = void (*)(xstar_thermal_context*);
using thermal_reset_fn = int (*)(xstar_thermal_context*, char*, size_t);
using thermal_heatt_fn = int (*)(xstar_thermal_context*, xstar_heatt_workspace_v1*, const xstar_heatt_line_v1*, size_t, const xstar_heatt_rrc_v1*, size_t, xstar_heatt_stats_v1*, char*, size_t);
using thermal_loop_fn = int (*)(xstar_thermal_context*, const xstar_dsec_config_v1*, xstar_thermal_state_v1*, xstar_thermal_evaluator_fn_v1, void*, xstar_thermal_trace_event_v1*, size_t, size_t*, xstar_dsec_stats_v1*, char*, size_t);

struct LoadedPlugin {
    void* handle = nullptr;
    const xstar_backend_descriptor_v1* descriptor = nullptr;
    std::string path;

    ~LoadedPlugin() {
        if (handle != nullptr) dlclose(handle);
    }
};

struct xstar_context_impl {
    xstar_config_v1 config{};
    std::unique_ptr<LoadedPlugin> plugin;
    void* backend_context = nullptr;
    void* element_handle = nullptr;
    xstar_element_engine_context* element_context = nullptr;
    element_create_fn element_create = nullptr;
    element_destroy_fn element_destroy = nullptr;
    element_reset_fn element_reset = nullptr;
    element_run_fn element_run = nullptr;
    element_eval_fn element_eval = nullptr;
    element_construct_fn element_construct = nullptr;
    element_construct_eval_fn element_construct_eval = nullptr;
    element_stats_fn element_stats = nullptr;
    void* spectral_handle = nullptr;
    xstar_spectral_context* spectral_context = nullptr;
    spectral_create_fn spectral_create = nullptr;
    spectral_destroy_fn spectral_destroy = nullptr;
    spectral_reset_fn spectral_reset = nullptr;
    spectral_apply_fn spectral_apply = nullptr;
    void* thermal_handle = nullptr;
    xstar_thermal_context* thermal_context = nullptr;
    thermal_create_fn thermal_create = nullptr;
    thermal_destroy_fn thermal_destroy = nullptr;
    thermal_reset_fn thermal_reset = nullptr;
    thermal_heatt_fn thermal_heatt = nullptr;
    thermal_loop_fn thermal_loop = nullptr;
    std::string last_error;
    mutable std::mutex mutex;
};

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Implement plugin directories as a local helper for the xstar api module; inputs and outputs are kept in the source-compatible units expected by its caller.
// Reference context: Implementation/ABI helper; no independent scientific formula beyond the shared core it invokes.
// XSTAR-FUNCTION-COMMENT-END
std::vector<std::filesystem::path> plugin_directories(const xstar_config_v1& config) {
    std::vector<std::filesystem::path> result;
    const std::string configured = field_text(config.plugin_directory, XSTAR_PATH_SIZE);
    if (!configured.empty()) result.emplace_back(configured);
    if (const char* env = std::getenv("XSTAR_PLUGIN_PATH")) {
        std::stringstream stream(env);
        std::string item;
        while (std::getline(stream, item, ':')) {
            if (!item.empty()) result.emplace_back(item);
        }
    }
    result.push_back(xstar_standalone::executable_or_library_directory(
        reinterpret_cast<const void*>(&xstar_api_abi_version)));
    result.push_back(std::filesystem::current_path());
    std::vector<std::filesystem::path> unique;
    for (const auto& path : result) {
        if (path.empty()) continue;
        std::error_code error;
        auto normalized = std::filesystem::weakly_canonical(path, error);
        if (error) normalized = path;
        if (std::find(unique.begin(), unique.end(), normalized) == unique.end()) {
            unique.push_back(normalized);
        }
    }
    return unique;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Load plugin into the typed runtime representation, validating the fields needed by downstream source-faithful calculations.
// Reference context: Implementation/ABI helper; no independent scientific formula beyond the shared core it invokes.
// XSTAR-FUNCTION-COMMENT-END
std::unique_ptr<LoadedPlugin> load_plugin(
    const xstar_config_v1& config,
    const std::string& backend,
    std::string& error_message
) {
    const std::string filename = "libxstar_backend_" + backend + ".so";
    std::vector<std::string> failures;
    for (const auto& directory : plugin_directories(config)) {
        const auto candidate = directory / filename;
        void* handle = dlopen(candidate.c_str(), RTLD_NOW | RTLD_GLOBAL);
        if (handle == nullptr) {
            const char* error = dlerror();
            failures.push_back(candidate.string() + ": " + (error ? error : "dlopen failed"));
            continue;
        }
        dlerror();
        auto getter = reinterpret_cast<xstar_backend_get_descriptor_v1_fn>(
            dlsym(handle, "xstar_backend_get_descriptor_v1"));
        const char* symbol_error = dlerror();
        if (getter == nullptr || symbol_error != nullptr) {
            failures.push_back(candidate.string() + ": missing xstar_backend_get_descriptor_v1");
            dlclose(handle);
            continue;
        }
        const xstar_backend_descriptor_v1* descriptor = getter();
        if (descriptor == nullptr ||
            descriptor->struct_size < sizeof(xstar_backend_descriptor_v1) ||
            descriptor->plugin_abi_version != XSTAR_BACKEND_PLUGIN_ABI_VERSION ||
            descriptor->backend_name == nullptr ||
            backend != descriptor->backend_name) {
            failures.push_back(candidate.string() + ": incompatible backend descriptor");
            dlclose(handle);
            continue;
        }
        auto plugin = std::make_unique<LoadedPlugin>();
        plugin->handle = handle;
        plugin->descriptor = descriptor;
        plugin->path = candidate.string();
        return plugin;
    }
    std::ostringstream output;
    output << "could not load backend '" << backend << "'";
    for (const auto& failure : failures) output << "\n  " << failure;
    error_message = output.str();
    return nullptr;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Implement ensure element engine as a local helper for the xstar api module; inputs and outputs are kept in the source-compatible units expected by its caller.
// Reference context: Implementation/ABI helper; no independent scientific formula beyond the shared core it invokes.
// XSTAR-FUNCTION-COMMENT-END
int ensure_element_engine(xstar_context_impl& context) {
    if (context.element_context != nullptr) return XSTAR_STATUS_OK;
    const std::string backend = field_text(context.config.backend, XSTAR_BACKEND_NAME_SIZE);
    const std::string engine_backend = field_text(context.config.engine_backend, XSTAR_BACKEND_NAME_SIZE);
    if (backend != "cpp" || (!engine_backend.empty() && engine_backend != "inherit" && engine_backend != "cpp")) {
        context.last_error = "typed native element API requires backend=cpp and engine_backend=cpp/inherit";
        return XSTAR_STATUS_NOT_IMPLEMENTED;
    }
    std::vector<std::string> failures;
    for (const auto& directory : plugin_directories(context.config)) {
        const auto candidate = directory / "libxstar_engine.so";
        void* handle = dlopen(candidate.c_str(), RTLD_NOW | RTLD_LOCAL);
        if (!handle) {
            const char* error = dlerror();
            failures.push_back(candidate.string() + ": " + (error ? error : "dlopen failed"));
            continue;
        }
        auto abi = reinterpret_cast<uint32_t (*)()>(dlsym(handle, "xstar_element_engine_abi_version"));
        auto create = reinterpret_cast<element_create_fn>(dlsym(handle, "xstar_element_engine_context_create_v1"));
        auto destroy = reinterpret_cast<element_destroy_fn>(dlsym(handle, "xstar_element_engine_context_destroy"));
        auto reset = reinterpret_cast<element_reset_fn>(dlsym(handle, "xstar_element_engine_context_reset_v1"));
        auto run = reinterpret_cast<element_run_fn>(dlsym(handle, "xstar_element_engine_run_element_v1"));
        auto eval = reinterpret_cast<element_eval_fn>(dlsym(handle, "xstar_element_engine_run_evaluation_v1"));
        auto construct = reinterpret_cast<element_construct_fn>(dlsym(handle, "xstar_element_engine_run_construction_v1"));
        auto construct_eval = reinterpret_cast<element_construct_eval_fn>(dlsym(handle, "xstar_element_engine_run_construction_evaluation_v1"));
        auto stats = reinterpret_cast<element_stats_fn>(dlsym(handle, "xstar_element_engine_get_stats_v1"));
        if (!abi || abi() != XSTAR_ELEMENT_ENGINE_ABI_VERSION || !create || !destroy || !reset || !run || !eval || !construct || !construct_eval || !stats) {
            failures.push_back(candidate.string() + ": incompatible element-engine ABI");
            dlclose(handle);
            continue;
        }
        std::array<char, XSTAR_MESSAGE_SIZE> message{};
        xstar_element_engine_context* element_context = nullptr;
        const int rc = create(&element_context, message.data(), message.size());
        if (rc != 0 || !element_context) {
            failures.push_back(candidate.string() + ": " + std::string(message.data()));
            dlclose(handle);
            continue;
        }
        context.element_handle = handle;
        context.element_context = element_context;
        context.element_create = create;
        context.element_destroy = destroy;
        context.element_reset = reset;
        context.element_run = run;
        context.element_eval = eval;
        context.element_construct = construct;
        context.element_construct_eval = construct_eval;
        context.element_stats = stats;
        context.last_error = message.data();
        return XSTAR_STATUS_OK;
    }
    std::ostringstream text;
    text << "could not load native element engine";
    for (const auto& failure : failures) text << "\n  " << failure;
    context.last_error = text.str();
    return XSTAR_STATUS_BACKEND_LOAD_FAILED;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute ensure spectral engine for the line/emissivity/opacity path on the source or publication energy grid.
// Reference context: XSTAR Manual ss11.5.1, 11.6-11.6.1; Kallman & Bautista (2001); data type 50 where applicable.
// XSTAR-FUNCTION-COMMENT-END
int ensure_spectral_engine(xstar_context_impl& context) {
    if (context.spectral_context != nullptr) return XSTAR_STATUS_OK;
    const std::string backend = field_text(context.config.backend, XSTAR_BACKEND_NAME_SIZE);
    const std::string emissivity_backend = field_text(context.config.emissivity_backend, XSTAR_BACKEND_NAME_SIZE);
    const std::string opacity_backend = field_text(context.config.opacity_backend, XSTAR_BACKEND_NAME_SIZE);
    const auto compatible = [](const std::string& value) {
        return value.empty() || value == "inherit" || value == "cpp";
    };
    if (backend != "cpp" || !compatible(emissivity_backend) || !compatible(opacity_backend)) {
        context.last_error = "typed native spectral API requires backend=cpp and emissivity/opacity backend=cpp/inherit";
        return XSTAR_STATUS_NOT_IMPLEMENTED;
    }
    std::vector<std::string> failures;
    for (const auto& directory : plugin_directories(context.config)) {
        const auto candidate = directory / "libxstar_emissivity.so";
        void* handle = dlopen(candidate.c_str(), RTLD_NOW | RTLD_LOCAL);
        if (!handle) {
            const char* error = dlerror();
            failures.push_back(candidate.string() + ": " + (error ? error : "dlopen failed"));
            continue;
        }
        auto abi = reinterpret_cast<uint32_t (*)()>(dlsym(handle, "xstar_spectral_engine_abi_version"));
        auto create = reinterpret_cast<spectral_create_fn>(dlsym(handle, "xstar_spectral_context_create_v1"));
        auto destroy = reinterpret_cast<spectral_destroy_fn>(dlsym(handle, "xstar_spectral_context_destroy"));
        auto reset = reinterpret_cast<spectral_reset_fn>(dlsym(handle, "xstar_spectral_context_reset_v1"));
        auto apply = reinterpret_cast<spectral_apply_fn>(dlsym(handle, "xstar_spectral_apply_contributions_v1"));
        if (!abi || abi() != XSTAR_SPECTRAL_ENGINE_ABI_VERSION || !create || !destroy || !reset || !apply) {
            failures.push_back(candidate.string() + ": incompatible spectral-engine ABI");
            dlclose(handle);
            continue;
        }
        std::array<char, XSTAR_MESSAGE_SIZE> message{};
        xstar_spectral_context* spectral_context = nullptr;
        const int rc = create(&spectral_context, message.data(), message.size());
        if (rc != 0 || !spectral_context) {
            failures.push_back(candidate.string() + ": " + std::string(message.data()));
            dlclose(handle);
            continue;
        }
        context.spectral_handle = handle;
        context.spectral_context = spectral_context;
        context.spectral_create = create;
        context.spectral_destroy = destroy;
        context.spectral_reset = reset;
        context.spectral_apply = apply;
        context.last_error = message.data();
        return XSTAR_STATUS_OK;
    }
    std::ostringstream text;
    text << "could not load native spectral engine";
    for (const auto& failure : failures) text << "\n  " << failure;
    context.last_error = text.str();
    return XSTAR_STATUS_BACKEND_LOAD_FAILED;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute ensure thermal engine as a contribution to, or control step in, the local thermal-equilibrium iteration.
// Reference context: XSTAR Manual s11.4.4 and s11.6; Kallman & Bautista (2001).
// XSTAR-FUNCTION-COMMENT-END
int ensure_thermal_engine(xstar_context_impl& context) {
    if (context.thermal_context != nullptr) return XSTAR_STATUS_OK;
    const std::string backend = field_text(context.config.backend, XSTAR_BACKEND_NAME_SIZE);
    const std::string thermal_backend = field_text(context.config.thermal_backend, XSTAR_BACKEND_NAME_SIZE);
    if (backend != "cpp" || (!thermal_backend.empty() && thermal_backend != "inherit" && thermal_backend != "cpp")) {
        context.last_error = "native thermal API requires backend=cpp and thermal_backend=cpp/inherit";
        return XSTAR_STATUS_NOT_IMPLEMENTED;
    }
    std::vector<std::string> failures;
    for (const auto& directory : plugin_directories(context.config)) {
        const auto candidate = directory / "libxstar_thermal.so";
        void* handle = dlopen(candidate.c_str(), RTLD_NOW | RTLD_LOCAL);
        if (!handle) {
            const char* error = dlerror();
            failures.push_back(candidate.string() + ": " + (error ? error : "dlopen failed"));
            continue;
        }
        auto abi = reinterpret_cast<uint32_t (*)()>(dlsym(handle, "xstar_thermal_engine_abi_version"));
        auto create = reinterpret_cast<thermal_create_fn>(dlsym(handle, "xstar_thermal_context_create_v1"));
        auto destroy = reinterpret_cast<thermal_destroy_fn>(dlsym(handle, "xstar_thermal_context_destroy"));
        auto reset = reinterpret_cast<thermal_reset_fn>(dlsym(handle, "xstar_thermal_context_reset_v1"));
        auto heatt = reinterpret_cast<thermal_heatt_fn>(dlsym(handle, "xstar_thermal_apply_heatt_v1"));
        auto loop = reinterpret_cast<thermal_loop_fn>(dlsym(handle, "xstar_thermal_run_evaluation_loop_v1"));
        if (!abi || abi() != XSTAR_THERMAL_ENGINE_ABI_VERSION || !create || !destroy || !reset || !heatt || !loop) {
            failures.push_back(candidate.string() + ": incompatible thermal-engine ABI");
            dlclose(handle);
            continue;
        }
        std::array<char, XSTAR_MESSAGE_SIZE> message{};
        xstar_thermal_context* thermal_context = nullptr;
        const int rc = create(&thermal_context, message.data(), message.size());
        if (rc != 0 || !thermal_context) {
            failures.push_back(candidate.string() + ": " + std::string(message.data()));
            dlclose(handle);
            continue;
        }
        context.thermal_handle = handle;
        context.thermal_context = thermal_context;
        context.thermal_create = create;
        context.thermal_destroy = destroy;
        context.thermal_reset = reset;
        context.thermal_heatt = heatt;
        context.thermal_loop = loop;
        context.last_error = message.data();
        return XSTAR_STATUS_OK;
    }
    std::ostringstream text;
    text << "could not load native thermal engine";
    for (const auto& failure : failures) text << "\n  " << failure;
    context.last_error = text.str();
    return XSTAR_STATUS_BACKEND_LOAD_FAILED;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Validate the invariants required by validate config; reject malformed dimensions, pointers, or state before scientific kernels are entered.
// Reference context: Implementation/safety helper; no independent scientific formula.
// XSTAR-FUNCTION-COMMENT-END
int validate_config(const xstar_config_v1* config, std::string& error) {
    if (config == nullptr) {
        error = "config is null";
        return XSTAR_STATUS_INVALID_ARGUMENT;
    }
    if (config->struct_size < sizeof(xstar_config_v1)) {
        error = "config struct is too small";
        return XSTAR_STATUS_INVALID_ARGUMENT;
    }
    if (config->abi_version != XSTAR_API_ABI_VERSION) {
        error = "config ABI version mismatch";
        return XSTAR_STATUS_ABI_MISMATCH;
    }
    const std::string backend = field_text(config->backend, XSTAR_BACKEND_NAME_SIZE);
    if (backend.empty()) {
        error = "backend name is empty";
        return XSTAR_STATUS_INVALID_ARGUMENT;
    }
    if (std::find_if(kBackends.begin(), kBackends.end(), [&](const char* name) {
            return backend == name;
        }) == kBackends.end()) {
        error = "backend is not registered: " + backend;
        return XSTAR_STATUS_BACKEND_NOT_FOUND;
    }
    return XSTAR_STATUS_OK;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Validate the invariants required by validate io; reject malformed dimensions, pointers, or state before scientific kernels are entered.
// Reference context: Implementation/safety helper; no independent scientific formula.
// XSTAR-FUNCTION-COMMENT-END
int validate_io(const xstar_zone_input_v1* input, xstar_zone_output_v1* output, std::string& error) {
    if (input == nullptr || output == nullptr) {
        error = "zone input/output is null";
        return XSTAR_STATUS_INVALID_ARGUMENT;
    }
    if (input->struct_size < sizeof(xstar_zone_input_v1) ||
        output->struct_size < sizeof(xstar_zone_output_v1)) {
        error = "zone input/output struct is too small";
        return XSTAR_STATUS_INVALID_ARGUMENT;
    }
    if (input->abundance_count > 0 && input->abundances == nullptr) {
        error = "abundances pointer is null";
        return XSTAR_STATUS_INVALID_ARGUMENT;
    }
    if (input->radiation_bin_count > 0 &&
        (input->radiation_energy == nullptr || input->radiation_flux == nullptr)) {
        error = "radiation arrays are incomplete";
        return XSTAR_STATUS_INVALID_ARGUMENT;
    }
    return XSTAR_STATUS_OK;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Implement impl as a local helper for the xstar api module; inputs and outputs are kept in the source-compatible units expected by its caller.
// Reference context: Implementation/ABI helper; no independent scientific formula beyond the shared core it invokes.
// XSTAR-FUNCTION-COMMENT-END
xstar_context_impl* impl(xstar_context* context) {
    return reinterpret_cast<xstar_context_impl*>(context);
}
// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Implement impl as a local helper for the xstar api module; inputs and outputs are kept in the source-compatible units expected by its caller.
// Reference context: Implementation/ABI helper; no independent scientific formula beyond the shared core it invokes.
// XSTAR-FUNCTION-COMMENT-END
const xstar_context_impl* impl(const xstar_context* context) {
    return reinterpret_cast<const xstar_context_impl*>(context);
}

} // namespace

extern "C" {

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Return the ABI version for the api interface so callers can reject incompatible binary layouts before execution.
// Reference context: Implementation/compatibility helper; no independent scientific formula.
// XSTAR-FUNCTION-COMMENT-END
uint32_t xstar_api_abi_version(void) { return XSTAR_API_ABI_VERSION; }
// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Implement api version string as a local helper for the xstar api module; inputs and outputs are kept in the source-compatible units expected by its caller.
// Reference context: Implementation/ABI helper; no independent scientific formula beyond the shared core it invokes.
// XSTAR-FUNCTION-COMMENT-END
const char* xstar_api_version_string(void) { return XSTAR_API_VERSION_STRING; }
// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Implement backend count as a local helper for the xstar api module; inputs and outputs are kept in the source-compatible units expected by its caller.
// Reference context: Implementation/ABI helper; no independent scientific formula beyond the shared core it invokes.
// XSTAR-FUNCTION-COMMENT-END
size_t xstar_backend_count(void) { return kBackends.size(); }
// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Report the compiled backend name capability metadata used by backend selection and provenance.
// Reference context: Implementation/provenance helper; no independent scientific formula.
// XSTAR-FUNCTION-COMMENT-END
const char* xstar_backend_name(size_t index) {
    return index < kBackends.size() ? kBackends[index] : nullptr;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Implement api last error as a local helper for the xstar api module; inputs and outputs are kept in the source-compatible units expected by its caller.
// Reference context: Implementation/ABI helper; no independent scientific formula beyond the shared core it invokes.
// XSTAR-FUNCTION-COMMENT-END
const char* xstar_api_last_error(void) { return g_api_last_error.c_str(); }

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Implement status string as a local helper for the xstar api module; inputs and outputs are kept in the source-compatible units expected by its caller.
// Reference context: Implementation/ABI helper; no independent scientific formula beyond the shared core it invokes.
// XSTAR-FUNCTION-COMMENT-END
const char* xstar_status_string(int status) {
    switch (status) {
        case XSTAR_STATUS_OK: return "ok";
        case XSTAR_STATUS_INVALID_ARGUMENT: return "invalid argument";
        case XSTAR_STATUS_ABI_MISMATCH: return "ABI mismatch";
        case XSTAR_STATUS_BACKEND_NOT_FOUND: return "backend not found";
        case XSTAR_STATUS_BACKEND_LOAD_FAILED: return "backend load failed";
        case XSTAR_STATUS_BACKEND_ERROR: return "backend error";
        case XSTAR_STATUS_BUFFER_TOO_SMALL: return "buffer too small";
        case XSTAR_STATUS_NOT_IMPLEMENTED: return "not implemented";
        case XSTAR_STATUS_INTERNAL_ERROR: return "internal error";
        default: return "unknown status";
    }
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Initialize the config init structure to its ABI-safe defaults before the caller supplies model-specific values.
// Reference context: Implementation/ABI helper; scientific meaning is defined by the consuming engine.
// XSTAR-FUNCTION-COMMENT-END
int xstar_config_init_v1(xstar_config_v1* config) {
    if (config == nullptr) return XSTAR_STATUS_INVALID_ARGUMENT;
    *config = {};
    config->struct_size = sizeof(*config);
    config->abi_version = XSTAR_API_ABI_VERSION;
    config->flags = XSTAR_CONFIG_ENABLE_FALLBACK | XSTAR_CONFIG_STRICT_SOURCE_ORDER;
    config->thread_count = 1;
    copy_text(config->backend, sizeof(config->backend), "cpp");
    copy_text(config->engine_backend, sizeof(config->engine_backend), "inherit");
    copy_text(config->rates_backend, sizeof(config->rates_backend), "inherit");
    copy_text(config->matrix_backend, sizeof(config->matrix_backend), "inherit");
    copy_text(config->solver_backend, sizeof(config->solver_backend), "inherit");
    copy_text(config->emissivity_backend, sizeof(config->emissivity_backend), "inherit");
    copy_text(config->opacity_backend, sizeof(config->opacity_backend), "inherit");
    copy_text(config->thermal_backend, sizeof(config->thermal_backend), "inherit");
    return XSTAR_STATUS_OK;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Initialize the zone input init structure to its ABI-safe defaults before the caller supplies model-specific values.
// Reference context: Implementation/ABI helper; scientific meaning is defined by the consuming engine.
// XSTAR-FUNCTION-COMMENT-END
int xstar_zone_input_init_v1(xstar_zone_input_v1* input) {
    if (input == nullptr) return XSTAR_STATUS_INVALID_ARGUMENT;
    *input = {};
    input->struct_size = sizeof(*input);
    return XSTAR_STATUS_OK;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Initialize the zone output init structure to its ABI-safe defaults before the caller supplies model-specific values.
// Reference context: Implementation/ABI helper; scientific meaning is defined by the consuming engine.
// XSTAR-FUNCTION-COMMENT-END
int xstar_zone_output_init_v1(xstar_zone_output_v1* output) {
    if (output == nullptr) return XSTAR_STATUS_INVALID_ARGUMENT;
    *output = {};
    output->struct_size = sizeof(*output);
    return XSTAR_STATUS_OK;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Initialize the context stats init structure to its ABI-safe defaults before the caller supplies model-specific values.
// Reference context: Implementation/ABI helper; scientific meaning is defined by the consuming engine.
// XSTAR-FUNCTION-COMMENT-END
int xstar_context_stats_init_v1(xstar_context_stats_v1* stats) {
    if (stats == nullptr) return XSTAR_STATUS_INVALID_ARGUMENT;
    *stats = {};
    stats->struct_size = sizeof(*stats);
    return XSTAR_STATUS_OK;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Initialize the component info init structure to its ABI-safe defaults before the caller supplies model-specific values.
// Reference context: Implementation/ABI helper; scientific meaning is defined by the consuming engine.
// XSTAR-FUNCTION-COMMENT-END
int xstar_component_info_init_v1(xstar_component_info_v1* info) {
    if (info == nullptr) return XSTAR_STATUS_INVALID_ARGUMENT;
    *info = {};
    info->struct_size = sizeof(*info);
    return XSTAR_STATUS_OK;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Create and validate persistent runtime state for context create, loading only the data needed by subsequent calls.
// Reference context: Implementation/lifetime helper; the scientific work is performed by the shared engine routines called from this context.
// XSTAR-FUNCTION-COMMENT-END
int xstar_context_create_v1(const xstar_config_v1* config, xstar_context** context) {
    if (context == nullptr) return XSTAR_STATUS_INVALID_ARGUMENT;
    *context = nullptr;
    std::string error;
    int status = validate_config(config, error);
    if (status != XSTAR_STATUS_OK) { g_api_last_error = error; return status; }

    auto result = std::make_unique<xstar_context_impl>();
    result->config = *config;
    const std::string backend = field_text(config->backend, XSTAR_BACKEND_NAME_SIZE);
    result->plugin = load_plugin(*config, backend, error);
    if (!result->plugin) { g_api_last_error = error; return XSTAR_STATUS_BACKEND_LOAD_FAILED; }
    if (result->plugin->descriptor->create == nullptr) {
        g_api_last_error = "backend create callback is missing";
        return XSTAR_STATUS_BACKEND_ERROR;
    }

    std::array<char, XSTAR_MESSAGE_SIZE> message{};
    status = result->plugin->descriptor->create(
        config, &result->backend_context, message.data(), message.size());
    if (status != XSTAR_STATUS_OK) {
        result->last_error = message.data();
        g_api_last_error = result->last_error;
        return status;
    }
    result->last_error.clear();
    g_api_last_error.clear();
    *context = reinterpret_cast<xstar_context*>(result.release());
    return XSTAR_STATUS_OK;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Destroy the persistent context destroy context and release its owned resources without changing external science state.
// Reference context: Implementation/lifetime helper; no independent scientific formula.
// XSTAR-FUNCTION-COMMENT-END
void xstar_context_destroy(xstar_context* context) {
    auto* value = impl(context);
    if (value == nullptr) return;
    if (value->thermal_context && value->thermal_destroy) {
        value->thermal_destroy(value->thermal_context);
        value->thermal_context = nullptr;
    }
    if (value->thermal_handle) {
        dlclose(value->thermal_handle);
        value->thermal_handle = nullptr;
    }
    if (value->spectral_context && value->spectral_destroy) {
        value->spectral_destroy(value->spectral_context);
        value->spectral_context = nullptr;
    }
    if (value->spectral_handle) {
        dlclose(value->spectral_handle);
        value->spectral_handle = nullptr;
    }
    if (value->element_context && value->element_destroy) {
        value->element_destroy(value->element_context);
        value->element_context = nullptr;
    }
    if (value->element_handle) {
        dlclose(value->element_handle);
        value->element_handle = nullptr;
    }
    if (value->plugin && value->plugin->descriptor && value->plugin->descriptor->destroy) {
        value->plugin->descriptor->destroy(value->backend_context);
    }
    delete value;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Reset reusable context reset state between model evaluations while preserving immutable loaded data and ABI invariants.
// Reference context: Implementation/lifetime helper; no independent scientific formula.
// XSTAR-FUNCTION-COMMENT-END
int xstar_context_reset(xstar_context* context) {
    auto* value = impl(context);
    if (value == nullptr) return XSTAR_STATUS_INVALID_ARGUMENT;
    std::lock_guard<std::mutex> lock(value->mutex);
    if (!value->plugin->descriptor->reset) return XSTAR_STATUS_NOT_IMPLEMENTED;
    std::array<char, XSTAR_MESSAGE_SIZE> message{};
    const int status = value->plugin->descriptor->reset(
        value->backend_context, message.data(), message.size());
    value->last_error = message.data();
    if (status == XSTAR_STATUS_OK && value->thermal_context && value->thermal_reset) {
        std::array<char, XSTAR_MESSAGE_SIZE> thermal_message{};
        const int thermal_status = value->thermal_reset(
            value->thermal_context, thermal_message.data(), thermal_message.size());
        if (thermal_status != 0) {
            value->last_error = thermal_message.data();
            return XSTAR_STATUS_BACKEND_ERROR;
        }
    }
    if (status == XSTAR_STATUS_OK && value->spectral_context && value->spectral_reset) {
        std::array<char, XSTAR_MESSAGE_SIZE> spectral_message{};
        const int spectral_status = value->spectral_reset(
            value->spectral_context, spectral_message.data(), spectral_message.size());
        if (spectral_status != 0) {
            value->last_error = spectral_message.data();
            return XSTAR_STATUS_BACKEND_ERROR;
        }
    }
    if (status == XSTAR_STATUS_OK && value->element_context && value->element_reset) {
        std::array<char, XSTAR_MESSAGE_SIZE> element_message{};
        const int element_status = value->element_reset(
            value->element_context, element_message.data(), element_message.size());
        if (element_status != 0) {
            value->last_error = element_message.data();
            return XSTAR_STATUS_BACKEND_ERROR;
        }
    }
    return status;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Report the compiled context backend name capability metadata used by backend selection and provenance.
// Reference context: Implementation/provenance helper; no independent scientific formula.
// XSTAR-FUNCTION-COMMENT-END
const char* xstar_context_backend_name(const xstar_context* context) {
    const auto* value = impl(context);
    if (!value || !value->plugin || !value->plugin->descriptor) return nullptr;
    return value->plugin->descriptor->backend_name;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Implement context last error as a local helper for the xstar api module; inputs and outputs are kept in the source-compatible units expected by its caller.
// Reference context: Implementation/ABI helper; no independent scientific formula beyond the shared core it invokes.
// XSTAR-FUNCTION-COMMENT-END
const char* xstar_context_last_error(const xstar_context* context) {
    const auto* value = impl(context);
    return value ? value->last_error.c_str() : "null context";
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Implement context get stats as a local helper for the xstar api module; inputs and outputs are kept in the source-compatible units expected by its caller.
// Reference context: Implementation/ABI helper; no independent scientific formula beyond the shared core it invokes.
// XSTAR-FUNCTION-COMMENT-END
int xstar_context_get_stats_v1(const xstar_context* context, xstar_context_stats_v1* stats) {
    const auto* value = impl(context);
    if (value == nullptr || stats == nullptr || stats->struct_size < sizeof(*stats)) {
        return XSTAR_STATUS_INVALID_ARGUMENT;
    }
    std::lock_guard<std::mutex> lock(value->mutex);
    if (!value->plugin->descriptor->get_stats) return XSTAR_STATUS_NOT_IMPLEMENTED;
    std::array<char, XSTAR_MESSAGE_SIZE> message{};
    const int status = value->plugin->descriptor->get_stats(
        value->backend_context, stats, message.data(), message.size());
    const_cast<xstar_context_impl*>(value)->last_error = message.data();
    return status;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Implement context get component info as a local helper for the xstar api module; inputs and outputs are kept in the source-compatible units expected by its caller.
// Reference context: Implementation/ABI helper; no independent scientific formula beyond the shared core it invokes.
// XSTAR-FUNCTION-COMMENT-END
int xstar_context_get_component_info_v1(
    const xstar_context* context,
    uint32_t component_id,
    xstar_component_info_v1* info
) {
    const auto* value = impl(context);
    if (value == nullptr || info == nullptr || info->struct_size < sizeof(*info) ||
        component_id >= XSTAR_COMPONENT_COUNT) {
        return XSTAR_STATUS_INVALID_ARGUMENT;
    }
    std::lock_guard<std::mutex> lock(value->mutex);
    if (!value->plugin->descriptor->get_component_info) return XSTAR_STATUS_NOT_IMPLEMENTED;
    std::array<char, XSTAR_MESSAGE_SIZE> message{};
    const int status = value->plugin->descriptor->get_component_info(
        value->backend_context, component_id, info, message.data(), message.size());
    const_cast<xstar_context_impl*>(value)->last_error = message.data();
    return status;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Implement context run zone as a local helper for the xstar api module; inputs and outputs are kept in the source-compatible units expected by its caller.
// Reference context: Implementation/ABI helper; no independent scientific formula beyond the shared core it invokes.
// XSTAR-FUNCTION-COMMENT-END
int xstar_context_run_zone_v1(
    xstar_context* context,
    const xstar_zone_input_v1* input,
    xstar_zone_output_v1* output
) {
    auto* value = impl(context);
    if (value == nullptr) return XSTAR_STATUS_INVALID_ARGUMENT;
    std::string validation_error;
    const int validation = validate_io(input, output, validation_error);
    if (validation != XSTAR_STATUS_OK) {
        value->last_error = validation_error;
        return validation;
    }
    std::lock_guard<std::mutex> lock(value->mutex);
    if (!value->plugin->descriptor->run_zone) return XSTAR_STATUS_NOT_IMPLEMENTED;
    std::array<char, XSTAR_MESSAGE_SIZE> message{};
    const int status = value->plugin->descriptor->run_zone(
        value->backend_context, input, output, message.data(), message.size());
    value->last_error = message.data();
    return status;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Implement context run batch as a local helper for the xstar api module; inputs and outputs are kept in the source-compatible units expected by its caller.
// Reference context: Implementation/ABI helper; no independent scientific formula beyond the shared core it invokes.
// XSTAR-FUNCTION-COMMENT-END
int xstar_context_run_batch_v1(
    xstar_context* context,
    const xstar_zone_input_v1* inputs,
    size_t zone_count,
    xstar_zone_output_v1* outputs
) {
    auto* value = impl(context);
    if (value == nullptr || (zone_count > 0 && (inputs == nullptr || outputs == nullptr))) {
        return XSTAR_STATUS_INVALID_ARGUMENT;
    }
    for (size_t index = 0; index < zone_count; ++index) {
        std::string error;
        const int validation = validate_io(inputs + index, outputs + index, error);
        if (validation != XSTAR_STATUS_OK) {
            value->last_error = "zone " + std::to_string(index) + ": " + error;
            return validation;
        }
    }
    std::lock_guard<std::mutex> lock(value->mutex);
    if (!value->plugin->descriptor->run_batch) return XSTAR_STATUS_NOT_IMPLEMENTED;
    std::array<char, XSTAR_MESSAGE_SIZE> message{};
    const int status = value->plugin->descriptor->run_batch(
        value->backend_context, inputs, zone_count, outputs, message.data(), message.size());
    value->last_error = message.data();
    return status;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Implement context run element construction as a local helper for the xstar api module; inputs and outputs are kept in the source-compatible units expected by its caller.
// Reference context: Implementation/ABI helper; no independent scientific formula beyond the shared core it invokes.
// XSTAR-FUNCTION-COMMENT-END
int xstar_context_run_element_construction_v1(
    xstar_context* context,
    const xstar_element_input_v1* input,
    const xstar_element_contribution_v1* contributions,
    size_t contribution_count,
    xstar_element_output_v1* output
) {
    auto* value = impl(context);
    if (!value || !input || !output || (contribution_count && !contributions)) return XSTAR_STATUS_INVALID_ARGUMENT;
    std::lock_guard<std::mutex> lock(value->mutex);
    const int load_status = ensure_element_engine(*value);
    if (load_status != XSTAR_STATUS_OK) return load_status;
    std::array<char, XSTAR_MESSAGE_SIZE> message{};
    const int rc = value->element_construct(value->element_context, input, contributions, contribution_count, output, message.data(), message.size());
    value->last_error = message.data();
    return rc == 0 ? XSTAR_STATUS_OK : XSTAR_STATUS_BACKEND_ERROR;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Implement context run element as a local helper for the xstar api module; inputs and outputs are kept in the source-compatible units expected by its caller.
// Reference context: Implementation/ABI helper; no independent scientific formula beyond the shared core it invokes.
// XSTAR-FUNCTION-COMMENT-END
int xstar_context_run_element_v1(
    xstar_context* context,
    const xstar_element_input_v1* input,
    xstar_element_output_v1* output
) {
    auto* value = impl(context);
    if (!value || !input || !output) return XSTAR_STATUS_INVALID_ARGUMENT;
    std::lock_guard<std::mutex> lock(value->mutex);
    const int load_status = ensure_element_engine(*value);
    if (load_status != XSTAR_STATUS_OK) return load_status;
    std::array<char, XSTAR_MESSAGE_SIZE> message{};
    const int rc = value->element_run(value->element_context, input, output, message.data(), message.size());
    value->last_error = message.data();
    return rc == 0 ? XSTAR_STATUS_OK : XSTAR_STATUS_BACKEND_ERROR;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Implement context run construction evaluation as a local helper for the xstar api module; inputs and outputs are kept in the source-compatible units expected by its caller.
// Reference context: Implementation/ABI helper; no independent scientific formula beyond the shared core it invokes.
// XSTAR-FUNCTION-COMMENT-END
int xstar_context_run_construction_evaluation_v1(
    xstar_context* context,
    const xstar_element_input_v1* inputs,
    const xstar_element_contribution_v1* const* contribution_arrays,
    const size_t* contribution_counts,
    size_t element_count,
    xstar_element_output_v1* outputs
) {
    auto* value = impl(context);
    if (!value || (element_count && (!inputs || !outputs || !contribution_arrays || !contribution_counts))) return XSTAR_STATUS_INVALID_ARGUMENT;
    std::lock_guard<std::mutex> lock(value->mutex);
    const int load_status = ensure_element_engine(*value);
    if (load_status != XSTAR_STATUS_OK) return load_status;
    std::array<char, XSTAR_MESSAGE_SIZE> message{};
    const int rc = value->element_construct_eval(value->element_context, inputs, contribution_arrays, contribution_counts, element_count, outputs, message.data(), message.size());
    value->last_error = message.data();
    return rc == 0 ? XSTAR_STATUS_OK : XSTAR_STATUS_BACKEND_ERROR;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Implement context run evaluation as a local helper for the xstar api module; inputs and outputs are kept in the source-compatible units expected by its caller.
// Reference context: Implementation/ABI helper; no independent scientific formula beyond the shared core it invokes.
// XSTAR-FUNCTION-COMMENT-END
int xstar_context_run_evaluation_v1(
    xstar_context* context,
    const xstar_element_input_v1* inputs,
    size_t element_count,
    xstar_element_output_v1* outputs
) {
    auto* value = impl(context);
    if (!value || (element_count && (!inputs || !outputs))) return XSTAR_STATUS_INVALID_ARGUMENT;
    std::lock_guard<std::mutex> lock(value->mutex);
    const int load_status = ensure_element_engine(*value);
    if (load_status != XSTAR_STATUS_OK) return load_status;
    std::array<char, XSTAR_MESSAGE_SIZE> message{};
    const int rc = value->element_eval(value->element_context, inputs, element_count, outputs, message.data(), message.size());
    value->last_error = message.data();
    return rc == 0 ? XSTAR_STATUS_OK : XSTAR_STATUS_BACKEND_ERROR;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Implement context get element stats as a local helper for the xstar api module; inputs and outputs are kept in the source-compatible units expected by its caller.
// Reference context: Implementation/ABI helper; no independent scientific formula beyond the shared core it invokes.
// XSTAR-FUNCTION-COMMENT-END
int xstar_context_get_element_stats_v1(
    const xstar_context* context,
    xstar_element_engine_stats_v1* stats
) {
    auto* value = const_cast<xstar_context_impl*>(impl(context));
    if (!value || !stats || stats->struct_size < sizeof(*stats)) return XSTAR_STATUS_INVALID_ARGUMENT;
    std::lock_guard<std::mutex> lock(value->mutex);
    const int load_status = ensure_element_engine(*value);
    if (load_status != XSTAR_STATUS_OK) return load_status;
    std::array<char, XSTAR_MESSAGE_SIZE> message{};
    const int rc = value->element_stats(value->element_context, stats, message.data(), message.size());
    value->last_error = message.data();
    return rc == 0 ? XSTAR_STATUS_OK : XSTAR_STATUS_BACKEND_ERROR;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute context apply spectral contributions for the line/emissivity/opacity path on the source or publication energy grid.
// Reference context: XSTAR Manual ss11.5.1, 11.6-11.6.1; Kallman & Bautista (2001); data type 50 where applicable.
// XSTAR-FUNCTION-COMMENT-END
int xstar_context_apply_spectral_contributions_v1(
    xstar_context* context,
    const xstar_spectral_contribution_v1* contributions,
    size_t contribution_count,
    const double* seed_profiles,
    size_t seed_profile_stride,
    xstar_spectral_workspace_v1* workspace,
    xstar_spectral_stats_v1* stats
) {
    auto* value = impl(context);
    if (!value || !workspace || !stats || (contribution_count && !contributions)) {
        return XSTAR_STATUS_INVALID_ARGUMENT;
    }
    std::lock_guard<std::mutex> lock(value->mutex);
    const int load_status = ensure_spectral_engine(*value);
    if (load_status != XSTAR_STATUS_OK) return load_status;
    std::array<char, XSTAR_MESSAGE_SIZE> message{};
    const int rc = value->spectral_apply(
        value->spectral_context, contributions, contribution_count,
        seed_profiles, seed_profile_stride, workspace, stats,
        message.data(), message.size());
    value->last_error = message.data();
    return rc == 0 ? XSTAR_STATUS_OK : XSTAR_STATUS_BACKEND_ERROR;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute context apply heatt as a contribution to, or control step in, the local thermal-equilibrium iteration.
// Reference context: XSTAR Manual s11.4.4 and s11.6; Kallman & Bautista (2001).
// XSTAR-FUNCTION-COMMENT-END
int xstar_context_apply_heatt_v1(
    xstar_context* context,
    xstar_heatt_workspace_v1* workspace,
    const xstar_heatt_line_v1* lines,
    size_t line_count,
    const xstar_heatt_rrc_v1* rrcs,
    size_t rrc_count,
    xstar_heatt_stats_v1* stats
) {
    auto* value = impl(context);
    if (!value || !workspace || !stats || (line_count && !lines) || (rrc_count && !rrcs)) {
        return XSTAR_STATUS_INVALID_ARGUMENT;
    }
    std::lock_guard<std::mutex> lock(value->mutex);
    const int load_status = ensure_thermal_engine(*value);
    if (load_status != XSTAR_STATUS_OK) return load_status;
    std::array<char, XSTAR_MESSAGE_SIZE> message{};
    const int rc = value->thermal_heatt(value->thermal_context, workspace, lines, line_count, rrcs, rrc_count, stats, message.data(), message.size());
    value->last_error = message.data();
    return rc == 0 ? XSTAR_STATUS_OK : XSTAR_STATUS_BACKEND_ERROR;
}

// XSTAR-FUNCTION-COMMENT-BEGIN
// Purpose: Compute context run thermal evaluation loop as a contribution to, or control step in, the local thermal-equilibrium iteration.
// Reference context: XSTAR Manual s11.4.4 and s11.6; Kallman & Bautista (2001).
// XSTAR-FUNCTION-COMMENT-END
int xstar_context_run_thermal_evaluation_loop_v1(
    xstar_context* context,
    const xstar_dsec_config_v1* config,
    xstar_thermal_state_v1* state,
    xstar_thermal_evaluator_fn_v1 evaluator,
    void* user_data,
    xstar_thermal_trace_event_v1* trace,
    size_t trace_capacity,
    size_t* trace_count,
    xstar_dsec_stats_v1* stats
) {
    auto* value = impl(context);
    if (!value || !config || !state || !evaluator || !stats) return XSTAR_STATUS_INVALID_ARGUMENT;
    std::lock_guard<std::mutex> lock(value->mutex);
    const int load_status = ensure_thermal_engine(*value);
    if (load_status != XSTAR_STATUS_OK) return load_status;
    std::array<char, XSTAR_MESSAGE_SIZE> message{};
    const int rc = value->thermal_loop(value->thermal_context, config, state, evaluator, user_data, trace, trace_capacity, trace_count, stats, message.data(), message.size());
    value->last_error = message.data();
    return rc == 0 ? XSTAR_STATUS_OK : XSTAR_STATUS_BACKEND_ERROR;
}

} // extern "C"
