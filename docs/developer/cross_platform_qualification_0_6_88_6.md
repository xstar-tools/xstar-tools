# 0.6.88.6 - CROSS_PLATFORM_QUALIFICATION

## Purpose

Close the `0.6.88` portability series with one qualification contract spanning the four native host targets that have been developed independently:

- Linux with GCC and GNU Make;
- macOS arm64 with Apple Clang and GNU Make;
- macOS x86_64 with Apple Clang and GNU Make;
- Windows with MSYS2 UCRT64, MinGW-w64 GCC, and GNU Make.

Windows MPI remains out of scope. The qualification covers the normal non-MPI production build and the local-process `xstar-xspec` scheduler on Windows.

## Production boundary

`0.6.88.6` is a qualification/documentation milestone. Relative to the formally accepted Windows predecessor `0.6.88.5.7`, production C++ behavior is unchanged. `Makefile`, `xstar_xspec_parallel.cpp`, and `xstar_xspec_mpi.cpp` change only package-version metadata. All other C/C++ production sources, including `xstar_backend_python.cpp`, are byte-identical to `.5.7`.

The release does not change scientific arithmetic, controller decisions, traversal order, contribution order, accumulation order, cutoffs, publication semantics, output schemas, atomic-data discovery, dynamic loading, process semantics, or public ABI values.

## Unified host contract

Every host runs the same source checker and a platform-aware host runner. Common gates include:

- compiler/toolchain discovery;
- platform `print-config` contract;
- clean native non-MPI build;
- strict warning-free compilation;
- platform-native binary/shared-library format;
- required public export symbols;
- package version reporting;
- sibling-library and `XSTAR_PLUGIN_PATH` discovery;
- direct process-layer smoke;
- synthetic four-job `xstar-xspec --processes 2` scheduler smoke;
- ABI60486 fixed-state self-test and batch self-test;
- fixed-state publication with byte-exact SHA-256 checks for `xout_step.log`, `xout_native_state.fits`, and `visited_records.csv`;
- embedded Python backend self-test;
- Python bridge test;
- existing `make test` regression suite.

The synthetic XSTAR2XSPEC smoke intentionally uses small fake planner/worker/table executables to qualify scheduler/process mechanics without requiring a large atomic database. It is not a scientific table-generation test.

## Frozen fixed-state hashes

The cross-platform runner requires:

```text
xout_step.log          5508313e40d514d63b4d5443bc67198fe1a62a82f76f428958e6a5ea07cafa38
xout_native_state.fits e430573df3bd1666fef4b3e5e8305f0b912e06456685aa921f4737f305e875f4
visited_records.csv    7d1addd4a66f29eda03d96954f8f07b3aa5bd627e8d506d84a3079f47474c3a3
```

These hashes are the accepted ABI60486 fixed-state scaffold evidence and do not require the external production `atdb.fits` database.

## CI topology

`.github/workflows/cross-platform-qualification.yml` runs:

1. Ubuntu/Linux GCC;
2. `macos-15` arm64 Apple Clang;
3. `macos-15-intel` x86_64 Apple Clang;
4. `windows-latest` with MSYS2 UCRT64/MinGW-w64.

Each job uploads its host-runner output directory independently so a platform rejection remains attributable to that host.

## Documentation closure

The user documentation adds a dedicated Windows native installation and usage guide covering MSYS2 UCRT64 dependencies, `PLATFORM=windows`, building `xstar-cpp.exe`, atomic-data setup, an included C5 example, direct `name=value` invocation, local-process XSTAR2XSPEC, troubleshooting, and the cross-platform host qualification command.
