#include "xstar_backend_plugin.h"
#include "xstar_standalone_internal.hpp"

#include <algorithm>
#include <array>
#include <cstdint>
#include <cstring>
#include <dlfcn.h>
#include <filesystem>
#include <memory>
#include <sstream>
#include <string>
#include <vector>

namespace {

using xstar_standalone::copy_text;

struct ComponentLibrary {
    std::uint32_t id = 0;
    std::string logical_name;
    std::string filename;
    std::string prefix;
    std::string path;
    std::string implementation;
    std::string error;
    void* handle = nullptr;
    int abi_version = 0;
    int feature_flags = 0;
    bool loaded = false;

    ComponentLibrary() = default;
    ComponentLibrary(const ComponentLibrary&) = delete;
    ComponentLibrary& operator=(const ComponentLibrary&) = delete;
    ComponentLibrary(ComponentLibrary&& other) noexcept
        : id(other.id), logical_name(std::move(other.logical_name)),
          filename(std::move(other.filename)), prefix(std::move(other.prefix)),
          path(std::move(other.path)), implementation(std::move(other.implementation)),
          error(std::move(other.error)), handle(other.handle), abi_version(other.abi_version),
          feature_flags(other.feature_flags), loaded(other.loaded) {
        other.handle = nullptr;
    }
    ComponentLibrary& operator=(ComponentLibrary&& other) noexcept {
        if (this != &other) {
            if (handle) dlclose(handle);
            id = other.id;
            logical_name = std::move(other.logical_name);
            filename = std::move(other.filename);
            prefix = std::move(other.prefix);
            path = std::move(other.path);
            implementation = std::move(other.implementation);
            error = std::move(other.error);
            handle = other.handle;
            abi_version = other.abi_version;
            feature_flags = other.feature_flags;
            loaded = other.loaded;
            other.handle = nullptr;
        }
        return *this;
    }
    ~ComponentLibrary() { if (handle) dlclose(handle); }
};

struct CppBackendContext {
    xstar_config_v1 config{};
    std::array<ComponentLibrary, 7> components;
    xstar_context_stats_v1 stats{};
};

std::filesystem::path component_directory(const xstar_config_v1& config) {
    const std::string configured = xstar_standalone::field_text(
        config.plugin_directory, XSTAR_PATH_SIZE);
    if (!configured.empty()) return configured;
    return xstar_standalone::executable_or_library_directory(
        reinterpret_cast<const void*>(&xstar_backend_get_descriptor_v1));
}

ComponentLibrary load_component(
    std::uint32_t id,
    const char* logical_name,
    const char* filename,
    const char* prefix,
    const std::filesystem::path& directory
) {
    ComponentLibrary result;
    result.id = id;
    result.logical_name = logical_name;
    result.filename = filename;
    result.prefix = prefix;
    const auto candidate = directory / filename;
    result.path = candidate.string();
    result.handle = dlopen(candidate.c_str(), RTLD_NOW | RTLD_LOCAL);
    if (!result.handle) {
        result.error = dlerror() ? dlerror() : "dlopen failed";
        return result;
    }
    using abi_fn = int (*)();
    using name_fn = const char* (*)();
    using flags_fn = int (*)();
    auto abi = reinterpret_cast<abi_fn>(dlsym(result.handle, (result.prefix + "_abi_version").c_str()));
    auto name = reinterpret_cast<name_fn>(dlsym(result.handle, (result.prefix + "_backend_name").c_str()));
    auto flags = reinterpret_cast<flags_fn>(dlsym(result.handle, (result.prefix + "_feature_flags").c_str()));
    if (!abi || !name) {
        result.error = "required ABI/name symbols missing";
        dlclose(result.handle);
        result.handle = nullptr;
        return result;
    }
    result.abi_version = abi();
    const char* implementation = name();
    result.implementation = implementation ? implementation : "unknown";
    result.feature_flags = flags ? flags() : 1;
    result.loaded = true;
    return result;
}

void initialize_components(CppBackendContext& context) {
    const auto directory = component_directory(context.config);
    context.components = {{
        load_component(XSTAR_COMPONENT_ENGINE, "engine", "libxstar_engine.so", "xstar_engine", directory),
        load_component(XSTAR_COMPONENT_RATES, "rates", "libxstar_rates.so", "xstar_rates", directory),
        load_component(XSTAR_COMPONENT_MATRIX, "matrix", "libxstar_matrix.so", "xstar_matrix", directory),
        load_component(XSTAR_COMPONENT_SOLVER, "solver", "libxstar_solver.so", "xstar_solver", directory),
        load_component(XSTAR_COMPONENT_EMISSIVITY, "emissivity", "libxstar_emissivity.so", "xstar_emissivity", directory),
        load_component(XSTAR_COMPONENT_OPACITY, "opacity", "libxstar_opacity.so", "xstar_opacity", directory),
        load_component(XSTAR_COMPONENT_THERMAL, "thermal", "libxstar_thermal.so", "xstar_thermal", directory),
    }};
}

int cpp_create(const xstar_config_v1* config, void** output, char* message, std::size_t message_size) {
    if (!config || !output) return XSTAR_STATUS_INVALID_ARGUMENT;
    auto context = std::make_unique<CppBackendContext>();
    context->config = *config;
    xstar_context_stats_init_v1(&context->stats);
    initialize_components(*context);
    std::size_t loaded = 0;
    for (const auto& component : context->components) loaded += component.loaded ? 1u : 0u;
    std::ostringstream text;
    text << "C++ backend context created; component_libraries=" << loaded << "/7"
         << "; persistent_context=true; physics_boundary=compiled_case_or_scaffold";
    copy_text(message, message_size, text.str());
    *output = context.release();
    return XSTAR_STATUS_OK;
}

void cpp_destroy(void* opaque) {
    delete static_cast<CppBackendContext*>(opaque);
}

int cpp_reset(void* opaque, char* message, std::size_t message_size) {
    auto* context = static_cast<CppBackendContext*>(opaque);
    if (!context) return XSTAR_STATUS_INVALID_ARGUMENT;
    xstar_context_stats_init_v1(&context->stats);
    copy_text(message, message_size, "C++ backend persistent counters reset");
    return XSTAR_STATUS_OK;
}

int copy_scaffold_result(
    CppBackendContext& context,
    const xstar_zone_input_v1& input,
    xstar_zone_output_v1& output,
    char* message,
    std::size_t message_size
) {
    context.stats.zones_attempted += 1;
    if ((context.config.flags & XSTAR_CONFIG_ALLOW_SCAFFOLD_MODEL) == 0) {
        const std::string text =
            "v0.6.48.5.3 standalone C++ zone boundary is architecture-only; "
            "full XSTAR physics remains on the accepted hybrid runner. "
            "Set XSTAR_CONFIG_ALLOW_SCAFFOLD_MODEL only for ABI tests.";
        copy_text(message, message_size, text);
        copy_text(output.message, sizeof(output.message), text);
        return XSTAR_STATUS_NOT_IMPLEMENTED;
    }

    output.status_flags = XSTAR_ZONE_STATUS_SCAFFOLD_RESULT | XSTAR_ZONE_STATUS_CPP_BACKEND;
    output.zone_id = input.zone_id;
    output.heating = 0.0;
    output.cooling = 0.0;
    output.electron_fraction = input.electron_fraction;
    output.ion_fraction_count = std::min(input.abundance_count, output.ion_fraction_capacity);
    for (std::size_t i = 0; i < output.ion_fraction_count; ++i) {
        output.ion_fractions[i] = input.abundances[i];
    }
    output.spectrum_count = std::min(input.radiation_bin_count, output.spectrum_capacity);
    for (std::size_t i = 0; i < output.spectrum_count; ++i) {
        output.spectrum[i] = input.radiation_flux[i];
    }
    output.opacity_count = std::min(input.radiation_bin_count, output.opacity_capacity);
    for (std::size_t i = 0; i < output.opacity_count; ++i) output.opacity[i] = 0.0;
    copy_text(output.backend, sizeof(output.backend), "cpp");
    const std::string text = "C++ persistent-context scaffold result; no production physics claimed";
    copy_text(output.message, sizeof(output.message), text);
    copy_text(message, message_size, text);
    context.stats.zones_completed += 1;
    return XSTAR_STATUS_OK;
}

int cpp_run_zone(
    void* opaque,
    const xstar_zone_input_v1* input,
    xstar_zone_output_v1* output,
    char* message,
    std::size_t message_size
) {
    auto* context = static_cast<CppBackendContext*>(opaque);
    if (!context || !input || !output) return XSTAR_STATUS_INVALID_ARGUMENT;
    return copy_scaffold_result(*context, *input, *output, message, message_size);
}

int cpp_run_batch(
    void* opaque,
    const xstar_zone_input_v1* inputs,
    std::size_t count,
    xstar_zone_output_v1* outputs,
    char* message,
    std::size_t message_size
) {
    auto* context = static_cast<CppBackendContext*>(opaque);
    if (!context || (count && (!inputs || !outputs))) return XSTAR_STATUS_INVALID_ARGUMENT;
    context->stats.batch_calls += 1;
    for (std::size_t i = 0; i < count; ++i) {
        const int status = copy_scaffold_result(
            *context, inputs[i], outputs[i], message, message_size);
        if (status != XSTAR_STATUS_OK) return status;
    }
    std::ostringstream text;
    text << "C++ persistent batch completed; zones=" << count << "; scaffold=true";
    copy_text(message, message_size, text.str());
    return XSTAR_STATUS_OK;
}

int cpp_get_stats(const void* opaque, xstar_context_stats_v1* stats, char* message, std::size_t message_size) {
    const auto* context = static_cast<const CppBackendContext*>(opaque);
    if (!context || !stats) return XSTAR_STATUS_INVALID_ARGUMENT;
    *stats = context->stats;
    stats->struct_size = sizeof(*stats);
    copy_text(message, message_size, "C++ backend statistics returned");
    return XSTAR_STATUS_OK;
}

int cpp_get_component_info(
    const void* opaque,
    std::uint32_t component_id,
    xstar_component_info_v1* info,
    char* message,
    std::size_t message_size
) {
    const auto* context = static_cast<const CppBackendContext*>(opaque);
    if (!context || !info || component_id >= XSTAR_COMPONENT_COUNT) {
        return XSTAR_STATUS_INVALID_ARGUMENT;
    }
    const std::uint32_t original_size = info->struct_size;
    *info = {};
    info->struct_size = original_size;
    info->component_id = component_id;
    copy_text(info->component_name, sizeof(info->component_name),
              xstar_standalone::component_name(component_id));
    copy_text(info->requested_backend, sizeof(info->requested_backend),
              xstar_standalone::requested_component_backend(context->config, component_id));

    if (component_id == XSTAR_COMPONENT_IO) {
        info->status_flags = XSTAR_COMPONENT_IMPLEMENTATION_AVAILABLE | XSTAR_COMPONENT_PRODUCT_ACTIVE;
        copy_text(info->implementation, sizeof(info->implementation),
                  "v0.6.48.5.3 native computed-state FITS/log development IO");
        copy_text(info->message, sizeof(info->message),
                  "compiled-case API writes exact prequalified science files; dynamic FITS synthesis remains on Python fallback");
        copy_text(message, message_size, info->message);
        return XSTAR_STATUS_OK;
    }

    const ComponentLibrary* found = nullptr;
    for (const auto& component : context->components) {
        if (component.id == component_id) { found = &component; break; }
    }
    if (!found) return XSTAR_STATUS_INTERNAL_ERROR;
    info->abi_version = found->abi_version;
    info->feature_flags = found->feature_flags;
    copy_text(info->implementation, sizeof(info->implementation), found->implementation);
    copy_text(info->library_path, sizeof(info->library_path), found->path);
    if (found->loaded) {
        info->status_flags |= XSTAR_COMPONENT_LIBRARY_LOADED |
                              XSTAR_COMPONENT_IMPLEMENTATION_AVAILABLE;
        if (found->feature_flags != 0) {
            info->status_flags |= XSTAR_COMPONENT_PRODUCT_ACTIVE;
        }
        copy_text(info->message, sizeof(info->message),
                  "component library loaded; status reflects v0.6.48.5.3 product ownership");
    } else {
        copy_text(info->message, sizeof(info->message), found->error);
    }
    copy_text(message, message_size, info->message);
    return XSTAR_STATUS_OK;
}

const xstar_backend_descriptor_v1 kDescriptor{
    sizeof(xstar_backend_descriptor_v1),
    XSTAR_BACKEND_PLUGIN_ABI_VERSION,
    "cpp",
    "xstar_backend_cpp_compiled_case_v0648",
    0x0Fu,
    &cpp_create,
    &cpp_destroy,
    &cpp_reset,
    &cpp_run_zone,
    &cpp_run_batch,
    &cpp_get_stats,
    &cpp_get_component_info,
};

} // namespace

extern "C" const xstar_backend_descriptor_v1* xstar_backend_get_descriptor_v1(void) {
    return &kDescriptor;
}
