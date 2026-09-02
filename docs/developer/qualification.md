# Qualification policy

Qualification follows this authority order:

1. accepted qualification evidence for already-closed behavior;
2. canonical XSTAR Fortran 2.59g executable semantics;
3. papers/manuals for explanation and scientific context.

The parity boundary is machine-readable in `qualification/parity_freeze.json` and enforced by `tools/qualification/check_parity_freeze.py`.

Normal productization changes should run the relevant targeted characterization gates. Scientific/orchestration changes use representative fast fixtures first. All-62 qualification is reserved for deliberate science changes, release candidates when required, or explicit parity campaigns rather than every documentation/API change.

Material numerical science, inventory/membership, rank/order, and attachment diagnostics remain distinct surfaces. Known structural exceptions belong in qualification metadata rather than being hidden by broad tolerances.

## Cross-platform portability qualification

The accepted `0.6.88.6.1.2.1` portability contract distinguishes same-host reproducibility from cross-platform numerical equivalence. A fixed-state run is repeated on each host and must be raw-byte deterministic against itself. Cross-host comparison then requires exact discrete state and FITS structure, normalizes text line endings, and applies the strict dual limit of relative difference `<= 1e-13` and ULP distance `<= 64` only to differing finite floating values.

This avoids treating CRLF serialization or legitimate last-bit architecture differences as scientific regressions while retaining exact checks for traversal/inventory/order/schema and strong per-host determinism. See {doc}`cross_platform_portability_status`.

