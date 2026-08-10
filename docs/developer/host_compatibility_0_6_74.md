# 0.6.74 host compatibility and benchmark semantics

## Scope

This maintenance release fixes compiler/Python-host compatibility and restores already-qualified benchmark semantics. It does **not** change the accepted XSTAR numerical science.

## Python C-API include order

`xstar_backend_python.cpp` includes `Python.h` before any project or C/C++ standard header. CPython documents this ordering because `pyconfig.h` can define feature-test macros that affect system headers. Newer glibc exposed the previous ordering as `_POSIX_C_SOURCE` and `_XOPEN_SOURCE` redefinition warnings.

## Fortran `comp2` diagnostic accumulator

Canonical `comp2.f90` accumulates `sum2` and uses it for the optional diagnostic quantity `cfake`. The production C++ path retains that source-equivalent accumulation for concordance but does not publish `cfake`; the two aggregate variables are therefore marked `[[maybe_unused]]`. No arithmetic expression was removed or changed.

## Python runner startup

`physical_output_diagnostics.py` was intentionally archived in the 0.6.56 parity-history cleanup. The remaining unconditional import was stale. Normal pure-Python and zone-Python runs no longer depend on it. The historical `--diagnostics-dir` compatibility branch imports it lazily and reports a clear error if requested.

## Frozen C++ FITS semantic rules

For `zone-cpp`, `zone-all`, and `xstar-cpp`, the public benchmark comparator applies the final fail-closed publication rules qualified in 43.3/43.3.2:

- `xo01_detal2.fits`: no candidate-only rows; Fortran-only primary indices restricted to `66822` / `88440`; common science, metadata, attachments, and common relative order must pass.
- `xout_rrc1.fits`: only Fortran-only identity `(23595, ca_xiii, 2p4.1S_0)` is permitted.
- carbon `xo01_detal3.fits`: unmatched candidate indices restricted to `{709,762}` and Fortran indices to `{681,691,726}`.
- O VII density-case `xo01_detal3.fits`: candidate-only rows must all be `o_iv` with `energy <= 0`, with no Fortran-only rows.
- detail3 full identity-union normalized L1 is recomputed with zeros on the absent side and must remain `<1%`.

The rules reject unknown identities, positive-threshold O IV extras, duplicate identities, HDU/column inventory changes, attachment errors, common-order errors, metadata failures, or material union NL1 failures.

## Uploaded 0.6.67 zone-cpp reanalysis

The supplied benchmark has 62/62 STEP numerical/full acceptance. The old public FITS comparator reported 49/62 solely because it required exact inventory. Direct FITS identity inspection showed all 13 nominal rejects belong to the frozen classes above. The maximum detail3 full-union NL1 is `4.57956962779e-4` (0.0458%), so the corrected result is 62/62 science ACCEPT.

See `qualification/zone_cpp_0667_reanalysis_0_6_74.json` and `.csv`.
## Frozen C++ reference is the primary benchmark acceptance

The uploaded `benchmark_0667` zone-cpp products were compared directly to the
accepted `0.6.48.12.3.44` `cpp-zone` products in
`v064812344_all62_three_mode.tar.gz`. All 62 models reproduce the frozen C++
reference exactly under the same cross-mode policy used by the original
qualification: all 558 persisted FITS HDU data payloads are byte-for-byte
identical and all 62 STEP logs are normalized-exact.

This exact frozen-C++ reproduction is stronger evidence for C++ regression
acceptance than forcing publication identity with Fortran. The known Fortran
Option-24 stale-local H I/He II alias remains a Fortran text-output bug, and
the already-qualified `xo01_detal2`, `xo01_detal3`, and RRC inventory/order
exceptions remain structural diagnostics so long as the accepted material
science policy is satisfied. Do not modify C++ science merely to reproduce
those Fortran publication defects.

## Native source-tree consolidation

`xstar_cpp_frontend.cpp` now lives beside the rest of the native implementation
in `src/xstar_tools/xstar/cpp/`. The former `src/xstar_tools/xstar/native/`
directory is removed. The normal Makefile build uses only files in `cpp/`; the
package version has a local default and wheel packaging overrides it explicitly.
Repository-only test targets may reference repository fixtures, but those are
not inputs to `make all`.

