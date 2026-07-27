# 0.6.48.9.4.1 boundary-reuse correction

## Why 0.6.48.9.4 was rejected

The 9.4 prototype reused an ordinary DSEC workspace produced with `XSTAR_FIXED_RUNTIME_STATE_DEFER_PRODUCT_PROJECTION`.  That workspace intentionally omitted the final `calc_emis_all` selected bound-free/RRC replay and the writer-facing line-emission projection.  The retained `opakcont` therefore lacked the selected bound-free continuum opacity, `dpthcont` remained zero after transport, STEP selected different shell lengths, and the source-style option-17 radial rows changed.  The blocking reuse-versus-legacy comparison rejected all nine FITS products and the scientific step log.

## 9.4.1 correction

The canonical Mg XI trajectory has fixed terminal DSEC positions 20/1/17/16.  In 9.4.1, all earlier DSEC evaluations remain deferred, but those four terminal DSEC evaluations run the normal non-deferred product projection after the thermal/rate calculation.  The accepted-boundary path then copies that exact completed source workspace and overlays the caller-owned cumulative radial state.  It refuses to promote a deferred workspace.  Generic/non-reference trajectories continue to fall back to the legacy accepted-boundary recomputation.

The terminal post-transport zero-thickness evaluation remains a real full fixed-state evaluation.

## Blocking host qualification

The normal path is compared against `XSTAR_V064894_FORCE_LEGACY_BOUNDARY_RECOMPUTE=1`.  Acceptance requires all nine FITS data payloads to be bit-identical and the non-timing `xout_step.log` content to be identical.  This directly covers the option-17 radial rows, nonzero continuum depth, radial STEP geometry, and final thermal state.

## Diagnostic output policy

`rccemis_attribution/` is disabled by default.  Set `XSTAR_ENABLE_RCCEMIS_ATTRIBUTION=1` on the qualification runner only when Type99/RRC producer attribution is needed.

The extra ProductWritingState/native product-surface footer is disabled by default in `xout_step.log`.  Set `XSTAR_DEBUG_PRODUCT_STATE_SUMMARY=1` when that internal inventory is needed.  The source-style option-17 table remains normal production output.
