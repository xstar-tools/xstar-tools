# 0.6.88.5.4 — WINDOWS_BUILD_FAILURE_DIAGNOSTIC_CLOSURE

## Purpose

This is a qualification-only follow-up to the real Windows/UCRT64 host rejection of `0.6.88.5.3`. The known local-zone and Python path fixes in `.5.3` all passed source qualification, but the native build still returned nonzero at a later stage and the console excerpt did not expose the actionable compiler/linker failure.

## Production scope

No scientific or production C++ behavior changes are permitted. The only production/build-source differences from `0.6.88.5.3` are package-version metadata in the Makefile and XSTAR2XSPEC version literals/comments. In particular, these remain byte-identical to `.5.3`:

- `local_zone_engine.cpp`
- `xstar_backend_python.cpp`
- `xstar_process.hpp`
- `xstar_path_compat.hpp`
- all solver/rates/matrix/opacity/thermal/emissivity/engine scientific units.

## Host diagnostic contract

On the Windows host the runner records:

1. `WINDOWS_BUILD_RETURN_CODE`;
2. `WINDOWS_BUILD_LOG_PATH`;
3. captured output character/byte count;
4. compiler/linker failure-context lines with nearby context;
5. a large tail of the captured `make all PLATFORM=windows` output;
6. an evidence-only `make -j1 all PLATFORM=windows` replay without cleaning, including its return code, failure context, and complete replay output.

The serial replay never promotes the original failed parallel build. When the production build fails, dependent gates are emitted as `SKIP_BUILD_FAILED`, not `REJECT`. The direct Win32 process smoke and fake-tool compilation still run independently. The XSTAR2XSPEC process pool is explicitly skipped if the real `xstar-xspec.exe` was not built.

## Acceptance

This release is accepted locally when source/focused qualification passes and exact predecessor comparison proves no unintended production C/C++ changes. Formal Windows host closure still requires a later host run; if the build fails, `.5.4` must surface the exact diagnostic needed for the next production patch.
