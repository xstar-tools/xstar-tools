# Native build

The accepted native build continues to use the retained GNU Make build rather than translating the scientific tree to a new build system.

## Platform matrix

| Platform | Toolchain | Non-MPI native status |
|---|---|---|
| Linux x86_64 | GCC / GNU Make | ACCEPT |
| macOS arm64 | Apple Clang / GNU Make | ACCEPT |
| macOS x86_64 | Apple Clang / GNU Make | ACCEPT |
| Windows x86_64 | MSYS2 UCRT64 / MinGW-w64 GCC / GNU Make | ACCEPT |

Current accepted portability closure: `0.6.88.6.1.2.1`.

## Source checkout build

Normal non-MPI build:

```bash
make -C src/xstar_tools/xstar/cpp -j4
```

Inspect resolved platform values:

```bash
make -C src/xstar_tools/xstar/cpp print-config
```

Important build-abstraction variables include:

```text
PLATFORM
SHLIB_EXT
EXEEXT
SHLIB_LDFLAGS
PIC_FLAGS
DL_LIBS
THREAD_LIBS
RPATH_ORIGIN
FILESYSTEM_LIBS
```

### Linux

```bash
make -C src/xstar_tools/xstar/cpp -j4 PLATFORM=linux
```

Requirements include a C++17 compiler, CFITSIO development files, `pkg-config`, and Python development support for the embedded Python backend.

### macOS

```bash
brew install cfitsio pkg-config
make -C src/xstar_tools/xstar/cpp -j4 PLATFORM=macos
```

The accepted build uses `.dylib`, `@rpath`, and `@loader_path` conventions.

### Windows

From an MSYS2 UCRT64 terminal:

```bash
make -C src/xstar_tools/xstar/cpp -j4 PLATFORM=windows
```

Windows builds `.dll`, `.dll.a`, and `.exe` artifacts and uses the qualified Win32 process backend. See {doc}`../user/windows_installation_and_usage` for packages and examples.

Windows MPI is intentionally out of scope.

## Optional MPI build

`xstar-xspec-mpi` is opt-in and not part of `all`:

```bash
make -C src/xstar_tools/xstar/cpp mpi
```

or:

```bash
make -C src/xstar_tools/xstar/cpp xstar-xspec-mpi
```

Override the compiler wrapper when needed:

```bash
make -C src/xstar_tools/xstar/cpp mpi MPICXX=/path/to/mpic++
```

The accepted production use case is Linux/HPC. A shared filesystem is required by the current file-backed MPI implementation.

## Python/wheel build controls

The Python packaging hook can request native compilation without changing the qualified Makefile/compiler policy:

```text
XSTAR_TOOLS_NATIVE=auto|required|off
XSTAR_TOOLS_NATIVE_JOBS=N
```

`required` converts missing native prerequisites into a build failure; `off` creates a Python-only installation. Packaging policy and direct source-build portability are deliberately treated as separate contracts.
