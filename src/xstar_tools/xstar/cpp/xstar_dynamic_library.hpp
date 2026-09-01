// XSTAR-SOURCE-CORRESPONDENCE-BEGIN
// Fortran: No direct Fortran routine.
// Role: Portable dynamic-library loading and module-location abstraction.
// Relation: Infrastructure only; no scientific operation.
// Concordance: BACKEND-001; ARCH-001
// Qualification: 0.6.88.2 PORTABLE_DYNAMIC_LIBRARY_LAYER
// XSTAR-SOURCE-CORRESPONDENCE-END

#ifndef XSTAR_DYNAMIC_LIBRARY_HPP
#define XSTAR_DYNAMIC_LIBRARY_HPP

#include <filesystem>
#include <string>

namespace xstar_platform {

#if !defined(_WIN32) && (defined(__GNUC__) || defined(__clang__))
#define XSTAR_PLATFORM_INTERNAL __attribute__((visibility("hidden")))
#else
#define XSTAR_PLATFORM_INTERNAL
#endif

using DynamicLibraryHandle = void*;

enum class DynamicLibraryVisibility {
    local,
    global,
};

XSTAR_PLATFORM_INTERNAL DynamicLibraryHandle dynamic_library_open(
    const std::filesystem::path& path,
    DynamicLibraryVisibility visibility);

XSTAR_PLATFORM_INTERNAL void* dynamic_library_symbol(
    DynamicLibraryHandle handle,
    const char* symbol_name);

XSTAR_PLATFORM_INTERNAL void dynamic_library_close(DynamicLibraryHandle handle) noexcept;

XSTAR_PLATFORM_INTERNAL const std::string& dynamic_library_error() noexcept;

XSTAR_PLATFORM_INTERNAL std::filesystem::path module_directory(const void* symbol_address);

} // namespace xstar_platform

#undef XSTAR_PLATFORM_INTERNAL

#endif
