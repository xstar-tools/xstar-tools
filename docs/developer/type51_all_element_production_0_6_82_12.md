# 0.6.82.12 — all-element canonical Type-51 production promotion

Canonical XSTAR `ucalc.f90` Type-51 collision handling is element-independent. The native C++ engine already contained a source-faithful Burgess-Tully evaluator, but commitment of that result was still mediated by qualification/compatibility flags.

For `0.6.82.12`, native production explicitly commits the canonical Type-51 result for every active element. The historical `XSTAR_QUALIFICATION_TYPE51_SOURCE_FAITHFUL` and `XSTAR_QUALIFICATION_MG_TYPE51_SOURCE_FAITHFUL` flags remain available only for explicit non-production compatibility or diagnostics. They are no longer implicitly promoted merely because native production is active.

The source result preserves the source temperature floor, Burgess-Tully transformed temperature and spline evaluation, statistical-weight detailed balance, source exponential convention, density scaling, and the source reuse of density-scaled answers in the heating/cooling energy channels.

This release intentionally keeps the accepted science revision `0.6.48.12.3.45.3.3.8`, C API ABI `60487`, production-zone ABI `6048110`, and fixed-state ABI `60488` unchanged. Those identifiers remain frozen until the broad FORTRAN qualification campaign closes (ABIs only change for actual binary-interface changes).

External host qualification priority remains `rlogxi=-3`, then `-2`, then `-5` for H+He+C, density `1e12`, column `1e20`, `cfrac=1`, `xdef`.
