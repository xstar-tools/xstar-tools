# Versioning and science freeze

`xstar-tools` tracks several independent identities:

- **package version** — product/API/docs/packaging evolution (`0.6.90.5.8` here);
- **science revision** — accepted Python scientific behavior (`0.6.90.5.5`);
- **frozen C++ science baseline** — accepted science-changing native milestone (`0.6.90.5.5`);
- **C API ABI** — `60487`;
- **production-zone ABI** — `6048110`.

A documentation, CLI, API, or packaging release must not change the science revision just because its distribution version changes.

`PARITY_FREEZE.md` and `qualification/parity_freeze.json` define the frozen scientific invariants, accepted comparator policy, and structural exceptions. Any intentional scientific reopening requires explicit qualification and a new science revision.

The `0.6.90.5.5` science revision was explicitly requalified and re-frozen in package `0.6.90.5.8` using an all-elements `mnabund=1` FORTRAN-vs-C++ host comparison. Package `0.6.90.5.6` and `0.6.90.5.7` changed terminal diagnostics only and therefore do not advance the science revision.
