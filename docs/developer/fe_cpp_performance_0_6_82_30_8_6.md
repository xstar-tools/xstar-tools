# 0.6.82.30.8.6 Fe C++ performance optimization

The accepted `0.6.82.30.8.4` Fe run established exact FORTRAN science parity (`ntotit=13,1,1`, `LOGT_MAX_ABS=0`). Its controller profile showed 102.890274 s total controller time, with 74.799553 s attributed to fixed-state traversal but only 4.068150 s to rate evaluation and 3.999204 s to the element/Lucy solve.

This revision removes publication bookkeeping from deferred DSEC/root-finding evaluations. `DEFER_PRODUCT_PROJECTION` is already a production runtime-state contract: those evaluations consume thermal/state results and do not publish line/RRC products. The optimization therefore skips only data structures whose consumers are in calc_emis/product publication.

Changes:

- do not construct the line/RRC `spectral` publication vector when product projection is deferred;
- do not retain Type-49/53 full-grid revisit `EvaluatedRecord` copies during deferred evaluations;
- do not construct `errc` publication maps during deferred evaluations;
- reuse the immutable context `record_index_by_identity_v064895` instead of rebuilding the full pprint(4) record map every evaluation;
- remove an unused copy of the committed contribution vector.

No rate, matrix, Type-82, solver, thermal, controller, transport, or publication arithmetic is changed. Non-deferred accepted/final boundaries execute the same publication code as before.
