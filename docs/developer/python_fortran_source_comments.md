# Python / FORTRAN source correspondence comments

Production Python modules in the source-faithful XSTAR layer carry concise comments that identify the corresponding FORTRAN XSTAR routines and important representation constraints. These comments are explanatory; they do not establish an independent scientific authority.

The canonical scientific oracle remains FORTRAN XSTAR 2.59g. The active scientific freeze is enforced by `tools/qualification/check_parity_freeze.py`, which verifies the accepted science revision and exact hashes for the current science-critical source set.

## Atomic-data terminology

Keep the distinction between **data type** and **rate type** explicit. Data type identifies the packed record formula/interpretation; rate type describes how the resulting data/rate is used downstream. They must not be treated as interchangeable identifiers.

## Maintenance rule

When editing correspondence comments:

- do not change source arithmetic or operation ordering under a documentation-only change;
- keep routine/file names factual and tied to the actual implementation;
- run the parity-freeze and source-concordance gates after any change near science-critical modules;
- if executable science must change, create a dedicated science qualification milestone rather than rebasing the documentation closure.

Closed comment-overlay manifests/checkers from earlier milestones are retained by version-control history/tags rather than shipped in active releases.
