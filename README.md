## v0.6.48.7.4 He II type-53 IEEE-exact application

The 31 evaluation-61 He II data-type 53 records now match the immutable v0.6.47.2 evaluator bit-for-bit in both shadow and applied native paths. The correction is intentionally limited to the oracle-qualified He II scope. Whole-state parity remains blocked because the corrected rates expose compensating errors in other helium contributions.

Run the qualification with:

```bash
./run_v04874_type53_ieee_application.sh LOWERED_PROGRAM OUTPUT_DIR 61
```

Run the full checker with:

```bash
python check_v04874_type53_ieee_application.py --lowered-program LOWERED_PROGRAM --baseline-audit V04871_AUDIT --source-archive XSTAR_TOOLS_06472_TAR
```

## v0.6.48.7.3 exact v0.6.47.2 type-53 runtime capture

v0.6.48.7.3 executes the untouched v0.6.47.2 type-53 evaluator in an isolated
fixed-state replay and freezes the resulting 31-record evaluation-61 oracle.
The translated C++ shadow is closer to the exact source than the applied path
for every record, but is not yet IEEE-exact. No production physics replacement
is enabled. See `V064873_V0472_TYPE53_RUNTIME_CAPTURE.md`.
