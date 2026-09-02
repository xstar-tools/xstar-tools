# xstar-tools documentation

`xstar-tools` provides Python, CLI, shared-C++, and native interfaces around a source-faithful XSTAR implementation whose accepted scientific behavior is frozen independently from package/API and portability evolution.

**Current formally accepted native portability baseline:** `0.6.88.6.1.2.1`, accepted on Linux GCC x86_64, macOS arm64, macOS Intel x86_64, and Windows MSYS2 UCRT64/AMD64. Windows MPI remains out of scope.

```{toctree}
:maxdepth: 2
:caption: User guide

user/index
```

```{toctree}
:maxdepth: 2
:caption: Python API

api/index
api/public_api
```

```{toctree}
:maxdepth: 2
:caption: C++ and CLI

cpp/index
```

```{toctree}
:maxdepth: 2
:caption: Developer guide

developer/index
```

```{toctree}
:maxdepth: 2
:caption: Science guide

science/index
```

```{toctree}
:maxdepth: 1
:caption: History

history/index
```

Useful starting points:

- {doc}`user/installation` — installation and source-build prerequisites;
- {doc}`user/windows_installation_and_usage` — accepted MSYS2 UCRT64 Windows path;
- {doc}`user/atomic_data` — `atdb.fits` / `coheat.dat` discovery and setup;
- {doc}`cpp/index` — native CLI reference;
- {doc}`developer/cross_platform_portability_status` — current platform matrix and portability closure;
- {doc}`developer/qualification` — qualification policy and frozen-boundary rules.
