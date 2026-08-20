# 0.6.82.30.8.7 Fe C++ hot-record performance candidate

This is a performance-only successor to host-accepted `0.6.82.30.8.6`.

The accepted `.30.8.6` Fe run reduced controller time from 102.890274 s to 85.216579 s while retaining exact FORTRAN science. Its remaining fixed-state traversal cost was 56.662577 s across 2,222,932 evaluated records.

## Change 1: lazy Type-49/53 sidecar

`EvaluatedRecord` previously stored six `Type53SourceShadow` objects plus bound-free context inline for every atomic record. On the qualification compiler this made the record 6016 bytes, even though only Type-49/53 records need those shadows.

`.30.8.7` moves those fields into `BoundFreeEvaluatedPayloadV06823087`, owned by a lazy `std::shared_ptr`. Mutable access implements copy-on-write: if a retained diagnostic/revisit copy shares the payload, the mutating record detaches first. This preserves value semantics while reducing `sizeof(EvaluatedRecord)` to 1184 bytes.

No rate, endpoint, matrix, solver, thermal, controller-order, or transport equation changes.

## Change 2: deferred DSEC element-diagnostic elision

True-production DSEC/root-finding evaluations have `DEFER_PRODUCT_PROJECTION` set. They consume thermal/state results but do not consume the retained element diagnostic package. `.30.8.7` therefore skips deep-copying contribution vectors, populations, residuals, and related diagnostic arrays only for those deferred native-production evaluations.

Accepted-boundary/final evaluations, ordinary library calls, and diagnostic runs keep the old behavior. `XSTAR_V06823087_FORCE_ELEMENT_DIAGNOSTICS=1` forces the retained diagnostic package for A/B inspection.

## Acceptance

The host run must retain the exact accepted Fe science surface (`STEP`, material, spectrum, `ntotit=13,1,1`, and `LOGT_MAX_ABS=0`) and should improve on the `.30.8.6` controller/traversal timing.
