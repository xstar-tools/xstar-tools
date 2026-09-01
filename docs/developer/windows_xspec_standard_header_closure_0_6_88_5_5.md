# 0.6.88.5.5 — WINDOWS_XSPEC_STANDARD_HEADER_CLOSURE

## Purpose

Close the deterministic MinGW compilation failure exposed by the real `0.6.88.5.4` Windows/UCRT64 host run. Both the authoritative parallel build and the evidence-only `-j1` replay failed at `xstar_xspec_parallel.cpp` because portable standard-library headers were inside a POSIX-only preprocessor guard.

## Root cause

Before this release, `xstar_xspec_parallel.cpp` placed `<fstream>`, `<iostream>`, `<map>`, `<sstream>`, `<stdexcept>`, `<string>`, and `<vector>` inside `#if !defined(_WIN32)`. Those headers are platform-neutral and are required by code compiled on Windows. MinGW therefore reported incomplete stream types and missing `std::cout`.

## Production scope

The only functional production-source change is the include block in `xstar_xspec_parallel.cpp`:

- move the portable C++ standard headers outside the `_WIN32` exclusion;
- keep only `<fcntl.h>`, `<signal.h>`, `<sys/types.h>`, `<sys/wait.h>`, and `<unistd.h>` under `#if !defined(_WIN32)`.

No executable statements are changed. No scientific arithmetic, controller decisions, traversal/contribution/accumulation order, cutoffs, publication semantics, output schemas, process semantics, filesystem-path adapters, or public ABI values are changed.

Normal package-version metadata changes are permitted in `pyproject.toml`, `Makefile`, `xstar_xspec_parallel.cpp`, and `xstar_xspec_mpi.cpp`.

## Preservation requirements

The predecessor comparison must prove:

- `xstar_xspec_parallel.cpp` equals the exact `.5.4` file after only the version update and the specified include-block transformation;
- `Makefile` and `xstar_xspec_mpi.cpp` are version-only changes;
- `local_zone_engine.cpp`, `xstar_backend_python.cpp`, `xstar_process.hpp`, `xstar_path_compat.hpp`, `xstar_standalone.cpp`, `xstar_science_fits.cpp`, and `xstar_step_log.cpp` are byte-identical to `.5.4`;
- Linux dry-run build commands remain equivalent after version normalization.

## Windows host acceptance

The real MSYS2/UCRT64 host run must build the full native target set, then exercise the existing PE/import-library/export/version/discovery/process-pool/regression gates. The `.5.4` parallel/serial diagnostic capture remains present so a later failure is actionable rather than hidden.

Windows MPI remains out of scope.
