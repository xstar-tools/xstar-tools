# C ABI

The current public C API ABI is `60487`; the production-zone ABI is `6048110`. ABI versions are independent of both the Python distribution version and the frozen science revision.

`xstar-cpp` queries the linked ABI identities before scientific execution and fails clearly if the packaged frontend and linked production libraries do not agree.

Compatibility rules:

1. do not change ABI numbers for documentation/API-only productization;
2. change an ABI only when its exported binary contract changes;
3. keep the science revision independent unless scientific behavior is intentionally reopened;
4. fail before science when a required runtime ABI is incompatible.

The exported-function inventory and implementation details are documented in `docs/developer/c_abi.md`.
