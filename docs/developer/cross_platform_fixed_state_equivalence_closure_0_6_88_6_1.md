# 0.6.88.6.1 - CROSS_PLATFORM_FIXED_STATE_EQUIVALENCE_CLOSURE

## Purpose

Close the qualification defect exposed by the real `0.6.88.6` four-host matrix without changing production science or portability implementation.

`0.6.88.6` incorrectly required the Linux/x86-64 raw SHA-256 values for all three ABI60486 fixed-state products on every architecture. That contract rejected Windows because of CRLF text serialization and rejected macOS arm64 because of tiny architecture-dependent floating-point differences, even though the surrounding build/runtime/science-structure gates accepted.

## Production boundary

Relative to `0.6.88.6`, production behavior is unchanged. Only normal package-version metadata changes in:

- `pyproject.toml`;
- `src/xstar_tools/xstar/cpp/Makefile`;
- `src/xstar_tools/xstar/cpp/xstar_xspec_parallel.cpp`;
- `src/xstar_tools/xstar/cpp/xstar_xspec_mpi.cpp`.

All other Python and C/C++ production sources remain byte-identical. No scientific arithmetic/order, controller, traversal, contribution, publication, loader, process, path, schema, or public ABI change is introduced.

Windows MPI remains out of scope.

## Corrected fixed-state qualification contract

### Same-host determinism

Every native host runs `run-fixed-state` twice. The raw SHA-256 of each product must match its repeat on that same host:

- `xout_step.log`;
- `xout_native_state.fits`;
- `visited_records.csv`.

This retains a strict byte-determinism requirement without assuming different operating systems/architectures serialize or round identically.

### Cross-platform text semantics

For comparison to the canonical reference, CRLF and bare CR are normalized to LF. `visited_records.csv` must then match exactly. Non-floating/discrete fields in `xout_step.log` must match exactly and in the same order.

### Cross-platform FITS semantics

The comparator parses the fixed-state FITS file directly and requires exact HDU count and exact binary-table structure, including `EXTNAME`, row length/count, field count, column names, and column formats. The current qualification fixture contains only `D` (IEEE binary64) columns in the two binary tables.

### Finite floating-point equivalence

Every floating field from `xout_step.log` and both FITS tables is compared to the canonical x86-64 reference. A non-identical finite nonzero value is accepted only when **both** are true:

```text
relative difference <= 1e-13
ULP distance        <= 64
```

Zero/nonzero changes, NaN mismatches, infinity mismatches, discrete-state changes, schema changes, and traversal changes remain hard failures.

## Canonical qualification reference

The qualification-only reference directory is:

```text
qualification/cross_platform_fixed_state_reference_0_6_88_6_1/
```

It contains the `0.6.88.6` Linux GCC x86-64 payload; macOS Intel x86-64 produced the same raw hashes:

```text
xout_step.log          5508313e40d514d63b4d5443bc67198fe1a62a82f76f428958e6a5ea07cafa38
xout_native_state.fits e430573df3bd1666fef4b3e5e8305f0b912e06456685aa921f4737f305e875f4
visited_records.csv    7d1addd4a66f29eda03d96954f8f07b3aa5bd627e8d506d84a3079f47474c3a3
```

Those raw hashes remain useful diagnostic evidence but no longer constitute the cross-architecture acceptance rule.

## Evidence from the predecessor rejection

The real `.88.6` artifacts were checked with the new comparator before promotion:

```text
Linux GCC x86-64       numeric differences=0  result=ACCEPT
macOS Intel x86-64     numeric differences=0  result=ACCEPT
Windows UCRT64 x86-64  numeric differences=0  result=ACCEPT after text newline normalization
macOS arm64            numeric differences=9  max_relative=4.5635339780748665e-15  max_ulp=39  result=ACCEPT
```

## Host acceptance

Formal `.88.6.1` acceptance still requires the same four native hosts:

1. Linux GCC (`ubuntu-24.04`);
2. macOS arm64 Apple Clang (`macos-15`);
3. macOS x86-64 Apple Clang (`macos-15-intel`);
4. Windows MSYS2 UCRT64/MinGW-w64 (`windows-latest`).

Each must return:

```text
CROSS_PLATFORM_FIXED_STATE_EQUIVALENCE_CLOSURE_068861_HOST_RESULT=ACCEPT
```
