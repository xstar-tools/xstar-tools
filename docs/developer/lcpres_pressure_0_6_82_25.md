# 0.6.82.25 `lcpres` / `pressure` source contract

Canonical reference: attached unmodified FORTRAN XSTAR 2.59g source.

## Public/source mapping

- `lcpres=0` -> `lcdd=1`: constant hydrogen density; `rread1` reads `density`.
- `lcpres=1` -> `lcdd=0`: constant pressure; `rread1` reads `pressure` and does not read the supplied density for science.

## Source equations and ordering

At input, `rread1.f90` uses XPI REAL(4)-promoted values. For constant pressure it sets `xpx = p/(1.38d-12*T4)` and selects the initial radius from `sqrt(L38/(REAL4(12.56)*c*p*10**rlogxi))*REAL4(1e19)`. Thus the input `rlogxi` is the pressure-form ionization parameter used to set the start radius.

During each `calc_hmc_all`, `calc_emisab_all`, and `calc_emis_all`, source XSTAR recomputes `xpx = p/(REAL4(1.38e-12)*max(T4,1d-24))`. The accepted live density is then used by HEATT/transport and retained into the radial state.

Within the radial loop, XSTAR computes ordinary `xi = L38/(r19^2*xpx)` before `xstarcalc`. After the accepted local calculation and radial move, it accumulates `xcol = xcol + xpx*delr` using the live/post-local density.

## 0.6.82.25 implementation rule

C++ and Python must carry this live density through fixed-state input, source STEP, bremsstrahlung/Thomson continuum reconstruction, HEATT, STPCUT, live STEP, terminal state, and FITS publication. The constant-density branch keeps its pre-0.6.82.25 arithmetic wherever the source density is immutable.

## Qualification

The host runner tests H+He+C in one `lcpres=0` reference and pressure-controlled input `rlogxi=-2,0,2`, comparing STEP/material science, Option 1, and `xout_abund1` radius/density/pressure/temperature/electron-fraction trajectories. Material science criterion remains <1%; STEP percentage fields use <1 absolute percentage point.
