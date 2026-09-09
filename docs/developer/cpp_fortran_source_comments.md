# C++ / FORTRAN source correspondence comments

The C++ scientific implementation carries marked source-correspondence comments describing the FORTRAN XSTAR routine(s) that own the corresponding behavior. These comments help maintainers navigate a source-faithful port; they do not authorize changing accepted formulas, indexing, accumulation order, or publication semantics.

The canonical scientific oracle remains FORTRAN XSTAR 2.59g. Current exact science-critical source bytes are protected by `tools/qualification/check_parity_freeze.py`; structural/routine ownership is described by `qualification/source_concordance.json` and checked by `tools/qualification/check_source_concordance.py`.

## Important interpretation rules

- preserve one-based/source identities where the source uses them;
- preserve default-REAL/default-INTEGER conversion semantics when they affect results;
- keep numerical science distinct from output inventory/order diagnostics;
- do not treat an ABI wrapper or portability layer as an independent source of physics;
- keep optimization comments tied to qualified source-equivalent behavior rather than performance claims.

## Maintenance rule

Comment-only maintenance should not alter science-critical code bytes. If a required documentation edit touches a frozen source file, it must be handled under an explicit qualified source/documentation exception or a new science/refactor milestone rather than silently rebasing the freeze.

Earlier version-specific comment-overlay evidence is retained in repository history/tags rather than copied into every release archive.
