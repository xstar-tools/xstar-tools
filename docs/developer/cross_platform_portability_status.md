# Cross-platform portability status

This page summarizes the **current accepted native portability contract**. Detailed milestone investigations and historical host rejections remain in the individual `0.6.88.*` developer notes and in `CHANGELOG.md`.

## Linux ARM64 candidate

`0.6.91.1 — LINUX_ARM64_BUILD` adds an independent native build/link/loader qualification job on `ubuntu-24.04-arm`. This is **not** a change to the accepted platform table below until the actual ARM64 runner reports ACCEPT. No science-critical source or frozen ABI changes are authorized. ARM32 (`armhf`)/piwheels is out of scope. See {doc}`linux_arm64_build_0_6_91_1`.

## Current accepted release

`0.6.88.6.1.2.1 — WINDOWS_GIT_PREFLIGHT_SHELL_CLOSURE` is formally accepted across the full four-host GitHub Actions matrix.

| Host | Toolchain | Native non-MPI status |
|---|---|---|
| Linux x86_64 | GCC / GNU Make | ACCEPT |
| macOS arm64 | Apple Clang / GNU Make | ACCEPT |
| macOS x86_64 | Apple Clang / GNU Make | ACCEPT |
| Windows x86_64 | MSYS2 UCRT64 / MinGW-w64 GCC / GNU Make | ACCEPT |

Windows MPI remains intentionally out of scope. The accepted Windows concurrency path is `xstar-xspec --processes N`.

## Accepted fixed-state cross-platform contract

The portability qualification deliberately separates two properties:

1. **same-host determinism** — repeat the fixed-state calculation on the same host and require raw-byte equality;
2. **cross-platform scientific equivalence** — compare discrete state, FITS structure, and numerical payload against the canonical reference without requiring unlike architectures to emit identical floating-point bytes.

Cross-platform rules are:

- text line endings are normalized from CRLF/CR to LF for semantic comparison;
- visited-record identity/order is exact;
- non-floating step-log state is exact;
- FITS HDU/schema/row/column structure is exact;
- zero/nonzero, NaN, and infinity behavior is exact;
- every differing finite floating value must satisfy both relative difference `<= 1e-13` and ULP distance `<= 64`.

Observed accepted results:

| Host | Result |
|---|---|
| Linux x86_64 | canonical fixed-state payloads byte-exact |
| macOS x86_64 | canonical fixed-state payloads byte-exact |
| Windows UCRT64 | FITS byte-exact; text differs only by CRLF serialization and normalizes exactly |
| macOS arm64 | same-host deterministic; maximum observed relative difference `4.5635339780748665e-15`, maximum `39 ULP` |

## Portability boundaries

Cross-platform behavior is intentionally concentrated in infrastructure layers:

- Makefile platform variables own library/executable extensions and linker policy;
- the dynamic-library wrapper owns `dlopen`/`dlsym` vs. Win32 library loading;
- `xstar_process.hpp` owns POSIX process/environment calls vs. `CreateProcessW` and Win32 wait/termination;
- `xstar_path_compat.hpp` adapts Windows `std::filesystem::path` objects at existing narrow CFITSIO/XSTAR C interfaces;
- Windows embedded Python registers the UCRT64 DLL directory through the qualified `sys.base_prefix` path.

The scientific kernels, controller/traversal order, publication semantics, output schema, and public ABI values remain outside these portability adaptations.

## Historical portability sequence

The accepted path through the `0.6.88` series was:

- `0.6.88.1` — platform build abstraction;
- `0.6.88.2` / `.2.1` / `.2.2` — portable dynamic-library layer and fixed-state regression scaffold closure;
- `0.6.88.3` / `.3.1` / `.3.2` — macOS compile/link closure;
- `0.6.88.4` / `.4.1` / `.4.2` — portable process layer and Apple-Clang warning cleanup;
- `0.6.88.5` through `.5.7` — Windows UCRT64 build, path, local-zone, XSTAR2XSPEC, embedded-Python, and warning-free closure;
- `0.6.88.6` — first four-host unified qualification; historically rejected by an over-strict cross-host raw-hash rule;
- `0.6.88.6.1` — fixed-state equivalence contract; historically rejected only by hard-coded workflow lookup;
- `0.6.88.6.1.1` — workflow discovery closure; Windows then exposed CRLF conversion of checked-in text fixtures;
- `0.6.88.6.1.2` — reference-payload line-ending closure; Windows workflow stopped before the host runner because `git` was not visible inside the MSYS2 preflight shell;
- `0.6.88.6.1.2.1` — native-PowerShell Git preflight closure; all four hosts accepted.

Historical `REJECT` labels are intentionally preserved. Later closures do not rewrite the result of an earlier real host run.

## Build policy

The normal build is non-MPI:

```bash
make -C src/xstar_tools/xstar/cpp -j4
```

True MPI is explicit:

```bash
make -C src/xstar_tools/xstar/cpp mpi
```

The accepted MPI implementation is a Linux/macOS/HPC path. Windows MPI is not planned; Windows native support remains the standalone/local-process MinGW path, while production HPC deployment uses POSIX platforms.
