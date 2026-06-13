## v0.6.48.7.20 type-53 independent-state parity correction

This qualification release closes the evaluation-60 type-53 runtime-state gap discovered by v0.6.48.7.17. It corrects the Milne `rnist` continuum-energy semantics, adds a first-class DSEC covering-fraction field to runtime ABI `60487`, and allows the exact captured Kelvin temperature to be supplied without reconstructing it from rounded `T/10^4` trajectory text.

With the independent original-DSEC evaluation-60 capture, all 44 type-53 records, 264 answers, 176 matrix/thermal terms, and 176 absolute source-order positions reproduce IEEE-exactly. The evaluation-61 anchor remains exact from v0.6.48.7.16. Type-53 arbitrary-state qualification promotion is accepted; whole fixed-state, thermal, controller, output-product, and production promotion remain blocked.

## v0.6.48.7.15 original-DSEC type-53 row-46 runtime-contract audit

This qualification-only release embeds the 44-record, 176-term original DSEC
type-53 manifold contributing to compact helium row 46 at evaluation 61. The
current native path does not reproduce its answers or matrix terms. Applying
the full manifold offline reduces the reference residual by 97.93% and changes
the solved helium population vector toward the v0.6.47.2 reference. The result
justifies a coupled source-faithful implementation, not a single-record or
production correction. See
`V0648715_TYPE53_ROW46_DSEC_RUNTIME_CONTRACT_AUDIT.md`.

## v0.6.48.7.9 type-99 record 1695/type-71 coupled-path audit

## v0.6.48.7.12 DSEC type-50 runtime capture

This release adds a qualification-only observational probe for the untouched
v0.6.47.2 physical DSEC run. It captures the live escape-probability and matrix
contract for the 79 He II type-50 rows-46-54 records without changing the old
calculation. General-state replacement and production promotion remain blocked.


v0.6.48.7.9 preserves the 31 IEEE-exact He II type-53 records and adds an
independent v0.6.47.2 fixed-state evaluator oracle for type-99 source position
6312 / record 1695. The native type-99 path is not IEEE-exact and has incorrect
thermal-channel signs. Grouped and combined ablations isolate the type-71
cascades ending on row 77 and confirm strong non-additivity with record 1695.
No type-99 or type-71 physics correction is promoted. See
`V064876_TYPE99_RECORD1695_TYPE71_COUPLED_PATH_AUDIT.md`.

## v0.6.48.7.3 exact v0.6.47.2 type-53 runtime capture

v0.6.48.7.3 executes the untouched v0.6.47.2 type-53 evaluator in an isolated
fixed-state replay and freezes the resulting 31-record evaluation-61 oracle.
The translated C++ shadow is closer to the exact source than the applied path
for every record, but is not yet IEEE-exact. No production physics replacement
is enabled. See `V064873_V0472_TYPE53_RUNTIME_CAPTURE.md`.

## v0.6.48.7.20 qualification milestone

The complete 44-record type-53 row-46 contract is now promoted at two independently captured states through both the fixed-state entry point and the thermal-controller callback. Evaluation 60 and 61 are IEEE-exact for all 264 answers, 176 matrix/thermal terms, and absolute source order. The remaining `hmctot` gap is not caused by type 53; the promoted manifold adds net helium heating while the original reference requires substantially more cooling.


### v0.6.48.7.20 controller trajectory audit

Use `run_v048720_thermal_controller_state_trajectory_audit.sh` with an existing
v0.6.48.7.19/19.1 output directory to identify workspace selection, first
thermal branch divergence, early termination, and missing between-call state
refresh. This is qualification-only and does not promote the full controller.
