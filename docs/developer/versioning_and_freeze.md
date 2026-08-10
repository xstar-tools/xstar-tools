# Versioning and science freeze

`xstar-tools` tracks several independent identities:

- **package version** — product/API/docs/packaging evolution (`0.6.72` here);
- **science revision** — accepted Python scientific behavior (`0.6.48.12.3.45.3.3.8`);
- **frozen C++ baseline** — accepted all-62 native baseline (`0.6.48.12.3.44`);
- **C API ABI** — `60487`;
- **production-zone ABI** — `6048110`.

A documentation, CLI, API, or packaging release must not change the science revision just because its distribution version changes.

`PARITY_FREEZE.md` and `qualification/parity_freeze.json` define the frozen scientific invariants, accepted comparator policy, and structural exceptions. Any intentional scientific reopening requires explicit qualification and a new science revision.
