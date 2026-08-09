# Qualification policy

Qualification follows this authority order:

1. accepted qualification evidence for already-closed behavior;
2. canonical XSTAR Fortran 2.59g executable semantics;
3. papers/manuals for explanation and scientific context.

The parity boundary is machine-readable in `qualification/parity_freeze.json` and enforced by `tools/qualification/check_parity_freeze.py`.

Normal productization changes should run the relevant targeted characterization gates. Scientific/orchestration changes use representative fast fixtures first. All-62 qualification is reserved for deliberate science changes, release candidates when required, or explicit parity campaigns rather than every documentation/API change.

Material numerical science, inventory/membership, rank/order, and attachment diagnostics remain distinct surfaces. Known structural exceptions belong in qualification metadata rather than being hidden by broad tolerances.
