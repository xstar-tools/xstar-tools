# CI and release engineering

The active CI policy is intentionally compact. Closed version-specific host
closure workflows are preserved in repository history rather than copied into
each release.

## Current always-on gates

`.github/workflows/ci.yml` installs the package with development dependencies,
runs generic repository/metadata policy checks, validates the frozen scientific
boundary and source concordance, then runs the current pytest regression suite.

The generic policy tools are:

- `tools/ci/check_tree_clean.py` — rejects generated build/cache artifacts;
- `tools/ci/check_package_metadata.py` — package-version/science/ABI consistency;
- `tools/ci/check_python_contract.py` — Python syntax/import/public API typing;
- `tools/ci/check_text_policy.py` — conservative text-format policy;
- `tools/qualification/check_parity_freeze.py` — exact scientific source/reference/ABI boundary;
- `tools/qualification/check_source_concordance.py` — current Fortran/Python/C++ correspondence map;
- `tools/release/check_release_candidate.py` — current release-tree boundary.

`.github/workflows/parity-freeze.yml` provides a lightweight standalone frozen
boundary check. `.github/workflows/pypi-release.yml` is the generic wheel/sdist
build workflow.

## Optional deeper qualification/report helpers

`tools/ci/check_science_results.py`, `require_science_assets.py`,
`report_benchmark_results.py`, and `performance_report.py` remain for controlled
scientific/performance qualification where external reference assets or
specialized runners are available. They are not historical replay gates.
