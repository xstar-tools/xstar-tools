# 0.6.48.9.7 quiet/compact/PGO-native plan

`0.6.48.9.7` starts from the accepted `0.6.48.9.6` source and keeps its science-critical implementation frozen.

## Runtime changes

1. **Quiet controller output** — native standalone production suppresses the historical controller attribution/status stream while it is timed. Set `XSTAR_V064897_VERBOSE_CONTROLLER_DIAGNOSTICS=1` to restore the full 9.6-style stream for qualification.
2. **Compact deferred-DSEC provenance** — the 54 ordinary DSEC evaluations still build the complete live `EvaluatedRecord` data required by science, but no longer copy that full object into the retained `last_record_diagnostics` sidecar. Exact accepted-boundary/final evaluations still retain the complete record product diagnostics. Set `XSTAR_V064897_FORCE_096_RECORD_PROVENANCE=1` to restore 9.6 retention on every evaluation.
3. **Compiler evaluation** — the Makefile supports PGO generate/use and optional `-march=native`. These modes are not production defaults until host exact-product qualification passes.

## Frozen science

The 9.6 Type50 kernel, Type49/53 rate engine, exact 9.4.2 boundary recomputation, thermal source-order implementation, FITS writer, step log, and related science kernels are source-hash frozen by `tools/qualification/v064897/check_readiness.py`.

## Required promotion gates

The default 9.7 build must be byte-exact to the accepted 9.6 C++ products and to the same executable with 9.6 record provenance forced. Public FORTRAN/Python science gates must remain accepted.

PGO and PGO+native are evaluated independently. Each compiler variant must reproduce the accepted 9.6 FITS data payloads and normalized scientific `xout_step.log` exactly before its timing is considered. `-ffast-math` remains forbidden and `-ffp-contract=off` remains on source-critical translation units.
