# XSTAR standalone C++ and shared-library tree

This directory is the retained flat native tree for `xstar_tools`.

All native artifacts stay here:

```text
src/xstar_tools/xstar/cpp/
  *.h, *.hpp, *.cpp
  Makefile
  build_lib.sh
  libxstar_*.so
  xstar_cpp
```

Python XSTAR code remains one directory above, under:

```text
src/xstar_tools/xstar/*.py
```

Do not copy shared libraries into `src/xstar_tools/xstar/`.

## v0.6.44.2 standalone architecture

v0.6.44.2 adds:

- `libxstar_api.so`: stable versioned C ABI, backend registry, context lifecycle,
  single-zone API, batch API, component status, and counters;
- `libxstar_backend_cpp.so`: persistent C++ backend plugin that discovers the
  existing physics libraries in this directory;
- `libxstar_backend_python.so`: optional embedded-CPython backend plugin plus a
  generic JSON bridge for adapted Python routines;
- `xstar_cpp`: standalone executable linked only to `libxstar_api.so`;
- public headers `xstar_api.h`, `xstar_backend_plugin.h`,
  `xstar_python_bridge.h`, and the C++ RAII wrapper `xstar_api.hpp`.

The typed zone/batch boundary is deliberately **scaffold-only in v0.6.44.2**.
Without `XSTAR_CONFIG_ALLOW_SCAFFOLD_MODEL`, `run_zone` returns
`XSTAR_STATUS_NOT_IMPLEMENTED`. Production science remains on the accepted
v0.6.43.1 Python/hybrid runner while complete engine, emissivity, opacity, and
thermal ownership are moved behind this ABI.

## Build

```bash
cd src/xstar_tools/xstar/cpp
make clean
make -j
make test
```

or:

```bash
./build_lib.sh
```

The build uses `python3-config` for the optional Python plugin. Override it when
needed:

```bash
make PYTHON_CONFIG=/path/to/python3-config
```

## Standalone commands

```bash
./xstar_cpp list-backends
./xstar_cpp backend-info --backend cpp --plugin-dir .
./xstar_cpp backend-info --backend python --plugin-dir . --python-path ../../..
./xstar_cpp self-test --backend cpp --plugin-dir . --batch 8
PYTHONPATH=../../.. ./xstar_cpp self-test \
  --backend python --plugin-dir . --python-path ../../.. --batch 8
```

Component requests can be selected independently:

```bash
./xstar_cpp backend-info \
  --backend cpp \
  --solver-backend cpp \
  --rates-backend cpp \
  --matrix-backend cpp \
  --emissivity-backend python \
  --opacity-backend python \
  --thermal-backend python \
  --plugin-dir .
```

In v0.6.44.2 these overrides are recorded and exposed by the ABI. Mixed physics
dispatch will be activated as each complete component becomes product-ready.

## Public ABI

Use `xstar_api.h` from C, Fortran `ISO_C_BINDING`, Julia, or other languages.
Use `xstar_api.hpp` for a small C++ RAII wrapper.

Key calls:

```c
xstar_context_create_v1(...);
xstar_context_run_zone_v1(...);
xstar_context_run_batch_v1(...);
xstar_context_get_component_info_v1(...);
xstar_context_get_stats_v1(...);
xstar_context_destroy(...);
```

The API uses caller-owned arrays, explicit capacities, opaque persistent
contexts, and no STL types in the public ABI.

## Python shared-library bridge

`libxstar_backend_python.so` exports:

```c
xstar_python_call_json_v1(module, callable, request_json, ...);
```

This lets external native programs invoke Python adapters through a shared
library while keeping Python out of the main executable. The target callable
receives one JSON-decoded object and returns a JSON-serializable object. Typed,
high-throughput physics should use the zone/batch ABI instead of JSON.

## Existing physics libraries

The retained libraries are:

- `libxstar_solver.so`
- `libxstar_rates.so`
- `libxstar_matrix.so`
- `libxstar_emissivity.so`
- `libxstar_opacity.so`
- `libxstar_thermal.so`
- `libxstar_engine.so`

The C++ backend plugin loads these dynamically and reports their ABI,
implementation name, feature flags, and product/scaffold status.

`libxstar_opacity.so` and `libxstar_thermal.so` remain scaffolds in v0.6.44.2;
loading them does not mean those physics paths are active.

## Development rules

- Keep every native source/header/library/executable in this directory.
- Keep Python implementations under `src/xstar_tools/xstar/`.
- Preserve a stable, versioned C ABI.
- Use persistent contexts and coarse zone/evaluation calls.
- Do not add per-record Python/C++ transitions to the production path.
- Keep Python backends and whole-evaluation fallback available during porting.
- Do not report scaffold output as a science result.
