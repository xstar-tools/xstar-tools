#include "xstar_backend_plugin.h"
#include "xstar_python_bridge.h"
#include "xstar_standalone_internal.hpp"

#include <Python.h>
#include <algorithm>
#include <array>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <memory>
#include <sstream>
#include <string>
#include <vector>

namespace {

using xstar_standalone::copy_text;

struct PythonBackendContext {
    xstar_config_v1 config{};
    PyObject* module = nullptr;
    PyObject* context = nullptr;
};

std::string python_error_text() {
    if (!PyErr_Occurred()) return "unknown Python error";
    PyObject *type = nullptr, *value = nullptr, *traceback = nullptr;
    PyErr_Fetch(&type, &value, &traceback);
    PyErr_NormalizeException(&type, &value, &traceback);
    std::string result = "Python error";
    if (value) {
        PyObject* text = PyObject_Str(value);
        if (text) {
            const char* utf8 = PyUnicode_AsUTF8(text);
            if (utf8) result = utf8;
            Py_DECREF(text);
        }
    }
    Py_XDECREF(type);
    Py_XDECREF(value);
    Py_XDECREF(traceback);
    return result;
}

bool ensure_python(const xstar_config_v1* config, std::string& error) {
    if (!Py_IsInitialized()) {
        if (config && config->python_home[0] != '\0') {
            error = "python_home is reserved in v0.6.44.2; use PYTHONHOME before process start";
            return false;
        }
        Py_Initialize();
    }
    if (!Py_IsInitialized()) {
        error = "Py_Initialize failed";
        return false;
    }
    PyGILState_STATE gil = PyGILState_Ensure();
    PyObject* path = PySys_GetObject("path");
    if (!path) {
        error = "could not access sys.path";
        PyGILState_Release(gil);
        return false;
    }
    std::vector<std::filesystem::path> additions;
    if (config && config->python_path[0] != '\0') additions.emplace_back(config->python_path);
    const auto cpp_dir = xstar_standalone::executable_or_library_directory(
        reinterpret_cast<const void*>(&xstar_backend_get_descriptor_v1));
    additions.push_back(cpp_dir.parent_path().parent_path().parent_path());
    for (const auto& addition : additions) {
        if (addition.empty()) continue;
        PyObject* text = PyUnicode_FromString(addition.c_str());
        if (!text) {
            error = python_error_text();
            PyGILState_Release(gil);
            return false;
        }
        if (PySequence_Contains(path, text) == 0) PyList_Insert(path, 0, text);
        Py_DECREF(text);
    }
    PyGILState_Release(gil);
    return true;
}

PyObject* config_dict(const xstar_config_v1& config) {
    PyObject* result = PyDict_New();
    if (!result) return nullptr;
    auto set_text = [&](const char* key, const char* value) {
        PyObject* object = PyUnicode_FromString(value ? value : "");
        if (!object || PyDict_SetItemString(result, key, object) != 0) {
            Py_XDECREF(object);
            return false;
        }
        Py_DECREF(object);
        return true;
    };
    auto set_long = [&](const char* key, unsigned long value) {
        PyObject* object = PyLong_FromUnsignedLong(value);
        if (!object || PyDict_SetItemString(result, key, object) != 0) {
            Py_XDECREF(object);
            return false;
        }
        Py_DECREF(object);
        return true;
    };
    if (!set_text("backend", config.backend) ||
        !set_text("atomic_database_path", config.atomic_database_path) ||
        !set_text("cache_directory", config.cache_directory) ||
        !set_long("flags", config.flags) ||
        !set_long("thread_count", config.thread_count)) {
        Py_DECREF(result);
        return nullptr;
    }
    return result;
}

PyObject* double_list(const double* values, std::size_t count) {
    PyObject* list = PyList_New(static_cast<Py_ssize_t>(count));
    if (!list) return nullptr;
    for (std::size_t i = 0; i < count; ++i) {
        PyObject* value = PyFloat_FromDouble(values[i]);
        if (!value) { Py_DECREF(list); return nullptr; }
        PyList_SET_ITEM(list, static_cast<Py_ssize_t>(i), value);
    }
    return list;
}

PyObject* zone_dict(const xstar_zone_input_v1& input) {
    PyObject* result = PyDict_New();
    if (!result) return nullptr;
    auto set_object = [&](const char* key, PyObject* value) {
        if (!value) return false;
        const int status = PyDict_SetItemString(result, key, value);
        Py_DECREF(value);
        return status == 0;
    };
    if (!set_object("zone_id", PyLong_FromUnsignedLongLong(input.zone_id)) ||
        !set_object("temperature", PyFloat_FromDouble(input.temperature)) ||
        !set_object("electron_density", PyFloat_FromDouble(input.electron_density)) ||
        !set_object("hydrogen_density", PyFloat_FromDouble(input.hydrogen_density)) ||
        !set_object("electron_fraction", PyFloat_FromDouble(input.electron_fraction)) ||
        !set_object("ionization_parameter", PyFloat_FromDouble(input.ionization_parameter)) ||
        !set_object("column_density", PyFloat_FromDouble(input.column_density)) ||
        !set_object("abundances", double_list(input.abundances, input.abundance_count)) ||
        !set_object("radiation_energy", double_list(input.radiation_energy, input.radiation_bin_count)) ||
        !set_object("radiation_flux", double_list(input.radiation_flux, input.radiation_bin_count))) {
        Py_DECREF(result);
        return nullptr;
    }
    return result;
}

bool dict_double(PyObject* dict, const char* key, double& output) {
    PyObject* value = PyDict_GetItemString(dict, key);
    if (!value) return false;
    output = PyFloat_AsDouble(value);
    return !PyErr_Occurred();
}

bool dict_u64(PyObject* dict, const char* key, std::uint64_t& output) {
    PyObject* value = PyDict_GetItemString(dict, key);
    if (!value) return false;
    output = PyLong_AsUnsignedLongLong(value);
    return !PyErr_Occurred();
}

bool dict_u32(PyObject* dict, const char* key, std::uint32_t& output) {
    std::uint64_t temp = 0;
    if (!dict_u64(dict, key, temp)) return false;
    output = static_cast<std::uint32_t>(temp);
    return true;
}

bool copy_sequence(PyObject* dict, const char* key, double* destination,
                   std::size_t capacity, std::size_t& count) {
    PyObject* value = PyDict_GetItemString(dict, key);
    if (!value) return false;
    PyObject* sequence = PySequence_Fast(value, "expected sequence");
    if (!sequence) return false;
    const std::size_t available = static_cast<std::size_t>(PySequence_Fast_GET_SIZE(sequence));
    count = std::min(available, capacity);
    PyObject** items = PySequence_Fast_ITEMS(sequence);
    for (std::size_t i = 0; i < count; ++i) {
        destination[i] = PyFloat_AsDouble(items[i]);
        if (PyErr_Occurred()) { Py_DECREF(sequence); return false; }
    }
    Py_DECREF(sequence);
    return true;
}

bool copy_dict_text(PyObject* dict, const char* key, char* destination, std::size_t capacity) {
    PyObject* value = PyDict_GetItemString(dict, key);
    if (!value) return false;
    const char* text = PyUnicode_AsUTF8(value);
    if (!text) return false;
    copy_text(destination, capacity, text);
    return true;
}

int python_create(const xstar_config_v1* config, void** output, char* message, std::size_t message_size) {
    if (!config || !output) return XSTAR_STATUS_INVALID_ARGUMENT;
    std::string error;
    if (!ensure_python(config, error)) {
        copy_text(message, message_size, error);
        return XSTAR_STATUS_BACKEND_LOAD_FAILED;
    }
    PyGILState_STATE gil = PyGILState_Ensure();
    auto context = std::make_unique<PythonBackendContext>();
    context->config = *config;
    context->module = PyImport_ImportModule("xstar_tools.xstar.standalone_backend");
    if (!context->module) {
        error = python_error_text();
        copy_text(message, message_size, error);
        PyGILState_Release(gil);
        return XSTAR_STATUS_BACKEND_LOAD_FAILED;
    }
    PyObject* create = PyObject_GetAttrString(context->module, "create_context");
    PyObject* config_object = config_dict(*config);
    if (!create || !config_object) {
        Py_XDECREF(create);
        Py_XDECREF(config_object);
        error = python_error_text();
        copy_text(message, message_size, error);
        PyGILState_Release(gil);
        return XSTAR_STATUS_BACKEND_ERROR;
    }
    context->context = PyObject_CallOneArg(create, config_object);
    Py_DECREF(create);
    Py_DECREF(config_object);
    if (!context->context) {
        error = python_error_text();
        copy_text(message, message_size, error);
        PyGILState_Release(gil);
        return XSTAR_STATUS_BACKEND_ERROR;
    }
    copy_text(message, message_size,
              "embedded Python backend created; persistent_context=true; physics_boundary=scaffold");
    *output = context.release();
    PyGILState_Release(gil);
    return XSTAR_STATUS_OK;
}

void python_destroy(void* opaque) {
    auto* context = static_cast<PythonBackendContext*>(opaque);
    if (!context) return;
    PyGILState_STATE gil = PyGILState_Ensure();
    Py_XDECREF(context->context);
    Py_XDECREF(context->module);
    PyGILState_Release(gil);
    delete context;
}

int python_reset(void* opaque, char* message, std::size_t message_size) {
    auto* context = static_cast<PythonBackendContext*>(opaque);
    if (!context) return XSTAR_STATUS_INVALID_ARGUMENT;
    PyGILState_STATE gil = PyGILState_Ensure();
    PyObject* callable = PyObject_GetAttrString(context->module, "reset_context");
    PyObject* result = callable ? PyObject_CallOneArg(callable, context->context) : nullptr;
    Py_XDECREF(callable);
    if (!result) {
        const std::string error = python_error_text();
        copy_text(message, message_size, error);
        PyGILState_Release(gil);
        return XSTAR_STATUS_BACKEND_ERROR;
    }
    Py_DECREF(result);
    copy_text(message, message_size, "Python backend persistent counters reset");
    PyGILState_Release(gil);
    return XSTAR_STATUS_OK;
}

int python_run_zone(void* opaque, const xstar_zone_input_v1* input,
                    xstar_zone_output_v1* output, char* message, std::size_t message_size) {
    auto* context = static_cast<PythonBackendContext*>(opaque);
    if (!context || !input || !output) return XSTAR_STATUS_INVALID_ARGUMENT;
    PyGILState_STATE gil = PyGILState_Ensure();
    PyObject* callable = PyObject_GetAttrString(context->module, "run_zone");
    PyObject* zone = zone_dict(*input);
    PyObject* args = PyTuple_Pack(2, context->context, zone ? zone : Py_None);
    PyObject* kwargs = PyDict_New();
    PyObject* allow = PyBool_FromLong(
        (context->config.flags & XSTAR_CONFIG_ALLOW_SCAFFOLD_MODEL) != 0);
    if (kwargs && allow) PyDict_SetItemString(kwargs, "allow_scaffold", allow);
    Py_XDECREF(allow);
    PyObject* result = (callable && zone && args && kwargs)
        ? PyObject_Call(callable, args, kwargs) : nullptr;
    Py_XDECREF(callable);
    Py_XDECREF(zone);
    Py_XDECREF(args);
    Py_XDECREF(kwargs);
    if (!result) {
        const bool not_implemented = PyErr_ExceptionMatches(PyExc_NotImplementedError);
        const std::string error = python_error_text();
        copy_text(message, message_size, error);
        copy_text(output->message, sizeof(output->message), error);
        PyGILState_Release(gil);
        return not_implemented ? XSTAR_STATUS_NOT_IMPLEMENTED : XSTAR_STATUS_BACKEND_ERROR;
    }
    bool ok = PyDict_Check(result) &&
              dict_u64(result, "zone_id", output->zone_id) &&
              dict_u32(result, "status_flags", output->status_flags) &&
              dict_double(result, "heating", output->heating) &&
              dict_double(result, "cooling", output->cooling) &&
              dict_double(result, "electron_fraction", output->electron_fraction) &&
              copy_sequence(result, "ion_fractions", output->ion_fractions,
                            output->ion_fraction_capacity, output->ion_fraction_count) &&
              copy_sequence(result, "spectrum", output->spectrum,
                            output->spectrum_capacity, output->spectrum_count) &&
              copy_sequence(result, "opacity", output->opacity,
                            output->opacity_capacity, output->opacity_count) &&
              copy_dict_text(result, "backend", output->backend, sizeof(output->backend)) &&
              copy_dict_text(result, "message", output->message, sizeof(output->message));
    Py_DECREF(result);
    if (!ok) {
        const std::string error = python_error_text();
        copy_text(message, message_size, error);
        PyGILState_Release(gil);
        return XSTAR_STATUS_BACKEND_ERROR;
    }
    copy_text(message, message_size, output->message);
    PyGILState_Release(gil);
    return XSTAR_STATUS_OK;
}

int python_run_batch(void* opaque, const xstar_zone_input_v1* inputs, std::size_t count,
                     xstar_zone_output_v1* outputs, char* message, std::size_t message_size) {
    auto* context = static_cast<PythonBackendContext*>(opaque);
    if (!context || (count && (!inputs || !outputs))) return XSTAR_STATUS_INVALID_ARGUMENT;
    /* Keep ABI behavior simple and deterministic in v0.6.44.2. The persistent
       Python context is reused; later releases can vectorize this call. */
    for (std::size_t i = 0; i < count; ++i) {
        const int status = python_run_zone(context, inputs + i, outputs + i, message, message_size);
        if (status != XSTAR_STATUS_OK) return status;
    }
    PyGILState_STATE gil = PyGILState_Ensure();
    PyObject* stats = PyObject_GetAttrString(context->context, "batch_calls");
    if (stats) {
        const unsigned long current = PyLong_AsUnsignedLong(stats);
        Py_DECREF(stats);
        if (!PyErr_Occurred()) {
            PyObject* next = PyLong_FromUnsignedLong(current + 1);
            if (next) {
                PyObject_SetAttrString(context->context, "batch_calls", next);
                Py_DECREF(next);
            }
        } else {
            PyErr_Clear();
        }
    }
    PyGILState_Release(gil);
    std::ostringstream text;
    text << "Python persistent batch completed; zones=" << count << "; scaffold=true";
    copy_text(message, message_size, text.str());
    return XSTAR_STATUS_OK;
}

int python_get_stats(const void* opaque, xstar_context_stats_v1* stats,
                     char* message, std::size_t message_size) {
    const auto* context = static_cast<const PythonBackendContext*>(opaque);
    if (!context || !stats) return XSTAR_STATUS_INVALID_ARGUMENT;
    PyGILState_STATE gil = PyGILState_Ensure();
    PyObject* callable = PyObject_GetAttrString(context->module, "context_stats");
    PyObject* result = callable ? PyObject_CallOneArg(callable, context->context) : nullptr;
    Py_XDECREF(callable);
    if (!result) {
        const std::string error = python_error_text();
        copy_text(message, message_size, error);
        PyGILState_Release(gil);
        return XSTAR_STATUS_BACKEND_ERROR;
    }
    std::uint64_t value = 0;
    bool ok = dict_u64(result, "zones_attempted", value);
    stats->zones_attempted = value;
    ok = ok && dict_u64(result, "zones_completed", stats->zones_completed);
    ok = ok && dict_u64(result, "batch_calls", stats->batch_calls);
    ok = ok && dict_u64(result, "fallback_count", stats->fallback_count);
    stats->struct_size = sizeof(*stats);
    Py_DECREF(result);
    if (!ok) {
        const std::string error = python_error_text();
        copy_text(message, message_size, error);
        PyGILState_Release(gil);
        return XSTAR_STATUS_BACKEND_ERROR;
    }
    copy_text(message, message_size, "Python backend statistics returned");
    PyGILState_Release(gil);
    return XSTAR_STATUS_OK;
}

int python_get_component_info(const void* opaque, std::uint32_t component_id,
                              xstar_component_info_v1* info,
                              char* message, std::size_t message_size) {
    const auto* context = static_cast<const PythonBackendContext*>(opaque);
    if (!context || !info || component_id >= XSTAR_COMPONENT_COUNT) {
        return XSTAR_STATUS_INVALID_ARGUMENT;
    }
    const std::uint32_t original_size = info->struct_size;
    *info = {};
    info->struct_size = original_size;
    info->component_id = component_id;
    info->abi_version = XSTAR_API_ABI_VERSION;
    info->status_flags = XSTAR_COMPONENT_IMPLEMENTATION_AVAILABLE |
                         XSTAR_COMPONENT_PYTHON_MODULE_AVAILABLE;
    copy_text(info->component_name, sizeof(info->component_name),
              xstar_standalone::component_name(component_id));
    copy_text(info->requested_backend, sizeof(info->requested_backend),
              xstar_standalone::requested_component_backend(context->config, component_id));
    copy_text(info->implementation, sizeof(info->implementation),
              "xstar_tools.xstar Python reference module family");
    copy_text(info->library_path, sizeof(info->library_path),
              "libxstar_backend_python.so -> embedded CPython");
    copy_text(info->message, sizeof(info->message),
              "Python modules are available; full typed standalone zone mapping is pending");
    copy_text(message, message_size, info->message);
    return XSTAR_STATUS_OK;
}

const xstar_backend_descriptor_v1 kDescriptor{
    sizeof(xstar_backend_descriptor_v1),
    XSTAR_BACKEND_PLUGIN_ABI_VERSION,
    "python",
    "xstar_backend_python_embedded_cpython_v0644",
    0x0Fu,
    &python_create,
    &python_destroy,
    &python_reset,
    &python_run_zone,
    &python_run_batch,
    &python_get_stats,
    &python_get_component_info,
};

} // namespace

extern "C" const xstar_backend_descriptor_v1* xstar_backend_get_descriptor_v1(void) {
    return &kDescriptor;
}

extern "C" std::uint32_t xstar_python_bridge_abi_version(void) {
    return XSTAR_PYTHON_BRIDGE_ABI_VERSION;
}

extern "C" int xstar_python_call_json_v1(
    const char* module_name,
    const char* callable_name,
    const char* request_json,
    char* response,
    std::size_t* response_size,
    char* error_message,
    std::size_t error_message_size
) {
    if (!module_name || !callable_name || !request_json || !response_size) {
        return XSTAR_STATUS_INVALID_ARGUMENT;
    }
    xstar_config_v1 config{};
    xstar_config_init_v1(&config);
    std::string error;
    if (!ensure_python(&config, error)) {
        copy_text(error_message, error_message_size, error);
        return XSTAR_STATUS_BACKEND_LOAD_FAILED;
    }
    PyGILState_STATE gil = PyGILState_Ensure();
    PyObject* json = PyImport_ImportModule("json");
    PyObject* loads = json ? PyObject_GetAttrString(json, "loads") : nullptr;
    PyObject* dumps = json ? PyObject_GetAttrString(json, "dumps") : nullptr;
    PyObject* request_text = PyUnicode_FromString(request_json);
    PyObject* request = (loads && request_text) ? PyObject_CallOneArg(loads, request_text) : nullptr;
    PyObject* module = request ? PyImport_ImportModule(module_name) : nullptr;
    PyObject* callable = module ? PyObject_GetAttrString(module, callable_name) : nullptr;
    PyObject* result = (callable && PyCallable_Check(callable)) ? PyObject_CallOneArg(callable, request) : nullptr;
    PyObject* result_text = (result && dumps) ? PyObject_CallOneArg(dumps, result) : nullptr;
    const char* utf8 = result_text ? PyUnicode_AsUTF8(result_text) : nullptr;
    int status = XSTAR_STATUS_OK;
    if (!utf8) {
        error = python_error_text();
        copy_text(error_message, error_message_size, error);
        status = XSTAR_STATUS_BACKEND_ERROR;
    } else {
        const std::size_t required = std::strlen(utf8) + 1;
        if (!response || *response_size < required) {
            *response_size = required;
            status = XSTAR_STATUS_BUFFER_TOO_SMALL;
        } else {
            std::memcpy(response, utf8, required);
            *response_size = required;
            copy_text(error_message, error_message_size, "ok");
        }
    }
    Py_XDECREF(result_text);
    Py_XDECREF(result);
    Py_XDECREF(callable);
    Py_XDECREF(module);
    Py_XDECREF(request);
    Py_XDECREF(request_text);
    Py_XDECREF(dumps);
    Py_XDECREF(loads);
    Py_XDECREF(json);
    PyGILState_Release(gil);
    return status;
}
