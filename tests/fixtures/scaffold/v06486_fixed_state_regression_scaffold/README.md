# ABI 60486 fixed-state regression scaffold

This directory is a **qualification-only scaffold** for the C++ fixed-state
ABI/scaffold commands used by `make test`.  It is not a historical XSTAR
fixture and must not be used as a science/parity oracle.

The scaffold is derived from coefficient payloads in the historical
`v06485_active_family_phase2_fixture`, but it is deliberately reshaped for the
current `60486` file-program contract:

- the compact rows form one synthetic ion with four levels, so the historical
  file-loader LTE-topology fallback covers the complete compact element;
- executable records use the current 21-column file schema and dense one-based
  line indices;
- `native_continuum_count=63` gives the 64-slot source-workspace shape expected
  by the long-standing fixed-state scaffold self-test;
- Types 49, 53, 57, 88, and 99 are excluded because their current evaluators
  require transport/source-order/literal-payload context that this small
  file-program scaffold does not own.

The retained records preserve their historical source positions, record IDs,
real/int payload offsets and counts, and scalar/matrix classification.  The
scaffold is intended only to exercise context creation, state-dependent
fixed-state evaluation, batch evaluation, exact source-workspace retention,
and native output publication without importing a transport controller into a
local ABI smoke test.
