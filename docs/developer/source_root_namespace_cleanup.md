# Top-level Python source namespace cleanup

Version 0.6.64 separates the installed top-level `xstar_tools` package from
parity-campaign attribution/probe utilities that no longer have an active
source importer or console entry point.

## Active boundary

The active `src/xstar_tools/*.py` set is for runtime/public APIs, current CLI
entry points, and intentionally retained public facade modules.  In
particular, `matrix.py`, `rates.py`, `runs.py`, `solve.py`, and `validate.py`
remain active even when they are not imported internally because they are
user-facing namespaces.

The source-faithful production path remains in `src/xstar_tools/xstar/`, with
stable public execution orchestration in `execution.py`, `backends.py`, and
`cli/`.

## Archived boundary

Thirty-one top-level parity/attribution/probe modules were moved to:

`historical/python/source_root_parity_campaign/`

The archived set includes the Call-1/O VII attribution CLIs, matrix/population
closure probes, priority native-integration audits, record-level replay/parity
utilities, and old native-rate parity probes.  Their original paths and
SHA-256 hashes are recorded in
`qualification/source_root_history_cleanup_0_6_64.json` and the historical
relocation manifest.

Active source, tests, and qualification tools must not import these modules.
Normal distributions prune the top-level `historical/` tree.

## Generated O VII directory

`o7_solver_source_fit_density_xstar_grid/` was generated output from the
retired O VII density-grid example.  It was never an input fixture or runtime
resource.  It is removed completely, and the package-tree test now requires
that the directory does not exist.

## Test collection

The repository-level pytest configuration now sets `testpaths = ["tests"]`
and excludes `historical/`.  Plain `pytest` therefore runs the active suite
instead of trying to collect intentionally archived tests whose source modules
have also been archived.

## Concordance characterization

Current source-concordance characterization is anchored by
`tests/test_source_characterization_current.py`.  Earlier `test_source_port_*`
tests remain historical qualification lineage, but active concordance
documentation no longer presents them as current runnable tests.
