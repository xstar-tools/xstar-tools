# Native build

Build the native targets from a source checkout:

```bash
make -C src/xstar_tools/xstar/cpp -j2
```

Primary products include the shared libraries used by Python/shared production modes and the `xstar-cpp` executable.

Requirements:

- a C++17 compiler;
- CFITSIO development headers/libraries;
- a standard library with C++17 filesystem support.

For GNU/libstdc++ compatibility, the Makefile exposes:

```text
FILESYSTEM_LIBS ?= -lstdc++fs
```

Override it when the platform supplies `std::filesystem` without a separate compatibility archive:

```bash
make -C src/xstar_tools/xstar/cpp FILESYSTEM_LIBS= -j2
```

Milestone 8 will formalize the native build inside pip/wheel packaging. This page documents the current source-build contract rather than promising a binary wheel matrix.
