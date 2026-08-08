# C++ Namespace Cleanup

Version 0.6.57 separates retired C++ parity/performance sources from the active native build.

## Archived sources

- `opacity_type50_experiments.cpp`: retired 12.3.26/12.3.27 Type50 performance experiments. The active `Makefile` does not compile it; current compatibility telemetry is implemented as zero ABI stubs in `opacity_kernels.cpp`.
- `xstar_backend_common.cpp`: unused scaffold translation unit. Its exported ABI/name/feature functions had no callers and it was not compiled. Production helpers remain header-only in `xstar_backend_common.hpp`.
- `Makefile.before_v67`: superseded build snapshot, retained only under `historical/cpp/build/`.

## Headers

No current `.h` or `.hpp` file was archived. The coheat/Type50/Type53 oracle headers are still consumed by `fixed_state_engine.cpp`; public API headers remain intentional product interfaces.

## Rule

Active source, tests, tools, and the native `Makefile` must not depend on files under `historical/cpp/`. The 0.6.57 cleanup gate enforces that split while preserving archived bytes and frozen science hashes as provenance.
