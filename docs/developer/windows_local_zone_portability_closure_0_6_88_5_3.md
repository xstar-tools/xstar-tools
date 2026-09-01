# 0.6.88.5.3 — WINDOWS_LOCAL_ZONE_PORTABILITY_CLOSURE

## Status

Linux-qualified candidate; Windows UCRT64 host qualification pending.

## Production scope

This release is intentionally restricted to three production edits discovered by the real 0.6.88.5.2 Windows host run:

1. Rename the Type-85 local identifier `far` to `far_coeff`, preserving the same coefficient value, multiplication order, and call argument position.
2. Extend the existing exact Type-77 special-value branch from `__APPLE__` to `__APPLE__ || _WIN32`, keeping Linux on the historical `::exp10(rec)` branch.
3. Route the Python backend `addition` filesystem path through `XSTAR_C_PATH` before calling `PyUnicode_FromString`.

No ABI value, controller rule, traversal order, contribution order, accumulation order, cutoff, publication rule, process behavior, or output schema is changed. Windows MPI remains out of scope.

## Qualification scope

Qualification extends the direct filesystem-path `c_str()` audit to `xstar_backend_python.cpp`, requires exact predecessor normalization of the two modified production sources, preserves `xstar_process.hpp` and `xstar_path_compat.hpp` byte-for-byte, and improves synthetic `xstar-xspec` process-pool diagnostics. On a pool rejection the host runner prints each predicate, scheduler log, output tree, and each job's stdout/success-marker state.

## Formal Windows acceptance

Formal acceptance requires `WINDOWS_LOCAL_ZONE_PORTABILITY_CLOSURE_068853_HOST_RESULT=ACCEPT` on the real MSYS2/UCRT64 GitHub Actions host, including warning-free native build, PE/import/export checks, versions, sibling/plugin discovery, direct process smoke, synthetic four-job/two-process pool smoke, and `make test PLATFORM=windows`.
