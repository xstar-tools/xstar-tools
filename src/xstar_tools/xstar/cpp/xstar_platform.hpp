// XSTAR-SOURCE-CORRESPONDENCE-BEGIN
// Fortran: No direct Fortran routine.
// Role: Cross-platform native build/runtime naming conventions.
// Relation: Infrastructure only; no scientific operation.
// Concordance: BACKEND-001; ARCH-001
// Qualification: 0.6.88.2 PORTABLE_DYNAMIC_LIBRARY_LAYER
// XSTAR-SOURCE-CORRESPONDENCE-END

#ifndef XSTAR_PLATFORM_HPP
#define XSTAR_PLATFORM_HPP

#include <string>

namespace xstar_platform {

#if defined(_WIN32)
inline constexpr const char* kSharedLibraryPrefix = "lib";
inline constexpr const char* kSharedLibraryExtension = ".dll";
inline constexpr char kPathListSeparator = ';';
#elif defined(__APPLE__)
inline constexpr const char* kSharedLibraryPrefix = "lib";
inline constexpr const char* kSharedLibraryExtension = ".dylib";
inline constexpr char kPathListSeparator = ':';
#else
inline constexpr const char* kSharedLibraryPrefix = "lib";
inline constexpr const char* kSharedLibraryExtension = ".so";
inline constexpr char kPathListSeparator = ':';
#endif

inline std::string shared_library_filename(const std::string& stem) {
    return std::string(kSharedLibraryPrefix) + stem + kSharedLibraryExtension;
}

inline std::string executable_filename(const std::string& stem) {
#if defined(_WIN32)
    return stem + ".exe";
#else
    return stem;
#endif
}

inline constexpr char path_list_separator() noexcept {
    return kPathListSeparator;
}

} // namespace xstar_platform

#endif
