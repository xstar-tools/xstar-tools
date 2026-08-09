# Active test namespace cleanup

## Purpose

`xstar_tools` accumulated a large number of parity-campaign tests while the source tree still contained the retired `xstar_atomic` package and version-specific diagnostic utilities.  Those tests are useful provenance, but they are not an appropriate active test surface after productization.

Version 0.6.62 separates current runnable characterization from historical regression evidence without deleting the latter.

## Active-test rule

An active test must target at least one of the following:

- a module or executable still present in the active package;
- a current public execution or benchmark contract;
- a current parity/source-concordance gate;
- a fixture intentionally retained under `tests/fixtures/historical/` because an active test still consumes it.

Tests whose only target is the removed `xstar_atomic` namespace, retired parity launchers/checkers, superseded ABI/version contracts, removed benchmark bundles, or unshipped patch artifacts belong under `historical/tests/`.

## 0.6.62 relocation

The cleanup archives 189 tests:

- 155 `xstar_atomic` legacy tests -> `historical/tests/xstar_atomic_legacy/`;
- 18 retired parity-artifact tests -> `historical/tests/parity_artifact_legacy/`;
- 16 superseded regression tests -> `historical/tests/superseded_regressions/`.

Two no-longer-consumed historical fixture directories are also moved to `historical/tests/unused_fixtures/`.

The active test tree contains 66 test files and zero references to `xstar_atomic`.

## Characterization continuity

Historical test files remain byte-preserved with hashes in `qualification/test_history_cleanup_0_6_62.json`.  Milestone-2 source concordance no longer treats retired `xstar_atomic` tests as current runnable characterization.  Current dependency-free anchors are collected in `tests/test_source_characterization_current.py`.

A future scientific refactor must still point to a current runnable characterization test for each affected concordance entry. Historical tests may provide attribution context, but they do not satisfy that gate by themselves.

## Native build regression discovered during cleanup

The first host benchmark build after 0.6.61 exposed a separate productization defect in the new `xstar-cpp` frontend: its Makefile rule referenced the undefined `STDCXXFS_LIBS` variable even though the package already defines `FILESYSTEM_LIBS ?= -lstdc++fs`. On GCC/libstdc++ toolchains where C++17 `std::filesystem` still requires the compatibility library, the frontend therefore failed at link time with undefined `std::filesystem` symbols.

0.6.62 fixes the rule to use `$(FILESYSTEM_LIBS)` and supplies the distribution version from `pyproject.toml` through `XSTAR_TOOLS_PACKAGE_VERSION`. This is a build/provenance correction only; the qualified native science executable and science sources are unchanged.
