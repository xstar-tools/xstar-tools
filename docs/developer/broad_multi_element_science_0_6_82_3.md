# 0.6.82.3 broad multi-element radius and Fe Type-85 closure

## Why this milestone exists

The first completed 15-element `0.6.82.2` host run proved that generic ATDB lowering and Type-51 execution reached production, but direct comparison with XSTAR FORTRAN 2.59g exposed two later defects.

For the fixture with `density=1e12`, `rlrad38=1e6`, and `rlogxi=1`, FORTRAN starts at approximately `log(r)=15.50`, `log(xi)=1.00`.  The C++ retained product instead used `log(r)=17.25`, `log(xi)=-2.50`.  The input values themselves were correct.  The product-retention code had reconstructed `radius0` from a JSON key that the public `.par` envelope does not carry and therefore selected a historical `1.778279410038923e17 cm` fallback.  That is a publication/state-ownership error: the accepted controller had already computed and stored the source-derived radius.

The same comparison showed FORTRAN Fe heating/cooling of order 8 in the first thermal row while C++ Fe was effectively zero.  XSTAR 2.59g `ucalc.f90` Type 85 calls `phintfo`, then explicitly zeroes `ans2`, `ans4`, and `ans6` before applying the universal channel swap.  Consequently the final Type-85 contribution is:

```
ans1 = pirt
ans2 = 0
ans3 = 0
ans4 = -piht
ans5 = 0
ans6 = -piht2
```

The shared C++ `source_phintfo_sigma_generic` returns the ordinary already-swapped channel vector `[pirt, rrrt, -rrcl, -piht, -rrcl2, -piht2]`.  The old Type-85 branch negated indices 2 and 4, thereby selecting recombination cooling rather than the source photoionization-heating channels.  `0.6.82.3` takes indices 3 and 5 directly and zeros the same reverse channels as FORTRAN.

## Radius ownership rule

`retain_controller_owned_product_workspaces()` now derives the initial radius from the first live radial zone when that zone carries valid controller geometry:

```
radius0 = first_zone.radius_cm - first_zone.delta_radius_cm
```

Only older diagnostic/qualification states that do not carry valid live geometry may use the prior JSON/historical fallback.  The fix does not recompute physical radius from publication metadata and does not alter the controller's `rread1` implementation.

## Live zone progress

`xstar-cpp --progress text` propagates `XSTAR_CPP_PROGRESS_MODE=text`.  A header is printed before entering the quiet controller and one row is emitted from the already accepted boundary immediately after `production_zone_mark_complete`.  The progress stream uses `stderr` and is flushed per zone, so quiet legacy `stdout` diagnostics do not suppress it.  The old post-controller table is skipped in live-text mode to avoid duplicates.

This progress path is read-only and has no writes into scientific state.

## Qualification boundary

This milestone keeps the accepted historical science revision and all public ABIs unchanged.  It qualifies source semantics on a previously rejected broad-composition surface; it does not silently redefine the previously accepted all-62/Ca/O/C5 boundary.

Local qualification proves source mapping, code ownership, strict compilation, successor compatibility, and aggregate parity.  A real 15-element run with canonical `atdb.fits` remains the physical end-to-end gate.  The earlier broad runtime result (~3215 s C++ versus ~870 s FORTRAN) is recorded as a separate performance problem; Type-50 optimization is intentionally deferred until the corrected science is remeasured.
