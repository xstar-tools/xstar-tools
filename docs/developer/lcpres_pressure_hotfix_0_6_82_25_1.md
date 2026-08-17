# xstar_tools 0.6.82.25.1 — lcpres/pressure host hotfix

## Status

`0.6.82.25` is host-science **REJECT** as a release candidate, but the rejection is localized to STEP/publication and one pure-Python minimum-grid capacity defect. The constant-pressure equations introduced in `.25` are not changed by `.25.1`.

## Host evidence from 0.6.82.25

- `cd_xi1`: C++ ACCEPT.
- `cp_xim2`: C++ REJECT only because STEP `log(N)` differs by up to 0.08 dex. Ionic columns, heating/cooling, Option 1, pressure/density/temperature trajectory and `ntotit` are concordant.
- `cp_xi0`: C++ ACCEPT.
- `cp_xi2`: C++ REJECT because STEP `log(N)` differs by up to 0.05 dex and tiny positive forward optical depths were printed below the FORTRAN `-10.00` floor. Material science remains concordant.
- pure Python `cp_xim2` stops before the first zone with `BremsMapPortError` at `ncn2=999` because the caller did not allocate BREMSMAP's `ncn2m+1` tail row.

## Root cause 1 — cumulative column publication

Canonical `pprint.f90` prints `log10(max(xcol,1.d-10))`. In constant pressure, `xpx=n_H` changes as temperature changes. Therefore cumulative `xcol` cannot be reconstructed at publication as current `n_H * cumulative_depth`.

`.25.1` publishes the retained `RadialZoneState::column_density_cm2` source state for native STEP rows. No radial-step or pressure arithmetic changes.

## Root cause 2 — optical-depth display floor

Canonical `pprint.f90` prints `log10(max(dpthc(direction,nry),1.d-10))`. `.25` logged any positive depth directly, exposing values such as `-14.45` where FORTRAN prints `-10.00`.

`.25.1` applies the literal `1e-10` floor in all live and persisted STEP publication paths.

## Root cause 3 — Python BREMSMAP caller tail

FORTRAN allocates `bremsint` at global `ncn` capacity. `bremsmap.f90` reads row `ncn2m+1`; therefore the public minimum `ncn2=999` with `ncn2m=999` still requires a caller-owned row 1000. Python previously allocated only `ncn2` rows.

`.25.1` allocates `max(ncn2,ncn2m+1)` rows for `bremsint`, materializes the required high-grid tail for BREMSMAP, and slices only the active first `ncn2` rows in full-grid emissivity consumers.

## Frozen science

The `.25` source formulas remain unchanged:

- `lcpres=0 -> lcdd=1` constant density;
- `lcpres=1 -> lcdd=0` constant pressure;
- initial pressure density: `p/(1.38d-12*T4)`;
- runtime pressure density: `p/[REAL4(1.38e-12)*T4]`;
- initial pressure-form Xi radius;
- live radial `xi=L/(nR^2)`;
- `xcol += live_xpx*delr`.

Science revision and ABIs remain frozen.

## Packaging qualification

All 32 `0.6.82.x` milestone test files pass on the candidate tree and independently extracted sdist (101/101 tests). The corrected sdist includes the new hotfix checker, host runner, direct minimum-grid test, technical note, host-validation instructions and handoff. The archive contains no compiled objects/libraries/executables or Python cache artifacts.
