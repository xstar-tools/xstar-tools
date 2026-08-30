// XSTAR-SOURCE-CORRESPONDENCE-BEGIN
// Fortran: No direct Fortran routine.
// Role: Portable dynamic-library loading and module-location implementation.
// Relation: Infrastructure only; no scientific operation.
// Concordance: BACKEND-001; ARCH-001
// Qualification: 0.6.88.2 PORTABLE_DYNAMIC_LIBRARY_LAYER
// XSTAR-SOURCE-CORRESPONDENCE-END

#include "xstar_dynamic_library.hpp"

#include <filesystem>
#include <string>

#if defined(_WIN32)
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <vector>
#else
#include <dlfcn.h>
#endif

namespace xstar_platform {
namespace {

thread_local std::string g_dynamic_library_error;

#if defined(_WIN32)
std::string windows_error_message(DWORD code) {
    if (code == 0) return {};
    LPSTR buffer = nullptr;
    const DWORD flags = FORMAT_MESSAGE_ALLOCATE_BUFFER |
                        FORMAT_MESSAGE_FROM_SYSTEM |
                        FORMAT_MESSAGE_IGNORE_INSERTS;
    const DWORD size = FormatMessageA(
        flags, nullptr, code, 0,
        reinterpret_cast<LPSTR>(&buffer), 0, nullptr);
    std::string result;
    if (size != 0 && buffer != nullptr) {
        result.assign(buffer, size);
        while (!result.empty() &&
               (result.back() == '\r' || result.back() == '\n' || result.back() == ' ')) {
            result.pop_back();
        }
    } else {
        result = "Windows error " + std::to_string(static_cast<unsigned long>(code));
    }
    if (buffer != nullptr) LocalFree(buffer);
    return result;
}
#endif

} // namespace

DynamicLibraryHandle dynamic_library_open(
    const std::filesystem::path& path,
    DynamicLibraryVisibility visibility) {
    g_dynamic_library_error.clear();
#if defined(_WIN32)
    (void)visibility;
    HMODULE module = LoadLibraryW(path.wstring().c_str());
    if (module == nullptr) {
        g_dynamic_library_error = windows_error_message(GetLastError());
        return nullptr;
    }
    return reinterpret_cast<DynamicLibraryHandle>(module);
#else
    const int flags = RTLD_NOW |
        (visibility == DynamicLibraryVisibility::global ? RTLD_GLOBAL : RTLD_LOCAL);
    dlerror();
    void* handle = dlopen(path.c_str(), flags);
    if (handle == nullptr) {
        const char* error = dlerror();
        g_dynamic_library_error = error ? error : "dlopen failed";
    }
    return handle;
#endif
}

void* dynamic_library_symbol(
    DynamicLibraryHandle handle,
    const char* symbol_name) {
    g_dynamic_library_error.clear();
    if (handle == nullptr || symbol_name == nullptr) {
        g_dynamic_library_error = "invalid dynamic-library handle or symbol name";
        return nullptr;
    }
#if defined(_WIN32)
    FARPROC symbol = GetProcAddress(
        reinterpret_cast<HMODULE>(handle), symbol_name);
    if (symbol == nullptr) {
        g_dynamic_library_error = windows_error_message(GetLastError());
        return nullptr;
    }
    return reinterpret_cast<void*>(symbol);
#else
    dlerror();
    void* symbol = dlsym(handle, symbol_name);
    const char* error = dlerror();
    if (error != nullptr) {
        g_dynamic_library_error = error;
        return nullptr;
    }
    return symbol;
#endif
}

void dynamic_library_close(DynamicLibraryHandle handle) noexcept {
    if (handle == nullptr) return;
#if defined(_WIN32)
    FreeLibrary(reinterpret_cast<HMODULE>(handle));
#else
    dlclose(handle);
#endif
}

const std::string& dynamic_library_error() noexcept {
    return g_dynamic_library_error;
}

std::filesystem::path module_directory(const void* symbol_address) {
#if defined(_WIN32)
    if (symbol_address != nullptr) {
        HMODULE module = nullptr;
        const DWORD flags = GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
                            GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT;
        if (GetModuleHandleExW(
                flags,
                reinterpret_cast<LPCWSTR>(symbol_address),
                &module) != 0 &&
            module != nullptr) {
            std::vector<wchar_t> buffer(32768, L'\0');
            const DWORD length = GetModuleFileNameW(
                module, buffer.data(), static_cast<DWORD>(buffer.size()));
            if (length > 0 && length < buffer.size()) {
                std::filesystem::path path(
                    std::wstring(buffer.data(), static_cast<std::size_t>(length)));
                std::error_code error;
                auto normalized = std::filesystem::weakly_canonical(path, error);
                return (error ? path : normalized).parent_path();
            }
        }
    }
#else
    if (symbol_address != nullptr) {
        Dl_info info{};
        if (dladdr(symbol_address, &info) != 0 && info.dli_fname != nullptr) {
            std::filesystem::path path(info.dli_fname);
            std::error_code error;
            auto normalized = std::filesystem::weakly_canonical(path, error);
            return (error ? path : normalized).parent_path();
        }
    }
#endif
    return std::filesystem::current_path();
}

} // namespace xstar_platform
