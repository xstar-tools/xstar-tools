# 0.6.88.5.1 — WINDOWS_PATH_ENCODING_CLOSURE

## Host finding

The first real UCRT64/MinGW run of 0.6.88.5 rejected the full build because `std::filesystem::path::c_str()` is `const wchar_t*` on Windows while CFITSIO and the frozen XSTAR C interfaces use narrow `const char*` paths. The direct Win32 process/environment smoke passed, so this closure does not redesign process creation.

## Fix

`xstar_path_compat.hpp` defines `XSTAR_C_PATH(expr)`. On Windows it materializes `expr.string().c_str()` for the duration of the C call. On Linux/macOS it expands to the pre-existing `expr.c_str()` expression. The affected sites are limited to filesystem-path arguments passed into narrow C APIs in `xstar_standalone.cpp`, `xstar_science_fits.cpp`, and `xstar_step_log.cpp`.

This is an encoding/type portability closure, not a scientific change. For current GitHub Actions paths (ASCII MSYS2/UCRT64 workspace and generated XSTAR filenames), the narrow representation preserves the exact path spelling expected by CFITSIO and the existing XSTAR C ABI.

## Acceptance

Linux must retain build/test/fixed-state output equivalence. Windows must complete the full DLL/executable build, PE/import/export checks, versions, sibling/plugin discovery, direct process smoke, synthetic xstar-xspec two-process smoke, and regression.
