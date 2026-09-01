// 0.6.88.5.1 WINDOWS_PATH_ENCODING_CLOSURE
// Narrow C-API path adapter. On Linux/macOS this expands to the historical
// std::filesystem::path::c_str() expression. On Windows MinGW, path::value_type
// is wchar_t, so materialize a narrow path string for APIs that accept char*.
#ifndef XSTAR_PATH_COMPAT_HPP
#define XSTAR_PATH_COMPAT_HPP
#include <filesystem>
#if defined(_WIN32)
#define XSTAR_C_PATH(expr) ((expr).string().c_str())
#else
#define XSTAR_C_PATH(expr) ((expr).c_str())
#endif
#endif
