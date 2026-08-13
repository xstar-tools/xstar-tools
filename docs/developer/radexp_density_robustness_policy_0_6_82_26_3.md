# `0.6.82.26.3`: `radexp` / `density.dat` robustness-policy closure

## Scope

`0.6.82.26.3` is deliberately **not** a numerical-science change. Host qualification of `0.6.82.26.2` accepted all six valid radial-density cases in both native C++ and pure Python against canonical FORTRAN XSTAR 2.59g:

```text
radexp0       STEP 3/3   density_rel=0   law=0
radexpm05     STEP 7/7   density_rel=0   law=9.22e-07
radexpp1      STEP 3/3   density_rel=0   law=1.88e-06
radexpm2      STEP 9/9   density_rel=0   law=2.60e-06
table_column  STEP 4/4   density_rel=0   law=0
table_eof     STEP 5/5   density_rel=0   law=0
```

The only remaining `.26.2` REJECT was the failure harness expecting canonical FORTRAN to emit a `missing density file` error. The actual FORTRAN run did not do so.

## Missing `density.dat`: observed canonical behavior

With hidden table mode selected but `density.dat` absent, canonical FORTRAN XSTAR 2.59g returned zero and continued far enough to print non-finite/overflow-formatted state, including `Inf` and `******`, before the normal final print. It did **not** emit `missing density file`.

Reproducing that behavior in the modern ports would deliberately propagate invalid state. `0.6.82.26.3` therefore records the difference as an explicit robustness divergence:

```text
table_missing:
    FORTRAN = LEGACY_UNSAFE_CONTINUE
    C++     = SAFE_REJECT
    Python  = SAFE_REJECT
    policy  = ACCEPT_DOCUMENTED_ROBUSTNESS_DIVERGENCE
```

C++ retains its explicit `missing density file` error and nonzero return. Pure Python retains `TabulatedRadialDensityError` with the same missing-file message and a nonzero return. This difference is classified as **not a science discrepancy**.

## Non-monotonic radius

The canonical source condition remains unchanged:

```text
table_nonmonotonic:
    FORTRAN = radius error
    C++     = radius error
    Python  = radius error
    policy  = ACCEPT_SOURCE_CONCORDANT
```

FORTRAN `STOP radius error` may return process status zero; C++ and Python return nonzero. The semantic error condition/message is the source-concordance requirement.

## Direct six-case freeze

To ensure this policy hotfix cannot silently alter the already accepted `.26.2` science, the `.26.3` manifest contains SHA-256 hashes for every numerical file under `src/xstar_tools/xstar` with extensions `.py`, `.cpp`, `.h`, `.hpp`, `.def`, or `.dat`: 137 files from the exact `.26.2` predecessor.

The `.26.3` checker rejects if any hash differs. It also compares the six successful case inputs, thresholds, and the successful-case runner/comparator function ASTs against the packaged `.26.2` host runner.

Only package-version/qualification/documentation files are permitted to differ.

## Frozen identifiers

```text
science revision:     0.6.48.12.3.45.3.3.8
C API ABI:            60487
production-zone ABI:  6048110
fixed-state ABI:      60488
```

No ABI or science-revision update is made.
