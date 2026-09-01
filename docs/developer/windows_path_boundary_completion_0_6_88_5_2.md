# 0.6.88.5.2 - WINDOWS_PATH_BOUNDARY_COMPLETION

## Host findings

The 0.6.88.5.1 UCRT64 host run proved that its broad path adapter worked and that the direct CreateProcessW process smoke remained healthy, but two direct `std::filesystem::path::c_str()` calls remained in `xstar_standalone.cpp`. MinGW exposes those values as `const wchar_t*`, while the frozen XSTAR C interfaces expect `const char*`.

The same run reported two Win32-only `-Wmisleading-indentation` warnings in `xstar_process.hpp`. The synthetic XSTAR2XSPEC fake executable also built, but the pool checker read a scheduler path that production never writes.

## Closure

The two remaining C-API path arguments now use the existing `XSTAR_C_PATH(...)` boundary. `xstar_path_compat.hpp` itself is byte-identical to 0.6.88.5.1. The Win32 warning sites are split across lines with no branch or return-value change. The XSTAR2XSPEC qualification runner now reads `<output>/xstar2xspec_scheduler.log`, matching production, and emits pool stdout plus scheduler text if the gate rejects.

The source checker additionally inventories variables declared as `std::filesystem::path`/`fs::path` in `xstar_standalone.cpp` and rejects any direct `.c_str()` call on those objects, plus direct parenthesized path-join `.c_str()` expressions.

## Frozen boundaries

No scientific arithmetic, controller decision, traversal order, contribution order, accumulation order, cutoff, publication schema, C API ABI, production-zone ABI, or science revision changes are permitted. The CreateProcessW backend and Windows MPI-out-of-scope policy remain unchanged.

## Acceptance

Linux requires dry-run equivalence to 0.6.88.5.1, real build/test success, and fixed-state output hash preservation. Windows formal acceptance requires a warning-free full native build, DLL/import/export/PE/version/discovery gates, direct process smoke, synthetic four-job/two-process XSTAR2XSPEC smoke, regression, and final HOST_RESULT=ACCEPT.
