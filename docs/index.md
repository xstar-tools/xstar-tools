# xstar-tools documentation

`xstar-tools` provides Python, command-line, shared-C++, and native interfaces for XSTAR atomic data and source-faithful XSTAR execution. Distribution/productization versions evolve independently from the accepted scientific revision.

**Accepted native non-MPI portability baselines:** Linux GCC x86_64 and aarch64, macOS arm64/x86_64 with Apple Clang, and Windows MSYS2 UCRT64/MinGW-w64. The five-host CPython 3.13 installed-wheel qualification, **0.6.91.4 — CROSS_PLATFORM_CLOSURE**, is ACCEPTED (2026-10-08). Linux ARM64 build (0.6.91.1) and packaging (0.6.91.3) are also ACCEPTED. The ARM64 physics/fixed-state science regression checks passed under the same platform-level standard as other hosts. The separate, optional external-data full-model comparison in the historical 0.6.91.2 runner remains **NOT_RUN**; it is not a prerequisite that was imposed on macOS or Windows, nor evidence of a failed model. Windows conda packages are not supported; MSVC and Windows MPI are not planned. Local Windows parallelism is available through `xstar-xspec --processes N`.

```{toctree}
:maxdepth: 2
:caption: User guide

user/index
```

```{toctree}
:maxdepth: 2
:caption: Python guide

python/index
```

```{toctree}
:maxdepth: 2
:caption: Python API

api/index
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

- {doc}`user/installation` — installation and native source-build prerequisites;
- {doc}`user/cli` — current command-line entry points and compatibility commands;
- {doc}`user/atomic_data` — `atdb.fits` / `coheat.dat` discovery and setup;
- {doc}`python/index` — Python execution, atomic-data, output, and XSPEC-table workflows;
- {doc}`cpp/index` — complete native executable reference;
- {doc}`developer/qualification` — current compact qualification/freeze policy.
