## v0.6.48.7.5 helium non-type-53 matrix contribution isolation

v0.6.48.7.5 preserves the 31 IEEE-exact He II type-53 records while adding
qualification-only helium matrix-family and source-position ablations. It
produces per-record, per-family, and per-row ledgers for types 50, 54, 56, 57,
63, 69, 71, 74, 76, 77, 95, and 99, and audits type 30 separately in the
preliminary ion-rate path. Type 99 and type 71 are co-dominant; a causal
source-position pass isolates type 99 source position 6312 / record 1695 as
the strongest candidate. No new physics correction or production promotion is
enabled. See `V064875_HELIUM_NON_TYPE53_MATRIX_ISOLATION.md`.

## v0.6.48.7.3 exact v0.6.47.2 type-53 runtime capture

v0.6.48.7.3 executes the untouched v0.6.47.2 type-53 evaluator in an isolated
fixed-state replay and freezes the resulting 31-record evaluation-61 oracle.
The translated C++ shadow is closer to the exact source than the applied path
for every record, but is not yet IEEE-exact. No production physics replacement
is enabled. See `V064873_V0472_TYPE53_RUNTIME_CAPTURE.md`.
